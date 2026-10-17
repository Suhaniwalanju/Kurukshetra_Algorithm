import os
import json
import pytest
from backend.materials.topic_retriever import topic_retriever
from backend.materials.notes_generator import (
    generate_notes_for_slide,
    generate_notes_for_deck_slides,
    validate_timing,
)
from backend.database import SessionLocal, DeckRecord
from backend.materials.slide_regenerator import regenerate_single_slide


def test_topic_retriever_finds_and_chunks_pdf():
    """Verifies that TopicRetriever finds topic folder in input/Topics and extracts factual chunks."""
    # Java 21 Virtual Threads
    chunks = topic_retriever.get_topic_chunks("Spring Boot 3 Architecture", "Java")
    assert len(chunks) > 0
    # Spot-check keywords in chunks
    combined = " ".join(chunks).lower()
    assert "thread" in combined or "concurrency" in combined or "java" in combined

    # Check slide retrieval
    slide = {
        "title": "Virtual Threads Executor",
        "bullets": ["Lightweight execution", "No OS thread blocking"],
        "code": "Thread.ofVirtual().start(() -> System.out.println(\"Hi\"));",
    }
    retrieved = topic_retriever.retrieve_chunks_for_slide(slide, "Virtual Threads", "Java", top_k=3)
    assert len(retrieved) > 0
    assert len(retrieved) <= 3


def test_generate_notes_for_slide_schema_and_constraints():
    """
    Verifies that generate_notes_for_slide produces JSON with:
    - talking_points (max 4)
    - one example (with code_ref if code is needed)
    - common_mistakes (max 2)
    - ask_the_class (one question)
    - timing_minutes
    """
    slide_with_code = {
        "id": 2,
        "type": "code",
        "title": "Virtual Threads API",
        "bullets": ["Thread.ofVirtual() factory", "Carrier thread mounting"],
        "code": {
            "source": "Thread.startVirtualThread(() -> System.out.println(\"Running\"));",
            "language": "java",
        },
    }

    notes = generate_notes_for_slide(
        slide=slide_with_code,
        topic="Java 21 Virtual Threads",
        tech="Java",
        tech_version="21",
        target_timing=6.0,
        session_length=45.0,
    )

    # 1. Structure validation
    assert isinstance(notes, dict)
    assert "talking_points" in notes
    assert "example" in notes
    assert "common_mistakes" in notes
    assert "ask_the_class" in notes
    assert "timing_minutes" in notes

    # 2. Constraints validation
    assert len(notes["talking_points"]) <= 4
    assert len(notes["talking_points"]) >= 1

    assert isinstance(notes["example"], dict)
    assert "description" in notes["example"]
    assert "code_ref" in notes["example"]
    assert notes["example"]["code_ref"] is not None  # Code was provided

    assert len(notes["common_mistakes"]) <= 2
    assert len(notes["common_mistakes"]) >= 1

    assert isinstance(notes["ask_the_class"], str)
    assert notes["ask_the_class"].endswith("?")

    assert isinstance(notes["timing_minutes"], (int, float))
    assert notes["timing_minutes"] > 0


def test_generate_notes_for_slide_without_code():
    """Verifies that non-code slides have code_ref as None or empty in the example."""
    slide_no_code = {
        "id": 1,
        "type": "cover",
        "title": "Welcome to Java 21",
        "bullets": ["Modern concurrency", "Overview of course"],
    }
    notes = generate_notes_for_slide(
        slide=slide_no_code,
        topic="Java 21 Concurrency",
        tech="Java",
        target_timing=2.0,
        session_length=40.0,
    )
    assert len(notes["talking_points"]) <= 4
    assert len(notes["common_mistakes"]) <= 2
    assert notes["example"]["code_ref"] is None
    assert notes["ask_the_class"].endswith("?")


def test_timing_validation_and_regeneration_within_10_percent():
    """
    Verifies that total timing across slides is validated against 10% of session length,
    and regenerate adjusts timings to fit within [0.90 * session_length, 1.10 * session_length].
    """
    session_length = 45.0  # 10% tolerance is [40.5, 49.5]

    # Valid notes (total = 45.0)
    valid_notes = [
        {"timing_minutes": 5.0},
        {"timing_minutes": 15.0},
        {"timing_minutes": 15.0},
        {"timing_minutes": 10.0},
    ]
    is_valid, total, msg = validate_timing(valid_notes, session_length)
    assert is_valid is True
    assert total == 45.0

    # Invalid notes (total = 20.0, diff = 55% > 10%)
    invalid_notes = [
        {"timing_minutes": 5.0},
        {"timing_minutes": 5.0},
        {"timing_minutes": 5.0},
        {"timing_minutes": 5.0},
    ]
    is_valid_inv, total_inv, msg_inv = validate_timing(invalid_notes, session_length)
    assert is_valid_inv is False
    assert total_inv == 20.0

    # Test full deck notes generation enforces 10% tolerance
    slides = [
        {"id": 1, "type": "cover", "title": "Java Concurrency", "bullets": ["Intro"]},
        {"id": 2, "type": "concept", "title": "Virtual Threads", "bullets": ["Concept"]},
        {"id": 3, "type": "code", "title": "API Demo", "code": "System.out.println(1);", "bullets": ["Code"]},
        {"id": 4, "type": "exercise", "title": "Lab Exercise", "bullets": ["Practice"]},
        {"id": 5, "type": "closing", "title": "Summary", "bullets": ["Conclusion"]},
    ]

    updated_slides = generate_notes_for_deck_slides(
        slides=slides,
        topic="Java 21 Concurrency",
        tech="Java",
        session_length=session_length,
    )

    deck_notes = [s["notes"] for s in updated_slides]
    is_valid_deck, total_deck, msg_deck = validate_timing(deck_notes, session_length)
    assert is_valid_deck is True, f"Failed timing validation: {msg_deck}"
    assert 40.5 <= total_deck <= 49.5


def test_single_slide_notes_regenerated_without_touching_others():
    """
    Verifies that regenerating a single slide regenerates ONLY that slide's notes,
    while leaving all other slides' notes completely untouched.
    """
    db = SessionLocal()
    try:
        deck_id = "test_notes_single_slide_deck"
        slides = [
            {
                "id": 1,
                "type": "cover",
                "title": "Slide 1 Cover",
                "bullets": ["Intro A"],
                "notes": {
                    "talking_points": ["Point 1A", "Point 1B"],
                    "example": {"description": "Ex 1", "code_ref": None},
                    "common_mistakes": ["Mistake 1"],
                    "ask_the_class": "Question 1?",
                    "timing_minutes": 3.0,
                },
            },
            {
                "id": 2,
                "type": "code",
                "title": "Slide 2 Code",
                "bullets": ["Code 2A"],
                "code": "print('Original 2')",
                "notes": {
                    "talking_points": ["Point 2A"],
                    "example": {"description": "Ex 2", "code_ref": "print('Original 2')"},
                    "common_mistakes": ["Mistake 2"],
                    "ask_the_class": "Question 2?",
                    "timing_minutes": 10.0,
                },
            },
            {
                "id": 3,
                "type": "closing",
                "title": "Slide 3 Closing",
                "bullets": ["Conclusion 3"],
                "notes": {
                    "talking_points": ["Point 3A"],
                    "example": {"description": "Ex 3", "code_ref": None},
                    "common_mistakes": ["Mistake 3"],
                    "ask_the_class": "Question 3?",
                    "timing_minutes": 2.0,
                },
            },
        ]

        record = DeckRecord(
            id=deck_id,
            college="VIT",
            professor_name="Prof. Test",
            topic="Python Scripting",
            student_level="Beginner",
            session_length=15,
            tech="Python",
            tech_version="3.12",
            status="completed",
            slides_json=json.dumps(slides),
            preview_paths_json=json.dumps(["/p1.png", "/p2.png", "/p3.png"]),
        )
        db.merge(record)
        db.commit()

        # Capture serialized untouched slides before regenerating slide index 1
        slide_0_before = json.dumps(slides[0], sort_keys=True)
        slide_2_before = json.dumps(slides[2], sort_keys=True)

        res = regenerate_single_slide(
            deck_id=deck_id,
            slide_index=1,
            instruction="Focus on error handling in Python",
            db_session=db,
        )

        assert res["success"] is True

        # Reload updated record from DB
        updated_record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        updated_slides = json.loads(updated_record.slides_json)

        # Slide 1 notes were regenerated
        assert "notes" in updated_slides[1]
        assert len(updated_slides[1]["notes"]["talking_points"]) <= 4
        assert len(updated_slides[1]["notes"]["common_mistakes"]) <= 2

        # Slide 0 and Slide 2 notes and content MUST remain byte-for-byte identical!
        slide_0_after = json.dumps(updated_slides[0], sort_keys=True)
        slide_2_after = json.dumps(updated_slides[2], sort_keys=True)

        assert slide_0_before == slide_0_after, "Slide 0 was modified during single slide regeneration!"
        assert slide_2_before == slide_2_after, "Slide 2 was modified during single slide regeneration!"

    finally:
        db.close()
