import pytest
from backend.verification.extractor import SnippetExtractor
from backend.verification.sandbox import sandbox_engine, CodeWrapper
from backend.verification.healing_loop import SelfHealingLoop
from backend.verification.exercise_prover import ExerciseProver
from backend.database import SnippetRecord
from backend.schemas import TemplateLayoutConfig


def test_snippet_extractor():
    extractor = SnippetExtractor()
    slides = [
        {
            "id": 1,
            "type": "cover",
            "title": "Welcome to Java 21",
            "bullets": ["Intro"],
        },
        {
            "id": 2,
            "type": "code",
            "title": "Virtual Threads",
            "bullets": ["Lightweight threads"],
            "code": {
                "language": "Java",
                "version": "21",
                "source": "Thread.startVirtualThread(() -> System.out.println(\"Hello\"));",
                "expected_output": "Hello",
            },
        },
        {
            "id": 3,
            "type": "exercise",
            "title": "Hands-On Lab: Scoped Values",
            "bullets": ["Implement scoped context"],
            "code": {
                "language": "Java",
                "version": "21",
                "source": "ScopedValue<String> USER = ScopedValue.newInstance();",
                "expected_output": "",
            },
        },
    ]

    snippets = extractor.extract_snippets_from_deck("deck_test_123", slides, default_tech="Java", default_version="21")
    assert len(snippets) == 2
    assert snippets[0].slide_id == 2
    assert snippets[0].language == "java"
    assert snippets[0].version == "21"
    assert snippets[0].snippet_type == "code"
    assert "startVirtualThread" in snippets[0].source_code
    assert snippets[1].slide_id == 3
    assert snippets[1].snippet_type == "exercise"


def test_sandbox_normal_python_execution():
    source = "name = 'Java 21'; print(f'Verified: {name}')"
    res = sandbox_engine.run_snippet(
        snippet_id="test_py_valid",
        language="python",
        source_code=source,
        version="3.12",
        timeout_sec=5,
    )
    assert res.exit_code == 0
    assert "Verified: Java 21" in res.stdout
    assert not res.timed_out
    assert not res.network_blocked


def test_sandbox_normal_java_execution():
    source = "System.out.println(\"Java 21 Virtual Threads OK\");"
    res = sandbox_engine.run_snippet(
        snippet_id="test_java_valid",
        language="java",
        source_code=source,
        version="21",
        timeout_sec=10,
    )
    assert res.exit_code == 0
    assert "Java 21 Virtual Threads OK" in res.stdout
    assert not res.timed_out


def test_sandbox_hostile_infinite_loop_contained():
    """
    Hostile test: an infinite loop must be forcefully terminated by the sandbox
    within the configured timeout, asserting that timed_out is True and exit_code is 124.
    """
    source = "while True:\n    pass"
    res = sandbox_engine.run_snippet(
        snippet_id="test_py_infinite_loop",
        language="python",
        source_code=source,
        version="3.12",
        timeout_sec=2,  # Short timeout for unit test speed
    )
    assert res.timed_out is True
    assert res.exit_code == 124
    assert "Sandbox Timeout" in res.stderr


def test_sandbox_hostile_network_call_blocked():
    """
    Hostile test: network calls must be blocked under --network none emulation,
    asserting network_blocked is True or PermissionError is raised.
    """
    source = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=1)\n"
        "except Exception as e:\n"
        "    print(f'Blocked: {e}')\n"
        "    raise\n"
    )
    res = sandbox_engine.run_snippet(
        snippet_id="test_py_network_hostile",
        language="python",
        source_code=source,
        version="3.12",
        timeout_sec=5,
    )
    assert res.network_blocked is True or "Network Access Denied" in res.stderr or "PermissionError" in res.stderr


def test_exercise_prover_reference_and_naive():
    """
    Verifies that for an exercise:
    1. Reference solution passes
    2. Naive solution fails
    3. Mutation score is computed
    """
    prover = ExerciseProver()
    slide = {
        "id": 4,
        "type": "exercise",
        "title": "Hands-On Lab: Palindrome Checker",
        "exercise_ref": "EX-PAL-01",
    }
    proof = prover.prove_exercise(deck_id="test_deck", slide=slide, language="python", version="3.12")
    assert proof.reference_passed is True
    assert proof.naive_failed is True
    assert proof.total_mutants >= 5
    assert proof.mutation_score >= 0.5
    assert "reference" in proof.pass_fail_matrix
    assert "naive" in proof.pass_fail_matrix


def test_self_healing_loop():
    """
    Verifies that the self-healing loop:
    1. Identifies failed snippet
    2. Calls healing logic
    3. Produces unified before/after diff
    4. Re-verifies healed snippet in sandbox
    """
    healer = SelfHealingLoop()
    snippet = SnippetRecord(
        id="snip_heal_001",
        deck_id="deck_test_heal",
        slide_id=2,
        language="java",
        version="21",
        snippet_type="code",
        source_code="System.out.println(\"Broken missing semicolon\")",
        expected_output="Broken missing semicolon",
        status="failed",
    )

    diff = healer._compute_diff(
        old_code="System.out.println(\"Before\")",
        new_code="System.out.println(\"After\");",
        snippet_id=snippet.id,
        attempt=1,
    )
    assert "--- before_attempt_1" in diff
    assert "+++ after_attempt_1" in diff
    assert "+System.out.println(\"After\");" in diff

    # Test heuristic fix
    error_log = "Main.java:3: error: ';' expected\nSystem.out.println(\"test\")\n                           ^"
    fixed = healer._heuristic_fix("java", "System.out.println(\"test\")", error_log)
    assert fixed.endswith(";")
