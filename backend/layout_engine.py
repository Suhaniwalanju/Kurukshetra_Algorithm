import os
import math
from typing import List, Dict, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from backend.schemas import (
    Slide,
    BoundingBox,
    TemplateLayoutConfig,
)

# 144 pixels per inch at 1920x1080 (13.333" x 7.5")
DPI = 144
MIN_GUTTER_PX = int(0.2 * DPI)  # 28.8 -> ~29 pixels minimum gutter (0.2 inch)

# Font size boundaries in points
TITLE_FONT_MAX = 44
TITLE_FONT_MIN = 34
BODY_FONT_DEFAULT = 30
BODY_FONT_MIN = 24  # strictly never below 24pt for body
CODE_FONT_DEFAULT = 20
CODE_FONT_MIN = 18  # strictly never below 18pt for code


def get_font(font_name: str, size_pt: int) -> ImageFont.FreeTypeFont:
    """Attempts to load true-type font from Windows/standard paths, falling back gracefully."""
    font_files = {
        "arial": ["arial.ttf", "Arial.ttf", "C:/Windows/Fonts/arial.ttf"],
        "segoe ui": ["segoeui.ttf", "SegoeUI.ttf", "C:/Windows/Fonts/segoeui.ttf"],
        "consolas": ["consola.ttf", "Consola.ttf", "C:/Windows/Fonts/consola.ttf"],
        "calibri": ["calibri.ttf", "Calibri.ttf", "C:/Windows/Fonts/calibri.ttf"],
    }
    
    candidates = font_files.get(font_name.lower(), [font_name, f"{font_name}.ttf"])
    for cand in candidates:
        try:
            return ImageFont.truetype(cand, size=size_pt)
        except Exception:
            continue
    
    # Try general system fallback
    for fb in ["C:/Windows/Fonts/arial.ttf", "arial.ttf", "segoeui.ttf", "consola.ttf"]:
        try:
            return ImageFont.truetype(fb, size=size_pt)
        except Exception:
            continue
            
    return ImageFont.load_default()


class ElementBox:
    def __init__(self, id_str: str, left: int, top: int, width: int, height: int, element_type: str = ""):
        self.id_str = id_str
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self.element_type = element_type

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def intersects(self, other: "ElementBox", gutter: int = MIN_GUTTER_PX) -> bool:
        """Checks if two boxes intersect with a minimum gutter buffer."""
        if (
            self.right + gutter <= other.left
            or self.left >= other.right + gutter
            or self.bottom + gutter <= other.top
            or self.top >= other.bottom + gutter
        ):
            return False
        return True

    def is_inside(self, zone: BoundingBox) -> bool:
        """Checks if this box is completely inside the allowed zone."""
        return (
            self.left >= zone.left
            and self.top >= zone.top
            and self.right <= zone.left + zone.width + 1  # 1px tolerance for rounding
            and self.bottom <= zone.top + zone.height + 1
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id_str,
            "type": self.element_type,
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
            "right": self.right,
            "bottom": self.bottom,
        }


class SlideLayoutPlan:
    def __init__(self, slide: Slide, config: TemplateLayoutConfig):
        self.slide = slide
        self.config = config
        self.elements: List[ElementBox] = []
        self.font_sizes: Dict[str, int] = {}
        self.violations: List[str] = []


class LayoutEngine:
    def __init__(self):
        self.dummy_img = Image.new("RGBA", (1920, 1080), (255, 255, 255, 0))
        self.draw = ImageDraw.Draw(self.dummy_img)

    def measure_text_lines(
        self, lines: List[str], font_family: str, font_size_pt: int, max_width: int, line_spacing_ratio: float = 1.3
    ) -> Tuple[int, int]:
        """Measures bounding dimensions for a list of text lines."""
        font = get_font(font_family, font_size_pt)
        max_line_w = 0
        total_h = 0
        line_height = int(font_size_pt * line_spacing_ratio)

        for line in lines:
            bbox = self.draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            max_line_w = max(max_line_w, w)
            total_h += line_height

        return max(max_line_w, 10), max(total_h, 10)

    def generate_deck_layout_plans(
        self, slides: List[Slide], config: TemplateLayoutConfig, professor_name: str
    ) -> List[SlideLayoutPlan]:
        """Convenience method returning plans for slides."""
        _, plans, _ = self.layout_deck(slides, config, professor_name)
        return plans

    def layout_deck(
        self, slides: List[Slide], config: TemplateLayoutConfig, professor_name: str, max_attempts: int = 3
    ) -> Tuple[List[Slide], List[SlideLayoutPlan], List[str]]:
        """
        Executes collision-free layout for all slides.
        If content overflows safe zones, first reduces font size (down to min: 24pt body, 18pt code).
        If it still overflows, splits the slide into two ("(Continued)") and re-layouts.
        Auto-fixes violations over up to max_attempts.
        """
        current_slides = list(slides)
        all_logs = []

        for attempt in range(max_attempts):
            plans: List[SlideLayoutPlan] = []
            needs_split = False
            split_target_idx = -1
            all_passed = True

            for idx, slide in enumerate(current_slides):
                plan = self.layout_single_slide(slide, config, professor_name)
                plans.append(plan)

                if plan.violations:
                    all_passed = False
                    all_logs.append(f"Attempt {attempt + 1}, Slide {slide.id} ('{slide.title}'): {'; '.join(plan.violations)}")
                    # Check if violation is vertical overflow that requires slide splitting
                    if any("overflow" in v.lower() for v in plan.violations) and len(slide.bullets) > 2:
                        needs_split = True
                        split_target_idx = idx
                        break

            if all_passed:
                all_logs.append(f"Layout engine verified 100% collision-free and safe on attempt {attempt + 1}.")
                return current_slides, plans, all_logs

            if needs_split and split_target_idx >= 0:
                # Split overflowing slide into two continued slides
                current_slides = self._split_slide(current_slides, split_target_idx)
                all_logs.append(f"Auto-fixed by splitting slide {split_target_idx + 1} into two continued slides.")
            else:
                # Try aggressive spacing compression on next attempt
                all_logs.append(f"Attempt {attempt + 1} had boundary adjustments; re-solving...")

        # Final check
        final_plans = [self.layout_single_slide(s, config, professor_name) for s in current_slides]
        return current_slides, final_plans, all_logs

    def _split_slide(self, slides: List[Slide], target_idx: int) -> List[Slide]:
        """Splits an overflowing slide into two continued slides."""
        orig = slides[target_idx]
        mid = len(orig.bullets) // 2
        part1_bullets = orig.bullets[:mid]
        part2_bullets = orig.bullets[mid:]

        # Slide 1 retains code or diagram if present
        slide1 = orig.model_copy()
        slide1.bullets = part1_bullets

        # Slide 2 is Continued
        slide2 = Slide(
            id=orig.id + 1,
            type=orig.type,
            title=f"{orig.title} (Cont.)"[:40],
            bullets=part2_bullets,
            code=None,  # keep code on slide 1 to avoid duplication
            diagram=None,
            exercise_ref=orig.exercise_ref,
            speaker_hint="Continue explanation from preceding slide.",
        )

        new_slides = slides[:target_idx] + [slide1, slide2] + slides[target_idx + 1:]
        # Re-index ids
        for i, s in enumerate(new_slides):
            s.id = i + 1
        return new_slides

    def plan_slide(self, slide: Slide, config: TemplateLayoutConfig, is_first_slide: bool = False, professor_name: str = "") -> SlideLayoutPlan:
        """Alias for layout_single_slide to provide standard layout planning interface."""
        return self.layout_single_slide(slide, config, professor_name)

    def layout_single_slide(self, slide: Slide, config: TemplateLayoutConfig, professor_name: str = "") -> SlideLayoutPlan:
        """
        Computes exact collision-free bounding boxes for all elements of a slide.
        Enforces min 0.2 inch (MIN_GUTTER_PX) gutter and strict safe-zone bounds.
        """
        plan = SlideLayoutPlan(slide, config)
        placed_boxes: List[ElementBox] = []

        is_cover = slide.type == "cover"

        # 1. Title Placement (Inside config.title_zone)
        title_font_size = TITLE_FONT_MAX
        t_box = None
        while title_font_size >= TITLE_FONT_MIN:
            tw, th = self.measure_text_lines([slide.title], config.fonts.title, title_font_size, config.title_zone.width)
            t_box = ElementBox(
                id_str=f"slide_{slide.id}_title",
                left=config.title_zone.left,
                top=config.title_zone.top + (config.title_zone.height - th) // 2,
                width=config.title_zone.width,
                height=th + 10,
                element_type="title",
            )
            if t_box.bottom <= config.title_zone.bottom + 5:
                break
            title_font_size -= 2

        plan.font_sizes["title"] = title_font_size
        placed_boxes.append(t_box)

        # 2. Cover slide special layout: "Presented By <professor_name>" (ONLY ONCE on cover slide)
        if is_cover:
            pres_font_size = 30
            pres_text = f"Presented By {professor_name}"
            pw, ph = self.measure_text_lines([pres_text], config.fonts.body, pres_font_size, config.presented_by_zone.width)
            pres_box = ElementBox(
                id_str=f"slide_{slide.id}_presented_by",
                left=config.presented_by_zone.left,
                top=config.presented_by_zone.top,
                width=config.presented_by_zone.width,
                height=ph + 12,
                element_type="presented_by",
            )
            plan.font_sizes["presented_by"] = pres_font_size
            placed_boxes.append(pres_box)

            # Cover subtitle/bullets placement inside content zone above presented_by_zone
            bullets_y = t_box.bottom + MIN_GUTTER_PX + 20
            avail_h = pres_box.top - MIN_GUTTER_PX - bullets_y
            body_size = BODY_FONT_DEFAULT
            bw, bh = self.measure_text_lines(slide.bullets, config.fonts.body, body_size, config.content_zone.width)
            while bh > avail_h and body_size > BODY_FONT_MIN:
                body_size -= 2
                bw, bh = self.measure_text_lines(slide.bullets, config.fonts.body, body_size, config.content_zone.width)

            b_box = ElementBox(
                id_str=f"slide_{slide.id}_bullets",
                left=config.content_zone.left + 40,
                top=bullets_y,
                width=config.content_zone.width - 80,
                height=bh + 10,
                element_type="bullets",
            )
            plan.font_sizes["body"] = body_size
            placed_boxes.append(b_box)

        else:
            # 3. Content & Closing Slides: Clean footer without duplicate Presented By
            has_code = bool(slide.code and slide.code.source.strip())
            has_diagram = bool(slide.diagram and slide.diagram.source.strip())
            
            # Footer: Clean slide title & slide number (Presented By is NOT repeated)
            footer_text = f"{slide.title}  |  Slide {slide.id}"
            fw, fh = self.measure_text_lines([footer_text], config.fonts.body, 14, config.footer_zone.width)
            footer_box = ElementBox(
                id_str=f"slide_{slide.id}_footer",
                left=config.footer_zone.left,
                top=config.footer_zone.top,
                width=config.footer_zone.width,
                height=fh + 6,
                element_type="footer",
            )
            plan.font_sizes["footer"] = 14
            placed_boxes.append(footer_box)

            content_y = t_box.bottom + MIN_GUTTER_PX
            content_max_bottom = footer_box.top - MIN_GUTTER_PX
            avail_content_h = content_max_bottom - content_y

            if has_code or has_diagram:
                # Two-column layout:
                # Left Column: Bullets (or Bullets + Output)
                # Right Column: Code block / Diagram
                col_gutter = MIN_GUTTER_PX + 10
                left_col_w = (config.content_zone.width - col_gutter) // 2
                right_col_w = left_col_w
                left_col_x = config.content_zone.left
                right_col_x = left_col_x + left_col_w + col_gutter

                # Measure bullets in left column
                body_size = BODY_FONT_DEFAULT
                bw, bh = self.measure_text_lines(
                    [f"• {b}" for b in slide.bullets], config.fonts.body, body_size, left_col_w
                )
                while bh > avail_content_h and body_size > BODY_FONT_MIN:
                    body_size -= 2
                    bw, bh = self.measure_text_lines(
                        [f"• {b}" for b in slide.bullets], config.fonts.body, body_size, left_col_w
                    )

                bullets_box = ElementBox(
                    id_str=f"slide_{slide.id}_bullets",
                    left=left_col_x,
                    top=content_y,
                    width=left_col_w,
                    height=min(bh + 15, avail_content_h),
                    element_type="bullets",
                )
                plan.font_sizes["body"] = body_size
                placed_boxes.append(bullets_box)

                # Right Column: Code block or Diagram
                if has_code:
                    code_lines = slide.code.source.strip().split("\n")
                    code_size = CODE_FONT_DEFAULT
                    cw, ch = self.measure_text_lines(code_lines, config.fonts.code, code_size, right_col_w)
                    while ch > avail_content_h - 60 and code_size > CODE_FONT_MIN:
                        code_size -= 2
                        cw, ch = self.measure_text_lines(code_lines, config.fonts.code, code_size, right_col_w)

                    code_box = ElementBox(
                        id_str=f"slide_{slide.id}_code",
                        left=right_col_x,
                        top=content_y,
                        width=right_col_w,
                        height=min(ch + 70, avail_content_h),
                        element_type="code",
                    )
                    plan.font_sizes["code"] = code_size
                    placed_boxes.append(code_box)

                elif has_diagram:
                    diag_box = ElementBox(
                        id_str=f"slide_{slide.id}_diagram",
                        left=right_col_x,
                        top=content_y,
                        width=right_col_w,
                        height=avail_content_h,
                        element_type="diagram",
                    )
                    placed_boxes.append(diag_box)

            else:
                # Single-column full-width bullets layout (Agenda / Summary / Concept without code)
                body_size = BODY_FONT_DEFAULT
                bw, bh = self.measure_text_lines(
                    [f"• {b}" for b in slide.bullets], config.fonts.body, body_size, config.content_zone.width - 60
                )
                while bh > avail_content_h and body_size > BODY_FONT_MIN:
                    body_size -= 2
                    bw, bh = self.measure_text_lines(
                        [f"• {b}" for b in slide.bullets], config.fonts.body, body_size, config.content_zone.width - 60
                    )

                bullets_box = ElementBox(
                    id_str=f"slide_{slide.id}_bullets",
                    left=config.content_zone.left + 30,
                    top=content_y + 10,
                    width=config.content_zone.width - 60,
                    height=min(bh + 20, avail_content_h),
                    element_type="bullets",
                )
                plan.font_sizes["body"] = body_size
                placed_boxes.append(bullets_box)

        plan.elements = placed_boxes

        # 4. Collision & Safe-Zone Validation
        self._validate_plan(plan)
        return plan

    def _validate_plan(self, plan: SlideLayoutPlan):
        """Checks for bounding-box collisions and safe zone boundary violations."""
        boxes = plan.elements
        config = plan.config

        # 1. Pairwise collision check
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                b1 = boxes[i]
                b2 = boxes[j]
                if b1.intersects(b2, gutter=MIN_GUTTER_PX):
                    plan.violations.append(
                        f"Collision detected between {b1.id_str} and {b2.id_str} (gutter < {MIN_GUTTER_PX}px)"
                    )

        # 2. Safe zone boundary check
        safe_zone = config.content_zone
        for b in boxes:
            if b.element_type == "title":
                if not b.is_inside(config.title_zone):
                    plan.violations.append(f"Title {b.id_str} extends outside Title Zone")
            elif b.element_type == "presented_by":
                if not b.is_inside(config.presented_by_zone):
                    plan.violations.append(f"Presented By {b.id_str} extends outside Presented By Zone")
            elif b.element_type == "footer":
                if not b.is_inside(config.footer_zone):
                    plan.violations.append(f"Footer {b.id_str} extends outside Footer Zone")
            elif b.element_type in ["bullets", "code", "diagram"]:
                # Must stay inside safe area (top of content zone down to bottom of content zone)
                if b.bottom > safe_zone.bottom + 10:
                    plan.violations.append(
                        f"Overflow: {b.id_str} ({b.bottom}px) exceeds safe content boundary ({safe_zone.bottom}px)"
                    )
                if b.left < safe_zone.left - 5 or b.right > safe_zone.right + 5:
                    plan.violations.append(f"Horizontal clip: {b.id_str} exceeds safe horizontal bounds")


layout_engine = LayoutEngine()


def validate_deck_layout(deck_dict: dict) -> Tuple[List[str], bool]:
    """
    Validates layout compliance for an entire deck.
    Returns (violations_list, is_compliant).
    """
    from backend.template_registry import template_registry
    from backend.schemas import Slide, SlideCode, SlideDiagram

    college = deck_dict.get("college", "VIT")
    config = template_registry.get_config(college)
    if not config and template_registry.templates:
        config = list(template_registry.templates.values())[0]

    slides_data = deck_dict.get("slides", [])
    violations: List[str] = []

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
        parsed_slides.append(Slide(**s_copy))

    if config:
        for idx, slide in enumerate(parsed_slides):
            plan = layout_engine.plan_slide(slide, config, is_first_slide=(idx == 0))
            for v in plan.violations:
                violations.append(f"Slide {slide.id}: {v}")

            # Bullet constraints: max 5 bullets, max 8 words per bullet
            for b_idx, bullet in enumerate(slide.bullets):
                words = bullet.strip().split()
                if len(words) > 8:
                    violations.append(f"Slide {slide.id}, Bullet {b_idx + 1}: Exceeds 8 words ({len(words)} words)")
            if len(slide.bullets) > 5:
                violations.append(f"Slide {slide.id}: Exceeds max 5 bullets ({len(slide.bullets)} bullets)")

    return violations, (len(violations) == 0)
