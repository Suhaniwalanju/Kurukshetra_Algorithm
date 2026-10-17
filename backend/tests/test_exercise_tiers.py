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
        assert len(mutants) >= 3
        for m in mutants:
            assert m["classification"] != "COMPILE_ERROR"
            if m["killed"]:
                assert m["classification"] == "TEST_FAILURE"
        assert p.mutation_score >= 80.0

        # Commands run and execution runs must be stored
        assert len(p.commands_run) >= 3, "Commands run must be stored per exercise"
        assert len(p.runs) >= 3, "Runs breakdown must be stored per exercise"
        assert p_dict["final_status"] == "verified"
        assert p_dict["commands_run"] == p.commands_run
        assert p_dict["runs"] == p.runs

        # Verify run classifications and failing test names
        ref_run = next(r for r in p.runs if r["step"] == "reference")
        assert ref_run["classification"] == "PASS"

        naive_run = next(r for r in p.runs if r["step"] == "naive")
        assert naive_run["classification"] == "TEST_FAILURE"
        assert naive_run["failing_test_name"], "Failing test name must be captured for naive solution"


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
    def mock_generate_suite(*args, **kwargs):
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


def test_exercise_proof_rejects_deliberately_weak_tests(monkeypatch):
    """
    Feeds in an exercise suite with deliberately weak tests where the naive solution
    passes all test assertions. Confirms it is rejected, retries up to max_attempts,
    marked needs_review, and not shown as verified.
    """
    deck_id = "test_deck_weak_tests"
    topic = "Algorithms: Basic Sorting"

    # Weak test: only tests an input for which naive returns the right answer!
    weak_suite = {
        "task": "Implement sort_asc(arr)",
        "problem_statement": "Implement sort_asc(arr)",
        "starter_code": "def sort_asc(arr): pass",
        "test_code": "assert sort_asc([1, 2, 3]) == [1, 2, 3], 'Weak test passed'\nprint('All tests passed')",
        "reference_solution": "def sort_asc(arr): return sorted(arr)",
        # Naive solution: returns arr unmodified without sorting! Passes the weak test!
        "naive_solution": "def sort_asc(arr): return arr",
    }

    call_count = 0
    def mock_generate_suite(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return weak_suite

    monkeypatch.setattr(exercise_prover, "_generate_exercise_suite", mock_generate_suite)

    proof = exercise_prover.prove_single_exercise(
        deck_id=deck_id,
        slide_id=1,
        exercise_ref="EX-WEAK-01",
        topic=topic,
        difficulty="medium",
        language="python",
        version="3.12",
        max_attempts=3,
    )

    # Must retry all 3 attempts
    assert call_count == 3
    # Must reject and mark needs_review, never verified
    assert proof.status == "needs_review"
    assert proof.status != "verified"
    assert proof.reference_passed is True
    assert proof.naive_failed is False
    assert proof.attempts == 3

    # Check commands_run and runs metadata
    assert len(proof.commands_run) >= 2
    naive_run = next(r for r in proof.runs if r["step"] == "naive")
    assert naive_run["classification"] == "PASS"  # Weak test let naive pass


def test_exercise_proof_rejects_naive_runtime_crash_or_compile_error(monkeypatch):
    """
    Verifies that if the naive solution results in a COMPILE_ERROR or RUNTIME_ERROR crash,
    it does NOT count as a valid proof failure (must fail on a test assertion, TEST_FAILURE).
    """
    deck_id = "test_deck_naive_crash"
    topic = "Algorithms: Safe Division"

    crash_suite = {
        "task": "Implement safe_divide(a, b)",
        "problem_statement": "Implement safe_divide(a, b)",
        "starter_code": "def safe_divide(a, b): pass",
        "test_code": "assert safe_divide(10, 2) == 5\nassert safe_divide(10, 0) == 0",
        "reference_solution": "def safe_divide(a, b):\n    return a // b if b != 0 else 0",
        # Naive solution: crashes with ZeroDivisionError (RUNTIME_ERROR, not an assertion failure)
        "naive_solution": "def safe_divide(a, b):\n    return a // b",
    }

    call_count = 0
    def mock_generate_suite(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return crash_suite

    monkeypatch.setattr(exercise_prover, "_generate_exercise_suite", mock_generate_suite)

    proof = exercise_prover.prove_single_exercise(
        deck_id=deck_id,
        slide_id=1,
        exercise_ref="EX-CRASH-01",
        topic=topic,
        difficulty="medium",
        language="python",
        version="3.12",
        max_attempts=3,
    )

    # Must retry all 3 attempts
    assert call_count == 3
    # Must reject and mark needs_review because naive did not fail on assertion
    assert proof.status == "needs_review"
    assert proof.status != "verified"
    assert proof.naive_failed is False
    naive_run = next(r for r in proof.runs if r["step"] == "naive")
    assert naive_run["classification"] in ["RUNTIME_ERROR", "COMPILE_ERROR"]


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
    assert "Sandbox Execution Runs & Classifications:" in html_content
    assert "TEST_FAILURE" in html_content

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


def test_exercise_with_deliberately_weak_tests_is_rejected_and_regenerated(monkeypatch):
    """
    Verifies that an exercise with deliberately weak tests (where naive solution passes)
    is rejected on attempt 1, then regenerated with stronger tests and re-verified.
    """
    deck_id = "test_weak_regen_deck"
    topic = "Algorithms: Array Operations"

    attempt_counter = 0

    def mock_generate_exercise_suite(
        topic, language, version, difficulty="medium", slides=None, source_slides=None,
        topic_chunks=None, student_level="intermediate", do_not_use=None, attempt=1, model_name="qwen2.5:3b"
    ):
        nonlocal attempt_counter
        attempt_counter += 1

        if attempt == 1:
            # Deliberately weak test: passes naive solution!
            return {
                "id": "exercise_01",
                "title": f"{topic} (Weak Attempt)",
                "task": "Implement compute(nums)",
                "problem_statement": "Implement compute(nums)",
                "difficulty": difficulty,
                "estimated_minutes": 15,
                "source_slides": [1],
                "starter_code": "def compute(nums: list) -> int:\n    return 0\n",
                # Weak test: only tests empty list where naive happens to return 0!
                "test_code": "def run_tests():\n    assert compute([]) == 0, 'Test 1 failed'\n    print('All tests passed!')\nrun_tests()\n",
                "reference_solution": "def compute(nums: list) -> int:\n    return sum(x for x in nums if x > 0)\n",
                # Naive returns 0 for empty list, so it PASSES this weak test!
                "naive_solution": "def compute(nums: list) -> int:\n    return 0\n",
            }
        else:
            # Regenerated strengthened test: catches naive solution!
            return {
                "id": "exercise_01",
                "title": f"{topic} (Strengthened Attempt)",
                "task": "Implement compute(nums)",
                "problem_statement": "Implement compute(nums)",
                "difficulty": difficulty,
                "estimated_minutes": 15,
                "source_slides": [1],
                "starter_code": "def compute(nums: list) -> int:\n    return 0\n",
                "test_code": "def run_tests():\n    assert compute([1, 2, 3]) == 6, 'Test 1 failed'\n    assert compute([]) == 0, 'Test 2 failed'\n    print('All tests passed!')\nrun_tests()\n",
                "reference_solution": "def compute(nums: list) -> int:\n    return sum(x for x in nums if x > 0)\n",
                # Naive returns 0, so it FAILS on [1, 2, 3] != 0!
                "naive_solution": "def compute(nums: list) -> int:\n    return 0\n",
            }

    monkeypatch.setattr(exercise_prover, "_generate_exercise_suite", mock_generate_exercise_suite)

    proof = exercise_prover.prove_single_exercise(
        deck_id=deck_id,
        slide_id=1,
        exercise_ref="EX-WEAK-REGEN-01",
        topic=topic,
        difficulty="medium",
        language="python",
        version="3.12",
        max_attempts=3,
    )

    # Must have rejected attempt 1 and regenerated on attempt 2
    assert attempt_counter == 2
    assert proof.attempts == 2
    assert proof.status == "verified"
    assert proof.reference_passed is True
    assert proof.naive_failed is True


def test_export_exercises_zip_packages_all_three_tiers(tmp_path):
    """
    Verifies that export_exercises_zip packages each difficulty tier:
    - student/ has NO solutions (only task.md, starter, tests)
    - All solutions live only in instructor/
    - proof_report.md shows passing reference run and failing naive run
    - README.md and exercises_verification.json exist
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
        "tech_version": "3.12",
    }

    zip_path = os.path.join(str(tmp_path), "Exercises.zip")
    export_exercises_zip(deck_dict, proofs, zip_path)

    assert os.path.exists(zip_path)

    import zipfile
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()

        # Check README.md and exercises_verification.json exist
        assert "README.md" in names
        assert "exercises_verification.json" in names

        # Read exercises_verification.json to verify content
        verif_raw = z.read("exercises_verification.json").decode("utf-8")
        verif_data = json.loads(verif_raw)
        assert len(verif_data) == 3

        # Check folders for all 3 exercises
        for idx in range(1, 4):
            folder = f"exercise_{idx:02d}"
            # student/ must contain task.md, starter.py, tests.py
            assert f"student/{folder}/task.md" in names
            assert f"student/{folder}/starter.py" in names
            assert f"student/{folder}/tests.py" in names

            # student/ MUST NOT contain any solution files!
            student_files = [n for n in names if n.startswith(f"student/{folder}/")]
            for sf in student_files:
                assert "solution" not in sf.lower(), f"student/ must not contain solutions: {sf}"

            # instructor/ must contain reference_solution.py, naive_solution.py, proof_report.md
            assert f"instructor/{folder}/reference_solution.py" in names
            assert f"instructor/{folder}/naive_solution.py" in names
            assert f"instructor/{folder}/proof_report.md" in names

            # Read proof_report.md and verify reference pass and naive failure
            proof_content = z.read(f"instructor/{folder}/proof_report.md").decode("utf-8")
            assert "PASS ✔" in proof_content
            assert "TEST_FAILURE ✔" in proof_content
            assert "Mutation Score:" in proof_content
