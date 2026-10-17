import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.node_express import NodeExpressRunner


@pytest.fixture
def node_runner():
    runner = runtime_registry.get_runner("node_express")
    assert runner is not None
    assert isinstance(runner, NodeExpressRunner)
    return runner


def test_node_express_hello_world_route(node_runner):
    code = (
        'app.get("/api/health", (req, res) => {\n'
        '    res.status(200).json({ status: "healthy", version: "20.18.0" });\n'
        '});\n'
    )
    res = node_runner.execute(code, options={"endpoint": "/api/health"})
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "artifacts" in res.to_dict()
    assert "http_response" in res.artifacts
    http_resp = res.artifacts["http_response"]
    assert http_resp["status"] == 200
    assert "healthy" in str(http_resp["body"])


def test_node_express_syntax_error_cleanly_reported(node_runner):
    broken_code = 'app.get("/api/data", (req, res => { missing_paren;'
    res = node_runner.execute(broken_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "SyntaxError" in res.stderr or "SyntaxError" in res.compile_output or "SyntaxError" in str(res.compile_output)


def test_node_express_runtime_error_captured(node_runner):
    error_code = 'const x = null; x.someMethodCall();'
    res = node_runner.execute(error_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "TypeError" in res.stderr or "error" in res.stderr.lower()


def test_node_express_timeout_contained(node_runner):
    infinite_loop = 'while (true) { /* runaway */ }'
    res = node_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_node_express_network_call_blocked(node_runner):
    net_code = 'const net = require("net"); const client = net.createConnection({ port: 80, host: "8.8.8.8" });'
    res = node_runner.execute(net_code)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_node_express_determinism(node_runner):
    code = (
        'console.log("Server listening on port 54321");\n'
        'console.log(\'date: "Sat, 17 Oct 2026 12:34:56 GMT"\');\n'
    )
    res1 = node_runner.execute(code)
    res2 = node_runner.execute(code)

    norm1 = node_runner.normalize(res1.stdout)
    norm2 = node_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "port 3000" in norm1
    assert 'date: "Sat, 17 Oct 2026 00:00:00 GMT"' in norm1


def test_node_express_exercise_proof_reference_passes_naive_fails(node_runner):
    exercise = {
        "problem_statement": "Expose GET /api/health returning HTTP 200 with { status: 'healthy' }",
    }

    reference_solution = (
        'app.get("/api/health", (req, res) => {\n'
        '    res.status(200).json({ status: "healthy" });\n'
        '});\n'
    )

    naive_solution = (
        'app.get("/api/health", (req, res) => {\n'
        '    res.status(500).json({ error: "Server Error" });\n'
        '});\n'
    )

    ref_res = node_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = node_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0


def test_node_throw_deprecation_enforced(node_runner):
    code = "process.emitWarning('This is deprecated', 'DeprecationWarning');"
    res = node_runner.execute(code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert any("DeprecationWarning" in d for d in res.deprecations) or "DeprecationWarning" in res.stderr
    assert "--throw-deprecation" in res.command

