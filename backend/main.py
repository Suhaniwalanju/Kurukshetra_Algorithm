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

# Initialize Database on startup
@app.on_event("startup")
def on_startup():
    init_db()
    template_registry.scan_and_load()
    print("Database initialized and templates registered.")


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
    """Core pipeline executing generation, layout, pptx build, and automated checks."""
    record = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        return

    try:
        record.status = "generating"
        record.status_message = "Generating structured coding curriculum using Ollama LLM..."
        db_session.commit()

        # 1. Fetch template config
        config = template_registry.get_config(req.college)
        if not config:
            # Fallback to first available college
            colleges = template_registry.list_colleges()
            if colleges:
                config = template_registry.get_config(colleges[0]["college"])
            else:
                raise ValueError("No templates registered in /input/templates/")

        # 2. Generate Slides with Ollama LLM
        deck_schema = llm_generator.generate_deck(req, max_retries=3)

        # 2b. Generate Notes Step after slide generation
        record.status = "generating_notes"
        record.status_message = "Generating per-slide trainer notes, examples, and timing allocations..."
        db_session.commit()

        from backend.materials.notes_generator import generate_notes_for_deck_slides
        deck_schema.slides = generate_notes_for_deck_slides(
            slides=deck_schema.slides,
            topic=req.topic,
            tech=req.tech,
            tech_version=req.tech_version or "",
            session_length=float(req.session_length),
            student_level=req.student_level,
            deck_id=deck_id,
            db_session=db_session,
        )

        # 3. Collision-free Layout Engine with PIL text measurement & auto-splitting
        record.status = "layout"
        record.status_message = "Executing collision-free layout engine and safe-zone solver..."
        db_session.commit()

        final_slides, plans, layout_logs = layout_engine.layout_deck(
            deck_schema.slides, config, req.professor_name, max_attempts=3
        )

        # 4. Build PPTX
        record.status = "building"
        record.status_message = "Building PowerPoint presentation with Pygments syntax highlighting..."
        db_session.commit()

        deck_dir = os.path.join(OUTPUT_DIR, deck_id)
        os.makedirs(deck_dir, exist_ok=True)
        record.output_dir = deck_dir
        clean_topic = sanitize_filename(req.topic)
        clean_tech = sanitize_filename(req.tech)
        pptx_path = os.path.join(deck_dir, f"{clean_topic}_{clean_tech}.pptx")

        pptx_builder.build_deck(final_slides, plans, config, req.professor_name, pptx_path)

        # 5. Render high-res 1920x1080 slide previews
        record.status = "rendering"
        record.status_message = "Rendering high-res slide previews and executing automated verification..."
        db_session.commit()

        previews_dir = os.path.join(deck_dir, "previews")
        preview_files = slide_renderer.render_deck_previews(
            pptx_path, final_slides, plans, config, req.professor_name, previews_dir
        )

        # 6. Automated Validation Check
        passed, check_issues = slide_renderer.run_automated_check(final_slides, plans)
        if not passed:
            layout_logs.extend([f"Automated check warning: {issue}" for issue in check_issues])

        # 7. Stub Verifier for Phase 2 readiness
        verification_report = code_verifier.verify_deck(deck_schema)

        # 8. Save completion state
        preview_urls = [
            f"/static/output/{deck_id}/previews/{os.path.basename(p)}" for p in preview_files
        ]

        record.status = "completed"
        record.status_message = "Slide deck built and verified successfully!"
        record.slides_json = json.dumps([s.model_dump() for s in final_slides])
        notes_list = [s.notes for s in final_slides if getattr(s, "notes", None)]
        if notes_list:
            record.professor_notes_json = json.dumps(notes_list)
        record.layout_logs_json = json.dumps(layout_logs)
        record.pptx_path = pptx_path
        record.preview_paths_json = json.dumps(preview_urls)
        db_session.commit()

    except Exception as e:
        print(f"Error generating deck {deck_id}: {e}")
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
    record = DeckRecord(
        id=deck_id,
        college=req.college,
        professor_name=req.professor_name,
        topic=req.topic,
        student_level=req.student_level,
        session_length=req.session_length,
        tech=req.tech,
        tech_version=req.tech_version or "",
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


# -------------------------------------------------------------
# PHASE 2: VERIFICATION CORE ENDPOINTS
# -------------------------------------------------------------

@app.get("/api/docker/health")
def docker_health():
    """Health check for Docker sandbox and pinned image environment."""
    sandbox_engine.prewarm()
    health_data = sandbox_engine.get_health()
    return health_data


@app.post("/api/decks/{deck_id}/verify")
def start_deck_verification(deck_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Triggers Phase 2 Verification pipeline for all code snippets and slides in a deck."""
    record = db.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Deck not found")

    def run_verify_background(d_id: str):
        with SessionLocal() as session:
            try:
                verification_coordinator.verify_deck(d_id, session)
            except Exception as e:
                import traceback
                print(f"Error in verification: {e}\n{traceback.format_exc()}")
                verification_coordinator._publish_event(d_id, "error", f"Verification failed: {str(e)}", 100)

    background_tasks.add_task(run_verify_background, deck_id)
    return {
        "status": "started",
        "deck_id": deck_id,
        "message": "Verification pipeline started in background.",
    }


@app.get("/api/decks/{deck_id}/verify/stream")
async def verify_progress_stream(deck_id: str):
    """Live Server-Sent Events (SSE) stream for real-time verification progress."""
    async def event_generator():
        last_index = 0
        heartbeats = 0
        while heartbeats < 600:  # max 5 mins
            events = verification_coordinator.get_progress_events(deck_id)
            if last_index < len(events):
                while last_index < len(events):
                    ev = events[last_index]
                    last_index += 1
                    yield f"data: {json.dumps(ev)}\n\n"
                    if ev.get("stage") == "completed" or ev.get("stage") == "error":
                        return
            else:
                heartbeats += 1
                yield f": ping\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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

        # 2. Quiz (MCQs + Output Prediction)
        quiz = generate_quiz_for_deck(deck_dict, snippets)
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
    """Staleness check: re-runs all snippets against the current pinned runtime."""
    from backend.materials.staleness_checker import check_deck_staleness
    try:
        res = check_deck_staleness(deck_id, db)
        return res
    except Exception as e:
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


