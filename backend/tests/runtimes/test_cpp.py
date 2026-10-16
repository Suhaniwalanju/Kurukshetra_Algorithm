import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.cpp import CppRunner


@pytest.fixture
def cpp_runner():
    runner = runtime_registry.get_runner("cpp")
    assert runner is not None
    assert isinstance(runner, CppRunner)
    return runner


def test_cpp_hello_world(cpp_runner):
    code = 'std::cout << "Hello from C++20 g++ runtime!" << std::endl;'
    res = cpp_runner.execute(code)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "Hello from C++20 g++ runtime!" in res.stdout


def test_cpp_syntax_error_cleanly_reported(cpp_runner):
    broken = 'std::cout << "Missing semicolon"'
    res = cpp_runner.execute(broken)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "expected ';'" in res.stderr or "expected ';'" in res.compile_output


def test_cpp_runtime_error_captured(cpp_runner):
    code = 'int a = 20; int b = a / 0; std::cout << b;'
    res = cpp_runner.execute(code)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_cpp_timeout_contained(cpp_runner):
    infinite_loop = 'while (true) { /* runaway */ }'
    res = cpp_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_cpp_network_call_blocked(cpp_runner):
    net_code = 'int fd = socket(AF_INET, SOCK_STREAM, 0); connect(fd, nullptr, 0);'
    res = cpp_runner.execute(net_code)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_cpp_determinism(cpp_runner):
    code = (
        'std::cout << "Pointer at ==54321== address 0x603000000040" << std::endl;\n'
    )
    res1 = cpp_runner.execute(code)
    res2 = cpp_runner.execute(code)

    norm1 = cpp_runner.normalize(res1.stdout)
    norm2 = cpp_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "==00000==" in norm1
    assert "0x00000000" in norm1


def test_cpp_memory_bug_caught_by_sanitizer(cpp_runner):
    buggy_code = (
        'int* ptr = new int[5];\n'
        'ptr[10] = 99; // heap-buffer-overflow\n'
        'delete[] ptr;\n'
    )
    res = cpp_runner.execute(buggy_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "AddressSanitizer" in res.stderr or len(res.warnings) > 0


def test_cpp_exercise_proof_reference_passes_naive_fails(cpp_runner):
    exercise = {
        "problem_statement": "Sum a vector of integers",
        "test_code": (
            "TEST_CASE(\"vector sum\") {\n"
            "    CHECK(compute({1, 2, 3}) == 6);\n"
            "    CHECK(compute({10}) == 10);\n"
            "    CHECK(compute({}) == 0);\n"
            "}\n"
        ),
    }

    reference_solution = (
        "int compute(const std::vector<int>& nums) {\n"
        "    int s = 0;\n"
        "    for (int n : nums) s += n;\n"
        "    return s;\n"
        "}\n"
    )

    naive_solution = (
        "int compute(const std::vector<int>& nums) {\n"
        "    return nums.empty() ? -1 : nums[0];\n"
        "}\n"
    )

    ref_res = cpp_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = cpp_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0
