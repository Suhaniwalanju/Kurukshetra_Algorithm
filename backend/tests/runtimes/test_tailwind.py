import os
import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.tailwind import TailwindRunner


@pytest.fixture
def tailwind_runner():
    runner = runtime_registry.get_runner("tailwind")
    assert runner is not None
    assert isinstance(runner, TailwindRunner)
    return runner


def test_tailwind_hello_world_build(tailwind_runner):
    snippet = '<div class="bg-blue-600 text-white p-4 rounded-lg shadow-md font-bold">Tailwind Card</div>'
    res = tailwind_runner.execute(snippet)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "screenshot_path" in res.artifacts
    assert os.path.exists(res.artifacts["screenshot_path"])
    assert res.artifacts["computed_styles"]["background-color"] == "rgb(37, 99, 235)"
    assert res.artifacts["computed_styles"]["color"] == "rgb(255, 255, 255)"


def test_tailwind_flags_non_existent_utility(tailwind_runner):
    # Requirement: "flag utilities that do not exist in the pinned version"
    invalid_snippet = '<div class="bg-ultra-fake-magic-color-999 p-4">Invalid</div>'
    res = tailwind_runner.execute(invalid_snippet)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert len(res.warnings) > 0
    assert "Non-existent utility flagged" in res.warnings[0] or "Unknown utility" in res.stderr


def test_tailwind_network_cdn_blocked(tailwind_runner):
    cdn_snippet = '<script src="https://cdn.tailwindcss.com"></script><div class="p-4">CDN Test</div>'
    res = tailwind_runner.execute(cdn_snippet)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "External CDNs prohibited" in res.stderr


def test_tailwind_timeout_contained(tailwind_runner):
    infinite_loop = '<script>while (true) {}</script><div class="p-4">Loop</div>'
    res = tailwind_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_tailwind_determinism(tailwind_runner):
    snippet = '<div class="p-4 text-white">Consistent Box</div>'
    res1 = tailwind_runner.execute(snippet)
    res2 = tailwind_runner.execute(snippet)

    norm1 = tailwind_runner.normalize(res1.stdout)
    norm2 = tailwind_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "tailwind_render_000000000000.png" in norm1


def test_tailwind_exercise_proof_reference_passes_naive_fails(tailwind_runner):
    exercise = {
        "problem_statement": "Create a container with blue-600 background and rounded-lg border",
        "expected_class": "bg-blue-600",
    }

    reference_solution = '<div class="bg-blue-600 p-6 rounded-lg text-white">Feature Banner</div>'
    naive_solution = '<div class="bg-red-500 p-6 rounded-lg text-white">Feature Banner</div>'

    ref_res = tailwind_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = tailwind_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0
