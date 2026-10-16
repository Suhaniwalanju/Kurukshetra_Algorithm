import os
import hashlib
import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.web_foundations import WebFoundationsRunner


@pytest.fixture
def web_runner():
    runner = runtime_registry.get_runner("web_foundations")
    assert runner is not None
    assert isinstance(runner, WebFoundationsRunner)
    return runner


def test_web_hello_world_dom_render(web_runner):
    snippet = '<div class="card"><h1>Interactive Web Component</h1><button>Click Me</button></div>'
    res = web_runner.execute(snippet)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "screenshot_path" in res.artifacts
    assert os.path.exists(res.artifacts["screenshot_path"])


def test_web_console_error_triggers_failure(web_runner):
    snippet = (
        '<h1>Test Error Page</h1>\n'
        '<script>\n'
        '    console.error("Uncaught ReferenceError: variableIsNotDefined is not defined");\n'
        '</script>\n'
    )
    res = web_runner.execute(snippet)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "Console Errors" in res.stderr


def test_web_timeout_contained(web_runner):
    infinite_loop = '<script>while (true) { /* runaway script */ }</script>'
    res = web_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_web_network_blocked(web_runner):
    net_snippet = '<script>fetch("http://8.8.8.8/api").then(r => r.json());</script>'
    res = web_runner.execute(net_snippet)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_web_screenshot_identical_across_runs(web_runner):
    snippet = '<div class="card"><h1>Deterministic Component</h1><button>Submit</button></div>'
    res1 = web_runner.execute(snippet)
    res2 = web_runner.execute(snippet)

    path1 = res1.artifacts["screenshot_path"]
    path2 = res2.artifacts["screenshot_path"]

    with open(path1, "rb") as f1, open(path2, "rb") as f2:
        hash1 = hashlib.sha256(f1.read()).hexdigest()
        hash2 = hashlib.sha256(f2.read()).hexdigest()

    # Byte-for-byte screenshot determinism
    assert hash1 == hash2


def test_web_determinism(web_runner):
    snippet = '<h1>Dynamic Header</h1>'
    res1 = web_runner.execute(snippet)
    res2 = web_runner.execute(snippet)

    norm1 = web_runner.normalize(res1.stdout)
    norm2 = web_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "web_render_000000000000.png" in norm1


def test_web_exercise_proof_reference_passes_naive_fails(web_runner):
    exercise = {
        "problem_statement": "Create a card with a call-to-action button",
        "expected_element": "<button",
    }

    reference_solution = '<div class="card"><h2>Course Enrollment</h2><button>Enroll Now</button></div>'
    naive_solution = '<div class="card"><h2>Course Enrollment</h2><p>Enrollment closed</p></div>'

    ref_res = web_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = web_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
