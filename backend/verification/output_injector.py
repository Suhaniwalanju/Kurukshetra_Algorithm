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
            if exec_result.deprecation_level == "removal":
                snippet.status = "failed"
                note += " (Failed: Deprecation marked for removal)"
            else:
                snippet.status = "verified"
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
                break

        return mismatch, note


output_injector = OutputInjector()
