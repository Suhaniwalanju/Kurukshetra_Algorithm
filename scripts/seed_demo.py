import os
import sys
import json
import uuid
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import init_db, SessionLocal, DeckRecord, SnippetRecord, ExerciseProofRecord, VerificationRunRecord
from backend.template_registry import template_registry
from backend.pptx_builder import pptx_builder
from backend.slide_renderer import slide_renderer
from backend.layout_engine import layout_engine
from backend.schemas import Slide, SlideCode
from backend.materials.notes_generator import generate_notes_for_deck
from backend.materials.quiz_generator import generate_quiz_for_deck
from backend.materials.cheat_sheet_generator import generate_cheat_sheet_data, render_cheat_sheet_pdf
from backend.materials.exporter import build_all_deck_exports


def seed_demo_deck():
    print("=" * 70)
    print(" Seeding Sample Java 21 + Spring Boot 3 Deck with 2 College Templates")
    print("=" * 70)

    # 1. Initialize DB & scan templates
    init_db()
    colleges = template_registry.list_colleges()
    college_names = [c["college"] for c in colleges]
    print(f"[OK] Registered College Templates: {', '.join(college_names)}")

    db = SessionLocal()
    try:
        deck_id = "demo_java21_spring"

        # Check if already exists
        existing = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        if existing:
            db.delete(existing)
            db.commit()

        college = "VIT" if "VIT" in college_names else college_names[0]
        topic = "Java 21 & Spring Boot 3 Microservices Architecture"
        tech = "Java"
        tech_version = "21"
        professor_name = "Dr. Arvind Sharma"

        config = template_registry.get_config(college)

        # 2. Define Sample Slides
        slide_objs = [
            Slide(
                id=1,
                type="cover",
                title=topic,
                bullets=[
                    "High-throughput microservices using Virtual Threads",
                    "Spring Boot 3 native compilation patterns",
                    "Deterministic verification & sandbox safety"
                ]
            ),
            Slide(
                id=2,
                type="concept",
                title="Java 21 Virtual Threads Architecture",
                bullets=[
                    "Lightweight user-mode threads managed by JVM",
                    "Zero carrier thread pinning on blocking I/O",
                    "Millions of concurrent HTTP request handlers"
                ],
                code=SlideCode(
                    language="java",
                    version="21",
                    source=(
                        "public class Solution {\n"
                        "    public static void main(String[] args) throws Exception {\n"
                        "        var thread = Thread.startVirtualThread(() -> {\n"
                        "            System.out.println(\"Virtual Thread Executing!\");\n"
                        "        });\n"
                        "        thread.join();\n"
                        "    }\n"
                        "}"
                    ),
                    expected_output="Virtual Thread Executing!\n"
                )
            ),
            Slide(
                id=3,
                type="concept",
                title="Spring Boot 3 RESTful Endpoint",
                bullets=[
                    "Jakarta EE 10 namespace standards",
                    "Embedded Tomcat virtual thread executor",
                    "Observability via Micrometer tracing"
                ],
                code=SlideCode(
                    language="java",
                    version="21",
                    source=(
                        "public class Solution {\n"
                        "    public static void main(String[] args) {\n"
                        "        String status = \"UP\";\n"
                        "        int port = 8080;\n"
                        "        System.out.println(\"Service: \" + status + \" on: \" + port);\n"
                        "    }\n"
                        "}"
                    ),
                    expected_output="Service: UP on: 8080\n"
                )
            ),
            Slide(
                id=4,
                type="exercise",
                title="Exercise: Structured Concurrency Scope",
                bullets=[
                    "Fork concurrent user and order service queries",
                    "Ensure fail-fast cancellation on task failure",
                    "Synthesize results deterministically"
                ],
                code=SlideCode(
                    language="java",
                    version="21",
                    source=(
                        "public class Solution {\n"
                        "    public static void main(String[] args) {\n"
                        "        int res = 42;\n"
                        "        System.out.println(\"Synthesized: \" + res);\n"
                        "    }\n"
                        "}"
                    ),
                    expected_output="Synthesized: 42\n"
                )
            ),
            Slide(
                id=5,
                type="closing",
                title="Summary & Key Takeaways",
                bullets=[
                    "Virtual threads replace reactive complexity",
                    "Spring Boot 3 modernizes enterprise Java",
                    "All presentation snippets verified by execution"
                ]
            )
        ]

        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output", deck_id))
        os.makedirs(output_dir, exist_ok=True)
        pptx_path = os.path.join(output_dir, f"{deck_id}.pptx")

        print("[...] Executing collision-free layout engine...")
        final_slides, plans, layout_logs = layout_engine.layout_deck(
            slide_objs, config, professor_name, max_attempts=3
        )

        print("[...] Building PowerPoint presentation...")
        pptx_builder.build_deck(final_slides, plans, config, professor_name, pptx_path)

        print("[...] Rendering 1080p slide previews...")
        previews_dir = os.path.join(output_dir, "previews")
        preview_files = slide_renderer.render_deck_previews(
            pptx_path, final_slides, plans, config, professor_name, previews_dir
        )
        preview_urls = [f"/static/output/{deck_id}/previews/{os.path.basename(p)}" for p in preview_files]

        slides_data = [s.model_dump() for s in final_slides]

        # 4. Create Deck Record in DB
        record = DeckRecord(
            id=deck_id,
            college=college,
            professor_name=professor_name,
            topic=topic,
            student_level="Intermediate",
            session_length=30,
            tech=tech,
            tech_version=tech_version,
            status="completed",
            status_message="Seeded sample presentation verified successfully",
            slides_json=json.dumps(slides_data),
            layout_logs_json=json.dumps(["Zero overlap verified", "0.2 inch gutter respected"]),
            pptx_path=pptx_path,
            output_dir=output_dir,
            preview_paths_json=json.dumps(preview_urls),
            verified=True,
            approved=True,
            approved_at=datetime.utcnow(),
            materials_status="generating"
        )
        db.add(record)
        db.commit()

        # 5. Add Snippet Records
        def get_source_str(c):
            if isinstance(c, dict):
                return c.get("source", "")
            if hasattr(c, "source"):
                return c.source
            return str(c) if c else ""

        snip1 = SnippetRecord(
            id=f"{deck_id}_snip_2",
            deck_id=deck_id,
            slide_id=2,
            language="java",
            version="21",
            source_code=get_source_str(slides_data[1]["code"]),
            actual_output="Virtual Thread Executing!\n",
            status="verified"
        )
        snip2 = SnippetRecord(
            id=f"{deck_id}_snip_3",
            deck_id=deck_id,
            slide_id=3,
            language="java",
            version="21",
            source_code=get_source_str(slides_data[2]["code"]),
            actual_output="Service: UP on: 8080\n",
            status="verified"
        )
        db.add_all([snip1, snip2])
        db.commit()

        # 6. Add Exercise Proof Record
        proof = ExerciseProofRecord(
            id=f"{deck_id}_proof_4",
            deck_id=deck_id,
            slide_id=4,
            exercise_ref="Exercise: Structured Concurrency Scope",
            problem_statement="Synthesize concurrent tasks using StructuredTaskScope",
            starter_code="// Complete task synthesis\npublic class Solution { public static void main(String[] args) {} }",
            test_code="// Test assertions\nassert res == 42;",
            reference_solution=get_source_str(slides_data[3]["code"]),
            reference_passed=True,
            naive_solution="// Incomplete\npublic class Solution { public static void main(String[] args) { System.out.println(0); } }",
            naive_failed=True,
            mutants_json=json.dumps([{"mutant": "Wrong return value", "killed": True}, {"mutant": "Timeout delay", "killed": True}]),
            mutation_score=100.0
        )
        db.add(proof)
        db.commit()

        # 7. Generate Supporting Materials (Phase 3)
        print("[...] Generating Student Notes & Professor Notes...")
        deck_dict = record.to_dict()
        snippets_list = [snip1.to_dict(), snip2.to_dict()]
        student_notes, prof_notes = generate_notes_for_deck(deck_dict, snippets_list)
        record.student_notes_json = json.dumps([n.model_dump() for n in student_notes])
        record.professor_notes_json = json.dumps([n.model_dump() for n in prof_notes])

        print("[...] Generating Quiz (MCQs + Code Prediction)...")
        quiz = generate_quiz_for_deck(deck_dict, snippets_list)
        record.quiz_json = json.dumps([q.model_dump() for q in quiz])

        print("[...] Generating 1-Page A4 Cheat Sheet...")
        cheat_sheet = generate_cheat_sheet_data(deck_dict, snippets_list)
        record.cheat_sheet_json = json.dumps(cheat_sheet.model_dump())
        db.commit()

        # 8. Build All Exports (PDFs, ZIPs)
        print("[...] Building all export packages (PDFs, Exercises ZIP, All_Materials ZIP)...")
        exports = build_all_deck_exports(deck_id, db)
        record.materials_status = "ready"
        db.commit()

        print("=" * 70)
        print(f" [SUCCESS] Seeded Deck ID: {deck_id}")
        print(f" Slides Count: {len(slides_data)}")
        print(f" Student Notes Generated: {len(student_notes)}")
        print(f" Quiz Questions Generated: {len(quiz)}")
        print(f" Cheat Sheet PDF: {exports.get('cheat_sheet')}")
        print(f" All Materials ZIP: {exports.get('all_zip')}")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_deck()
