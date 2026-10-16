import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.runtimes.registry import runtime_registry


if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_health_checks():
    print("=" * 80)
    print(" Studio Language & Runtime Runners Health Check (make health)")
    print("=" * 80)

    health = runtime_registry.healthcheck_all()
    tracks = health.get("tracks", {})
    all_green = True

    print(f"{'TRACK':<18} | {'DISPLAY NAME':<28} | {'PINNED VERSION':<16} | {'STATUS'}")
    print("-" * 80)

    for track_id, info in tracks.items():
        status = info.get("status", "unknown").upper()
        mode = info.get("mode", "sandbox")
        disp = info.get("display_name", track_id)[:26]
        ver = info.get("pinned_version", "latest")[:14]

        # Colors & symbols
        is_green = status in ["READY", "STANDBY", "PASS"]
        status_badge = f"[OK] {status} ({mode})" if is_green else f"[FAIL] {status}"

        print(f"{track_id:<18} | {disp:<28} | {ver:<16} | {status_badge}")
        if not is_green:
            all_green = False

    print("=" * 80)
    print(f"Total Configured Tracks: {health.get('total_tracks')} | Active Adapters: {health.get('loaded_adapters')}")
    if all_green:
        print("\033[92m[ALL RUNNERS GREEN] Ready for isolated course verification.\033[0m")
    else:
        print("\033[91m[WARNING] Some runners reported non-ready status.\033[0m")
    print("=" * 80)

    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(run_health_checks())
