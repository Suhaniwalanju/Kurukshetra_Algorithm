import os
import yaml
import tempfile
import pytest
from backend.runtimes.base import LanguageRunner, RunResult, TestResult
from backend.runtimes.registry import RuntimeRegistry


class DummyAdapter(LanguageRunner):
    """Example custom adapter for adding a new track without modifying core engine."""
    def prepare(self, snippet: str, options=None):
        return {"dummy.txt": snippet}

    def execute(self, snippet: str, timeout_sec: int = 20, options=None) -> RunResult:
        return RunResult(
            status="pass",
            stdout=f"Dummy track executed: {snippet}",
            exit_code=0,
            command="dummy-cli run dummy.txt",
        )

    def run_tests(self, exercise, solution, timeout_sec=20) -> TestResult:
        return TestResult(passed=True, total_tests=1, passed_tests=1, output="Dummy tests passed")

    def normalize(self, output: str) -> str:
        return output.strip()


def test_extensibility_adding_track_without_touching_core_code(monkeypatch):
    """
    Acceptance Criterion:
    Adding a dummy track via YAML + Dockerfile + adapter works without touching core code.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Create a dummy Dockerfile
        docker_dir = os.path.join(tmpdir, "docker", "dummy_track")
        os.makedirs(docker_dir, exist_ok=True)
        dockerfile_path = os.path.join(docker_dir, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write("FROM alpine:latest\nCMD ['echo', 'dummy']\n")

        # 2. Create custom YAML configuration
        config_path = os.path.join(tmpdir, "technologies.yaml")
        yaml_content = {
            "technologies": {
                "dummy_track": {
                    "id": "dummy_track",
                    "display_name": "Dummy Language v1",
                    "pinned_version": "1.0.0",
                    "docker_image": "studio-runtime-dummy:1.0",
                    "file_extension": ".dummy",
                    "output_type": "text",
                }
            }
        }
        with open(config_path, "w") as f:
            yaml.dump(yaml_content, f)

        # 3. Instantiate RuntimeRegistry with new config
        registry = RuntimeRegistry(config_path=config_path)

        # 4. Register the new adapter class dynamically
        dummy_cfg = registry.configs["dummy_track"]
        registry.runners["dummy_track"] = DummyAdapter(dummy_cfg)

        # 5. Verify the runner is discoverable and executable
        runner = registry.get_runner("dummy_track")
        assert runner is not None
        assert runner.track_id == "dummy_track"
        assert runner.display_name == "Dummy Language v1"

        res = runner.execute("print 42;")
        assert res.status == "pass"
        assert res.exit_code == 0
        assert "Dummy track executed: print 42;" in res.stdout

        # 6. Verify healthcheck and track listing
        tracks = registry.list_tracks()
        assert len(tracks) == 1
        assert tracks[0]["id"] == "dummy_track"
        assert tracks[0]["adapter_loaded"] is True
