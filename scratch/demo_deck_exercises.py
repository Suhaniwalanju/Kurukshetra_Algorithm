import os
import sys
import json
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import init_db, SessionLocal, DeckRecord
from backend.verification.exercise_prover import exercise_prover
from backend.materials.exporter import build_all_deck_exports

def main():
    init_db()
    db = SessionLocal()

    deck_id = "demo_deck_exercises"
    topic = "Python List Comprehensions & Advanced Data Filtering"
    tech = "Python"
    tech_version = "3.12"

    print("=" * 80)
    print(f"GENERATING DECK AND HANDS-ON EXERCISES FOR TOPIC: {topic}")
    print("=" * 80)

    # 1. Mock Slides representing the generated PPT
    slides = [
        {
            "id": 1,
            "title": "Introduction to Python List Comprehensions",
            "type": "concept",
            "content": ["Basic syntax: [expr for item in iterable]", "Inline filtering with if condition", "Avoiding nested loop verbosity"],
            "trainer_notes": "Emphasize readable element filtering without mutative append loops.",
        },
        {
            "id": 2,
            "title": "Conditional Filtering & Predicate Logic",
            "type": "code",
            "content": ["Strict positive filters (> 0)", "Handling mixed negative and zero values", "Zero overhead comprehension bytecode"],
            "trainer_notes": "Show how filter predicates reject zero and negative integers.",
        },
        {
            "id": 3,
            "title": "Aggregations & Adjacent Window Computations",
            "type": "concept",
            "content": ["Pairwise summation across contiguous elements", "Handling edge cases where len < 2", "Optimal memory footprint"],
            "trainer_notes": "Discuss boundary checks when computing adjacent pairs.",
        },
        {
            "id": 4,
            "title": "Hands-On Lab: Performance Optimization",
            "type": "exercise",
            "content": ["Implement high performance filtering", "Prove unit tests against student mistakes"],
            "trainer_notes": "Students frequently make off-by-one errors or return length instead of filtered count.",
        }
    ]

    # Clean existing record if any
    existing = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if existing:
        db.delete(existing)
        db.commit()

    deck = DeckRecord(
        id=deck_id,
        college="DPU",
        professor_name="Prof. Sharma",
        topic=topic,
        student_level="intermediate",
        session_length=45,
        tech=tech,
        tech_version=tech_version,
        status="completed",
        status_message="Deck generated successfully",
        slides_json=json.dumps(slides),
    )
    db.add(deck)
    db.commit()

    # 2. Run Exercise Prover
    print("\n--- 1. Proving Hands-On Exercises in Sandbox ---")
    proofs = exercise_prover.prove_deck_exercises(
        deck_id=deck_id,
        topic=topic,
        language=tech,
        version=tech_version,
        slides=slides,
        student_level="intermediate",
        max_attempts=3,
        db_session=db,
    )

    print(f"Generated and proven: {len(proofs)} exercises\n")

    # 3. Print Exercise List
    print("=" * 80)
    print("EXERCISE LIST (GENERATED & PROVEN)")
    print("=" * 80)
    for idx, p in enumerate(proofs):
        print(f"[{idx + 1}] Title:             {p.title}")
        print(f"    Difficulty:        {p.difficulty.upper()}")
        print(f"    Estimated Time:    {p.estimated_minutes} minutes")
        print(f"    Source Slides:     Slides {p.source_slides}")
        print(f"    Verification:      {p.status.upper()} (Ref Passed: {p.reference_passed}, Naive Caught: {p.naive_failed})")
        print(f"    Failing Test Name: {p.failing_test_name}")
        print(f"    Mutation Score:    {p.mutation_score}%")
        print(f"    Model Used:        {p.model_used}")
        print(f"    Attempts:          {p.attempts}")
        print(f"    Commands Run:      {len(p.commands_run)} execution commands")
        print("    --- Task Preview ---")
        task_preview = (p.problem_statement or p.starter_code)[:200].replace('\n', ' ')
        print(f"    {task_preview}...")
        print("-" * 80)

    # 4. Build Export All Zip
    print("\n--- 2. Building Export All ZIP Package ---")
    exports = build_all_deck_exports(deck_id, db)
    all_zip = exports["all_zip"]
    print(f"Export All ZIP Path: {all_zip}\n")

    # 5. Display Folder Tree of Exported ZIP
    print("=" * 80)
    print("FOLDER TREE OF EXPORTED ZIP (All_Materials.zip)")
    print("=" * 80)
    with zipfile.ZipFile(all_zip, 'r') as z:
        namelist = sorted(z.namelist())
        for name in namelist:
            print(f"- {name} ({z.getinfo(name).file_size} bytes)")
    print("=" * 80)

if __name__ == "__main__":
    main()
