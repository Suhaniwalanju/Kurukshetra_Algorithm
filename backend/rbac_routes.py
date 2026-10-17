import os
import csv
import io
import json
import uuid
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from PIL import Image
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from backend.database import (
    get_db,
    SessionLocal,
    InstituteRecord,
    UserRecord,
    SubjectRecord,
    PublicationRecord,
    QuizAttemptRecord,
    DeckRecord,
    ExerciseProofRecord,
    SnippetRecord,
)
from backend.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_role,
    MAX_FAILED_ATTEMPTS,
    LOCKOUT_MINUTES,
)
from backend.template_registry import template_registry, CONFIGS_DIR
from backend.publishing import publish_deck_for_subject, PUBLISHED_BASE_DIR

rbac_router = APIRouter()


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    institute_id: str
    login_id: Optional[str] = None
    roll_number: Optional[str] = None
    password: Optional[str] = None
    passkey: Optional[str] = None
    role: Optional[str] = None  # "admin", "trainer", "student"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class InstituteUpdateRequest(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    contact_email: Optional[str] = None
    safe_area_top: Optional[int] = None
    safe_area_bottom: Optional[int] = None
    safe_area_left: Optional[int] = None
    safe_area_right: Optional[int] = None


class TrainerCreateRequest(BaseModel):
    display_name: str
    login_id: str
    contact_email: Optional[str] = ""


class TrainerUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    is_active: Optional[bool] = None


class StudentCreateRequest(BaseModel):
    roll_number: str
    display_name: str
    class_branch: Optional[str] = ""


class StudentUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    class_branch: Optional[str] = None
    is_active: Optional[bool] = None


class SubjectCreateRequest(BaseModel):
    name: str
    folder_slug: Optional[str] = None


class SubjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    folder_slug: Optional[str] = None
    is_active: Optional[bool] = None


class PublishRequest(BaseModel):
    deck_id: str
    subject_id: Optional[str] = None
    subject_name: Optional[str] = None
    include_slides: bool = True
    confirmed: bool = False


class QuizSubmitRequest(BaseModel):
    answers: Dict[str, Any]


# ---------------------------------------------------------------------------
# 1. Authentication & Common Endpoints
# ---------------------------------------------------------------------------

@rbac_router.get("/api/institutes")
@rbac_router.get("/api/auth/institutes")
def list_institutes(db: Session = Depends(get_db)):
    """Returns list of active institutes for login dropdown."""
    institutes = db.query(InstituteRecord).all()
    return [{"id": inst.id, "name": inst.name, "short_name": inst.short_name} for inst in institutes]


@rbac_router.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Role-aware login with rate limiting & lockout.
    - Admin & Trainer: login_id + password
    - Student: roll_number + passkey
    """
    ident = (req.roll_number or req.login_id or "").strip()
    pwd = req.passkey if (req.role == "student" or req.passkey) else req.password
    if not ident or not pwd:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login identifier and password/passkey are required.",
        )

    # Scoped strictly by institute_id
    user = db.query(UserRecord).filter(
        UserRecord.institute_id == req.institute_id,
        UserRecord.login_id == ident,
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials for this institute.",
        )

    # Check lockout
    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        remaining_secs = int((user.locked_until - now).total_seconds())
        remaining_mins = max(1, remaining_secs // 60)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account is temporarily locked due to repeated failed logins. Please try again after {remaining_mins} minutes.",
        )

    # Role validation if specified
    if req.role and user.role != req.role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User is not registered as a {req.role}.",
        )

    # Verify password against bcrypt hash
    if not verify_password(pwd, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked for {LOCKOUT_MINUTES} minutes due to repeated failed login attempts.",
            )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    # Success: reset failed attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    token_payload = {
        "sub": user.id,
        "institute_id": user.institute_id,
        "role": user.role,
        "display_name": user.display_name,
        "must_change_password": user.must_change_password,
    }
    token = create_access_token(token_payload)

    return {
        "token": token,
        "user": user.to_dict(),
        "must_change_password": user.must_change_password,
    }


@rbac_router.get("/api/auth/me")
def get_current_user_profile(
    current_user: UserRecord = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns current user details and institute information."""
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == current_user.institute_id).first()
    return {
        "user": current_user.to_dict(),
        "institute": inst.to_dict() if inst else None,
    }


@rbac_router.post("/api/auth/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: UserRecord = Depends(require_role(["admin", "trainer", "student"], allow_pending_password_change=True)),
    db: Session = Depends(get_db),
):
    """Allows user to change their password (required on first login for seeded accounts)."""
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password does not match.")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    current_user.password_hash = hash_password(req.new_password)
    current_user.must_change_password = False
    db.commit()
    return {"success": True, "message": "Password changed successfully."}


# ---------------------------------------------------------------------------
# 2. Admin Dashboard Endpoints (Role: admin)
# ---------------------------------------------------------------------------

@rbac_router.get("/api/admin/overview")
def admin_overview(
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Read-only metrics overview: trainers, students, published subjects, institute details."""
    inst_id = current_user.institute_id
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == inst_id).first()

    trainers_count = db.query(UserRecord).filter(
        UserRecord.institute_id == inst_id,
        UserRecord.role == "trainer",
    ).count()

    students_count = db.query(UserRecord).filter(
        UserRecord.institute_id == inst_id,
        UserRecord.role == "student",
    ).count()

    published_count = db.query(PublicationRecord).filter(
        PublicationRecord.institute_id == inst_id,
        PublicationRecord.status == "published",
    ).count()

    subjects_count = db.query(SubjectRecord).filter(
        SubjectRecord.institute_id == inst_id,
    ).count()

    return {
        "institute": inst.to_dict() if inst else None,
        "metrics": {
            "trainers_count": trainers_count,
            "students_count": students_count,
            "published_subjects_count": published_count,
            "total_subjects_count": subjects_count,
            "has_template": bool(inst and inst.template_png and os.path.exists(inst.template_png)),
        },
    }


@rbac_router.get("/api/admin/institute")
def get_institute_settings(
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Returns institute settings including safe area margins."""
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == current_user.institute_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institute not found.")
    return inst.to_dict()


@rbac_router.put("/api/admin/institute")
def update_institute_settings(
    req: InstituteUpdateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Updates institute details and safe-area margins."""
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == current_user.institute_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institute not found.")

    if req.name is not None:
        inst.name = req.name.strip()
    if req.short_name is not None:
        inst.short_name = req.short_name.strip()
    if req.contact_email is not None:
        inst.contact_email = req.contact_email.strip()
    if req.safe_area_top is not None:
        inst.safe_area_top = max(10, min(300, req.safe_area_top))
    if req.safe_area_bottom is not None:
        inst.safe_area_bottom = max(10, min(300, req.safe_area_bottom))
    if req.safe_area_left is not None:
        inst.safe_area_left = max(10, min(500, req.safe_area_left))
    if req.safe_area_right is not None:
        inst.safe_area_right = max(10, min(500, req.safe_area_right))

    db.commit()

    # If template PNG exists, re-register and generate updated sample slide preview
    if inst.template_png and os.path.exists(inst.template_png):
        template_registry.register_custom_institute_template(
            college=inst.short_name,
            png_path=inst.template_png,
            top=inst.safe_area_top,
            bottom=inst.safe_area_bottom,
            left=inst.safe_area_left,
            right=inst.safe_area_right,
        )

    return {"success": True, "institute": inst.to_dict()}


@rbac_router.post("/api/admin/institute/template")
async def upload_institute_template(
    file: UploadFile = File(...),
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """
    Validates and stores institute template PNG:
    - Type must be PNG
    - Max size 10 MB
    - Recommended 1920x1080 16:9
    - Rejects others with clear error message
    """
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == current_user.institute_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institute not found.")

    # 1. Validate file extension
    if not file.filename.lower().endswith(".png"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Only high-resolution PNG images are accepted (.png).",
        )

    # 2. Read bytes and validate size <= 10 MB
    contents = await file.read()
    max_bytes = 10 * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum size limit of 10 MB (received {len(contents) / (1024 * 1024):.1f} MB).",
        )

    # 3. Validate image integrity and dimensions using PIL
    try:
        img = Image.open(io.BytesIO(contents))
        if img.format != "PNG":
            raise HTTPException(status_code=400, detail="Corrupted image: Header is not standard PNG.")
        width, height = img.size
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid image file: {str(e)}")

    # 4. Save to uploads/templates/<institute_id>_<timestamp>.png
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    upload_dir = os.path.join(base_dir, "input", "templates", inst.short_name)
    os.makedirs(upload_dir, exist_ok=True)
    target_path = os.path.join(upload_dir, "template.png")

    with open(target_path, "wb") as f:
        f.write(contents)

    inst.template_png = target_path
    db.commit()

    # 5. Register with template registry and generate preview
    template_registry.register_custom_institute_template(
        college=inst.short_name,
        png_path=target_path,
        top=inst.safe_area_top,
        bottom=inst.safe_area_bottom,
        left=inst.safe_area_left,
        right=inst.safe_area_right,
    )

    ratio_note = ""
    if (width, height) != (1920, 1080):
        ratio_note = f" Note: Image size was {width}x{height}. It has been normalized to 1920x1080 (16:9 widescreen)."

    return {
        "success": True,
        "message": f"Template PNG uploaded and registered successfully.{ratio_note}",
        "template_png": target_path,
        "dimensions": f"{width}x{height}",
    }


@rbac_router.get("/api/admin/institute/preview")
def get_admin_template_preview(
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Returns sample slide preview rendered on the template with safe-area bounds."""
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == current_user.institute_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institute not found.")

    preview_path = os.path.join(CONFIGS_DIR, f"{inst.short_name}_sample_preview.png")
    if not os.path.exists(preview_path):
        config = template_registry.get_config(inst.short_name)
        if not config:
            colleges = template_registry.list_colleges()
            if colleges:
                config = template_registry.get_config(colleges[0]["college"])
        if config:
            preview_path = template_registry.generate_sample_slide_preview(
                college=inst.short_name,
                config=config,
                top=inst.safe_area_top,
                bottom=inst.safe_area_bottom,
                left=inst.safe_area_left,
                right=inst.safe_area_right,
            )

    if not os.path.exists(preview_path):
        raise HTTPException(status_code=404, detail="Preview image not found.")
    return FileResponse(preview_path, media_type="image/png")


# --- Manage Trainers ---

@rbac_router.get("/api/admin/trainers")
def list_trainers(
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Lists all trainers for current admin's institute."""
    trainers = db.query(UserRecord).filter(
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.role == "trainer",
    ).order_by(UserRecord.created_at.desc()).all()
    return [t.to_dict() for t in trainers]


@rbac_router.post("/api/admin/trainers")
def create_trainer(
    req: TrainerCreateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Creates a trainer and auto-generates a temporary password shown once."""
    login_id = req.login_id.strip()
    existing = db.query(UserRecord).filter(
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.login_id == login_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Trainer login ID '{login_id}' already exists in this institute.")

    # Auto-generate temporary password
    temp_password = f"Trn#{secrets.token_urlsafe(6)}!"
    new_trainer = UserRecord(
        id=f"usr_tr_{uuid.uuid4().hex[:8]}",
        institute_id=current_user.institute_id,
        role="trainer",
        display_name=req.display_name.strip(),
        login_id=login_id,
        password_hash=hash_password(temp_password),
        is_active=True,
        must_change_password=True,
    )
    db.add(new_trainer)
    db.commit()
    db.refresh(new_trainer)

    return {
        "trainer": new_trainer.to_dict(),
        "temporary_password": temp_password,
        "message": "Trainer created. Please copy the temporary password now; it will not be displayed again.",
    }


@rbac_router.put("/api/admin/trainers/{trainer_id}")
def update_trainer(
    trainer_id: str,
    req: TrainerUpdateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Updates trainer status or display name."""
    trainer = db.query(UserRecord).filter(
        UserRecord.id == trainer_id,
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.role == "trainer",
    ).first()
    if not trainer:
        raise HTTPException(status_code=404, detail="Trainer not found.")

    if req.display_name is not None:
        trainer.display_name = req.display_name.strip()
    if req.is_active is not None:
        trainer.is_active = req.is_active

    db.commit()
    return trainer.to_dict()


@rbac_router.post("/api/admin/trainers/{trainer_id}/reset-password")
def reset_trainer_password(
    trainer_id: str,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Resets trainer password to a new auto-generated temporary password."""
    trainer = db.query(UserRecord).filter(
        UserRecord.id == trainer_id,
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.role == "trainer",
    ).first()
    if not trainer:
        raise HTTPException(status_code=404, detail="Trainer not found.")

    new_temp = f"Trn#{secrets.token_urlsafe(6)}!"
    trainer.password_hash = hash_password(new_temp)
    trainer.must_change_password = True
    db.commit()

    return {
        "success": True,
        "temporary_password": new_temp,
        "message": "Password reset. Copy the new temporary password now.",
    }


# --- Manage Students ---

@rbac_router.get("/api/admin/students")
def list_students(
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Lists all students in current admin's institute."""
    students = db.query(UserRecord).filter(
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.role == "student",
    ).order_by(UserRecord.roll_number.asc()).all()
    return [s.to_dict() for s in students]


@rbac_router.post("/api/admin/students")
def create_student(
    req: StudentCreateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Creates a single student and auto-generates a passkey shown once."""
    roll = req.roll_number.strip()
    existing = db.query(UserRecord).filter(
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.login_id == roll,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Student roll number '{roll}' already exists in this institute.")

    passkey = f"Std#{secrets.token_urlsafe(5)}!"
    student = UserRecord(
        id=f"usr_st_{uuid.uuid4().hex[:8]}",
        institute_id=current_user.institute_id,
        role="student",
        display_name=req.display_name.strip(),
        login_id=roll,
        roll_number=roll,
        class_branch=req.class_branch.strip() if req.class_branch else "",
        password_hash=hash_password(passkey),
        is_active=True,
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    return {
        "student": student.to_dict(),
        "passkey": passkey,
        "message": "Student created. Save the passkey credentials now.",
    }


@rbac_router.post("/api/admin/students/bulk")
async def bulk_upload_students(
    file: UploadFile = File(...),
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """
    Bulk uploads students via CSV (roll_number, name, class/branch).
    Auto-generates passkeys and returns credentials list for download once.
    """
    contents = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(contents))

    created = []
    credentials = []

    for row in reader:
        if not row or not row[0].strip() or row[0].lower().startswith("roll"):
            continue
        roll = row[0].strip()
        name = row[1].strip() if len(row) > 1 else roll
        branch = row[2].strip() if len(row) > 2 else ""

        # Check existing
        existing = db.query(UserRecord).filter(
            UserRecord.institute_id == current_user.institute_id,
            UserRecord.login_id == roll,
        ).first()
        if existing:
            continue

        passkey = f"Std#{secrets.token_urlsafe(5)}!"
        student = UserRecord(
            id=f"usr_st_{uuid.uuid4().hex[:8]}",
            institute_id=current_user.institute_id,
            role="student",
            display_name=name,
            login_id=roll,
            roll_number=roll,
            class_branch=branch,
            password_hash=hash_password(passkey),
            is_active=True,
        )
        db.add(student)
        created.append(student)
        credentials.append({
            "roll_number": roll,
            "name": name,
            "class_branch": branch,
            "passkey": passkey,
        })

    db.commit()

    return {
        "created_count": len(created),
        "credentials": credentials,
        "message": f"Successfully registered {len(created)} students. Download credentials list now.",
    }


@rbac_router.put("/api/admin/students/{student_id}")
def update_student(
    student_id: str,
    req: StudentUpdateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Updates student details or active status."""
    student = db.query(UserRecord).filter(
        UserRecord.id == student_id,
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.role == "student",
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    if req.display_name is not None:
        student.display_name = req.display_name.strip()
    if req.class_branch is not None:
        student.class_branch = req.class_branch.strip()
    if req.is_active is not None:
        student.is_active = req.is_active

    db.commit()
    return student.to_dict()


@rbac_router.post("/api/admin/students/{student_id}/reset-passkey")
def reset_student_passkey(
    student_id: str,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Resets student passkey and returns the new passkey once."""
    student = db.query(UserRecord).filter(
        UserRecord.id == student_id,
        UserRecord.institute_id == current_user.institute_id,
        UserRecord.role == "student",
    ).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")

    new_passkey = f"Std#{secrets.token_urlsafe(5)}!"
    student.password_hash = hash_password(new_passkey)
    db.commit()

    return {
        "success": True,
        "new_passkey": new_passkey,
        "message": "Student passkey reset successfully.",
    }


# --- Manage Subjects / Topics ---

@rbac_router.get("/api/admin/subjects")
def list_subjects(
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Lists all subjects for current institute."""
    subjects = db.query(SubjectRecord).filter(
        SubjectRecord.institute_id == current_user.institute_id,
    ).order_by(SubjectRecord.created_at.desc()).all()
    return [s.to_dict() for s in subjects]


@rbac_router.post("/api/admin/subjects")
def create_subject(
    req: SubjectCreateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Creates a new subject / topic entry."""
    name = req.name.strip()
    slug = (req.folder_slug or name.lower().replace(" ", "-")).strip()
    # Sanitize slug
    import re
    slug = re.sub(r'[^a-zA-Z0-9_\-]', '', slug)

    existing = db.query(SubjectRecord).filter(
        SubjectRecord.institute_id == current_user.institute_id,
        SubjectRecord.folder_slug == slug,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Subject folder slug '{slug}' already exists in this institute.")

    subject = SubjectRecord(
        id=f"subj_{uuid.uuid4().hex[:8]}",
        institute_id=current_user.institute_id,
        name=name,
        folder_slug=slug,
        is_active=True,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject.to_dict()


@rbac_router.put("/api/admin/subjects/{subject_id}")
def update_subject(
    subject_id: str,
    req: SubjectUpdateRequest,
    current_user: UserRecord = Depends(require_role(["admin"])),
    db: Session = Depends(get_db),
):
    """Renames, updates folder slug, or toggles active status for a subject."""
    subject = db.query(SubjectRecord).filter(
        SubjectRecord.id == subject_id,
        SubjectRecord.institute_id == current_user.institute_id,
    ).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found.")

    if req.name is not None:
        subject.name = req.name.strip()
    if req.folder_slug is not None:
        subject.folder_slug = req.folder_slug.strip()
    if req.is_active is not None:
        subject.is_active = req.is_active

    db.commit()
    return subject.to_dict()


# ---------------------------------------------------------------------------
# 3. Trainer Dashboard Endpoints (Role: trainer | admin)
# ---------------------------------------------------------------------------

@rbac_router.get("/api/trainer/institute")
def get_trainer_institute_branding(
    current_user: UserRecord = Depends(require_role(["trainer", "admin"])),
    db: Session = Depends(get_db),
):
    """
    Returns trainer's institute branding, template preview URL, and safe area config.
    Applied automatically so trainer does not need to choose a template.
    """
    inst = db.query(InstituteRecord).filter(InstituteRecord.id == current_user.institute_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="Institute not found.")
    return {
        "institute": inst.to_dict(),
        "preview_url": f"/api/templates/{inst.short_name}/preview",
    }


@rbac_router.get("/api/trainer/subjects")
def get_trainer_subjects(
    current_user: UserRecord = Depends(require_role(["trainer", "admin"])),
    db: Session = Depends(get_db),
):
    """Returns active subjects for the trainer's institute."""
    subjects = db.query(SubjectRecord).filter(
        SubjectRecord.institute_id == current_user.institute_id,
        SubjectRecord.is_active == True,
    ).all()
    return [s.to_dict() for s in subjects]


@rbac_router.get("/api/trainer/publications")
def get_trainer_publications(
    current_user: UserRecord = Depends(require_role(["trainer", "admin"])),
    db: Session = Depends(get_db),
):
    """Returns all publications for the trainer's institute."""
    pubs = db.query(PublicationRecord).filter(
        PublicationRecord.institute_id == current_user.institute_id,
    ).order_by(PublicationRecord.published_at.desc()).all()
    return [p.to_dict() for p in pubs]


@rbac_router.post("/api/trainer/publish")
def publish_materials(
    req: PublishRequest,
    current_user: UserRecord = Depends(require_role(["trainer", "admin"])),
    db: Session = Depends(get_db),
):
    """
    Publishes verified deck materials (notes, stripped quiz, exercises, slides)
    to the student-accessible storage under storage/published/<institute_id>/<subject_slug>/.
    If any item is low_assurance or needs_review, returns a confirmation prompt listing them.
    """
    deck = db.query(DeckRecord).filter(DeckRecord.id == req.deck_id).first()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found.")

    # Check that all materials exist
    if not deck.slides_json or deck.status != "completed":
        raise HTTPException(status_code=400, detail="Deck must be fully generated and verified before publishing.")

    # Check for flagged items if not confirmed
    flagged = []
    snippets = db.query(SnippetRecord).filter(SnippetRecord.deck_id == req.deck_id).all()
    for sn in snippets:
        if sn.status == "needs_review":
            flagged.append(f"Slide {sn.slide_id} code snippet: Needs Review ({sn.classification})")
        elif sn.status == "verified_low_assurance":
            flagged.append(f"Slide {sn.slide_id} code snippet: Ran on local subprocess fallback (Low Assurance)")

    exercise_proofs = db.query(ExerciseProofRecord).filter(ExerciseProofRecord.deck_id == req.deck_id).all()
    for ep in exercise_proofs:
        if ep.status == "needs_review":
            flagged.append(f"Exercise '{ep.title}': Proof flagged needs_review (mutation score {ep.mutation_score:.0f}%)")

    if flagged and not req.confirmed:
        return {
            "needs_confirmation": True,
            "flagged_items": flagged,
            "message": "Some materials have low assurance or require review. Please confirm to publish.",
        }

    # Resolve subject_id
    subject_id = req.subject_id
    if not subject_id and req.subject_name:
        import re
        slug = re.sub(r'[^a-zA-Z0-9_]+', '_', req.subject_name.strip().lower()).strip('_')
        sub = db.query(SubjectRecord).filter(
            SubjectRecord.institute_id == current_user.institute_id,
            (SubjectRecord.name == req.subject_name.strip()) | (SubjectRecord.folder_slug == slug)
        ).first()
        if not sub:
            sub = SubjectRecord(
                id=f"sub_{uuid.uuid4().hex[:8]}",
                institute_id=current_user.institute_id,
                name=req.subject_name.strip(),
                folder_slug=slug or "course",
                is_active=True
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)
        subject_id = sub.id

    if not subject_id:
        raise HTTPException(status_code=400, detail="subject_id or subject_name is required.")

    # Execute publication
    try:
        pub = publish_deck_for_subject(
            deck_id=req.deck_id,
            subject_id=subject_id,
            include_slides=req.include_slides,
            trainer_id=current_user.id,
            institute_id=current_user.institute_id,
            db=db,
        )
        return {
            "success": True,
            "publication": pub.to_dict(),
            "publication_id": pub.id,
            "version": pub.version,
            "status": pub.status,
            "published_path": pub.published_path,
            "message": f"Successfully published version {pub.version} of course materials for students.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Publication failed: {str(e)}")


@rbac_router.post("/api/trainer/unpublish/{pub_id}")
def unpublish_materials(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["trainer", "admin"])),
    db: Session = Depends(get_db),
):
    """Sets a publication to unpublished status."""
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    pub.status = "unpublished"
    db.commit()
    return {"success": True, "status": "unpublished", "message": "Course material unpublished successfully."}


# ---------------------------------------------------------------------------
# 4. Student Dashboard Endpoints (Role: student)
# ---------------------------------------------------------------------------

@rbac_router.get("/api/student/subjects")
def get_student_subjects(
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """
    Returns active published subjects for student's institute.
    Read-only view of course materials.
    """
    inst_id = current_user.institute_id
    active_pubs = db.query(PublicationRecord).filter(
        PublicationRecord.institute_id == inst_id,
        PublicationRecord.status == "published",
    ).order_by(PublicationRecord.published_at.desc()).all()

    result = []
    seen_subjects = set()

    for pub in active_pubs:
        if pub.subject_id in seen_subjects:
            continue
        seen_subjects.add(pub.subject_id)

        pub_path = pub.published_path
        has_notes = os.path.exists(os.path.join(pub_path, "notes", "notes.md"))
        has_quiz = os.path.exists(os.path.join(pub_path, "quiz", "quiz.json"))
        has_exercises = os.path.exists(os.path.join(pub_path, "exercises", "exercises.zip"))
        has_slides = pub.include_slides and os.path.exists(os.path.join(pub_path, "slides", "deck.pdf"))

        result.append({
            "id": pub.id,
            "publication_id": pub.id,
            "subject_id": pub.subject_id,
            "institute_id": pub.institute_id,
            "status": pub.status,
            "subject_name": pub.subject.name if pub.subject else "Course Subject",
            "folder_slug": pub.subject.folder_slug if pub.subject else "",
            "topic": pub.deck.topic if pub.deck else "",
            "tech": pub.deck.tech if pub.deck else "",
            "tech_version": pub.deck.tech_version if pub.deck else "",
            "level": pub.deck.student_level if pub.deck else "Beginner",
            "version": pub.version,
            "published_at": pub.published_at.isoformat() if pub.published_at else None,
            "trainer_name": pub.trainer.display_name if pub.trainer else "Professor",
            "has_notes": has_notes,
            "has_quiz": has_quiz,
            "has_exercises": has_exercises,
            "has_slides": has_slides,
        })

    return result


@rbac_router.get("/api/student/publications/{pub_id}/notes")
@rbac_router.get("/api/student/subjects/{pub_id}/notes")
def get_student_notes(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """Returns markdown text for student notes."""
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    notes_file = os.path.join(pub.published_path, "notes", "notes.md")
    if not os.path.exists(notes_file):
        raise HTTPException(status_code=404, detail="Notes file not found.")

    with open(notes_file, "r", encoding="utf-8") as f:
        content = f.read()

    has_pdf = os.path.exists(os.path.join(pub.published_path, "notes", "notes.pdf"))
    return {"markdown": content, "has_pdf": has_pdf}


@rbac_router.get("/api/student/publications/{pub_id}/notes/pdf")
@rbac_router.get("/api/student/subjects/{pub_id}/notes/pdf")
def download_student_notes_pdf(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """Downloads student notes PDF."""
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    pdf_file = os.path.join(pub.published_path, "notes", "notes.pdf")
    if not os.path.exists(pdf_file):
        raise HTTPException(status_code=404, detail="PDF notes file not found.")
    return FileResponse(pdf_file, media_type="application/pdf", filename="Course_Notes.pdf")


@rbac_router.get("/api/student/publications/{pub_id}/slides")
@rbac_router.get("/api/student/subjects/{pub_id}/slides")
def download_student_slides(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """Downloads lecture deck PDF if included in publication."""
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub or not pub.include_slides:
        raise HTTPException(status_code=404, detail="Slides not available for this course publication.")

    slides_file = os.path.join(pub.published_path, "slides", "deck.pdf")
    if not os.path.exists(slides_file):
        raise HTTPException(status_code=404, detail="Slide deck PDF not found.")
    return FileResponse(slides_file, media_type="application/pdf", filename="Lecture_Slides.pdf")


@rbac_router.get("/api/student/publications/{pub_id}/exercises")
@rbac_router.get("/api/student/subjects/{pub_id}/exercises")
def get_student_exercises(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """
    Returns student exercise tasks and starter codes.
    Strictly contains NO reference solutions or test proof reports.
    """
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    ex_dir = os.path.join(pub.published_path, "exercises")
    if not os.path.exists(ex_dir):
        return []

    exercises = []
    subfolders = sorted([d for d in os.listdir(ex_dir) if os.path.isdir(os.path.join(ex_dir, d))])

    for folder_name in subfolders:
        folder_path = os.path.join(ex_dir, folder_name)
        task_file = os.path.join(folder_path, "task.md")
        task_md = ""
        if os.path.exists(task_file):
            with open(task_file, "r", encoding="utf-8") as f:
                task_md = f.read()

        # Find starter code and test file
        starter_code = ""
        starter_filename = ""
        test_code = ""
        test_filename = ""

        for f in os.listdir(folder_path):
            if f == "task.md":
                continue
            lower_f = f.lower()
            if "test" in lower_f:
                test_filename = f
                with open(os.path.join(folder_path, f), "r", encoding="utf-8") as tf:
                    test_code = tf.read()
            else:
                starter_filename = f
                with open(os.path.join(folder_path, f), "r", encoding="utf-8") as sf:
                    starter_code = sf.read()

        exercises.append({
            "folder": folder_name,
            "task_markdown": task_md,
            "starter_code": starter_code,
            "starter_filename": starter_filename,
            "test_code": test_code,
            "test_filename": test_filename,
        })

    return exercises


@rbac_router.get("/api/student/publications/{pub_id}/exercises/zip")
@rbac_router.get("/api/student/subjects/{pub_id}/exercises/zip")
def download_student_exercises_zip(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """Downloads all student exercises packaged into a ZIP archive."""
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    zip_file = os.path.join(pub.published_path, "exercises", "exercises.zip")
    if not os.path.exists(zip_file):
        raise HTTPException(status_code=404, detail="Exercises archive not found.")
    return FileResponse(zip_file, media_type="application/zip", filename=f"{pub.subject.folder_slug}_exercises.zip")


@rbac_router.get("/api/student/publications/{pub_id}/quiz")
@rbac_router.get("/api/student/subjects/{pub_id}/quiz")
def get_student_quiz(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """
    Returns quiz questions and options ONLY.
    Answers and explanations are NEVER sent to the student client prior to submission.
    """
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    quiz_file = os.path.join(pub.published_path, "quiz", "quiz.json")
    if not os.path.exists(quiz_file):
        return []

    with open(quiz_file, "r", encoding="utf-8") as f:
        quiz_data = json.load(f)

    # Secondary safety: ensure answers/explanations are never present
    sanitized = []
    for item in quiz_data:
        sanitized.append({
            "id": item.get("id"),
            "number": item.get("number"),
            "question": item.get("question"),
            "options": item.get("options") or [],
            "code_snippet": item.get("code_snippet") or "",
        })
    return sanitized


@rbac_router.post("/api/student/publications/{pub_id}/quiz/submit")
@rbac_router.post("/api/student/subjects/{pub_id}/quiz/submit")
def submit_student_quiz(
    pub_id: str,
    req: QuizSubmitRequest,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """
    Evaluates student's quiz answers against the server-side answer key in DeckRecord.
    Returns score and reveals question explanations and correct answers ONLY after submission.
    Saves attempt record.
    """
    pub = db.query(PublicationRecord).filter(
        PublicationRecord.id == pub_id,
        PublicationRecord.institute_id == current_user.institute_id,
        PublicationRecord.status == "published",
    ).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found.")

    deck = db.query(DeckRecord).filter(DeckRecord.id == pub.deck_id).first()
    if not deck or not deck.quiz_json:
        raise HTTPException(status_code=400, detail="Quiz data not available for evaluation.")

    server_quiz = json.loads(deck.quiz_json)
    score = 0
    total = len(server_quiz)
    details = []

    for idx, q in enumerate(server_quiz, 1):
        q_id = q.get("id") or f"q_{idx}"
        student_ans = req.answers.get(q_id)
        if student_ans is None:
            student_ans = req.answers.get(str(idx))
        if student_ans is None:
            student_ans = req.answers.get(str(idx - 1))
        if student_ans is None:
            student_ans = req.answers.get(idx - 1)

        correct_ans = q.get("correct_answer") or q.get("correct_option") or q.get("answer") or ""
        explanation = q.get("explanation") or q.get("rationale") or "Correct concept applied."

        # Compare answers (index or string match)
        is_correct = False
        if student_ans is not None:
            # Handle index match
            if isinstance(student_ans, int) and isinstance(q.get("options"), list):
                if 0 <= student_ans < len(q["options"]):
                    chosen_str = q["options"][student_ans].strip()
                    is_correct = (chosen_str.lower() == str(correct_ans).strip().lower() or
                                  student_ans == q.get("correct_index"))
            else:
                is_correct = str(student_ans).strip().lower() == str(correct_ans).strip().lower()

        if is_correct:
            score += 1

        details.append({
            "id": q_id,
            "number": idx,
            "question": q.get("question") or f"Question {idx}",
            "student_answer": student_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct,
            "explanation": explanation,
        })

    # Save attempt in DB
    attempt = QuizAttemptRecord(
        id=f"att_{uuid.uuid4().hex[:8]}",
        institute_id=current_user.institute_id,
        publication_id=pub_id,
        student_id=current_user.id,
        score=score,
        total_questions=total,
        answers_json=json.dumps(req.answers),
        submitted_at=datetime.utcnow(),
    )
    db.add(attempt)
    db.commit()

    return {
        "score": score,
        "total": total,
        "percentage": round((score / max(1, total)) * 100, 1),
        "details": details,
        "results": details,
        "submitted_at": attempt.submitted_at.isoformat(),
    }


@rbac_router.get("/api/student/publications/{pub_id}/quiz/attempts")
@rbac_router.get("/api/student/subjects/{pub_id}/quiz/attempts")
def get_student_quiz_attempts(
    pub_id: str,
    current_user: UserRecord = Depends(require_role(["student"])),
    db: Session = Depends(get_db),
):
    """Returns past quiz attempts for this student on this publication."""
    attempts = db.query(QuizAttemptRecord).filter(
        QuizAttemptRecord.publication_id == pub_id,
        QuizAttemptRecord.student_id == current_user.id,
    ).order_by(QuizAttemptRecord.submitted_at.desc()).all()
    return [a.to_dict() for a in attempts]
