import os
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.database import SnippetRecord


def normalize_language(lang: str) -> str:
    l = lang.lower().strip()
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


class SnippetExtractor:
    def __init__(self):
        pass

    def extract_snippets_from_deck(
        self,
        deck_id: str,
        slides: List[Dict[str, Any]],
        default_tech: str = "Java",
        default_version: str = "21",
        db_session: Optional[Session] = None,
    ) -> List[SnippetRecord]:
        """
        Walks slide JSON and extracts all code blocks (concept slides, code slides, exercise starter code, quiz code).
        Assigns snippet_id linked to slide_id, language, and pinned version.
        Persists each into database.
        """
        extracted = []
        normalized_default_lang = normalize_language(default_tech)

        for s_idx, slide in enumerate(slides):
            slide_id = slide.get("id", s_idx + 1)
            slide_type = slide.get("type", "concept")
            title = slide.get("title", "")
            code_obj = slide.get("code")

            if not code_obj or not isinstance(code_obj, dict):
                continue

            source = code_obj.get("source", "").strip()
            if not source:
                continue

            lang = normalize_language(code_obj.get("language") or normalized_default_lang)
            version = code_obj.get("version") or default_version
            expected_output = code_obj.get("expected_output", "")

            # Determine snippet type
            snippet_type = "code"
            if slide_type == "exercise" or slide.get("exercise_ref"):
                snippet_type = "exercise"
            elif "quiz" in title.lower() or "knowledge check" in title.lower():
                snippet_type = "quiz"
            elif slide_type == "concept":
                snippet_type = "concept_code"

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
                attempts_count=1,
            )
            if db_session:
                record = db_session.merge(record)

            extracted.append(record)

        if db_session:
            db_session.commit()

        return extracted


snippet_extractor = SnippetExtractor()
