import os
import json
import uuid
import pytest
from backend.database import SessionLocal, DeckRecord, SnippetRecord, VerificationRunRecord, HealingLogRecord, ExerciseProofRecord
from backend.verification.coordinator import verification_coordinator
from backend.template_registry import template_registry


def test_e2e_java_21_spring_boot_deck_with_injected_broken_snippet():
    """
    Acceptance Criteria Test:
    1. A Java 21 deck, including a Spring Boot 3 topic, is fully verified end to end.
    2. Intentionally inject a broken snippet to demonstrate fail -> auto-fix -> pass in the report.
    3. For each exercise the reference passes and the naive fails.
    4. Compliance QA reports zero overlap and zero overflow on the final deck.
    5. Report downloadable as HTML and PDF.
    """
    session = SessionLocal()
    deck_id = f"test_e2e_{str(uuid.uuid4())[:6]}"

    # Load default template
    template_registry.scan_and_load()
    colleges = template_registry.list_colleges()
    college_name = colleges[0]["college"] if colleges else "Vidyalankar"

    # Construct Java 21 + Spring Boot 3 slide deck with an intentionally broken snippet
    slides = [
        {
            "id": 1,
            "type": "cover",
            "title": "Spring Boot 3 & Java 21 Architecture",
            "bullets": ["Modern Java backend engineering", "Virtual threads in Spring Boot"],
            "speaker_hint": "Welcome students to advanced Java 21 and Spring Boot 3.",
        },
        {
            "id": 2,
            "type": "code",
            "title": "Spring Boot 3 REST Controller",
            "bullets": ["Exposing endpoint with Virtual Threads", "Fast non-blocking responses"],
            "code": {
                "language": "Java",
                "version": "21",
                # Valid Java 21 snippet
                "source": "System.out.println(\"Spring Boot 3 Web Endpoint Initialized\");",
                "expected_output": "Wrong initial output to be replaced",
            },
        },
        {
            "id": 3,
            "type": "code",
            "title": "Virtual Threads Executor (Broken)",
            "bullets": ["Demonstrating virtual thread creation", "Injected syntax error for healing"],
            "code": {
                "language": "Java",
                "version": "21",
                # Intentionally broken snippet: missing semicolon
                "source": "System.out.println(\"Java 21 Virtual Thread Running\")",
                "expected_output": "Java 21 Virtual Thread Running",
            },
        },
        {
            "id": 4,
            "type": "exercise",
            "title": "Hands-On Lab: Scoped Values vs ThreadLocal",
            "bullets": ["Implement scoped value binding", "Pass context safely"],
            "exercise_ref": "LAB-JAVA21-01",
            "code": {
                "language": "Java",
                "version": "21",
                "source": "System.out.println(\"Exercise Starter Code\");",
                "expected_output": "Exercise Starter Code",
            },
        },
        {
            "id": 5,
            "type": "closing",
            "title": "Summary & Key Takeaways",
            "bullets": ["Java 21 Virtual Threads", "Spring Boot 3 Starters", "Production readiness"],
        },
    ]

    out_dir = os.path.join(os.getcwd(), "output", deck_id)
    os.makedirs(out_dir, exist_ok=True)

    deck_record = DeckRecord(
        id=deck_id,
        college=college_name,
        professor_name="Dr. Samruddhi Khade",
        topic="Spring Boot 3 & Java 21 Architecture",
        student_level="Advanced",
        session_length=45,
        tech="Java",
        tech_version="21",
        slides_json=json.dumps(slides),
        status="ready_for_verification",
        output_dir=out_dir,
    )
    session.add(deck_record)
    session.commit()

    try:
        # Run Verification Pipeline End-to-End
        result = verification_coordinator.verify_deck(deck_id, session)

        # 1. Pipeline status
        assert result["status"] == "success"
        assert result["snippets_count"] >= 3

        # 2. Broken snippet auto-healed demonstration
        healed_logs = session.query(HealingLogRecord).filter(HealingLogRecord.deck_id == deck_id).all()
        assert len(healed_logs) >= 1
        last_log = healed_logs[-1]
        assert last_log.healed_successfully is True
        assert "before_attempt" in last_log.diff_text
        assert "after_attempt" in last_log.diff_text

        # Verify snippet status became auto_healed
        healed_snippet = session.query(SnippetRecord).filter(
            SnippetRecord.deck_id == deck_id,
            SnippetRecord.slide_id == 3,
        ).first()
        assert healed_snippet.status == "auto_healed"
        assert "System.out.println(\"Java 21 Virtual Thread Running\");" in healed_snippet.source_code or healed_snippet.source_code.strip().endswith(";")

        # 3. Real output injection check
        updated_deck = session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        updated_slides = json.loads(updated_deck.slides_json)
        # Expected output on slide 2 should now match real stdout
        slide_2_code = updated_slides[1]["code"]
        assert "Spring Boot 3 Web Endpoint Initialized" in slide_2_code["expected_output"]

        # 4. Verified badge check on slides
        for s in updated_slides:
            assert "verification_badge" in s
            assert "Verified ✔ Ran on Java 21" in s["verification_badge"]

        # 5. Exercise Proof: Reference passes, naive fails, mutation score computed
        exercise_proofs = session.query(ExerciseProofRecord).filter(ExerciseProofRecord.deck_id == deck_id).all()
        assert len(exercise_proofs) >= 1
        ep = exercise_proofs[0]
        assert ep.reference_passed is True
        assert ep.naive_failed is True
        assert ep.total_mutants >= 5
        assert ep.mutation_score >= 50.0

        # 6. Template Compliance QA: Zero violations
        assert result["compliance_passed"] is True

        # 7. HTML and PDF reports generated and downloadable
        html_path = result["html_report_path"]
        pdf_path = result["pdf_report_path"]
        assert os.path.exists(html_path)
        assert os.path.getsize(html_path) > 1000
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000

        # Check content of HTML report
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        assert "Spring Boot 3 &amp; Java 21 Architecture" in html_content or "Spring Boot 3" in html_content
        assert "Auto-Healed" in html_content
        assert "View Auto-Healing Diff" in html_content
        assert "Mutation Score" in html_content

    finally:
        session.close()
