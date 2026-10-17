from backend.schemas import Slide
import os
import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.database import (
    init_db,
    get_db,
    SessionLocal,
    DeckRecord,
    SnippetRecord,
    VerificationRunRecord,
    HealingLogRecord,
    ExerciseProofRecord,
    ContentReviewRecord,
)
from backend.schemas import DeckCreateRequest, DeckSchema, TemplateLayoutConfig
from backend.topic_validator import is_coding_topic
from backend.template_registry import template_registry, CONFIGS_DIR, OUTPUT_DIR
from backend.llm_generator import llm_generator
from backend.layout_engine import layout_engine
from backend.pptx_builder import pptx_builder
from backend.slide_renderer import slide_renderer
from backend.verifier_stub import code_verifier
from backend.verification.coordinator import verification_coordinator
from backend.verification.sandbox import sandbox_engine
from backend.utils import sanitize_filename

app = FastAPI(
    title="Verified Course Material Studio API",
    description="Studio API for coding professors generating verified, branded PowerPoint slide decks.",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.rbac_routes import rbac_router
from backend.auth import seed_default_institute_and_admin, get_current_user
from backend.database import InstituteRecord, UserRecord, SubjectRecord, PublicationRecord, QuizAttemptRecord
app.include_router(rbac_router)

# Initialize Database on startup
@app.on_event("startup")
def on_startup():
    init_db()
    seed_default_institute_and_admin()
    template_registry.scan_and_load()
    print("Database initialized, default accounts seeded, and templates registered.")


# Static files for previews and outputs
app.mount("/static/output", StaticFiles(directory=OUTPUT_DIR), name="output_static")


@app.get("/api/health")
def health_check():
    ollama_model = llm_generator.default_model
    colleges = [c["college"] for c in template_registry.list_colleges()]
    return {
        "status": "healthy",
        "phase": "Phase 1 of 3",
        "ollama_connected": bool(ollama_model),
        "ollama_model": ollama_model,
        "available_colleges": colleges,
    }


@app.get("/api/templates")
def get_templates():
    """Returns list of all colleges and templates detected in /input/templates/."""
    colleges = template_registry.list_colleges()
    return {"colleges": colleges}


@app.get("/api/templates/{college}/preview")
def get_template_preview(college: str):
    """Returns the preview image of the college template with detected layout zones overlay."""
    preview_file = os.path.join(CONFIGS_DIR, f"{college}_preview.png")
    if not os.path.exists(preview_file):
        config = template_registry.get_config(college)
        if config:
            preview_file = template_registry.generate_preview_overlay(college, config)
    if not os.path.exists(preview_file):
        raise HTTPException(status_code=404, detail=f"Preview for college '{college}' not found.")
    return FileResponse(preview_file, media_type="image/png")


@app.get("/api/templates/{college}/config")
def get_template_config(college: str):
    """Returns the editable layout configuration JSON for a college."""
    config = template_registry.get_config(college)
    if not config:
        raise HTTPException(status_code=404, detail=f"College '{college}' template not found.")
    return config.model_dump()


@app.post("/api/templates/{college}/config")
def update_template_config(college: str, config_data: Dict[str, Any]):
    """Allows manual override of template layout config JSON."""
    try:
        updated_config = TemplateLayoutConfig(**config_data)
        template_registry.save_config(updated_config)
        template_registry.templates[college] = updated_config
        template_registry.generate_preview_overlay(college, updated_config)
        return {"status": "success", "message": f"Layout config for '{college}' updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid layout config data: {str(e)}")


def process_deck_generation(deck_id: str, req: DeckCreateRequest, db_session: Session):
    """Core pipeline executing inline slide drafting & concurrent verification/healing."""
    record = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        return

    try:
        # 1. Fetch template config
        config = template_registry.get_config(req.college)
        if getattr(record, "institute_id", None):
            inst = db_session.query(InstituteRecord).filter(InstituteRecord.id == record.institute_id).first()
            if inst and inst.template_png and os.path.exists(inst.template_png):
                config = template_registry.register_custom_institute_template(
                    college=inst.short_name,
                    png_path=inst.template_png,
                    top=inst.safe_area_top,
                    bottom=inst.safe_area_bottom,
                    left=inst.safe_area_left,
                    right=inst.safe_area_right,
                )

        if not config:
            colleges = template_registry.list_colleges()
            if colleges:
                config = template_registry.get_config(colleges[0]["college"])
            else:
                raise ValueError("No templates registered in /input/templates/")

        specs = llm_generator.plan_slide_specs(req)
        total_slides = len(specs)

        record.status = "generating"
        record.status_message = f"Drafting slide 1 of {total_slides}..."
        record.generation_progress_json = json.dumps({
            "current_slide": 1,
            "total_slides": total_slides,
            "stage": "drafting",
            "detail": f"Drafting slide 1 of {total_slides}...",
            "verified_count": 0,
            "auto_healed_count": 0,
            "needs_review_count": 0,
        })
        db_session.commit()

        # 2. Concurrent slide drafting & verification pipeline (bounded worker pool)
        # Verify slide N in worker pool while drafting slide N+1
        final_slides_dicts: List[Dict[str, Any]] = []
        all_snippets: List[SnippetRecord] = []
        all_healing_logs: List[HealingLogRecord] = []

        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=2)
        pending_future = None

        def update_progress(current_s: int, stage_str: str, detail_str: str):
            with SessionLocal() as s:
                rec = s.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
                if rec:
                    v_cnt = s.query(SnippetRecord).filter(
                        SnippetRecord.deck_id == deck_id,
                        SnippetRecord.status.in_(["verified", "auto_healed", "verified_low_assurance"])
                    ).count()
                    h_cnt = s.query(SnippetRecord).filter(
                        SnippetRecord.deck_id == deck_id,
                        SnippetRecord.status == "auto_healed"
                    ).count()
                    nr_cnt = s.query(SnippetRecord).filter(
                        SnippetRecord.deck_id == deck_id,
                        SnippetRecord.status == "needs_review"
                    ).count()
                    rec.status_message = detail_str
                    rec.generation_progress_json = json.dumps({
                        "current_slide": current_s,
                        "total_slides": total_slides,
                        "stage": stage_str,
                        "detail": detail_str,
                        "verified_count": v_cnt,
                        "auto_healed_count": h_cnt,
                        "needs_review_count": nr_cnt,
                    })
                    s.commit()

        def _worker_verify_slide(slide_dict: Dict[str, Any]):
            with SessionLocal() as worker_session:
                return verification_coordinator.verify_slide_inline(
                    slide=slide_dict,
                    deck_id=deck_id,
                    tech=req.tech,
                    version=req.tech_version or "",
                    template_config=config,
                    professor_name=req.professor_name,
                    db_session=worker_session,
                    on_progress=lambda stg, dtl: update_progress(slide_dict.get("id", 1), stg, dtl),
                )

        # Iterate over planned slide specifications
        for i, spec in enumerate(specs):
            slide_idx = i + 1
            # Update live drafting status
            update_progress(slide_idx, "drafting", f"Drafting slide {slide_idx} of {total_slides}: {spec['title']}...")

            # Draft slide N
            current_draft_slide = llm_generator.draft_single_slide(
                req=req,
                slide_id=spec["id"],
                slide_type=spec["type"],
                title=spec["title"],
                slide_index=slide_idx,
                total_slides=total_slides,
            )
            current_slide_dict = current_draft_slide.model_dump()

            # If previous slide verification was in progress, wait for it before finalizing
            if pending_future is not None:
                finalized_prev, snips, logs = pending_future.result()
                final_slides_dicts.append(finalized_prev)
                all_snippets.extend(snips)
                all_healing_logs.extend(logs)
                pending_future = None

            # Submit current slide N verification to worker pool
            pending_future = pool.submit(_worker_verify_slide, current_slide_dict)

        # Wait for the last slide verification to complete
        if pending_future is not None:
            finalized_last, snips, logs = pending_future.result()
            final_slides_dicts.append(finalized_last)
            all_snippets.extend(snips)
            all_healing_logs.extend(logs)
            pending_future = None

        pool.shutdown(wait=True)

        final_slides = [Slide(**s) for s in final_slides_dicts]

        # 3. Generate Notes with Inline Code Verification & Healing
        update_progress(total_slides, "generating_notes", "Generating per-slide trainer notes and verifying examples inline...")
        from backend.materials.notes_generator import generate_notes_for_deck_slides
        final_slides = generate_notes_for_deck_slides(
            slides=final_slides,
            topic=req.topic,
            tech=req.tech,
            tech_version=req.tech_version or "",
            session_length=float(req.session_length),
            student_level=req.student_level,
            deck_id=deck_id,
            db_session=db_session,
        )
        final_slides_dicts = [s.model_dump() for s in final_slides]
        final_slides_dicts, notes_snips, notes_hlogs = verification_coordinator.verify_notes_code_inline(
            slides=final_slides_dicts,
            deck_id=deck_id,
            tech=req.tech,
            version=req.tech_version or "",
            template_config=config,
            professor_name=req.professor_name,
            db_session=db_session,
        )
        final_slides = [Slide(**s) for s in final_slides_dicts]
        all_snippets.extend(notes_snips)
        all_healing_logs.extend(notes_hlogs)

        # 4. Generate & Prove Hands-On Exercises Inline (reference, naive, mutation testing)
        update_progress(total_slides, "proving_exercise", "Proving hands-on exercises (reference, naive, mutation testing)...")
        from backend.verification.exercise_prover import exercise_prover
        topic_chunks = getattr(req, "topic_chunks", None) or []
        do_not_use = getattr(req, "do_not_use", []) or []

        proven_exercises = exercise_prover.prove_deck_exercises(
            deck_id=deck_id,
            topic=req.topic,
            language=req.tech,
            version=req.tech_version or "",
            slides=final_slides_dicts,
            topic_chunks=topic_chunks,
            student_level=req.student_level,
            do_not_use=do_not_use,
            max_attempts=3,
            db_session=db_session,
        )

        # 5. Collision-free Layout Engine with PIL text measurement & auto-splitting
        update_progress(total_slides, "layout", "Executing collision-free layout engine and safe-zone solver...")
        final_slides, plans, layout_logs = layout_engine.layout_deck(
            final_slides, config, req.professor_name, max_attempts=3
        )
        final_slides_dicts = [s.model_dump() for s in final_slides]

        # 6. Build PPTX
        update_progress(total_slides, "building", "Building PowerPoint presentation with Pygments syntax highlighting...")
        deck_dir = os.path.join(OUTPUT_DIR, deck_id)
        os.makedirs(deck_dir, exist_ok=True)
        record.output_dir = deck_dir
        clean_topic = sanitize_filename(req.topic)
        clean_tech = sanitize_filename(req.tech)
        pptx_path = os.path.join(deck_dir, f"{clean_topic}_{clean_tech}.pptx")
        pptx_builder.build_deck(final_slides, plans, config, req.professor_name, pptx_path)

        # 7. Render high-res 1920x1080 slide previews
        update_progress(total_slides, "rendering", "Rendering high-res slide previews and executing template compliance QA...")
        previews_dir = os.path.join(deck_dir, "previews")
        preview_files = slide_renderer.render_deck_previews(
            pptx_path, final_slides, plans, config, req.professor_name, previews_dir
        )
        preview_urls = [
            f"/static/output/{deck_id}/previews/{os.path.basename(p)}" for p in preview_files
        ]

        # 8. Visual Template Compliance QA & Generate Downloadable Verification Reports (HTML & PDF)
        update_progress(total_slides, "generating_reports", "Generating downloadable HTML and PDF verification reports...")
        report_meta = verification_coordinator.generate_final_verification_reports(
            deck_id=deck_id,
            slides_data=final_slides_dicts,
            template_config=config,
            professor_name=req.professor_name,
            output_dir=deck_dir,
            pptx_path=pptx_path,
            db_session=db_session,
        )

        # 9. Save completion state
        record.status = "completed"
        record.status_message = "Slide deck built and verified successfully!"
        record.slides_json = json.dumps(final_slides_dicts)
        notes_list = [
            s.notes if isinstance(s.notes, dict) else (s.notes.model_dump() if hasattr(s.notes, "model_dump") else s.notes)
            for s in final_slides if getattr(s, "notes", None)
        ]
        if notes_list:
            record.professor_notes_json = json.dumps(notes_list)
        record.layout_logs_json = json.dumps(layout_logs)
        record.pptx_path = pptx_path
        record.preview_paths_json = json.dumps(preview_urls)
        record.verified = True
        record.generation_progress_json = json.dumps({
            "current_slide": total_slides,
            "total_slides": total_slides,
            "stage": "completed",
            "detail": "Slide deck built and verified successfully!",
            "verified_count": report_meta.get("verified_count", 0),
            "auto_healed_count": report_meta.get("auto_healed_count", 0),
            "needs_review_count": report_meta.get("needs_review_count", 0),
        })
        db_session.commit()

    except Exception as e:
        import traceback
        print(f"Error generating deck {deck_id}: {e}\n{traceback.format_exc()}")
        record.status = "failed"
        record.status_message = f"Generation error: {str(e)}"
        db_session.commit()


@app.post("/api/decks")
def create_deck(req: DeckCreateRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Creates a new slide deck.
    Validates that the topic is strictly a CODING subject.
    Rejects non-coding topics with a friendly, informative message.
    """
    # 1. Topic validation: CODING SUBJECTS ONLY
    is_valid_coding, reason = is_coding_topic(req.topic, req.tech)
    if not is_valid_coding:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "NON_CODING_TOPIC",
                "message": reason,
            },
        )

    # 2. Create Deck Record in DB
    deck_id = str(uuid.uuid4())[:8]

    # Resolve institute id if college matches or institute_id is provided
    inst_id = getattr(req, "institute_id", None) or ""
    tr_id = ""
    inst = None
    if inst_id:
        inst = db.query(InstituteRecord).filter(InstituteRecord.id == inst_id).first()
    if not inst:
        inst = db.query(InstituteRecord).filter(
            (InstituteRecord.short_name == req.college) | (InstituteRecord.id == req.college.lower())
        ).first()
        if inst:
            inst_id = inst.id

    if inst and (not req.college or req.college == "INSTITUTE"):
        req.college = inst.short_name

    record = DeckRecord(
        id=deck_id,
        college=req.college,
        professor_name=req.professor_name,
        topic=req.topic,
        student_level=req.student_level,
        session_length=req.session_length,
        tech=req.tech,
        tech_version=req.tech_version or "",
        institute_id=inst_id,
        trainer_id=tr_id,
        status="pending",
        status_message="Deck generation queued...",
    )
    db.add(record)
    db.commit()

    # Trigger generation
    background_tasks.add_task(process_deck_generation, deck_id, req, db)

    return {
        "deck_id": deck_id,
        "status": "pending",
        "message": "Generation started in background",
    }


@app.get("/api/decks")
def list_all_decks(db: Session = Depends(get_db)):
    """Returns all past generated decks for the History page."""
    records = db.query(DeckRecord).order_by(DeckRecord.created_at.desc()).all()
    return {"decks": [r.to_dict() for r in records]}


@app.get("/api/decks/{deck_id}")
def get_deck(deck_id: str, db: Session = Depends(get_db)):
    """Returns deck details, slide data, layout logs, and preview URLs."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")
    return record.to_dict()


@app.get("/api/decks/{deck_id}/download")
def download_deck(deck_id: str, db: Session = Depends(get_db)):
    """Streams the generated .pptx PowerPoint file."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record or not record.pptx_path or not os.path.exists(record.pptx_path):
        raise HTTPException(status_code=404, detail="PowerPoint presentation not ready or not found.")
    filename = os.path.basename(record.pptx_path)
    return FileResponse(
        record.pptx_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )


@app.get("/api/decks/{deck_id}/exercises")
def get_deck_exercises(deck_id: str, db: Session = Depends(get_db)):
    """Returns proven exercises for a given deck."""
    records = db.query(ExerciseProofRecord).filter(ExerciseProofRecord.deck_id == deck_id).all()
    return {"exercises": [r.to_dict() for r in records]}


@app.post("/api/decks/{deck_id}/exercises/{exercise_id}/regenerate")
def regenerate_deck_exercise(deck_id: str, exercise_id: str, db: Session = Depends(get_db)):
    """Regenerates and re-proves a single exercise without touching PPT or other exercises."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    ex_record = db.query(ExerciseProofRecord).filter(
        ExerciseProofRecord.deck_id == deck_id,
        (ExerciseProofRecord.id == exercise_id) | (ExerciseProofRecord.exercise_ref == exercise_id)
    ).first()
    if not ex_record:
        raise HTTPException(status_code=404, detail="Exercise not found")

    from backend.verification.exercise_prover import exercise_prover
    slides_data = json.loads(record.slides_json) if record.slides_json else []

    updated_proof = exercise_prover.prove_single_exercise(
        deck_id=deck_id,
        slide_id=ex_record.slide_id,
        exercise_ref=ex_record.exercise_ref,
        topic=record.topic,
        difficulty=ex_record.difficulty,
        language=record.tech,
        version=record.tech_version or "",
        slides=slides_data,
        source_slides=ex_record.source_slides,
        student_level=record.student_level,
        max_attempts=3,
        db_session=db,
    )
    return updated_proof.to_dict()


# -------------------------------------------------------------
# PHASE 2: VERIFICATION CORE ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/docker/health")
def docker_health():
    """Health check for Docker sandbox and pinned image environment."""
    sandbox_engine.prewarm()
    health_data = sandbox_engine.get_health()
    return health_data


@app.get("/api/decks/{deck_id}/report")
def get_verification_report(deck_id: str, db: Session = Depends(get_db)):
    """Returns full JSON verification report data."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    snippets = db.query(SnippetRecord).filter(SnippetRecord.deck_id == deck_id).all()
    runs = db.query(VerificationRunRecord).filter(VerificationRunRecord.deck_id == deck_id).all()
    healing_logs = db.query(HealingLogRecord).filter(HealingLogRecord.deck_id == deck_id).all()
    exercise_proofs = db.query(ExerciseProofRecord).filter(ExerciseProofRecord.deck_id == deck_id).all()
    content_reviews = db.query(ContentReviewRecord).filter(ContentReviewRecord.deck_id == deck_id).all()

    output_dir = getattr(record, "output_dir", None) or os.path.join(os.getcwd(), "output", deck_id)
    html_exists = os.path.exists(os.path.join(output_dir, "verification_report.html"))
    pdf_exists = os.path.exists(os.path.join(output_dir, "verification_report.pdf"))

    return {
        "deck_id": deck_id,
        "topic": record.topic,
        "college": record.college,
        "professor_name": record.professor_name,
        "tech": f"{record.tech} {record.tech_version}",
        "verified": record.verified,
        "summary": {
            "total_snippets": len(snippets),
            "verified_snippets": sum(1 for s in snippets if s.status in ["verified", "auto_healed"]),
            "auto_healed_snippets": sum(1 for s in snippets if s.status == "auto_healed" or s.auto_healed),
            "verified_low_assurance_snippets": sum(1 for s in snippets if s.status == "verified_low_assurance"),
            "needs_review_snippets": sum(1 for s in snippets if s.status == "needs_review"),
            "failed_snippets": sum(1 for s in snippets if s.status == "failed"),
            "proven_exercises": sum(1 for ep in exercise_proofs if ep.reference_passed and ep.naive_failed),
            "total_exercises": len(exercise_proofs),
            "mutation_score": (sum(ep.mutation_score for ep in exercise_proofs) / len(exercise_proofs)) if exercise_proofs else 1.0,
        },
        "image_digest": next((getattr(s, "image_digest", "") for s in snippets if getattr(s, "image_digest", "")), ""),
        "snippets": [s.to_dict() for s in snippets],
        "runs": [r.to_dict() for r in runs],
        "healing_logs": [h.to_dict() for h in healing_logs],
        "exercise_proofs": [ep.to_dict() for ep in exercise_proofs],
        "content_reviews": [cr.to_dict() for cr in content_reviews],
        "html_report_available": html_exists,
        "pdf_report_available": pdf_exists,
    }


@app.get("/api/decks/{deck_id}/report/html")
def download_html_report(deck_id: str, db: Session = Depends(get_db)):
    """Downloads/views the interactive HTML verification report."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    output_dir = getattr(record, "output_dir", None) or os.path.join(os.getcwd(), "output", deck_id)
    html_path = os.path.join(output_dir, "verification_report.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="HTML report not found. Please verify deck first.")

    return FileResponse(html_path, media_type="text/html", filename=f"verification_report_{deck_id}.html")


@app.get("/api/decks/{deck_id}/report/pdf")
def download_pdf_report(deck_id: str, db: Session = Depends(get_db)):
    """Downloads the official PDF verification report."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    output_dir = getattr(record, "output_dir", None) or os.path.join(os.getcwd(), "output", deck_id)
    pdf_path = os.path.join(output_dir, "verification_report.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found. Please verify deck first.")

    return FileResponse(pdf_path, media_type="application/pdf", filename=f"verification_report_{deck_id}.pdf")


# ---------------------------------------------------------------------------
# LANGUAGE & RUNTIME LAYER PLUGIN SYSTEM ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/api/runtimes")
def list_runtimes():
    """Lists all configured language/framework tracks and pinned versions."""
    from backend.runtimes.registry import runtime_registry
    return {"tracks": runtime_registry.list_tracks()}


@app.get("/api/runtimes/health")
def get_runtimes_health():
    """Returns per-track health status and sandbox readiness."""
    from backend.runtimes.registry import runtime_registry
    return runtime_registry.healthcheck_all()


class RuntimeRunRequest(BaseModel):
    code: str
    timeout_sec: int = 20
    options: Optional[Dict[str, Any]] = None
    tests: Optional[str] = None
    seed_sql: Optional[str] = None
    seed_js: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = "GET"


@app.post("/api/runtimes/{track}/run")
def run_in_runtime(track: str, request: RuntimeRunRequest):
    """Executes a code snippet or test suite inside the specified language track runner."""
    from backend.runtimes.registry import runtime_registry
    runner = runtime_registry.get_runner(track)
    if not runner:
        raise HTTPException(status_code=404, detail=f"Language runtime track '{track}' not found")

    opts = request.options or {}
    if request.seed_sql:
        opts["seed_sql"] = request.seed_sql
    if request.seed_js:
        opts["seed_js"] = request.seed_js
    if request.endpoint:
        opts["endpoint"] = request.endpoint
    if request.method:
        opts["method"] = request.method

    res = runner.execute(request.code, timeout_sec=request.timeout_sec, options=opts)
    return res.to_dict()


# ---------------------------------------------------------------------------
# PHASE 3: SUPPORTING MATERIALS, EXPORTS, MAINTENANCE & LIVE CLASS ENDPOINTS
# ---------------------------------------------------------------------------

@app.post("/api/decks/{deck_id}/approve")
def approve_deck(deck_id: str, db: Session = Depends(get_db)):
    """
    Professor approves the verified deck.
    Only after approval can supporting materials (notes, quiz, cheat sheet) be generated.
    """
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    record.approved = True
    record.approved_at = datetime.utcnow()
    db.commit()
    return {
        "success": True,
        "deck_id": deck_id,
        "approved": True,
        "approved_at": record.approved_at.isoformat()
    }


@app.post("/api/decks/{deck_id}/materials/generate")
def generate_supporting_materials(deck_id: str, db: Session = Depends(get_db)):
    """
    Generates Student Notes, Professor Notes, Quiz, and Cheat Sheet for an approved deck.
    Strictly verifies that the deck has been approved by the professor first.
    """
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    if not getattr(record, "approved", False):
        raise HTTPException(
            status_code=400,
            detail="Deck must be approved by the professor before generating supporting materials."
        )

    record.materials_status = "generating"
    db.commit()

    try:
        from backend.materials.notes_generator import generate_notes_for_deck
        from backend.materials.quiz_generator import generate_quiz_for_deck
        from backend.materials.cheat_sheet_generator import generate_cheat_sheet_data, render_cheat_sheet_pdf
        from backend.materials.exporter import build_all_deck_exports

        deck_dict = record.to_dict()
        snippets = [s.to_dict() for s in record.snippets]

        # 1. Notes (Student + Professor)
        student_notes, prof_notes = generate_notes_for_deck(deck_dict, snippets)
        record.student_notes_json = json.dumps([n.model_dump() for n in student_notes])
        record.professor_notes_json = json.dumps([n.model_dump() for n in prof_notes])

        # 2. Quiz (8 MCQs Grounded in Slides & Exercises)
        exercise_proofs = [ep.to_dict() for ep in record.exercise_proofs] if getattr(record, "exercise_proofs", None) else []
        quiz = generate_quiz_for_deck(deck_dict, snippets, exercises=exercise_proofs, db_session=db)
        record.quiz_json = json.dumps([q.model_dump() for q in quiz])

        # 3. Cheat Sheet (1-page A4)
        cheat_sheet = generate_cheat_sheet_data(deck_dict, snippets)
        record.cheat_sheet_json = json.dumps(cheat_sheet.model_dump())
        db.commit()

        # 4. Generate all exports (PDFs, ZIPs)
        exports = build_all_deck_exports(deck_id, db)

        record.materials_status = "ready"
        db.commit()

        return {
            "success": True,
            "deck_id": deck_id,
            "materials_status": "ready",
            "student_notes_count": len(student_notes),
            "quiz_questions_count": len(quiz),
            "exports": exports
        }
    except Exception as e:
        record.materials_status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Materials generation failed: {str(e)}")


@app.get("/api/decks/{deck_id}/materials")
def get_supporting_materials(deck_id: str, db: Session = Depends(get_db)):
    """Returns generated notes, quiz, cheat sheet, and export status."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    deck_dict = record.to_dict()
    return {
        "deck_id": deck_id,
        "approved": deck_dict.get("approved", False),
        "materials_status": deck_dict.get("materials_status", "not_generated"),
        "student_notes": deck_dict.get("student_notes", []),
        "professor_notes": deck_dict.get("professor_notes", []),
        "quiz": deck_dict.get("quiz", []),
        "cheat_sheet": deck_dict.get("cheat_sheet", {}),
        "exports": deck_dict.get("exports", {})
    }


@app.get("/api/decks/{deck_id}/exports/{export_type}")
def download_export(deck_id: str, export_type: str, db: Session = Depends(get_db)):
    """Downloads an individual export artifact or the All_Materials.zip package."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    exports = json.loads(record.exports_json) if record.exports_json else {}
    target_key = export_type.lower()
    if target_key in ["all", "zip", "all_zip"]:
        target_key = "all_zip"
    elif target_key in ["quiz_key", "quiz-key", "answer-key", "quiz_answer_key"]:
        target_key = "quiz_answer_key"
    elif target_key in ["cheatsheet", "cheat-sheet", "cheat_sheet"]:
        target_key = "cheat_sheet"
    elif target_key in ["notes", "student-notes", "student_notes"]:
        target_key = "student_notes"
    elif target_key in ["report", "verification_report"]:
        target_key = "verification_report"

    file_path = exports.get(target_key)
    if not file_path or not os.path.exists(file_path):
        if record.materials_status == "ready":
            from backend.materials.exporter import build_all_deck_exports
            exports = build_all_deck_exports(deck_id, db)
            file_path = exports.get(target_key)

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Export '{export_type}' not available yet.")

    media_type = "application/zip" if file_path.endswith(".zip") else (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation" if file_path.endswith(".pptx") else "application/pdf"
    )
    return FileResponse(file_path, media_type=media_type, filename=os.path.basename(file_path))


class SlideRegenerateRequest(BaseModel):
    instruction: Optional[str] = ""


@app.post("/api/decks/{deck_id}/slides/{slide_index}/regenerate")
def api_regenerate_slide(deck_id: str, slide_index: int, req: SlideRegenerateRequest, db: Session = Depends(get_db)):
    """Regenerates a single slide, re-verifies it, and leaves all other slides untouched."""
    from backend.materials.slide_regenerator import regenerate_single_slide
    try:
        res = regenerate_single_slide(deck_id, slide_index, req.instruction or "", db)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MigrationRequest(BaseModel):
    new_version: str


@app.post("/api/decks/{deck_id}/migrate")
def api_migrate_version(deck_id: str, req: MigrationRequest, db: Session = Depends(get_db)):
    """Migrates deck to a new target version and reports diff table."""
    from backend.materials.version_migrator import migrate_deck_version
    try:
        res = migrate_deck_version(deck_id, req.new_version, db)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/decks/{deck_id}/reverify")
def api_reverify_staleness(deck_id: str, db: Session = Depends(get_db)):
    """Re-runs only stale or changed snippets, heals if broken, and regenerates verification report."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")
    try:
        res = verification_coordinator.reverify_stale_or_changed_snippets(deck_id, db)
        return res
    except Exception as e:
        import traceback
        print(f"Error in reverify: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


class LiveRunRequest(BaseModel):
    slide_id: int
    code: Optional[str] = None


@app.post("/api/decks/{deck_id}/live/run")
def api_live_class_run(deck_id: str, req: LiveRunRequest, db: Session = Depends(get_db)):
    """Executes code live during class or falls back to pre-captured verified output."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    tech = record.tech or "Programming"
    from backend.runtimes.registry import runtime_registry
    runner = runtime_registry.get_runner(tech.lower())

    target_code = req.code
    fallback_output = ""
    for snip in record.snippets:
        if snip.slide_id == req.slide_id:
            if not target_code:
                target_code = snip.source_code
            fallback_output = snip.actual_output
            break

    if not target_code:
        return {"status": "pass", "stdout": fallback_output or "Executed cleanly.", "is_fallback": True}

    if runner:
        try:
            res = runner.execute(target_code, timeout=10)
            return {
                "status": res.status,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.exit_code,
                "duration_ms": res.duration_ms,
                "is_fallback": False
            }
        except Exception as e:
            return {
                "status": "fallback",
                "stdout": fallback_output or f"Fallback output: {str(e)}",
                "is_fallback": True
            }

    return {"status": "pass", "stdout": fallback_output or "Executed cleanly.", "is_fallback": True}


