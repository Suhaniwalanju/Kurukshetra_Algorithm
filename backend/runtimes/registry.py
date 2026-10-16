import os
import yaml
import importlib
from typing import Dict, Any, List, Optional
from backend.runtimes.base import LanguageRunner

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "technologies.yaml")


class RuntimeRegistry:
    """
    Plugin Registry for Language and Technology Runtimes.
    Discovers and registers adapters dynamically from /backend/runtimes/<track>.py
    based on /config/technologies.yaml.
    """

    def __init__(self, config_path: str = CONFIG_PATH):
        self.config_path = config_path
        self.configs: Dict[str, Any] = {}
        self.runners: Dict[str, LanguageRunner] = {}
        self.load()

    def load(self):
        """Loads configuration and instantiates discovered runtime adapters."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                    self.configs = data.get("technologies", {})
            except Exception as e:
                print(f"[RuntimeRegistry] Failed to read {self.config_path}: {e}")

        for track_id, cfg in self.configs.items():
            self._register_adapter(track_id, cfg)

    def _register_adapter(self, track_id: str, cfg: Dict[str, Any]):
        """Dynamically imports and registers adapter from backend.runtimes.<track_id>."""
        module_name = f"backend.runtimes.{track_id}"
        try:
            mod = importlib.import_module(module_name)
            # Find LanguageRunner subclass in module
            runner_cls = None
            if hasattr(mod, "RUNNER_CLASS"):
                runner_cls = getattr(mod, "RUNNER_CLASS")
            else:
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, LanguageRunner)
                        and attr is not LanguageRunner
                    ):
                        runner_cls = attr
                        break

            if runner_cls:
                runner_instance = runner_cls(cfg)
                self.runners[track_id] = runner_instance
            else:
                print(f"[RuntimeRegistry] Warning: No LanguageRunner subclass found in {module_name}")
        except ModuleNotFoundError:
            # Module not implemented yet, skip silently
            pass
        except Exception as e:
            print(f"[RuntimeRegistry] Failed to load adapter for {track_id}: {e}")

    def get_runner(self, track_id: str) -> Optional[LanguageRunner]:
        """Returns runner adapter for track_id, with normalization for common aliases."""
        clean_id = (track_id or "").lower().strip()
        # Aliases mapping
        alias_map = {
            "py": "python",
            "python3": "python",
            "python312": "python",
            "temurin": "java",
            "java21": "java",
            "spring": "java",
            "spring-boot": "java",
            "spring boot": "java",
            "c++": "cpp",
            "c++20": "cpp",
            "postgres": "sql",
            "postgresql": "sql",
            "node": "node_express",
            "nodejs": "node_express",
            "express": "node_express",
            "html": "web_foundations",
            "css": "web_foundations",
            "js": "web_foundations",
            "web": "web_foundations",
            "mongo": "mongodb",
        }
        resolved_id = alias_map.get(clean_id, clean_id)
        if resolved_id in self.runners:
            return self.runners[resolved_id]

        # Try on-demand load if in configs
        if resolved_id in self.configs and resolved_id not in self.runners:
            self._register_adapter(resolved_id, self.configs[resolved_id])
            return self.runners.get(resolved_id)

        return None

    def list_tracks(self) -> List[Dict[str, Any]]:
        """Lists all configured technologies and their status."""
        result = []
        for track_id, cfg in self.configs.items():
            runner = self.runners.get(track_id)
            result.append({
                "id": track_id,
                "display_name": cfg.get("display_name", track_id),
                "pinned_version": cfg.get("pinned_version", ""),
                "docker_image": cfg.get("docker_image", ""),
                "output_type": cfg.get("output_type", "text"),
                "adapter_loaded": runner is not None,
                "trusted_docs_domains": cfg.get("trusted_docs_domains", []),
            })
        return result

    def healthcheck_all(self) -> Dict[str, Any]:
        """Runs health checks on all loaded runtime runners."""
        health = {
            "total_tracks": len(self.configs),
            "loaded_adapters": len(self.runners),
            "tracks": {},
        }
        for track_id, runner in self.runners.items():
            health["tracks"][track_id] = runner.healthcheck()
        return health


runtime_registry = RuntimeRegistry()
