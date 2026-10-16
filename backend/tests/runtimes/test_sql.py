import pytest
from backend.runtimes.registry import runtime_registry
from backend.runtimes.sql import SqlRunner


@pytest.fixture
def sql_runner():
    runner = runtime_registry.get_runner("sql")
    assert runner is not None
    assert isinstance(runner, SqlRunner)
    return runner


def test_sql_hello_world_query(sql_runner):
    seed = "CREATE TABLE courses (id SERIAL, name TEXT, credits INT); INSERT INTO courses (name, credits) VALUES ('Distributed Systems', 4), ('Compilers', 3);"
    query = "SELECT name, credits FROM courses WHERE credits > 3;"
    res = sql_runner.execute(query, options={"seed_sql": seed})
    assert res.status == "pass"
    assert res.exit_code == 0
    assert "Distributed Systems" in res.stdout
    assert "table" in res.artifacts
    assert len(res.artifacts["table"]) == 1
    assert res.artifacts["table"][0]["name"] == "Distributed Systems"


def test_sql_syntax_error_cleanly_reported(sql_runner):
    broken_query = "SELEECT * FORM non_existent_table WHERE;"
    res = sql_runner.execute(broken_query)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "Syntax" in res.compile_output or "syntax error" in res.stderr.lower() or "error" in res.stderr.lower()


def test_sql_runtime_error_captured(sql_runner):
    bad_table_query = "SELECT * FROM missing_table_123;"
    res = sql_runner.execute(bad_table_query)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "no such table" in res.stderr.lower() or "does not exist" in res.stderr.lower()


def test_sql_timeout_contained(sql_runner):
    infinite_query = "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM cnt) SELECT * FROM cnt;"
    res = sql_runner.execute(infinite_query, timeout_sec=2)
    assert res.status == "timeout"
    assert res.exit_code == 124
    assert "Timeout" in res.stderr


def test_sql_drop_database_blocked(sql_runner):
    malicious_query = "DROP DATABASE studio_sandbox;"
    res = sql_runner.execute(malicious_query)
    assert res.status == "fail"
    assert res.exit_code != 0
    assert "DROP DATABASE is strictly prohibited" in res.stderr
    assert len(res.warnings) > 0


def test_sql_explain_query_plan(sql_runner):
    seed = "CREATE TABLE students (id SERIAL, gpa REAL); INSERT INTO students (gpa) VALUES (3.9), (3.5);"
    query = "SELECT * FROM students WHERE gpa >= 3.8;"
    res = sql_runner.execute(query, options={"seed_sql": seed, "explain": True})
    assert res.status == "pass"
    assert "explain" in res.artifacts
    assert len(res.artifacts["explain"]) > 0


def test_sql_determinism(sql_runner):
    query = "SELECT '2026-10-17 00:08:12' AS current_time, 42 AS answer;"
    res1 = sql_runner.execute(query)
    res2 = sql_runner.execute(query)

    norm1 = sql_runner.normalize(res1.stdout)
    norm2 = sql_runner.normalize(res2.stdout)

    assert norm1 == norm2
    assert "2026-01-01 00:00:00" in norm1


def test_sql_exercise_proof_reference_passes_naive_fails(sql_runner):
    exercise = {
        "problem_statement": "Select only active administrators",
        "seed_sql": (
            "CREATE TABLE staff (id SERIAL, name TEXT, role TEXT, active BOOLEAN);\n"
            "INSERT INTO staff (name, role, active) VALUES\n"
            "('Carol', 'admin', TRUE),\n"
            "('Dave', 'admin', FALSE),\n"
            "('Eve', 'user', TRUE);\n"
        ),
        "expected_rows_count": 1,
    }

    # Reference query correctly filters role and active status (returns 1 row)
    reference_query = "SELECT name FROM staff WHERE role = 'admin' AND active = 1;"

    # Naive query forgets to check active status (returns 2 rows)
    naive_query = "SELECT name FROM staff WHERE role = 'admin';"

    ref_res = sql_runner.run_tests(exercise, reference_query)
    assert ref_res.passed is True

    naive_res = sql_runner.run_tests(exercise, naive_query)
    assert naive_res.passed is False
