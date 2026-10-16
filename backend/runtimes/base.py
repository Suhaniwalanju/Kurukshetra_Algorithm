import os
import re
import sys
import time
import shutil
import tempfile
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


OUTPUT_SIZE_CAP_BYTES = 64 * 1024  # 64 KB output cap


@dataclass
class RunResult:
    status: str  # "pass", "fail", "warning", "timeout", "error"
    compile_output: str = ""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    command: str = ""
    artifacts: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    deprecations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "compile_output": self.compile_output,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "command": self.command,
            "artifacts": self.artifacts,
            "warnings": self.warnings,
            "deprecations": self.deprecations,
        }


@dataclass
class TestResult:
    __test__ = False
    passed: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    test_matrix: List[Dict[str, Any]] = field(default_factory=list)
    output: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "test_matrix": self.test_matrix,
            "output": self.output,
            "duration_ms": self.duration_ms,
        }


class LanguageRunner(ABC):
    """
    Abstract LanguageRunner plugin interface for Verified Course Material Studio.
    Every language/framework track implements this base adapter.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.track_id: str = config.get("id", "generic")
        self.display_name: str = config.get("display_name", self.track_id)
        self.pinned_version: str = config.get("pinned_version", "latest")
        self.docker_image: str = config.get("docker_image", "")
        self.file_extension: str = config.get("file_extension", ".txt")
        self.main_file: str = config.get("main_file", f"main{self.file_extension}")
        self.docker_path: Optional[str] = shutil.which("docker")

    @abstractmethod
    def prepare(self, snippet: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Wraps code fragment into a runnable unit, generates boilerplate,
        and returns a dictionary of filename -> file_content.
        Must include at least self.main_file.
        """
        pass

    @abstractmethod
    def execute(self, snippet: str, timeout_sec: int = 20, options: Optional[Dict[str, Any]] = None) -> RunResult:
        """
        Executes code snippet inside isolated sandbox (Docker or hardened local runner).
        Returns RunResult.
        """
        pass

    @abstractmethod
    def run_tests(self, exercise: Dict[str, Any], solution: str, timeout_sec: int = 20) -> TestResult:
        """
        Runs student-facing tests against given solution (reference, naive, or mutant).
        Returns TestResult with pass/fail matrix.
        """
        pass

    @abstractmethod
    def normalize(self, output: str) -> str:
        """
        Normalizes outputs (e.g. timestamps, memory addresses, ObjectIds, dynamic ports)
        to produce deterministic text for output verification.
        """
        pass

    def healthcheck(self) -> Dict[str, Any]:
        """
        Verifies health and readiness of the runner.
        """
        docker_available = self.is_docker_available()
        return {
            "track": self.track_id,
            "display_name": self.display_name,
            "pinned_version": self.pinned_version,
            "docker_image": self.docker_image,
            "docker_available": docker_available,
            "status": "ready" if docker_available or self._has_local_toolchain() else "standby",
            "mode": "docker" if docker_available else "isolated_subprocess",
        }

    def is_docker_available(self) -> bool:
        if not self.docker_path:
            return False
        try:
            res = subprocess.run([self.docker_path, "info"], capture_output=True, timeout=3)
            return res.returncode == 0
        except Exception:
            return False

    def _has_local_toolchain(self) -> bool:
        """Override in subclasses to check if local compiler/runtime is installed."""
        return True

    def _truncate_output(self, text: str) -> str:
        """Enforces output size cap to prevent runaway memory consumption."""
        if len(text.encode("utf-8", errors="ignore")) > OUTPUT_SIZE_CAP_BYTES:
            truncated = text.encode("utf-8")[:OUTPUT_SIZE_CAP_BYTES].decode("utf-8", errors="ignore")
            return truncated + "\n... [Output truncated at 64KB cap]"
        return text

    def run_in_docker(
        self,
        files: Dict[str, str],
        command: str,
        timeout_sec: int = 20,
        network: str = "none",
        env: Optional[Dict[str, str]] = None,
    ) -> RunResult:
        """
        Executes command in a fresh, hardened Docker container per run.
        Enforces:
        - --network none (or custom internal network)
        - --memory 512m
        - --cpus 1.0
        - --pids-limit 100
        - --read-only root filesystem with /tmp tmpfs
        - non-root user (1001:1001)
        - 20s configurable timeout
        """
        with tempfile.TemporaryDirectory(prefix=f"studio_dock_{self.track_id}_") as tmpdir:
            for fname, content in files.items():
                fpath = os.path.join(tmpdir, fname)
                os.makedirs(os.path.dirname(fpath), exist_ok=True)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(content)

            docker_cmd = [
                self.docker_path,
                "run",
                "--rm",
                f"--network={network}",
                "--memory=512m",
                "--cpus=1.0",
                "--pids-limit=100",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=64m",
                "-v",
                f"{tmpdir}:/workspace:rw",
                "-w",
                "/workspace",
                "--user",
                "1001:1001",
            ]

            if env:
                for k, v in env.items():
                    docker_cmd.extend(["-e", f"{k}={v}"])

            docker_cmd.append(self.docker_image)
            docker_cmd.extend(["sh", "-c", command])

            start_t = time.time()
            try:
                proc = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                )
                duration_ms = (time.time() - start_t) * 1000
                stdout = self._truncate_output(proc.stdout)
                stderr = self._truncate_output(proc.stderr)
                status = "pass" if proc.returncode == 0 else "fail"
                return RunResult(
                    status=status,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=proc.returncode,
                    duration_ms=duration_ms,
                    command=command,
                )
            except subprocess.TimeoutExpired:
                duration_ms = (time.time() - start_t) * 1000
                return RunResult(
                    status="timeout",
                    stdout="",
                    stderr=f"[Sandbox Timeout: Container exceeded {timeout_sec}s execution limit and was killed]",
                    exit_code=124,
                    duration_ms=duration_ms,
                    command=command,
                )
            except Exception as e:
                duration_ms = (time.time() - start_t) * 1000
                return RunResult(
                    status="error",
                    stdout="",
                    stderr=f"Docker runner error: {str(e)}",
                    exit_code=1,
                    duration_ms=duration_ms,
                    command=command,
                )
