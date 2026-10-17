import os
import shutil
from typing import List, Dict, Any, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

from backend.schemas import Slide, SlideCode, SlideDiagram, TemplateLayoutConfig
from backend.layout_engine import ElementBox, SlideLayoutPlan
from backend.diagram_renderer import diagram_renderer
from backend.code_renderer import render_code_block, PPTX_TOKEN_COLOR_MAP, DEFAULT_CODE_RGB
from backend.utils import sanitize_filename

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
        Builds a PowerPoint presentation adhering strictly to the DPU Template:
        - Loads DPU template and uses its own layouts and placeholders.
        - Populates title, body, footer, logo, and slide number placeholders directly.
        - Does not draw custom text boxes where placeholders exist.
        - Uses shared render_code_block for code with Pygments syntax highlighting,
          minimum 14pt, max 14 lines, max 60 columns, preserved indentation.
        - Renders diagrams at 2x resolution with text >= 16pt.
        """
        dir_name = os.path.dirname(os.path.abspath(output_pptx_path))
        base_name = os.path.basename(output_pptx_path)
        name, ext = os.path.splitext(base_name)
        safe_base = f"{sanitize_filename(name)}{ext if ext else '.pptx'}"
        output_pptx_path = os.path.join(dir_name, safe_base)
        os.makedirs(dir_name, exist_ok=True)

        # 1. Load DPU template PPTX if present, otherwise initialize presentation with DPU dimensions
        template_pptx = getattr(config, "template_pptx_path", None)
        if not template_pptx or not os.path.exists(template_pptx):
            dpu_cand = os.path.join(os.path.dirname(__file__), "..", "input", "templates", "DPU", "DPU_Template.pptx")
            if os.path.exists(dpu_cand):
                template_pptx = dpu_cand

        if template_pptx and os.path.exists(template_pptx):
            prs = Presentation(template_pptx)
        else:
            prs = Presentation()

        prs.slide_width = Inches(SLIDE_W_INCHES)
        prs.slide_height = Inches(SLIDE_H_INCHES)

        bg_path = config.template_image_path
        logo_path = getattr(config, "logo_path", None)
        if not logo_path or not os.path.exists(logo_path):
            cand_logo = os.path.join(os.path.dirname(__file__), "..", "input", "templates", "DPU", "dpu_logo.png")
            if os.path.exists(cand_logo):
                logo_path = cand_logo

        # Layout mapping from DPU Template
        # Layout 0: Title Slide
        # Layout 1: Title and Content (Single Content)
        # Layout 3: Two Content (Split Left/Right)
        num_layouts = len(prs.slide_layouts)
        title_layout = prs.slide_layouts[0] if num_layouts > 0 else prs.slide_layouts[0]
        content_layout = prs.slide_layouts[1] if num_layouts > 1 else title_layout
        two_content_layout = prs.slide_layouts[3] if num_layouts > 3 else content_layout

        for slide_idx, (slide, plan) in enumerate(zip(slides, plans)):
            has_split = (slide.code and (slide.diagram or slide.bullets)) or (slide.diagram and slide.bullets)

            # Select layout from DPU template
            if slide.type == "cover":
                selected_layout = title_layout
            elif has_split:
                selected_layout = two_content_layout
            else:
                selected_layout = content_layout

            pptx_slide = prs.slides.add_slide(selected_layout)

            # Ensure background image is present and placed in the background
            if os.path.exists(bg_path):
                bg_pic = pptx_slide.shapes.add_picture(bg_path, Inches(0), Inches(0), width=prs.slide_width, height=prs.slide_height)
                try:
                    pptx_slide.shapes._spTree.remove(bg_pic._element)
                    pptx_slide.shapes._spTree.insert(2, bg_pic._element)
                except Exception:
                    pass

            # Ensure logo is present
            if logo_path and os.path.exists(logo_path):
                pptx_slide.shapes.add_picture(logo_path, Inches(0.4), Inches(0.2), width=Inches(3.2), height=Inches(0.8))

            # -------------------------------------------------------------
            # 1. Title Placeholder (Never draw custom textbox when title placeholder exists)
            # -------------------------------------------------------------
            title_p = pptx_slide.shapes.title
            if not title_p:
                title_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 0), None)
            
            title_box = next((b for b in plan.elements if b.element_type == "title"), None)
            title_font_size = max(28, plan.font_sizes.get("title", 36))

            if title_p:
                tf = title_p.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                p.text = slide.title
                p.font.name = config.fonts.title
                p.font.size = Pt(title_font_size)
                p.font.bold = True
                p.font.color.rgb = hex_to_rgb(config.colors.secondary)
                p.alignment = PP_ALIGN.LEFT
                # Re-position title placeholder to safe zone if needed
                if title_box:
                    title_p.left = px_to_inches(title_box.left, config.slide_width, SLIDE_W_INCHES)
                    title_p.top = px_to_inches(title_box.top, config.slide_height, SLIDE_H_INCHES)
                    title_p.width = px_to_inches(title_box.width, config.slide_width, SLIDE_W_INCHES)
                    title_p.height = px_to_inches(title_box.height, config.slide_height, SLIDE_H_INCHES)

            # -------------------------------------------------------------
            # 2. Cover / Title Slide Subtitle Placeholder
            # -------------------------------------------------------------
            if slide.type == "cover":
                sub_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 1), None)
                pres_text = f"Presented By {professor_name}\n{config.college} Curriculum"
                pres_box = next((b for b in plan.elements if b.element_type == "presented_by"), None)

                if sub_p:
                    stf = sub_p.text_frame
                    stf.word_wrap = True
                    p0 = stf.paragraphs[0]
                    p0.text = f"Presented By {professor_name}"
                    p0.font.name = config.fonts.body
                    p0.font.size = Pt(max(20, plan.font_sizes.get("presented_by", 24)))
                    p0.font.bold = True
                    p0.font.color.rgb = hex_to_rgb(config.colors.primary)
                    p0.alignment = PP_ALIGN.LEFT

                    p1 = stf.add_paragraph()
                    p1.text = f"{config.college} Course Material"
                    p1.font.name = config.fonts.body
                    p1.font.size = Pt(16)
                    p1.font.color.rgb = hex_to_rgb(config.colors.muted or "#64748B")
                    p1.alignment = PP_ALIGN.LEFT

                    if pres_box:
                        sub_p.left = px_to_inches(pres_box.left, config.slide_width, SLIDE_W_INCHES)
                        sub_p.top = px_to_inches(pres_box.top, config.slide_height, SLIDE_H_INCHES)
                        sub_p.width = px_to_inches(pres_box.width, config.slide_width, SLIDE_W_INCHES)
                        sub_p.height = px_to_inches(pres_box.height, config.slide_height, SLIDE_H_INCHES)
                else:
                    if pres_box:
                        self._add_presented_by_card(pptx_slide, pres_text, pres_box, config)

            # -------------------------------------------------------------
            # 3. Content Placeholders (Body, Split Left, Split Right)
            # -------------------------------------------------------------
            if slide.type != "cover":
                if has_split:
                    # Layout 3: Two Content Placeholders (idx 1 = Left, idx 2 = Right)
                    left_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 1), None)
                    right_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 2), None)
                    
                    # Case A: Bullets (Left) and Code (Right)
                    if slide.bullets and slide.code:
                        bullet_box = next((b for b in plan.elements if b.element_type == "bullets"), None)
                        code_box = next((b for b in plan.elements if b.element_type == "code"), None)
                        if left_p:
                            self._populate_bullets_into_placeholder(left_p, slide, plan, config, bullet_box)
                        if code_box:
                            self._add_shared_code_block(pptx_slide, slide, code_box, config, target_placeholder=right_p)

                    # Case B: Code (Left) and Diagram (Right)
                    elif slide.code and slide.diagram:
                        code_box = next((b for b in plan.elements if b.element_type == "code"), None)
                        diag_box = next((b for b in plan.elements if b.element_type == "diagram"), None)
                        if code_box:
                            self._add_shared_code_block(pptx_slide, slide, code_box, config, target_placeholder=left_p)
                        if diag_box:
                            self._add_diagram_to_slide(pptx_slide, slide, diag_box, config, target_placeholder=right_p)

                    # Case C: Bullets (Left) and Diagram (Right)
                    elif slide.bullets and slide.diagram:
                        bullet_box = next((b for b in plan.elements if b.element_type == "bullets"), None)
                        diag_box = next((b for b in plan.elements if b.element_type == "diagram"), None)
                        if left_p:
                            self._populate_bullets_into_placeholder(left_p, slide, plan, config, bullet_box)
                        if diag_box:
                            self._add_diagram_to_slide(pptx_slide, slide, diag_box, config, target_placeholder=right_p)

                else:
                    # Single Content Placeholder (idx 1)
                    body_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 1), None)

                    if slide.bullets:
                        bullet_box = next((b for b in plan.elements if b.element_type == "bullets"), None)
                        if body_p:
                            self._populate_bullets_into_placeholder(body_p, slide, plan, config, bullet_box)
                        elif bullet_box:
                            self._add_bullets_card(pptx_slide, slide, bullet_box, plan, config)

                    elif slide.code:
                        code_box = next((b for b in plan.elements if b.element_type == "code"), None)
                        if code_box:
                            self._add_shared_code_block(pptx_slide, slide, code_box, config, target_placeholder=body_p)

                    elif slide.diagram:
                        diag_box = next((b for b in plan.elements if b.element_type == "diagram"), None)
                        if diag_box:
                            self._add_diagram_to_slide(pptx_slide, slide, diag_box, config, target_placeholder=body_p)

            # -------------------------------------------------------------
            # 4. Footer Placeholder & Slide Number Placeholder
            # -------------------------------------------------------------
            footer_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 11 or "footer" in p.name.lower()), None)
            default_footer = getattr(config, "footer_text", None) or f"{config.college}   •   {slide.title}"
            footer_box = next((b for b in plan.elements if b.element_type == "footer"), None)
            if not footer_box and config.footer_zone:
                footer_box = ElementBox(
                    id_str="footer",
                    left=config.footer_zone.left,
                    top=config.footer_zone.top,
                    width=config.footer_zone.width,
                    height=config.footer_zone.height,
                    element_type="footer",
                )

            if footer_p:
                ftf = footer_p.text_frame
                ftf.word_wrap = True
                fp = ftf.paragraphs[0]
                badge_text = f"   [{slide.verification_badge}]" if slide.verification_badge else ""
                fp.text = f"{default_footer}{badge_text}"
                fp.font.name = config.fonts.body
                fp.font.size = Pt(11)
                fp.font.color.rgb = hex_to_rgb(config.colors.muted or "#64748B")
                fp.alignment = PP_ALIGN.LEFT
                if footer_box:
                    footer_p.left = px_to_inches(footer_box.left, config.slide_width, SLIDE_W_INCHES)
                    footer_p.top = px_to_inches(footer_box.top, config.slide_height, SLIDE_H_INCHES)
                    footer_p.width = px_to_inches(footer_box.width - 150, config.slide_width, SLIDE_W_INCHES)
                    footer_p.height = px_to_inches(footer_box.height, config.slide_height, SLIDE_H_INCHES)
            elif footer_box:
                self._add_custom_footer(pptx_slide, default_footer, footer_box, config, slide.verification_badge)

            # Slide Number Placeholder
            num_p = next((p for p in pptx_slide.placeholders if p.placeholder_format.idx == 12 or "slide number" in p.name.lower()), None)
            if num_p:
                ntf = num_p.text_frame
                np = ntf.paragraphs[0]
                np.text = f"{slide.id}"
                np.font.name = config.fonts.body
                np.font.size = Pt(11)
                np.font.color.rgb = hex_to_rgb(config.colors.muted or "#64748B")
                np.alignment = PP_ALIGN.RIGHT
                if footer_box:
                    num_p.left = px_to_inches(footer_box.right - 120, config.slide_width, SLIDE_W_INCHES)
                    num_p.top = px_to_inches(footer_box.top, config.slide_height, SLIDE_H_INCHES)
                    num_p.width = px_to_inches(120, config.slide_width, SLIDE_W_INCHES)
                    num_p.height = px_to_inches(footer_box.height, config.slide_height, SLIDE_H_INCHES)

            # -------------------------------------------------------------
            # 5. Slide Speaker and Trainer Notes
            # -------------------------------------------------------------
            notes_parts = []
            if getattr(slide, "speaker_hint", ""):
                notes_parts.append(f"Speaker Hint:\n{slide.speaker_hint}")
            if getattr(slide, "trainer_notes", ""):
                notes_parts.append(f"Trainer Notes:\n{slide.trainer_notes}")
            if notes_parts:
                try:
                    pptx_slide.notes_slide.notes_text_frame.text = "\n\n".join(notes_parts)
                except Exception:
                    pass

        prs.save(output_pptx_path)
        return output_pptx_path

    def _populate_bullets_into_placeholder(self, placeholder, slide: Slide, plan: SlideLayoutPlan, config: TemplateLayoutConfig, box: Optional[ElementBox] = None):
        """Populates bullets directly into a DPU template content placeholder."""
        if box:
            placeholder.left = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
            placeholder.top = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
            placeholder.width = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
            placeholder.height = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

        tf = placeholder.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP
        font_size = max(16, plan.font_sizes.get("body", 22))

        for idx, bullet in enumerate(slide.bullets):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = f"•  {bullet}"
            p.font.name = config.fonts.body
            p.font.size = Pt(font_size)
            p.font.color.rgb = hex_to_rgb(config.colors.text)
            p.space_after = Pt(10)
            p.alignment = PP_ALIGN.LEFT

        if slide.exercise_ref:
            p_ref = tf.add_paragraph()
            p_ref.text = f"Exercise Reference: {slide.exercise_ref}"
            p_ref.font.name = config.fonts.body
            p_ref.font.size = Pt(max(14, font_size - 2))
            p_ref.font.italic = True
            p_ref.font.color.rgb = hex_to_rgb(config.colors.primary)

    def _add_shared_code_block(self, pptx_slide, slide: Slide, box: ElementBox, config: TemplateLayoutConfig, target_placeholder=None):
        """
        Renders a syntax-highlighted code block using the shared render_code_block module:
        - Monospace font Consolas
        - Pygments syntax highlighting
        - Minimum 14pt
        - Max 14 lines, max 60 columns
        - Preserved indentation, no line wrapping
        - Padded panel using template palette
        """
        code_data = slide.code
        if not code_data or not code_data.source:
            return

        rendered = render_code_block(
            code=code_data.source,
            language=code_data.language,
            palette=config.colors.model_dump(),
            font_size_pt=14,
            max_lines=14,
            max_cols=60,
        )

        left_in = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
        top_in = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
        width_in = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
        height_in = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

        if target_placeholder:
            target_placeholder.left = left_in
            target_placeholder.top = top_in
            target_placeholder.width = width_in
            target_placeholder.height = height_in

        # Padded dark panel matching template palette
        panel = pptx_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_in, top_in, width_in, height_in)
        panel.fill.solid()
        panel.fill.fore_color.rgb = hex_to_rgb(rendered["bg_color"])
        panel.line.color.rgb = hex_to_rgb(rendered["border_color"])
        panel.line.width = Pt(1.5)

        tf = panel.text_frame
        tf.word_wrap = False  # Strict no line wrapping requirement
        tf.vertical_anchor = MSO_ANCHOR.TOP

        # Language tag header
        p_head = tf.paragraphs[0]
        header_text = f"// {code_data.language.upper()} {code_data.version or ''}".strip()
        if rendered["is_split"]:
            header_text += " [Part 1/2]"
        p_head.text = header_text
        p_head.font.name = rendered["font_family"]
        p_head.font.size = Pt(max(14, rendered["font_size_pt"]))
        p_head.font.color.rgb = RGBColor(96, 165, 250)
        p_head.space_after = Pt(6)

        # Render syntax-highlighted tokens line by line preserving indentation
        code_lines = rendered["code"].splitlines()
        for c_line in code_lines:
            p_line = tf.add_paragraph()
            p_line.font.name = rendered["font_family"]
            p_line.font.size = Pt(rendered["font_size_pt"])
            p_line.space_after = Pt(2)

            line_tokens = get_tokens_for_line(c_line, code_data.language)
            for token_type, token_val in line_tokens:
                clean_val = token_val.replace("\r", "").replace("\n", "")
                if not clean_val:
                    continue
                run = p_line.add_run()
                run.text = clean_val
                run.font.name = rendered["font_family"]
                run.font.size = Pt(rendered["font_size_pt"])

                color_rgb = DEFAULT_CODE_RGB
                for k, col in PPTX_TOKEN_COLOR_MAP.items():
                    if token_type in k:
                        color_rgb = col
                        break
                run.font.color.rgb = RGBColor(color_rgb[0], color_rgb[1], color_rgb[2])

        # If full code was excerpted, record the full code in trainer notes
        if rendered["excerpt"] and not getattr(slide, "trainer_notes", ""):
            slide.trainer_notes = f"Full Code:\n{rendered['full_code']}"

    def _add_diagram_to_slide(self, pptx_slide, slide: Slide, box: ElementBox, config: TemplateLayoutConfig, target_placeholder=None):
        """
        Renders diagram spec to 2x resolution PNG and inserts into placeholder/content area.
        Never leaves a placeholder box or empty diagram area.
        """
        diag_data = slide.diagram
        if not diag_data or not diag_data.source:
            return

        temp_dir = os.path.join(os.path.dirname(config.template_image_path), "..", "..", "output", "temp_diagrams")
        os.makedirs(temp_dir, exist_ok=True)
        diag_img_path = os.path.join(temp_dir, f"diag_slide_{slide.id}.png")

        left_in = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
        top_in = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
        width_in = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
        height_in = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

        if target_placeholder:
            target_placeholder.left = left_in
            target_placeholder.top = top_in
            target_placeholder.width = width_in
            target_placeholder.height = height_in

        success = diagram_renderer.render_diagram_to_png(
            spec=diag_data.source,
            output_path=diag_img_path,
            target_width=box.width,
            target_height=box.height,
            palette=config.colors.model_dump(),
            font_family=config.fonts.body,
            scale=2.0,
        )

        if success and os.path.exists(diag_img_path):
            pptx_slide.shapes.add_picture(diag_img_path, left_in, top_in, width=width_in, height=height_in)

    def _add_presented_by_card(self, slide, text: str, box: ElementBox, config: TemplateLayoutConfig):
        left_in = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
        top_in = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
        width_in = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
        height_in = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

        rect = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_in, top_in, width_in, height_in)
        rect.fill.solid()
        rect.fill.fore_color.rgb = RGBColor(255, 255, 255)
        rect.line.color.rgb = hex_to_rgb(config.colors.primary)
        rect.line.width = Pt(1.5)

        tf = rect.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.text = text
        p.font.name = config.fonts.body
        p.font.size = Pt(22)
        p.font.bold = True
        p.font.color.rgb = hex_to_rgb(config.colors.primary)
        p.alignment = PP_ALIGN.CENTER

    def _add_bullets_card(self, slide, slide_data: Slide, box: ElementBox, plan: SlideLayoutPlan, config: TemplateLayoutConfig):
        left_in = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
        top_in = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
        width_in = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
        height_in = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left_in, top_in, width_in, height_in)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(248, 250, 252)
        card.line.color.rgb = RGBColor(226, 232, 240)
        card.line.width = Pt(1)

        tf = card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.TOP
        font_size = max(16, plan.font_sizes.get("body", 22))

        for idx, bullet in enumerate(slide_data.bullets):
            p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            p.text = f"•  {bullet}"
            p.font.name = config.fonts.body
            p.font.size = Pt(font_size)
            p.font.color.rgb = hex_to_rgb(config.colors.text)
            p.space_after = Pt(12)
            p.alignment = PP_ALIGN.LEFT

    def _add_custom_footer(self, slide, text: str, box: ElementBox, config: TemplateLayoutConfig, badge: Optional[str] = None):
        left_in = px_to_inches(box.left, config.slide_width, SLIDE_W_INCHES)
        top_in = px_to_inches(box.top, config.slide_height, SLIDE_H_INCHES)
        width_in = px_to_inches(box.width, config.slide_width, SLIDE_W_INCHES)
        height_in = px_to_inches(box.height, config.slide_height, SLIDE_H_INCHES)

        tx_box = slide.shapes.add_textbox(left_in, top_in, width_in, height_in)
        tx_box.name = "Footer Placeholder"
        tf = tx_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        badge_text = f"   [{badge}]" if badge else ""
        p.text = f"{text}{badge_text}"
        p.font.name = config.fonts.body
        p.font.size = Pt(11)
        p.font.color.rgb = hex_to_rgb(config.colors.muted or "#64748B")
        p.alignment = PP_ALIGN.LEFT


def get_tokens_for_line(line: str, language: str):
    from pygments import lex
    from pygments.lexers import get_lexer_by_name, TextLexer
    try:
        lexer = get_lexer_by_name(language.lower(), stripall=False)
    except Exception:
        lexer = TextLexer()
    return list(lex(line, lexer))


pptx_builder = PPTXBuilder()


def build_presentation(deck_dict: dict) -> str:
    from backend.template_registry import template_registry
    from backend.layout_engine import layout_engine

    deck_id = deck_dict.get("id", "deck")
    college = deck_dict.get("college", "DPU")
    prof_name = deck_dict.get("professor_name", "Professor")
    topic = deck_dict.get("topic", "Presentation")
    tech = deck_dict.get("tech", "Code")

    config = template_registry.get_config(college)
    if not config and template_registry.templates:
        config = list(template_registry.templates.values())[0]

    output_dir = os.path.join(os.path.abspath("output"), deck_id)
    os.makedirs(output_dir, exist_ok=True)
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

    pptx_builder.build_deck(parsed_slides, plans, config, prof_name, pptx_path)
    return pptx_path
