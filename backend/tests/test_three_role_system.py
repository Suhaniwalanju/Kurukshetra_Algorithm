import os
import io
import json
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import (
    Base,
    get_db,
    InstituteRecord,
    UserRecord,
    SubjectRecord,
    PublicationRecord,
    DeckRecord,
    QuizAttemptRecord,
    ExerciseProofRecord,
)
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    seed_default_institute_and_admin,
    MAX_FAILED_ATTEMPTS,
)
from backend.publishing import publish_deck_for_subject, verify_no_solutions_in_published, PUBLISHED_BASE_DIR
import backend.template_registry as template_registry

# Setup isolated test database
TEST_DB_PATH = "test_three_roles.db"
if os.path.exists(TEST_DB_PATH):
    try:
        os.remove(TEST_DB_PATH)
    except Exception:
        pass

engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_module():
    # Seed initial database
    db = TestingSessionLocal()
    seed_default_institute_and_admin(db)
    yield
    db.close()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass


def get_token_for(login_id: str, institute_id: str = "dpu") -> str:
    db = TestingSessionLocal()
    user = db.query(UserRecord).filter(
        UserRecord.login_id == login_id,
        UserRecord.institute_id == institute_id
    ).first()
    db.close()
    assert user is not None, f"User {login_id} not found"
    return create_access_token({
        "sub": user.id,
        "institute_id": user.institute_id,
        "role": user.role,
        "display_name": user.display_name,
        "must_change_password": user.must_change_password,
    })


# ---------------------------------------------------------
# 1. AUTH & STUDENT LOGIN TESTS
# ---------------------------------------------------------
def test_student_login_and_hash_security():
    """Verify passwords/passkeys are stored hashed and student login works properly."""
    db = TestingSessionLocal()
    student = db.query(UserRecord).filter(UserRecord.login_id == "STUDENT01").first()
    assert student is not None
    # Password must NEVER be plaintext
    assert not student.password_hash.startswith("Student@123")
    assert student.password_hash.startswith("$2b$") or student.password_hash.startswith("$2a$")
    assert verify_password("Student@123", student.password_hash)
    db.close()

    # Successful login
    res = client.post("/api/auth/login", json={
        "login_id": "STUDENT01",
        "password": "Student@123",
        "institute_id": "dpu"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "student"
    assert "token" in data

    # Wrong passkey
    res_bad = client.post("/api/auth/login", json={
        "login_id": "STUDENT01",
        "password": "WrongPassword!",
        "institute_id": "dpu"
    })
    assert res_bad.status_code == 401

    # Nonexistent student
    res_none = client.post("/api/auth/login", json={
        "login_id": "DOESNOTEXIST",
        "password": "AnyPassword",
        "institute_id": "dpu"
    })
    assert res_none.status_code == 401


def test_rate_limiting_and_lockout():
    """Verify rate-limiting and temporary lockout after repeated failed attempts."""
    db = TestingSessionLocal()
    # Create test user for rate limiting
    rate_user = UserRecord(
        id="user_rate_test",
        institute_id="dpu",
        role="student",
        display_name="Rate Test",
        login_id="ratetest",
        roll_number="ratetest",
        password_hash=hash_password("ValidPassword123!"),
        is_active=True,
    )
    db.add(rate_user)
    db.commit()
    db.close()

    # Fail 5 times
    for i in range(MAX_FAILED_ATTEMPTS):
        res = client.post("/api/auth/login", json={
            "login_id": "ratetest",
            "password": f"wrong_{i}",
            "institute_id": "dpu"
        })
        if i < MAX_FAILED_ATTEMPTS - 1:
            assert res.status_code == 401
        else:
            # 5th attempt triggers lockout
            assert res.status_code == 429
            assert "locked" in res.json()["detail"].lower()

    # Subsequent attempt within lockout window returns 429 even with correct password
    res_locked = client.post("/api/auth/login", json={
        "login_id": "ratetest",
        "password": "ValidPassword123!",
        "institute_id": "dpu"
    })
    assert res_locked.status_code == 429


# ---------------------------------------------------------
# 2. RBAC & ROUTE PROTECTION TESTS
# ---------------------------------------------------------
def test_rbac_rejects_wrong_roles():
    """Verify that every protected route rejects the wrong role."""
    student_token = get_token_for("STUDENT01")
    trainer_token = get_token_for("trainer")

    # 1. Student cannot access Admin overview
    res = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {student_token}"})
    assert res.status_code == 403

    # 2. Student cannot access Admin institute settings
    res = client.get("/api/admin/institute", headers={"Authorization": f"Bearer {student_token}"})
    assert res.status_code == 403

    # 3. Student cannot access Trainer publications or publish route
    res = client.get("/api/trainer/publications", headers={"Authorization": f"Bearer {student_token}"})
    assert res.status_code == 403

    res = client.post("/api/trainer/publish", json={"deck_id": "dummy", "subject_name": "Test"}, headers={"Authorization": f"Bearer {student_token}"})
    assert res.status_code == 403

    # 4. Trainer cannot access Admin routes
    res = client.get("/api/admin/overview", headers={"Authorization": f"Bearer {trainer_token}"})
    assert res.status_code == 403

    res = client.post("/api/admin/trainers", json={"login_id": "t2", "display_name": "T2"}, headers={"Authorization": f"Bearer {trainer_token}"})
    assert res.status_code == 403

    # 5. Unauthenticated request rejected
    res = client.get("/api/admin/overview")
    assert res.status_code == 401


# ---------------------------------------------------------
# 3. CROSS-INSTITUTE ISOLATION TESTS
# ---------------------------------------------------------
def test_cross_institute_data_isolation():
    """Verify that queries are strictly scoped by institute_id so institutes never see each other's data."""
    db = TestingSessionLocal()
    # Create second institute: MIT
    inst_mit = InstituteRecord(
        id="mit",
        name="MIT World Peace University",
        short_name="MIT",
        contact_email="admin@mit.edu",
    )
    db.add(inst_mit)
    student_mit = UserRecord(
        id="mit_stud_1",
        institute_id="mit",
        role="student",
        display_name="MIT Student",
        login_id="MIT001",
        roll_number="MIT001",
        password_hash=hash_password("MitPass@123"),
        is_active=True,
    )
    db.add(student_mit)

    # Add a published item for DPU only
    pub_dpu = PublicationRecord(
        id="pub_dpu_test",
        institute_id="dpu",
        subject_id="sub_dpu_1",
        deck_id="deck_1",
        trainer_id="trainer",
        version=1,
        status="published",
        include_slides=True,
        published_path="storage/published/dpu/java_concurrency/v1"
    )
    db.add(pub_dpu)
    db.commit()
    db.close()

    mit_student_token = get_token_for("MIT001", institute_id="mit")

    # MIT student requests published subjects
    res = client.get("/api/student/subjects", headers={"Authorization": f"Bearer {mit_student_token}"})
    assert res.status_code == 200
    subjects = res.json()
    # Must NOT see DPU's publication!
    for s in subjects:
        assert s["institute_id"] != "dpu"
        assert s["id"] != "pub_dpu_test"

    # MIT student tries to directly request DPU's notes by pub_id
    res_notes = client.get("/api/student/subjects/pub_dpu_test/notes", headers={"Authorization": f"Bearer {mit_student_token}"})
    assert res_notes.status_code in [403, 404]


# ---------------------------------------------------------
# 4. TEMPLATE PNG VALIDATION & SAFE-AREA TESTS
# ---------------------------------------------------------
def test_template_png_validation():
    """Test that uploaded template PNG is validated (format, dimensions, max size) and rejects others."""
    # We need admin token with must_change_password = False
    db = TestingSessionLocal()
    admin = db.query(UserRecord).filter(UserRecord.login_id == "admin").first()
    admin.must_change_password = False
    db.commit()
    db.close()

    admin_token = get_token_for("admin")

    # 1. Non-PNG file rejection
    text_content = io.BytesIO(b"This is not a PNG file")
    res = client.post(
        "/api/admin/institute/template",
        files={"file": ("template.txt", text_content, "text/plain")},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 400
    assert "PNG" in res.json()["detail"]

    # 2. Oversized file rejection (> 10MB)
    fake_large_png = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024))
    res = client.post(
        "/api/admin/institute/template",
        files={"file": ("big.png", fake_large_png, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 400
    assert "10 MB" in res.json()["detail"]

    # 3. Valid 1920x1080 PNG upload
    img = Image.new("RGB", (1920, 1080), color=(18, 24, 38))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    res = client.post(
        "/api/admin/institute/template",
        files={"file": ("institute_template.png", img_byte_arr, "image/png")},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 4. Safe-area settings update
    res = client.put(
        "/api/admin/institute",
        json={
            "safe_area_top": 12.0,
            "safe_area_bottom": 12.0,
            "safe_area_left": 8.0,
            "safe_area_right": 8.0,
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 200
    assert res.json()["institute"]["safe_area_top"] == 12.0

    # 5. Live preview reflects uploaded template & safe area
    res_prev = client.get("/api/admin/institute/preview", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_prev.status_code == 200
    assert res_prev.headers["content-type"] == "image/png"


# ---------------------------------------------------------
# 5. PUBLISH, RE-PUBLISH (VERSIONING) & UNPUBLISH TESTS
# ---------------------------------------------------------
def test_publish_republish_and_unpublish():
    """Test publish, re-publish (version increment) and unpublish."""
    trainer_token = get_token_for("trainer")

    # Create dummy deck in DB
    db = TestingSessionLocal()
    deck = DeckRecord(
        id="deck_test_pub",
        college="DPU",
        professor_name="Prof. Sharma",
        topic="Python Data Structures",
        student_level="Beginner",
        session_length=20,
        tech="Python",
        tech_version="3.12",
        institute_id="dpu",
        trainer_id="trainer",
        status="completed",
        verified=True,
        slides_json=json.dumps([{
            "slide_id": 1,
            "title": "Lists & Tuples",
            "bullets": ["Sequential data structures"],
            "code": "x = [1, 2, 3]\nprint(len(x))"
        }]),
        materials_status="ready",
        student_notes_json=json.dumps([
            {"slide_id": 1, "note": "Lists are mutable sequences in Python."}
        ]),
        quiz_json=json.dumps([
            {
                "question": "What is the complexity of list append?",
                "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"],
                "correct_answer": "O(1)",
                "explanation": "List append in Python is amortized O(1)."
            }
        ]),
    )
    db.add(deck)
    db.commit()

    ex = ExerciseProofRecord(
        id="ex_proof_1",
        deck_id="deck_test_pub",
        slide_id=1,
        exercise_ref="ex_01",
        title="Reverse a List",
        problem_statement="Write reverse_list function.",
        starter_code="def reverse_list(lst):\n    # TODO\n    pass",
        test_code="assert reverse_list([1, 2]) == [2, 1]",
        reference_solution="def reverse_list(lst):\n    return lst[::-1]",
        naive_solution="def reverse_list(lst):\n    return []",
        status="verified",
        mutation_score=100.0,
    )
    db.add(ex)
    db.commit()
    db.close()

    # 1. First Publish -> Version 1
    res1 = client.post(
        "/api/trainer/publish",
        json={
            "deck_id": "deck_test_pub",
            "subject_name": "Python Data Structures",
            "include_slides": True,
        },
        headers={"Authorization": f"Bearer {trainer_token}"}
    )
    if res1.status_code != 200:
        print("RES1 ERROR:", res1.json())
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["version"] == 1
    assert data1["status"] == "published"
    pub1_id = data1["publication_id"]

    # 2. Re-publish the same subject -> Version 2
    res2 = client.post(
        "/api/trainer/publish",
        json={
            "deck_id": "deck_test_pub",
            "subject_name": "Python Data Structures",
            "include_slides": True,
        },
        headers={"Authorization": f"Bearer {trainer_token}"}
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["version"] == 2
    pub2_id = data2["publication_id"]

    # Verify student only sees the latest active version
    student_token = get_token_for("STUDENT01")
    res_stud = client.get("/api/student/subjects", headers={"Authorization": f"Bearer {student_token}"})
    assert res_stud.status_code == 200
    subjects = res_stud.json()
    python_sub = next((s for s in subjects if s["folder_slug"] == "python_data_structures"), None)
    assert python_sub is not None
    assert python_sub["version"] == 2

    # 3. Unpublish Version 2
    res_unpub = client.post(
        f"/api/trainer/unpublish/{pub2_id}",
        headers={"Authorization": f"Bearer {trainer_token}"}
    )
    assert res_unpub.status_code == 200
    assert res_unpub.json()["status"] == "unpublished"

    # Verify student no longer sees it in available subjects
    res_stud_after = client.get("/api/student/subjects", headers={"Authorization": f"Bearer {student_token}"})
    subjects_after = res_stud_after.json()
    python_sub_after = next((s for s in subjects_after if s["folder_slug"] == "python_data_structures"), None)
    assert python_sub_after is None


# ---------------------------------------------------------
# 6. ZERO-SOLUTIONS SECURITY SCAN TEST
# ---------------------------------------------------------
def test_published_folder_contains_no_solutions():
    """Verify that published folder contains no answers, no reference solutions, no naive solutions, no proof reports."""
    # Publish fresh content
    trainer_token = get_token_for("trainer")
    res = client.post(
        "/api/trainer/publish",
        json={
            "deck_id": "deck_test_pub",
            "subject_name": "Python Data Structures",
            "include_slides": True,
        },
        headers={"Authorization": f"Bearer {trainer_token}"}
    )
    assert res.status_code == 200
    published_path = res.json()["published_path"]

    assert os.path.exists(published_path)
    # Run the comprehensive anti-leak scanner
    assert verify_no_solutions_in_published(published_path) is True

    # Ensure exercises folder only has task, starter, and tests
    ex_dir = os.path.join(published_path, "exercises", "exercise_01")
    assert os.path.exists(ex_dir)
    files = os.listdir(ex_dir)
    assert "task.md" in files
    assert "starter.py" in files or "starter_code.py" in files
    assert "test_exercise.py" in files or "test_code.py" in files
    assert "reference_solution.py" not in files
    assert "naive_solution.py" not in files
    assert "proof_report.json" not in files

    # Ensure quiz questions file does not contain 'correct_answer' or 'explanation'
    quiz_file = os.path.join(published_path, "quiz", "quiz.json")
    assert os.path.exists(quiz_file)
    with open(quiz_file, "r") as f:
        quiz_content = f.read()
    assert "correct_answer" not in quiz_content
    assert "explanation" not in quiz_content


# ---------------------------------------------------------
# 7. QUIZ EVALUATION & SERVER-SIDE GRADING TEST
# ---------------------------------------------------------
def test_quiz_answers_server_side_only():
    """Quiz questions do not leak answers. Submission grades on server and saves attempt."""
    student_token = get_token_for("STUDENT01")

    # Get student subjects
    res_sub = client.get("/api/student/subjects", headers={"Authorization": f"Bearer {student_token}"})
    assert res_sub.status_code == 200
    subjects = res_sub.json()
    python_sub = next(s for s in subjects if s["folder_slug"] == "python_data_structures")
    pub_id = python_sub["id"]

    # 1. Fetch student quiz
    res_quiz = client.get(f"/api/student/subjects/{pub_id}/quiz", headers={"Authorization": f"Bearer {student_token}"})
    assert res_quiz.status_code == 200
    quiz_data = res_quiz.json()
    assert len(quiz_data) > 0
    # Crucial assertion: NO answer key in payload
    for q in quiz_data:
        assert "correct_answer" not in q
        assert "explanation" not in q

    # 2. Submit student answers
    res_submit = client.post(
        f"/api/student/subjects/{pub_id}/quiz/submit",
        json={"answers": {0: "O(1)"}},
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert res_submit.status_code == 200
    grade = res_submit.json()
    assert grade["score"] == 1
    assert grade["total"] == 1
    assert grade["percentage"] == 100.0
    # Answers and explanations revealed only AFTER submission
    assert len(grade["results"]) == 1
    assert grade["results"][0]["correct_answer"] == "O(1)"
    assert "explanation" in grade["results"][0]

    # 3. Check past attempts history
    res_attempts = client.get(
        f"/api/student/subjects/{pub_id}/quiz/attempts",
        headers={"Authorization": f"Bearer {student_token}"}
    )
    assert res_attempts.status_code == 200
    attempts = res_attempts.json()
    assert len(attempts) >= 1
    assert attempts[0]["score"] == 1
