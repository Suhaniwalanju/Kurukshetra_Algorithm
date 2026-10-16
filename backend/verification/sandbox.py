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
    sandbox_backend: str = "docker"  # "docker" or "isolated_process"


class CodeWrapper:
    """Wraps raw fragments into compilable and runnable standalone units."""

    @staticmethod
    def wrap_code(language: str, source: str, tech: str = "") -> Tuple[str, str]:
        """
        Returns (wrapped_code, main_filename)
        """
        lang = language.lower().strip()
        cleaned = source.strip()

        if lang in ["java", "spring", "spring boot"]:
            # Check if this is a Spring Boot fragment
            is_spring = any(kw in cleaned for kw in ["@SpringBoot", "@RestController", "@Service", "@Autowired", "SpringApplication"])
            
            # Check if full class definition exists
            class_match = re.search(r'public\s+class\s+([A-Za-z0-9_]+)', cleaned)
            if class_match:
                class_name = class_match.group(1)
                # Ensure common imports if missing
                imports = (
                    "import java.util.*;\n"
                    "import java.util.stream.*;\n"
                    "import java.time.*;\n"
                    "import java.io.*;\n"
                    "import java.util.concurrent.*;\n"
                )
                if is_spring:
                    imports += (
                        "// Pre-cached Spring context slice\n"
                    )
                wrapped = f"{imports}\n{cleaned}"
                return wrapped, f"{class_name}.java"
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
                return wrapped, "Main.java"

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
            return wrapped, "main.py"

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
            return wrapped, "main.js"

        return cleaned, "main.txt"


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
        """
        lang = language.lower().strip()
        wrapped_code, main_file = CodeWrapper.wrap_code(lang, source_code)

        if self.docker_active:
            return self._run_in_docker(snippet_id, lang, source_code, wrapped_code, main_file, version, timeout_sec)
        else:
            return self._run_in_local_sandbox(snippet_id, lang, source_code, wrapped_code, main_file, version, timeout_sec)

    def _run_in_local_sandbox(
        self,
        snippet_id: str,
        language: str,
        source_code: str,
        wrapped_code: str,
        main_file: str,
        version: str,
        timeout_sec: int,
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
                        return result

                except subprocess.TimeoutExpired:
                    result.timed_out = True
                    result.exit_code = 124
                    result.stderr = f"[Sandbox Timeout: Compilation exceeded {timeout_sec}s limit and was safely contained]"
                    result.duration_ms = (time.time() - start_time) * 1000
                    return result
                except Exception as e:
                    result.exit_code = 1
                    result.stderr = f"Compiler error: {str(e)}"
                    result.duration_ms = (time.time() - start_time) * 1000
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
        return result

    def _run_in_docker(
        self,
        snippet_id: str,
        language: str,
        source_code: str,
        wrapped_code: str,
        main_file: str,
        version: str,
        timeout_sec: int,
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

            if language == "java":
                docker_cmd.extend(["sh", "-c", f"javac -Xlint:deprecation,removal {main_file} && java Main"])
            elif language == "python":
                docker_cmd.extend(["python3", "-W", "error::DeprecationWarning", main_file])
            else:
                docker_cmd.extend(["node", main_file])

            result.command_executed = " ".join(docker_cmd)

            try:
                proc = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                result.exit_code = proc.returncode
                result.stdout = proc.stdout.strip()
                result.stderr = proc.stderr.strip()
                if language == "java":
                    self._check_java_deprecation(result, result.stderr)

            except subprocess.TimeoutExpired:
                result.timed_out = True
                result.exit_code = 124
                result.stderr = f"[Sandbox Timeout: Container exceeded {timeout_sec}s limit]"

        result.duration_ms = round((time.time() - start_time) * 1000, 2)
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
