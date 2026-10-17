import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from backend.database import SnippetRecord, DeckRecord


def normalize_language(lang: str) -> str:
    l = (lang or "").lower().strip()
    if l in ["java", "java21", "temurin"]:
        return "java"
    elif l in ["python", "py", "python3", "python312"]:
        return "python"
    elif l in ["javascript", "js", "node", "nodejs", "node20"]:
        return "javascript"
    elif l in ["typescript", "ts"]:
        return "typescript"
    elif l in ["cpp", "c++"]:
        return "cpp"
    return l or "java"


def extract_fenced_and_inline_code(text: str) -> List[Tuple[str, str]]:
    """
    Extracts (code_snippet, 'fenced' | 'inline') from markdown/text.
    Replaces fenced blocks first to avoid inner backtick duplication.
    """
    if not text or not isinstance(text, str):
        return []

    results: List[Tuple[str, str]] = []
    
    # 1. Fenced code blocks ```...```
    fenced_matches = list(re.finditer(r"```(?:[a-zA-Z0-9_\-\+\#]*\n)?(.*?)```", text, re.DOTALL))
    for m in fenced_matches:
        code = m.group(1).strip()
        if code:
            results.append((code, "fenced"))

    # Replace fenced blocks with placeholder before checking inline
    remaining_text = re.sub(r"```(?:[a-zA-Z0-9_\-\+\#]*\n)?(.*?)```", " __FENCED_BLOCK__ ", text, flags=re.DOTALL)

    # 2. Inline code blocks `...`
    inline_matches = re.findall(r"`([^`\n]+)`", remaining_text)
    for code in inline_matches:
        c = code.strip()
        # Filter out empty or trivially short non-code tokens
        if len(c) > 1 and not c.startswith("__FENCED_"):
            results.append((c, "inline"))

    return results


class SnippetExtractor:
    def __init__(self):
        pass

    def get_found_vs_executed_counts(self, snippets: List[SnippetRecord]) -> Dict[str, int]:
        """Calculates found vs executed snippet counts."""
        found = len(snippets)
        executed = sum(1 for s in snippets if getattr(s, "was_executed", True))
        unverified = sum(1 for s in snippets if not getattr(s, "was_executed", True))
        return {
            "found": found,
            "executed": executed,
            "unverified": unverified,
        }

    def extract_snippets_from_deck(
        self,
        deck_id: str,
        slides: List[Dict[str, Any]],
        default_tech: str = "Java",
        default_version: str = "21",
        db_session: Optional[Session] = None,
        quiz_items: Optional[List[Dict[str, Any]]] = None,
        cheat_sheet_data: Optional[Dict[str, Any]] = None,
    ) -> List[SnippetRecord]:
        """
        Walks slide JSON and scans:
        1. Primary executable slide code (concept, code, exercise) -> marked for execution.
        2. Trainer notes & speaker hints (fenced and inline code) -> marked unverified.
        3. Exercise starter code -> marked unverified if not already executed.
        4. Quiz items (code_snippet, fenced/inline in question/options/explanation) -> marked unverified.
        5. Cheat sheet (syntax cards, tiny examples, pitfall snippets) -> marked unverified.

        Reports found vs executed counts and marks any code that wasn't run as unverified.
        """
        extracted: List[SnippetRecord] = []
        seen_codes = set()
        normalized_default_lang = normalize_language(default_tech)

        # -------------------------------------------------------------
        # 1. Primary Slide Executable Code
        # -------------------------------------------------------------
        for s_idx, slide in enumerate(slides):
            slide_id = slide.get("id", s_idx + 1)
            slide_type = slide.get("type", "concept")
            title = slide.get("title", "")
            code_obj = slide.get("code")

            # For concept slides: prefer the complete runnable example file with its own imports
            notes_data = slide.get("notes") or {}
            ex_data = notes_data.get("example") if isinstance(notes_data, dict) else {}
            full_concept_code = (
                (ex_data.get("full_code") if isinstance(ex_data, dict) else "")
                or (notes_data.get("full_file") if isinstance(notes_data, dict) else "")
                or ""
            ).strip()

            if code_obj and isinstance(code_obj, dict):
                slide_source = code_obj.get("source", "").strip()
                source = full_concept_code if (slide_type == "concept" and full_concept_code) else slide_source
                if source:
                    lang = normalize_language(code_obj.get("language") or normalized_default_lang)
                    version = code_obj.get("version") or default_version
                    expected_output = code_obj.get("expected_output", "")

                    snippet_type = "code"
                    if slide_type == "exercise" or slide.get("exercise_ref"):
                        snippet_type = "exercise"
                    elif "quiz" in title.lower() or "knowledge check" in title.lower():
                        snippet_type = "quiz"
                    elif slide_type == "concept":
                        snippet_type = "concept_example" if full_concept_code else "concept_code"

                    snippet_id = f"snip_{deck_id}_{slide_id}_{len(extracted) + 1}"
                    record = SnippetRecord(
                        id=snippet_id,
                        deck_id=deck_id,
                        slide_id=slide_id,
                        snippet_type=snippet_type,
                        language=lang,
                        version=version,
                        source_code=source,
                        expected_output=expected_output,
                        status="pending",
                        was_executed=True,
                        source_location="slide_code" if not full_concept_code else "concept_example_file",
                        attempts_count=1,
                    )
                    extracted.append(record)
                    seen_codes.add(source)
                    if slide_source:
                        seen_codes.add(slide_source)

        # -------------------------------------------------------------
        # 2. Trainer Notes & Speaker Hints (fenced & inline code)
        # -------------------------------------------------------------
        for s_idx, slide in enumerate(slides):
            slide_id = slide.get("id", s_idx + 1)
            notes_texts = [
                slide.get("trainer_notes", ""),
                slide.get("notes", ""),
                slide.get("speaker_hint", ""),
            ]
            for text in notes_texts:
                if not text:
                    continue
                code_matches = extract_fenced_and_inline_code(text)
                for code_str, block_kind in code_matches:
                    if code_str not in seen_codes:
                        seen_codes.add(code_str)
                        snip_id = f"snip_{deck_id}_{slide_id}_notes_{len(extracted) + 1}"
                        record = SnippetRecord(
                            id=snip_id,
                            deck_id=deck_id,
                            slide_id=slide_id,
                            snippet_type=f"{block_kind}_trainer_notes",
                            language=normalized_default_lang,
                            version=default_version,
                            source_code=code_str,
                            expected_output="",
                            status="unverified",
                            was_executed=False,
                            source_location="trainer_notes",
                            attempts_count=0,
                        )
                        extracted.append(record)

        # -------------------------------------------------------------
        # 3. Exercise Starter Code
        # -------------------------------------------------------------
        for s_idx, slide in enumerate(slides):
            slide_id = slide.get("id", s_idx + 1)
            starter = slide.get("exercise_starter_code") or slide.get("starter_code")
            if starter and isinstance(starter, str):
                starter_clean = starter.strip()
                if starter_clean and starter_clean not in seen_codes:
                    seen_codes.add(starter_clean)
                    snip_id = f"snip_{deck_id}_{slide_id}_starter_{len(extracted) + 1}"
                    record = SnippetRecord(
                        id=snip_id,
                        deck_id=deck_id,
                        slide_id=slide_id,
                        snippet_type="exercise_starter",
                        language=normalized_default_lang,
                        version=default_version,
                        source_code=starter_clean,
                        expected_output="",
                        status="unverified",
                        was_executed=False,
                        source_location="exercise_starter",
                        attempts_count=0,
                    )
                    extracted.append(record)

        # -------------------------------------------------------------
        # 4. Quiz Items (code_snippet, question, options, explanation)
        # -------------------------------------------------------------
        # Fetch from parameter, DB, or slide quiz objects
        quizzes = quiz_items or []
        if not quizzes and db_session:
            deck_rec = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
            if deck_rec and getattr(deck_rec, "quiz_json", None):
                try:
                    quizzes = json.loads(deck_rec.quiz_json)
                except Exception:
                    pass

        # Also inspect slide-level quiz definitions
        for s in slides:
            if s.get("quiz_items"):
                quizzes.extend(s.get("quiz_items"))
            elif s.get("quiz"):
                q_val = s.get("quiz")
                if isinstance(q_val, list):
                    quizzes.extend(q_val)
                elif isinstance(q_val, dict):
                    quizzes.append(q_val)

        for q_idx, item in enumerate(quizzes):
            if not isinstance(item, dict):
                continue
            # Direct code snippet in quiz
            code_snip = item.get("code_snippet") or item.get("code")
            if code_snip and isinstance(code_snip, str):
                clean_c = code_snip.strip()
                if clean_c and clean_c not in seen_codes:
                    seen_codes.add(clean_c)
                    snip_id = f"snip_{deck_id}_quiz_{q_idx + 1}_{len(extracted) + 1}"
                    record = SnippetRecord(
                        id=snip_id,
                        deck_id=deck_id,
                        slide_id=item.get("source_slide_id") or item.get("slide_id", 1),
                        snippet_type="quiz_code",
                        language=normalized_default_lang,
                        version=default_version,
                        source_code=clean_c,
                        expected_output=item.get("expected_output", ""),
                        status="unverified",
                        was_executed=False,
                        source_location="quiz_item",
                        attempts_count=0,
                    )
                    extracted.append(record)

            # Fenced and inline code in question, options, explanation
            text_sources = [
                item.get("question", ""),
                item.get("explanation", ""),
            ]
            options = item.get("options")
            if isinstance(options, list):
                text_sources.extend([str(o) for o in options])
            elif isinstance(options, dict):
                text_sources.extend([str(v) for v in options.values()])

            for txt in text_sources:
                if not txt:
                    continue
                for code_str, block_kind in extract_fenced_and_inline_code(txt):
                    if code_str not in seen_codes:
                        seen_codes.add(code_str)
                        snip_id = f"snip_{deck_id}_quiz_{q_idx + 1}_{len(extracted) + 1}"
                        record = SnippetRecord(
                            id=snip_id,
                            deck_id=deck_id,
                            slide_id=item.get("source_slide_id") or item.get("slide_id", 1),
                            snippet_type=f"{block_kind}_quiz_item",
                            language=normalized_default_lang,
                            version=default_version,
                            source_code=code_str,
                            expected_output="",
                            status="unverified",
                            was_executed=False,
                            source_location="quiz_item",
                            attempts_count=0,
                        )
                        extracted.append(record)

        # -------------------------------------------------------------
        # 5. Cheat Sheet (syntax cards, tiny example, pitfalls)
        # -------------------------------------------------------------
        cheat_data = cheat_sheet_data or {}
        if not cheat_data and db_session:
            deck_rec = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
            if deck_rec and getattr(deck_rec, "cheat_sheet_json", None):
                try:
                    cheat_data = json.loads(deck_rec.cheat_sheet_json)
                except Exception:
                    pass

        if isinstance(cheat_data, dict):
            # Syntax cards
            for sc in cheat_data.get("syntax_cards", []):
                if isinstance(sc, dict):
                    syn = sc.get("syntax", "")
                    if syn and syn not in seen_codes:
                        seen_codes.add(syn)
                        snip_id = f"snip_{deck_id}_cheat_{len(extracted) + 1}"
                        record = SnippetRecord(
                            id=snip_id,
                            deck_id=deck_id,
                            slide_id=1,
                            snippet_type="cheat_sheet_syntax",
                            language=normalized_default_lang,
                            version=default_version,
                            source_code=syn,
                            expected_output="",
                            status="unverified",
                            was_executed=False,
                            source_location="cheat_sheet",
                            attempts_count=0,
                        )
                        extracted.append(record)

            # Tiny Example
            tiny_ex = cheat_data.get("tiny_example")
            if isinstance(tiny_ex, dict):
                tiny_code = tiny_ex.get("code", "")
                if tiny_code and tiny_code not in seen_codes:
                    seen_codes.add(tiny_code)
                    snip_id = f"snip_{deck_id}_cheat_tiny_{len(extracted) + 1}"
                    record = SnippetRecord(
                        id=snip_id,
                        deck_id=deck_id,
                        slide_id=1,
                        snippet_type="cheat_sheet_example",
                        language=normalized_default_lang,
                        version=default_version,
                        source_code=tiny_code,
                        expected_output=tiny_ex.get("output", ""),
                        status="unverified",
                        was_executed=False,
                        source_location="cheat_sheet",
                        attempts_count=0,
                    )
                    extracted.append(record)

            # Pitfall prevention snippets
            for pf in cheat_data.get("pitfalls", []):
                if isinstance(pf, dict):
                    for pf_text in [pf.get("pitfall", ""), pf.get("prevention", "")]:
                        for code_str, block_kind in extract_fenced_and_inline_code(pf_text):
                            if code_str not in seen_codes:
                                seen_codes.add(code_str)
                                snip_id = f"snip_{deck_id}_cheat_pf_{len(extracted) + 1}"
                                record = SnippetRecord(
                                    id=snip_id,
                                    deck_id=deck_id,
                                    slide_id=1,
                                    snippet_type=f"{block_kind}_cheat_sheet",
                                    language=normalized_default_lang,
                                    version=default_version,
                                    source_code=code_str,
                                    expected_output="",
                                    status="unverified",
                                    was_executed=False,
                                    source_location="cheat_sheet",
                                    attempts_count=0,
                                )
                                extracted.append(record)

        # Persist all extracted records if db_session given
        if db_session:
            persisted = []
            for rec in extracted:
                merged = db_session.merge(rec)
                persisted.append(merged)
            db_session.commit()
            return persisted

        return extracted


snippet_extractor = SnippetExtractor()

