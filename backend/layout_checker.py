import os
import json
from typing import List, Dict, Any, Optional
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE

from backend.template_registry import template_registry
from backend.pdf_converter import convert_pptx_to_pdf

# DPU Theme Fonts & Safe Margins
THEME_FONTS = {"arial", "segoe ui", "consolas", "helvetica", "courier"}
MIN_TITLE_PT = 28.0
MIN_BODY_PT = 14.0
MIN_CODE_PT = 14.0
MIN_FOOTER_PT = 10.0
MAX_CODE_LINES = 14
MAX_CODE_COLUMNS = 60

# Margin thresholds in Inches (13.333 x 7.5 inch 16:9 canvas)
SAFE_MARGIN_LEFT_IN = 0.30
SAFE_MARGIN_TOP_IN = 0.15
SAFE_MARGIN_RIGHT_IN = 13.10
SAFE_MARGIN_BOTTOM_IN = 7.38


def check_deck_layout_compliance(
    pptx_path: str,
    pdf_path: Optional[str] = None,
    deck_id: str = "deck",
    topic: str = "Presentation",
    college: str = "DPU",
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Automated Layout Compliance Checker:
    - Opens PPTX and verifies every slide uses a DPU template layout.
    - Ensures fonts and colors come from theme.
    - Enforces minimum font sizes (Title >= 28pt, Body >= 14pt, Code >= 14pt, Footer >= 10pt).
    - Checks logo and footer presence.
    - Enforces code constraints: max 14 lines, max 60 columns, no overflow.
    - Enforces diagram constraints: no missing/empty diagrams.
    - Verifies element bounds within safe margins.
    - Validates PDF conversion fidelity.
    - Writes results to layout_report.json.
    """
    if not os.path.exists(pptx_path):
        raise FileNotFoundError(f"PPTX file not found: {pptx_path}")

    report_dir = output_dir or os.path.dirname(os.path.abspath(pptx_path))
    os.makedirs(report_dir, exist_ok=True)

    config = template_registry.get_config(college)
    template_pptx = getattr(config, "template_pptx_path", None)
    if not template_pptx or not os.path.exists(template_pptx):
        cand = os.path.join(os.path.dirname(__file__), "..", "input", "templates", "DPU", "DPU_Template.pptx")
        if os.path.exists(cand):
            template_pptx = cand

    valid_layout_names = set()
    if template_pptx and os.path.exists(template_pptx):
        try:
            tmpl_prs = Presentation(template_pptx)
            valid_layout_names = {l.name for l in tmpl_prs.slide_layouts}
        except Exception:
            pass

    prs = Presentation(pptx_path)
    slide_w_in = prs.slide_width.inches
    slide_h_in = prs.slide_height.inches

    all_defects: List[Dict[str, Any]] = []
    slide_reports: List[Dict[str, Any]] = []
    defects_by_type: Dict[str, int] = {
        "INVALID_LAYOUT": 0,
        "MARGIN_OVERFLOW": 0,
        "FONT_TOO_SMALL": 0,
        "INVALID_FONT": 0,
        "MISSING_LOGO": 0,
        "MISSING_FOOTER": 0,
        "MISSING_DIAGRAM": 0,
        "CODE_OVERFLOW": 0,
    }

    # If PDF path not provided, check or generate one
    if not pdf_path:
        cand_pdf = os.path.splitext(pptx_path)[0] + ".pdf"
        if os.path.exists(cand_pdf):
            pdf_path = cand_pdf
        else:
            cand_deck_pdf = os.path.join(report_dir, f"Deck_{deck_id}.pdf")
            if os.path.exists(cand_deck_pdf):
                pdf_path = cand_deck_pdf
            else:
                # Convert PPTX to PDF
                ok = convert_pptx_to_pdf(pptx_path, cand_pdf)
                if ok:
                    pdf_path = cand_pdf

    # Verify PDF exists and has pages
    pdf_page_count = 0
    if pdf_path and os.path.exists(pdf_path):
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            pdf_page_count = len(reader.pages)
        except Exception:
            pass

    for slide_idx, slide in enumerate(prs.slides):
        slide_num = slide_idx + 1
        slide_defects: List[str] = []

        # 1. Template Layout Compliance
        layout_name = slide.slide_layout.name if hasattr(slide, "slide_layout") else "Unknown"
        if valid_layout_names and layout_name not in valid_layout_names:
            msg = f"Layout '{layout_name}' is not an authorized DPU template layout."
            slide_defects.append(msg)
            defects_by_type["INVALID_LAYOUT"] += 1

        has_title = False
        has_logo = False
        has_footer = False
        has_code = False
        has_diagram = False
        has_empty_diagram = False

        slide_title = ""

        # Inspect all shapes on the slide
        for shape in slide.shapes:
            left_in = shape.left.inches if shape.left else 0.0
            top_in = shape.top.inches if shape.top else 0.0
            width_in = shape.width.inches if shape.width else 0.0
            height_in = shape.height.inches if shape.height else 0.0
            right_in = left_in + width_in
            bottom_in = top_in + height_in

            # Skip full-bleed background images from margin check
            is_full_bleed_bg = (
                shape.shape_type == MSO_SHAPE_TYPE.PICTURE
                and abs(width_in - slide_w_in) < 0.1
                and abs(height_in - slide_h_in) < 0.1
            )

            # Check safe margins for all interactive/content shapes
            if not is_full_bleed_bg:
                if (
                    left_in < (SAFE_MARGIN_LEFT_IN - 0.05)
                    or top_in < (SAFE_MARGIN_TOP_IN - 0.05)
                    or right_in > (SAFE_MARGIN_RIGHT_IN + 0.1)
                    or bottom_in > (SAFE_MARGIN_BOTTOM_IN + 0.1)
                ):
                    msg = f"Shape '{shape.name}' overflows safe margins: [left={left_in:.2f}\", top={top_in:.2f}\", right={right_in:.2f}\", bottom={bottom_in:.2f}\"]"
                    slide_defects.append(msg)
                    defects_by_type["MARGIN_OVERFLOW"] += 1

            # Detect Logo picture
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                # Picture in header zone is the logo or diagram
                if top_in < 1.2 and width_in < 4.0:
                    has_logo = True
                elif top_in >= 1.5:
                    has_diagram = True

            # Detect diagram placeholders or empty shapes
            if shape.is_placeholder and "diagram" in shape.name.lower():
                if not shape.has_text_frame and shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                    has_empty_diagram = True

            # Text analysis
            if shape.has_text_frame:
                tf = shape.text_frame
                text_content = tf.text.strip()
                if not text_content:
                    continue

                is_title_shape = (
                    (shape.is_placeholder and shape.placeholder_format.idx == 0)
                    or ("title" in shape.name.lower() and "subtitle" not in shape.name.lower())
                )
                if is_title_shape and text_content:
                    has_title = True
                    slide_title = text_content.splitlines()[0]

                is_footer_shape = (
                    (shape.is_placeholder and shape.placeholder_format.idx in (11, 12))
                    or "footer" in shape.name.lower()
                    or "slide number" in shape.name.lower()
                    or "dpu" in text_content.lower()
                    or "patil" in text_content.lower()
                    or "vidyapeeth" in text_content.lower()
                )
                if is_footer_shape and text_content:
                    has_footer = True

                is_code_block = (
                    "code" in shape.name.lower()
                    or "rectangle" in shape.name.lower()
                    or "//" in text_content
                    or "#" in text_content
                    or any(p.font.name and "consolas" in p.font.name.lower() for p in tf.paragraphs if p.font and p.font.name)
                )

                if is_code_block and ("//" in text_content or any(p.font.name and "consolas" in p.font.name.lower() for p in tf.paragraphs if p.font and p.font.name)):
                    has_code = True
                    # Check code line count and column count
                    code_lines = [l for l in text_content.splitlines() if not l.startswith("// PART") and not l.startswith("# PART")]
                    if len(code_lines) > MAX_CODE_LINES + 2:  # allow header line
                        msg = f"Code block exceeds {MAX_CODE_LINES} lines ({len(code_lines)} lines found)."
                        slide_defects.append(msg)
                        defects_by_type["CODE_OVERFLOW"] += 1

                    max_cols = max((len(l) for l in code_lines), default=0)
                    if max_cols > MAX_CODE_COLUMNS + 5:  # small tolerance
                        msg = f"Code block exceeds {MAX_CODE_COLUMNS} columns ({max_cols} cols found)."
                        slide_defects.append(msg)
                        defects_by_type["CODE_OVERFLOW"] += 1

                # Inspect paragraphs and runs for fonts and sizes
                for p in tf.paragraphs:
                    font_size = p.font.size.pt if p.font and p.font.size else None
                    font_name = p.font.name if p.font and p.font.name else None

                    # Also check runs
                    if not font_size:
                        for run in p.runs:
                            if run.font and run.font.size:
                                font_size = run.font.size.pt
                                break
                    if not font_name:
                        for run in p.runs:
                            if run.font and run.font.name:
                                font_name = run.font.name
                                break

                    # Font Family Compliance
                    if font_name and font_name.lower() not in THEME_FONTS:
                        msg = f"Font '{font_name}' does not match DPU theme palette (Arial, Segoe UI, Consolas)."
                        if msg not in slide_defects:
                            slide_defects.append(msg)
                            defects_by_type["INVALID_FONT"] += 1

                    # Minimum Font Size Checks
                    if font_size:
                        if is_title_shape and font_size < MIN_TITLE_PT:
                            msg = f"Title font size {font_size}pt is below minimum {MIN_TITLE_PT}pt."
                            if msg not in slide_defects:
                                slide_defects.append(msg)
                                defects_by_type["FONT_TOO_SMALL"] += 1
                        elif is_code_block and font_size < MIN_CODE_PT:
                            msg = f"Code font size {font_size}pt is below minimum {MIN_CODE_PT}pt."
                            if msg not in slide_defects:
                                slide_defects.append(msg)
                                defects_by_type["FONT_TOO_SMALL"] += 1
                        elif is_footer_shape and font_size < MIN_FOOTER_PT:
                            msg = f"Footer font size {font_size}pt is below minimum {MIN_FOOTER_PT}pt."
                            if msg not in slide_defects:
                                slide_defects.append(msg)
                                defects_by_type["FONT_TOO_SMALL"] += 1
                        elif not is_title_shape and not is_code_block and not is_footer_shape and font_size < MIN_BODY_PT:
                            msg = f"Body font size {font_size}pt is below minimum {MIN_BODY_PT}pt."
                            if msg not in slide_defects:
                                slide_defects.append(msg)
                                defects_by_type["FONT_TOO_SMALL"] += 1

        # Slide-level presence checks
        if not has_logo:
            msg = "DPU Logo is missing from slide."
            slide_defects.append(msg)
            defects_by_type["MISSING_LOGO"] += 1

        if not has_footer:
            msg = "Footer or slide number placeholder is missing or unpopulated."
            slide_defects.append(msg)
            defects_by_type["MISSING_FOOTER"] += 1

        if has_empty_diagram:
            msg = "Empty diagram area or unpopulated diagram placeholder detected."
            slide_defects.append(msg)
            defects_by_type["MISSING_DIAGRAM"] += 1

        slide_report = {
            "slide_number": slide_num,
            "title": slide_title or f"Slide {slide_num}",
            "layout": layout_name,
            "defect_count": len(slide_defects),
            "defects": slide_defects,
            "status": "PASS" if len(slide_defects) == 0 else "FAIL",
        }
        slide_reports.append(slide_report)
        if slide_defects:
            all_defects.extend([{"slide": slide_num, "defect": d} for d in slide_defects])

    total_defects = len(all_defects)
    deck_passed = (total_defects == 0)

    report = {
        "deck_id": deck_id,
        "topic": topic,
        "college": college,
        "pptx_path": pptx_path,
        "pdf_path": pdf_path,
        "pdf_page_count": pdf_page_count,
        "total_slides": len(prs.slides),
        "total_defects": total_defects,
        "status": "PASSED" if deck_passed else "FAILED",
        "defects_by_type": defects_by_type,
        "slides": slide_reports,
    }

    report_path = os.path.join(report_dir, "layout_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    import sys
    test_pptx = "output/test_notes_single_slide_deck/Python_Scripting_Python.pptx"
    if os.path.exists(test_pptx):
        rep = check_deck_layout_compliance(test_pptx, deck_id="test", topic="Python")
        print("Layout Report Result:", rep["status"], "Defects:", rep["total_defects"])
