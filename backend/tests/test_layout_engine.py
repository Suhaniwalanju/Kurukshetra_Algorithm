import pytest
from backend.schemas import (
    Slide,
    SlideCode,
    SlideDiagram,
    BoundingBox,
    TemplateLayoutConfig,
    TemplateColors,
    TemplateFonts,
    DeckCreateRequest,
)
from backend.layout_engine import (
    layout_engine,
    MIN_GUTTER_PX,
    ElementBox,
    BODY_FONT_MIN,
    CODE_FONT_MIN,
)
from backend.template_registry import template_registry
from backend.slide_renderer import slide_renderer
from backend.topic_validator import is_coding_topic


@pytest.fixture
def mock_template_config():
    return TemplateLayoutConfig(
        college="VIT",
        slide_width=1920,
        slide_height=1080,
        aspect_ratio="16:9",
        template_image_path="input/templates/VIT/VIT_Brand_template.png",
        title_zone=BoundingBox(left=200, top=140, width=1520, height=100),
        content_zone=BoundingBox(left=200, top=260, width=1520, height=680),
        code_zone=BoundingBox(left=200, top=260, width=740, height=680),
        diagram_zone=BoundingBox(left=980, top=260, width=740, height=680),
        footer_zone=BoundingBox(left=200, top=960, width=1520, height=45),
        presented_by_zone=BoundingBox(left=250, top=860, width=1420, height=80),
        colors=TemplateColors(),
        fonts=TemplateFonts(),
    )


def test_topic_validation_rejects_non_coding():
    # Non-coding topics should be rejected with friendly message
    valid, msg = is_coding_topic("French Literature and Poetry", "Humanities")
    assert not valid
    assert "French" in msg or "coding" in msg

    valid, msg = is_coding_topic("Baking Croissants and Pastries", "Cooking")
    assert not valid
    assert "cooking" in msg.lower() or "coding" in msg.lower()

    # Coding topics should pass
    valid, msg = is_coding_topic("Java 21 Virtual Threads & Concurrency", "Java 21")
    assert valid
    assert msg == ""

    valid, msg = is_coding_topic("Spring Boot 3 RESTful Microservices", "Spring Boot")
    assert valid


def test_bullet_constraints():
    # Maximum 5 bullets, maximum 8 words per bullet
    slide = Slide(
        id=1,
        type="concept",
        title="Java 21 Virtual Threads",
        bullets=[
            "High throughput lightweight threads for concurrency",
            "Managed by the Java runtime natively",
            "Eliminates OS thread allocation bottleneck",
            "Drop-in replacement for traditional thread pool",
            "Massive scalability for IO operations",
        ],
    )
    assert len(slide.bullets) <= 5
    for b in slide.bullets:
        assert len(b.split()) <= 8


def test_element_box_intersection_and_gutter():
    box1 = ElementBox("box1", left=100, top=100, width=200, height=100)
    # Box2 is separated by less than MIN_GUTTER_PX -> should intersect
    box2 = ElementBox("box2", left=100, top=210, width=200, height=100)
    assert box1.intersects(box2, gutter=MIN_GUTTER_PX)

    # Box3 is separated by more than MIN_GUTTER_PX -> no intersection
    box3 = ElementBox("box3", left=100, top=100 + 100 + MIN_GUTTER_PX + 5, width=200, height=100)
    assert not box1.intersects(box3, gutter=MIN_GUTTER_PX)


def test_presented_by_on_cover_and_closing(mock_template_config):
    cover_slide = Slide(
        id=1,
        type="cover",
        title="Modern Java 21 Concurrency",
        bullets=["Presented By Dr. Alan Turing", "Department of Computer Science"],
    )
    plan = layout_engine.layout_single_slide(cover_slide, mock_template_config, "Dr. Alan Turing")
    
    # Check that presented_by element exists on cover slide
    pres_elements = [e for e in plan.elements if e.element_type == "presented_by"]
    assert len(pres_elements) == 1
    pres_box = pres_elements[0]
    # Check it is inside presented_by_zone
    assert pres_box.is_inside(mock_template_config.presented_by_zone)
    assert len(plan.violations) == 0

    # Verify that closing slide does NOT duplicate presented_by
    closing_slide = Slide(
        id=2,
        type="closing",
        title="Thank You & Questions",
        bullets=["Q&A Session", "Lab Repository"],
    )
    closing_plan = layout_engine.layout_single_slide(closing_slide, mock_template_config, "Dr. Alan Turing")
    assert not any(e.element_type == "presented_by" for e in closing_plan.elements)


def test_slide_auto_splitting_on_overflow(mock_template_config):
    # Construct a heavily loaded slide with 5 long bullets and a large code block
    huge_slide = Slide(
        id=3,
        type="concept",
        title="Advanced Memory and Garbage Collection",
        bullets=[
            "ZGC generational garbage collection architecture",
            "Ultra low pause times below one millisecond",
            "Colored pointers and load barrier tracking",
            "Dynamic memory region sizing and compaction",
            "Scale heap memory up to sixteen terabytes",
        ],
        code=SlideCode(
            language="java",
            version="21",
            source="\n".join([f"// Line {i}: complex GC operation and memory allocation" for i in range(12)]),
            expected_output="Heap allocated: 16GB",
        ),
    )

    slides = [huge_slide]
    final_slides, plans, logs = layout_engine.layout_deck(slides, mock_template_config, "Prof. Sharma")
    
    # After layout, check that automated check reports zero violations
    passed, issues = slide_renderer.run_automated_check(final_slides, plans)
    assert passed, f"Violations found: {issues}"


def test_java_21_sample_deck_zero_violations(mock_template_config):
    # Acceptance Criteria: Zero overlaps/overflow in the automated check on a Java 21 sample deck
    slides = [
        Slide(
            id=1,
            type="cover",
            title="Java 21 Features",
            bullets=["Presented By Prof. Khade", "Subject: Java 21", "Level: Advanced"],
        ),
        Slide(
            id=2,
            type="agenda",
            title="Today's Lecture Agenda",
            bullets=[
                "Virtual Threads Architecture",
                "Sequenced Collections API",
                "Record Patterns & Matching",
                "Hands-on Coding Lab",
                "Summary & Review",
            ],
        ),
        Slide(
            id=3,
            type="concept",
            title="Virtual Threads in Java",
            bullets=[
                "Lightweight threads managed by JVM",
                "Millions of concurrent tasks possible",
                "Preserves synchronous programming style",
                "High performance IO throughput",
            ],
            code=SlideCode(
                language="java",
                version="21",
                source=(
                    "try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {\n"
                    "    IntStream.range(0, 10_000).forEach(i -> {\n"
                    "        executor.submit(() -> {\n"
                    "            Thread.sleep(Duration.ofSeconds(1));\n"
                    "            return i;\n"
                    "        });\n"
                    "    });\n"
                    "}"
                ),
                expected_output="Execution completed in 1.02s",
            ),
        ),
        Slide(
            id=4,
            type="closing",
            title="Thank You & Questions",
            bullets=["Presented By Prof. Khade", "VIT Computer Engineering", "Next Lab: Friday 10 AM"],
        ),
    ]

    final_slides, plans, logs = layout_engine.layout_deck(slides, mock_template_config, "Prof. Khade")
    passed, issues = slide_renderer.run_automated_check(final_slides, plans)
    assert passed, f"Acceptance check failed on Java 21 deck: {issues}"
    assert len(issues) == 0
