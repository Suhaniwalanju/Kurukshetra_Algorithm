import os
import re
import sys
import time
import socket
import tempfile
import subprocess
from typing import Dict, Any, Optional, List
from backend.runtimes.base import LanguageRunner, RunResult, TestResult


NETWORK_GUARD = (
    "# Studio isolated sandbox --network none guard\n"
    "import socket\n"
    "def _blocked_connect(*args, **kwargs):\n"
    "    raise PermissionError('[Network Access Denied: --network none enforced]')\n"
    "socket.socket.connect = _blocked_connect\n\n"
)


class PythonRunner(LanguageRunner):
    """
    Python 3.12 Runtime Adapter.
    Executes Python scripts and pytest suites inside isolated containers or hardened subprocessing.
    Enforces -W error::DeprecationWarning, network containment, and 20s timeout limits.
    """

    def prepare(self, snippet: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        options = options or {}
        wrap_network = options.get("network_guard", True)

        cleaned = snippet.strip()
        wrapped = (NETWORK_GUARD + cleaned) if wrap_network else cleaned
        return {"main.py": wrapped}

    def execute(self, snippet: str, timeout_sec: int = 20, options: Optional[Dict[str, Any]] = None) -> RunResult:
        files = self.prepare(snippet, options)
        command = "python3 -W error::DeprecationWarning main.py"

        if self.is_docker_available():
            res = self.run_in_docker(files, command, timeout_sec=timeout_sec, network="none")
            self._analyze_python_deprecations(res)
            return res

        # Hardened Local Runner Fallback
        start_time = time.time()
        with tempfile.TemporaryDirectory(prefix="studio_py_") as tmpdir:
            main_path = os.path.join(tmpdir, "main.py")
            with open(main_path, "w", encoding="utf-8") as f:
                f.write(files["main.py"])

            # 1. Syntax compile check
            try:
                compile(files["main.py"], "main.py", "exec")
            except SyntaxError as e:
                duration_ms = (time.time() - start_time) * 1000
                return RunResult(
                    status="fail",
                    compile_output=f"SyntaxError: {e.msg} (line {e.lineno})",
                    stdout="",
                    stderr=f"SyntaxError: {e.msg} on line {e.lineno}\n  {e.text}",
                    exit_code=1,
                    duration_ms=duration_ms,
                    command=command,
                )

            # 2. Run with deprecation checking
            # We pass -W error::DeprecationWarning
            run_cmd = [sys.executable, "-W", "error::DeprecationWarning", "main.py"]
            try:
                proc = subprocess.run(
                    run_cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                duration_ms = (time.time() - start_time) * 1000
                stdout = self._truncate_output(proc.stdout)
                stderr = self._truncate_output(proc.stderr)
                status = "pass" if proc.returncode == 0 else "fail"

                res = RunResult(
                    status=status,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=proc.returncode,
                    duration_ms=duration_ms,
                    command=command,
                )
                self._analyze_python_deprecations(res)
                return res

            except subprocess.TimeoutExpired:
                duration_ms = (time.time() - start_time) * 1000
                return RunResult(
                    status="timeout",
                    stdout="",
                    stderr=f"[Sandbox Timeout: Process exceeded {timeout_sec}s execution limit and was killed]",
                    exit_code=124,
                    duration_ms=duration_ms,
                    command=command,
                )
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                return RunResult(
                    status="error",
                    stdout="",
                    stderr=f"Execution error: {str(e)}",
                    exit_code=1,
                    duration_ms=duration_ms,
                    command=command,
                )

    def _analyze_python_deprecations(self, res: RunResult):
        combined = res.stderr + "\n" + res.stdout
        if "DeprecationWarning" in combined:
            res.deprecations.append("DeprecationWarning detected")
            if res.exit_code != 0:
                res.status = "fail"
            else:
                res.status = "warning"

    def run_tests(self, exercise: Dict[str, Any], solution: str, timeout_sec: int = 20) -> TestResult:
        """
        Runs student-facing tests against given solution.
        """
        start_time = time.time()
        test_code = exercise.get("test_code", "")

        # Combine solution and tests
        combined = f"{solution}\n\n{test_code}"
        files = {"test_runner.py": combined}

        with tempfile.TemporaryDirectory(prefix="studio_py_test_") as tmpdir:
            test_path = os.path.join(tmpdir, "test_runner.py")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write(combined)

            run_cmd = [sys.executable, "test_runner.py"]
            try:
                proc = subprocess.run(
                    run_cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                duration_ms = (time.time() - start_time) * 1000
                passed = proc.returncode == 0
                matrix = [
                    {
                        "name": "Suite Execution",
                        "status": "PASS" if passed else "FAIL",
                        "message": proc.stdout if passed else proc.stderr,
                    }
                ]
                return TestResult(
                    passed=passed,
                    total_tests=1,
                    passed_tests=1 if passed else 0,
                    failed_tests=0 if passed else 1,
                    test_matrix=matrix,
                    output=proc.stdout + "\n" + proc.stderr,
                    duration_ms=duration_ms,
                )
            except subprocess.TimeoutExpired:
                duration_ms = (time.time() - start_time) * 1000
                return TestResult(
                    passed=False,
                    total_tests=1,
                    passed_tests=0,
                    failed_tests=1,
                    test_matrix=[{"name": "Suite Execution", "status": "TIMEOUT", "message": "Test execution timed out"}],
                    output="TimeoutExpired",
                    duration_ms=duration_ms,
                )

    def normalize(self, output: str) -> str:
        """
        Normalizes memory addresses, temporary directory paths, and variable timings.
        """
        text = output or ""
        # Normalize memory addresses like <object at 0x0000019C67BBA7A0>
        text = re.sub(r"at 0x[0-9a-fA-F]+", "at 0x00000000", text)
        # Normalize Windows / temp paths
        text = re.sub(r'File ".*?[\\/]([^\\/]+)", line (\d+)', r'File "\1", line \2', text)
        # Normalize execution timing numbers e.g. "in 0.04s"
        text = re.sub(r"\bin \d+\.\d+s\b", "in 0.00s", text)
        return text.strip()


RUNNER_CLASS = PythonRunner
