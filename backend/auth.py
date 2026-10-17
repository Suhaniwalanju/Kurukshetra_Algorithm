import os
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.database import get_db, SessionLocal, InstituteRecord, UserRecord, SubjectRecord

SECRET_KEY = os.environ.get("JWT_SECRET", "kurukshetra_super_secret_jwt_key_2026_rbac")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 5

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """Hashes a password using bcrypt. Plaintext is never stored."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed JWT with expiry."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> dict:
    """Decodes and validates a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> UserRecord:
    """FastAPI dependency to extract and validate the authenticated user."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
        )
    user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )
    return user


def require_role(allowed_roles: List[str], allow_pending_password_change: bool = False):
    """
    Enforces Role-Based Access Control on backend endpoints.
    Verifies user has one of allowed_roles and isn't blocked by pending password change.
    """
    def role_checker(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied for role '{current_user.role}'. Required: {allowed_roles}",
            )
        if current_user.must_change_password and not allow_pending_password_change:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password change required on first login.",
            )
        return current_user
    return role_checker


def seed_default_institute_and_admin(db: Optional[Session] = None):
    """
    Seeds default institute, admin, trainer, and student if database is fresh.
    Admin is seeded from environment variables and must change password on first login.
    """
    session = db or SessionLocal()
    try:
        # Check if DPU institute exists
        dpu = session.query(InstituteRecord).filter(InstituteRecord.id == "dpu").first()
        if not dpu:
            # Check for existing template file
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            dpu_png = os.path.join(base_dir, "input", "templates", "DPU", "blank.png")
            if not os.path.exists(dpu_png):
                dpu_png = os.path.join(base_dir, "input", "DPU_template.png")
            if not os.path.exists(dpu_png):
                dpu_png = ""

            dpu = InstituteRecord(
                id="dpu",
                name="Dr. D. Y. Patil Institute of Technology",
                short_name="DPU",
                contact_email="admin@dpu.edu.in",
                logo_path="",
                template_png=dpu_png,
                safe_area_top=100,
                safe_area_bottom=100,
                safe_area_left=120,
                safe_area_right=120,
            )
            session.add(dpu)
            session.commit()

        # Check default admin
        admin_login = os.environ.get("DEFAULT_ADMIN_LOGIN", "admin")
        admin_pass = os.environ.get("DEFAULT_ADMIN_PASSWORD", "Admin@12345")
        existing_admin = session.query(UserRecord).filter(
            UserRecord.institute_id == "dpu",
            UserRecord.login_id == admin_login,
        ).first()

        if not existing_admin:
            admin_user = UserRecord(
                id=f"usr_admin_{uuid.uuid4().hex[:6]}",
                institute_id="dpu",
                role="admin",
                display_name="Institute Administrator",
                login_id=admin_login,
                password_hash=hash_password(admin_pass),
                is_active=True,
                must_change_password=True,
            )
            session.add(admin_user)
            session.commit()

        # Seed default trainer if not present
        existing_trainer = session.query(UserRecord).filter(
            UserRecord.institute_id == "dpu",
            UserRecord.login_id == "trainer",
        ).first()
        if not existing_trainer:
            trainer_user = UserRecord(
                id=f"usr_tr_{uuid.uuid4().hex[:6]}",
                institute_id="dpu",
                role="trainer",
                display_name="Dr. S. Walanju",
                login_id="trainer",
                password_hash=hash_password("Trainer@12345"),
                is_active=True,
                must_change_password=False,
            )
            session.add(trainer_user)
            session.commit()

        # Seed default student if not present
        existing_student = session.query(UserRecord).filter(
            UserRecord.institute_id == "dpu",
            UserRecord.login_id == "STUDENT01",
        ).first()
        if not existing_student:
            student_user = UserRecord(
                id=f"usr_st_{uuid.uuid4().hex[:6]}",
                institute_id="dpu",
                role="student",
                display_name="Samruddhi K.",
                login_id="STUDENT01",
                roll_number="STUDENT01",
                class_branch="TE Computer Science",
                password_hash=hash_password("Student@123"),
                is_active=True,
                must_change_password=False,
            )
            session.add(student_user)
            session.commit()

        # Seed initial subject if none
        existing_subject = session.query(SubjectRecord).filter(
            SubjectRecord.institute_id == "dpu",
            SubjectRecord.folder_slug == "java-21-concurrency",
        ).first()
        if not existing_subject:
            sub = SubjectRecord(
                id=f"subj_{uuid.uuid4().hex[:6]}",
                institute_id="dpu",
                name="Java 21 Concurrency",
                folder_slug="java-21-concurrency",
                is_active=True,
            )
            session.add(sub)
            session.commit()

    finally:
        if not db:
            session.close()
