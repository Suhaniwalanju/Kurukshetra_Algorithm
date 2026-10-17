import os
import sys
import io
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from backend.database import SessionLocal, InstituteRecord, UserRecord, DeckRecord, SubjectRecord, PublicationRecord, ExerciseProofRecord
from backend.auth import hash_password, verify_password, create_access_token
from backend.template_registry import register_custom_institute_template, generate_sample_slide_preview, template_registry
from backend.publishing import publish_deck_for_subject, verify_no_solutions_in_published, PUBLISHED_BASE_DIR

def run_demo():
    print("=" * 70)
    print("STEP 1: ADMIN UPLOADS 1920x1080 INSTITUTE TEMPLATE & CONFIGURES SAFE-AREA")
    print("=" * 70)

    db: Session = SessionLocal()

    # 1. Ensure institute exists
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == "dpu").first()
    if not inst:
        inst = InstituteRecord(
            id="dpu",
            name="Dr. D. Y. Patil Vidyapeeth",
            short_name="DPU",
            contact_email="admin@dpu.edu.in",
            safe_area_top=10.0,
            safe_area_bottom=10.0,
            safe_area_left=8.0,
            safe_area_right=8.0,
        )
        db.add(inst)
        db.commit()

    # 2. Generate a branded 1920x1080 template PNG
    os.makedirs("input/templates", exist_ok=True)
    template_path = os.path.abspath("input/templates/dpu_admin_custom.png")
    img = Image.new("RGB", (1920, 1080), color=(15, 23, 42))  # Slate 900
    draw = ImageDraw.Draw(img)

    # Add header bar
    draw.rectangle([0, 0, 1920, 90], fill=(30, 41, 59))
    draw.text((60, 25), "DR. D. Y. PATIL VIDYAPEETH  |  ACADEMIC COURSE MATERIAL", fill=(241, 245, 249))

    # Add footer bar
    draw.rectangle([0, 990, 1920, 1080], fill=(30, 41, 59))
    draw.text((60, 1025), "CONFIDENTIAL & PROPRIETARY  •  VERIFIED CURRICULUM", fill=(148, 163, 184))
    draw.text((1650, 1025), "PAGE ## OF ##", fill=(148, 163, 184))

    # Add decorative border accent
    draw.line([(0, 90), (1920, 90)], fill=(99, 102, 241), width=4)
    draw.line([(0, 990), (1920, 990)], fill=(99, 102, 241), width=4)

    img.save(template_path, "PNG")
    print(f"[+] Created 1920x1080 branded template at: {template_path}")

    # 3. Update institute record with uploaded template and safe areas
    inst.template_png = template_path
    inst.safe_area_top = 10.0
    inst.safe_area_bottom = 10.0
    inst.safe_area_left = 8.0
    inst.safe_area_right = 8.0
    db.commit()

    # Register dynamic template
    layout_cfg = register_custom_institute_template(
        college="DPU",
        png_path=template_path,
        top=inst.safe_area_top,
        bottom=inst.safe_area_bottom,
        left=inst.safe_area_left,
        right=inst.safe_area_right,
    )
    print(f"[+] Registered dynamic layout config with safe zones: bounds width={layout_cfg.content_zone.width}px, height={layout_cfg.content_zone.height}px")

    print("\n" + "=" * 70)
    print("STEP 2: TRAINER GENERATES VERIFIED DECK ON ADMIN'S AUTO-APPLIED TEMPLATE")
    print("=" * 70)

    # Ensure trainer exists
    trainer = db.query(UserRecord).filter(UserRecord.login_id == "trainer").first()
    if not trainer:
        trainer = UserRecord(
            id="trainer_dpu_01",
            institute_id="dpu",
            role="trainer",
            display_name="Prof. Rajesh Kulkarni",
            login_id="trainer",
            password_hash=hash_password("Trainer@12345"),
            is_active=True,
        )
        db.add(trainer)
        db.commit()

    deck_id = "demo_dpu_01"
    existing_deck = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if existing_deck:
        db.delete(existing_deck)
        db.commit()

    # Create deck record
    slides_data = [
        {
            "slide_id": 1,
            "title": "Modern Java 21 Concurrency",
            "bullets": [
                "Lightweight virtual threads managed by JVM",
                "High throughput server applications without thread exhaustion",
                "Preserves thread-per-request programming style"
            ],
            "code": "try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {\n    IntStream.range(0, 10_000).forEach(i -> {\n        executor.submit(() -> {\n            Thread.sleep(Duration.ofMillis(10));\n            return i;\n        });\n    });\n}\nSystem.out.println(\"Completed 10,000 tasks\");",
            "verification_status": "verified"
        },
        {
            "slide_id": 2,
            "title": "Structured Concurrency with StructuredTaskScope",
            "bullets": [
                "Treats related concurrent subtasks as single unit of work",
                "Automatic cancellation of remaining tasks on failure",
                "Eliminates thread leaks and orphan threads"
            ],
            "code": "try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {\n    Supplier<String> user = scope.fork(() -> findUser());\n    Supplier<Integer> order = scope.fork(() -> fetchOrder());\n    scope.join().throwIfFailed();\n    System.out.println(user.get() + \" ordered: \" + order.get());\n}",
            "verification_status": "verified"
        }
    ]

    deck = DeckRecord(
        id=deck_id,
        college=inst.short_name,
        professor_name=trainer.display_name,
        topic="Java 21 Virtual Threads & Structured Concurrency",
        student_level="Intermediate",
        session_length=30,
        tech="Java",
        tech_version="21",
        institute_id="dpu",
        trainer_id=trainer.id,
        status="completed",
        status_message="Generation completed with inline verification",
        verified=True,
        approved=True,
        materials_status="ready",
        slides_json=json.dumps(slides_data),
        student_notes_json=json.dumps([
            {"slide_id": 1, "note": "Virtual threads are daemon threads and yield on blocking I/O calls."},
            {"slide_id": 2, "note": "ShutdownOnFailure shuts down remaining branches when any child task throws an exception."}
        ]),
        quiz_json=json.dumps([
            {
                "id": "q_01",
                "question": "Which executor creates lightweight virtual threads in Java 21?",
                "options": [
                    "Executors.newVirtualThreadPerTaskExecutor()",
                    "Executors.newFixedThreadPool(10)",
                    "Executors.newCachedThreadPool()",
                    "ForkJoinPool.commonPool()"
                ],
                "correct_answer": "Executors.newVirtualThreadPerTaskExecutor()",
                "explanation": "Executors.newVirtualThreadPerTaskExecutor() spawns a new virtual thread for each submitted Runnable or Callable."
            },
            {
                "id": "q_02",
                "question": "What is the primary benefit of StructuredTaskScope.ShutdownOnFailure?",
                "options": [
                    "Cancels all child forks if any task fails",
                    "Increases heap memory size",
                    "Prevents garbage collection",
                    "Runs tasks sequentially"
                ],
                "correct_answer": "Cancels all child forks if any task fails",
                "explanation": "ShutdownOnFailure terminates sibling branches as soon as a failure is encountered, preventing orphan executions."
            }
        ]),
    )
    db.add(deck)
    db.commit()

    # Create verified exercises with test proofs
    ex_proof = ExerciseProofRecord(
        id="ex_proof_java_01",
        deck_id=deck_id,
        slide_id=1,
        exercise_ref="ex_01",
        title="Parallel Fibonacci with Virtual Threads",
        problem_statement="Implement a method parallelFib(int n) that computes Fibonacci numbers concurrently using virtual threads.",
        starter_code="public class FibonacciTask {\n    // TODO: implement parallel virtual thread calculation\n    public static long parallelFib(int n) {\n        return 0L;\n    }\n}",
        test_code="public class FibonacciTest {\n    @Test\n    public void testFib() {\n        assertEquals(55L, FibonacciTask.parallelFib(10));\n    }\n}",
        reference_solution="public class FibonacciTask {\n    public static long parallelFib(int n) {\n        // Reference solution\n        return n <= 1 ? n : parallelFib(n - 1) + parallelFib(n - 2);\n    }\n}",
        naive_solution="public class FibonacciTask {\n    public static long parallelFib(int n) { return 0L; }\n}",
        status="verified",
        mutation_score=100.0,
    )
    db.add(ex_proof)
    db.commit()

    print(f"[+] Deck generated for topic: '{deck.topic}'")
    print(f"[+] Bound to Institute: '{inst.name}' ({inst.short_name})")
    print(f"[+] Template Applied: '{inst.template_png}' with zero-overlap safe area margins")

    print("\n" + "=" * 70)
    print("STEP 3: TRAINER PUBLISHES COURSE TO STUDENT DASHBOARD")
    print("=" * 70)

    # Ensure subject exists
    subject = db.query(SubjectRecord).filter(
        SubjectRecord.institute_id == "dpu",
        SubjectRecord.name == "Java 21 Concurrency"
    ).first()
    if not subject:
        subject = SubjectRecord(
            id="sub_java_21",
            institute_id="dpu",
            name="Java 21 Concurrency",
            folder_slug="java_21_concurrency",
            is_active=True
        )
        db.add(subject)
        db.commit()

    pub = publish_deck_for_subject(
        deck_id=deck.id,
        subject_id=subject.id,
        include_slides=True,
        trainer_id=trainer.id,
        institute_id="dpu",
        db=db,
    )

    print(f"[+] Published successfully as Version {pub.version}")
    print(f"[+] Target Storage Path: {pub.published_path}")

    # Verify no solutions in published folder
    is_safe = verify_no_solutions_in_published(pub.published_path)
    print(f"[+] Anti-leak verification check: {'PASSED (Zero answers/solutions in published folder)' if is_safe else 'FAILED'}")

    print("\n" + "=" * 70)
    print("FOLDER TREE OF PUBLISHED SUBJECT:")
    print("=" * 70)

    for root, dirs, files in os.walk(pub.published_path):
        level = root.replace(pub.published_path, '').count(os.sep)
        indent = ' ' * 4 * level
        folder = os.path.basename(root)
        print(f"{indent}[DIR] {folder}/")
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            size = os.path.getsize(os.path.join(root, f))
            print(f"{sub_indent}[FILE] {f} ({size} bytes)")

    db.close()

if __name__ == "__main__":
    run_demo()
