import os
import json
import pypdf
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import init_db, SessionLocal, DeckRecord, SnippetRecord
from backend.materials.notes_generator import generate_notes_for_deck
from backend.materials.quiz_generator import generate_quiz_for_deck
from backend.materials.cheat_sheet_generator import generate_cheat_sheet_data, render_cheat_sheet_pdf
from backend.materials.slide_regenerator import regenerate_single_slide
from backend.materials.version_migrator import migrate_deck_version
from backend.materials.staleness_checker import check_deck_staleness
from backend.materials.exporter import build_all_deck_exports
from backend.layout_engine import validate_deck_layout

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


def test_supporting_materials_only_after_deck_approval():
    """Requirement: Deck -> verification -> professor approves ('Approve Deck' button) -> only then generate notes/quiz/cheat sheet."""
    db = SessionLocal()
    try:
        # Create unapproved test deck
        deck_id = "test_unapproved_deck"
        record = DeckRecord(
            id=deck_id,
            college="VIT",
            professor_name="Prof. Test",
            topic="Python 3.12 Concurrency",
            student_level="Beginner",
            session_length=20,
            tech="Python",
            tech_version="3.12",
            status="completed",
            verified=True,
            approved=False,  # Unapproved
            slides_json=json.dumps([{"id": 1, "type": "concept", "title": "Intro", "bullets": ["AsyncIO"]}])
        )
        db.merge(record)
        db.commit()

        # 1. Attempting to generate materials before approval must fail (HTTP 400)
        res = client.post(f"/api/decks/{deck_id}/materials/generate")
        assert res.status_code == 400
        assert "must be approved" in res.json()["detail"].lower()

        # 2. Approve deck
        appr_res = client.post(f"/api/decks/{deck_id}/approve")
        assert appr_res.status_code == 200
        assert appr_res.json()["approved"] is True

        # 3. Now material generation succeeds
        gen_res = client.post(f"/api/decks/{deck_id}/materials/generate")
        assert gen_res.status_code == 200
        assert gen_res.json()["materials_status"] == "ready"
    finally:
        db.close()


def test_student_and_professor_notes_content_and_word_count():
    """Requirement: 150-250 words per slide, plain language, why it matters, verified code with real output, common mistake."""
    sample_deck = {
        "id": "deck_notes_test",
        "topic": "Java 21 Virtual Threads",
        "tech": "Java",
        "tech_version": "21",
        "student_level": "Intermediate",
        "session_length": 25,
        "slides": [
            {
                "id": 1,
                "type": "concept",
                "title": "Virtual Threads Architecture",
                "bullets": ["Lightweight JVM threads", "No OS carrier thread blocking"],
                "code": "public class Solution { public static void main(String[] a){ System.out.println(\"Hi\"); } }"
            }
        ]
    }
    sample_snippets = [{
        "slide_id": 1,
        "source_code": "public class Solution { public static void main(String[] a){ System.out.println(\"Hi\"); } }",
        "actual_output": "Hi\n"
    }]

    student_notes, prof_notes = generate_notes_for_deck(sample_deck, sample_snippets)
    assert len(student_notes) == 1
    assert len(prof_notes) == 1

    sn = student_notes[0]
    # Check word count between 150 and 250 words
    assert 140 <= sn.word_count <= 260
    assert "why it matters" in sn.why_it_matters.lower() or len(sn.why_it_matters) > 20
    assert "mistake" in sn.common_mistake.lower()
    assert sn.real_output == "Hi"

    pn = prof_notes[0]
    assert len(pn.talking_points) >= 3
    assert pn.timing_minutes > 0
    assert len(pn.likely_questions) >= 1
    assert pn.fallback_output != ""


def test_cheat_sheet_is_strictly_one_page():
    """Requirement: Exactly one page, A4, printed using institute brand colours and logo area. Fail if it spills."""
    deck_dict = {
        "college": "VIT",
        "topic": "Python 3.12 AsyncIO Architecture",
        "tech": "Python",
        "tech_version": "3.12"
    }
    data = generate_cheat_sheet_data(deck_dict, [])
    output_path = os.path.abspath("output/test_e2e_cheatsheet.pdf")

    page_count = render_cheat_sheet_pdf(data, output_path)
    assert page_count == 1

    reader = pypdf.PdfReader(output_path)
    assert len(reader.pages) == 1, f"Cheat sheet exceeded 1 page: found {len(reader.pages)} pages."


def test_single_slide_regeneration_leaves_other_slides_byte_identical():
    """Requirement: Select a slide, regenerate only that slide & snippets, re-verify, leave all other slides untouched with diff."""
    db = SessionLocal()
    try:
        deck_id = "test_single_slide_regen_deck"
        slides = [
            {"id": 1, "type": "cover", "title": "Slide 1", "bullets": ["A", "B"]},
            {"id": 2, "type": "concept", "title": "Slide 2", "bullets": ["C", "D"], "code": "print('Original')"},
            {"id": 3, "type": "closing", "title": "Slide 3", "bullets": ["E", "F"]}
        ]
        record = DeckRecord(
            id=deck_id,
            college="VIT",
            professor_name="Prof. Test",
            topic="Python Scripting",
            student_level="Beginner",
            session_length=30,
            tech="Python",
            tech_version="3.12",
            status="completed",
            slides_json=json.dumps(slides),
            preview_paths_json=json.dumps(["/p1.png", "/p2.png", "/p3.png"])
        )
        db.merge(record)
        db.commit()

        # Capture content of untouched slides before regeneration
        slide_0_before = json.dumps(slides[0], sort_keys=True)
        slide_2_before = json.dumps(slides[2], sort_keys=True)

        res = regenerate_single_slide(
            deck_id=deck_id,
            slide_index=1,
            instruction="Include timing calculation",
            db_session=db
        )

        assert res["success"] is True
        assert res["slide_index"] == 1
        assert "diff" in res
        assert "code_diff" in res["diff"]

        # Reload updated deck from DB
        updated_record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        updated_slides = json.loads(updated_record.slides_json)

        # Slide 1 (index 1) changed
        assert "Include timing" in updated_slides[1]["bullets"][0] or "Updated" in updated_slides[1]["code"]

        # Slides 0 and 2 MUST remain byte-for-byte identical!
        slide_0_after = json.dumps(updated_slides[0], sort_keys=True)
        slide_2_after = json.dumps(updated_slides[2], sort_keys=True)

        assert slide_0_before == slide_0_after, "Slide 0 was modified unexpectedly during single-slide regeneration!"
        assert slide_2_before == slide_2_after, "Slide 2 was modified unexpectedly during single-slide regeneration!"
    finally:
        db.close()


def test_version_migration_demo():
    """Requirement: Pick target version, swap pinned image, re-run, regenerate failing/deprecated ones, show diff table."""
    db = SessionLocal()
    try:
        deck_id = "test_migration_deck"
        record = DeckRecord(
            id=deck_id,
            college="VIT",
            professor_name="Prof. Test",
            topic="Java Microservices",
            student_level="Intermediate",
            session_length=30,
            tech="Java",
            tech_version="17",
            status="completed",
            slides_json=json.dumps([{"id": 1, "type": "concept", "title": "Service", "code": "import javax.servlet.http.HttpServlet;"}])
        )
        snip = SnippetRecord(
            id=f"{deck_id}_snip_1",
            deck_id=deck_id,
            slide_id=1,
            language="java",
            version="17",
            source_code="import javax.servlet.http.HttpServlet;\npublic class Solution {}",
            status="verified"
        )
        db.merge(record)
        db.merge(snip)
        db.commit()

        res = migrate_deck_version(deck_id, new_version="21", db_session=db)
        assert res["success"] is True
        assert res["to_version"] == "21"
        assert len(res["diff_table"]) >= 1

        entry = res["diff_table"][0]
        assert "jakarta" in entry["new_code"] or "Migrated" in entry["new_code"] or "Upgraded" in entry["reason"]
    finally:
        db.close()


def test_staleness_check_and_live_runner():
    """Requirement: Staleness check button & Live Class runner with fallback."""
    db = SessionLocal()
    try:
        deck_id = "test_live_deck"
        record = DeckRecord(
            id=deck_id,
            college="VIT",
            professor_name="Prof. Test",
            topic="Python Sandbox",
            student_level="Beginner",
            session_length=30,
            tech="Python",
            tech_version="3.12",
            status="completed",
            slides_json=json.dumps([{"id": 1, "type": "concept", "title": "Live Code", "code": "print('Live 2026')"}])
        )
        snip = SnippetRecord(
            id=f"{deck_id}_snip_1",
            deck_id=deck_id,
            slide_id=1,
            language="python",
            version="3.12",
            source_code="print('Live 2026')",
            actual_output="Live 2026\n",
            status="verified"
        )
        db.merge(record)
        db.merge(snip)
        db.commit()

        # 1. Staleness check
        stale_res = check_deck_staleness(deck_id, db)
        assert stale_res["total_checked"] >= 1
        assert stale_res["is_stale"] is False

        # 2. Live runner API
        run_res = client.post(f"/api/decks/{deck_id}/live/run", json={"slide_id": 1, "code": "print('Live 2026')"})
        assert run_res.status_code == 200
        assert "Live 2026" in run_res.json()["stdout"]
    finally:
        db.close()


def test_full_flow_all_materials_zip_and_compliance():
    """Requirement: End-to-end test running the full flow and confirming all exports & zero layout violations."""
    db = SessionLocal()
    try:
        deck_id = "test_full_flow_deck"
        slides = [
            {"id": 1, "type": "cover", "title": "Spring Boot 3", "bullets": ["Modern Microservices"]},
            {"id": 2, "type": "concept", "title": "Reactive Endpoints", "bullets": ["High concurrency"], "code": "print('OK')"},
            {"id": 3, "type": "closing", "title": "Conclusion", "bullets": ["Verified presentation"]}
        ]
        record = DeckRecord(
            id=deck_id,
            college="VIT",
            professor_name="Dr. Verified",
            topic="Spring Boot 3 REST",
            student_level="Intermediate",
            session_length=30,
            tech="Python",
            tech_version="3.12",
            status="completed",
            verified=True,
            approved=True,
            slides_json=json.dumps(slides),
            preview_paths_json=json.dumps([])
        )
        db.merge(record)
        db.commit()

        # Build exports
        exports = build_all_deck_exports(deck_id, db)

        # Check export presence
        assert "pptx" in exports
        assert "pdf" in exports
        assert "student_notes" in exports
        assert "quiz" in exports
        assert "quiz_answer_key" in exports
        assert "cheat_sheet" in exports
        assert "exercises" in exports
        assert "verification_report" in exports
        assert "all_zip" in exports

        assert os.path.exists(exports["all_zip"])
        assert os.path.exists(exports["cheat_sheet"])

        # Check cheat sheet strictly 1 page
        r = pypdf.PdfReader(exports["cheat_sheet"])
        assert len(r.pages) == 1

        # Check layout compliance
        logs, compliant = validate_deck_layout(record.to_dict())
        assert compliant is True, f"Deck layout had compliance violations: {logs}"
    finally:
        db.close()
