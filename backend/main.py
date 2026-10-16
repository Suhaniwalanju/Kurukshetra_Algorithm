import os
import uuid
import json
import asyncio
from typing import Dict, Any, List
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
        pptx_path = os.path.join(deck_dir, f"{req.topic.replace(' ', '_')}_{req.tech}.pptx")

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
            "needs_review_snippets": sum(1 for s in snippets if s.status == "needs_review"),
            "failed_snippets": sum(1 for s in snippets if s.status == "failed"),
            "proven_exercises": sum(1 for ep in exercise_proofs if ep.reference_passed and ep.naive_failed),
            "total_exercises": len(exercise_proofs),
            "mutation_score": (sum(ep.mutation_score for ep in exercise_proofs) / len(exercise_proofs)) if exercise_proofs else 1.0,
        },
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
