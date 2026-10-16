import os
import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.react import ReactRunner


@pytest.fixture
def react_runner():
    runner = runtime_registry.get_runner("react")
    assert runner is not None
    assert isinstance(runner, ReactRunner)
    return runner


def test_react_hello_world_component(react_runner):
    snippet = (
        'export default function App() {\n'
        '    return (\n'
        '        <div className="card">\n'
        '            <h1>Hello from React 18.3.1!</h1>\n'
        '            <button>Click Here</button>\n'
        '        </div>\n'
        '    );\n'
        '}\n'
    )
    res = react_runner.execute(snippet)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "screenshot_path" in res.artifacts
    assert os.path.exists(res.artifacts["screenshot_path"])


def test_react_build_error_cleanly_reported(react_runner):
    broken_jsx = (
        'export default function App() {\n'
        '    return <div><h1>Missing Closing Div</h1>;\n'
        '}\n'
    )
    res = react_runner.execute(broken_jsx)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "JSX" in res.stderr or "JSX" in res.compile_output


def test_react_console_warning_triggers_failure(react_runner):
    # Missing key prop in array mapping triggers mandatory failure
    warning_jsx = (
        'export default function App() {\n'
        '    const items = ["A", "B", "C"];\n'
        '    return (\n'
        '        <ul>\n'
        '            {items.map(i => <li>{i}</li>)}\n'
        '        </ul>\n'
        '    );\n'
        '}\n'
    )
    res = react_runner.execute(warning_jsx)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert 'unique "key" prop' in res.stderr or len(res.warnings) > 0


def test_react_timeout_contained(react_runner):
    infinite_loop = 'export default function App() { while (true) {} return <div>Loop</div>; }'
    res = react_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_react_network_call_blocked(react_runner):
    net_jsx = (
        'export default function App() {\n'
        '    fetch("https://8.8.8.8/api");\n'
        '    return <div>Network Request</div>;\n'
        '}\n'
    )
    res = react_runner.execute(net_jsx)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_react_determinism(react_runner):
    snippet = 'export default function App() { return <h1>Static Title</h1>; }'
    res1 = react_runner.execute(snippet)
    res2 = react_runner.execute(snippet)

    norm1 = react_runner.normalize(res1.stdout)
    norm2 = react_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "react_render_000000000000.png" in norm1


def test_react_exercise_proof_reference_passes_naive_fails(react_runner):
    exercise = {
        "problem_statement": "Render interactive button with text 'Submit Form'",
        "expected_text": "Submit Form",
    }

    reference_solution = (
        'export default function App() {\n'
        '    return (\n'
        '        <div>\n'
        '            <h2>Survey</h2>\n'
        '            <button>Submit Form</button>\n'
        '        </div>\n'
        '    );\n'
        '}\n'
    )

    naive_solution = (
        'export default function App() {\n'
        '    return (\n'
        '        <div>\n'
        '            <h2>Survey</h2>\n'
        '            <p>Form disabled</p>\n'
        '        </div>\n'
        '    );\n'
        '}\n'
    )

    ref_res = react_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = react_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0
