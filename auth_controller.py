import hashlib
import logging
import os
import re
import secrets
import smtplib
import time
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth_model import AdminAccount, TeacherAccount
from auth_security import hash_password, require_admin, verify_password
from database import get_db
from mailer import send_student_credentials_email, send_student_setup_email
from student_model import SemesterUpdateRequest, Student


router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)
STUDENT_SETUP_TOKEN_LIFETIME = 60 * 60 * 24


def approve_pending_registration(student_id: int, db: Session) -> bool:
    student = (
        db.query(Student)
        .filter_by(id=student_id, account_status="pending")
        .first()
    )
    if student is None:
        return False

    token = secrets.token_urlsafe(32)
    student.setup_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    student.setup_token_expires = int(time.time()) + STUDENT_SETUP_TOKEN_LIFETIME
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    setup_url = f"{base_url}/student/setup-password?token={token}"
    try:
        send_student_setup_email(student.email, student.roll, setup_url)
        student.account_status = "approved"
        db.commit()
        return True
    except (OSError, RuntimeError, smtplib.SMTPException, SQLAlchemyError):
        db.rollback()
        logger.exception("Could not approve and email student registration %s", student_id)
        return False


@router.get("/login")
def login_choice(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login_choice.html",
        context={},
    )


@router.get("/login/admin")
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    if db.query(AdminAccount).count() == 0:
        return RedirectResponse("/setup/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"role": "Admin", "action": "/login/admin", "error": None},
    )


@router.post("/login/admin")
def admin_login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    admin = db.query(AdminAccount).filter_by(username=username.strip()).first()
    if admin is None or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "role": "Admin",
                "action": "/login/admin",
                "error": "Username or password is incorrect.",
            },
            status_code=401,
        )
    request.session.clear()
    request.session.update({"role": "admin", "user_id": admin.id, "username": admin.username})
    return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login/teacher")
def teacher_login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"role": "Teacher", "action": "/login/teacher", "error": None},
    )


@router.post("/login/teacher")
def teacher_login(
    request: Request,
    username: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    teacher = (
        db.query(TeacherAccount)
        .filter(TeacherAccount.username.ilike(username.strip()))
        .first()
    )
    if (
        teacher is None
        or teacher.account_status != "approved"
        or not verify_password(password, teacher.password_hash)
    ):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "role": "Teacher",
                "action": "/login/teacher",
                "error": "Username/password is incorrect, or the teacher account is awaiting Admin approval.",
            },
            status_code=401,
        )
    request.session.clear()
    request.session.update(
        {"role": "teacher", "user_id": teacher.id, "username": teacher.username}
    )
    return RedirectResponse("/teacher/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/teacher/register")
def teacher_registration_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="teacher_register.html",
        context={"error": None},
    )


@router.post("/teacher/register")
def register_teacher(
    request: Request,
    name: str = Form(min_length=1, max_length=255),
    username: str = Form(min_length=3, max_length=100),
    email: str = Form(min_length=3, max_length=255),
    password: str = Form(min_length=6, max_length=6),
    confirm_password: str = Form(min_length=6, max_length=6),
    db: Session = Depends(get_db),
):
    if (
        not name.strip()
        or not username.strip()
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip())
    ):
        return templates.TemplateResponse(
            request=request,
            name="teacher_register.html",
            context={"error": "Enter a name, username, and valid email address."},
            status_code=400,
        )
    if not password.isascii() or not password.isdigit():
        return templates.TemplateResponse(
            request=request,
            name="teacher_register.html",
            context={"error": "Password must contain exactly 6 digits (0-9)."},
            status_code=400,
        )
    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="teacher_register.html",
            context={"error": "Passwords do not match."},
            status_code=400,
        )
    normalized_username = username.strip().lower()
    normalized_email = email.strip().lower()
    teacher = TeacherAccount(
        name=name.strip(),
        username=normalized_username,
        email=normalized_email,
        password_hash=hash_password(password),
        account_status="pending",
    )
    db.add(teacher)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            request=request,
            name="teacher_register.html",
            context={"error": "That username or email is already registered."},
            status_code=409,
        )
    return templates.TemplateResponse(
        request=request,
        name="teacher_registration_submitted.html",
        context={"name": teacher.name},
    )


@router.get("/login/student")
def student_login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"role": "Student", "action": "/login/student", "error": None},
    )


@router.post("/login/student")
def student_login(
    request: Request,
    roll: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .filter(Student.roll.ilike(roll.strip()))
        .first()
    )
    if (
        student is None
        or not student.password_hash
        or student.account_status != "approved"
        or not verify_password(password, student.password_hash)
    ):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "role": "Student",
                "action": "/login/student",
                "error": "Roll number or password is incorrect.",
            },
            status_code=401,
        )
    request.session.clear()
    request.session.update({"role": "student", "user_id": student.id})
    return RedirectResponse("/student/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/student/setup-password")
def student_setup_password_page(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    student = (
        db.query(Student)
        .filter(
            Student.setup_token_hash == token_hash,
            Student.setup_token_expires > int(time.time()),
            Student.account_status == "approved",
        )
        .first()
    )
    if student is None:
        return templates.TemplateResponse(
            request=request,
            name="student_setup_password.html",
            context={"token": token, "error": "This setup link is invalid or has expired."},
            status_code=400,
        )
    return templates.TemplateResponse(
        request=request,
        name="student_setup_password.html",
        context={"token": token, "error": None},
    )


@router.post("/student/setup-password")
def set_student_password(
    request: Request,
    token: str = Form(),
    password: str = Form(min_length=4, max_length=4),
    confirm_password: str = Form(min_length=4, max_length=4),
    db: Session = Depends(get_db),
):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    student = (
        db.query(Student)
        .filter(
            Student.setup_token_hash == token_hash,
            Student.setup_token_expires > int(time.time()),
            Student.account_status == "approved",
        )
        .first()
    )
    if student is None:
        error = "This setup link is invalid or has expired."
    elif not password.isascii() or not password.isdigit():
        error = "Password must contain exactly 4 digits (0-9)."
    elif password != confirm_password:
        error = "Passwords do not match."
    else:
        student.password_hash = hash_password(password)
        student.setup_token_hash = None
        student.setup_token_expires = None
        db.commit()
        request.session.clear()
        request.session.update({"role": "student", "user_id": student.id})
        return RedirectResponse(
            "/student/dashboard",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return templates.TemplateResponse(
        request=request,
        name="student_setup_password.html",
        context={"token": token, "error": error},
        status_code=400,
    )


@router.get("/setup/admin")
def admin_setup_page(request: Request, db: Session = Depends(get_db)):
    if db.query(AdminAccount).count():
        return RedirectResponse("/login/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request=request,
        name="admin_setup.html",
        context={"error": None},
    )


@router.post("/setup/admin")
def create_first_admin(
    request: Request,
    username: str = Form(min_length=3, max_length=100),
    password: str = Form(min_length=6, max_length=6),
    confirm_password: str = Form(min_length=6, max_length=6),
    db: Session = Depends(get_db),
):
    if db.query(AdminAccount).count():
        return RedirectResponse("/login/admin", status_code=status.HTTP_303_SEE_OTHER)
    if not password.isascii() or not password.isdigit():
        return templates.TemplateResponse(
            request=request,
            name="admin_setup.html",
            context={"error": "Admin password must contain exactly 6 digits (0-9)."},
            status_code=400,
        )
    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="admin_setup.html",
            context={"error": "Passwords do not match."},
            status_code=400,
        )
    admin = AdminAccount(
        id=1,
        username=username.strip(),
        password_hash=hash_password(password),
    )
    db.add(admin)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/login/admin", status_code=status.HTTP_303_SEE_OTHER)
    request.session.clear()
    request.session.update({"role": "admin", "user_id": admin.id, "username": admin.username})
    return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@router.post(
    "/admin/registrations/{student_id}/approve",
    dependencies=[Depends(require_admin)],
)
def approve_student_registration(
    student_id: int,
    db: Session = Depends(get_db),
):
    if not approve_pending_registration(student_id, db):
        return RedirectResponse(
            "/admin/authorised-list?email_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/admin/authorised-list?approved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/semester-update-requests/approve-selected",
    dependencies=[Depends(require_admin)],
)
def approve_selected_semester_update_requests(
    request_ids: list[int] = Form(default=[]),
    department: str = Form(default=""),
    requested_semester: str = Form(default=""),
    db: Session = Depends(get_db),
):
    filters = {}
    if department:
        filters["department"] = department
    if requested_semester:
        filters["requested_semester"] = requested_semester
    selected_ids = set(request_ids)
    if not selected_ids:
        filters["semester_request_error"] = "1"
        return RedirectResponse(
            f"/admin/authorised-list?{urlencode(filters)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    selected_requests = (
        db.query(SemesterUpdateRequest, Student)
        .join(Student, Student.id == SemesterUpdateRequest.student_id)
        .filter(
            SemesterUpdateRequest.id.in_(selected_ids),
            SemesterUpdateRequest.status == "pending",
        )
        .all()
    )
    if len(selected_requests) != len(selected_ids) or (
        department
        and any(student.department != department for _, student in selected_requests)
    ) or (
        requested_semester
        and any(
            semester_request.requested_semester != requested_semester
            for semester_request, _ in selected_requests
        )
    ):
        filters["semester_request_error"] = "1"
        return RedirectResponse(
            f"/admin/authorised-list?{urlencode(filters)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    for semester_request, student in selected_requests:
        student.semester = semester_request.requested_semester
        semester_request.status = "approved"
        semester_request.reviewed_at = datetime.utcnow()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not bulk approve semester update requests")
        filters["semester_request_error"] = "1"
        return RedirectResponse(
            f"/admin/authorised-list?{urlencode(filters)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    filters["semester_request_approved_count"] = str(len(selected_requests))
    return RedirectResponse(
        f"/admin/authorised-list?{urlencode(filters)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/semester-update-requests/{request_id}/{decision}",
    dependencies=[Depends(require_admin)],
)
def review_semester_update_request(
    request_id: int,
    decision: str,
    db: Session = Depends(get_db),
):
    if decision not in {"approve", "reject"}:
        return RedirectResponse(
            "/admin/authorised-list?semester_request_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    semester_request = (
        db.query(SemesterUpdateRequest)
        .filter_by(id=request_id, status="pending")
        .first()
    )
    if semester_request is None:
        return RedirectResponse(
            "/admin/authorised-list?semester_request_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    student = db.query(Student).filter_by(id=semester_request.student_id).first()
    if student is None:
        return RedirectResponse(
            "/admin/authorised-list?semester_request_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if decision == "approve":
        student.semester = semester_request.requested_semester
        semester_request.status = "approved"
    else:
        semester_request.status = "rejected"
    semester_request.reviewed_at = datetime.utcnow()
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not review semester update request %s", request_id)
        return RedirectResponse(
            "/admin/authorised-list?semester_request_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    result = "approved" if decision == "approve" else "rejected"
    return RedirectResponse(
        f"/admin/authorised-list?semester_request_{result}=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/teachers/{teacher_id}/approve",
    dependencies=[Depends(require_admin)],
)
def approve_teacher_account(teacher_id: int, db: Session = Depends(get_db)):
    teacher = (
        db.query(TeacherAccount)
        .filter_by(id=teacher_id, account_status="pending")
        .first()
    )
    if teacher is not None:
        teacher.account_status = "approved"
        db.commit()
    return RedirectResponse(
        "/admin/authorised-list?teacher_approved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/teachers/approve-selected",
    dependencies=[Depends(require_admin)],
)
def approve_selected_teacher_accounts(
    teacher_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    selected_ids = set(teacher_ids)
    approved_count = 0
    if not selected_ids:
        return RedirectResponse(
            "/admin/authorised-list?teacher_approval_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        approved_count = (
            db.query(TeacherAccount)
            .filter(
                TeacherAccount.id.in_(selected_ids),
                TeacherAccount.account_status == "pending",
            )
            .update(
                {TeacherAccount.account_status: "approved"},
                synchronize_session=False,
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not bulk approve teacher accounts")
        return RedirectResponse(
            "/admin/authorised-list?teacher_approval_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/authorised-list?teacher_approved_count={approved_count}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/teachers/{teacher_id}/reject",
    dependencies=[Depends(require_admin)],
)
def reject_teacher_account(teacher_id: int, db: Session = Depends(get_db)):
    teacher = (
        db.query(TeacherAccount)
        .filter_by(id=teacher_id, account_status="pending")
        .first()
    )
    if teacher is not None:
        teacher.account_status = "rejected"
        db.commit()
    return RedirectResponse(
        "/admin/authorised-list",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/registrations/{student_id}/approve-manual",
    dependencies=[Depends(require_admin)],
)
def approve_student_registration_with_password(
    student_id: int,
    password: str = Form(min_length=4, max_length=4),
    db: Session = Depends(get_db),
):
    student = (
        db.query(Student)
        .filter_by(id=student_id, account_status="pending")
        .first()
    )
    if student is None:
        return RedirectResponse("/admin/authorised-list", status_code=status.HTTP_303_SEE_OTHER)
    if not password.isascii() or not password.isdigit():
        return RedirectResponse(
            "/admin/authorised-list?password_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    student.password_hash = hash_password(password)
    student.setup_token_hash = None
    student.setup_token_expires = None
    try:
        student.account_status = "approved"
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not save manual approval for student %s", student_id)
        return RedirectResponse(
            "/admin/authorised-list?approval_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        send_student_credentials_email(student.email, student.roll, password)
    except (OSError, RuntimeError, smtplib.SMTPException, SQLAlchemyError):
        logger.exception("Could not approve and email student credentials %s", student_id)
        return RedirectResponse(
            "/admin/authorised-list?manual_email_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/admin/authorised-list?manual_approved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/registrations/approve-selected",
    dependencies=[Depends(require_admin)],
)
def approve_selected_student_registrations(
    student_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
):
    approved_count = sum(
        approve_pending_registration(student_id, db)
        for student_id in dict.fromkeys(student_ids)
    )
    failed_count = len(set(student_ids)) - approved_count
    return RedirectResponse(
        f"/admin/authorised-list?approved_count={approved_count}&failed_count={failed_count}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/registrations/approve-all",
    dependencies=[Depends(require_admin)],
)
def approve_all_student_registrations(db: Session = Depends(get_db)):
    pending_ids = [
        student_id
        for (student_id,) in (
            db.query(Student.id)
            .filter_by(account_status="pending")
            .order_by(Student.id)
            .all()
        )
    ]
    approved_count = sum(
        approve_pending_registration(student_id, db)
        for student_id in pending_ids
    )
    failed_count = len(pending_ids) - approved_count
    return RedirectResponse(
        f"/admin/authorised-list?approved_count={approved_count}&failed_count={failed_count}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/registrations/approve-excel-passwords",
    dependencies=[Depends(require_admin)],
)
def approve_excel_password_registrations(db: Session = Depends(get_db)):
    students = (
        db.query(Student)
        .filter(
            Student.account_status == "pending",
            Student.password_hash.is_not(None),
        )
        .order_by(Student.id)
        .all()
    )
    for student in students:
        student.account_status = "approved"
        student.setup_token_hash = None
        student.setup_token_expires = None
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not approve Excel-password student registrations")
        return RedirectResponse(
            "/admin/authorised-list?approval_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        f"/admin/authorised-list?password_approved_count={len(students)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/registrations/{student_id}/resend-setup",
    dependencies=[Depends(require_admin)],
)
def resend_student_setup_email(student_id: int, db: Session = Depends(get_db)):
    student = (
        db.query(Student)
        .filter_by(id=student_id, account_status="approved", password_hash=None)
        .first()
    )
    if student is None:
        return RedirectResponse("/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    token = secrets.token_urlsafe(32)
    student.setup_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    student.setup_token_expires = int(time.time()) + STUDENT_SETUP_TOKEN_LIFETIME
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    setup_url = f"{base_url}/student/setup-password?token={token}"
    try:
        send_student_setup_email(student.email, student.roll, setup_url)
        db.commit()
    except (OSError, RuntimeError, smtplib.SMTPException, SQLAlchemyError):
        db.rollback()
        logger.exception("Could not resend setup email for student %s", student_id)
        return RedirectResponse(
            "/admin/authorised-list?email_error=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/admin/authorised-list?approved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/admin/registrations/{student_id}/reject",
    dependencies=[Depends(require_admin)],
)
def reject_student_registration(student_id: int, db: Session = Depends(get_db)):
    student = (
        db.query(Student)
        .filter_by(id=student_id, account_status="pending")
        .first()
    )
    if student is not None:
        student.account_status = "rejected"
        db.commit()
    return RedirectResponse("/admin/authorised-list", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
