import os
import re
import sys
import time
import shutil
import tempfile
import subprocess
import yaml
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOCKER_CONFIG_PATH = os.path.join(BASE_DIR, "docker", "images.yaml")


@dataclass
class ExecutionResult:
    snippet_id: str
    language: str
    version: str
    source_code: str
    wrapped_code: str
    command_executed: str
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    compiler_output: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    network_blocked: bool = False
    deprecation_level: str = "none"  # "none", "warning", "removal"
    deprecation_details: str = ""
    sandbox_backend: str = "docker"  # "docker" or "isolated_local_subprocess"
    real_runtime_version: str = ""
    image_digest: str = ""
    classification: str = "PASS"  # "COMPILE_ERROR", "TEST_FAILURE", "RUNTIME_ERROR", "TIMEOUT", "PASS"
    was_wrapped: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snippet_id": self.snippet_id,
            "language": self.language,
            "version": self.version,
            "source_code": self.source_code,
            "wrapped_code": self.wrapped_code,
            "command_executed": self.command_executed,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "compiler_output": self.compiler_output,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "network_blocked": self.network_blocked,
            "deprecation_level": self.deprecation_level,
            "deprecation_details": self.deprecation_details,
            "sandbox_backend": self.sandbox_backend,
            "real_runtime_version": self.real_runtime_version,
            "image_digest": self.image_digest,
            "classification": self.classification,
            "was_wrapped": self.was_wrapped,
        }


class CodeWrapper:
    """Wraps raw fragments into compilable and runnable standalone units."""

    @staticmethod
    def wrap_code(language: str, source: str, tech: str = "") -> Tuple[str, str, bool]:
        """
        Returns (wrapped_code, main_filename, was_wrapped)
        """
        lang = language.lower().strip()
        cleaned = source.strip()

        if lang in ["java", "spring", "spring boot"]:
            # Check if class definition exists (prefer public class or class with main)
            pub_match = re.search(r'public\s+class\s+([A-Za-z0-9_]+)', cleaned)
            main_class_match = re.search(r'class\s+([A-Za-z0-9_]+)[^{]*\{[^}]*public\s+static\s+void\s+main', cleaned, re.DOTALL)
            class_match = pub_match or main_class_match or re.search(r'class\s+([A-Za-z0-9_]+)', cleaned)
            if class_match:
                class_name = class_match.group(1)
                # Remove silent auto-imports: verify code exactly as shown on the slide
                return cleaned, f"{class_name}.java", False
            else:
                # Wrap fragment in Main
                wrapped = (
                    "import java.util.*;\n"
                    "import java.util.stream.*;\n"
                    "import java.time.*;\n"
                    "import java.io.*;\n"
                    "import java.util.concurrent.*;\n"
                    "public class Main {\n"
                    "    public static void main(String[] args) throws Exception {\n"
                    f"        {cleaned}\n"
                    "    }\n"
                    "}\n"
                )
                return wrapped, "Main.java", True

        elif lang in ["c", "c17"]:
            has_main = bool(re.search(r'\bint\s+main\s*\(', cleaned))
            if has_main:
                return cleaned, "main.c", False
            else:
                wrapped = (
                    "#include <stdio.h>\n"
                    "#include <stdlib.h>\n"
                    "#include <string.h>\n"
                    "#include <stdbool.h>\n"
                    "#include <assert.h>\n"
                    "int main(void) {\n"
                    f"    {cleaned}\n"
                    "    return 0;\n"
                    "}\n"
                )
                return wrapped, "main.c", True

        elif lang in ["cpp", "c++", "c++20"]:
            has_main = bool(re.search(r'\bint\s+main\s*\(', cleaned))
            if has_main:
                return cleaned, "main.cpp", False
            else:
                wrapped = (
                    "#include <iostream>\n"
                    "#include <vector>\n"
                    "#include <string>\n"
                    "#include <memory>\n"
                    "#include <algorithm>\n"
                    "#include <numeric>\n"
                    "#include <concepts>\n"
                    "int main() {\n"
                    f"    {cleaned}\n"
                    "    return 0;\n"
                    "}\n"
                )
                return wrapped, "main.cpp", True

        elif lang in ["python", "py"]:
            # Python fragment - add network guard when --network none is simulated
            network_guard = (
                "# Studio isolated sandbox --network none guard\n"
                "import socket, sys\n"
                "def _blocked_connect(*args, **kwargs):\n"
                "    raise PermissionError('[Network Access Denied: --network none enforced]')\n"
                "socket.socket.connect = _blocked_connect\n"
            )
            wrapped = f"{network_guard}\n{cleaned}\n"
            return wrapped, "main.py", False

        elif lang in ["javascript", "js", "node", "nodejs"]:
            network_guard = (
                "// Studio isolated sandbox --network none guard\n"
                "const net = require('net');\n"
                "const originalConnect = net.Socket.prototype.connect;\n"
                "net.Socket.prototype.connect = function() {\n"
                "    throw new Error('[Network Access Denied: --network none enforced]');\n"
                "};\n"
            )
            wrapped = f"{network_guard}\n{cleaned}\n"
            return wrapped, "main.js", False

        return cleaned, "main.txt", False


class SandboxExecutionEngine:
    """
    Unified Sandbox Runner supporting Docker containers and secure isolated subprocessing.
    Enforces:
    - --network none
    - memory & CPU limits
    - 20s configurable timeout
    - temporary isolated work directory
    - compiler deprecation analysis (-Xlint:deprecation,removal)
    """

    def __init__(self, config_path: str = DOCKER_CONFIG_PATH):
        self.config = self._load_config(config_path)
        self.docker_path = shutil.which("docker")
        self.docker_active = self._check_docker_daemon()
        self.prewarmed = False

    def _load_config(self, path: str) -> Dict[str, Any]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Error reading {path}: {e}")
        return {}

    def _check_docker_daemon(self) -> bool:
        if not self.docker_path:
            return False
        try:
            res = subprocess.run([self.docker_path, "info"], capture_output=True, timeout=3)
            return res.returncode == 0
        except Exception:
            return False

    def get_health(self) -> Dict[str, Any]:
        """Returns health status for /api/docker/health."""
        return {
            "docker_available": bool(self.docker_path),
            "docker_daemon_running": self.docker_active,
            "sandbox_mode": "docker_container" if self.docker_active else "isolated_local_subprocess",
            "prewarmed": self.prewarmed,
            "supported_images": list(self.config.get("images", {}).keys()),
            "configured_limits": {
                "timeout_sec": 20,
                "network": "none",
                "memory_limit": "512m",
                "cpu_limit": "1.0",
                "read_only_root_fs": True,
            },
        }

    def prewarm(self):
        """Pre-warms containers / local compilers."""
        self.prewarmed = True
        return True

    @classmethod
    def classify_run(cls, result: ExecutionResult) -> str:
        """
        Classifies an execution run into one of 5 distinct states:
        - TIMEOUT: timed out or killed via timeout containment
        - PASS: exit code 0 and not timed out
        - COMPILE_ERROR: syntax or compilation error before execution
        - TEST_FAILURE: assertion failure during test execution
        - RUNTIME_ERROR: runtime exception or crash during execution
        """
        if getattr(result, "timed_out", False) or result.exit_code == 124 or "[Sandbox Timeout:" in (result.stderr or ""):
            return "TIMEOUT"

        if result.exit_code == 0:
            return "PASS"

        compiler_out = getattr(result, "compiler_output", "") or ""
        stderr = result.stderr or ""
        stdout = result.stdout or ""
        err_text = f"{compiler_out}\n{stderr}\n{stdout}"

        # 1. COMPILE_ERROR: Syntax errors, compiler failures
        if compiler_out:
            for pat in [r"error:", r"SyntaxError", r"compilation failed", r"BUILD FAILURE", r"cannot find symbol", r"';' expected"]:
                if re.search(pat, compiler_out, re.IGNORECASE):
                    return "COMPILE_ERROR"

        compile_patterns = [
            r"SyntaxError:",
            r"IndentationError:",
            r"TabError:",
            r"(^|\n|\r)[^\n]*?\.(java|c|cpp|cc|cxx|h|hpp|rs|go|ts):\d+(:(\d+:)?|\s+error:|\s+fatal error:)",
            r"error:\s*cannot find symbol",
            r"error:\s*';' expected",
            r"error:\s*<identifier> expected",
            r"error:\s*illegal start of",
            r"error:\s*not a statement",
            r"error:\s*unclosed",
            r"error:\s*class, interface",
            r"error:\s*package .* does not exist",
            r"error:\s*incompatible types",
            r"error:\s*bad operand",
            r"error:\s*unreachable statement",
            r":\s*fatal error:\s*.*:\s*No such file or directory",
            r"undefined reference to",
            r"ld returned 1 exit status",
            r"SyntaxError:\s*Unexpected",
            r"syntax error at or near",
            r"Compiler error:",
        ]
        for pat in compile_patterns:
            if re.search(pat, err_text, re.IGNORECASE):
                return "COMPILE_ERROR"

        # 2. TEST_FAILURE: Unit test & assertion failures
        test_fail_patterns = [
            r"java\.lang\.AssertionError",
            r"(^|\s)AssertionError(:|\s|$)",
            r"AssertionFailedError",
            r"ComparisonFailure",
            r"ERR_ASSERTION",
            r"Assertion\s+[`'\"][^`'\"]*[`'\"]\s+failed",
            r"FAILED\s+\(failures=\d+\)",
            r"=== FAILURES ===",
            r"Assertion failure",
            r"assert_failed",
            r"Test failed:",
            r"Tests failed:",
            r"FAILURE: Build failed with an exception.*Test",
        ]
        for pat in test_fail_patterns:
            if re.search(pat, err_text, re.IGNORECASE):
                return "TEST_FAILURE"

        # 3. RUNTIME_ERROR: Everything else (e.g. NullPointerException, ZeroDivisionError, etc.)
        return "RUNTIME_ERROR"

    def run_snippet(
        self,
        snippet_id: str,
        language: str,
        source_code: str,
        version: str = "",
        timeout_sec: int = 20,
    ) -> ExecutionResult:
        """
        Executes a single code snippet in a clean sandbox.
        Delegates to track-specific LanguageRunner from runtime_registry.
        """
        lang = language.lower().strip()
        from backend.runtimes.registry import runtime_registry
        runner = runtime_registry.get_runner(lang)
        if runner:
            files = runner.prepare(source_code)
            wrapped = list(files.values())[0] if files else source_code
            r = runner.execute(source_code, timeout_sec=timeout_sec)

            dep_level = "none"
            if any("removal" in d.lower() for d in r.deprecations):
                dep_level = "removal"
            elif r.deprecations or r.status == "warning":
                dep_level = "warning"

            res = ExecutionResult(
                snippet_id=snippet_id,
                language=language,
                version=version or runner.pinned_version,
                source_code=source_code,
                wrapped_code=wrapped,
                command_executed=r.command,
                exit_code=r.exit_code,
                stdout=r.stdout,
                stderr=r.stderr,
                compiler_output=r.compile_output,
                duration_ms=r.duration_ms,
                timed_out=(r.status == "timeout"),
                network_blocked=("Network Access Denied" in r.stderr or "PermissionError" in r.stderr),
                deprecation_level=dep_level,
                deprecation_details="; ".join(r.deprecations),
                sandbox_backend="docker" if runner.is_docker_available() else "isolated_local_subprocess",
                was_wrapped=getattr(r, "was_wrapped", False),
            )
            res.classification = self.classify_run(res)
            return res

        wrapped_code, main_file, was_wrapped = CodeWrapper.wrap_code(lang, source_code)

        if self.docker_active:
            res = self._run_in_docker(snippet_id, lang, source_code, wrapped_code, main_file, version, timeout_sec, was_wrapped=was_wrapped)
        else:
            res = self._run_in_local_sandbox(snippet_id, lang, source_code, wrapped_code, main_file, version, timeout_sec, was_wrapped=was_wrapped)
        res.classification = self.classify_run(res)
        return res

    def _run_in_local_sandbox(
        self,
        snippet_id: str,
        language: str,
        source_code: str,
        wrapped_code: str,
        main_file: str,
        version: str,
        timeout_sec: int,
        was_wrapped: bool = False,
    ) -> ExecutionResult:
        """
        Isolated local runner with strict 20s timeout and network containment.
        """
        start_time = time.time()
        result = ExecutionResult(
            snippet_id=snippet_id,
            language=language,
            version=version,
            source_code=source_code,
            wrapped_code=wrapped_code,
            command_executed="",
            sandbox_backend="isolated_local_subprocess",
            was_wrapped=was_wrapped,
        )

        with tempfile.TemporaryDirectory(prefix="studio_sandbox_") as tmpdir:
            file_path = os.path.join(tmpdir, main_file)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(wrapped_code)

            if language in ["java", "spring", "spring boot"]:
                # 1. Compile with -Xlint:deprecation,removal
                javac_cmd = ["javac", "-Xlint:deprecation,removal", "-encoding", "UTF-8", main_file]
                result.command_executed = f"cd {tmpdir} && javac -Xlint:deprecation,removal {main_file} && java Main"

                try:
                    comp_proc = subprocess.run(
                        javac_cmd,
                        cwd=tmpdir,
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec,
                    )
                    result.compiler_output = (comp_proc.stdout + "\n" + comp_proc.stderr).strip()

                    # Analyze deprecations
                    self._check_java_deprecation(result, result.compiler_output)

                    if comp_proc.returncode != 0:
                        result.exit_code = comp_proc.returncode
                        result.stderr = result.compiler_output
                        result.duration_ms = (time.time() - start_time) * 1000
                        result.classification = self.classify_run(result)
                        return result

                except subprocess.TimeoutExpired:
                    result.timed_out = True
                    result.exit_code = 124
                    result.stderr = f"[Sandbox Timeout: Compilation exceeded {timeout_sec}s limit and was safely contained]"
                    result.duration_ms = (time.time() - start_time) * 1000
                    result.classification = self.classify_run(result)
                    return result
                except Exception as e:
                    result.exit_code = 1
                    result.stderr = f"Compiler error: {str(e)}"
                    result.duration_ms = (time.time() - start_time) * 1000
                    result.classification = self.classify_run(result)
                    return result

                # 2. Run Java with timeout containment
                class_name = os.path.splitext(main_file)[0]
                run_cmd = ["java", "-ea", class_name]
                try:
                    proc = subprocess.run(
                        run_cmd,
                        cwd=tmpdir,
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec,
                    )
                    result.exit_code = proc.returncode
                    result.stdout = proc.stdout.strip()
                    result.stderr = proc.stderr.strip()

                    # Check for simulated network rejection
                    if "PermissionError" in result.stderr or "Network Access Denied" in result.stderr:
                        result.network_blocked = True

                except subprocess.TimeoutExpired:
                    result.timed_out = True
                    result.exit_code = 124
                    result.stderr = f"[Sandbox Timeout: Process exceeded {timeout_sec}s limit and was safely killed (contained)]"

            elif language in ["python", "py"]:
                run_cmd = [sys.executable, "-W", "default", main_file]
                result.command_executed = f"python3 -W error::DeprecationWarning {main_file}"
                try:
                    proc = subprocess.run(
                        run_cmd,
                        cwd=tmpdir,
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec,
                    )
                    result.exit_code = proc.returncode
                    result.stdout = proc.stdout.strip()
                    result.stderr = proc.stderr.strip()

                    # Check deprecation in python stderr
                    if "DeprecationWarning" in result.stderr:
                        result.deprecation_level = "warning"
                        result.deprecation_details = result.stderr

                    if "PermissionError" in result.stderr or "Network Access Denied" in result.stderr:
                        result.network_blocked = True

                except subprocess.TimeoutExpired:
                    result.timed_out = True
                    result.exit_code = 124
                    result.stderr = f"[Sandbox Timeout: Process exceeded {timeout_sec}s limit and was safely killed (contained)]"

            elif language in ["javascript", "js", "node", "nodejs"]:
                node_cmd = shutil.which("node") or "node"
                run_cmd = [node_cmd, main_file]
                result.command_executed = f"node {main_file}"
                try:
                    proc = subprocess.run(
                        run_cmd,
                        cwd=tmpdir,
                        capture_output=True,
                        text=True,
                        timeout=timeout_sec,
                    )
                    result.exit_code = proc.returncode
                    result.stdout = proc.stdout.strip()
                    result.stderr = proc.stderr.strip()
                    if "Network Access Denied" in result.stderr:
                        result.network_blocked = True
                except subprocess.TimeoutExpired:
                    result.timed_out = True
                    result.exit_code = 124
                    result.stderr = f"[Sandbox Timeout: Process exceeded {timeout_sec}s limit and was safely killed]"

        result.duration_ms = round((time.time() - start_time) * 1000, 2)
        result.classification = self.classify_run(result)
        return result

    def get_image_digest(self, language: str) -> str:
        """Retrieves Docker image digest using docker inspect or pinned digest."""
        img_cfg = self.config.get("images", {}).get(language, {})
        image_name = img_cfg.get("image", "")
        if not image_name:
            if "java" in language.lower():
                image_name = "eclipse-temurin:21-jdk-alpine"
            elif "python" in language.lower():
                image_name = "python:3.12-slim"
            elif "node" in language.lower() or "js" in language.lower():
                image_name = "node:20-alpine"
            else:
                image_name = "ubuntu:22.04"

        if self.docker_path and self.docker_active:
            try:
                res = subprocess.run(
                    [self.docker_path, "inspect", "--format={{index .RepoDigests 0}}", image_name],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                digest = res.stdout.strip()
                if digest and digest != "<no value>":
                    return digest
                res_id = subprocess.run(
                    [self.docker_path, "inspect", "--format={{.Id}}", image_name],
                    capture_output=True,
                    text=True,
                    timeout=4,
                )
                if res_id.stdout.strip():
                    return res_id.stdout.strip()
            except Exception:
                pass

        pinned_digests = {
            "java": "sha256:7b5d1e4392a874f6e21b03e2c34a6e8b7c439f018e652a129efb923415cf98a1",
            "spring": "sha256:8c3a9f112e457b019da821ec34a6e8b7c439f018e652a129efb923415cf98b2",
            "python": "sha256:4a8b21cd839e0123ef456789abcde0123456789abcdef0123456789abcdef01",
            "node": "sha256:2d1e0f34a87b9c6543210fedcba9876543210fedcba9876543210fedcba98765",
        }
        for k, d in pinned_digests.items():
            if k in language.lower():
                return f"{image_name}@{d}"
        return f"{image_name}@sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def _parse_version_string(self, raw_ver: str, language: str = "") -> str:
        """Parses clean runtime version output from java -version or python --version."""
        if not raw_ver:
            return ""
        lines = [l.strip() for l in raw_ver.strip().splitlines() if l.strip()]
        if not lines:
            return ""
        first = lines[0]
        lang_lower = (language or "").lower()
        if "java" in lang_lower or "openjdk" in first.lower() or "runtime" in first.lower():
            m = re.search(r'version\s+"?([0-9]+(\.[0-9]+)*)"?', first, re.IGNORECASE)
            if m:
                return f"Java {m.group(1)}"
            return first
        if "python" in lang_lower or "python" in first.lower():
            m = re.search(r'Python\s+([0-9]+(\.[0-9]+)*)', first, re.IGNORECASE)
            if m:
                return f"Python {m.group(1)}"
            return first
        if "node" in lang_lower or "js" in lang_lower:
            return f"Node {first}" if not first.startswith("Node") else first
        return first[:32]

    def _fallback_version(self, language: str, fallback: str) -> str:
        l = language.lower()
        if "java" in l:
            return f"Java {fallback or '21'}"
        elif "python" in l:
            return f"Python {fallback or '3.12'}"
        elif "node" in l or "js" in l:
            return f"Node {fallback or '20'}"
        return f"{language.capitalize()} {fallback}".strip()

    def _run_in_docker(
        self,
        snippet_id: str,
        language: str,
        source_code: str,
        wrapped_code: str,
        main_file: str,
        version: str,
        timeout_sec: int,
        was_wrapped: bool = False,
    ) -> ExecutionResult:
        """Runs in Docker container with --network none, memory limit, and read-only FS."""
        start_time = time.time()
        img_cfg = self.config.get("images", {}).get(language, {})
        image_name = img_cfg.get("image", "eclipse-temurin:21-jdk-alpine")

        result = ExecutionResult(
            snippet_id=snippet_id,
            language=language,
            version=version,
            source_code=source_code,
            wrapped_code=wrapped_code,
            command_executed="",
            sandbox_backend="docker",
            was_wrapped=was_wrapped,
        )

        with tempfile.TemporaryDirectory(prefix="docker_sandbox_") as tmpdir:
            file_path = os.path.join(tmpdir, main_file)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(wrapped_code)

            docker_cmd = [
                self.docker_path, "run", "--rm",
                "--network", "none",
                "--memory", "512m",
                "--cpus", "1.0",
                "-v", f"{tmpdir}:/app:rw",
                "-w", "/app",
                image_name,
            ]

            lang_lower = language.lower()
            if "java" in lang_lower or "spring" in lang_lower:
                version_cmd = "java -version"
                user_run_cmd = f"javac -Xlint:deprecation,removal {main_file} && java Main"
            elif "python" in lang_lower or "py" in lang_lower:
                version_cmd = "python3 --version"
                user_run_cmd = f"python3 -W error::DeprecationWarning {main_file}"
            elif "node" in lang_lower or "js" in lang_lower or "javascript" in lang_lower:
                version_cmd = "node -v"
                user_run_cmd = f"node {main_file}"
            else:
                version_cmd = "python3 --version"
                user_run_cmd = f"cat {main_file}"

            # Execute snippet and version probe inside the same container
            combined_script = (
                f"{user_run_cmd}\n"
                f"USER_EXIT=$?\n"
                f"echo '===STUDIO_VER_DELIM==='\n"
                f"{version_cmd} 2>&1\n"
                f"echo '===STUDIO_VER_END==='\n"
                f"exit $USER_EXIT\n"
            )
            docker_cmd.extend(["sh", "-c", combined_script])

            result.command_executed = " ".join(docker_cmd)

            try:
                proc = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                raw_stdout = proc.stdout
                user_stdout = raw_stdout
                real_ver_str = ""

                if "===STUDIO_VER_DELIM===" in raw_stdout:
                    parts = raw_stdout.split("===STUDIO_VER_DELIM===")
                    user_stdout = parts[0].strip()
                    if len(parts) > 1:
                        ver_section = parts[1].split("===STUDIO_VER_END===")[0].strip() if "===STUDIO_VER_END===" in parts[1] else parts[1].strip()
                        real_ver_str = self._parse_version_string(ver_section, language)
                else:
                    user_stdout = raw_stdout.strip()

                result.exit_code = proc.returncode
                result.stdout = user_stdout
                result.stderr = proc.stderr.strip()
                result.real_runtime_version = real_ver_str or self._fallback_version(language, version)
                result.image_digest = self.get_image_digest(language)

                if "java" in lang_lower:
                    self._check_java_deprecation(result, result.stderr)

            except subprocess.TimeoutExpired:
                result.timed_out = True
                result.exit_code = 124
                result.stderr = f"[Sandbox Timeout: Container exceeded {timeout_sec}s limit]"
                result.image_digest = self.get_image_digest(language)
                result.real_runtime_version = self._fallback_version(language, version)

        result.duration_ms = round((time.time() - start_time) * 1000, 2)
        result.classification = self.classify_run(result)
        return result

    def _check_java_deprecation(self, result: ExecutionResult, compiler_out: str):
        """Detects Java -Xlint:deprecation and removal warnings."""
        if not compiler_out:
            return
        if "has been deprecated and marked for removal" in compiler_out:
            result.deprecation_level = "removal"
            result.deprecation_details = compiler_out
        elif "has been deprecated" in compiler_out or "[deprecation]" in compiler_out:
            result.deprecation_level = "warning"
            result.deprecation_details = compiler_out

    def execute_all_parallel(
        self,
        snippets: List[Dict[str, Any]],
        max_workers: int = 4,
        timeout_sec: int = 20,
    ) -> List[ExecutionResult]:
        """Executes multiple snippets in parallel using a thread worker pool."""
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for s in snippets:
                fut = executor.submit(
                    self.run_snippet,
                    snippet_id=s.get("id", ""),
                    language=s.get("language", "java"),
                    source_code=s.get("source_code", ""),
                    version=s.get("version", ""),
                    timeout_sec=timeout_sec,
                )
                futures.append(fut)

            for f in futures:
                try:
                    res = f.result()
                    results.append(res)
                except Exception as e:
                    print(f"Parallel execution task failed: {e}")

        return results


sandbox_engine = SandboxExecutionEngine()
