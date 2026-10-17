import os
import shutil
import subprocess
from typing import List, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

from backend.schemas import Slide, TemplateLayoutConfig
from backend.layout_engine import SlideLayoutPlan, ElementBox, get_font, MIN_GUTTER_PX, layout_engine
from backend.diagram_renderer import diagram_renderer
from backend.utils import sanitize_filename

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
                font = get_font(config.fonts.title, plan.font_sizes.get("title", 38))
                color = hex_to_rgb_tuple(config.colors.secondary)
                draw.text((box.left, box.top + 2), slide.title, fill=color, font=font)
                # Subtle accent indicator under title
                bbox = draw.textbbox((box.left, box.top + 2), slide.title, font=font)
                accent_color = hex_to_rgb_tuple(config.colors.primary)
                draw.rectangle([box.left, bbox[3] + 8, box.left + 64, bbox[3] + 12], fill=accent_color)

            elif box.element_type == "presented_by":
                # Cover slide elegant presenter badge
                primary_rgb = hex_to_rgb_tuple(config.colors.primary)
                sec_rgb = hex_to_rgb_tuple(config.colors.secondary)
                draw.rounded_rectangle(
                    [box.left, box.top, box.right, box.bottom], radius=16, fill=(255, 255, 255, 240), outline=primary_rgb, width=2
                )
                font = get_font(config.fonts.body, plan.font_sizes.get("presented_by", 26))
                text = f"Presented By {professor_name}"
                bbox = draw.textbbox((0, 0), text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = box.left + (box.width - tw) // 2
                ty = box.top + (box.height - th) // 2
                draw.text((tx, ty), text, fill=sec_rgb, font=font)

            elif box.element_type == "footer":
                font = get_font(config.fonts.body, 13)
                # Left footer: College & Slide info
                text_left = f"{config.college}   •   {slide.title}   •   Slide {slide.id}"
                draw.text((box.left, box.top + 6), text_left, fill=(100, 116, 139), font=font)

                # Center footer: Prepared by {professor_name} (matching brand template)
                if professor_name:
                    center_font = get_font(config.fonts.body, 14)
                    center_text = f"Prepared by: {professor_name}"
                    c_bbox = draw.textbbox((0, 0), center_text, font=center_font)
                    c_w = c_bbox[2] - c_bbox[0]
                    c_x = (1920 - c_w) // 2
                    draw.text((c_x, box.top + 5), center_text, fill=(71, 85, 105), font=center_font)

                # Right footer: Verified or Unverified Badge (None if no code)
                if slide.verification_badge:
                    badge_font = get_font(config.fonts.code, 11)
                    raw_badge = slide.verification_badge.strip()
                    is_unverified = "unverified" in raw_badge.lower()

                    if is_unverified:
                        badge_label = f"⚠ {raw_badge}" if "⚠" not in raw_badge else raw_badge
                        pill_fill = (254, 242, 242)
                        pill_outline = (239, 68, 68)
                        pill_text_color = (185, 28, 28)
                    else:
                        badge_label = raw_badge if ("✔" in raw_badge or "✓" in raw_badge) else f"✓ {raw_badge}"
                        pill_fill = (240, 253, 244)
                        pill_outline = (34, 197, 94)
                        pill_text_color = (22, 101, 52)

                    bbox = draw.textbbox((0, 0), badge_label, font=badge_font)
                    bw = bbox[2] - bbox[0] + 20
                    bh = bbox[3] - bbox[1] + 10
                    bx = box.right - bw - 10
                    by = box.top + 2
                    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=6, fill=pill_fill, outline=pill_outline, width=1)
                    draw.text((bx + 10, by + 4), badge_label, fill=pill_text_color, font=badge_font)

            elif box.element_type == "bullets":
                # Subtle modern card for bullets
                draw.rounded_rectangle(
                    [box.left, box.top, box.right, box.bottom],
                    radius=16,
                    fill=(248, 250, 252, 235),
                    outline=(226, 232, 240),
                    width=1,
                )
                font_size = plan.font_sizes.get("body", 26)
                font = get_font(config.fonts.body, font_size)
                text_color = hex_to_rgb_tuple(config.colors.text)
                bullet_color = hex_to_rgb_tuple(config.colors.primary)
                cur_y = box.top + 22
                line_h = int(font_size * 1.4)
                max_w = box.width - 56

                for b in slide.bullets:
                    # Word wrap bullet lines
                    wrapped_lines = layout_engine.wrap_text(b, font, max_w)
                    # Draw bullet indicator circle
                    dot_y = cur_y + (line_h // 2)
                    draw.ellipse([box.left + 22, dot_y - 4, box.left + 30, dot_y + 4], fill=bullet_color)

                    for line_idx, w_line in enumerate(wrapped_lines):
                        draw.text((box.left + 42, cur_y), w_line, fill=text_color, font=font)
                        cur_y += line_h

                    cur_y += 12  # Spacing between bullets

                if slide.exercise_ref:
                    ex_font = get_font(config.fonts.body, font_size - 4)
                    draw.text(
                        (box.left + 42, cur_y + 6),
                        f"Ref: {slide.exercise_ref}",
                        fill=bullet_color,
                        font=ex_font,
                    )

            elif box.element_type == "code":
                code_data = slide.code
                if not code_data:
                    continue

                # Dark modern IDE terminal card
                code_bg = hex_to_rgb_tuple(config.colors.code_bg)
                draw.rounded_rectangle(
                    [box.left, box.top, box.right, box.bottom],
                    radius=16,
                    fill=code_bg,
                    outline=(30, 41, 59),
                    width=1,
                )

                # Terminal Window Controls (Red, Yellow, Green dots)
                dot_y = box.top + 18
                draw.ellipse([box.left + 20, dot_y - 5, box.left + 30, dot_y + 5], fill=(239, 68, 68))
                draw.ellipse([box.left + 38, dot_y - 5, box.left + 48, dot_y + 5], fill=(245, 158, 11))
                draw.ellipse([box.left + 56, dot_y - 5, box.left + 66, dot_y + 5], fill=(16, 185, 129))

                # Language Badge Pill at top-right
                tag_font = get_font(config.fonts.code, 12)
                tag_text = f"{code_data.language.upper()} {code_data.version or ''}".strip()
                t_bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
                tw = t_bbox[2] - t_bbox[0] + 16
                th = t_bbox[3] - t_bbox[1] + 8
                tx = box.right - tw - 18
                ty = box.top + 10
                draw.rounded_rectangle([tx, ty, tx + tw, ty + th], radius=6, fill=(30, 41, 59), outline=(51, 65, 85), width=1)
                draw.text((tx + 8, ty + 3), tag_text, fill=(96, 165, 250), font=tag_font)

                # Imports omitted badge if fragment was wrapped
                if getattr(slide, "imports_omitted", False):
                    note_font = get_font(config.fonts.code, 11)
                    note_text = "* imports omitted"
                    n_bbox = draw.textbbox((0, 0), note_text, font=note_font)
                    nw = n_bbox[2] - n_bbox[0] + 16
                    nh = n_bbox[3] - n_bbox[1] + 8
                    nx = tx - nw - 10
                    ny = box.top + 10
                    draw.rounded_rectangle([nx, ny, nx + nw, ny + nh], radius=6, fill=(88, 28, 135, 200), outline=(168, 85, 247), width=1)
                    draw.text((nx + 8, ny + 3), note_text, fill=(216, 180, 254), font=note_font)

                # Header Divider
                draw.line([box.left, box.top + 36, box.right, box.top + 36], fill=(30, 41, 59), width=1)

                # Code lines with Pygments syntax highlighting
                code_font_size = plan.font_sizes.get("code", 17)
                code_font = get_font(config.fonts.code, code_font_size)
                try:
                    lexer = get_lexer_by_name(code_data.language.lower(), stripall=True)
                except Exception:
                    lexer = TextLexer(stripall=True)

                cur_y = box.top + 46
                code_lines = code_data.source.split("\n")
                code_line_h = int(code_font_size * 1.35)

                for line in code_lines:
                    cur_x = box.left + 24
                    tokens = list(lex(line, lexer))
                    for t_type, t_val in tokens:
                        if not t_val or t_val == "\n":
                            continue
                        color_hex = DEFAULT_CODE_HEX
                        for k, c in TOKEN_HEX_MAP.items():
                            if t_type in k:
                                color_hex = c
                                break
                        draw.text((cur_x, cur_y), t_val, fill=hex_to_rgb_tuple(color_hex), font=code_font)
                        bbox = draw.textbbox((cur_x, cur_y), t_val, font=code_font)
                        cur_x = bbox[2]
                    cur_y += code_line_h

                # Expected Output Footer Bar
                if code_data.expected_output:
                    out_bar_top = max(cur_y + 10, box.bottom - 46)
                    draw.rectangle([box.left + 1, out_bar_top, box.right - 1, box.bottom - 1], fill=(10, 15, 26))
                    draw.line([box.left, out_bar_top, box.right, out_bar_top], fill=(30, 41, 59), width=1)
                    prompt_font = get_font(config.fonts.code, 13)
                    draw.text((box.left + 20, out_bar_top + 12), "> Output:", fill=(52, 211, 153), font=prompt_font)
                    p_bbox = draw.textbbox((box.left + 20, out_bar_top + 12), "> Output: ", font=prompt_font)
                    draw.text((p_bbox[2], out_bar_top + 12), code_data.expected_output, fill=(241, 245, 249), font=prompt_font)

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


def render_deck_previews(deck_dict: dict) -> List[str]:
    """
    Renders high-res previews for all slides in the deck dictionary.
    Returns list of preview URLs (/static/output/{deck_id}/previews/slide_{id}.png).
    """
    from backend.template_registry import template_registry
    from backend.layout_engine import layout_engine
    from backend.schemas import Slide, SlideCode, SlideDiagram

    deck_id = deck_dict.get("id", "temp_deck")
    college = deck_dict.get("college", "VIT")
    prof_name = deck_dict.get("professor_name", "Professor")
    topic = deck_dict.get("topic", "Presentation")
    tech = deck_dict.get("tech", "Code")

    config = template_registry.get_config(college)
    if not config and template_registry.templates:
        config = list(template_registry.templates.values())[0]

    output_dir = os.path.join(os.path.abspath("output"), deck_id)
    previews_dir = os.path.join(output_dir, "previews")
    os.makedirs(previews_dir, exist_ok=True)
    clean_topic = sanitize_filename(topic)
    clean_tech = sanitize_filename(tech)
    pptx_path = os.path.join(output_dir, f"{clean_topic}_{clean_tech}.pptx")

    slides_data = deck_dict.get("slides", [])
    parsed_slides = []
    for s in slides_data:
        s_copy = dict(s)
        code_raw = s_copy.get("code")
        if isinstance(code_raw, str):
            s_copy["code"] = SlideCode(source=code_raw)
        elif isinstance(code_raw, dict):
            s_copy["code"] = SlideCode(**code_raw)

        diag_raw = s_copy.get("diagram")
        if isinstance(diag_raw, str):
            s_copy["diagram"] = SlideDiagram(source=diag_raw)
        elif isinstance(diag_raw, dict):
            s_copy["diagram"] = SlideDiagram(**diag_raw)
        if "type" not in s_copy:
            s_copy["type"] = "concept"
        parsed_slides.append(Slide(**s_copy))

    plans = []
    if config:
        for idx, slide in enumerate(parsed_slides):
            plan = layout_engine.plan_slide(slide, config, is_first_slide=(idx == 0))
            plans.append(plan)

    img_paths = slide_renderer.render_deck_previews(
        pptx_path, parsed_slides, plans, config, prof_name, previews_dir
    )
    return [f"/static/output/{deck_id}/previews/{os.path.basename(p)}" for p in img_paths]


def render_slide_preview(deck_dict: dict, slide_index: int) -> str:
    """
    Renders high-res preview for a single slide in the deck dictionary.
    Returns preview URL (/static/output/{deck_id}/previews/slide_{id}.png).
    """
    from backend.template_registry import template_registry
    from backend.layout_engine import layout_engine
    from backend.schemas import Slide, SlideCode, SlideDiagram

    deck_id = deck_dict.get("id", "temp_deck")
    college = deck_dict.get("college", "VIT")
    prof_name = deck_dict.get("professor_name", "Professor")

    config = template_registry.get_config(college)
    if not config and template_registry.templates:
        config = list(template_registry.templates.values())[0]

    output_dir = os.path.join(os.path.abspath("output"), deck_id)
    previews_dir = os.path.join(output_dir, "previews")
    os.makedirs(previews_dir, exist_ok=True)

    slides_data = deck_dict.get("slides", [])
    if not (0 <= slide_index < len(slides_data)):
        return ""

    s_raw = slides_data[slide_index]
    s_copy = dict(s_raw)
    code_raw = s_copy.get("code")
    if isinstance(code_raw, str):
        s_copy["code"] = SlideCode(source=code_raw)
    elif isinstance(code_raw, dict):
        s_copy["code"] = SlideCode(**code_raw)

    diag_raw = s_copy.get("diagram")
    if isinstance(diag_raw, str):
        s_copy["diagram"] = SlideDiagram(source=diag_raw)
    elif isinstance(diag_raw, dict):
        s_copy["diagram"] = SlideDiagram(**diag_raw)
    slide = Slide(**s_copy)

    plan = layout_engine.plan_slide(slide, config, is_first_slide=(slide_index == 0)) if config else None
    img_path = os.path.join(previews_dir, f"slide_{slide.id}.png")

    if config and plan:
        slide_renderer._render_single_slide_pil(slide, plan, config, prof_name, img_path)

    return f"/static/output/{deck_id}/previews/slide_{slide.id}.png"
