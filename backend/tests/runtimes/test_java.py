import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.java import JavaRunner


@pytest.fixture
def java_runner():
    runner = runtime_registry.get_runner("java")
    assert runner is not None
    assert isinstance(runner, JavaRunner)
    return runner


def test_java_hello_world(java_runner):
    code = 'System.out.println("Hello from Java 21 Virtual Threads!");'
    res = java_runner.execute(code)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "Hello from Java 21 Virtual Threads!" in res.stdout


def test_java_compile_error_cleanly_reported(java_runner):
    broken_code = 'System.out.println("Missing closing semicolon")'
    res = java_runner.execute(broken_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "';' expected" in res.compile_output or "';' expected" in res.stderr


def test_java_runtime_error_captured(java_runner):
    runtime_err = 'int x = 10 / 0;'
    res = java_runner.execute(runtime_err)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "ArithmeticException" in res.stderr


def test_java_timeout_contained(java_runner):
    infinite_loop = 'while (true) { Thread.sleep(50); }'
    res = java_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_java_determinism(java_runner):
    code = (
        'Object obj = new Object();\n'
        'System.out.println("Object ref: " + obj.toString());\n'
    )
    res1 = java_runner.execute(code)
    res2 = java_runner.execute(code)

    norm1 = java_runner.normalize(res1.stdout)
    norm2 = java_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "@00000000" in norm1


def test_java_exercise_proof_reference_passes_naive_fails(java_runner):
    exercise = {
        "problem_statement": "Implement sum calculation",
        "test_code": (
            "public class TestRunner {\n"
            "    public static void main(String[] args) {\n"
            "        if (Solution.compute(new int[]{1, 2, 3}) != 6) throw new AssertionError(\"Test 1 failed\");\n"
            "        if (Solution.compute(new int[]{5}) != 5) throw new AssertionError(\"Test 2 failed\");\n"
            "        if (Solution.compute(new int[]{}) != 0) throw new AssertionError(\"Test 3 failed\");\n"
            "        System.out.println(\"All tests passed!\");\n"
            "    }\n"
            "}\n"
        ),
    }

    reference_solution = (
        "public class Solution {\n"
        "    public static int compute(int[] nums) {\n"
        "        int sum = 0;\n"
        "        for (int n : nums) sum += n;\n"
        "        return sum;\n"
        "    }\n"
        "}\n"
    )

    naive_solution = (
        "public class Solution {\n"
        "    public static int compute(int[] nums) {\n"
        "        return nums.length == 0 ? -1 : nums[0];\n"
        "    }\n"
        "}\n"
    )

    ref_res = java_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True
    assert "All tests passed!" in ref_res.output

    naive_res = java_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0


def test_java_deprecation_handling(java_runner):
    # System.runFinalizersOnExit is deprecated for removal in modern Java
    code = 'System.runFinalizersOnExit(true);'
    res = java_runner.execute(code)
    # Should flag removal as failure
    assert res.status == "fail"
    assert len(res.deprecations) > 0 or res.exit_code != 0
