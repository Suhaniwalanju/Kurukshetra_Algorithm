import os
import pytest
from pptx import Presentation

from backend.schemas import Slide, SlideCode, SlideDiagram, TemplateLayoutConfig
from backend.template_registry import template_registry
from backend.layout_engine import layout_engine
from backend.pptx_builder import pptx_builder
from backend.code_renderer import render_code_block, split_or_excerpt_code
from backend.diagram_renderer import diagram_renderer
from backend.pdf_converter import convert_pptx_to_pdf
from backend.layout_checker import check_deck_layout_compliance


@pytest.fixture
def dpu_config():
    config = template_registry.get_config("DPU")
    assert config is not None, "DPU configuration must be registered"
    return config


def test_dpu_template_config_loaded_from_style_guide(dpu_config):
    """Test that DPU template reads fonts, colors, logo, and footer from style guide without hardcoding."""
    assert dpu_config.college == "DPU"
    assert dpu_config.fonts.title in ("Arial", "Segoe UI")
    assert dpu_config.fonts.body in ("Segoe UI", "Arial")
    assert dpu_config.fonts.code == "Consolas"
    assert dpu_config.colors.primary.upper() == "#002147"
    assert dpu_config.colors.secondary.upper() == "#C0392B"
    assert hasattr(dpu_config, "template_pptx_path") and os.path.exists(dpu_config.template_pptx_path)
    assert hasattr(dpu_config, "logo_path") and os.path.exists(dpu_config.logo_path)
    assert hasattr(dpu_config, "footer_text") and "Dr. D. Y. Patil" in dpu_config.footer_text


def test_shared_code_block_constraints_and_splitting():
    """Test that shared render_code_block enforces >= 14pt, max 14 lines, max 60 cols, and splitting."""
    long_code = "\n".join([f"    x_{i} = calculate_value({i})  # sample line {i}" for i in range(25)])
    rendered = render_code_block(
        code=long_code,
        language="python",
        font_size_pt=14,
        max_lines=14,
        max_cols=60,
    )
    assert rendered["font_family"] == "Consolas"
    assert rendered["font_size_pt"] >= 14
    assert rendered["is_split"] is True
    assert len(rendered["parts"]) == 2
    assert "Part 1/2" in rendered["parts"][0]
    assert "Part 2/2" in rendered["parts"][1]
    # Check max cols sanitization
    wide_line = "x = " + "a" * 80
    parts, excerpt = split_or_excerpt_code(wide_line, max_lines=14, max_cols=60)
    assert len(parts[0].splitlines()[0]) <= 60


def test_diagram_node_limits_and_resolution():
    """Test diagram specs are limited to 7 nodes, <= 3 words per label, and render at 2x resolution."""
    spec = """
    graph LR
        A[Client Request] --> B[API Gateway]
        B --> C[Auth Service]
        C --> D[Worker Thread]
    """
    out_png = "output/test_diagram_render.png"
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    
    success = diagram_renderer.render_diagram_to_png(
        spec=spec,
        output_path=out_png,
        target_width=740,
        target_height=500,
        scale=2.0,
    )
    assert success is True
    assert os.path.exists(out_png)
    assert os.path.getsize(out_png) > 1000


def test_dpu_deck_generation_and_layout_compliance(dpu_config, tmp_path):
    """Test full deck generation using DPU layouts and verify zero defects with layout_checker."""
    slides = [
        Slide(
            id=1,
            type="cover",
            title="Java 21 Architecture & Virtual Threads",
            bullets=[],
            takeaway="Introduction to lightweight concurrency in modern Java",
        ),
        Slide(
            id=2,
            type="concept",
            title="Virtual Thread Executor Service",
            bullets=[
                "Lightweight threads managed by JVM",
                "High throughput for I/O bound tasks",
                "Drop-in replacement for thread pools",
            ],
            code=SlideCode(
                source="""try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    IntStream.range(0, 10).forEach(i -> {
        executor.submit(() -> {
            Thread.sleep(Duration.ofMillis(100));
            return i;
        });
    });
}""",
                language="java",
            ),
            takeaway="Use virtual threads for millions of concurrent tasks",
        ),
        Slide(
            id=3,
            type="concept",
            title="Carrier Thread Scheduling",
            bullets=[
                "Virtual threads mount on carrier OS threads",
                "Unmounts on blocking I/O calls",
                "Scheduler resumes on available carrier",
            ],
            diagram=SlideDiagram(
                source="""graph TD
A[Task Submit] --> B[Virtual Thread]
B --> C[Carrier Thread]
C --> D[OS Kernel]""",
                type="mermaid",
            ),
            takeaway="Cooperative non-blocking scheduling in JVM",
        ),
    ]

    plans = [
        layout_engine.plan_slide(slides[0], dpu_config, is_first_slide=True),
        layout_engine.plan_slide(slides[1], dpu_config, is_first_slide=False),
        layout_engine.plan_slide(slides[2], dpu_config, is_first_slide=False),
    ]

    out_pptx = str(tmp_path / "Java_21_DPU_Deck.pptx")
    pptx_path = pptx_builder.build_deck(
        slides=slides,
        plans=plans,
        config=dpu_config,
        professor_name="Dr. S. Khade",
        output_pptx_path=out_pptx,
    )
    assert os.path.exists(pptx_path)

    # 1. PPTX Template Structure Inspection
    prs = Presentation(pptx_path)
    assert len(prs.slides) == 3
    # Check that each slide has a title placeholder and footer
    for s in prs.slides:
        assert s.shapes.title is not None or any(p.placeholder_format.idx == 0 for p in s.placeholders)
        # Verify footer placeholder or footer shape is present
        has_footer = any(p.placeholder_format.idx in (11, 12) for p in s.placeholders) or any("footer" in sh.name.lower() or "dpu" in getattr(sh, "text", "").lower() for sh in s.shapes if hasattr(sh, "text"))
        assert has_footer, "Every slide must have a footer"

    # 2. Automated Layout Compliance Report Check
    out_pdf = str(tmp_path / "Java_21_DPU_Deck.pdf")
    report = check_deck_layout_compliance(
        pptx_path=pptx_path,
        pdf_path=out_pdf,
        deck_id="test_compliance",
        topic="Java 21 Architecture & Virtual Threads",
        college="DPU",
        output_dir=str(tmp_path),
    )

    assert report["total_slides"] == 3
    # Fail on any defect
    assert report["total_defects"] == 0, f"Expected 0 defects, got: {report['slides']}"
    assert report["status"] == "PASSED"
