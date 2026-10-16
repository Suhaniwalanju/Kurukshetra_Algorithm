import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.python import PythonRunner


@pytest.fixture
def python_runner():
    runner = runtime_registry.get_runner("python")
    assert runner is not None
    assert isinstance(runner, PythonRunner)
    return runner


def test_python_hello_world(python_runner):
    code = 'print("Hello from Python 3.12 Runtime!")'
    res = python_runner.execute(code)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "Hello from Python 3.12 Runtime!" in res.stdout


def test_python_syntax_error_cleanly_reported(python_runner):
    broken_code = 'def invalid_syntax(\n  print("Missing colon and closing paren"'
    res = python_runner.execute(broken_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "SyntaxError" in res.compile_output or "SyntaxError" in res.stderr


def test_python_runtime_error_captured(python_runner):
    code = 'x = 10 / 0'
    res = python_runner.execute(code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "ZeroDivisionError" in res.stderr


def test_python_timeout_contained(python_runner):
    infinite_loop = 'while True:\n    pass'
    # Run with short 2s timeout
    res = python_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_python_network_call_blocked(python_runner):
    network_code = (
        'import socket\n'
        's = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n'
        's.connect(("8.8.8.8", 53))\n'
    )
    res = python_runner.execute(network_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "PermissionError" in res.stderr or "Network Access Denied" in res.stderr


def test_python_determinism(python_runner):
    code = (
        'class CustomObj:\n'
        '    pass\n'
        'obj = CustomObj()\n'
        'print("Created object:", repr(obj))\n'
    )
    res1 = python_runner.execute(code)
    res2 = python_runner.execute(code)

    norm1 = python_runner.normalize(res1.stdout)
    norm2 = python_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "at 0x00000000" in norm1


def test_python_exercise_proof_reference_passes_naive_fails(python_runner):
    exercise = {
        "problem_statement": "Compute sum of elements in a list.",
        "test_code": (
            "assert compute([1, 2, 3]) == 6, 'Test 1 failed'\n"
            "assert compute([10]) == 10, 'Test 2 failed'\n"
            "assert compute([]) == 0, 'Test 3 failed'\n"
            "print('All tests passed!')\n"
        ),
    }

    reference_solution = (
        "def compute(nums):\n"
        "    return sum(nums)\n"
    )

    naive_solution = (
        "def compute(nums):\n"
        "    return nums[0] if nums else -1\n"
    )

    ref_res = python_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True
    assert "All tests passed!" in ref_res.output

    naive_res = python_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0
