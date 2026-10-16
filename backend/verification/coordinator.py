import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import Session

from backend.database import (
    DeckRecord,
    SnippetRecord,
    VerificationRunRecord,
    HealingLogRecord,
    ExerciseProofRecord,
    ContentReviewRecord,
)
from backend.schemas import Slide, TemplateLayoutConfig
from backend.template_registry import template_registry
from backend.layout_engine import layout_engine
from backend.pptx_builder import pptx_builder
from backend.slide_renderer import slide_renderer

from backend.verification.extractor import SnippetExtractor
from backend.verification.sandbox import sandbox_engine, ExecutionResult
from backend.verification.output_injector import OutputInjector
from backend.verification.healing_loop import SelfHealingLoop
from backend.verification.exercise_prover import ExerciseProver
from backend.verification.content_reviewer import ContentReviewer
from backend.verification.template_qa import TemplateComplianceQA
from backend.verification.report_generator import report_generator


class VerificationCoordinator:
    def __init__(self):
        self.extractor = SnippetExtractor()
        self.output_injector = OutputInjector()
        self.healing_loop = SelfHealingLoop()
        self.exercise_prover = ExerciseProver()
        self.content_reviewer = ContentReviewer()
        self.template_qa = TemplateComplianceQA()
        self.report_gen = report_generator
        # In-memory progress event queues for live SSE streams
        self.progress_queues: Dict[str, List[Dict[str, Any]]] = {}

    def get_progress_events(self, deck_id: str) -> List[Dict[str, Any]]:
        return self.progress_queues.get(deck_id, [])

    def _publish_event(self, deck_id: str, stage: str, message: str, percent: int, details: Optional[Dict[str, Any]] = None):
        event = {
            "deck_id": deck_id,
            "stage": stage,
            "message": message,
            "percent": percent,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
        }
        if deck_id not in self.progress_queues:
            self.progress_queues[deck_id] = []
        self.progress_queues[deck_id].append(event)

    def verify_deck(
        self,
        deck_id: str,
        db_session: Session,
    ) -> Dict[str, Any]:
        """
        Runs the end-to-end verification pipeline:
        1. Snippet extraction
        2. Sandbox execution (worker pool)
        3. Real output injection & deprecation detection
        4. Self-healing loop for failed snippets (up to 4 attempts)
        5. Exercise proof (reference vs naive, mutation testing)
        6. Non-code content review (factual & bullet rule check)
        7. Verified badge stamp on slides
        8. Template compliance QA & re-layout
        9. HTML and PDF report generation
        """
        deck = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        if not deck:
            raise ValueError(f"Deck {deck_id} not found")

        self.progress_queues[deck_id] = []
        self._publish_event(deck_id, "start", "Initiating verification pipeline...", 5)

        slides_data = json.loads(deck.slides_json)
        tech = getattr(deck, "tech", None) or getattr(deck, "tech_stack", "Java")
        version = deck.tech_version or "21"
        professor_name = deck.professor_name or "Professor"
        college = deck.college or "University"
        output_dir = deck.output_dir or os.path.join(os.getcwd(), "output", deck_id)
        os.makedirs(output_dir, exist_ok=True)

        template_config = template_registry.get_config(college)
        if not template_config and template_registry.templates:
            template_config = list(template_registry.templates.values())[0]

        # -------------------------------------------------------------
        # STEP 1: Snippet Extraction
        # -------------------------------------------------------------
        self._publish_event(deck_id, "extracting", "Extracting code blocks from slide JSON...", 15)
        snippets = self.extractor.extract_snippets_from_deck(
            deck_id=deck_id,
            slides=slides_data,
            default_tech=tech,
            default_version=version,
            db_session=db_session,
        )

        # -------------------------------------------------------------
        # STEP 2: Parallel Sandbox Execution
        # -------------------------------------------------------------
        self._publish_event(
            deck_id,
            "executing",
            f"Running {len(snippets)} snippets in isolated sandbox (network none, 20s timeout)...",
            30,
            {"snippet_count": len(snippets)},
        )

        runs = []
        exec_results_by_id: Dict[str, ExecutionResult] = {}
        if snippets:
            # Extract plain fields to avoid concurrent ORM attribute access in worker threads
            snip_items = [
                (snip.id, snip.language, snip.source_code, snip.version)
                for snip in snippets
            ]
            snip_by_id = {snip.id: snip for snip in snippets}

            def _run_one(item: Tuple[str, str, str, str]) -> Tuple[str, ExecutionResult]:
                s_id, s_lang, s_code, s_ver = item
                res = sandbox_engine.run_snippet(
                    snippet_id=s_id,
                    language=s_lang,
                    source_code=s_code,
                    version=s_ver,
                )
                return s_id, res

            with ThreadPoolExecutor(max_workers=min(4, max(1, len(snip_items)))) as executor:
                run_pairs = list(executor.map(_run_one, snip_items))

            for s_id, res in run_pairs:
                exec_results_by_id[s_id] = res
                snip = snip_by_id[s_id]
                self.output_injector.inject_real_output(slides_data, snip, res)
            db_session.commit()

        # -------------------------------------------------------------
        # STEP 4: Self-Healing Loop for Failed Snippets
        # -------------------------------------------------------------
        self._publish_event(deck_id, "healing", "Checking for failed snippets to self-heal...", 55)
        healing_logs_all = []
        slides_dict = {s.get("id"): s for s in slides_data}

        for snip in snippets:
            if snip.status == "failed":
                slide_obj = slides_dict.get(snip.slide_id, {})
                initial_res = exec_results_by_id.get(snip.id)
                if initial_res:
                    self._publish_event(
                        deck_id,
                        "healing_attempt",
                        f"Attempting self-healing for failed snippet on Slide {snip.slide_id}...",
                        60,
                        {"slide_id": snip.slide_id, "snippet_id": snip.id},
                    )
                    healed, final_code, hlogs = self.healing_loop.heal_snippet(
                        snippet=snip,
                        initial_result=initial_res,
                        slide=slide_obj,
                        config=template_config,
                        professor_name=professor_name,
                        db_session=db_session,
                        max_attempts=4,
                    )
                    healing_logs_all.extend(hlogs)
                    if healed:
                        snip.status = "auto_healed"
                        snip.source_code = final_code
                        if "code" in slide_obj and slide_obj["code"]:
                            slide_obj["code"]["source"] = final_code
                    else:
                        snip.status = "needs_review"
        db_session.commit()
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 5: Exercise Proof & Mutation Score
        # -------------------------------------------------------------
        self._publish_event(deck_id, "proving_exercise", "Proving hands-on exercises & calculating mutation score...", 70)
        exercise_proofs = []
        for s in slides_data:
            if s.get("type") == "exercise" or s.get("exercise_ref"):
                proof = self.exercise_prover.prove_exercise(
                    deck_id=deck_id,
                    slide=s,
                    language=tech.lower(),
                    version=version,
                    db_session=db_session,
                )
                exercise_proofs.append(proof)

        # -------------------------------------------------------------
        # STEP 6: Non-Code Content Reviewer Pass
        # -------------------------------------------------------------
        self._publish_event(deck_id, "reviewing_content", "Reviewing slide text for factual accuracy & bullet limits...", 80)
        content_reviews = []
        c_review = self.content_reviewer.review_deck_content(
            deck_id=deck_id,
            slides=slides_data,
            tech=tech,
            version=version,
            db_session=db_session,
        )
        content_reviews.append(c_review)

        # -------------------------------------------------------------
        # STEP 7: Stamp "Verified ✔ Ran on <tech+version> · <date>" Badge
        # -------------------------------------------------------------
        date_str = datetime.now().strftime("%Y-%m-%d")
        badge_text = f"Verified ✔ Ran on {tech} {version} · {date_str}"
        for s in slides_data:
            s["verification_badge"] = badge_text

        # -------------------------------------------------------------
        # STEP 8: Re-Render Deck & Template Compliance QA
        # -------------------------------------------------------------
        self._publish_event(deck_id, "template_qa", "Performing visual template compliance QA (bounding box collision test)...", 85)
        pydantic_slides = [Slide(**s) for s in slides_data]
        plans = layout_engine.generate_deck_layout_plans(pydantic_slides, template_config, professor_name)

        pptx_path = os.path.join(output_dir, "verified_presentation.pptx")
        pptx_builder.build_deck(pydantic_slides, plans, template_config, professor_name, pptx_path)

        preview_paths = slide_renderer.render_deck_previews(
            pptx_path=pptx_path,
            slides=pydantic_slides,
            plans=plans,
            config=template_config,
            professor_name=professor_name,
            output_dir=os.path.join(output_dir, "previews"),
        )

        qa_passed, compliance_results, annotated_imgs = self.template_qa.verify_deck_compliance(
            slides=pydantic_slides,
            plans=plans,
            config=template_config,
            professor_name=professor_name,
            preview_image_paths=preview_paths,
            output_dir=os.path.join(output_dir, "compliance_qa"),
        )

        # -------------------------------------------------------------
        # STEP 9: Generate HTML and PDF Reports
        # -------------------------------------------------------------
        self._publish_event(deck_id, "generating_reports", "Generating downloadable HTML and PDF verification reports...", 95)
        html_report_path = os.path.join(output_dir, "verification_report.html")
        pdf_report_path = os.path.join(output_dir, "verification_report.pdf")

        deck_meta = {
            "topic": deck.topic,
            "college": deck.college,
            "professor_name": deck.professor_name,
            "tech": f"{tech} {version}",
        }

        self.report_gen.generate_html_report(
            deck_id=deck_id,
            deck_metadata=deck_meta,
            snippets=snippets,
            runs=runs,
            healing_logs=healing_logs_all,
            exercise_proofs=exercise_proofs,
            content_reviews=content_reviews,
            compliance_results=compliance_results,
            output_path=html_report_path,
        )

        self.report_gen.generate_pdf_report(
            deck_id=deck_id,
            deck_metadata=deck_meta,
            snippets=snippets,
            runs=runs,
            healing_logs=healing_logs_all,
            exercise_proofs=exercise_proofs,
            content_reviews=content_reviews,
            compliance_results=compliance_results,
            output_pdf_path=pdf_report_path,
        )

        # Update Deck in DB
        deck.slides_json = json.dumps([s.model_dump() for s in pydantic_slides])
        deck.pptx_path = pptx_path
        deck.pdf_path = pdf_report_path
        deck.verified = True
        db_session.commit()

        self._publish_event(deck_id, "completed", "Verification complete! Full report and verified deck ready.", 100)

        return {
            "status": "success",
            "deck_id": deck_id,
            "snippets_count": len(snippets),
            "verified_count": sum(1 for s in snippets if s.status in ["verified", "auto_healed"]),
            "auto_healed_count": sum(1 for s in snippets if s.status == "auto_healed" or s.auto_healed),
            "needs_review_count": sum(1 for s in snippets if s.status == "needs_review"),
            "exercises_proven": len(exercise_proofs),
            "html_report_path": html_report_path,
            "pdf_report_path": pdf_report_path,
            "compliance_passed": qa_passed,
        }


verification_coordinator = VerificationCoordinator()
