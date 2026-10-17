import os
import json
import shutil
import zipfile
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from backend.database import DeckRecord, SubjectRecord, PublicationRecord, ExerciseProofRecord

PUBLISHED_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "published"))


def get_file_extension_for_tech(tech: str) -> str:
    t = (tech or "").lower()
    if "python" in t or "py" in t:
        return "py"
    if "java" in t:
        return "java"
    if "c++" in t or "cpp" in t:
        return "cpp"
    if "c" == t:
        return "c"
    if "node" in t or "javascript" in t or "js" in t or "react" in t:
        return "js"
    if "sql" in t or "postgres" in t:
        return "sql"
    return "txt"


def safe_rmtree(path: str, max_retries: int = 5, delay: float = 0.2):
    import time
    import stat
    if not os.path.exists(path):
        return

    def on_error(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for attempt in range(max_retries):
        try:
            shutil.rmtree(path, onerror=on_error)
            return
        except Exception:
            if attempt == max_retries - 1:
                # Fallback: remove files one-by-one
                for root, dirs, files in os.walk(path, topdown=False):
                    for f in files:
                        try:
                            fp = os.path.join(root, f)
                            os.chmod(fp, stat.S_IWRITE)
                            os.remove(fp)
                        except Exception:
                            pass
                    for d in dirs:
                        try:
                            os.rmdir(os.path.join(root, d))
                        except Exception:
                            pass
            time.sleep(delay)


def publish_deck_for_subject(
    deck_id: str,
    subject_id: str,
    include_slides: bool,
    trainer_id: str,
    institute_id: str,
    db: Session,
) -> PublicationRecord:
    """
    Creates or updates the published folder for a subject:
      <subject>/
        notes/       student-friendly notes (notes.md, notes.pdf)
        quiz/        questions and options ONLY (no answers, no explanations)
        exercises/   exercise_01..N with task.md, starter code, tests ONLY
        slides/      deck PDF (if include_slides is True)
    Guarantees no solutions, naive code, or proof reports are published.
    """
    deck = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not deck:
        raise ValueError(f"Deck '{deck_id}' not found.")

    subject = db.query(SubjectRecord).filter(
        SubjectRecord.id == subject_id,
        SubjectRecord.institute_id == institute_id,
    ).first()
    if not subject:
        raise ValueError(f"Subject '{subject_id}' not found for institute '{institute_id}'.")

    # 1. Determine publication version
    existing_pubs = db.query(PublicationRecord).filter(
        PublicationRecord.subject_id == subject_id,
        PublicationRecord.institute_id == institute_id,
    ).all()
    next_version = max([p.version for p in existing_pubs], default=0) + 1

    # Mark existing active publications as unpublished (archived in history)
    for p in existing_pubs:
        if p.status == "published":
            p.status = "unpublished"
    db.commit()


    # 2. Setup directory structure under storage/published/<institute_id>/<folder_slug>/
    target_dir = os.path.join(PUBLISHED_BASE_DIR, institute_id, subject.folder_slug)
    safe_rmtree(target_dir)
    os.makedirs(target_dir, exist_ok=True)

    notes_dir = os.path.join(target_dir, "notes")
    quiz_dir = os.path.join(target_dir, "quiz")
    exercises_dir = os.path.join(target_dir, "exercises")
    slides_dir = os.path.join(target_dir, "slides")

    os.makedirs(notes_dir, exist_ok=True)
    os.makedirs(quiz_dir, exist_ok=True)
    os.makedirs(exercises_dir, exist_ok=True)
    os.makedirs(slides_dir, exist_ok=True)

    # 3. Publish Notes (Student-Friendly Version)
    notes_md_path = os.path.join(notes_dir, "notes.md")
    notes_content = []
    notes_content.append(f"# {subject.name} - Student Course Notes\n")
    notes_content.append(f"**Topic:** {deck.topic}  \n**Technology:** {deck.tech} {deck.tech_version}  \n**Level:** {deck.student_level}\n\n---\n")

    student_notes = []
    if deck.student_notes_json:
        try:
            student_notes = json.loads(deck.student_notes_json)
        except Exception:
            student_notes = []

    if student_notes:
        for idx, sn in enumerate(student_notes, 1):
            if isinstance(sn, dict):
                title = sn.get("title") or f"Section {idx}"
                bullets = sn.get("bullets", [])
                notes_content.append(f"### {idx}. {title}\n")
                if bullets:
                    for b in bullets:
                        notes_content.append(f"- {b}")
                    notes_content.append("")
                if sn.get("code"):
                    notes_content.append(f"```{get_file_extension_for_tech(deck.tech)}\n{sn['code']}\n```\n")
            elif isinstance(sn, str):
                notes_content.append(f"{sn}\n")
    else:
        # Fallback from slides summary
        slides = json.loads(deck.slides_json) if deck.slides_json else []
        for s in slides:
            notes_content.append(f"### {s.get('title', 'Slide')}\n")
            for b in s.get("bullets", []):
                notes_content.append(f"- {b}")
            notes_content.append("")

    with open(notes_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(notes_content))

    # Copy notes PDF if generated
    if deck.output_dir:
        for cand in [
            os.path.join(deck.output_dir, f"Student_Notes_{deck.id}.pdf"),
            os.path.join(deck.output_dir, "student_notes.pdf"),
            os.path.join(deck.output_dir, "notes.pdf"),
        ]:
            if os.path.exists(cand):
                shutil.copy2(cand, os.path.join(notes_dir, "notes.pdf"))
                break

    # If no PDF was copied, write notes.pdf dummy or placeholder
    if not os.path.exists(os.path.join(notes_dir, "notes.pdf")):
        with open(os.path.join(notes_dir, "notes.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 Notes Document Placeholder")

    # 4. Publish Quiz (Questions and Options ONLY, NO ANSWERS, NO EXPLANATIONS)
    raw_quiz = []
    if deck.quiz_json:
        try:
            raw_quiz = json.loads(deck.quiz_json)
        except Exception:
            raw_quiz = []

    student_quiz = []
    for idx, q in enumerate(raw_quiz, 1):
        if not isinstance(q, dict):
            continue
        q_item = {
            "id": q.get("id") or f"q_{idx}",
            "number": idx,
            "question": q.get("question") or q.get("prompt") or f"Question {idx}",
            "options": q.get("options") or q.get("choices") or [],
            "code_snippet": q.get("code_snippet") or q.get("code") or "",
        }
        # EXPLICIT SAFETY: Never include answers or explanations in published file
        for forbidden in ["correct_answer", "answer", "correct_option", "explanation", "rationale", "solution"]:
            q_item.pop(forbidden, None)
        student_quiz.append(q_item)

    quiz_json_path = os.path.join(quiz_dir, "quiz.json")
    with open(quiz_json_path, "w", encoding="utf-8") as f:
        json.dump(student_quiz, f, indent=2)

    # 5. Publish Exercises (Task, Starter, and Tests ONLY, NO SOLUTIONS)
    ext = get_file_extension_for_tech(deck.tech)
    proof_records = db.query(ExerciseProofRecord).filter(ExerciseProofRecord.deck_id == deck_id).all()

    exercise_folders = []
    if proof_records:
        for idx, rec in enumerate(proof_records, 1):
            ex_folder = os.path.join(exercises_dir, f"exercise_{idx:02d}")
            os.makedirs(ex_folder, exist_ok=True)
            exercise_folders.append(ex_folder)

            # 1. task.md
            task_md = (
                f"# Exercise {idx}: {rec.title or f'Practice Problem {idx}'}\n\n"
                f"**Difficulty:** {rec.difficulty.capitalize()}  \n"
                f"**Estimated Time:** {rec.estimated_minutes} minutes  \n\n"
                f"## Problem Statement\n{rec.problem_statement or 'Implement the required function or method according to the unit tests.'}\n\n"
                f"## Instructions\n"
                f"1. Open the starter code file.\n"
                f"2. Implement the missing logic indicated by the TODO comments.\n"
                f"3. Run the provided tests to verify your solution!\n"
            )
            with open(os.path.join(ex_folder, "task.md"), "w", encoding="utf-8") as tf:
                tf.write(task_md)

            # 2. Starter code (contains TODO, NO reference solution)
            starter_name = f"Exercise_{idx}.{ext}" if ext == "java" else f"starter.{ext}"
            starter_code = rec.starter_code or f"// TODO: Implement solution\n"
            with open(os.path.join(ex_folder, starter_name), "w", encoding="utf-8") as sf:
                sf.write(starter_code)

            # 3. Unit test file
            test_name = f"ExerciseTest_{idx}.{ext}" if ext == "java" else f"test_exercise.{ext}"
            test_code = rec.test_code or f"// Test assertions\n"
            with open(os.path.join(ex_folder, test_name), "w", encoding="utf-8") as tstf:
                tstf.write(test_code)

    # Create downloadable exercises.zip containing all student exercises
    zip_path = os.path.join(exercises_dir, "exercises.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(exercises_dir):
            for file in files:
                if file == "exercises.zip":
                    continue
                full_p = os.path.join(root, file)
                rel_p = os.path.relpath(full_p, exercises_dir)
                zf.write(full_p, rel_p)

    # 6. Publish Slides (Deck PDF if requested)
    if include_slides:
        pdf_source = deck.pdf_path
        if not pdf_source or not os.path.exists(pdf_source):
            if deck.output_dir:
                cand = os.path.join(deck.output_dir, f"Deck_{deck.id}.pdf")
                if os.path.exists(cand):
                    pdf_source = cand
        if pdf_source and os.path.exists(pdf_source):
            shutil.copy2(pdf_source, os.path.join(slides_dir, "deck.pdf"))
        else:
            # Create a simple placeholder PDF if slides requested but not compiled
            with open(os.path.join(slides_dir, "deck.pdf"), "wb") as f:
                f.write(b"%PDF-1.4 Slides Document Placeholder")

    # 7. Create Publication DB Record
    publication = PublicationRecord(
        id=f"pub_{uuid.uuid4().hex[:8]}",
        institute_id=institute_id,
        subject_id=subject_id,
        deck_id=deck_id,
        trainer_id=trainer_id,
        version=next_version,
        published_at=datetime.utcnow(),
        status="published",
        include_slides=include_slides,
        published_path=target_dir,
    )
    db.add(publication)
    db.commit()
    db.refresh(publication)

    return publication


def verify_no_solutions_in_published(published_path: str) -> bool:
    """
    Scans the published folder and verifies:
    - NO reference solutions
    - NO naive solutions
    - NO quiz correct answers or explanations
    - NO proof reports or mutation results
    Returns True if clean, raises AssertionError if any forbidden content is found.
    """
    forbidden_terms = [
        "reference_solution",
        "naive_solution",
        "proof_report",
        "mutation_score",
        "correct_answer",
        "answer_key",
        "reference_passed",
        "failing_test_name",
    ]

    for root, _, files in os.walk(published_path):
        for f in files:
            if f.endswith(".zip"):
                continue
            lower_name = f.lower()
            if "reference" in lower_name or "naive" in lower_name or "proof" in lower_name:
                raise AssertionError(f"Forbidden file found in published directory: {f}")

            # Check file content
            f_path = os.path.join(root, f)
            try:
                with open(f_path, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read().lower()
                    for term in forbidden_terms:
                        if term in content:
                            raise AssertionError(f"Forbidden instructor-only content '{term}' detected in published file: {f}")
            except Exception as e:
                if isinstance(e, AssertionError):
                    raise e
    return True
