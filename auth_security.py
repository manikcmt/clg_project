import hashlib
import hmac
import os
import secrets

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from auth_model import AdminAccount, TeacherAccount
from database import get_db
from fastapi import Depends
from student_model import Student


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        600_000,
    )
    return f"pbkdf2_sha256$600000${salt.hex()}${password_hash.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = stored_hash.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(actual_hash.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def require_admin(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminAccount:
    if request.session.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login/admin"},
        )
    admin = db.query(AdminAccount).filter_by(id=request.session.get("user_id")).first()
    if admin is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login/admin"},
        )
    return admin


def require_admin_api(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminAccount:
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
    admin = db.query(AdminAccount).filter_by(id=request.session.get("user_id")).first()
    if admin is None:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required")
    return admin


def require_student(
    request: Request,
    db: Session = Depends(get_db),
) -> Student:
    if request.session.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login/student"},
        )
    student = db.query(Student).filter_by(id=request.session.get("user_id")).first()
    if (
        student is None
        or not student.password_hash
        or student.account_status != "approved"
    ):
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login/student"},
        )
    return student


def require_teacher(
    request: Request,
    db: Session = Depends(get_db),
) -> TeacherAccount:
    if request.session.get("role") != "teacher":
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login/teacher"},
        )
    teacher = (
        db.query(TeacherAccount)
        .filter_by(id=request.session.get("user_id"), account_status="approved")
        .first()
    )
    if teacher is None:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login/teacher"},
        )
    return teacher


def session_secret() -> str:
    value = os.getenv("SESSION_SECRET")
    if value:
        return value
    local_secret_file = os.path.join(os.path.dirname(__file__), ".session_secret")
    try:
        with open(local_secret_file, "x", encoding="utf-8") as secret_file:
            value = secrets.token_urlsafe(48)
            secret_file.write(value)
            return value
    except FileExistsError:
        with open(local_secret_file, encoding="utf-8") as secret_file:
            value = secret_file.read().strip()
        if value:
            return value
        raise RuntimeError("SESSION_SECRET or a non-empty .session_secret is required.")
