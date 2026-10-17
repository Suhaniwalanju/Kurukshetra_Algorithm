import os
import json
import uuid
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

    def verify_slide_inline(
        self,
        slide: Dict[str, Any],
        deck_id: str,
        tech: str,
        version: str,
        template_config: Any,
        professor_name: str,
        db_session: Session,
        on_progress: Optional[Callable[[str, str], None]] = None,
    ) -> Tuple[Dict[str, Any], List[SnippetRecord], List[HealingLogRecord]]:
        """
        Inline verification for a single slide immediately after it is drafted.
        Extracts code, executes in sandbox, heals if failed (up to 4 attempts),
        injects real output, stamps verification badge, and saves records.
        """
        code_obj = slide.get("code")
        if not code_obj or not isinstance(code_obj, dict) or not (code_obj.get("source") or "").strip():
            slide["verification_badge"] = None
            return slide, [], []

        s_id = slide.get("id", 1)
        source_code = code_obj.get("source", "").strip()
        lang = (code_obj.get("language") or tech).lower()
        ver = code_obj.get("version") or version
        expected_output = code_obj.get("expected_output") or ""

        snip_id = f"snip_{deck_id}_s{s_id}"
        snip = db_session.query(SnippetRecord).filter(SnippetRecord.id == snip_id).first()
        if snip:
            snip.source_code = source_code
            snip.language = lang
            snip.version = ver
            snip.expected_output = expected_output
        else:
            snip = SnippetRecord(
                id=snip_id,
                deck_id=deck_id,
                slide_id=s_id,
                snippet_type="code",
                language=lang,
                version=ver,
                source_code=source_code,
                expected_output=expected_output,
                source_location="slide_code",
                status="pending",
            )
            db_session.add(snip)
        db_session.commit()

        if on_progress:
            on_progress("running code", f"Executing code on Slide {s_id} in sandbox...")

        # Run 1: Primary execution
        res1 = sandbox_engine.run_snippet(
            snippet_id=snip.id,
            language=lang,
            source_code=source_code,
            version=ver,
        )
        # Run 2: Determinism check
        res2 = sandbox_engine.run_snippet(
            snippet_id=f"{snip.id}_det",
            language=lang,
            source_code=source_code,
            version=ver,
        )
        out1 = (res1.stdout or "").strip()
        out2 = (res2.stdout or "").strip()
        if out1 != out2:
            res1.is_non_deterministic = True
            res1.non_deterministic_details = f"Run 1: '{out1}' vs Run 2: '{out2}'"

        snip.actual_output = res1.stdout or ""
        snip.stderr = res1.stderr or ""
        snip.compiler_output = res1.compiler_output or ""
        snip.exit_code = res1.exit_code
        snip.duration_ms = res1.duration_ms
        snip.command_executed = res1.command_executed or ""
        snip.sandbox_backend = res1.sandbox_backend or "docker"
        snip.real_runtime_version = res1.real_runtime_version or ""
        snip.image_digest = res1.image_digest or ""
        snip.classification = res1.classification or "PASS"
        snip.is_non_deterministic = res1.is_non_deterministic
        snip.deprecation_details = res1.deprecation_details or ""

        healing_logs: List[HealingLogRecord] = []

        if (getattr(res1, "status", None) == "pass" or res1.exit_code == 0) and res1.exit_code == 0 and not getattr(res1, "timed_out", False):
            if res1.sandbox_backend == "docker":
                snip.status = "verified"
            else:
                snip.status = "verified_low_assurance"
            self.output_injector.inject_real_output([slide], snip, res1)
        else:
            snip.status = "failed"
            # Trigger self-healing loop
            def handle_healing_attempt(att, total):
                if on_progress:
                    on_progress(f"healing attempt {att} of {total}", f"Auto-healing failed code on Slide {s_id} (attempt {att} of {total})...")

            healed, final_code, hlogs = self.healing_loop.heal_snippet(
                snippet=snip,
                initial_result=res1,
                slide=slide,
                config=template_config,
                professor_name=professor_name,
                db_session=db_session,
                max_attempts=4,
                on_attempt=handle_healing_attempt,
            )
            healing_logs.extend(hlogs)
            if healed:
                snip.status = "auto_healed"
                snip.source_code = final_code
                slide["code"]["source"] = final_code
                # Re-run in sandbox to capture final real output
                res_healed = sandbox_engine.run_snippet(
                    snippet_id=f"{snip.id}_healed_output",
                    language=lang,
                    source_code=final_code,
                    version=ver,
                )
                self.output_injector.inject_real_output([slide], snip, res_healed)
                snip.actual_output = res_healed.stdout or ""
                snip.exit_code = res_healed.exit_code
                snip.command_executed = res_healed.command_executed or snip.command_executed
            else:
                snip.status = "needs_review"

        # Badge stamping according to strict rules:
        # A slide is only emitted as final when it is verified, auto_healed, or flagged needs_review after max attempts.
        # Never emit an unverified slide with a verified badge.
        date_str = datetime.now().strftime("%Y-%m-%d")
        if snip.status == "needs_review" or snip.status == "failed":
            slide["verification_badge"] = "Unverified"
        elif snip.status in ["verified", "auto_healed"] and snip.sandbox_backend == "docker":
            real_v = snip.real_runtime_version or f"{tech} {ver}"
            slide["verification_badge"] = f"Verified ✔ Ran on {real_v} · {date_str}"
        else:
            slide["verification_badge"] = "Unverified"

        db_session.commit()
        return slide, [snip], healing_logs

    def verify_notes_code_inline(
        self,
        slides: List[Dict[str, Any]],
        deck_id: str,
        tech: str,
        version: str,
        template_config: Any,
        professor_name: str,
        db_session: Session,
    ) -> Tuple[List[Dict[str, Any]], List[SnippetRecord], List[HealingLogRecord]]:
        """Verifies code blocks inside trainer notes inline."""
        notes_snips = []
        notes_hlogs = []
        for s in slides:
            notes_obj = s.get("notes")
            if not isinstance(notes_obj, dict):
                continue
            example_obj = notes_obj.get("example")
            example_code = ""
            if isinstance(example_obj, dict):
                example_code = example_obj.get("full_code") or example_obj.get("code") or ""
            elif isinstance(example_obj, str):
                example_code = example_obj
            if not example_code.strip():
                example_code = notes_obj.get("full_file") or ""

            if example_code.strip():
                snip_id = f"snip_{deck_id}_notes_s{s.get('id', 1)}"
                lang = tech.lower()
                ver = version or ""
                snip = db_session.query(SnippetRecord).filter(SnippetRecord.id == snip_id).first()
                if not snip:
                    snip = SnippetRecord(
                        id=snip_id,
                        deck_id=deck_id,
                        slide_id=s.get("id", 1),
                        snippet_type="code",
                        language=lang,
                        version=ver,
                        source_code=example_code,
                        source_location="trainer_notes",
                        status="pending",
                    )
                    db_session.add(snip)
                    db_session.commit()

                res = sandbox_engine.run_snippet(snip.id, lang, example_code, ver)
                snip.actual_output = res.stdout or ""
                snip.stderr = res.stderr or ""
                snip.exit_code = res.exit_code
                snip.duration_ms = res.duration_ms
                snip.command_executed = res.command_executed or ""
                snip.sandbox_backend = res.sandbox_backend or "docker"
                snip.real_runtime_version = res.real_runtime_version or ""

                if (getattr(res, "status", None) == "pass" or res.exit_code == 0) and res.exit_code == 0 and not getattr(res, "timed_out", False):
                    snip.status = "verified" if res.sandbox_backend == "docker" else "verified_low_assurance"
                else:
                    snip.status = "failed"
                    healed, final_code, hlogs = self.healing_loop.heal_snippet(
                        snippet=snip,
                        initial_result=res,
                        slide=s,
                        config=template_config,
                        professor_name=professor_name,
                        db_session=db_session,
                        max_attempts=4,
                    )
                    notes_hlogs.extend(hlogs)
                    if healed:
                        snip.status = "auto_healed"
                        snip.source_code = final_code
                        if isinstance(notes_obj.get("example"), dict):
                            notes_obj["example"]["full_code"] = final_code
                    else:
                        snip.status = "needs_review"
                db_session.commit()
                notes_snips.append(snip)

        return slides, notes_snips, notes_hlogs

    def verify_quiz_code_inline(
        self,
        quiz_items: List[Dict[str, Any]],
        deck_id: str,
        tech: str,
        version: str,
        template_config: Any,
        professor_name: str,
        db_session: Session,
    ) -> Tuple[List[Dict[str, Any]], List[SnippetRecord], List[HealingLogRecord]]:
        """Verifies code blocks inside quiz items inline."""
        quiz_snips = []
        quiz_hlogs = []
        import re
        for idx, q in enumerate(quiz_items):
            code_text = ""
            for field in [q.get("question", ""), q.get("code", ""), q.get("explanation", "")]:
                if "```" in field:
                    match = re.search(r"```(?:[a-zA-Z0-9_-]+)?\s*([\s\S]*?)\s*```", field)
                    if match:
                        code_text = match.group(1).strip()
                        break
                elif field and ("class " in field or "def " in field or "System.out" in field or "SELECT " in field or "console.log" in field):
                    code_text = field.strip()
                    break

            if code_text:
                snip_id = f"snip_{deck_id}_quiz_{idx+1}"
                lang = tech.lower()
                ver = version or ""
                snip = db_session.query(SnippetRecord).filter(SnippetRecord.id == snip_id).first()
                if not snip:
                    snip = SnippetRecord(
                        id=snip_id,
                        deck_id=deck_id,
                        slide_id=q.get("source_slide_id") or (idx + 1),
                        snippet_type="quiz",
                        language=lang,
                        version=ver,
                        source_code=code_text,
                        source_location="quiz_item",
                        status="pending",
                    )
                    db_session.add(snip)
                    db_session.commit()

                res = sandbox_engine.run_snippet(snip.id, lang, code_text, ver)
                snip.actual_output = res.stdout or ""
                snip.stderr = res.stderr or ""
                snip.exit_code = res.exit_code
                snip.duration_ms = res.duration_ms
                snip.command_executed = res.command_executed or ""
                snip.sandbox_backend = res.sandbox_backend or "docker"
                snip.real_runtime_version = res.real_runtime_version or ""

                if (getattr(res, "status", None) == "pass" or res.exit_code == 0) and res.exit_code == 0 and not getattr(res, "timed_out", False):
                    snip.status = "verified" if res.sandbox_backend == "docker" else "verified_low_assurance"
                else:
                    snip.status = "failed"
                    fake_slide = {"id": snip.slide_id, "title": q.get("question", "Quiz Question")}
                    healed, final_code, hlogs = self.healing_loop.heal_snippet(
                        snippet=snip,
                        initial_result=res,
                        slide=fake_slide,
                        config=template_config,
                        professor_name=professor_name,
                        db_session=db_session,
                        max_attempts=4,
                    )
                    quiz_hlogs.extend(hlogs)
                    if healed:
                        snip.status = "auto_healed"
                        snip.source_code = final_code
                    else:
                        snip.status = "needs_review"
                db_session.commit()
                quiz_snips.append(snip)

        return quiz_items, quiz_snips, quiz_hlogs

    def generate_final_verification_reports(
        self,
        deck_id: str,
        slides_data: List[Dict[str, Any]],
        template_config: Any,
        professor_name: str,
        output_dir: str,
        pptx_path: str,
        db_session: Session,
    ) -> Dict[str, Any]:
        """
        Executes non-code content review, visual compliance QA, and generates
        HTML and PDF verification reports immediately before the deck completes.
        """
        deck = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        if not deck:
            raise ValueError(f"Deck {deck_id} not found")

        tech = getattr(deck, "tech", "Java")
        version = getattr(deck, "tech_version", "21") or "21"

        snippets = db_session.query(SnippetRecord).filter(SnippetRecord.deck_id == deck_id).all()
        healing_logs = db_session.query(HealingLogRecord).filter(HealingLogRecord.deck_id == deck_id).all()
        exercise_proofs = db_session.query(ExerciseProofRecord).filter(ExerciseProofRecord.deck_id == deck_id).all()

        # 1. Non-code content review
        c_review = self.content_reviewer.review_deck_content(
            deck_id=deck_id,
            slides=slides_data,
            tech=tech,
            version=version,
            db_session=db_session,
        )
        content_reviews = [c_review]

        # 2. Template compliance QA
        pydantic_slides = [Slide(**s) for s in slides_data]
        plans = layout_engine.generate_deck_layout_plans(pydantic_slides, template_config, professor_name)
        preview_dir = os.path.join(output_dir, "previews")
        preview_paths = slide_renderer.render_deck_previews(
            pptx_path=pptx_path,
            slides=pydantic_slides,
            plans=plans,
            config=template_config,
            professor_name=professor_name,
            output_dir=preview_dir,
        )

        qa_passed, compliance_results, annotated_imgs = self.template_qa.verify_deck_compliance(
            slides=pydantic_slides,
            plans=plans,
            config=template_config,
            professor_name=professor_name,
            preview_image_paths=preview_paths,
            output_dir=os.path.join(output_dir, "compliance_qa"),
        )

        # 3. HTML and PDF Reports
        html_report_path = os.path.join(output_dir, "verification_report.html")
        pdf_report_path = os.path.join(output_dir, "verification_report.pdf")

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

        runs = []
        self.report_gen.generate_html_report(
            deck_id=deck_id,
            deck_metadata=deck_meta,
            snippets=snippets,
            runs=runs,
            healing_logs=healing_logs,
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
            healing_logs=healing_logs,
            exercise_proofs=exercise_proofs,
            content_reviews=content_reviews,
            compliance_results=compliance_results,
            output_pdf_path=pdf_report_path,
        )

        # 4. Save VerificationRunRecord
        v_run = VerificationRunRecord(
            id=str(uuid.uuid4())[:12] if 'uuid' in globals() else f"vrun_{deck_id}",
            deck_id=deck_id,
            status="completed",
            status_message="Inline verification & QA complete.",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            total_snippets=len(snippets),
            verified_count=sum(1 for s in snippets if s.status in ["verified", "auto_healed", "verified_low_assurance"]),
            fixed_count=sum(1 for s in snippets if s.status == "auto_healed" or s.auto_healed),
            needs_review_count=sum(1 for s in snippets if s.status == "needs_review"),
            exercises_proven_count=len(exercise_proofs),
            mutation_score=(sum(ep.mutation_score for ep in exercise_proofs) / len(exercise_proofs)) if exercise_proofs else 100.0,
            layout_passed=qa_passed,
            report_html_path=html_report_path,
            report_pdf_path=pdf_report_path,
            summary_json=json.dumps({
                "total_snippets": len(snippets),
                "verified": sum(1 for s in snippets if s.status in ["verified", "auto_healed", "verified_low_assurance"]),
                "auto_healed": sum(1 for s in snippets if s.status == "auto_healed" or s.auto_healed),
                "needs_review": sum(1 for s in snippets if s.status == "needs_review"),
                "exercises_proven": len(exercise_proofs),
            }),
        )
        db_session.add(v_run)

        deck.verified = True
        deck.pdf_path = pdf_report_path
        db_session.commit()

        return {
            "html_report_path": html_report_path,
            "pdf_report_path": pdf_report_path,
            "compliance_passed": qa_passed,
            "verified_count": v_run.verified_count,
            "auto_healed_count": v_run.fixed_count,
            "needs_review_count": v_run.needs_review_count,
        }

    def reverify_stale_or_changed_snippets(
        self,
        deck_id: str,
        db_session: Session,
    ) -> Dict[str, Any]:
        """
        Re-verifies only stale or changed snippets in an existing deck.
        Checks for changed code, non-zero exits, or needs_review items,
        re-runs sandbox & healing, updates SnippetRecords, and regenerates reports.
        """
        deck = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
        if not deck:
            raise ValueError(f"Deck {deck_id} not found")

        snippets = db_session.query(SnippetRecord).filter(SnippetRecord.deck_id == deck_id).all()
        slides_data = json.loads(deck.slides_json) if deck.slides_json else []
        slides_by_id = {s.get("id"): s for s in slides_data}

        # Identify stale or changed snippets
        stale_snippets: List[SnippetRecord] = []
        for sn in snippets:
            slide = slides_by_id.get(sn.slide_id)
            code_in_slide = ""
            if slide and isinstance(slide.get("code"), dict):
                code_in_slide = slide["code"].get("source", "").strip()

            is_changed = code_in_slide and (code_in_slide != sn.source_code.strip())
            is_unverified_or_failed = sn.status in ["needs_review", "failed", "pending"]
            if is_changed or is_unverified_or_failed:
                if is_changed:
                    sn.source_code = code_in_slide
                stale_snippets.append(sn)

        # If no snippets are flagged as changed or failed, re-run all as safety check
        snippets_to_run = stale_snippets if stale_snippets else snippets

        reverified_count = 0
        healed_count = 0
        template_config = template_registry.get_config(deck.college)
        if not template_config and template_registry.templates:
            template_config = list(template_registry.templates.values())[0]

        for sn in snippets_to_run:
            slide = slides_by_id.get(sn.slide_id, {})
            res = sandbox_engine.run_snippet(
                snippet_id=f"{sn.id}_reverify",
                language=sn.language,
                source_code=sn.source_code,
                version=sn.version,
            )
            sn.actual_output = res.stdout or ""
            sn.stderr = res.stderr or ""
            sn.compiler_output = res.compiler_output or ""
            sn.exit_code = res.exit_code
            sn.duration_ms = res.duration_ms
            sn.command_executed = res.command_executed or sn.command_executed
            sn.sandbox_backend = res.sandbox_backend or "docker"
            sn.real_runtime_version = res.real_runtime_version or ""

            if (getattr(res, "status", None) == "pass" or res.exit_code == 0) and res.exit_code == 0 and not getattr(res, "timed_out", False):
                sn.status = "verified" if res.sandbox_backend == "docker" else "verified_low_assurance"
                reverified_count += 1
            else:
                # Heal if broken
                healed, final_code, hlogs = self.healing_loop.heal_snippet(
                    snippet=sn,
                    initial_result=res,
                    slide=slide,
                    config=template_config,
                    professor_name=deck.professor_name,
                    db_session=db_session,
                    max_attempts=4,
                )
                if healed:
                    sn.status = "auto_healed"
                    sn.source_code = final_code
                    if slide and "code" in slide and isinstance(slide["code"], dict):
                        slide["code"]["source"] = final_code
                    healed_count += 1
                else:
                    sn.status = "needs_review"
            db_session.commit()

        # Update badges on slides
        date_str = datetime.now().strftime("%Y-%m-%d")
        snips_by_slide = {}
        for sn in snippets:
            snips_by_slide.setdefault(sn.slide_id, []).append(sn)

        for s in slides_data:
            s_snips = snips_by_slide.get(s.get("id"), [])
            if not s_snips:
                continue
            if any(sn.status in ["needs_review", "failed"] for sn in s_snips):
                s["verification_badge"] = "Unverified"
            elif all(sn.status in ["verified", "auto_healed"] and sn.sandbox_backend == "docker" for sn in s_snips):
                real_v = next((sn.real_runtime_version for sn in s_snips if sn.real_runtime_version), None) or deck.tech
                s["verification_badge"] = f"Verified ✔ Ran on {real_v} · {date_str}"
            else:
                s["verification_badge"] = "Unverified"

        deck.slides_json = json.dumps(slides_data)
        db_session.commit()

        # Re-generate reports
        output_dir = deck.output_dir or os.path.join(os.getcwd(), "output", deck_id)
        report_meta = self.generate_final_verification_reports(
            deck_id=deck_id,
            slides_data=slides_data,
            template_config=template_config,
            professor_name=deck.professor_name,
            output_dir=output_dir,
            pptx_path=deck.pptx_path,
            db_session=db_session,
        )

        return {
            "success": True,
            "deck_id": deck_id,
            "stale_checked": len(snippets_to_run),
            "reverified_count": reverified_count,
            "healed_count": healed_count,
            "total_snippets": len(snippets),
            "report_summary": report_meta,
        }


verification_coordinator = VerificationCoordinator()
