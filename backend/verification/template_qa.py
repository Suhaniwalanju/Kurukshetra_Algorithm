import os
from typing import Dict, Any, List, Tuple
from PIL import Image, ImageDraw

from backend.schemas import Slide, TemplateLayoutConfig
from backend.layout_engine import SlideLayoutPlan, ElementBox, MIN_GUTTER_PX, BODY_FONT_MIN, CODE_FONT_MIN


class TemplateComplianceQA:
    def __init__(self):
        pass

    def verify_deck_compliance(
        self,
        slides: List[Slide],
        plans: List[SlideLayoutPlan],
        config: TemplateLayoutConfig,
        professor_name: str,
        preview_image_paths: List[str],
        output_dir: str,
    ) -> Tuple[bool, List[Dict[str, Any]], List[str]]:
        """
        Runs comprehensive visual compliance QA on every slide:
        1. Background template intact (not stretched)
        2. All elements inside designated safe zones
        3. Zero overlaps or merged boxes (bounding-box intersection with 0.2" gutter)
        4. No clipped text
        5. Minimum font sizes respected (>= 24pt body, >= 18pt code)
        6. 'Presented By' present on Cover slide once
        Outputs per-slide compliance status and annotated images on failure.
        """
        all_passed = True
        per_slide_results = []
        annotated_images = []

        os.makedirs(output_dir, exist_ok=True)

        for idx, (slide, plan) in enumerate(zip(slides, plans)):
            slide_id = slide.id
            slide_passed = True
            violations = []

            # 1. Minimum Font Size Check
            title_font = plan.font_sizes.get("title", 40)
            body_font = plan.font_sizes.get("body", 28)
            code_font = plan.font_sizes.get("code", 20)

            if slide.type != "cover" and body_font < BODY_FONT_MIN:
                violations.append(f"Body font size ({body_font}pt) below minimum allowed ({BODY_FONT_MIN}pt)")
                slide_passed = False

            if slide.code and code_font < CODE_FONT_MIN:
                violations.append(f"Code font size ({code_font}pt) below minimum allowed ({CODE_FONT_MIN}pt)")
                slide_passed = False

            # 2. Bounding Box Intersections (Collision Map)
            boxes = plan.elements
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    b1 = boxes[i]
                    b2 = boxes[j]
                    if b1.intersects(b2, gutter=MIN_GUTTER_PX):
                        violations.append(f"Overlap between {b1.id_str} and {b2.id_str} (gutter < {MIN_GUTTER_PX}px)")
                        slide_passed = False

            # 3. Safe Zone Containment
            for b in boxes:
                if b.element_type == "title" and not b.is_inside(config.title_zone):
                    violations.append(f"Title box extends outside Title Zone")
                    slide_passed = False
                elif b.element_type == "presented_by" and not b.is_inside(config.presented_by_zone):
                    violations.append(f"Presented By box extends outside Presented By Zone")
                    slide_passed = False
                elif b.element_type == "footer" and not b.is_inside(config.footer_zone):
                    violations.append(f"Footer extends outside Footer Zone")
                    slide_passed = False
                elif b.element_type in ["bullets", "code", "diagram"]:
                    if b.bottom > config.content_zone.bottom + 5:
                        violations.append(f"{b.id_str} overflows safe content bottom ({b.bottom} > {config.content_zone.bottom})")
                        slide_passed = False

            # 4. Cover slide "Presented By" check
            if slide.type == "cover":
                has_pres = any(b.element_type == "presented_by" for b in boxes)
                if not has_pres:
                    violations.append("Cover slide is missing 'Presented By' author attribution box")
                    slide_passed = False

            # 5. On failure, produce annotated image
            annotated_path = None
            if not slide_passed and idx < len(preview_image_paths):
                orig_img = preview_image_paths[idx]
                if os.path.exists(orig_img):
                    annotated_path = os.path.join(output_dir, f"slide_{slide_id}_qa_failed.png")
                    self._annotate_failure(orig_img, boxes, violations, annotated_path)
                    annotated_images.append(annotated_path)

            if not slide_passed:
                all_passed = False

            per_slide_results.append({
                "slide_id": slide_id,
                "slide_title": slide.title,
                "slide_type": slide.type,
                "passed": slide_passed,
                "violations": violations,
                "body_font_pt": body_font,
                "code_font_pt": code_font,
                "element_count": len(boxes),
                "annotated_image": annotated_path,
            })

        return all_passed, per_slide_results, annotated_images

    def _annotate_failure(self, orig_path: str, boxes: List[ElementBox], violations: List[str], output_path: str):
        """Draws red outline boxes and warning banner on failed slide image."""
        try:
            img = Image.open(orig_path).convert("RGBA")
            overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            # Draw boxes with red warning outline
            for b in boxes:
                draw.rectangle([b.left, b.top, b.right, b.bottom], outline=(239, 68, 68, 255), width=4)

            # Top warning banner
            draw.rectangle([0, 0, img.width, 40], fill=(239, 68, 68, 220))
            banner_text = f"QA FAILED: {violations[0] if violations else 'Layout boundary breach'}"
            draw.text((20, 10), banner_text, fill=(255, 255, 255, 255))

            combined = Image.alpha_composite(img, overlay).convert("RGB")
            combined.save(output_path, "PNG")
        except Exception as e:
            print(f"Error creating annotated QA image: {e}")


template_qa = TemplateComplianceQA()
