import os
import shutil
from typing import List, Dict, Any, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

from backend.schemas import Slide, TemplateLayoutConfig
from backend.layout_engine import ElementBox, SlideLayoutPlan
from backend.diagram_renderer import diagram_renderer

# 1920x1080 maps to 13.333 x 7.5 inches
SLIDE_W_INCHES = 13.333333
SLIDE_H_INCHES = 7.5


def px_to_inches(px: int, total_px: int, total_inches: float) -> Inches:
    return Inches(px * (total_inches / total_px))


def hex_to_rgb(hex_str: str) -> RGBColor:
    hex_clean = hex_str.lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    return RGBColor(r, g, b)


# Vibrant One Dark / Monokai syntax highlighting map
TOKEN_COLOR_MAP = {
    Token.Keyword: RGBColor(198, 120, 221),       # Purple / Magenta
    Token.Keyword.Constant: RGBColor(229, 192, 123),# Amber
    Token.Name.Class: RGBColor(229, 192, 123),    # Gold / Yellow
    Token.Name.Function: RGBColor(97, 175, 239),  # Light Blue
    Token.Name.Builtin: RGBColor(229, 192, 123),  # Gold
    Token.String: RGBColor(152, 195, 121),        # Soft Green
    Token.Number: RGBColor(209, 154, 102),        # Orange
    Token.Comment: RGBColor(120, 130, 145),       # Slate Muted Gray
    Token.Operator: RGBColor(86, 182, 194),       # Cyan
    Token.Punctuation: RGBColor(171, 178, 191),   # Light Gray
}
DEFAULT_CODE_COLOR = RGBColor(240, 244, 250)


class PPTXBuilder:
    def __init__(self):
        pass

    def build_deck(
        self,
        slides: List[Slide],
        plans: List[SlideLayoutPlan],
        config: TemplateLayoutConfig,
        professor_name: str,
        output_pptx_path: str,
    ) -> str:
        """
        Builds a PowerPoint presentation adhering strictly to layout config,
        safe zones, syntax highlighting, and template background.
        """
        os.makedirs(os.path.dirname(output_pptx_path), exist_ok=True)

        prs = Presentation()
        prs.slide_width = Inches(SLIDE_W_INCHES)
        prs.slide_height = Inches(SLIDE_H_INCHES)

        # Blank slide layout (layout index 6)
        blank_layout = prs.slide_layouts[6]

        bg_path = config.template_image_path

        for slide_idx, (slide, plan) in enumerate(zip(slides, plans)):
            pptx_slide = prs.slides.add_slide(blank_layout)

            # 1. Full-slide Background Picture
            if os.path.exists(bg_path):
                pptx_slide.shapes.add_picture(bg_path, Inches(0), Inches(0), width=prs.slide_width, height=prs.slide_height)

            # 2. Place elements from layout plan
            for box in plan.elements:
                left_in = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
                top_in = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
                width_in = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
                height_in = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

                if box.element_type == "title":
                    self._add_title(pptx_slide, slide.title, left_in, top_in, width_in, height_in, plan, config)

                elif box.element_type == "presented_by":
                    pres_text = f"Presented By {professor_name}"
                    self._add_presented_by(pptx_slide, pres_text, left_in, top_in, width_in, height_in, plan, config)

                elif box.element_type == "footer":
                    footer_text = f"{config.college}   •   {slide.title}   •   Slide {slide.id}"
                    self._add_footer(pptx_slide, footer_text, left_in, top_in, width_in, height_in, plan, config, slide.verification_badge)

                elif box.element_type == "bullets":
                    self._add_bullets(pptx_slide, slide, left_in, top_in, width_in, height_in, plan, config)

                elif box.element_type == "code":
                    self._add_code_block(pptx_slide, slide, left_in, top_in, width_in, height_in, plan, config)

                elif box.element_type == "diagram":
                    self._add_diagram(pptx_slide, slide, left_in, top_in, width_in, height_in, plan, config)

        prs.save(output_pptx_path)
        return output_pptx_path

    def _add_title(self, slide, text: str, left, top, width, height, plan: SlideLayoutPlan, config: TemplateLayoutConfig):
        tx_box = slide.shapes.add_textbox(left, top, width, height)
        tf = tx_box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = config.fonts.title
        p.font.size = Pt(plan.font_sizes.get("title", 40))
        p.font.bold = True
        p.font.color.rgb = hex_to_rgb(config.colors.secondary)
        p.alignment = PP_ALIGN.LEFT

    def _add_presented_by(self, slide, text: str, left, top, width, height, plan: SlideLayoutPlan, config: TemplateLayoutConfig):
        # Subtle elegant pill badge on cover/closing slides
        rect = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        rect.fill.solid()
        rect.fill.fore_color.rgb = hex_to_rgb(config.colors.primary)
        rect.line.color.rgb = hex_to_rgb(config.colors.secondary)
        rect.line.width = Pt(1.5)

        tf = rect.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = config.fonts.body
        p.font.size = Pt(plan.font_sizes.get("presented_by", 28))
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

    def _add_footer(self, slide, text: str, left, top, width, height, plan: SlideLayoutPlan, config: TemplateLayoutConfig, badge: Optional[str] = None):
        tx_box = slide.shapes.add_textbox(left, top, width, height)
        tf = tx_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = config.fonts.body
        p.font.size = Pt(13)
        p.font.color.rgb = RGBColor(100, 116, 139)
        p.alignment = PP_ALIGN.LEFT

        if badge:
            # Place verified badge inside footer zone on the right side with zero overlap
            badge_width = Inches(3.6)
            badge_left = left + width - badge_width
            badge_shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, badge_left, top, badge_width, height)
            badge_shape.fill.solid()
            badge_shape.fill.fore_color.rgb = RGBColor(240, 253, 244)
            badge_shape.line.color.rgb = RGBColor(34, 197, 94)
            badge_shape.line.width = Pt(1)

            btf = badge_shape.text_frame
            btf.word_wrap = True
            btf.vertical_anchor = MSO_ANCHOR.MIDDLE
            bp = btf.paragraphs[0]
            bp.text = badge
            bp.font.name = config.fonts.code
            bp.font.size = Pt(10)
            bp.font.bold = True
            bp.font.color.rgb = RGBColor(22, 101, 52)
            bp.alignment = PP_ALIGN.CENTER

    def _add_bullets(self, slide, slide_data: Slide, left, top, width, height, plan: SlideLayoutPlan, config: TemplateLayoutConfig):
        # Card container with subtle backdrop
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(255, 255, 255)
        card.line.color.rgb = hex_to_rgb(config.colors.primary)
        card.line.width = Pt(1)

        tf = card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP
        font_size = plan.font_sizes.get("body", 28)

        for idx, bullet in enumerate(slide_data.bullets):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = f"•  {bullet}"
            p.font.name = config.fonts.body
            p.font.size = Pt(font_size)
            p.font.color.rgb = hex_to_rgb(config.colors.text)
            p.space_after = Pt(12)
            p.alignment = PP_ALIGN.LEFT

        # If exercise slide has ref or note, add it
        if slide_data.exercise_ref:
            p = tf.add_paragraph()
            p.text = f"Reference: {slide_data.exercise_ref}"
            p.font.size = Pt(font_size - 4)
            p.font.italic = True
            p.font.color.rgb = hex_to_rgb(config.colors.primary)

    def _add_code_block(self, slide, slide_data: Slide, left, top, width, height, plan: SlideLayoutPlan, config: TemplateLayoutConfig):
        code_data = slide_data.code
        if not code_data or not code_data.source:
            return

        # 1. Dark Code Container Shape
        dark_box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        dark_box.fill.solid()
        dark_box.fill.fore_color.rgb = hex_to_rgb(config.colors.code_bg)
        dark_box.line.color.rgb = hex_to_rgb(config.colors.primary)
        dark_box.line.width = Pt(1.5)

        tf = dark_box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP

        # Header tag (Language & Version pill)
        lang_header = f"// Language: {code_data.language.upper()} {code_data.version or ''}".strip()
        p_head = tf.paragraphs[0]
        p_head.text = lang_header
        p_head.font.name = config.fonts.code
        p_head.font.size = Pt(13)
        p_head.font.color.rgb = RGBColor(140, 155, 175)
        p_head.space_after = Pt(8)

        # 2. Syntax Highlighted Code Runs using Pygments
        code_font_size = plan.font_sizes.get("code", 18)
        try:
            lexer = get_lexer_by_name(code_data.language.lower(), stripall=True)
        except Exception:
            lexer = TextLexer(stripall=True)

        lines = code_data.source.split("\n")
        for line in lines:
            p = tf.add_paragraph()
            p.font.name = config.fonts.code
            p.font.size = Pt(code_font_size)
            p.space_after = Pt(2)

            tokens = list(lex(line, lexer))
            for token_type, token_val in tokens:
                if not token_val or token_val == "\n":
                    continue
                run = p.add_run()
                run.text = token_val
                run.font.name = config.fonts.code
                run.font.size = Pt(code_font_size)

                # Find matching color
                matched_color = DEFAULT_CODE_COLOR
                for k, col in TOKEN_COLOR_MAP.items():
                    if token_type in k:
                        matched_color = col
                        break
                run.font.color.rgb = matched_color

        # 3. Expected Output section
        if code_data.expected_output:
            p_out = tf.add_paragraph()
            p_out.space_before = Pt(12)
            run_lbl = p_out.add_run()
            run_lbl.text = "Expected Output: "
            run_lbl.font.name = config.fonts.code
            run_lbl.font.size = Pt(code_font_size - 2)
            run_lbl.font.bold = True
            run_lbl.font.color.rgb = RGBColor(74, 222, 128)  # Bright green

            run_val = p_out.add_run()
            run_val.text = code_data.expected_output
            run_val.font.name = config.fonts.code
            run_val.font.size = Pt(code_font_size - 2)
            run_val.font.color.rgb = RGBColor(226, 232, 240)

    def _add_diagram(self, slide, slide_data: Slide, left, top, width, height, plan: SlideLayoutPlan, config: TemplateLayoutConfig):
        diag_data = slide_data.diagram
        if not diag_data or not diag_data.source:
            return

        # Render diagram to temporary image
        temp_dir = os.path.join(os.path.dirname(config.template_image_path), "..", "..", "output", "temp_diagrams")
        os.makedirs(temp_dir, exist_ok=True)
        diag_img_path = os.path.join(temp_dir, f"diag_slide_{slide_data.id}.png")

        success = diagram_renderer.render_mermaid(diag_data.source, diag_img_path, width=700, height=450)
        if success and os.path.exists(diag_img_path):
            slide.shapes.add_picture(diag_img_path, left, top, width=width, height=height)


pptx_builder = PPTXBuilder()
