import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.c import CRunner


@pytest.fixture
def c_runner():
    runner = runtime_registry.get_runner("c")
    assert runner is not None
    assert isinstance(runner, CRunner)
    return runner


def test_c_hello_world(c_runner):
    code = 'printf("Hello from C17 gcc runtime!\\n");'
    res = c_runner.execute(code)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "Hello from C17 gcc runtime!" in res.stdout


def test_c_syntax_error_cleanly_reported(c_runner):
    broken = 'printf("Missing semicolon")'
    res = c_runner.execute(broken)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "expected ';'" in res.stderr or "expected ';'" in res.compile_output


def test_c_runtime_error_captured(c_runner):
    code = 'int a = 10; int b = a / 0; printf("%d", b);'
    res = c_runner.execute(code)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_c_timeout_contained(c_runner):
    infinite_loop = 'while (1) { /* runaway */ }'
    res = c_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_c_network_call_blocked(c_runner):
    net_code = 'int fd = socket(AF_INET, SOCK_STREAM, 0); connect(fd, NULL, 0);'
    res = c_runner.execute(net_code)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_c_determinism(c_runner):
    code = (
        'int *ptr = (int*)malloc(sizeof(int));\n'
        'printf("Allocated pointer at ==12345== address 0x7ffeefbff5c0\\n");\n'
        'free(ptr);\n'
    )
    res1 = c_runner.execute(code)
    res2 = c_runner.execute(code)

    norm1 = c_runner.normalize(res1.stdout)
    norm2 = c_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "==00000==" in norm1
    assert "0x00000000" in norm1


def test_c_memory_bug_caught_by_sanitizer(c_runner):
    # Buffer overflow bug
    buggy_code = (
        'int *arr = (int*)malloc(4 * sizeof(int));\n'
        'arr[10] = 99; // heap-buffer-overflow\n'
        'printf("%d", arr[10]);\n'
    )
    res = c_runner.execute(buggy_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "AddressSanitizer" in res.stderr or len(res.warnings) > 0


def test_c_exercise_proof_reference_passes_naive_fails(c_runner):
    exercise = {
        "problem_statement": "Sum an array of integers",
        "test_code": (
            "int main(void) {\n"
            "    int arr1[] = {1, 2, 3};\n"
            "    assert(compute(arr1, 3) == 6);\n"
            "    printf(\"All C assertions passed!\\n\");\n"
            "    return 0;\n"
            "}\n"
        ),
    }

    reference_solution = (
        "int compute(int *nums, int len) {\n"
        "    int s = 0;\n"
        "    for (int i = 0; i < len; i++) s += nums[i];\n"
        "    return s;\n"
        "}\n"
    )

    naive_solution = (
        "int compute(int *nums, int len) {\n"
        "    return len == 0 ? -1 : nums[0];\n"
        "}\n"
    )

    ref_res = c_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = c_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
