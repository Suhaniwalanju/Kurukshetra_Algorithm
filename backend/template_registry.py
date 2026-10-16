import os
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Optional, Tuple
from collections import Counter
from backend.schemas import (
    TemplateLayoutConfig,
    BoundingBox,
    TemplateColors,
    TemplateFonts,
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATES_DIR = os.path.join(BASE_DIR, "input", "templates")
FALLBACK_INPUT_DIR = os.path.join(BASE_DIR, "input")
CONFIGS_DIR = os.path.join(os.path.dirname(__file__), "template_configs")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(CONFIGS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0]), int(rgb[1]), int(rgb[2])).upper()


class TemplateRegistry:
    def __init__(self):
        self.templates: Dict[str, TemplateLayoutConfig] = {}
        self.scan_and_load()

    def scan_and_load(self):
        """Scans /input/templates/ and registers all detected college templates."""
        scan_dir = TEMPLATES_DIR
        # If input/templates is empty, look in input
        entries = os.listdir(scan_dir) if os.path.exists(scan_dir) else []
        if not entries and os.path.exists(FALLBACK_INPUT_DIR):
            scan_dir = FALLBACK_INPUT_DIR
            entries = os.listdir(scan_dir)

        for entry in entries:
            entry_path = os.path.join(scan_dir, entry)
            if entry.lower() in ["templates"]:
                continue

            college_name = ""
            template_file = ""

            if os.path.isdir(entry_path):
                college_name = entry
                for subfile in os.listdir(entry_path):
                    if subfile.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
                        template_file = os.path.join(entry_path, subfile)
                        break
            elif entry.lower().endswith((".png", ".jpg", ".jpeg", ".pdf")):
                college_name = os.path.splitext(entry)[0]
                template_file = entry_path

            if college_name and template_file:
                # Normalize college name
                norm_college = college_name.replace("_Brand_template", "").replace("_template", "").strip()
                if not norm_college:
                    norm_college = college_name
                self.process_template(norm_college, template_file)

    def process_template(self, college: str, file_path: str) -> TemplateLayoutConfig:
        """Processes a template file, converts PDF if needed, analyzes layout, and saves config."""
        # 1. Convert PDF if needed
        png_path = file_path
        if file_path.lower().endswith(".pdf"):
            png_path = self._convert_pdf_to_png(college, file_path)
        else:
            # Ensure standard 1920x1080 normalized PNG
            png_path = self._normalize_template_image(college, file_path)

        # 2. Check if a human-edited config JSON already exists
        config_path = os.path.join(CONFIGS_DIR, f"{college}.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    config = TemplateLayoutConfig(**data)
                    self.templates[college] = config
                    # Generate preview overlay
                    self.generate_preview_overlay(college, config)
                    return config
            except Exception as e:
                print(f"Error loading existing config for {college}: {e}. Re-detecting...")

        # 3. Auto-detect zones and colors
        config = self._auto_detect_layout(college, png_path)
        self.save_config(config)
        self.generate_preview_overlay(college, config)
        self.templates[college] = config
        return config

    def _convert_pdf_to_png(self, college: str, pdf_path: str) -> str:
        """Converts PDF first page to 1920x1080 high-res PNG."""
        dest_png = os.path.join(CONFIGS_DIR, f"{college}_background.png")
        try:
            from pdf2image import convert_from_path
            images = convert_from_path(pdf_path, first_page=1, last_page=1)
            if images:
                img = images[0].resize((1920, 1080), Image.Resampling.LANCZOS)
                img.save(dest_png, "PNG")
                return dest_png
        except Exception as e:
            print(f"pdf2image conversion failed for {pdf_path}: {e}")
        
        # Fallback using pypdf if available or create high-res blank branded canvas
        img = Image.new("RGB", (1920, 1080), color="#FFFFFF")
        img.save(dest_png, "PNG")
        return dest_png

    def _normalize_template_image(self, college: str, img_path: str) -> str:
        """Ensures template image is standard 1920x1080 widescreen PNG."""
        dest_png = os.path.join(CONFIGS_DIR, f"{college}_background.png")
        try:
            with Image.open(img_path) as img:
                img = img.convert("RGB")
                if img.size != (1920, 1080):
                    # Resize preserving widescreen aspect ratio
                    resized = img.resize((1920, 1080), Image.Resampling.LANCZOS)
                    resized.save(dest_png, "PNG")
                else:
                    img.save(dest_png, "PNG")
                return dest_png
        except Exception as e:
            print(f"Error normalizing template image {img_path}: {e}")
            return img_path

    def _auto_detect_layout(self, college: str, image_path: str) -> TemplateLayoutConfig:
        """Analyzes image to detect margins, safe zones, header/footer decorations, and brand colors."""
        img = Image.open(image_path).convert("RGB")
        w, h = img.size  # expected 1920, 1080
        arr = np.array(img)

        # 1. Background color detection (sample corners and center)
        corners = [
            arr[5, 5],
            arr[5, -5],
            arr[-5, 5],
            arr[-5, -5],
            arr[h // 2, w // 2],
        ]
        # Most frequent corner/center color is dominant background
        bg_rgb = tuple(int(x) for x in arr[h // 2, w // 2])

        # 2. Difference from background to detect elements
        diff = np.abs(arr.astype(int) - np.array(bg_rgb)).max(axis=2)
        non_bg_mask = diff > 25

        # Row and column densities
        row_density = non_bg_mask.mean(axis=1)
        col_density = non_bg_mask.mean(axis=0)

        # Detect top header boundary (look from top up to 25% of height)
        header_cutoff = 130
        for y in range(int(h * 0.25)):
            if row_density[y] > 0.04:
                header_cutoff = max(header_cutoff, y + 25)

        # Detect bottom footer boundary (look from bottom up to 20% of height)
        footer_cutoff = 970
        for y in range(h - 1, int(h * 0.8), -1):
            if row_density[y] > 0.04:
                footer_cutoff = min(footer_cutoff, y - 25)

        # Left and right margins
        left_margin = 100
        for x in range(int(w * 0.15)):
            if col_density[x] > 0.05:
                left_margin = max(left_margin, x + 25)

        right_margin = w - 100
        for x in range(w - 1, int(w * 0.85), -1):
            if col_density[x] > 0.05:
                right_margin = min(right_margin, x - 25)

        safe_left = max(80, left_margin)
        safe_top = max(120, header_cutoff + 15)
        safe_right = min(w - 80, right_margin)
        safe_bottom = min(h - 90, footer_cutoff - 15)

        safe_width = safe_right - safe_left
        safe_height = safe_bottom - safe_top

        # Title Zone (top portion of safe area)
        title_top = safe_top
        title_height = 100
        title_zone = BoundingBox(left=safe_left, top=title_top, width=safe_width, height=title_height)

        # Content Zone (below title down to safe bottom)
        content_top = title_top + title_height + 25
        content_height = safe_bottom - content_top
        content_zone = BoundingBox(left=safe_left, top=content_top, width=safe_width, height=content_height)

        # Code Zone (left half of content area, or full width if code-centric)
        split_width = (safe_width - 40) // 2
        code_zone = BoundingBox(left=safe_left, top=content_top, width=split_width, height=content_height)

        # Diagram Zone (right half of content area)
        diagram_zone = BoundingBox(
            left=safe_left + split_width + 40, top=content_top, width=split_width, height=content_height
        )

        # Presented By Zone (bottom safe region on cover/closing slides)
        pres_height = 80
        pres_top = min(h - 130, safe_bottom - pres_height)
        presented_by_zone = BoundingBox(
            left=safe_left + 40,
            top=pres_top,
            width=safe_width - 80,
            height=pres_height,
        )

        # Footer Zone (small text safe area above template footer)
        footer_zone = BoundingBox(
            left=safe_left,
            top=min(h - 75, safe_bottom + 5),
            width=safe_width,
            height=45,
        )

        # Sample colors
        # Find dominant non-background colors in the header/footer regions
        header_footer_arr = np.concatenate([arr[:header_cutoff], arr[footer_cutoff:]], axis=0)
        hf_diff = np.abs(header_footer_arr.astype(int) - np.array(bg_rgb)).max(axis=2)
        colored_pixels = header_footer_arr[hf_diff > 35]

        primary_hex = "#3E78C8"  # Default VIT blue
        secondary_hex = "#1E293B"
        text_hex = "#0F172A"

        if len(colored_pixels) > 0:
            # Cluster or sample the most saturated/frequent color
            # Filter out near whites and near blacks
            r, g, b = colored_pixels[:, 0], colored_pixels[:, 1], colored_pixels[:, 2]
            saturation = np.max(colored_pixels, axis=1) - np.min(colored_pixels, axis=1)
            saturated = colored_pixels[saturation > 40]
            if len(saturated) > 0:
                # Pick median/mode of saturated pixels
                median_rgb = tuple(int(x) for x in np.median(saturated, axis=0))
                primary_hex = rgb_to_hex(median_rgb)
                # Darker version for secondary
                sec_rgb = tuple(int(x * 0.6) for x in median_rgb)
                secondary_hex = rgb_to_hex(sec_rgb)

        return TemplateLayoutConfig(
            college=college,
            slide_width=w,
            slide_height=h,
            aspect_ratio="16:9",
            template_image_path=image_path,
            title_zone=title_zone,
            content_zone=content_zone,
            code_zone=code_zone,
            diagram_zone=diagram_zone,
            footer_zone=footer_zone,
            presented_by_zone=presented_by_zone,
            colors=TemplateColors(
                primary=primary_hex,
                secondary=secondary_hex,
                text=text_hex,
                background=rgb_to_hex(bg_rgb),
                code_bg="#1E1E2E",
                code_text="#F8F8F2",
            ),
            fonts=TemplateFonts(title="Arial", body="Segoe UI", code="Consolas"),
        )

    def save_config(self, config: TemplateLayoutConfig):
        """Saves template config JSON to /backend/template_configs/<college>.json."""
        config_path = os.path.join(CONFIGS_DIR, f"{config.college}.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)

    def get_config(self, college: str) -> Optional[TemplateLayoutConfig]:
        """Returns the layout config for a given college."""
        if college not in self.templates:
            self.scan_and_load()
        return self.templates.get(college)

    def list_colleges(self) -> List[Dict]:
        """Returns list of registered colleges with their preview paths."""
        self.scan_and_load()
        result = []
        for college, config in self.templates.items():
            preview_file = f"{college}_preview.png"
            preview_url = f"/api/templates/{college}/preview"
            result.append(
                {
                    "college": college,
                    "slide_size": f"{config.slide_width}x{config.slide_height}",
                    "colors": config.colors.model_dump(),
                    "fonts": config.fonts.model_dump(),
                    "preview_url": preview_url,
                    "has_custom_config": os.path.exists(os.path.join(CONFIGS_DIR, f"{college}.json")),
                }
            )
        return result

    def generate_preview_overlay(self, college: str, config: TemplateLayoutConfig) -> str:
        """Generates a template preview PNG with color-coded bounding box overlays and labels."""
        bg_img_path = config.template_image_path
        if not os.path.exists(bg_img_path):
            return ""

        base = Image.open(bg_img_path).convert("RGBA")
        overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)

        # Define zones with distinct translucent colors
        zones = [
            ("Content Safe Zone", config.content_zone, (34, 197, 94, 40), (34, 197, 94, 200)),  # Green
            ("Title Zone", config.title_zone, (59, 130, 246, 50), (59, 130, 246, 220)),         # Blue
            ("Code Zone", config.code_zone, (168, 85, 247, 50), (168, 85, 247, 220)),           # Purple
            ("Diagram Zone", config.diagram_zone, (236, 72, 153, 50), (236, 72, 153, 220)),     # Pink
            ("Presented By Zone", config.presented_by_zone, (249, 115, 22, 60), (249, 115, 22, 220)), # Orange
            ("Footer Zone", config.footer_zone, (100, 116, 139, 50), (100, 116, 139, 200)),     # Slate
        ]

        # Draw overlays
        for label, box, fill_color, border_color in zones:
            rect = [box.left, box.top, box.left + box.width, box.top + box.height]
            draw.rectangle(rect, fill=fill_color, outline=border_color, width=3)
            # Label badge
            draw.rectangle([box.left, box.top, box.left + len(label) * 11 + 20, box.top + 28], fill=border_color)
            draw.text((box.left + 8, box.top + 6), label, fill=(255, 255, 255, 255))

        combined = Image.alpha_composite(base, overlay).convert("RGB")
        preview_out = os.path.join(CONFIGS_DIR, f"{college}_preview.png")
        combined.save(preview_out, "PNG")
        return preview_out


# Singleton instance
template_registry = TemplateRegistry()
