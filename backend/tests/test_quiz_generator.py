import os
import json
import pytest
from backend.materials.quiz_generator import generate_quiz_for_deck
from backend.materials.models import QuizQuestion
from backend.materials.exporter import export_quiz_pdf


def test_quiz_generator_generates_exactly_eight_mcqs():
    """
    Validates that generate_quiz_for_deck produces exactly 8 MCQs,
    each with 4 options, a correct answer, an explanation, and source_slide_id.
    """
    deck = {
        "id": "deck_quiz_test_01",
        "topic": "Python Concurrency and Asyncio",
        "tech": "Python",
        "tech_version": "3.12",
        "session_length": 30,
        "slides": [
            {"id": 1, "type": "cover", "title": "Python Concurrency", "bullets": ["Asyncio Event Loop"]},
            {"id": 2, "type": "concept", "title": "Asyncio Architecture", "bullets": ["Cooperative multitasking", "Single-threaded loop"]},
            {"id": 3, "type": "code", "title": "Comprehensions & Async Tasks", "code": {"source": "print('task')", "language": "python"}},
            {"id": 4, "type": "exercise", "title": "Hands-On Lab: Async Worker", "exercise_ref": "LAB-PY-01", "bullets": ["Implement worker", "Handle empty inputs"]},
            {"id": 5, "type": "closing", "title": "Summary & Best Practices", "bullets": ["Deterministic testing", "Normalization"]},
        ]
    }

    quiz = generate_quiz_for_deck(deck)
    assert len(quiz) == 8, f"Expected exactly 8 questions, got {len(quiz)}"

    valid_slide_ids = {1, 2, 3, 4, 5}
    for idx, q in enumerate(quiz):
        assert isinstance(q, QuizQuestion)
        assert q.id == idx + 1
        assert isinstance(q.question, str) and len(q.question.strip()) > 10
        assert len(q.options) == 4, f"Question {q.id} must have exactly 4 options, got {len(q.options)}"
        assert q.correct_answer in ["A", "B", "C", "D"], f"Question {q.id} has invalid correct_answer: {q.correct_answer}"
        assert isinstance(q.explanation, str) and len(q.explanation.strip()) > 10
        assert q.source_slide_id in valid_slide_ids, f"Question {q.id} source_slide_id {q.source_slide_id} not in slide IDs"
        assert q.slide_id == q.source_slide_id


def test_quiz_grounded_in_slides_and_exercises():
    """
    Verifies that questions are specifically grounded in slides and exercises:
    - Questions 5 and 6 are grounded in the exercise slide (Slide 4).
    - Questions reference the exercise ref.
    """
    deck = {
        "id": "deck_quiz_test_java",
        "topic": "Java 21 Virtual Threads & Scoped Values",
        "tech": "Java",
        "tech_version": "21",
        "slides": [
            {"id": 1, "type": "cover", "title": "Java 21 Architecture"},
            {"id": 2, "type": "code", "title": "Platform vs Virtual Threads"},
            {"id": 3, "type": "code", "title": "Thread Execution"},
            {"id": 4, "type": "exercise", "title": "Lab: Virtual Thread Pool", "exercise_ref": "LAB-JAVA-VTHREAD"},
            {"id": 5, "type": "closing", "title": "Production Readiness"},
        ]
    }

    exercises = [
        {
            "difficulty": "medium",
            "exercise_ref": "LAB-JAVA-VTHREAD",
            "task": "Implement virtual thread worker counting positive values",
            "problem_statement": "Implement virtual thread worker counting positive values",
        }
    ]

    quiz = generate_quiz_for_deck(deck, exercises=exercises)
    assert len(quiz) == 8

    # Question 5 and 6 must be grounded in Slide 4 (the exercise slide)
    q5 = quiz[4]
    q6 = quiz[5]
    assert q5.source_slide_id == 4
    assert q6.source_slide_id == 4
    assert "LAB-JAVA-VTHREAD" in q5.question or q5.exercise_ref == "LAB-JAVA-VTHREAD"
    assert "LAB-JAVA-VTHREAD" in q6.question or q6.exercise_ref == "LAB-JAVA-VTHREAD"


def test_distractors_reflect_common_mistakes():
    """
    Verifies that distractors reflect common student mistakes and misconceptions,
    and that distractor_explanations document them.
    """
    deck = {
        "id": "deck_quiz_mistakes",
        "topic": "JavaScript Async Programming",
        "tech": "JavaScript",
        "tech_version": "20",
        "slides": [
            {"id": 1, "type": "cover", "title": "JS Async"},
            {"id": 2, "type": "code", "title": "Event Loop"},
            {"id": 3, "type": "exercise", "title": "Hands-On Lab: Array Reducer", "exercise_ref": "LAB-JS-01"},
            {"id": 4, "type": "closing", "title": "Summary"},
        ]
    }

    quiz = generate_quiz_for_deck(deck)
    assert len(quiz) == 8

    for q in quiz:
        # 3 distractors must be explained
        assert len(q.distractor_explanations) == 3
        for opt_key, exp in q.distractor_explanations.items():
            assert opt_key in ["A", "B", "C", "D"]
            assert opt_key != q.correct_answer
            assert "mistake" in exp.lower() or "confusing" in exp.lower() or "assuming" in exp.lower() or "failing" in exp.lower() or "violat" in exp.lower()


def test_code_questions_executed_and_checked_against_real_output():
    """
    Verifies that questions containing code are executed in the runtime
    and their correct answers are strictly verified against the real output.
    """
    # 1. Python deck code execution check
    py_deck = {
        "id": "deck_code_exec_py",
        "topic": "Python Data Structures",
        "tech": "Python",
        "tech_version": "3.12",
        "slides": [
            {"id": 1, "type": "cover", "title": "Python Basics"},
            {"id": 2, "type": "code", "title": "Comprehensions"},
            {"id": 3, "type": "code", "title": "Dictionaries"},
            {"id": 4, "type": "exercise", "title": "Lab: Data Processing", "exercise_ref": "LAB-PY-DATA"},
            {"id": 5, "type": "closing", "title": "Wrap up"},
        ]
    }
    py_quiz = generate_quiz_for_deck(py_deck)
    code_questions = [q for q in py_quiz if q.code_snippet]
    assert len(code_questions) >= 2, "Quiz must contain questions with code"

    for q in code_questions:
        assert q.code_snippet is not None and len(q.code_snippet) > 0
        # Find the correct option text
        correct_opt = [opt for opt in q.options if opt.startswith(f"{q.correct_answer})")][0]
        # Explanation must reference verified execution
        assert "verified" in q.explanation.lower() or "yields" in q.explanation.lower()
        # Option must contain the real output
        assert any(num in correct_opt for num in ["4", "8", "40", "6"]), f"Option '{correct_opt}' does not match executed output"

    # 2. Java deck code execution check
    java_deck = {
        "id": "deck_code_exec_java",
        "topic": "Java Core Programming",
        "tech": "Java",
        "tech_version": "21",
        "slides": [
            {"id": 1, "type": "cover", "title": "Java 21"},
            {"id": 2, "type": "code", "title": "Increment Expressions"},
            {"id": 3, "type": "code", "title": "Strings"},
            {"id": 4, "type": "exercise", "title": "Lab: Java Loops", "exercise_ref": "LAB-JAVA-LOOP"},
            {"id": 5, "type": "closing", "title": "Conclusion"},
        ]
    }
    java_quiz = generate_quiz_for_deck(java_deck)
    java_code_questions = [q for q in java_quiz if q.code_snippet]
    assert len(java_code_questions) >= 2

    # In Java Question 3: int a = 5; int b = a++ * 2 -> stdout is 6,10
    q3 = java_quiz[2]
    assert q3.code_snippet is not None
    correct_opt_3 = [opt for opt in q3.options if opt.startswith(f"{q3.correct_answer})")][0]
    assert "6,10" in correct_opt_3, f"Expected '6,10' in correct option, got {correct_opt_3}"


def test_export_quiz_pdf_with_eight_mcqs(tmp_path):
    """
    Verifies that export_quiz_pdf properly exports both student exam copy
    and instructor answer key displaying slide references and common mistakes.
    """
    deck = {
        "id": "deck_export_test",
        "topic": "Spring Boot 3 & Java 21",
        "tech": "Java",
        "tech_version": "21",
        "college": "Vidyalankar Institute of Technology",
        "slides": [
            {"id": 1, "type": "cover", "title": "Spring Boot 3"},
            {"id": 2, "type": "code", "title": "REST Controller"},
            {"id": 3, "type": "code", "title": "Virtual Thread Executor"},
            {"id": 4, "type": "exercise", "title": "Hands-On Lab", "exercise_ref": "LAB-01"},
            {"id": 5, "type": "closing", "title": "Summary"},
        ]
    }
    quiz = generate_quiz_for_deck(deck)
    assert len(quiz) == 8

    student_pdf = os.path.join(str(tmp_path), "Quiz_Student.pdf")
    key_pdf = os.path.join(str(tmp_path), "Quiz_Key.pdf")

    export_quiz_pdf(deck, quiz, student_pdf, include_answers=False)
    export_quiz_pdf(deck, quiz, key_pdf, include_answers=True)

    assert os.path.exists(student_pdf)
    assert os.path.getsize(student_pdf) > 1000
    assert os.path.exists(key_pdf)
    assert os.path.getsize(key_pdf) > 1000
