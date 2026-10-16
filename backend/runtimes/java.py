import os
import re
import time
import shutil
import tempfile
import subprocess
from typing import Dict, Any, Optional, List
from backend.runtimes.base import LanguageRunner, RunResult, TestResult


COMMON_IMPORTS = (
    "import java.util.*;\n"
    "import java.util.stream.*;\n"
    "import java.time.*;\n"
    "import java.io.*;\n"
    "import java.util.concurrent.*;\n"
)


class JavaRunner(LanguageRunner):
    """
    Java 21 Runtime Adapter.
    Executes Java snippets with automatic class wrapping, JUnit test harnesses,
    and -Xlint:deprecation,removal inspection.
    """

    def _has_local_toolchain(self) -> bool:
        return shutil.which("javac") is not None and shutil.which("java") is not None

    def prepare(self, snippet: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        cleaned = snippet.strip()
        class_match = re.search(r'public\s+class\s+([A-Za-z0-9_]+)', cleaned)

        if class_match:
            class_name = class_match.group(1)
            wrapped = f"{COMMON_IMPORTS}\n{cleaned}"
            return {f"{class_name}.java": wrapped}
        else:
            wrapped = (
                f"{COMMON_IMPORTS}\n"
                f"public class Main {{\n"
                f"    public static void main(String[] args) throws Exception {{\n"
                f"        {cleaned}\n"
                f"    }}\n"
                f"}}\n"
            )
            return {"Main.java": wrapped}

    def execute(self, snippet: str, timeout_sec: int = 20, options: Optional[Dict[str, Any]] = None) -> RunResult:
        files = self.prepare(snippet, options)
        main_file = list(files.keys())[0]
        class_name = os.path.splitext(main_file)[0]
        command = f"javac -Xlint:deprecation,removal {main_file} && java -ea {class_name}"

        if self.is_docker_available():
            res = self.run_in_docker(files, command, timeout_sec=timeout_sec, network="none")
            self._analyze_java_deprecations(res)
            return res

        # Hardened Local Runner Fallback
        start_time = time.time()
        with tempfile.TemporaryDirectory(prefix="studio_java_") as tmpdir:
            file_path = os.path.join(tmpdir, main_file)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(files[main_file])

            # 1. Compile with -Xlint:deprecation,removal
            javac_cmd = ["javac", "-Xlint:deprecation,removal", "-encoding", "UTF-8", main_file]
            try:
                comp_proc = subprocess.run(
                    javac_cmd,
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                comp_output = (comp_proc.stdout + "\n" + comp_proc.stderr).strip()

                if comp_proc.returncode != 0:
                    duration_ms = (time.time() - start_time) * 1000
                    return RunResult(
                        status="fail",
                        compile_output=comp_output,
                        stdout="",
                        stderr=comp_output,
                        exit_code=comp_proc.returncode,
                        duration_ms=duration_ms,
                        command=command,
                    )

            except subprocess.TimeoutExpired:
                duration_ms = (time.time() - start_time) * 1000
                return RunResult(
                    status="timeout",
                    stdout="",
                    stderr=f"[Sandbox Timeout: Compilation exceeded {timeout_sec}s limit and was killed]",
                    exit_code=124,
                    duration_ms=duration_ms,
                    command=command,
                )
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                return RunResult(
                    status="error",
                    stdout="",
                    stderr=f"Compiler invocation error: {str(e)}",
                    exit_code=1,
                    duration_ms=duration_ms,
                    command=command,
                )

            # 2. Run class with assertions enabled (-ea)
            run_cmd = ["java", "-ea", class_name]
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
                    compile_output=comp_output,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=proc.returncode,
                    duration_ms=duration_ms,
                    command=command,
                )
                self._analyze_java_deprecations(res)
                return res

            except subprocess.TimeoutExpired:
                duration_ms = (time.time() - start_time) * 1000
                return RunResult(
                    status="timeout",
                    stdout="",
                    stderr=f"[Sandbox Timeout: Execution exceeded {timeout_sec}s limit and was killed]",
                    exit_code=124,
                    duration_ms=duration_ms,
                    command=command,
                )

    def _analyze_java_deprecations(self, res: RunResult):
        combined = (res.compile_output or "") + "\n" + (res.stderr or "")
        has_removal = "has been deprecated and marked for removal" in combined or "[removal]" in combined
        has_dep = "has been deprecated" in combined or "[deprecation]" in combined

        if has_removal:
            res.deprecations.append("Removal-level deprecation detected")
            res.status = "fail"
            res.exit_code = 1
            if not res.stderr:
                res.stderr = "Deprecation Error: API is marked for removal."
        elif has_dep:
            res.deprecations.append("Deprecation warning detected")
            if res.exit_code == 0:
                res.status = "warning"

    def run_tests(self, exercise: Dict[str, Any], solution: str, timeout_sec: int = 20) -> TestResult:
        start_time = time.time()
        test_code = exercise.get("test_code", "")

        # Clean public class in solution so it can compile alongside TestRunner in one file
        cleaned_sol = solution.replace("public class Solution", "class Solution")
        combined = f"{cleaned_sol}\n\n{test_code}"

        files = {"TestRunner.java": combined}
        with tempfile.TemporaryDirectory(prefix="studio_java_test_") as tmpdir:
            fpath = os.path.join(tmpdir, "TestRunner.java")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(combined)

            comp = subprocess.run(["javac", "TestRunner.java"], cwd=tmpdir, capture_output=True, text=True, timeout=timeout_sec)
            if comp.returncode != 0:
                duration_ms = (time.time() - start_time) * 1000
                return TestResult(
                    passed=False,
                    total_tests=1,
                    passed_tests=0,
                    failed_tests=1,
                    test_matrix=[{"name": "Compilation", "status": "FAIL", "message": comp.stderr}],
                    output=comp.stderr,
                    duration_ms=duration_ms,
                )

            proc = subprocess.run(["java", "-ea", "TestRunner"], cwd=tmpdir, capture_output=True, text=True, timeout=timeout_sec)
            duration_ms = (time.time() - start_time) * 1000
            passed = proc.returncode == 0
            matrix = [
                {
                    "name": "JUnit/Assertion Suite",
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

    def normalize(self, output: str) -> str:
        text = output or ""
        # Normalize Java Object hash codes like Main@15db9742
        text = re.sub(r'([A-Za-z0-9_]+)@[0-9a-fA-F]{4,16}', r'\1@00000000', text)
        # Normalize thread IDs or timestamps
        text = re.sub(r'VirtualThread\[#\d+,', 'VirtualThread[#0,', text)
        return text.strip()


RUNNER_CLASS = JavaRunner
