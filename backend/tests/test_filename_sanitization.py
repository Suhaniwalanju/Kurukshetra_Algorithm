import os
import shutil
import pytest
from backend.utils import sanitize_filename
from backend.schemas import Slide, TemplateLayoutConfig
from backend.pptx_builder import pptx_builder, build_presentation
from backend.slide_renderer import render_deck_previews
from backend.layout_engine import layout_engine
from backend.template_registry import template_registry


def test_sanitize_filename_basic_and_forbidden_chars():
    # 1. Colon and ampersand
    res = sanitize_filename("Web Foundations: Responsive DOM Manipulation & CSS Grid")
    assert ":" not in res
    assert res == "Web_Foundations_Responsive_DOM_Manipulation_&_CSS_Grid"

    # 2. Slashes (common in tech names like HTML/CSS/JS or C/C++)
    assert sanitize_filename("HTML/CSS/JS") == "HTML_CSS_JS"
    assert sanitize_filename("C/C++") == "C_C++"

    # 3. Windows forbidden characters <>:"/\|?*
    nasty = '<bad>:"path"/\\with|all?*chars'
    sanitized = sanitize_filename(nasty)
    for char in '<>:"/\\|?*':
        assert char not in sanitized

    # 4. Reserved Windows device names
    assert sanitize_filename("CON") == "CON_safe"
    assert sanitize_filename("nul") == "nul_safe"
    assert sanitize_filename("COM1") == "COM1_safe"

    # 5. Empty or whitespace-only inputs
    assert sanitize_filename("") == "deck"
    assert sanitize_filename("   ...___   ") == "deck"

    # 6. Max length truncation
    long_name = "a" * 200
    assert len(sanitize_filename(long_name, max_length=50)) == 50


def test_pptx_builder_with_illegal_characters_in_path(tmp_path):
    config = list(template_registry.templates.values())[0] if template_registry.templates else None
    if not config:
        pytest.skip("No template configuration available.")

    slides = [
        Slide(
            id=1,
            type="concept",
            title="Web Foundations: Responsive DOM Manipulation & CSS Grid",
            bullets=["Bullet 1", "Bullet 2"]
        )
    ]
    plans = [layout_engine.plan_slide(slides[0], config, is_first_slide=True)]

    # Intentionally pass a path containing colon and slashes in the filename
    unsafe_filename = "Web_Foundations:_Responsive_DOM_Manipulation_&_CSS_Grid_HTML_CSS_JS.pptx"
    target_path = os.path.join(str(tmp_path), unsafe_filename)

    # Must build cleanly without raising WinError 267 or path errors
    result_path = pptx_builder.build_deck(
        slides=slides,
        plans=plans,
        config=config,
        professor_name="Prof Test",
        output_pptx_path=target_path
    )

    assert os.path.exists(result_path)
    assert ":" not in os.path.basename(result_path)


def test_build_presentation_with_colon_topic_and_slashed_tech():
    deck_dict = {
        "id": "test_sanitized_build",
        "college": "VIT",
        "professor_name": "Prof Smith",
        "topic": "Web Foundations: Responsive DOM Manipulation & CSS Grid",
        "tech": "HTML/CSS/JS",
        "slides": [
            {
                "id": 1,
                "title": "Introduction to DOM Manipulation",
                "bullets": ["Selectors", "Event Listeners"]
            }
        ]
    }

    pptx_path = build_presentation(deck_dict)
    assert os.path.exists(pptx_path)
    assert ":" not in os.path.basename(pptx_path)
    assert "/" not in os.path.basename(pptx_path)

    # Clean up test output directory
    out_dir = os.path.dirname(pptx_path)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)


def test_render_deck_preview_images_with_colon_topic_and_slashed_tech():
    deck_dict = {
        "id": "test_sanitized_previews",
        "college": "VIT",
        "professor_name": "Prof Smith",
        "topic": "Web Foundations: Responsive DOM Manipulation & CSS Grid",
        "tech": "HTML/CSS/JS",
        "slides": [
            {
                "id": 1,
                "title": "Introduction to DOM Manipulation",
                "bullets": ["Selectors", "Event Listeners"]
            }
        ]
    }

    preview_urls = render_deck_previews(deck_dict)
    assert len(preview_urls) == 1
    assert "test_sanitized_previews" in preview_urls[0]

    # Clean up test output directory
    out_dir = os.path.join(os.path.abspath("output"), "test_sanitized_previews")
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir, ignore_errors=True)
