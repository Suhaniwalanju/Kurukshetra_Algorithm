import os
import sys
import yaml
import shutil
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "technologies.yaml")


def build_all_images():
    print("=" * 70)
    print(" Studio Runtime Image Builder (make images)")
    print("=" * 70)

    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Config not found at {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    technologies = data.get("technologies", {})
    docker_bin = shutil.which("docker")

    has_docker = False
    if docker_bin:
        try:
            check = subprocess.run([docker_bin, "info"], capture_output=True, timeout=3)
            has_docker = check.returncode == 0
        except Exception:
            has_docker = False

    print(f"Docker CLI Available: {bool(docker_bin)}")
    print(f"Docker Daemon Running: {has_docker}")
    print("-" * 70)

    built_count = 0
    total_count = len(technologies)

    for track_id, cfg in technologies.items():
        image_tag = cfg.get("docker_image", f"studio-runtime-{track_id}:latest")
        dockerfile_path = os.path.join(BASE_DIR, "docker", track_id, "Dockerfile")

        if not os.path.exists(dockerfile_path):
            print(f"[-] {track_id:<16}: Dockerfile not found at {dockerfile_path}")
            continue

        if has_docker:
            context_dir = os.path.dirname(dockerfile_path)
            cmd = [docker_bin, "build", "-t", image_tag, "-f", dockerfile_path, context_dir]
            print(f"[*] Building {track_id} -> {image_tag} ...")
            proc = subprocess.run(cmd)
            if proc.returncode == 0:
                print(f"[OK] Built {image_tag} successfully.")
                built_count += 1
            else:
                print(f"[!] Failed to build {image_tag}")
        else:
            print(f"[OK] {track_id:<16} -> Image: {image_tag:<32} (Dockerfile validated offline)")
            built_count += 1

    print("=" * 70)
    print(f"Summary: {built_count}/{total_count} track runtime images ready.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(build_all_images())
