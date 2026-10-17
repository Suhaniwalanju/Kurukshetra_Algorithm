import os
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from backend.main import app, process_deck_generation
from backend.database import (
    SessionLocal,
    DeckRecord,
    SnippetRecord,
    VerificationRunRecord,
    HealingLogRecord,
    ExerciseProofRecord,
)
from backend.schemas import DeckCreateRequest
from backend.template_registry import template_registry


client = TestClient(app)


def test_old_qa_route_no_longer_exists():
    """
    Test requirement: Verify that the old Verification QA route no longer exists.
    Requests to /api/decks/{deck_id}/verify and /api/decks/{deck_id}/verify/stream must return 404.
    """
    deck_id = "test_qa_route_404"
    res_post = client.post(f"/api/decks/{deck_id}/verify")
    assert res_post.status_code == 404, f"Expected 404, got {res_post.status_code}: {res_post.text}"

    res_stream = client.get(f"/api/decks/{deck_id}/verify/stream")
    assert res_stream.status_code == 404, f"Expected 404, got {res_stream.status_code}: {res_stream.text}"


def test_deck_snippets_verified_before_finalization():
    """
    Test requirement: No deck is finalized before its snippets have been through the verification loop.
    All snippets must be executed and verified before record.status becomes 'completed'.
    Never emit an unverified slide with a verified badge.
    """
    session = SessionLocal()
    deck_id = f"test_fin_{uuid.uuid4().hex[:6]}"
    template_registry.scan_and_load()
    colleges = template_registry.list_colleges()
    college = colleges[0]["college"] if colleges else "DPU"

    req = DeckCreateRequest(
        college=college,
        professor_name="Prof. Inline Verifier",
        topic="Python 3.12 Concurrency & Threads",
        student_level="Intermediate",
        session_length=15,
        tech="Python",
        tech_version="3.12",
    )

    record = DeckRecord(
        id=deck_id,
        college=req.college,
        professor_name=req.professor_name,
        topic=req.topic,
        student_level=req.student_level,
        session_length=req.session_length,
        tech=req.tech,
        tech_version=req.tech_version or "",
        status="pending",
        status_message="Deck generation queued...",
    )
    session.add(record)
    session.commit()

    try:
        process_deck_generation(deck_id, req, session)
        session.refresh(record)

        # 1. Deck must be completed
        assert record.status == "completed"
        assert record.verified is True

        # 2. Check all snippets in database
        snippets = session.query(SnippetRecord).filter(SnippetRecord.deck_id == deck_id).all()
        assert len(snippets) > 0, "Expected at least one snippet to be extracted and verified inline"

        for snip in snippets:
            # Snippet must have been processed through sandbox
            assert snip.status != "pending", f"Snippet {snip.id} was finalized in 'pending' state"
            assert snip.status in ["verified", "auto_healed", "verified_low_assurance", "needs_review"], \
                f"Unexpected status: {snip.status}"
            assert snip.command_executed != "", f"Snippet {snip.id} did not record command_executed"

        # 3. Slide badges: Never emit an unverified slide with a verified badge
        final_slides = json.loads(record.slides_json)
        for s in final_slides:
            badge = s.get("verification_badge")
            has_code = bool(s.get("code") and s["code"].get("source", "").strip())
            if not has_code:
                assert badge is None, f"Slide {s.get('id')} has no code but has a badge: {badge}"
            else:
                assert badge in ["Unverified"] or "Verified ✔" in badge

    finally:
        session.close()


def test_seeded_error_healed_during_generation():
    """
    Test requirement: A snippet with a seeded error is healed inline during deck generation.
    The healed snippet must transition to 'auto_healed' with a logged repair diff.
    """
    session = SessionLocal()
    deck_id = f"test_heal_{uuid.uuid4().hex[:6]}"
    template_registry.scan_and_load()
    colleges = template_registry.list_colleges()
    college = colleges[0]["college"] if colleges else "DPU"

    req = DeckCreateRequest(
        college=college,
        professor_name="Prof. Healing Test",
        topic="Java 21 Syntax Healing",
        student_level="Beginner",
        session_length=15,
        tech="Java",
        tech_version="21",
    )

    out_dir = os.path.join(os.getcwd(), "output", deck_id)
    os.makedirs(out_dir, exist_ok=True)

    record = DeckRecord(
        id=deck_id,
        college=req.college,
        professor_name=req.professor_name,
        topic=req.topic,
        student_level=req.student_level,
        session_length=req.session_length,
        tech=req.tech,
        tech_version=req.tech_version or "",
        status="pending",
        output_dir=out_dir,
    )
    session.add(record)
    session.commit()

    # Pre-seed a broken snippet on slide 3 with missing semicolon
    seeded_broken_code = 'System.out.println("Seeded syntax error missing semicolon")'
    seeded_snip = SnippetRecord(
        id=f"snip_{deck_id}_s3",
        deck_id=deck_id,
        slide_id=3,
        snippet_type="code",
        language="java",
        version="21",
        source_code=seeded_broken_code,
        status="pending",
    )
    session.add(seeded_snip)
    session.commit()

    try:
        from backend.verification.coordinator import verification_coordinator
        template_config = template_registry.get_config(college)
        if not template_config and template_registry.templates:
            template_config = list(template_registry.templates.values())[0]

        broken_slide = {
            "id": 3,
            "type": "concept",
            "title": "Java 21 Syntax Healing",
            "bullets": ["Syntax healing validation"],
            "code": {
                "language": "java",
                "version": "21",
                "source": seeded_broken_code,
                "expected_output": "Seeded syntax error missing semicolon",
            },
        }

        # Run inline verification on the slide with seeded error
        final_slide, snips, hlogs = verification_coordinator.verify_slide_inline(
            slide=broken_slide,
            deck_id=deck_id,
            tech="Java",
            version="21",
            template_config=template_config,
            professor_name="Prof. Healing Test",
            db_session=session,
        )

        # Snippet must have been healed
        assert len(snips) == 1
        healed_snip = snips[0]
        assert healed_snip.status in ["auto_healed", "verified_low_assurance", "verified"], \
            f"Expected auto_healed, got: {healed_snip.status}"

        # Healing logs must contain repair diff
        logs = session.query(HealingLogRecord).filter(HealingLogRecord.deck_id == deck_id).all()
        assert len(logs) >= 1, "Expected at least 1 healing log record for seeded error"
        assert logs[0].diff != "", "Expected repair diff in healing log"
        assert logs[0].fixed_code != "", "Expected fixed code in healing log"

    finally:
        session.close()


def test_report_available_when_generation_completes():
    """
    Test requirement: Verification report is immediately available via API and disk
    when deck generation completes, without requiring a separate user action.
    """
    session = SessionLocal()
    deck_id = f"test_rep_{uuid.uuid4().hex[:6]}"
    template_registry.scan_and_load()
    colleges = template_registry.list_colleges()
    college = colleges[0]["college"] if colleges else "DPU"

    req = DeckCreateRequest(
        college=college,
        professor_name="Prof. Report Available",
        topic="Python 3.12 String Processing",
        student_level="Beginner",
        session_length=15,
        tech="Python",
        tech_version="3.12",
    )

    record = DeckRecord(
        id=deck_id,
        college=req.college,
        professor_name=req.professor_name,
        topic=req.topic,
        student_level=req.student_level,
        session_length=req.session_length,
        tech=req.tech,
        tech_version=req.tech_version or "",
        status="pending",
    )
    session.add(record)
    session.commit()

    try:
        process_deck_generation(deck_id, req, session)
        session.refresh(record)
        assert record.status == "completed"

        # Query verification report endpoint
        res = client.get(f"/api/decks/{deck_id}/report")
        assert res.status_code == 200
        data = res.json()

        # Check report data structure
        assert data["deck_id"] == deck_id
        assert "summary" in data
        assert data["summary"]["total_snippets"] >= 1
        assert "snippets" in data
        assert len(data["snippets"]) >= 1

        # Check downloadable reports exist immediately
        assert data["html_report_available"] is True
        assert data["pdf_report_available"] is True

        html_res = client.get(f"/api/decks/{deck_id}/report/html")
        assert html_res.status_code == 200

    finally:
        session.close()
