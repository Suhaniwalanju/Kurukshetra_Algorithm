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
        topic = getattr(deck, "topic", "Course Deck") or "Course Deck"
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
        # STEP 2: Parallel Sandbox Execution (Double run for determinism)
        # -------------------------------------------------------------
        executable_snippets = [s for s in snippets if getattr(s, "was_executed", True)]
        self._publish_event(
            deck_id,
            "executing",
            f"Running {len(executable_snippets)} executable snippets twice in isolated sandbox to verify determinism...",
            30,
            {"snippet_count": len(executable_snippets)},
        )

        runs = []
        exec_results_by_id: Dict[str, ExecutionResult] = {}
        if executable_snippets:
            # Extract plain fields to avoid concurrent ORM attribute access in worker threads
            snip_items = [
                (snip.id, snip.language, snip.source_code, snip.version)
                for snip in executable_snippets
            ]
            snip_by_id = {snip.id: snip for snip in executable_snippets}

            def _run_one(item: Tuple[str, str, str, str]) -> Tuple[str, ExecutionResult]:
                s_id, s_lang, s_code, s_ver = item
                # Run 1
                res1 = sandbox_engine.run_snippet(
                    snippet_id=s_id,
                    language=s_lang,
                    source_code=s_code,
                    version=s_ver,
                )
                # Run 2: determinism check
                res2 = sandbox_engine.run_snippet(
                    snippet_id=f"{s_id}_det_check",
                    language=s_lang,
                    source_code=s_code,
                    version=s_ver,
                )
                out1 = (res1.stdout or "").strip()
                out2 = (res2.stdout or "").strip()
                if out1 != out2:
                    res1.is_non_deterministic = True
                    res1.non_deterministic_details = f"Run 1: '{out1}' vs Run 2: '{out2}'"
                return s_id, res1

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
                            if slide_obj.get("type") == "concept":
                                from backend.materials.concept_examples import extract_code_excerpt
                                slide_obj["code"]["source"] = extract_code_excerpt(final_code, snip.language)
                                if isinstance(slide_obj.get("notes"), dict):
                                    ex_obj = slide_obj["notes"].get("example")
                                    if isinstance(ex_obj, dict):
                                        ex_obj["full_code"] = final_code
                                    slide_obj["notes"]["full_file"] = final_code
                            else:
                                slide_obj["code"]["source"] = final_code
                    else:
                        snip.status = "needs_review"
        db_session.commit()
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 5: Exercise Proof & Mutation Score (3 exercises: easy, medium, stretch)
        # -------------------------------------------------------------
        self._publish_event(deck_id, "proving_exercise", "Proving 3 hands-on exercises (easy, medium, stretch) & mutation score...", 70)
        exercise_proofs = self.exercise_prover.prove_deck_exercises(
            deck_id=deck_id,
            topic=topic,
            language=tech.lower(),
            version=version,
            slides=slides_data,
            max_attempts=3,
            db_session=db_session,
        )

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
        # STEP 7: Stamp Verification Badge According to Strict Rules:
        # 1. Appears only on slides where every snippet is verified or auto_healed AND ran with sandbox_backend == "docker"
        # 2. Uses real runtime version recorded from the container in the badge
        # 3. Slides with needs_review snippets get a visible "Unverified" badge
        # 4. Slides with no code get no badge
        # 5. If fallback process backend was used, never show the green badge
        # -------------------------------------------------------------
        date_str = datetime.now().strftime("%Y-%m-%d")
        snips_by_slide: Dict[int, List[SnippetRecord]] = {}
        for sn in snippets:
            snips_by_slide.setdefault(sn.slide_id, []).append(sn)

        for s in slides_data:
            s_id = s.get("id")
            s_snips = snips_by_slide.get(s_id, [])
            code_obj = s.get("code")
            has_code = bool((code_obj and isinstance(code_obj, dict) and code_obj.get("source", "").strip()) or s_snips)

            if not has_code:
                # Slides with no code get no badge
                s["verification_badge"] = None
            else:
                has_needs_review = any(sn.status == "needs_review" for sn in s_snips)
                has_failed = any(sn.status == "failed" for sn in s_snips)
                has_low_assurance = any(sn.status == "verified_low_assurance" or getattr(sn, "sandbox_backend", "") != "docker" for sn in s_snips)
                all_verified_docker = (
                    len(s_snips) > 0
                    and all(
                        sn.status in ["verified", "auto_healed"] and getattr(sn, "sandbox_backend", "") == "docker"
                        for sn in s_snips
                    )
                )

                if has_needs_review or has_failed:
                    # Slides with needs_review snippets get a visible "Unverified" badge
                    s["verification_badge"] = "Unverified"
                elif all_verified_docker:
                    # Verified in Docker: use real runtime version string recorded from container
                    real_v = next((sn.real_runtime_version for sn in s_snips if getattr(sn, "real_runtime_version", "")), None)
                    runtime_str = real_v if real_v else f"{tech} {version}"
                    s["verification_badge"] = f"Verified ✔ Ran on {runtime_str} · {date_str}"
                elif has_low_assurance:
                    # Fallback process backend was used: never show the green badge
                    s["verification_badge"] = "Unverified"
                else:
                    s["verification_badge"] = "Unverified"

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

        # Discover or query image digest
        img_digest = next((sn.image_digest for sn in snippets if getattr(sn, "image_digest", "")), "")
        if not img_digest:
            img_digest = sandbox_engine.get_image_digest(tech)

        deck_meta = {
            "topic": deck.topic,
            "college": deck.college,
            "professor_name": deck.professor_name,
            "tech": f"{tech} {version}",
            "image_digest": img_digest,
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
