import difflib
import uuid
import re
import json
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from backend.database import SnippetRecord, HealingLogRecord
from backend.verification.sandbox import sandbox_engine, ExecutionResult
from backend.llm_generator import llm_generator
from backend.schemas import Slide, SlideCode, TemplateLayoutConfig
from backend.layout_engine import layout_engine


class SelfHealingLoop:
    def __init__(self):
        pass

    def heal_snippet(
        self,
        snippet: SnippetRecord,
        initial_result: ExecutionResult,
        slide: Dict[str, Any],
        config: TemplateLayoutConfig,
        professor_name: str,
        db_session: Optional[Session] = None,
        max_attempts: int = 4,
    ) -> Tuple[bool, str, List[HealingLogRecord]]:
        """
        Executes self-healing loop for failed snippets:
        1. Sends snippet, error log, and pinned version to LLM
        2. Requests corrected snippet
        3. Re-verifies in sandbox
        4. Logs unified before/after diff for every attempt
        5. Max 4 attempts, then marks 'needs_review'
        6. Re-runs layout engine if code changed
        """
        healing_logs = []
        current_code = snippet.source_code
        last_error = initial_result.stderr or initial_result.compiler_output or "Execution error"

        for attempt in range(1, max_attempts + 1):
            snippet.attempts_count = attempt + 1

            # 1. Ask LLM to fix the snippet
            fixed_code = self._request_llm_fix(
                language=snippet.language,
                version=snippet.version,
                source_code=current_code,
                error_log=last_error,
                attempt=attempt,
            )

            # 2. Compute unified diff
            diff_text = self._compute_diff(current_code, fixed_code, snippet.id, attempt)

            # 3. Re-verify in sandbox
            new_result = sandbox_engine.run_snippet(
                snippet_id=f"{snippet.id}_heal_{attempt}",
                language=snippet.language,
                source_code=fixed_code,
                version=snippet.version,
            )

            is_success = new_result.exit_code == 0 and new_result.deprecation_level != "removal"

            # 4. Record Healing Log in DB
            log_rec = HealingLogRecord(
                id=str(uuid.uuid4())[:12],
                snippet_id=snippet.id,
                deck_id=snippet.deck_id,
                attempt_number=attempt,
                error_type="compile_or_runtime_error" if new_result.exit_code != 0 else "deprecation_removal",
                error_log=last_error,
                original_code=current_code,
                fixed_code=fixed_code,
                diff=diff_text,
                success=is_success,
            )
            healing_logs.append(log_rec)
            if db_session:
                db_session.add(log_rec)
                db_session.commit()

            if is_success:
                # Update snippet record and slide
                if getattr(new_result, "sandbox_backend", "") == "docker":
                    snippet.status = "auto_healed"
                else:
                    snippet.status = "verified_low_assurance"
                snippet.source_code = fixed_code
                snippet.actual_output = new_result.stdout or "Execution verified"
                snippet.compiler_output = new_result.compiler_output
                snippet.stderr = new_result.stderr
                snippet.exit_code = 0
                snippet.duration_ms = new_result.duration_ms
                snippet.sandbox_backend = getattr(new_result, "sandbox_backend", "docker")
                snippet.real_runtime_version = getattr(new_result, "real_runtime_version", "")
                snippet.image_digest = getattr(new_result, "image_digest", "")
                snippet.classification = getattr(new_result, "classification", "PASS")
                snippet.was_wrapped = getattr(new_result, "was_wrapped", False)

                # Update slide
                if slide.get("code"):
                    slide["code"]["source"] = fixed_code
                    slide["code"]["expected_output"] = new_result.stdout or "Execution verified"

                if snippet.was_wrapped:
                    slide["imports_omitted"] = True
                    slide["imports_omitted_note"] = "imports omitted"
                    full_runnable = (new_result.wrapped_code or snippet.wrapped_code or "").strip()
                    runnable_section = f"Full runnable version (with imports):\n{full_runnable}"
                    existing_trainer = slide.get("trainer_notes", "") or ""
                    if full_runnable and full_runnable not in existing_trainer:
                        slide["trainer_notes"] = f"{existing_trainer}\n\n{runnable_section}".strip()
                    elif not existing_trainer and full_runnable:
                        slide["trainer_notes"] = runnable_section

                # Re-run layout engine for this slide so it still fits
                self._re_layout_slide(slide, config, professor_name)

                if db_session:
                    db_session.commit()

                return True, fixed_code, healing_logs

            # Prepare for next attempt
            current_code = fixed_code
            last_error = new_result.stderr or new_result.compiler_output or "Still failing execution"

        # Failed after max_attempts
        snippet.status = "needs_review"
        if db_session:
            db_session.commit()

        return False, current_code, healing_logs

    def _request_llm_fix(
        self,
        language: str,
        version: str,
        source_code: str,
        error_log: str,
        attempt: int,
    ) -> str:
        """Prompts LLM to fix compile/runtime errors."""
        system_prompt = (
            "You are an expert compiler and software debugger. Fix the provided code snippet so that it compiles and "
            "executes cleanly with 0 errors. Return ONLY the raw corrected code with NO markdown code blocks, NO explanations."
        )
        user_prompt = f"""Language: {language} (Version: {version})
Original Code:
{source_code}

Error Log:
{error_log}

Fix all syntax errors, missing imports, unhandled exceptions, or deprecation removals.
Return ONLY the corrected runnable code snippet (maximum 12 lines):"""

        try:
            raw_response = llm_generator._call_ollama(system_prompt, user_prompt)
            cleaned = raw_response.strip().strip("'\"`")

            # Check if there's any JSON object in the response
            json_match = re.search(r"\{[\s\S]*\}", cleaned)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                    if isinstance(data, dict):
                        extracted = (
                            data.get("correctedCode")
                            or data.get("code")
                            or data.get("source")
                            or data.get("snippet")
                        )
                        if extracted:
                            cleaned = extracted.strip()
                except Exception:
                    pass

            # Clean markdown fences if present
            if "```" in cleaned:
                match = re.search(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```", cleaned)
                if match:
                    cleaned = match.group(1).strip()
                else:
                    lines = cleaned.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()

            if not cleaned or cleaned == source_code:
                cleaned = self._heuristic_fix(language, source_code, error_log)

            return cleaned if cleaned else source_code
        except Exception as e:
            print(f"Error calling LLM for healing attempt {attempt}: {e}")
            # Deterministic fallback fix for common syntax issues
            return self._heuristic_fix(language, source_code, error_log)

    def _heuristic_fix(self, language: str, source: str, error_log: str) -> str:
        """Deterministic fallback fix for common compiler errors (missing semicolons, variable typos)."""
        fixed = source
        err_lower = error_log.lower()
        if "';' expected" in error_log or "expected ';'" in err_lower or "semicolon" in err_lower or ("java" in language.lower() and not source.strip().endswith((";", "}"))):
            lines = [l + ";" if l.strip() and not l.strip().endswith((";", "{", "}", ":")) else l for l in fixed.split("\n")]
            fixed = "\n".join(lines)
        if "cannot find symbol" in error_log and "println" in source and "System.out.println" not in source:
            fixed = fixed.replace("println", "System.out.println")
        return fixed

    def _compute_diff(self, old_code: str, new_code: str, snippet_id: str, attempt: int) -> str:
        """Generates unified diff between original and healed code."""
        old_lines = [l + "\n" for l in old_code.split("\n")]
        new_lines = [l + "\n" for l in new_code.split("\n")]
        diff_lines = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"before_attempt_{attempt}_{snippet_id}.code",
                tofile=f"after_attempt_{attempt}_{snippet_id}.code",
            )
        )
        return "".join(diff_lines)

    def _re_layout_slide(self, slide_dict: Dict[str, Any], config: TemplateLayoutConfig, professor_name: str):
        """Re-runs layout engine for a slide whose code was healed to ensure it still fits."""
        try:
            # Build Pydantic Slide
            slide_obj = Slide(
                id=slide_dict.get("id", 1),
                type=slide_dict.get("type", "concept"),
                title=slide_dict.get("title", ""),
                bullets=slide_dict.get("bullets", []),
                code=SlideCode(**slide_dict["code"]) if slide_dict.get("code") else None,
                exercise_ref=slide_dict.get("exercise_ref", ""),
                speaker_hint=slide_dict.get("speaker_hint", ""),
            )
            plan = layout_engine.layout_single_slide(slide_obj, config, professor_name)
            if plan.violations:
                print(f"Slide {slide_obj.id} post-healing layout warning: {plan.violations}")
        except Exception as e:
            print(f"Error re-laying out slide {slide_dict.get('id')}: {e}")


healing_loop = SelfHealingLoop()
