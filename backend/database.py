import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio.db"))
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DeckRecord(Base):
    __tablename__ = "decks"

    id = Column(String(64), primary_key=True, index=True)
    college = Column(String(128), nullable=False)
    professor_name = Column(String(128), nullable=False)
    topic = Column(String(256), nullable=False)
    student_level = Column(String(32), default="Beginner", nullable=False)
    session_length = Column(Integer, default=30, nullable=False)
    tech = Column(String(128), nullable=False)
    tech_version = Column(String(64), default="")
    status = Column(String(32), default="pending")  # pending, generating, building, completed, failed
    status_message = Column(String(256), default="Initiated")
    slides_json = Column(Text, default="[]")
    layout_logs_json = Column(Text, default="[]")
    pptx_path = Column(String(512), default="")
    pdf_path = Column(String(512), default="")
    output_dir = Column(String(512), default="")
    verified = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)
    approved_at = Column(DateTime, nullable=True)
    materials_status = Column(String(32), default="not_generated")  # not_generated, generating, ready, failed
    student_notes_json = Column(Text, default="[]")
    professor_notes_json = Column(Text, default="[]")
    quiz_json = Column(Text, default="[]")
    cheat_sheet_json = Column(Text, default="{}")
    exports_json = Column(Text, default="{}")
    migration_history_json = Column(Text, default="[]")
    preview_paths_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Verification relations
    snippets = relationship("SnippetRecord", back_populates="deck", cascade="all, delete-orphan")
    verification_runs = relationship("VerificationRunRecord", back_populates="deck", cascade="all, delete-orphan")
    exercise_proofs = relationship("ExerciseProofRecord", back_populates="deck", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "college": self.college,
            "professor_name": self.professor_name,
            "topic": self.topic,
            "student_level": self.student_level,
            "session_length": self.session_length,
            "tech": self.tech,
            "tech_version": self.tech_version,
            "status": self.status,
            "status_message": self.status_message,
            "slides": json.loads(self.slides_json) if self.slides_json else [],
            "layout_logs": json.loads(self.layout_logs_json) if self.layout_logs_json else [],
            "pptx_path": self.pptx_path,
            "pdf_path": getattr(self, "pdf_path", "") or "",
            "output_dir": getattr(self, "output_dir", "") or "",
            "verified": getattr(self, "verified", False) or False,
            "approved": getattr(self, "approved", False) or False,
            "approved_at": self.approved_at.isoformat() if getattr(self, "approved_at", None) else None,
            "materials_status": getattr(self, "materials_status", "not_generated") or "not_generated",
            "student_notes": json.loads(self.student_notes_json) if getattr(self, "student_notes_json", None) else [],
            "professor_notes": json.loads(self.professor_notes_json) if getattr(self, "professor_notes_json", None) else [],
            "quiz": json.loads(self.quiz_json) if getattr(self, "quiz_json", None) else [],
            "cheat_sheet": json.loads(self.cheat_sheet_json) if getattr(self, "cheat_sheet_json", None) else {},
            "exports": json.loads(self.exports_json) if getattr(self, "exports_json", None) else {},
            "migration_history": json.loads(self.migration_history_json) if getattr(self, "migration_history_json", None) else [],
            "preview_paths": json.loads(self.preview_paths_json) if self.preview_paths_json else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SnippetRecord(Base):
    __tablename__ = "snippets"

    id = Column(String(64), primary_key=True, index=True)
    deck_id = Column(String(64), ForeignKey("decks.id"), index=True)
    slide_id = Column(Integer, nullable=False)
    snippet_type = Column(String(32), default="code")  # code, exercise, quiz
    language = Column(String(32), nullable=False)
    version = Column(String(32), default="")
    source_code = Column(Text, nullable=False)
    wrapped_code = Column(Text, default="")
    expected_output = Column(Text, default="")
    actual_output = Column(Text, default="")
    compiler_output = Column(Text, default="")
    stderr = Column(Text, default="")
    exit_code = Column(Integer, default=0)
    duration_ms = Column(Float, default=0.0)
    command_executed = Column(String(512), default="")
    status = Column(String(32), default="pending")  # pending, verified, failed, needs_review, fixed_auto
    mismatch_detected = Column(Boolean, default=False)
    deprecation_level = Column(String(16), default="none")  # none, warning, removal
    deprecation_details = Column(Text, default="")
    sandbox_backend = Column(String(32), default="docker")  # docker or isolated_local_subprocess
    real_runtime_version = Column(String(128), default="")
    image_digest = Column(String(128), default="")
    classification = Column(String(32), default="PASS")  # COMPILE_ERROR, TEST_FAILURE, RUNTIME_ERROR, TIMEOUT, PASS
    was_wrapped = Column(Boolean, default=False)
    attempts_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deck = relationship("DeckRecord", back_populates="snippets")
    healing_logs = relationship("HealingLogRecord", back_populates="snippet", cascade="all, delete-orphan")

    @property
    def auto_healed(self) -> bool:
        return self.status in ["auto_healed", "healed", "fixed_auto"]

    def to_dict(self):
        return {
            "id": self.id,
            "deck_id": self.deck_id,
            "slide_id": self.slide_id,
            "snippet_type": self.snippet_type,
            "language": self.language,
            "version": self.version,
            "source_code": self.source_code,
            "wrapped_code": self.wrapped_code,
            "expected_output": self.expected_output,
            "actual_output": self.actual_output,
            "compiler_output": self.compiler_output,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "command_executed": self.command_executed,
            "status": self.status,
            "mismatch_detected": self.mismatch_detected,
            "deprecation_level": self.deprecation_level,
            "deprecation_details": self.deprecation_details,
            "sandbox_backend": getattr(self, "sandbox_backend", "docker") or "docker",
            "real_runtime_version": getattr(self, "real_runtime_version", "") or "",
            "image_digest": getattr(self, "image_digest", "") or "",
            "classification": getattr(self, "classification", "PASS") or "PASS",
            "was_wrapped": bool(getattr(self, "was_wrapped", False)),
            "attempts_count": self.attempts_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class VerificationRunRecord(Base):
    __tablename__ = "verification_runs"

    id = Column(String(64), primary_key=True, index=True)
    deck_id = Column(String(64), ForeignKey("decks.id"), index=True)
    status = Column(String(32), default="running")  # running, completed, failed
    status_message = Column(String(256), default="Verification initiated")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_snippets = Column(Integer, default=0)
    verified_count = Column(Integer, default=0)
    fixed_count = Column(Integer, default=0)
    needs_review_count = Column(Integer, default=0)
    exercises_proven_count = Column(Integer, default=0)
    mutation_score = Column(Float, default=0.0)
    layout_passed = Column(Boolean, default=True)
    report_html_path = Column(String(512), default="")
    report_pdf_path = Column(String(512), default="")
    summary_json = Column(Text, default="{}")

    deck = relationship("DeckRecord", back_populates="verification_runs")

    def to_dict(self):
        return {
            "id": self.id,
            "deck_id": self.deck_id,
            "status": self.status,
            "status_message": self.status_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_snippets": self.total_snippets,
            "verified_count": self.verified_count,
            "fixed_count": self.fixed_count,
            "needs_review_count": self.needs_review_count,
            "exercises_proven_count": self.exercises_proven_count,
            "mutation_score": self.mutation_score,
            "layout_passed": self.layout_passed,
            "report_html_path": self.report_html_path,
            "report_pdf_path": self.report_pdf_path,
            "summary": json.loads(self.summary_json) if self.summary_json else {},
        }


class HealingLogRecord(Base):
    __tablename__ = "healing_logs"

    id = Column(String(64), primary_key=True, index=True)
    snippet_id = Column(String(64), ForeignKey("snippets.id"), index=True)
    deck_id = Column(String(64), index=True)
    attempt_number = Column(Integer, nullable=False)
    error_type = Column(String(64), default="execution_failure")
    error_log = Column(Text, default="")
    original_code = Column(Text, default="")
    fixed_code = Column(Text, default="")
    diff = Column(Text, default="")
    success = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    snippet = relationship("SnippetRecord", back_populates="healing_logs")

    @property
    def diff_text(self) -> str:
        return self.diff or ""

    @property
    def healed_successfully(self) -> bool:
        return self.success

    def to_dict(self):
        return {
            "id": self.id,
            "snippet_id": self.snippet_id,
            "deck_id": self.deck_id,
            "attempt_number": self.attempt_number,
            "error_type": self.error_type,
            "error_log": self.error_log,
            "original_code": self.original_code,
            "fixed_code": self.fixed_code,
            "diff": self.diff,
            "diff_text": self.diff_text,
            "success": self.success,
            "healed_successfully": self.healed_successfully,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExerciseProofRecord(Base):
    __tablename__ = "exercise_proofs"

    id = Column(String(64), primary_key=True, index=True)
    deck_id = Column(String(64), ForeignKey("decks.id"), index=True)
    slide_id = Column(Integer, nullable=False)
    exercise_ref = Column(String(64), default="")
    problem_statement = Column(Text, default="")
    starter_code = Column(Text, default="")
    test_code = Column(Text, default="")
    reference_solution = Column(Text, default="")
    reference_passed = Column(Boolean, default=False)
    naive_solution = Column(Text, default="")
    naive_failed = Column(Boolean, default=False)
    mutants_json = Column(Text, default="[]")
    mutation_score = Column(Float, default=0.0)
    matrix_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)

    deck = relationship("DeckRecord", back_populates="exercise_proofs")

    @property
    def mutants(self):
        return json.loads(self.mutants_json) if self.mutants_json else []

    @property
    def total_mutants(self):
        return len(self.mutants)

    @property
    def killed_mutants(self):
        return sum(1 for m in self.mutants if m.get("killed", False))

    @property
    def pass_fail_matrix(self):
        return json.loads(self.matrix_json) if self.matrix_json else {}

    def to_dict(self):
        return {
            "id": self.id,
            "deck_id": self.deck_id,
            "slide_id": self.slide_id,
            "exercise_ref": self.exercise_ref,
            "problem_statement": self.problem_statement,
            "starter_code": self.starter_code,
            "test_code": self.test_code,
            "reference_solution": self.reference_solution,
            "reference_passed": self.reference_passed,
            "naive_solution": self.naive_solution,
            "naive_failed": self.naive_failed,
            "mutants": self.mutants,
            "total_mutants": self.total_mutants,
            "killed_mutants": self.killed_mutants,
            "mutation_score": self.mutation_score,
            "matrix": self.pass_fail_matrix,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ContentReviewRecord(Base):
    __tablename__ = "content_reviews"

    id = Column(String(64), primary_key=True, index=True)
    deck_id = Column(String(64), ForeignKey("decks.id"), index=True)
    findings_json = Column(Text, default="[]")
    total_findings = Column(Integer, default=0)
    high_severity_count = Column(Integer, default=0)
    auto_fixed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def findings(self):
        return json.loads(self.findings_json) if self.findings_json else []

    def to_dict(self):
        return {
            "id": self.id,
            "deck_id": self.deck_id,
            "findings": self.findings,
            "total_findings": self.total_findings,
            "high_severity_count": self.high_severity_count,
            "auto_fixed_count": self.auto_fixed_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def init_db():
    Base.metadata.create_all(bind=engine)
    # Ensure newly added columns exist in decks table for existing SQLite database
    from sqlalchemy import text
    with engine.connect() as conn:
        cols = [
            ("pdf_path", "VARCHAR(512)"),
            ("output_dir", "VARCHAR(512)"),
            ("verified", "BOOLEAN DEFAULT 0"),
            ("approved", "BOOLEAN DEFAULT 0"),
            ("approved_at", "DATETIME"),
            ("materials_status", "VARCHAR(32) DEFAULT 'not_generated'"),
            ("student_notes_json", "TEXT DEFAULT '[]'"),
            ("professor_notes_json", "TEXT DEFAULT '[]'"),
            ("quiz_json", "TEXT DEFAULT '[]'"),
            ("cheat_sheet_json", "TEXT DEFAULT '{}'"),
            ("exports_json", "TEXT DEFAULT '{}'"),
            ("migration_history_json", "TEXT DEFAULT '[]'"),
        ]
        for col, col_type in cols:
            try:
                conn.execute(text(f"ALTER TABLE decks ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass

        snippet_cols = [
            ("sandbox_backend", "VARCHAR(32) DEFAULT 'docker'"),
            ("real_runtime_version", "VARCHAR(128) DEFAULT ''"),
            ("image_digest", "VARCHAR(128) DEFAULT ''"),
            ("classification", "VARCHAR(32) DEFAULT 'PASS'"),
            ("was_wrapped", "BOOLEAN DEFAULT 0"),
        ]
        for col, col_type in snippet_cols:
            try:
                conn.execute(text(f"ALTER TABLE snippets ADD COLUMN {col} {col_type}"))
                conn.commit()
            except Exception:
                pass


# Auto-apply schema migrations on module import
init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
