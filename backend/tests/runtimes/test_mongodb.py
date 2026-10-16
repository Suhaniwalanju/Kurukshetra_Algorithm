import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.mongodb import MongoDBRunner


@pytest.fixture
def mongo_runner():
    runner = runtime_registry.get_runner("mongodb")
    assert runner is not None
    assert isinstance(runner, MongoDBRunner)
    return runner


def test_mongo_hello_world_find(mongo_runner):
    code = 'db.articles.find({ status: "published" });'
    res = mongo_runner.execute(code)
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "documents" in res.artifacts
    assert len(res.artifacts["documents"]) > 0


def test_mongo_syntax_error_cleanly_reported(mongo_runner):
    broken_code = 'db.articles.find({ status: "published"'
    res = mongo_runner.execute(broken_code)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "SyntaxError" in res.stderr or "SyntaxError" in str(res.compile_output)


def test_mongo_runtime_error_captured(mongo_runner):
    invalid_pipeline = 'db.articles.aggregate([ { $invalidOperator: { field: 1 } } ]);'
    res = mongo_runner.execute(invalid_pipeline)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "Unrecognized pipeline stage" in res.stderr


def test_mongo_timeout_contained(mongo_runner):
    infinite_loop = 'while (true) { /* runaway cursor */ }'
    res = mongo_runner.execute(infinite_loop, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_mongo_network_blocked(mongo_runner):
    net_code = 'const client = new Mongo("mongodb://8.8.8.8:27017");'
    res = mongo_runner.execute(net_code)
    assert res.status == "fail"
    assert res.exit_code != 0


def test_mongo_determinism_normalizes_objectid_and_timestamp(mongo_runner):
    code = (
        '// MongoDB Query Document with dynamic IDs\n'
        'printjson({\n'
        '    _id: ObjectId("652f4a7b9c1d2e3f4a5b6c7d"),\n'
        '    createdAt: ISODate("2026-10-17T00:17:15.123Z")\n'
        '});\n'
    )
    res1 = mongo_runner.execute(code)
    res2 = mongo_runner.execute(code)

    norm1 = mongo_runner.normalize(res1.stdout)
    norm2 = mongo_runner.normalize(res2.stdout)

    assert norm1 == norm2
    # Ensure ObjectIds and timestamps are normalized to deterministic canonical forms
    assert "000000000000000000000000" in norm1
    assert "2026-01-01T00:00:00.000Z" in norm1


def test_mongo_exercise_proof_reference_passes_naive_fails(mongo_runner):
    exercise = {
        "problem_statement": "Filter published articles using $match",
        "expected_operator": "$match",
    }

    reference_solution = 'db.articles.aggregate([ { $match: { status: "published" } } ]);'
    naive_solution = 'db.articles.aggregate([ { $limit: 10 } ]);'

    ref_res = mongo_runner.run_tests(exercise, reference_solution)
    assert ref_res.passed is True

    naive_res = mongo_runner.run_tests(exercise, naive_solution)
    assert naive_res.passed is False
    assert naive_res.failed_tests > 0
