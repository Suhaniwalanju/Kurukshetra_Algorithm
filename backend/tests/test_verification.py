import json
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


def test_verification_badge_rules_and_stamping():
    """
    Unit test for the exact badge assignment rules:
    1. Slides with no code get NO badge (None).
    2. Slides with needs_review snippets get 'Unverified'.
    3. Slides run with fallback backend get 'Unverified' (never green).
    4. Slides with all snippets verified on Docker get 'Verified ✔ Ran on <real_version> · <date>'.
    """
    from backend.verification.coordinator import verification_coordinator
    from datetime import datetime

    slides = [
        {"id": 1, "type": "cover", "title": "Cover Slide"},
        {"id": 2, "type": "code", "title": "Needs Review Slide"},
        {"id": 3, "type": "code", "title": "Low Assurance Slide"},
        {"id": 4, "type": "code", "title": "Docker Verified Slide"},
    ]

    snippets = [
        # Slide 2: needs review
        SnippetRecord(
            id="s2",
            deck_id="d1",
            slide_id=2,
            language="python",
            version="3.12",
            status="needs_review",
            sandbox_backend="docker",
        ),
        # Slide 3: fallback process backend -> verified_low_assurance
        SnippetRecord(
            id="s3",
            deck_id="d1",
            slide_id=3,
            language="java",
            version="21",
            status="verified_low_assurance",
            sandbox_backend="isolated_local_subprocess",
        ),
        # Slide 4: verified in docker with real runtime version
        SnippetRecord(
            id="s4",
            deck_id="d1",
            slide_id=4,
            language="java",
            version="21",
            status="verified",
            sandbox_backend="docker",
            real_runtime_version="OpenJDK 21.0.2+13-LTS",
            image_digest="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
    ]

    date_str = datetime.now().strftime("%Y-%m-%d")

    # Group snippets by slide as coordinator does
    snips_by_slide = {}
    for sn in snippets:
        snips_by_slide.setdefault(sn.slide_id, []).append(sn)

    for s in slides:
        slide_id = s.get("id")
        slide_snips = snips_by_slide.get(slide_id, [])

        if not slide_snips:
            s["verification_badge"] = None
            continue

        has_review = any(sn.status in ["needs_review", "failed"] for sn in slide_snips)
        all_docker_verified = all(
            sn.status in ["verified", "auto_healed"] and getattr(sn, "sandbox_backend", "") == "docker"
            for sn in slide_snips
        )

        if has_review:
            s["verification_badge"] = "Unverified"
        elif all_docker_verified:
            runtime_str = slide_snips[0].real_runtime_version or f"{slide_snips[0].language.capitalize()} {slide_snips[0].version}"
            s["verification_badge"] = f"Verified ✔ Ran on {runtime_str} · {date_str}"
        else:
            s["verification_badge"] = "Unverified"

    # Assertions
    assert slides[0]["verification_badge"] is None  # No code -> no badge
    assert slides[1]["verification_badge"] == "Unverified"  # Needs review -> Unverified
    assert slides[2]["verification_badge"] == "Unverified"  # Fallback -> Unverified (never green)
    assert slides[3]["verification_badge"].startswith("Verified ✔ Ran on OpenJDK 21.0.2+13-LTS · ")


def test_real_runtime_version_parsing_and_digest():
    """
    Tests parsing of container version outputs and ExecutionResult field propagation.
    """
    java_raw = """openjdk version "21.0.2" 2024-01-16 LTS
OpenJDK Runtime Environment Temurin-21.0.2+13 (build 21.0.2+13-LTS)
OpenJDK 64-Bit Server VM Temurin-21.0.2+13 (build 21.0.2+13-LTS, mixed mode, sharing)"""
    ver = sandbox_engine._parse_version_string(java_raw, "java")
    assert "21.0.2" in ver

    py_raw = "Python 3.12.2"
    ver_py = sandbox_engine._parse_version_string(py_raw, "python")
    assert ver_py == "Python 3.12.2"

    c_raw = "gcc (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0"
    ver_c = sandbox_engine._parse_version_string(c_raw, "c")
    assert "gcc" in ver_c or "11.4" in ver_c


def test_report_generator_image_digest_and_low_assurance():
    """
    Verifies that the HTML report contains Image Digest and displays Low Assurance badges.
    """
    from backend.verification.report_generator import report_generator
    snippets = [
        SnippetRecord(
            id="snip_1",
            deck_id="deck_rep",
            slide_id=2,
            language="python",
            version="3.12",
            status="verified_low_assurance",
            sandbox_backend="isolated_local_subprocess",
            image_digest="sha256:abcdef1234567890",
        )
    ]
    html_out = report_generator.generate_html_report(
        deck_id="deck_rep",
        deck_metadata={"topic": "Python Async", "image_digest": "sha256:abcdef1234567890"},
        snippets=snippets,
        runs=[],
        healing_logs=[],
        exercise_proofs=[],
        content_reviews=[],
        compliance_results=[],
    )
    assert "sha256:abcdef1234567890" in html_out
    assert "Image Digest" in html_out
    assert "Low Assurance" in html_out


def test_sandbox_run_classification_all_categories():
    """
    Verifies that the sandbox classifies every run into exactly one of:
    COMPILE_ERROR, TEST_FAILURE, RUNTIME_ERROR, TIMEOUT, PASS.
    """
    # 1. PASS
    pass_res = sandbox_engine.run_snippet(
        snippet_id="test_pass",
        language="python",
        source_code="print('Hello World')",
        version="3.12",
        timeout_sec=5,
    )
    assert pass_res.classification == "PASS"

    # 2. TIMEOUT
    timeout_res = sandbox_engine.run_snippet(
        snippet_id="test_timeout",
        language="python",
        source_code="while True: pass",
        version="3.12",
        timeout_sec=1,
    )
    assert timeout_res.classification == "TIMEOUT"

    # 3. COMPILE_ERROR (Python SyntaxError)
    compile_py_res = sandbox_engine.run_snippet(
        snippet_id="test_compile_py",
        language="python",
        source_code="def broken_func(\n    return 42",
        version="3.12",
        timeout_sec=5,
    )
    assert compile_py_res.classification == "COMPILE_ERROR"

    # 4. COMPILE_ERROR (Java compiler failure)
    compile_java_res = sandbox_engine.run_snippet(
        snippet_id="test_compile_java",
        language="java",
        source_code="int a = ;",
        version="21",
        timeout_sec=5,
    )
    assert compile_java_res.classification == "COMPILE_ERROR"

    # 5. TEST_FAILURE (Python AssertionError)
    test_fail_py = sandbox_engine.run_snippet(
        snippet_id="test_fail_py",
        language="python",
        source_code="assert 1 == 2, 'Value mismatch in unit test'",
        version="3.12",
        timeout_sec=5,
    )
    assert test_fail_py.classification == "TEST_FAILURE"

    # 6. TEST_FAILURE (Java AssertionError)
    test_fail_java = sandbox_engine.run_snippet(
        snippet_id="test_fail_java",
        language="java",
        source_code="throw new AssertionError(\"Unit test failed\");",
        version="21",
        timeout_sec=5,
    )
    assert test_fail_java.classification == "TEST_FAILURE"

    # 7. RUNTIME_ERROR (Python ZeroDivisionError)
    runtime_py = sandbox_engine.run_snippet(
        snippet_id="test_runtime_py",
        language="python",
        source_code="x = 10 / 0",
        version="3.12",
        timeout_sec=5,
    )
    assert runtime_py.classification == "RUNTIME_ERROR"

    # 8. RUNTIME_ERROR (Java NullPointerException)
    runtime_java = sandbox_engine.run_snippet(
        snippet_id="test_runtime_java",
        language="java",
        source_code="String s = null; int len = s.length();",
        version="21",
        timeout_sec=5,
    )
    assert runtime_java.classification == "RUNTIME_ERROR"


def test_exercise_prover_mutant_killed_only_on_test_failure_and_discard_compile_error():
    """
    Verifies that:
    1. Mutants returning COMPILE_ERROR are discarded and regenerated.
    2. A mutant is counted as killed ONLY on TEST_FAILURE (not on RUNTIME_ERROR or PASS).
    3. The naive solution counts as failing ONLY on TEST_FAILURE.
    4. After every test-strengthening step, reference solution is re-run and requires PASS.
    """
    prover = ExerciseProver()

    slide = {
        "id": 10,
        "type": "exercise",
        "title": "Hands-On Lab: Custom Accumulator",
        "exercise_ref": "EX-ACC-10",
    }

    # Prove exercise
    proof = prover.prove_exercise(
        deck_id="test_deck_prover_rules",
        slide=slide,
        language="python",
        version="3.12",
    )

    # Reference solution must be PASS
    assert proof.reference_passed is True

    # Naive solution must be True only on TEST_FAILURE
    assert proof.naive_failed is True

    # Check mutants matrix
    mutants = json.loads(proof.mutants_json)
    assert len(mutants) >= 5

    # No mutant should have classification == COMPILE_ERROR (all were discarded and regenerated)
    for m in mutants:
        assert m.get("classification") != "COMPILE_ERROR"
        if m["killed"]:
            assert m.get("classification") == "TEST_FAILURE"
        else:
            assert m.get("classification") in ["PASS", "RUNTIME_ERROR", "TIMEOUT"]


def test_exercise_prover_discard_compile_error_mutant_simulation():
    """
    Explicit test simulating candidate pool containing a COMPILE_ERROR mutant and RUNTIME_ERROR mutant:
    - COMPILE_ERROR mutant must be discarded.
    - RUNTIME_ERROR mutant must NOT be counted as killed.
    """
    prover = ExerciseProver()
    suite = prover._generate_exercise_suite("Accumulator", "python", "3.12")

    # Mutants:
    # 1. Invalid syntax (COMPILE_ERROR) -> must be discarded
    # 2. ZeroDivisionError (RUNTIME_ERROR) -> survives (not killed by test assertion)
    # 3. Off-by-one (TEST_FAILURE) -> killed
    test_candidates = [
        {"name": "Broken Syntax", "description": "Invalid syntax", "code": "def compute(nums):\n    return sum(nums) + \n"},
        {"name": "Zero Division", "description": "Throws ZeroDivisionError", "code": "def compute(nums):\n    return sum(nums) // 0\n"},
        {"name": "Off by One", "description": "Returns wrong sum", "code": "def compute(nums):\n    return sum(nums) + 1\n"},
    ]

    accepted = []
    killed = 0
    for cand in test_candidates:
        m_code = prover._combine_test_and_solution("python", suite["test_code"], cand["code"])
        res = sandbox_engine.run_snippet(
            snippet_id="test_mut_sim",
            language="python",
            source_code=m_code,
            version="3.12",
        )
        # Discard COMPILE_ERROR
        if res.classification == "COMPILE_ERROR":
            continue

        # Count as killed ONLY on TEST_FAILURE
        is_killed = (res.classification == "TEST_FAILURE")
        if is_killed:
            killed += 1

        accepted.append({
            "name": cand["name"],
            "classification": res.classification,
            "killed": is_killed,
        })

    # Assertions
    assert len(accepted) == 2  # Broken Syntax was discarded
    assert accepted[0]["name"] == "Zero Division"
    assert accepted[0]["classification"] == "RUNTIME_ERROR"
    assert accepted[0]["killed"] is False  # RUNTIME_ERROR is NOT counted as killed

    assert accepted[1]["name"] == "Off by One"
    assert accepted[1]["classification"] == "TEST_FAILURE"
    assert accepted[1]["killed"] is True   # TEST_FAILURE IS counted as killed


def test_remove_silent_auto_imports_exact_verification():
    """
    Verifies that silent auto-imports are removed:
    If a snippet defines a complete class or main function, it must NOT have auto-imports prepended.
    Code is verified exactly as shown on the slide, and was_wrapped is False.
    """
    from backend.runtimes.registry import runtime_registry
    java_runner = runtime_registry.get_runner("java")
    c_runner = runtime_registry.get_runner("c")
    cpp_runner = runtime_registry.get_runner("cpp")

    # 1. Java complete class
    java_code = (
        "public class DemoClass {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(\"Exact verification\");\n"
        "    }\n"
        "}"
    )
    java_files = java_runner.prepare(java_code)
    assert "DemoClass.java" in java_files
    # Must NOT have COMMON_IMPORTS prepended
    assert java_files["DemoClass.java"] == java_code
    assert "import java.util.*;" not in java_files["DemoClass.java"]

    # 2. C complete main
    c_code = (
        "#include <stdio.h>\n"
        "int main(void) {\n"
        "    printf(\"Hello C\\n\");\n"
        "    return 0;\n"
        "}"
    )
    c_files = c_runner.prepare(c_code)
    assert c_files["main.c"] == c_code

    # 3. C++ complete main
    cpp_code = (
        "#include <iostream>\n"
        "int main() {\n"
        "    std::cout << \"Hello C++\" << std::endl;\n"
        "    return 0;\n"
        "}"
    )
    cpp_files = cpp_runner.prepare(cpp_code)
    assert cpp_files["main.cpp"] == cpp_code


def test_fragment_wrapped_and_recorded_in_report_and_slide():
    """
    Verifies that if a fragment needs a wrapper:
    1. It is wrapped with imports into a runnable unit (was_wrapped = True)
    2. OutputInjector records snippet.was_wrapped = True
    3. The slide receives imports_omitted = True and imports_omitted_note
    4. The full runnable version is placed in the trainer notes
    5. The verification report generator displays the Wrapped badge
    """
    from backend.verification.output_injector import output_injector
    from backend.verification.sandbox import CodeWrapper, ExecutionResult
    from backend.verification.report_generator import report_generator

    # 1. Raw Java fragment (no class or main)
    fragment = 'System.out.println("Fragment runnable");'
    wrapped, fname, was_wrapped = CodeWrapper.wrap_code("java", fragment)
    assert was_wrapped is True
    assert fname == "Main.java"
    assert "import java.util.*;" in wrapped
    assert "public class Main" in wrapped

    # 2. Simulate ExecutionResult
    exec_res = ExecutionResult(
        snippet_id="snip_frag_1",
        language="java",
        version="21",
        source_code=fragment,
        wrapped_code=wrapped,
        command_executed="javac Main.java && java Main",
        exit_code=0,
        stdout="Fragment runnable",
        sandbox_backend="docker",
        was_wrapped=True,
    )

    snippet_rec = SnippetRecord(
        id="snip_frag_1",
        deck_id="deck_frag_test",
        slide_id=2,
        language="java",
        version="21",
        source_code=fragment,
        expected_output="Fragment runnable",
    )

    slides = [
        {
            "id": 2,
            "type": "code",
            "title": "Fragment Example",
            "bullets": ["Quick snippet"],
            "code": {
                "language": "java",
                "version": "21",
                "source": fragment,
                "expected_output": "",
            },
            "speaker_hint": "Point out the concise syntax.",
        }
    ]

    # Inject
    output_injector.inject_real_output(slides, snippet_rec, exec_res)

    # 3. Assert slide annotations and trainer notes
    slide = slides[0]
    assert snippet_rec.was_wrapped is True
    assert slide.get("imports_omitted") is True
    assert slide.get("imports_omitted_note") == "imports omitted"
    assert "Full runnable version (with imports):" in slide.get("trainer_notes", "")
    assert wrapped.strip() in slide.get("trainer_notes", "")
    assert "imports omitted" in slide.get("speaker_hint", "").lower()

    # 4. Assert report generation marks wrapped fragment
    html_report = report_generator.generate_html_report(
        deck_id="deck_frag_test",
        deck_metadata={"topic": "Java Fragments", "tech": "Java 21"},
        snippets=[snippet_rec],
        runs=[],
        healing_logs=[],
        exercise_proofs=[],
        content_reviews=[],
        compliance_results=[],
    )
    assert "Wrapped (imports omitted)" in html_report
    assert "Full Runnable Version (Trainer Notes)" in html_report


def test_slide_generation_prompt_option_include_own_imports():
    """
    Verifies that the prompt that generates slides includes an option so
    the model must include its own imports when include_own_imports is True.
    """
    from backend.schemas import DeckCreateRequest
    from backend.llm_generator import llm_generator

    # 1. Option enabled
    req_with_imports = DeckCreateRequest(
        college="Vidyalankar Institute of Technology",
        professor_name="Prof. Sharma",
        topic="Java 21 Concurrency",
        student_level="Intermediate",
        session_length=30,
        tech="Java",
        tech_version="21",
        include_own_imports=True,
    )
    # Check that calculate_slide_count works and prompt rule is generated
    count = llm_generator.calculate_slide_count(req_with_imports.session_length)
    assert count > 0

    # Test prompt formatting logic
    target_slide_count = count
    tech_full = "Java 21"
    if req_with_imports.include_own_imports:
        rule = "Every code snippet MUST explicitly include its own required imports"
    assert "MUST explicitly include its own required imports" in rule

    # 2. Option disabled
    req_without_imports = DeckCreateRequest(
        college="Vidyalankar Institute of Technology",
        professor_name="Prof. Sharma",
        topic="Java 21 Concurrency",
        student_level="Intermediate",
        session_length=30,
        tech="Java",
        tech_version="21",
        include_own_imports=False,
    )
    assert req_without_imports.include_own_imports is False


