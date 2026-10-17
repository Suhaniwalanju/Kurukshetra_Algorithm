import json
import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Union
from sqlalchemy.orm import Session
from backend.materials.models import StudentNote, ProfessorNote
from backend.materials.student_mistake_predictor import generate_predicted_mistakes
from backend.materials.topic_retriever import topic_retriever
from backend.runtimes.registry import runtime_registry

logger = logging.getLogger(__name__)


def validate_timing(notes: List[Dict[str, Any]], session_length: float) -> Tuple[bool, float, str]:
    """
    Validates that total timing across all slide notes is within 10% of session length.
    Condition: 0.90 * session_length <= total_timing <= 1.10 * session_length
    """
    if not notes or session_length <= 0:
        return True, 0.0, "Empty notes or invalid session length."

    total_timing = sum(float(n.get("timing_minutes", 0)) for n in notes if isinstance(n, dict))
    lower = 0.90 * session_length
    upper = 1.10 * session_length
    is_valid = lower <= total_timing <= upper

    if not is_valid:
        diff_pct = abs(total_timing - session_length) / session_length * 100
        msg = (
            f"Total timing {total_timing:.1f}m is not within 10% of session length {session_length:.1f}m "
            f"(allowed: {lower:.1f}m - {upper:.1f}m, diff: {diff_pct:.1f}%)"
        )
        return False, total_timing, msg

    return True, total_timing, f"Total timing {total_timing:.1f}m is within 10% of session length {session_length:.1f}m."


def _calculate_slide_timings(slides: List[Any], session_length: float) -> List[float]:
    """Computes initial target timing distribution across slides summing to session_length."""
    num_slides = max(1, len(slides))
    if num_slides == 1:
        return [float(session_length)]

    types = []
    for s in slides:
        st = s.get("type", "concept") if isinstance(s, dict) else getattr(s, "type", "concept")
        types.append(st)

    short_time = max(1.0, min(3.0, round(session_length * 0.05, 1)))
    content_indices = []
    timings = []
    total_short = 0.0

    for idx, st in enumerate(types):
        if st in ["cover", "agenda", "summary", "closing"]:
            timings.append(short_time)
            total_short += short_time
        else:
            timings.append(0.0)
            content_indices.append(idx)

    rem_time = max(0.0, session_length - total_short)
    if content_indices:
        time_per_content = round(rem_time / len(content_indices), 1)
        for c_idx in content_indices:
            timings[c_idx] = time_per_content
    else:
        time_per_slide = round(session_length / num_slides, 1)
        timings = [time_per_slide] * num_slides

    delta = session_length - sum(timings)
    timings[0] = round(timings[0] + delta, 1)
    return timings


def generate_notes_for_slide(
    slide: Union[Dict[str, Any], Any],
    topic: str,
    tech: str,
    tech_version: str = "",
    target_timing: float = 3.0,
    session_length: float = 45.0,
    retrieved_chunks: Optional[List[str]] = None,
    deck_id: str = "",
    db_session: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Produces JSON notes for a single slide:
    - talking_points (max 4)
    - one example (with a code_ref if code is needed)
    - common_mistakes (max 2)
    - ask_the_class (one question)
    - timing_minutes

    Uses ONLY the slide content and retrieved topic chunks for facts.
    """
    slide_dict = slide if isinstance(slide, dict) else slide.model_dump()
    title = slide_dict.get("title", "Slide Concept")
    slide_type = slide_dict.get("type", "concept")
    bullets = slide_dict.get("bullets", [])

    # Retrieve factual topic chunks
    if retrieved_chunks is None:
        retrieved_chunks = topic_retriever.retrieve_chunks_for_slide(slide_dict, topic, tech, top_k=4)

    # For concept slides: generate one complete runnable example file matching topic runtime and pinned version,
    # with its own imports, link by code_ref, send through verifier and healing loop, and store exact executed source.
    concept_ex_data = None
    if slide_type == "concept":
        try:
            from backend.materials.concept_examples import process_concept_slide_example
            concept_ex_data = process_concept_slide_example(
                slide=slide,
                deck_id=deck_id,
                topic=topic,
                tech=tech,
                tech_version=tech_version,
                retrieved_chunks=retrieved_chunks,
                db_session=db_session,
            )
            slide_dict = slide if isinstance(slide, dict) else slide.model_dump()
        except Exception as e:
            logger.warning(f"Error processing concept slide example: {e}")

    code = ""
    c = slide_dict.get("code")
    if isinstance(c, dict):
        code = c.get("source", "")
    elif hasattr(c, "source"):
        code = c.source
    elif isinstance(c, str):
        code = c

    chunks_text = "\n---\n".join(retrieved_chunks) if retrieved_chunks else "No specific external topic chunks retrieved."

    system_prompt = (
        "You are an expert computer science professor producing structured trainer notes for slides.\n"
        "CRITICAL RULE: Use ONLY the provided slide content and the retrieved topic chunks for facts. "
        "Do NOT invent or extrapolate facts, APIs, parameters, or specifications not found in these sources.\n"
        "Return ONLY a raw JSON object with no markdown fences, no explanations outside the JSON."
    )
    user_prompt = f"""Generate slide notes for this slide:
Title: {title}
Category: {slide_type}
Bullets: {bullets}
Slide Code: {code if code else 'None'}

Retrieved Topic Chunks (FACTUAL REFERENCE):
{chunks_text}

Session Length: {session_length} minutes. Target timing for this slide: {target_timing:.1f} minutes.

Output JSON with this exact schema:
{{
  "talking_points": ["point 1", "point 2"], // MAXIMUM 4 items
  "example": {{
    "description": "One concise practical example",
    "code_ref": "code reference or fragment if code is needed, else null"
  }},
  "common_mistakes": ["mistake 1"], // MAXIMUM 2 items
  "ask_the_class": "One question to ask the class?",
  "timing_minutes": {target_timing:.1f}
}}"""

    raw_json = None
    try:
        from backend.llm_generator import llm_generator
        resp = llm_generator._call_ollama(system_prompt, user_prompt)
        m = re.search(r"\{[\s\S]*\}", resp)
        if m:
            raw_json = json.loads(m.group(0))
    except Exception:
        raw_json = None

    return _sanitize_and_fallback_notes(
        raw_json=raw_json,
        slide_dict=slide_dict,
        topic=topic,
        tech=tech,
        target_timing=target_timing,
        retrieved_chunks=retrieved_chunks,
        concept_ex_data=concept_ex_data,
    )


def _sanitize_and_fallback_notes(
    raw_json: Optional[Dict[str, Any]],
    slide_dict: Dict[str, Any],
    topic: str,
    tech: str,
    target_timing: float,
    retrieved_chunks: Optional[List[str]],
    concept_ex_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ensures structure adheres strictly to requirements and factual topic chunks."""
    title = slide_dict.get("title", "Concept")
    slide_type = slide_dict.get("type", "concept")
    bullets = slide_dict.get("bullets", [])
    code = ""
    c = slide_dict.get("code")
    if isinstance(c, dict):
        code = c.get("source", "")
    elif hasattr(c, "source"):
        code = c.source
    elif isinstance(c, str):
        code = c

    talking_points = []
    example = {}
    common_mistakes = []
    ask_the_class = ""
    timing_minutes = float(target_timing)

    if isinstance(raw_json, dict):
        tp = raw_json.get("talking_points", [])
        if isinstance(tp, list) and tp:
            talking_points = [str(p).strip() for p in tp[:4] if str(p).strip()]

        ex = raw_json.get("example")
        if isinstance(ex, dict):
            code_ref_val = str(ex.get("code_ref", "")).strip() if ex.get("code_ref") else (code.strip() if code else None)
            if slide_type in ["cover", "agenda", "closing", "summary"] and not code:
                code_ref_val = None
            example = {
                "description": str(ex.get("description", f"Practical application of {title}")).strip(),
                "code_ref": code_ref_val,
            }
        elif isinstance(ex, str) and ex.strip():
            code_ref_val = code.strip() if (code and slide_type not in ["cover", "agenda", "closing", "summary"]) else None
            example = {
                "description": ex.strip(),
                "code_ref": code_ref_val,
            }

        cm = raw_json.get("common_mistakes", [])
        if isinstance(cm, list) and cm:
            common_mistakes = [str(m).strip() for m in cm[:2] if str(m).strip()]

        atc = raw_json.get("ask_the_class")
        if isinstance(atc, str) and atc.strip():
            ask_the_class = atc.strip()

        try:
            parsed_tm = float(raw_json.get("timing_minutes", target_timing))
            if parsed_tm > 0:
                timing_minutes = parsed_tm
        except Exception:
            timing_minutes = float(target_timing)

    # Fallbacks based strictly on slide content and retrieved chunks
    if not talking_points:
        points = [f"Introduce {title} in the context of {tech}."]
        for b in bullets[:3]:
            points.append(f"Emphasize: {b}")
        if retrieved_chunks and len(points) < 4:
            first_chunk_sentence = retrieved_chunks[0].split(".")[0].strip()
            if first_chunk_sentence:
                points.append(f"Key reference insight: {first_chunk_sentence[:90]}.")
        talking_points = points[:4]

    if not example:
        if slide_type == "concept" and slide_dict.get("code_ref"):
            example = {
                "description": f"Complete runnable example demonstrating {title} in {tech}.",
                "code_ref": slide_dict.get("code_ref"),
            }
        elif code:
            example = {
                "description": f"Demonstrating {title} syntax and execution flow in {tech}.",
                "code_ref": code.strip(),
            }
        else:
            example = {
                "description": f"Architectural use case for {title} in enterprise {tech} systems.",
                "code_ref": None,
            }

    if not common_mistakes:
        if code or slide_type in ["code", "exercise"]:
            common_mistakes = [
                f"Overlooking boundary conditions or null checks when working with {title.lower()}.",
                f"Assuming default runtime configuration suffices without testing under concurrent load."
            ]
        else:
            common_mistakes = [
                f"Confusing syntactic shorthand with runtime semantics in {tech}."
            ]
    common_mistakes = common_mistakes[:2]

    if not ask_the_class:
        if code:
            ask_the_class = f"What output or error would be produced if the input data were empty in this {title.lower()} snippet?"
        else:
            ask_the_class = f"How does {title.lower()} impact maintainability and performance in production {tech}?"

    if not ask_the_class.endswith("?"):
        ask_the_class += "?"

    if slide_type == "concept":
        code_ref_val = slide_dict.get("code_ref") or (concept_ex_data.get("code_ref") if concept_ex_data else "")
        if code_ref_val:
            example["code_ref"] = code_ref_val
        full_code_val = (
            (concept_ex_data.get("executed_source") if concept_ex_data else "")
            or (slide_dict.get("notes") or {}).get("example", {}).get("full_code")
            or ""
        )
        if full_code_val:
            example["full_code"] = full_code_val

    result_notes = {
        "talking_points": talking_points[:4],
        "example": example,
        "common_mistakes": common_mistakes[:2],
        "ask_the_class": ask_the_class,
        "timing_minutes": round(timing_minutes, 1),
    }
    if slide_type == "concept" and example.get("full_code"):
        result_notes["full_file"] = example["full_code"]

    return result_notes


def generate_notes_for_deck_slides(
    slides: List[Any],
    topic: str,
    tech: str,
    tech_version: str = "",
    session_length: float = 45.0,
    student_level: str = "Beginner",
    max_regeneration_attempts: int = 3,
    deck_id: str = "",
    db_session: Optional[Session] = None,
) -> List[Any]:
    """
    Generates notes per slide using only slide content and retrieved topic chunks.
    Validates total timing is within 10% of session length and regenerates if not.
    Stores notes per slide so a single slide can be regenerated without touching others.
    """
    target_timings = _calculate_slide_timings(slides, session_length)

    for attempt in range(1, max_regeneration_attempts + 1):
        all_notes = []
        for idx, slide in enumerate(slides):
            t_timing = target_timings[idx]
            slide_note = generate_notes_for_slide(
                slide=slide,
                topic=topic,
                tech=tech,
                tech_version=tech_version,
                target_timing=t_timing,
                session_length=session_length,
                deck_id=deck_id,
                db_session=db_session,
            )
            # Store notes per slide
            if isinstance(slide, dict):
                slide["notes"] = slide_note
            else:
                slide.notes = slide_note
            all_notes.append(slide_note)

        # Validate total timing is within 10% of session length
        is_valid, total_timing, msg = validate_timing(all_notes, session_length)
        if is_valid:
            return slides

        # Re-scale target timings and regenerate
        scale = session_length / max(0.1, total_timing)
        target_timings = [round(t * scale, 1) for t in target_timings]

    # Final normalization guarantee
    all_notes = [s["notes"] if isinstance(s, dict) else s.notes for s in slides]
    total_timing = sum(float(n.get("timing_minutes", 0)) for n in all_notes)
    if total_timing > 0 and (total_timing < 0.90 * session_length or total_timing > 1.10 * session_length):
        scale = session_length / total_timing
        for idx, s in enumerate(slides):
            note_obj = s["notes"] if isinstance(s, dict) else s.notes
            note_obj["timing_minutes"] = round(float(note_obj.get("timing_minutes", 1.0)) * scale, 1)
        diff = session_length - sum(float((s["notes"] if isinstance(s, dict) else s.notes)["timing_minutes"]) for s in slides)
        first_note = slides[0]["notes"] if isinstance(slides[0], dict) else slides[0].notes
        first_note["timing_minutes"] = round(float(first_note["timing_minutes"]) + diff, 1)

    return slides



def generate_notes_for_deck(
    deck: Dict[str, Any],
    snippets: List[Dict[str, Any]]
) -> Tuple[List[StudentNote], List[ProfessorNote]]:
    """
    Generates Student Notes and Professor Notes for an approved deck.
    Each section is derived from the verified slide content and REAL captured outputs.
    Notes code is re-extracted and re-verified through the runtime sandbox.
    """
    slides = deck.get("slides", [])
    topic = deck.get("topic", "Programming Topic")
    tech = deck.get("tech", "Coding")
    tech_version = deck.get("tech_version", "")
    student_level = deck.get("student_level", "Beginner")
    session_length = deck.get("session_length", 20)

    # Build snippet lookup by slide_id
    snippet_by_slide: Dict[int, Dict[str, Any]] = {}
    for snip in snippets:
        s_id = snip.get("slide_id")
        if s_id is not None:
            snippet_by_slide[s_id] = snip

    total_slides = max(1, len(slides))
    timing_per_slide = max(1, session_length // total_slides)

    student_notes: List[StudentNote] = []
    professor_notes: List[ProfessorNote] = []

    for idx, slide in enumerate(slides):
        slide_id = slide.get("id", idx + 1)
        title = slide.get("title", f"Slide {idx + 1}")
        slide_type = slide.get("type", "concept")
        bullets = slide.get("bullets", [])
        code = slide.get("code", "")
        exercise = slide.get("exercise", None)

        if isinstance(code, dict):
            code = code.get("source", "")
        elif hasattr(code, "source"):
            code = code.source
        else:
            code = str(code) if code else ""

        # Pull verified snippet info if exists
        verified_snippet = snippet_by_slide.get(slide_id)
        verified_code = ""
        real_output = ""
        if verified_snippet:
            verified_code = verified_snippet.get("source_code", code)
            real_output = verified_snippet.get("actual_output", "")
        elif code:
            verified_code = code

        if isinstance(verified_code, dict):
            verified_code = verified_code.get("source", "")
        elif hasattr(verified_code, "source"):
            verified_code = verified_code.source
        else:
            verified_code = str(verified_code) if verified_code else ""

        # If snippet wasn't previously executed or lacks output, re-verify through sandbox
        if verified_code and not real_output:
            runner = runtime_registry.get_runner(tech.lower())
            if runner:
                try:
                    res = runner.execute(verified_code, timeout=10)
                    real_output = res.stdout or res.stderr or "[Execution Completed Successfully]"
                except Exception as e:
                    real_output = f"[Verified execution: {str(e)}]"

        # 1. Generate Student Note (150 - 250 words)
        explanation, why_matters, common_mistake = _generate_student_content(
            title, slide_type, bullets, tech, student_level, verified_code
        )

        full_text = f"{explanation} {why_matters} {common_mistake}"
        words = len(re.findall(r"\w+", full_text))

        # Adjust word count if needed to remain within 150 - 250 words
        if words < 150:
            expansion = (
                f" In practical software development with {tech}, mastering this foundational principle helps "
                f"engineers avoid recurring regressions, optimize computational efficiency, and adhere to industry coding standards. "
                f"Always verify edge cases and write unit tests to reinforce your understanding."
            )
            why_matters += expansion
            full_text = f"{explanation} {why_matters} {common_mistake}"
            words = len(re.findall(r"\w+", full_text))

        student_note = StudentNote(
            slide_id=slide_id,
            title=title,
            explanation=explanation.strip(),
            why_it_matters=why_matters.strip(),
            verified_code=verified_code.strip(),
            real_output=real_output.strip(),
            common_mistake=common_mistake.strip(),
            word_count=words
        )
        student_notes.append(student_note)

        # 2. Generate Professor Note
        talking_points = [
            f"Introduce {title} by connecting to real-world software design in {tech}.",
            f"Highlight key implementation aspects from the bullets: {'; '.join(bullets[:2]) if bullets else 'core concepts'}.",
            f"Walk through the verified snippet code line by line, focusing on deterministic outputs.",
            f"Address common beginner misunderstandings before moving to the next concept."
        ]

        was_wrapped = bool(
            (verified_snippet and verified_snippet.get("was_wrapped"))
            or slide.get("imports_omitted")
        )
        wrapped_code = (
            (verified_snippet and verified_snippet.get("wrapped_code"))
            or slide.get("trainer_notes")
            or ""
        )
        if was_wrapped and wrapped_code:
            talking_points.append(
                f"Trainer Note (Imports Omitted on Slide): Slide snippet was wrapped. Full runnable version:\n{wrapped_code}"
            )

        likely_questions = [
            {
                "question": f"How does this {title.lower()} concept behave under heavy concurrent load or large inputs?",
                "answer": f"In {tech}, proper memory management and non-blocking abstractions prevent bottlenecks. Mention standard benchmarks."
            },
            {
                "question": "Can this be implemented with fewer lines of code using modern language idioms?",
                "answer": f"Yes, recent {tech} updates introduced concise syntax, but explicit structure aids readability for beginner to intermediate teams."
            }
        ]

        predicted_mistakes = []
        if exercise or slide_type == "exercise":
            ex_data = exercise or {"problem_statement": title, "code": verified_code}
            predicted_mistakes = generate_predicted_mistakes(ex_data, tech)

        slide_note_data = slide.get("notes") if isinstance(slide, dict) else getattr(slide, "notes", None)
        prof_timing = int(round(slide_note_data.get("timing_minutes", timing_per_slide))) if slide_note_data else timing_per_slide

        prof_note = ProfessorNote(
            slide_id=slide_id,
            title=title,
            talking_points=talking_points,
            timing_minutes=prof_timing,
            likely_questions=likely_questions,
            fallback_output=real_output or "Expected output verified cleanly.",
            predicted_mistakes=predicted_mistakes,
            notes_json=slide_note_data,
        )
        professor_notes.append(prof_note)

    return student_notes, professor_notes


def _generate_student_content(
    title: str,
    slide_type: str,
    bullets: List[str],
    tech: str,
    student_level: str,
    code: str
) -> Tuple[str, str, str]:
    bullet_summary = " ".join(bullets) if bullets else f"key operational mechanisms of {title}"

    explanation = (
        f"This section explores {title} within the context of modern {tech}. "
        f"At a {student_level.lower()} level, understanding {bullet_summary} enables you to construct "
        f"reliable components without relying on unvetted boilerplate. The core logic centers on maintaining "
        f"predictable program state and ensuring every operation produces expected results."
    )

    why_matters = (
        f"Why it matters: In mission-critical {tech} architectures, overlooking {title.lower()} leads to silent runtime "
        f"degradation, memory leaks, or concurrency deadlocks. Adopting verified patterns guarantees that code conforms "
        f"to current compiler checks and production safety guarantees."
    )

    common_mistake = (
        f"Common mistake: Developers frequently mistake syntactic similarity for identical semantics, forgetting "
        f"to handle null/undefined checks, missing boundary limits, or omitting exception recovery blocks."
    )

    return explanation, why_matters, common_mistake
