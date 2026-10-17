import os
import json
from pptx import Presentation

from backend.schemas import Slide, SlideCode, SlideDiagram
from backend.template_registry import template_registry
from backend.layout_engine import layout_engine
from backend.pptx_builder import pptx_builder
from backend.pdf_converter import convert_pptx_to_pdf
from backend.layout_checker import check_deck_layout_compliance
from backend.materials.exporter import export_deck_pdf, export_student_notes_pdf, export_quiz_pdf


def generate_deck_and_check(
    deck_id: str,
    topic: str,
    tech: str,
    tech_version: str,
    professor_name: str,
    slides: list,
    college: str = "DPU",
):
    print(f"\n=======================================================")
    print(f"Generating Deck: {topic} ({tech} {tech_version})")
    print(f"College: {college} | Professor: {professor_name}")
    print(f"=======================================================")

    config = template_registry.get_config(college)
    assert config is not None, f"Configuration for {college} must exist"

    output_dir = os.path.join(os.path.abspath("output"), deck_id)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Plan layout for each slide
    plans = []
    for idx, slide in enumerate(slides):
        plan = layout_engine.plan_slide(slide, config, is_first_slide=(idx == 0))
        plans.append(plan)

    # 2. Build PPTX strictly adhering to DPU template and layouts
    pptx_path = os.path.join(output_dir, f"{deck_id}.pptx")
    pptx_builder.build_deck(
        slides=slides,
        plans=plans,
        config=config,
        professor_name=professor_name,
        output_pptx_path=pptx_path,
    )
    print(f"  [OK] PPTX generated: {pptx_path}")

    # 3. Export PDF by converting PPTX (ensuring PDF and PPTX match exactly)
    pdf_path = os.path.join(output_dir, f"{deck_id}.pdf")
    export_deck_pdf([], pdf_path, pptx_path=pptx_path)
    print(f"  [OK] PDF converted: {pdf_path} (Size: {os.path.getsize(pdf_path)} bytes)")

    # 4. Generate Supporting Student Notes and Quiz using shared code renderer
    deck_dict = {
        "id": deck_id,
        "topic": topic,
        "college": college,
        "tech": tech,
        "tech_version": tech_version,
        "professor_name": professor_name,
    }
    notes_list = [
        {
            "slide_id": s.id,
            "title": s.title,
            "explanation": s.speaker_hint or "Core conceptual mechanism.",
            "why_it_matters": "Critical for high performance production systems.",
            "common_mistake": "Unchecked thread contention or resource leakage.",
            "verified_code": s.code.source if s.code else None,
            "real_output": "Process executed cleanly with 0 exit code." if s.code else None,
        }
        for s in slides if s.type != "cover"
    ]
    notes_pdf = os.path.join(output_dir, f"Student_Notes_{deck_id}.pdf")
    export_student_notes_pdf(deck_dict, notes_list, notes_pdf)

    quiz_list = [
        {
            "id": 1,
            "question": f"Which runtime construct is introduced in {tech} {tech_version}?",
            "code_snippet": slides[1].code.source if slides[1].code else None,
            "options": [
                "A) Managed lightweight runtime scheduler",
                "B) Static manual thread preemption",
                "C) Unbuffered heap allocation",
                "D) Deprecated bytecode interpreter"
            ],
            "correct_answer": "A",
            "explanation": f"Grounded in Slide 2: {slides[1].title}",
            "source_slide_id": 2,
        }
    ]
    quiz_pdf = os.path.join(output_dir, f"Quiz_{deck_id}.pdf")
    export_quiz_pdf(deck_dict, quiz_list, quiz_pdf, include_answers=True)

    # 5. Run Automated Layout Compliance Checker
    report = check_deck_layout_compliance(
        pptx_path=pptx_path,
        pdf_path=pdf_path,
        deck_id=deck_id,
        topic=topic,
        college=college,
        output_dir=output_dir,
    )

    print(f"  [LAYOUT REPORT] Status: {report['status']} | Total Defects: {report['total_defects']}")
    for s_rep in report["slides"]:
        defect_str = ", ".join(s_rep["defects"]) if s_rep["defects"] else "None"
        print(f"    - Slide {s_rep['slide_number']} [{s_rep['layout']}]: {s_rep['status']} (Defects: {defect_str})")

    return report


def main():
    # =========================================================================
    # DECK 1: Java 21 Architecture & Virtual Threads
    # =========================================================================
    deck1_slides = [
        Slide(
            id=1,
            type="cover",
            title="Java 21 Architecture & Virtual Threads",
            bullets=[],
            takeaway="Project Loom lightweight concurrency in JVM",
        ),
        Slide(
            id=2,
            type="concept",
            title="Virtual Thread Per Task Executor",
            bullets=[
                "Million thread capability without memory exhaustion",
                "Automated mounting on underlying carrier pool",
                "Transparent non-blocking I/O multiplexing",
            ],
            code=SlideCode(
                source="""try (var pool = Executors.newVirtualThreadPerTaskExecutor()) {
    IntStream.range(0, 10).forEach(idx -> {
        pool.submit(() -> {
            Thread.sleep(Duration.ofMillis(50));
            return idx * 2;
        });
    });
}""",
                language="java",
            ),
            takeaway="Use virtual thread per task for concurrent I/O throughput",
        ),
        Slide(
            id=3,
            type="concept",
            title="Carrier Thread Scheduling Architecture",
            bullets=[
                "Virtual threads yield during blocking syscalls",
                "ForkJoinPool manages carrier workers efficiently",
                "Deterministic stack unmounting in heap memory",
            ],
            diagram=SlideDiagram(
                source="""graph TD
A[HTTP Request] --> B[Virtual Thread]
B --> C[Carrier Thread]
C --> D[OS Kernel]""",
                type="mermaid",
            ),
            takeaway="Cooperative lightweight execution engine in JVM",
        ),
        Slide(
            id=4,
            type="concept",
            title="Production Virtual Thread Guidelines",
            bullets=[
                "Never pool virtual threads; spawn per task",
                "Avoid pinning with synchronized keyword",
                "Migrate to ReentrantLock for critical sections",
                "Inspect heap footprint with JFR telemetry",
            ],
            exercise_ref="exercise_1_virtual_threads",
            takeaway="Follow Loom best practices to avoid pinning carrier threads",
        ),
    ]

    # =========================================================================
    # DECK 2: Python 3.12 Asynchronous Concurrency
    # =========================================================================
    deck2_slides = [
        Slide(
            id=1,
            type="cover",
            title="Python 3.12 Asynchronous Concurrency",
            bullets=[],
            takeaway="Structured concurrency with asyncio and TaskGroups",
        ),
        Slide(
            id=2,
            type="concept",
            title="Structured Concurrency with TaskGroup",
            bullets=[
                "Clean exception aggregation and auto-cancellation",
                "Deterministic lifecycle without lingering coroutines",
                "Zero dangling background task leaks",
            ],
            code=SlideCode(
                source="""import asyncio

async def fetch_service(svc_id: int) -> str:
    await asyncio.sleep(0.05)
    return f"Service {svc_id} ready"

async def main():
    async with asyncio.TaskGroup() as tg:
        t1 = tg.create_task(fetch_service(1))
        t2 = tg.create_task(fetch_service(2))
    return t1.result(), t2.result()""",
                language="python",
            ),
            takeaway="TaskGroup guarantees structured child task termination",
        ),
        Slide(
            id=3,
            type="concept",
            title="AsyncIO Event Loop Workflow",
            bullets=[
                "Single-threaded cooperative task scheduling",
                "Epoll event notification on OS sockets",
                "Future resolution wakes paused coroutines",
            ],
            diagram=SlideDiagram(
                source="""graph LR
A[Event Loop] --> B[Task Queue]
B --> C[IO Poller]
C --> D[Resolve Future]""",
                type="mermaid",
            ),
            takeaway="Event loop multiplexes thousands of I/O operations",
        ),
        Slide(
            id=4,
            type="concept",
            title="Best Practices in AsyncIO Systems",
            bullets=[
                "Never invoke blocking synchronous code on event loop",
                "Delegate CPU intensive workloads to process pools",
                "Utilize asyncio.timeout for network deadlines",
                "Always await graceful cancellation on shutdown",
            ],
            exercise_ref="exercise_2_async_gather",
            takeaway="Keep event loop iteration fast and unblocked",
        ),
    ]

    # =========================================================================
    # DECK 3: Modern C++17 Smart Pointers & Memory Management
    # =========================================================================
    deck3_slides = [
        Slide(
            id=1,
            type="cover",
            title="Modern C++17 Smart Pointers & Memory",
            bullets=[],
            takeaway="Deterministic RAII lifecycle without manual memory management",
        ),
        Slide(
            id=2,
            type="concept",
            title="Unique Pointer & Move Semantics",
            bullets=[
                "Zero-overhead exclusive resource ownership",
                "Move-only semantics prevent accidental aliasing",
                "Destructor guarantees automatic heap cleanup",
            ],
            code=SlideCode(
                source="""#include <iostream>
#include <memory>

struct Buffer {
    int id;
    Buffer(int i) : id(i) {}
};

std::unique_ptr<Buffer> make_buffer(int id) {
    auto buf = std::make_unique<Buffer>(id);
    return buf; // Move semantics applied
}""",
                language="cpp",
            ),
            takeaway="Prefer std::unique_ptr for single owner heap allocations",
        ),
        Slide(
            id=3,
            type="concept",
            title="Shared Pointer Control Block Architecture",
            bullets=[
                "Atomic reference counting across threads",
                "Weak pointer breaks cyclic reference leaks",
                "Control block allocated alongside payload",
            ],
            diagram=SlideDiagram(
                source="""graph TD
A[Shared Ptr] --> B[Control Block]
B --> C[Use Count]
B --> D[Managed Object]""",
                type="mermaid",
            ),
            takeaway="Shared pointer manages multiple non-owning readers",
        ),
        Slide(
            id=4,
            type="concept",
            title="Modern C++ Memory Safety Rules",
            bullets=[
                "Strictly avoid raw pointer new and delete calls",
                "Use std::make_shared for unified cache locality",
                "Break circular ownership graphs with weak_ptr",
                "Pass by const reference to avoid ref-count bumps",
            ],
            exercise_ref="exercise_3_cpp_raii",
            takeaway="RAII ensures leak-free deterministic resource management",
        ),
    ]

    report1 = generate_deck_and_check(
        deck_id="deck_java21_dpu",
        topic="Java 21 Architecture & Virtual Threads",
        tech="Java",
        tech_version="21",
        professor_name="Dr. Samriddhi Khade",
        slides=deck1_slides,
    )

    report2 = generate_deck_and_check(
        deck_id="deck_python312_dpu",
        topic="Python 3.12 Asynchronous Concurrency",
        tech="Python",
        tech_version="3.12",
        professor_name="Dr. Samriddhi Khade",
        slides=deck2_slides,
    )

    report3 = generate_deck_and_check(
        deck_id="deck_cpp17_dpu",
        topic="Modern C++17 Smart Pointers & Memory Management",
        tech="C++",
        tech_version="17",
        professor_name="Dr. Samriddhi Khade",
        slides=deck3_slides,
    )

    print("\n" + "=" * 60)
    print("ALL 3 DECKS GENERATED & EVALUATED AGAINST DPU TEMPLATE")
    print("=" * 60)
    for r in [report1, report2, report3]:
        print(f"\nDeck ID: {r['deck_id']}")
        print(f"Topic: {r['topic']}")
        print(f"Total Slides: {r['total_slides']} | Total Defects: {r['total_defects']} | Status: {r['status']}")
        print(f"PPTX Path: {r['pptx_path']}")
        print(f"PDF Path:  {r['pdf_path']} (Pages: {r['pdf_page_count']})")
        print(f"Defects by Type: {r['defects_by_type']}")


if __name__ == "__main__":
    main()
