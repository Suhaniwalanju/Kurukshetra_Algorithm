import os
import shutil
import subprocess
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

from backend.schemas import Slide, TemplateLayoutConfig
from backend.layout_engine import SlideLayoutPlan, ElementBox, get_font, MIN_GUTTER_PX
from backend.diagram_renderer import diagram_renderer

# Pygments hex mapping for PIL renderer
TOKEN_HEX_MAP = {
    Token.Keyword: "#C678DD",
    Token.Keyword.Constant: "#E5C07B",
    Token.Name.Class: "#E5C07B",
    Token.Name.Function: "#61AFEF",
    Token.Name.Builtin: "#E5C07B",
    Token.String: "#98C379",
    Token.Number: "#D19A66",
    Token.Comment: "#788291",
    Token.Operator: "#56B6C2",
    Token.Punctuation: "#ABB2BF",
}
DEFAULT_CODE_HEX = "#F0F4FA"


def hex_to_rgb_tuple(hex_str: str) -> Tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class SlideRenderer:
    def __init__(self):
        self.soffice_path = shutil.which("soffice") or shutil.which("libreoffice")
        if not self.soffice_path:
            for cand in [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ]:
                if os.path.exists(cand):
                    self.soffice_path = cand
                    break

    def render_deck_previews(
        self,
        pptx_path: str,
        slides: List[Slide],
        plans: List[SlideLayoutPlan],
        config: TemplateLayoutConfig,
        professor_name: str,
        output_dir: str,
    ) -> List[str]:
        """
        Renders each slide to a high-res 1920x1080 PNG image.
        Uses LibreOffice + pdf2image if available, with a pixel-accurate PIL fallback.
        """
        os.makedirs(output_dir, exist_ok=True)
        preview_paths = []

        # 1. Attempt LibreOffice headless if available
        if self.soffice_path:
            try:
                lo_images = self._render_via_libreoffice(pptx_path, output_dir)
                if lo_images and len(lo_images) == len(slides):
                    return lo_images
            except Exception as e:
                print(f"LibreOffice rendering attempt failed ({e}). Using native high-res visualizer.")

        # 2. High-Fidelity PIL Slide Renderer
        for slide, plan in zip(slides, plans):
            img_path = os.path.join(output_dir, f"slide_{slide.id}.png")
            self._render_single_slide_pil(slide, plan, config, professor_name, img_path)
            preview_paths.append(img_path)

        return preview_paths

    def _render_via_libreoffice(self, pptx_path: str, output_dir: str) -> List[str]:
        """Converts PPTX to PDF via LibreOffice headless, then converts PDF pages to PNG."""
        pdf_out_dir = os.path.join(output_dir, "temp_pdf")
        os.makedirs(pdf_out_dir, exist_ok=True)

        res = subprocess.run(
            [self.soffice_path, "--headless", "--convert-to", "pdf", "--outdir", pdf_out_dir, pptx_path],
            capture_output=True,
            timeout=60,
        )
        if res.returncode != 0:
            return []

        base_name = os.path.splitext(os.path.basename(pptx_path))[0]
        pdf_path = os.path.join(pdf_out_dir, f"{base_name}.pdf")
        if not os.path.exists(pdf_path):
            return []

        from pdf2image import convert_from_path

        pages = convert_from_path(pdf_path, dpi=144)
        result_paths = []
        for idx, page in enumerate(pages):
            out_img = os.path.join(output_dir, f"slide_{idx + 1}.png")
            page.resize((1920, 1080), Image.Resampling.LANCZOS).save(out_img, "PNG")
            result_paths.append(out_img)

        # Cleanup temp pdf
        try:
            shutil.rmtree(pdf_out_dir)
        except Exception:
            pass

        return result_paths

    def _render_single_slide_pil(
        self,
        slide: Slide,
        plan: SlideLayoutPlan,
        config: TemplateLayoutConfig,
        professor_name: str,
        output_png_path: str,
    ):
        """Renders an individual slide at 1920x1080 onto template background using PIL."""
        # 1. Base template background
        if os.path.exists(config.template_image_path):
            img = Image.open(config.template_image_path).convert("RGBA").resize((1920, 1080), Image.Resampling.LANCZOS)
        else:
            img = Image.new("RGBA", (1920, 1080), (255, 255, 255, 255))

        draw = ImageDraw.Draw(img)

        # 2. Render elements based on plan
        for box in plan.elements:
            if box.element_type == "title":
                font = get_font(config.fonts.title, plan.font_sizes.get("title", 40))
                color = hex_to_rgb_tuple(config.colors.secondary)
                draw.text((box.left, box.top + 5), slide.title, fill=color, font=font)

            elif box.element_type == "presented_by":
                # Presented By pill
                fill = hex_to_rgb_tuple(config.colors.primary)
                border = hex_to_rgb_tuple(config.colors.secondary)
                draw.rounded_rectangle(
                    [box.left, box.top, box.right, box.bottom], radius=16, fill=fill, outline=border, width=3
                )
                font = get_font(config.fonts.body, plan.font_sizes.get("presented_by", 28))
                text = f"Presented By {professor_name}"
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = box.left + (box.width - tw) // 2
                ty = box.top + (box.height - th) // 2
                draw.text((tx, ty), text, fill=(255, 255, 255), font=font)

            elif box.element_type == "footer":
                font = get_font(config.fonts.body, 14)
                text = f"{config.college}   •   {slide.title}   •   Slide {slide.id}"
                draw.text((box.left, box.top), text, fill=(100, 116, 139), font=font)

                if slide.verification_badge:
                    badge_font = get_font(config.fonts.code, 12)
                    badge_text = slide.verification_badge
                    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
                    bw = bbox[2] - bbox[0] + 20
                    bh = bbox[3] - bbox[1] + 10
                    bx = box.right - bw - 10
                    by = box.top - 2
                    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=6, fill=(240, 253, 244), outline=(34, 197, 94), width=1)
                    draw.text((bx + 10, by + 4), badge_text, fill=(22, 101, 52), font=badge_font)

            elif box.element_type == "bullets":
                # Bullet list card
                draw.rounded_rectangle(
                    [box.left, box.top, box.right, box.bottom],
                    radius=14,
                    fill=(255, 255, 255, 230),
                    outline=hex_to_rgb_tuple(config.colors.primary),
                    width=2,
                )
                font = get_font(config.fonts.body, plan.font_sizes.get("body", 28))
                text_color = hex_to_rgb_tuple(config.colors.text)
                cur_y = box.top + 20

                for b in slide.bullets:
                    bullet_text = f"•  {b}"
                    draw.text((box.left + 24, cur_y), bullet_text, fill=text_color, font=font)
                    cur_y += int(plan.font_sizes.get("body", 28) * 1.45)

                if slide.exercise_ref:
                    ex_font = get_font(config.fonts.body, plan.font_sizes.get("body", 28) - 4)
                    draw.text(
                        (box.left + 24, cur_y + 10),
                        f"Ref: {slide.exercise_ref}",
                        fill=hex_to_rgb_tuple(config.colors.primary),
                        font=ex_font,
                    )

            elif box.element_type == "code":
                code_data = slide.code
                if not code_data:
                    continue

                # Dark code card
                code_bg = hex_to_rgb_tuple(config.colors.code_bg)
                code_border = hex_to_rgb_tuple(config.colors.primary)
                draw.rounded_rectangle(
                    [box.left, box.top, box.right, box.bottom],
                    radius=14,
                    fill=code_bg,
                    outline=code_border,
                    width=2,
                )

                # Header tag
                tag_font = get_font(config.fonts.code, 14)
                tag_text = f"// Language: {code_data.language.upper()} {code_data.version or ''}".strip()
                draw.text((box.left + 16, box.top + 12), tag_text, fill=(148, 163, 184), font=tag_font)

                # Code lines with Pygments syntax highlighting
                code_font = get_font(config.fonts.code, plan.font_sizes.get("code", 18))
                try:
                    lexer = get_lexer_by_name(code_data.language.lower(), stripall=True)
                except Exception:
                    lexer = TextLexer(stripall=True)

                cur_y = box.top + 38
                for line in code_data.source.split("\n"):
                    cur_x = box.left + 20
                    tokens = list(lex(line, lexer))
                    for t_type, t_val in tokens:
                        if not t_val or t_val == "\n":
                            continue
                        # Determine color
                        color_hex = DEFAULT_CODE_HEX
                        for k, c in TOKEN_HEX_MAP.items():
                            if t_type in k:
                                color_hex = c
                                break
                        draw.text((cur_x, cur_y), t_val, fill=hex_to_rgb_tuple(color_hex), font=code_font)
                        bbox = draw.textbbox((cur_x, cur_y), t_val, font=code_font)
                        cur_x = bbox[2]
                    cur_y += int(plan.font_sizes.get("code", 18) * 1.35)

                # Expected Output section
                if code_data.expected_output:
                    out_y = max(cur_y + 10, box.bottom - 45)
                    draw.text(
                        (box.left + 20, out_y),
                        "Expected Output: ",
                        fill=(74, 222, 128),
                        font=get_font(config.fonts.code, 15),
                    )
                    bbox = draw.textbbox((box.left + 20, out_y), "Expected Output: ", font=get_font(config.fonts.code, 15))
                    draw.text(
                        (bbox[2], out_y),
                        code_data.expected_output,
                        fill=(241, 245, 249),
                        font=get_font(config.fonts.code, 15),
                    )

            elif box.element_type == "diagram":
                diag_data = slide.diagram
                if diag_data and diag_data.source:
                    temp_diag = output_png_path.replace(".png", "_diag.png")
                    if diagram_renderer.render_mermaid(diag_data.source, temp_diag, width=box.width, height=box.height):
                        if os.path.exists(temp_diag):
                            diag_img = Image.open(temp_diag).convert("RGBA")
                            img.paste(diag_img, (box.left, box.top), diag_img)

        img.convert("RGB").save(output_png_path, "PNG")

    def run_automated_check(self, slides: List[Slide], plans: List[SlideLayoutPlan]) -> Tuple[bool, List[str]]:
        """
        Runs comprehensive post-layout automated check:
        1. Elements out of safe zone
        2. Overlapping boxes (collision gutter >= 0.2 inch)
        3. Text clipped or overflowing
        4. No bullet exceeds 8 words
        5. No slide exceeds 5 bullets
        """
        issues = []

        for slide, plan in zip(slides, plans):
            # 1. Check bullets constraint
            if len(slide.bullets) > 5:
                issues.append(f"Slide {slide.id}: Exceeds max 5 bullets ({len(slide.bullets)} bullets)")

            for idx, b in enumerate(slide.bullets):
                words = b.strip().split()
                if len(words) > 8:
                    issues.append(
                        f"Slide {slide.id}, Bullet {idx + 1}: Exceeds 8 words ({len(words)} words: '{b}')"
                    )

            # 2. Check layout plan violations (collisions, safe-zone overflow)
            for v in plan.violations:
                issues.append(f"Slide {slide.id}: {v}")

        passed = len(issues) == 0
        return passed, issues


slide_renderer = SlideRenderer()
