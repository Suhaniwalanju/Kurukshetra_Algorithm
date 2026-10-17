import os
import json
import pytest
from backend.verification.exercise_prover import exercise_prover
from backend.verification.report_generator import VerificationReportGenerator, report_generator
from backend.materials.exporter import export_exercises_zip
from backend.database import ExerciseProofRecord, SessionLocal


def test_prove_deck_exercises_generates_three_tiers():
    """
    Verifies that prove_deck_exercises generates 3 exercises per deck:
    - easy, medium, stretch
    - each with task, starter_code, test_code, reference_solution, naive_solution
    - reference solution passes (PASS)
    - naive solution fails on TEST_FAILURE (assertion failure, not compile error)
    - mutation check runs and records killed mutants
    """
    deck_id = "test_deck_3tiers"
    topic = "Python List Comprehensions & Aggregations"

    proofs = exercise_prover.prove_deck_exercises(
        deck_id=deck_id,
        topic=topic,
        language="python",
        version="3.12",
        max_attempts=3,
    )

    assert len(proofs) == 3
    difficulties = [p.difficulty for p in proofs]
    assert difficulties == ["easy", "medium", "stretch"]

    for p in proofs:
        # Each must have task, starter_code, test_code, reference_solution, naive_solution
        p_dict = p.to_dict()
        assert p_dict["task"], "Task must be present"
        assert p_dict["problem_statement"], "Problem statement must be present"
        assert p_dict["starter_code"], "Starter code must be present"
        assert p_dict["test_code"], "Test code must be present"
        assert p_dict["reference_solution"], "Reference solution must be present"
        assert p_dict["naive_solution"], "Naive solution must be present"
        assert p.difficulty in ["easy", "medium", "stretch"]
        assert p.status == "verified"
        assert p.attempts >= 1

        # Reference solution must PASS
        assert p.reference_passed is True

        # Naive solution must fail on a test assertion (TEST_FAILURE)
        assert p.naive_failed is True

        # Mutation check must have run and recorded mutants
        mutants = json.loads(p.mutants_json)
        assert len(mutants) >= 5
        for m in mutants:
            assert m["classification"] != "COMPILE_ERROR"
            if m["killed"]:
                assert m["classification"] == "TEST_FAILURE"
        assert p.mutation_score >= 0.0


def test_exercise_retry_and_needs_review_on_persistent_failure(monkeypatch):
    """
    Verifies that if any step fails (e.g. naive solution passes or reference fails),
    the prover regenerates and re-verifies up to max_attempts, then flags as needs_review.
    """
    deck_id = "test_deck_failure"
    topic = "Faulty Algorithm Simulation"

    # Simulate a suite where reference solution always fails
    broken_suite = {
        "task": "Impossible task",
        "problem_statement": "Impossible task",
        "starter_code": "def compute(x): return 0",
        "test_code": "assert compute(1) == 999999, 'Will always fail'",
        "reference_solution": "def compute(x): return 0", # fails assertion!
        "naive_solution": "def compute(x): return 0",
    }

    call_count = 0
    def mock_generate_suite(topic, language, version, difficulty="medium", attempt=1):
        nonlocal call_count
        call_count += 1
        return broken_suite

    monkeypatch.setattr(exercise_prover, "_generate_exercise_suite", mock_generate_suite)

    proof = exercise_prover.prove_single_exercise(
        deck_id=deck_id,
        slide_id=1,
        exercise_ref="EX-FAIL-01",
        topic=topic,
        difficulty="medium",
        language="python",
        version="3.12",
        max_attempts=3,
    )

    # Must have retried up to max_attempts = 3
    assert call_count == 3
    # Must flag the exercise as needs_review
    assert proof.status == "needs_review"
    assert proof.reference_passed is False
    assert proof.attempts == 3


def test_verification_report_includes_three_exercise_tiers_html_and_pdf(tmp_path):
    """
    Verifies that both HTML and PDF reports include the 3 exercises, their difficulty badges,
    status badges (VERIFIED / NEEDS REVIEW), tasks, and mutation scores.
    """
    report_gen = VerificationReportGenerator()
    deck_id = "test_report_3tiers"
    topic = "Algorithms: Sorting & Searching"

    proofs = exercise_prover.prove_deck_exercises(
        deck_id=deck_id,
        topic=topic,
        language="python",
        version="3.12",
        max_attempts=3,
    )

    # Add one needs_review exercise to test status badge display
    needs_review_proof = ExerciseProofRecord(
        id="proof_nr_01",
        deck_id=deck_id,
        slide_id=99,
        difficulty="stretch",
        status="needs_review",
        attempts=3,
        exercise_ref="EX-NR-99",
        problem_statement="Complex Graph Partitioning",
        starter_code="def partition(g): pass",
        test_code="assert False",
        reference_solution="def partition(g): pass",
        reference_passed=False,
        naive_solution="def partition(g): pass",
        naive_failed=False,
        mutants_json="[]",
        mutation_score=0.0,
        matrix_json="{}",
    )
    all_proofs = proofs + [needs_review_proof]

    # 1. HTML Report
    html_path = os.path.join(str(tmp_path), "report.html")
    report_gen.generate_html_report(
        deck_id=deck_id,
        deck_metadata={"topic": topic, "tech": "Python"},
        snippets=[],
        runs=[],
        healing_logs=[],
        exercise_proofs=all_proofs,
        content_reviews=[],
        compliance_results=[],
        output_path=html_path,
    )

    assert os.path.exists(html_path)
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Check that tiers and status are rendered
    assert "EASY" in html_content
    assert "MEDIUM" in html_content
    assert "STRETCH" in html_content
    assert "VERIFIED ✔" in html_content
    assert "NEEDS REVIEW ✖" in html_content
    assert "Task:" in html_content
    assert "Mutation Score:" in html_content

    # 2. PDF Report
    pdf_path = os.path.join(str(tmp_path), "report.pdf")
    report_gen.generate_pdf_report(
        deck_id=deck_id,
        deck_metadata={"topic": topic, "tech": "Python"},
        snippets=[],
        runs=[],
        healing_logs=[],
        exercise_proofs=all_proofs,
        content_reviews=[],
        compliance_results=[],
        output_pdf_path=pdf_path,
    )

    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 1000


def test_export_exercises_zip_packages_all_three_tiers(tmp_path):
    """
    Verifies that export_exercises_zip packages each difficulty tier with task README,
    solution starter, test file, reference solution, naive solution, and mutation proof.
    """
    deck_id = "test_zip_3tiers"
    topic = "Data Structures: Trees & Maps"

    proofs = exercise_prover.prove_deck_exercises(
        deck_id=deck_id,
        topic=topic,
        language="python",
        version="3.12",
        max_attempts=3,
    )

    deck_dict = {
        "id": deck_id,
        "topic": topic,
        "tech": "Python",
    }

    zip_path = os.path.join(str(tmp_path), "Exercises.zip")
    export_exercises_zip(deck_dict, proofs, zip_path)

    assert os.path.exists(zip_path)

    import zipfile
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        # Verify subfolders for each tier exist in both student and instructor folders
        for diff in ["easy", "medium", "stretch"]:
            matching_student = [n for n in names if f"student/exercise_" in n and f"_{diff}/" in n]
            matching_instructor = [n for n in names if f"instructor/exercise_" in n and f"_{diff}/" in n]
            assert len(matching_student) >= 3, f"Student files for {diff} must be packaged"
            assert len(matching_instructor) >= 4, f"Instructor files for {diff} must be packaged"
            # Verify naive solution is present in instructor files
            assert any("naive_solution.py" in n and f"_{diff}" in n for n in names)
