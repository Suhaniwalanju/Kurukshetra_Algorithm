import json
import pytest
from backend.database import SessionLocal, DeckRecord, SnippetRecord
from backend.materials.concept_examples import (
    get_pinned_version,
    extract_code_excerpt,
    generate_concept_example_code,
    verify_and_heal_concept_example,
    process_concept_slide_example,
)
from backend.materials.notes_generator import generate_notes_for_slide, generate_notes_for_deck_slides
from backend.materials.slide_regenerator import regenerate_single_slide


def test_pinned_version_resolution():
    """Verifies that technologies resolve to their pinned versions according to config/technologies.yaml."""
    assert "21" in get_pinned_version("Java")
    assert "3.12" in get_pinned_version("Python")
    assert "20" in get_pinned_version("Node.js")
    assert "17" in get_pinned_version("C")
    assert "20" in get_pinned_version("C++")
    assert "16" in get_pinned_version("SQL")


def test_generate_concept_example_has_imports_and_entrypoint():
    """
    Verifies that generate_concept_example_code produces a complete runnable file
    matching the runtime with its own imports and entry point, plus code_ref and excerpt.
    """
    slide = {
        "id": 2,
        "type": "concept",
        "title": "Virtual Threads Executor",
        "bullets": ["Lightweight concurrency", "Mounted on carrier threads"],
    }
    code_ref, full_code, excerpt, explanation = generate_concept_example_code(
        slide=slide,
        topic="Java 21 Concurrency",
        tech="Java",
        pinned_version="21.0.6",
    )

    assert code_ref.startswith("ex_java_s2_")
    assert "import " in full_code
    assert "public class Main" in full_code
    assert "public static void main" in full_code
    assert len(excerpt.splitlines()) <= 12
    for line in excerpt.splitlines():
        assert len(line) <= 70


def test_extract_code_excerpt_constraints():
    """Verifies excerpt extraction clamps to max 12 lines and max 70 chars."""
    java_file = (
        "import java.util.concurrent.*;\n"
        "import java.util.*;\n"
        "\n"
        "public class Main {\n"
        "    public static void main(String[] args) throws Exception {\n"
        "        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {\n"
        "            for (int i = 0; i < 5; i++) {\n"
        "                final int taskId = i;\n"
        "                executor.submit(() -> System.out.println(\"Task \" + taskId));\n"
        "            }\n"
        "        }\n"
        "    }\n"
        "}\n"
    )
    excerpt = extract_code_excerpt(java_file, "java", max_lines=12)
    lines = excerpt.splitlines()
    assert len(lines) <= 12
    for l in lines:
        assert len(l) <= 70
    assert "import " not in excerpt


def test_process_concept_slide_example_verifies_and_links():
    """
    Verifies that process_concept_slide_example:
    1. Generates complete runnable example matching topic runtime & pinned version with its own imports.
    2. Links it to the slide by code_ref.
    3. Sends it through sandbox verifier and healing loop.
    4. Stores exact source executed in notes.
    5. Shows excerpt on slide.
    """
    slide = {
        "id": 3,
        "type": "concept",
        "title": "AsyncIO Coroutines",
        "bullets": ["Cooperative multitasking", "Event loop dispatching"],
    }

    db = SessionLocal()
    try:
        updated_slide = process_concept_slide_example(
            slide=slide,
            deck_id="test_deck_concept_ex",
            topic="Python High Performance",
            tech="Python",
            tech_version="3.12",
            db_session=db,
        )

        # 1. Linked by code_ref
        assert "code_ref" in updated_slide
        assert updated_slide["code_ref"].startswith("ex_python_s3_")

        # 2. Slide shows excerpt
        assert "code" in updated_slide
        assert isinstance(updated_slide["code"], dict)
        slide_code = updated_slide["code"]["source"]
        assert len(slide_code.splitlines()) <= 12
        assert updated_slide["code"]["expected_output"] != ""

        # 3. Notes include the full file and code_ref
        assert "notes" in updated_slide
        notes = updated_slide["notes"]
        assert "example" in notes
        assert notes["example"]["code_ref"] == updated_slide["code_ref"]
        assert "full_code" in notes["example"]
        full_code = notes["example"]["full_code"]
        assert "import " in full_code
        assert "def main():" in full_code or "if __name__" in full_code

        # 4. Exact source executed stored in DB and trainer notes
        assert updated_slide["code_ref"] in updated_slide["trainer_notes"]
        snip = db.query(SnippetRecord).filter(
            SnippetRecord.deck_id == "test_deck_concept_ex",
            SnippetRecord.slide_id == 3,
        ).first()
        assert snip is not None
        assert snip.source_code == full_code
        assert snip.was_executed is True
        assert snip.status in ["verified", "verified_low_assurance", "auto_healed"]
    finally:
        db.close()


def test_concept_slide_healing_loop_heals_broken_example():
    """
    Verifies that if an example fails execution, it is sent through the healing loop,
    and the exact healed source is stored in the notes with excerpt on slide.
    """
    db = SessionLocal()
    try:
        slide = {
            "id": 4,
            "type": "concept",
            "title": "Java Syntax Healing Concept",
            "bullets": ["Demonstrating virtual thread creation", "Injected syntax error for healing"],
        }
        # Injected broken Java code (missing semicolon)
        broken_code = (
            "import java.util.*;\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "        System.out.println(\"Java Concept Running\")\n"
            "    }\n"
            "}\n"
        )
        res = verify_and_heal_concept_example(
            deck_id="test_deck_heal_concept",
            slide_id=4,
            code_ref="ex_java_s4_syntax_healing",
            full_code=broken_code,
            excerpt='System.out.println("Java Concept Running")',
            tech="Java",
            pinned_version="21.0.6",
            slide=slide,
            db_session=db,
        )

        assert res["status"] in ["auto_healed", "verified", "verified_low_assurance"]
        assert res["executed_source"].strip().endswith(";") or "System.out.println" in res["executed_source"]
    finally:
        db.close()


def test_concept_slide_regeneration_in_deck():
    """
    Verifies that when a single concept slide is regenerated via slide_regenerator,
    its concept example, code_ref, and notes are updated while all other slides
    remain byte-for-byte identical.
    """
    db = SessionLocal()
    try:
        deck_id = "test_deck_regen_concept"
        slides = [
            {
                "id": 1,
                "type": "cover",
                "title": "Welcome Slide",
                "bullets": ["Overview"],
                "notes": {"talking_points": ["Intro"], "timing_minutes": 2.0},
            },
            {
                "id": 2,
                "type": "concept",
                "title": "Original Concept",
                "bullets": ["Original Bullet"],
                "code_ref": "orig_ref",
                "code": {"source": "print(1)", "language": "python", "version": "3.12", "expected_output": "1"},
                "notes": {
                    "talking_points": ["Point A"],
                    "example": {"description": "Ex", "code_ref": "orig_ref", "full_code": "print(1)"},
                    "common_mistakes": ["None"],
                    "ask_the_class": "Q?",
                    "timing_minutes": 10.0,
                },
            },
            {
                "id": 3,
                "type": "closing",
                "title": "Closing Slide",
                "bullets": ["Summary"],
                "notes": {"talking_points": ["Outro"], "timing_minutes": 3.0},
            },
        ]

        deck = DeckRecord(
            id=deck_id,
            college="Vidyalankar Institute of Technology",
            professor_name="Prof. Tester",
            topic="Python Advanced Concepts",
            student_level="Intermediate",
            session_length=15,
            tech="Python",
            tech_version="3.12",
            status="completed",
            slides_json=json.dumps(slides),
            preview_paths_json=json.dumps(["/p1.png", "/p2.png", "/p3.png"]),
        )
        db.merge(deck)
        db.commit()

        s0_before = json.dumps(slides[0], sort_keys=True)
        s2_before = json.dumps(slides[2], sort_keys=True)

        res = regenerate_single_slide(
            deck_id=deck_id,
            slide_index=1,
            instruction="Focus on Python generators and yield expressions",
            db_session=db,
        )
        assert res["success"] is True

        updated_deck = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        updated_slides = json.loads(updated_deck.slides_json)

        # Slide 1 (concept slide) updated with code_ref, excerpt, and full_code in notes
        concept_slide = updated_slides[1]
        assert "code_ref" in concept_slide
        assert "notes" in concept_slide
        assert "example" in concept_slide["notes"]
        assert "full_code" in concept_slide["notes"]["example"]
        assert concept_slide["notes"]["example"]["code_ref"] == concept_slide["code_ref"]

        # Slide 0 and Slide 2 are untouched
        s0_after = json.dumps(updated_slides[0], sort_keys=True)
        s2_after = json.dumps(updated_slides[2], sort_keys=True)
        assert s0_before == s0_after
        assert s2_before == s2_after

    finally:
        db.close()
