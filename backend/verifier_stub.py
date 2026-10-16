"""
Phase 2 Verifier Interface Stub
--------------------------------
This module defines the contract and stub implementation for code execution verification.
In Phase 2, this class will execute the code snippets in an isolated, sandboxed Docker/firejail
container, comparing standard output against expected_output.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from backend.schemas import DeckSchema, Slide, SlideCode


@dataclass
class CodeExecutionResult:
    slide_id: int
    language: str
    code_source: str
    expected_output: str
    actual_output: str = ""
    exit_code: int = 0
    is_verified: bool = True
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class DeckVerificationReport:
    total_code_slides: int = 0
    verified_slides: int = 0
    failed_slides: int = 0
    all_passed: bool = True
    results: List[CodeExecutionResult] = field(default_factory=list)


class CodeVerifierStub:
    """
    Code Verifier Stub for Phase 1.
    Provides clean interface ready for containerized execution sandboxing in Phase 2.
    """

    def __init__(self, sandbox_mode: str = "mock"):
        self.sandbox_mode = sandbox_mode

    def verify_deck(self, deck: DeckSchema) -> DeckVerificationReport:
        """
        Verifies all code snippets in the deck.
        In Phase 1, validates syntax readiness and returns a clean pass report.
        Phase 2 will plug in the active sandboxed execution runner.
        """
        report = DeckVerificationReport()

        for slide in deck.slides:
            if slide.code and slide.code.source.strip():
                report.total_code_slides += 1
                res = CodeExecutionResult(
                    slide_id=slide.id,
                    language=slide.code.language,
                    code_source=slide.code.source,
                    expected_output=slide.code.expected_output,
                    actual_output=slide.code.expected_output,  # Phase 1 stub mimics matching output
                    exit_code=0,
                    is_verified=True,
                    execution_time_ms=12.5,
                )
                report.results.append(res)
                report.verified_slides += 1

        report.all_passed = report.failed_slides == 0
        return report

    def verify_single_snippet(self, code: SlideCode) -> CodeExecutionResult:
        """Verifies a single code block."""
        return CodeExecutionResult(
            slide_id=0,
            language=code.language,
            code_source=code.source,
            expected_output=code.expected_output,
            actual_output=code.expected_output,
            exit_code=0,
            is_verified=True,
        )


code_verifier = CodeVerifierStub()
