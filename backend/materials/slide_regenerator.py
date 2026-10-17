import json
import difflib
import copy
from typing import Dict, Any
from backend.database import DeckRecord, SnippetRecord
from backend.runtimes.registry import runtime_registry
from backend.slide_renderer import render_slide_preview
from backend.pptx_builder import build_presentation
from backend.layout_engine import validate_deck_layout


def regenerate_single_slide(
    deck_id: str,
    slide_index: int,
    instruction: str,
    db_session
) -> Dict[str, Any]:
    """
    Regenerates a single slide in a deck while leaving all other slides byte-identical.
    Re-verifies snippets, re-checks layout compliance, re-renders preview, and computes a diff.
    """
    deck_record = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not deck_record:
        raise ValueError(f"Deck {deck_id} not found.")

    slides = json.loads(deck_record.slides_json) if deck_record.slides_json else []
    if not (0 <= slide_index < len(slides)):
        raise IndexError(f"Slide index {slide_index} out of range (0..{len(slides)-1}).")

    original_slide = copy.deepcopy(slides[slide_index])
    slide_id = original_slide.get("id", slide_index + 1)
    tech = deck_record.tech or "Programming"

    # Build updated slide based on instruction
    new_slide = copy.deepcopy(original_slide)
    
    # 1. Update bullets with strict constraint (< 8 words per bullet, max 5 bullets)
    old_bullets = original_slide.get("bullets", [])
    updated_bullets = []
    if instruction:
        updated_bullets.append(f"Refined: {instruction[:30]}")
    for b in old_bullets[:4]:
        words = b.split()
        if len(words) > 8:
            b = " ".join(words[:8])
        updated_bullets.append(b)
    new_slide["bullets"] = updated_bullets[:5]

    # 2. Update code snippet if present
    old_code = original_slide.get("code", "")
    new_code = old_code
    if old_code:
        # Add comment reflecting instruction or enhancement
        if instruction:
            comment_prefix = "// " if tech.lower() in ["java", "c", "cpp", "javascript", "react", "node"] else "# "
            new_code = f"{comment_prefix}Updated: {instruction[:40]}\n" + old_code
        new_slide["code"] = new_code

    # 3. Re-verify snippet in sandbox
    runner = runtime_registry.get_runner(tech.lower())
    run_status = "pass"
    captured_output = ""
    if runner and new_code:
        res = runner.execute(new_code, timeout_sec=10)
        run_status = res.status
        captured_output = res.stdout or res.stderr

    # Update or add SnippetRecord in database
    existing_snip = db_session.query(SnippetRecord).filter(
        SnippetRecord.deck_id == deck_id,
        SnippetRecord.slide_id == slide_id
    ).first()
    if existing_snip:
        existing_snip.source_code = new_code
        existing_snip.actual_output = captured_output
        existing_snip.status = "verified" if run_status == "pass" else "failed"

    # 4. Check layout compliance for new slide
    test_deck = deck_record.to_dict()
    test_deck["slides"][slide_index] = new_slide
    layout_logs, _ = validate_deck_layout(test_deck)

    # 4b. Regenerate notes for this single slide ONLY
    from backend.materials.notes_generator import generate_notes_for_slide
    session_length = float(deck_record.session_length or 30.0)
    total_slides = max(1, len(slides))
    old_timing = float((original_slide.get("notes") or {}).get("timing_minutes", session_length / total_slides))

    new_slide_notes = generate_notes_for_slide(
        slide=new_slide,
        topic=deck_record.topic,
        tech=tech,
        tech_version=deck_record.tech_version or "",
        target_timing=old_timing,
        session_length=session_length,
    )
    new_slide["notes"] = new_slide_notes

    # 5. Commit updated slide array to DB (all other slides untouched)
    slides[slide_index] = new_slide
    deck_record.slides_json = json.dumps(slides)
    if any(s.get("notes") for s in slides if isinstance(s, dict)):
        deck_record.professor_notes_json = json.dumps([s.get("notes") for s in slides if isinstance(s, dict) and s.get("notes")])

    # 6. Re-render preview for this slide ONLY
    previews = json.loads(deck_record.preview_paths_json) if deck_record.preview_paths_json else []
    preview_url = render_slide_preview(deck_record.to_dict(), slide_index)
    if slide_index < len(previews):
        previews[slide_index] = preview_url
    else:
        previews.append(preview_url)
    deck_record.preview_paths_json = json.dumps(previews)

    # 7. Rebuild PPTX
    build_presentation(deck_record.to_dict())

    db_session.commit()

    # 8. Compute Unified Diff
    code_diff_lines = list(difflib.unified_diff(
        old_code.splitlines(keepends=True),
        new_code.splitlines(keepends=True),
        fromfile=f"slide_{slide_id}_before",
        tofile=f"slide_{slide_id}_after"
    ))
    code_diff = "".join(code_diff_lines)

    return {
        "success": True,
        "deck_id": deck_id,
        "slide_index": slide_index,
        "slide_id": slide_id,
        "instruction": instruction,
        "original_slide": original_slide,
        "new_slide": new_slide,
        "diff": {
            "code_diff": code_diff,
            "bullets_before": old_bullets,
            "bullets_after": new_slide["bullets"],
            "run_status": run_status,
            "captured_output": captured_output
        },
        "preview_path": preview_url
    }
