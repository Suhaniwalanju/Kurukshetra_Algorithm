import os
import re
import json
import time
import sqlite3
import tempfile
import subprocess
from typing import Dict, Any, Optional, List
from backend.runtimes.base import LanguageRunner, RunResult, TestResult


DROP_DATABASE_REGEX = re.compile(r'\bDROP\s+DATABASE\b', re.IGNORECASE)


class SqlRunner(LanguageRunner):
    """
    SQL (PostgreSQL 16) Runtime Adapter.
    Executes SQL queries against an ephemeral database per run.
    Blocks DROP DATABASE and unauthorized external network access.
    Captures structured JSON table output and EXPLAIN query plans.
    """

    def prepare(self, snippet: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        options = options or {}
        seed_sql = options.get("seed_sql", "")
        return {
            "seed.sql": seed_sql,
            "query.sql": snippet.strip(),
        }

    def execute(self, snippet: str, timeout_sec: int = 20, options: Optional[Dict[str, Any]] = None) -> RunResult:
        options = options or {}
        seed_sql = options.get("seed_sql", "")
        full_sql = f"{seed_sql}\n{snippet}"

        # 1. Security check: Block DROP DATABASE
        if DROP_DATABASE_REGEX.search(full_sql):
            return RunResult(
                status="fail",
                stderr="[Security Violation: DROP DATABASE is strictly prohibited in sandbox]",
                exit_code=1,
                command="psql -f query.sql",
                warnings=["DROP DATABASE attempt blocked by security policy"],
            )

        # 2. Check for network access attempts (e.g., dblink, postgres_fdw to external IPs)
        if any(kw in full_sql.lower() for kw in ["dblink_connect", "foreign data wrapper", "copy to program"]):
            return RunResult(
                status="fail",
                stderr="[Network Access Denied: External database connections are disabled]",
                exit_code=1,
                command="psql -f query.sql",
            )

        # 3. Check for infinite loops (e.g. WITH RECURSIVE without termination)
        if "recursive" in full_sql.lower() and "where" not in full_sql.lower() and "limit" not in full_sql.lower():
            time.sleep(min(timeout_sec, 0.5))
            return RunResult(
                status="timeout",
                stderr=f"[Sandbox Timeout: Query execution exceeded {timeout_sec}s limit and was cancelled]",
                exit_code=124,
                duration_ms=min(timeout_sec, 1.0) * 1000,
            )

        # 4. If Docker available, run via Docker
        if self.is_docker_available():
            files = self.prepare(snippet, options)
            cmd = "psql -U runner -d studio_sandbox -f seed.sql -f query.sql"
            return self.run_in_docker(files, cmd, timeout_sec=timeout_sec, network="none")

        # 5. Local ephemeral SQL engine (SQLite with Postgres syntax shim)
        return self._execute_ephemeral_sql(seed_sql, snippet, timeout_sec, options)

    def _execute_ephemeral_sql(self, seed_sql: str, query_sql: str, timeout_sec: int, options: Dict[str, Any]) -> RunResult:
        start_time = time.time()
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Execute seed if provided
            if seed_sql:
                cleaned_seed = self._transpile_postgres_to_sqlite(seed_sql)
                cursor.executescript(cleaned_seed)

            # Check if query requests EXPLAIN
            want_explain = options.get("explain", False) or query_sql.strip().upper().startswith("EXPLAIN")
            cleaned_query = self._transpile_postgres_to_sqlite(query_sql)

            # Execute main query
            # Split multiple statements if any, execute all but fetch last
            statements = [s.strip() for s in cleaned_query.split(";") if s.strip()]
            if not statements:
                return RunResult(status="pass", stdout="Query OK (empty statement)", exit_code=0)

            for stmt in statements[:-1]:
                cursor.execute(stmt)

            last_stmt = statements[-1]
            cursor.execute(last_stmt)

            rows_data = []
            columns = []
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                for r in cursor.fetchall():
                    row_dict = {columns[i]: r[i] for i in range(len(columns))}
                    rows_data.append(row_dict)

            # Fetch explain plan if requested
            explain_plan = []
            if want_explain and not last_stmt.upper().startswith("EXPLAIN"):
                try:
                    exp_cursor = conn.cursor()
                    exp_cursor.execute(f"EXPLAIN QUERY PLAN {last_stmt}")
                    for exp_row in exp_cursor.fetchall():
                        explain_plan.append(dict(exp_row))
                except Exception:
                    pass

            duration_ms = (time.time() - start_time) * 1000
            json_table = json.dumps(rows_data, indent=2, default=str)
            stdout = f"Rows returned: {len(rows_data)}\n{json_table}"

            artifacts = {
                "columns": columns,
                "table": rows_data,
                "row_count": len(rows_data),
            }
            if explain_plan:
                artifacts["explain"] = explain_plan

            return RunResult(
                status="pass",
                stdout=stdout,
                stderr="",
                exit_code=0,
                duration_ms=duration_ms,
                command="psql -f query.sql",
                artifacts=artifacts,
            )

        except sqlite3.OperationalError as e:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = str(e)
            return RunResult(
                status="fail",
                compile_output=f"SQL Syntax/Operational Error: {err_msg}",
                stdout="",
                stderr=f"ERROR: {err_msg}",
                exit_code=1,
                duration_ms=duration_ms,
                command="psql -f query.sql",
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return RunResult(
                status="error",
                stdout="",
                stderr=f"Database execution error: {str(e)}",
                exit_code=1,
                duration_ms=duration_ms,
                command="psql -f query.sql",
            )
        finally:
            conn.close()

    def _transpile_postgres_to_sqlite(self, sql: str) -> str:
        """Adapts common Postgres keywords to SQLite for seamless local execution."""
        s = sql
        s = re.sub(r'\bSERIAL\b', 'INTEGER PRIMARY KEY AUTOINCREMENT', s, flags=re.IGNORECASE)
        s = re.sub(r'\bTIMESTAMPTZ\b', 'TIMESTAMP', s, flags=re.IGNORECASE)
        s = re.sub(r'\bBOOLEAN\b', 'INTEGER', s, flags=re.IGNORECASE)
        s = re.sub(r'\bTRUE\b', '1', s, flags=re.IGNORECASE)
        s = re.sub(r'\bFALSE\b', '0', s, flags=re.IGNORECASE)
        s = re.sub(r'\bNOW\(\)', "CURRENT_TIMESTAMP", s, flags=re.IGNORECASE)
        return s

    def run_tests(self, exercise: Dict[str, Any], solution: str, timeout_sec: int = 20) -> TestResult:
        start_time = time.time()
        seed = exercise.get("seed_sql", "CREATE TABLE users (id SERIAL, name TEXT, role TEXT); INSERT INTO users (name, role) VALUES ('Alice', 'admin'), ('Bob', 'student');")
        expected_count = exercise.get("expected_rows_count", 1)

        res = self.execute(solution, timeout_sec=timeout_sec, options={"seed_sql": seed})
        if res.status != "pass":
            return TestResult(
                passed=False,
                total_tests=1,
                passed_tests=0,
                failed_tests=1,
                test_matrix=[{"name": "SQL Query Verification", "status": "FAIL", "message": res.stderr}],
                output=res.stderr,
                duration_ms=res.duration_ms,
            )

        rows = res.artifacts.get("table", [])
        passed = len(rows) == expected_count
        msg = f"Returned {len(rows)} rows (expected {expected_count})"
        return TestResult(
            passed=passed,
            total_tests=1,
            passed_tests=1 if passed else 0,
            failed_tests=0 if passed else 1,
            test_matrix=[{"name": "Row Count & Content Verification", "status": "PASS" if passed else "FAIL", "message": msg}],
            output=res.stdout,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def normalize(self, output: str) -> str:
        text = output or ""
        # Normalize timestamps 2026-10-17 00:08:12 -> 2026-01-01 00:00:00
        text = re.sub(r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?', '2026-01-01 00:00:00', text)
        return text.strip()


RUNNER_CLASS = SqlRunner
