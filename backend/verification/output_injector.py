from typing import List, Dict, Any, Tuple
from backend.verification.sandbox import ExecutionResult
from backend.database import SnippetRecord


class OutputInjector:
    def __init__(self):
        pass

    def inject_real_output(
        self,
        slides: List[Dict[str, Any]],
        snippet: SnippetRecord,
        exec_result: ExecutionResult,
    ) -> Tuple[bool, str]:
        """
        Replaces each slide's expected_output with the ACTUAL captured stdout.
        If the LLM's expected output differs from the real one, records the mismatch and uses the real one.
        Returns (mismatch_detected: bool, comparison_note: str).
        """
        actual = (exec_result.stdout or "").strip()
        expected = (snippet.expected_output or "").strip()

        # Update snippet record with real output details
        snippet.actual_output = actual
        snippet.compiler_output = exec_result.compiler_output
        snippet.stderr = exec_result.stderr
        snippet.exit_code = exec_result.exit_code
        snippet.duration_ms = exec_result.duration_ms
        snippet.command_executed = exec_result.command_executed
        snippet.wrapped_code = exec_result.wrapped_code
        snippet.deprecation_level = exec_result.deprecation_level
        snippet.deprecation_details = exec_result.deprecation_details
        snippet.sandbox_backend = getattr(exec_result, "sandbox_backend", "docker")
        snippet.real_runtime_version = getattr(exec_result, "real_runtime_version", "")
        snippet.image_digest = getattr(exec_result, "image_digest", "")
        snippet.classification = getattr(exec_result, "classification", "PASS")
        snippet.was_wrapped = getattr(exec_result, "was_wrapped", False)
        snippet.is_non_deterministic = getattr(exec_result, "is_non_deterministic", False)

        # Flag non-deterministic output: outputs that differ across runs are flagged instead of injected
        if snippet.is_non_deterministic:
            snippet.status = "needs_review"
            note = f"Non-Deterministic Output: Run 1 and Run 2 produced different outputs ({getattr(exec_result, 'non_deterministic_details', '')})"
            for slide in slides:
                if slide.get("id") == snippet.slide_id:
                    slide["non_deterministic"] = True
                    slide["non_deterministic_note"] = "Non-deterministic output detected across runs"
                    # Do NOT inject non-deterministic output
                    break
            return True, note

        # Check for mismatch
        def clean_val(v: str) -> str:
            v_clean = v.replace("Expected Output:", "").replace("Output:", "").replace("Result:", "").strip()
            return " ".join(v_clean.split())

        norm_expected = clean_val(expected)
        norm_actual = clean_val(actual)

        mismatch = False
        note = "Output matched expected output"

        if actual and norm_expected != norm_actual:
            mismatch = True
            note = f"Output Mismatch: Expected '{expected}' vs Actual '{actual}'"

        snippet.mismatch_detected = mismatch

        # Determine snippet status
        if exec_result.exit_code == 0:
            if exec_result.deprecation_level in ["warning", "removal"] or exec_result.deprecation_details:
                snippet.status = "failed"
                note += f" (Failed: Deprecation detected: {exec_result.deprecation_details or exec_result.deprecation_level})"
            elif getattr(exec_result, "sandbox_backend", "") == "docker":
                snippet.status = "verified"
            else:
                # If the fallback process backend was used, set status to verified_low_assurance
                snippet.status = "verified_low_assurance"
                note += " (Verified Low Assurance: Executed via local fallback process)"
        else:
            snippet.status = "failed"
            note = f"Execution failed with exit code {exec_result.exit_code}"

        # Inject real output into target slide
        for slide in slides:
            if slide.get("id") == snippet.slide_id:
                if slide.get("code"):
                    # Inject verified actual stdout
                    if actual:
                        slide["code"]["expected_output"] = actual
                    elif exec_result.exit_code == 0:
                        slide["code"]["expected_output"] = "Execution successful"

                # If snippet was wrapped, record imports_omitted note on slide and store full runnable version in trainer notes
                if snippet.was_wrapped:
                    slide["imports_omitted"] = True
                    slide["imports_omitted_note"] = "imports omitted"
                    full_runnable = (exec_result.wrapped_code or snippet.wrapped_code or "").strip()
                    runnable_section = f"Full runnable version (with imports):\n{full_runnable}"

                    existing_trainer = slide.get("trainer_notes", "") or ""
                    if full_runnable and full_runnable not in existing_trainer:
                        slide["trainer_notes"] = f"{existing_trainer}\n\n{runnable_section}".strip()
                    elif not existing_trainer and full_runnable:
                        slide["trainer_notes"] = runnable_section

                    existing_hint = slide.get("speaker_hint", "") or ""
                    if "imports omitted" not in existing_hint.lower():
                        slide["speaker_hint"] = f"{existing_hint} [imports omitted - full runnable version in trainer notes]".strip()
                break

        return mismatch, note


output_injector = OutputInjector()
