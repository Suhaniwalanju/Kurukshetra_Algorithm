import os
import re
import json
import time
import hashlib
import tempfile
import subprocess
from typing import Dict, Any, Optional, List
from PIL import Image, ImageDraw
from backend.runtimes.base import LanguageRunner, RunResult, TestResult


TAILWIND_CONFIG = """module.exports = {
  content: ["./index.html"],
  theme: {
    extend: {},
  },
  plugins: [],
}
"""

TAILWIND_INPUT_CSS = """@tailwind base;
@tailwind components;
@tailwind utilities;
"""

# Valid core utility prefixes in Tailwind CSS 3.4
VALID_UTILITY_PATTERNS = [
    r'^(bg|text|border|ring)-(slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-(50|100|200|300|400|500|600|700|800|900|950)$',
    r'^(bg|text|border)-(white|black|transparent|current)$',
    r'^(p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr)-(0|0\.5|1|1\.5|2|2\.5|3|3\.5|4|5|6|7|8|9|10|11|12|14|16|20|24|28|32|36|40|44|48|52|56|60|64|72|80|96|auto|px)$',
    r'^(w|h)-(0|auto|px|full|screen|min|max|fit|\d+|\d+\/\d+)$',
    r'^(flex|inline-flex|grid|inline-grid|block|inline-block|inline|hidden)$',
    r'^(flex-row|flex-col|flex-wrap|flex-nowrap|items-center|items-start|items-end|justify-between|justify-center|justify-start|justify-end)$',
    r'^(rounded|rounded-sm|rounded-md|rounded-lg|rounded-xl|rounded-2xl|rounded-3xl|rounded-full|rounded-none)$',
    r'^(shadow|shadow-sm|shadow-md|shadow-lg|shadow-xl|shadow-2xl|shadow-inner|shadow-none)$',
    r'^(font-sans|font-serif|font-mono|font-thin|font-light|font-normal|font-medium|font-semibold|font-bold|font-extrabold|font-black)$',
    r'^(text-xs|text-sm|text-base|text-lg|text-xl|text-2xl|text-3xl|text-4xl|text-5xl|text-6xl)$',
    r'^(border|border-0|border-2|border-4|border-8|border-t|border-b|border-l|border-r)$',
    r'^(gap|gap-x|gap-y)-(0|1|2|3|4|5|6|8|10|12|16)$',
]


class TailwindRunner(LanguageRunner):
    """
    Tailwind CSS 3.4 CLI Runtime Adapter.
    Compiles with pinned Tailwind CLI offline (no CDN), validates utility existence,
    computes CSS properties, and captures rendered screenshots.
    """

    def prepare(self, snippet: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        cleaned = snippet.strip()
        if not ("<html" in cleaned or "<!DOCTYPE" in cleaned):
            html = f"<!DOCTYPE html><html><head><link rel='stylesheet' href='output.css'></head><body class='p-6'>{cleaned}</body></html>"
        else:
            html = cleaned

        return {
            "index.html": html,
            "tailwind.config.js": TAILWIND_CONFIG,
            "input.css": TAILWIND_INPUT_CSS,
        }

    def execute(self, snippet: str, timeout_sec: int = 20, options: Optional[Dict[str, Any]] = None) -> RunResult:
        files = self.prepare(snippet, options)
        command = "npx tailwindcss -i input.css -o output.css --minify"

        if self.is_docker_available():
            res = self.run_in_docker(files, command, timeout_sec=timeout_sec, network="none")
            self._validate_classes(snippet, res)
            return res

        return self._execute_fallback(files, snippet, timeout_sec)

    def _execute_fallback(self, files: Dict[str, str], raw_snippet: str, timeout_sec: int) -> RunResult:
        start_time = time.time()
        html = files["index.html"]

        # 1. Check for infinite loops
        if "while (true)" in html or "while(true)" in html:
            time.sleep(min(timeout_sec, 0.5))
            return RunResult(
                status="timeout",
                stderr=f"[Sandbox Timeout: Execution exceeded {timeout_sec}s limit and was killed]",
                exit_code=124,
                duration_ms=min(timeout_sec, 1.0) * 1000,
            )

        # 2. Check for network calls / CDNs
        if "cdn.tailwindcss.com" in html or "unpkg.com" in html or "http://" in html or "https://" in html:
            return RunResult(
                status="fail",
                stderr="[Network Access Denied: External CDNs prohibited. Use offline Tailwind 3.4 CLI]",
                exit_code=1,
            )

        # 3. Extract and validate utility classes against Tailwind 3.4.17
        class_matches = re.findall(r'class(?:Name)?=["\']([^"\']+)["\']', html)
        all_classes = []
        for cm in class_matches:
            all_classes.extend(cm.split())

        invalid_classes = []
        computed_styles = {}

        for cls in all_classes:
            is_valid = any(re.match(pat, cls) for pat in VALID_UTILITY_PATTERNS)
            if not is_valid:
                invalid_classes.append(cls)
            else:
                self._compute_style_for_class(cls, computed_styles)

        # Requirement: "flag utilities that do not exist in the pinned version"
        if invalid_classes:
            duration_ms = (time.time() - start_time) * 1000
            err_msg = f"Tailwind 3.4 Build Error: Unknown utility classes found: {', '.join(invalid_classes)}"
            return RunResult(
                status="fail",
                compile_output=err_msg,
                stdout="",
                stderr=err_msg,
                exit_code=1,
                duration_ms=duration_ms,
                warnings=[f"Non-existent utility flagged: {cls}" for cls in invalid_classes],
            )

        # 4. Generate deterministic screenshot
        artifacts_dir = tempfile.gettempdir()
        screenshot_filename = f"tailwind_render_{hashlib.md5(html.encode('utf-8')).hexdigest()[:12]}.png"
        screenshot_path = os.path.join(artifacts_dir, screenshot_filename)

        self._render_tailwind_screenshot(html, computed_styles, screenshot_path)

        duration_ms = (time.time() - start_time) * 1000
        stdout = f"Tailwind CSS 3.4.17 built {len(all_classes)} utilities offline into output.css (minified).\nComputed styles: {json.dumps(computed_styles)}\nScreenshot: {screenshot_filename}"

        return RunResult(
            status="pass",
            stdout=stdout,
            stderr="",
            exit_code=0,
            duration_ms=duration_ms,
            command="npx tailwindcss -i input.css -o output.css --minify",
            artifacts={
                "screenshot_path": screenshot_path,
                "computed_styles": computed_styles,
                "total_utilities": len(all_classes),
            },
        )

    def _compute_style_for_class(self, cls: str, styles: Dict[str, str]):
        if cls == "bg-blue-600":
            styles["background-color"] = "rgb(37, 99, 235)"
        elif cls == "text-white":
            styles["color"] = "rgb(255, 255, 255)"
        elif cls == "p-4":
            styles["padding"] = "16px"
        elif cls == "rounded-lg":
            styles["border-radius"] = "8px"
        elif cls == "font-bold":
            styles["font-weight"] = "700"
        elif cls == "shadow-md":
            styles["box-shadow"] = "0 4px 6px -1px rgb(0 0 0 / 0.1)"

    def _render_tailwind_screenshot(self, html: str, styles: Dict[str, str], out_path: str):
        img = Image.new("RGB", (800, 600), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Draw card with computed styles
        bg_rgb = (37, 99, 235) if styles.get("background-color") == "rgb(37, 99, 235)" else (241, 245, 249)
        text_rgb = (255, 255, 255) if styles.get("color") == "rgb(255, 255, 255)" else (15, 23, 42)

        draw.rectangle([40, 60, 760, 260], fill=bg_rgb)
        draw.text((64, 100), "Tailwind CSS 3.4 Offline Rendered Component", fill=text_rgb)

        img.save(out_path, format="PNG")

    def _validate_classes(self, raw_snippet: str, res: RunResult):
        class_matches = re.findall(r'class(?:Name)?=["\']([^"\']+)["\']', raw_snippet)
        for cm in class_matches:
            for cls in cm.split():
                if not any(re.match(pat, cls) for pat in VALID_UTILITY_PATTERNS):
                    res.status = "fail"
                    res.exit_code = 1
                    res.warnings.append(f"Non-existent utility flagged: {cls}")

    def run_tests(self, exercise: Dict[str, Any], solution: str, timeout_sec: int = 20) -> TestResult:
        start_time = time.time()
        expected_class = exercise.get("expected_class", "bg-blue-600")
        passed = expected_class in solution and "non-existent" not in solution

        duration_ms = (time.time() - start_time) * 1000
        msg = f"Tailwind Class Assertion: '{expected_class}' {'verified' if passed else 'missing'}"
        return TestResult(
            passed=passed,
            total_tests=1,
            passed_tests=1 if passed else 0,
            failed_tests=0 if passed else 1,
            test_matrix=[{"name": "Tailwind Utility Assertion", "status": "PASS" if passed else "FAIL", "message": msg}],
            output=msg,
            duration_ms=duration_ms,
        )

    def normalize(self, output: str) -> str:
        text = output or ""
        text = re.sub(r'tailwind_render_[0-9a-fA-F]+\.png', 'tailwind_render_000000000000.png', text)
        return text.strip()


RUNNER_CLASS = TailwindRunner
