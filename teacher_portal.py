from datetime import date
from io import BytesIO
import logging
import re
from urllib.parse import quote, urlencode
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth_model import TEACHER_DESIGNATIONS, TeacherAccount
from auth_security import require_student, require_teacher
from database import get_db
from enrollment_model import (
    Subject,
    SubjectEnrollment,
    SubjectPresentation,
    TeacherEmployment,
    TeacherQualification,
    TeacherTrainingArea,
    TeacherTrainingExperience,
)
from image_utils import read_picture
from student_model import Student
from web_controller import DEPARTMENTS, SEMESTERS


router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)
MAX_PRESENTATION_SIZE = 20 * 1024 * 1024
QUALIFICATION_LEVELS = ("SSC", "Diploma/HSC", "B.Sc", "M.Sc", "Other")


@router.get("/teacher/dashboard")
def teacher_dashboard(
    request: Request,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    subject_ids = db.query(Subject.id).filter_by(teacher_id=teacher.id)
    return templates.TemplateResponse(
        request=request,
        name="teacher_dashboard.html",
        context={
            "teacher": teacher,
            "student_count": db.query(Student).filter_by(account_status="approved").count(),
            "subject_count": db.query(Subject).filter_by(teacher_id=teacher.id).count(),
            "pending_enrollments": (
                db.query(SubjectEnrollment)
                .filter(
                    SubjectEnrollment.subject_id.in_(subject_ids),
                    SubjectEnrollment.status == "pending",
                )
                .count()
            ),
        },
    )


@router.get("/teacher/profile")
def teacher_profile(
    request: Request,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(
        request=request,
        name="teacher_profile.html",
        context={
            "teacher": teacher,
            "departments": DEPARTMENTS,
            "designations": TEACHER_DESIGNATIONS,
            "qualification_levels": QUALIFICATION_LEVELS,
            "qualifications": (
                db.query(TeacherQualification)
                .filter_by(teacher_id=teacher.id)
                .order_by(TeacherQualification.id)
                .all()
            ),
            "training_experiences": (
                db.query(TeacherTrainingExperience)
                .filter_by(teacher_id=teacher.id)
                .order_by(TeacherTrainingExperience.id)
                .all()
            ),
            "training_areas": (
                db.query(TeacherTrainingArea)
                .filter_by(teacher_id=teacher.id)
                .order_by(TeacherTrainingArea.id)
                .all()
            ),
            "employments": (
                db.query(TeacherEmployment)
                .filter_by(teacher_id=teacher.id)
                .order_by(TeacherEmployment.id)
                .all()
            ),
            "updated": request.query_params.get("updated") == "1",
            "error": request.query_params.get("error"),
        },
    )


@router.post("/teacher/profile")
async def update_teacher_profile(
    name: str = Form(min_length=1, max_length=255),
    designation: str = Form(default="", max_length=255),
    department: str = Form(default="", max_length=255),
    personal_website: str = Form(default="", max_length=500),
    email: str = Form(min_length=3, max_length=255),
    phone: str = Form(default="", max_length=50),
    qualification_level: list[str] = Form(default=[]),
    qualification_year: list[str] = Form(default=[]),
    qualification_institution: list[str] = Form(default=[]),
    qualification_subject: list[str] = Form(default=[]),
    training_name: list[str] = Form(default=[]),
    training_organization: list[str] = Form(default=[]),
    training_period: list[str] = Form(default=[]),
    training_details: list[str] = Form(default=[]),
    training_area: list[str] = Form(default=[]),
    employment_organization: list[str] = Form(default=[]),
    employment_position: list[str] = Form(default=[]),
    employment_period: list[str] = Form(default=[]),
    employment_details: list[str] = Form(default=[]),
    picture: UploadFile | None = File(default=None),
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    error_url = "/teacher/profile?error=invalid"
    if (
        not name.strip()
        or designation not in TEACHER_DESIGNATIONS
        or (department and department not in DEPARTMENTS)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip())
        or (
            personal_website.strip()
            and not re.fullmatch(r"https?://[^\s]+", personal_website.strip())
        )
    ):
        return RedirectResponse(
            error_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )
    row_groups = (
        (qualification_level, qualification_year, qualification_institution, qualification_subject),
        (training_name, training_organization, training_period, training_details),
        (employment_organization, employment_position, employment_period, employment_details),
    )
    if any(len({len(values) for values in group}) != 1 for group in row_groups):
        return RedirectResponse(error_url, status_code=status.HTTP_303_SEE_OTHER)
    qualifications = []
    for level, year, institution, subject in zip(
        qualification_level,
        qualification_year,
        qualification_institution,
        qualification_subject,
    ):
        level, year = level.strip(), year.strip()
        if not any((level, year, institution.strip(), subject.strip())):
            continue
        if (
            level not in QUALIFICATION_LEVELS
            or not re.fullmatch(r"\d{4}", year)
            or int(year) > date.today().year
        ):
            return RedirectResponse(error_url, status_code=status.HTTP_303_SEE_OTHER)
        qualifications.append((level, year, institution.strip(), subject.strip()))
    training_rows = []
    for item in zip(training_name, training_organization, training_period, training_details):
        if any(value.strip() for value in item):
            if not item[0].strip():
                return RedirectResponse(error_url, status_code=status.HTTP_303_SEE_OTHER)
            training_rows.append(tuple(value.strip() for value in item))
    areas = [value.strip() for value in training_area if value.strip()]
    employment_rows = []
    for item in zip(
        employment_organization,
        employment_position,
        employment_period,
        employment_details,
    ):
        if any(value.strip() for value in item):
            if not item[0].strip():
                return RedirectResponse(error_url, status_code=status.HTTP_303_SEE_OTHER)
            employment_rows.append(tuple(value.strip() for value in item))
    try:
        picture_data, picture_type = await read_picture(picture)
    except HTTPException as exc:
        if exc.status_code in (400, 413):
            return RedirectResponse(
                "/teacher/profile?error=picture",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        raise
    teacher.name = name.strip()
    teacher.designation = designation.strip() or None
    teacher.department = department or None
    teacher.personal_website = personal_website.strip() or None
    teacher.email = email.strip().lower()
    teacher.phone = phone.strip() or None
    if picture_data is not None and picture_type is not None:
        teacher.picture_data = picture_data
        teacher.picture_type = picture_type
    db.query(TeacherQualification).filter_by(teacher_id=teacher.id).delete()
    db.query(TeacherTrainingExperience).filter_by(teacher_id=teacher.id).delete()
    db.query(TeacherTrainingArea).filter_by(teacher_id=teacher.id).delete()
    db.query(TeacherEmployment).filter_by(teacher_id=teacher.id).delete()
    db.add_all(
        [
            TeacherQualification(
                teacher_id=teacher.id,
                level=level,
                passing_year=year,
                institution=institution or None,
                subject=subject or None,
            )
            for level, year, institution, subject in qualifications
        ]
    )
    db.add_all(
        [
            TeacherTrainingExperience(
                teacher_id=teacher.id,
                name=name,
                organization=organization or None,
                period=period or None,
                details=details or None,
            )
            for name, organization, period, details in training_rows
        ]
    )
    db.add_all(
        [
            TeacherTrainingArea(teacher_id=teacher.id, name=area)
            for area in areas
        ]
    )
    db.add_all(
        [
            TeacherEmployment(
                teacher_id=teacher.id,
                organization=organization,
                position=position or None,
                period=period or None,
                details=details or None,
            )
            for organization, position, period, details in employment_rows
        ]
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            "/teacher/profile?error=duplicate",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not update teacher profile %s", teacher.id)
        return RedirectResponse(
            "/teacher/profile?error=save",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/teacher/profile?updated=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/teacher/students")
def teacher_student_directory(
    request: Request,
    search: str = "",
    department: str = "",
    semester: str = "",
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    query = db.query(Student).filter(Student.account_status == "approved")
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            Student.name.ilike(term)
            | Student.roll.ilike(term)
            | Student.registration.ilike(term)
            | Student.email.ilike(term)
            | Student.phone_number.ilike(term)
            | Student.department.ilike(term)
            | Student.district.ilike(term)
            | Student.upazila.ilike(term)
        )
    if department:
        query = query.filter(Student.department == department)
    if semester:
        query = query.filter(Student.semester == semester)
    students = query.order_by(Student.department, Student.semester, Student.name).all()
    return templates.TemplateResponse(
        request=request,
        name="teacher_students.html",
        context={
            "teacher": teacher,
            "students": students,
            "search": search,
            "department": department,
            "semester": semester,
            "departments": DEPARTMENTS,
            "semesters": SEMESTERS,
        },
    )


@router.get("/teacher/subjects")
def teacher_subjects(
    request: Request,
    edit_id: int | None = None,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    edit_subject = None
    if edit_id is not None:
        edit_subject = (
            db.query(Subject)
            .filter_by(id=edit_id, teacher_id=teacher.id)
            .first()
        )
        if edit_subject is None:
            raise HTTPException(status_code=404, detail="Subject not found")
    return templates.TemplateResponse(
        request=request,
        name="teacher_subjects.html",
        context={
            "teacher": teacher,
            "subjects": (
                db.query(Subject)
                .filter_by(teacher_id=teacher.id)
                .order_by(Subject.department, Subject.semester, Subject.name)
                .all()
            ),
            "departments": DEPARTMENTS,
            "semesters": SEMESTERS,
            "edit_subject": edit_subject,
            "created": request.query_params.get("created") == "1",
            "error": request.query_params.get("error"),
            "updated": request.query_params.get("updated") == "1",
            "subject_status": request.query_params.get("subject_status"),
        },
    )


@router.post("/teacher/subjects")
def create_teacher_subject(
    name: str = Form(min_length=1, max_length=255),
    code: str = Form(min_length=1, max_length=50),
    department: str = Form(min_length=1, max_length=255),
    semester: str = Form(min_length=1, max_length=50),
    description: str = Form(default="", max_length=2000),
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    if department not in DEPARTMENTS or semester not in SEMESTERS:
        return RedirectResponse(
            "/teacher/subjects?error=invalid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    subject = Subject(
        teacher_id=teacher.id,
        name=name.strip(),
        code=code.strip().upper(),
        department=department,
        semester=semester,
        description=description.strip() or None,
    )
    db.add(subject)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            "/teacher/subjects?error=duplicate",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/teacher/subjects?created=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/teacher/subjects/{subject_id}/edit")
def edit_teacher_subject(
    subject_id: int,
    name: str = Form(min_length=1, max_length=255),
    code: str = Form(min_length=1, max_length=50),
    department: str = Form(min_length=1, max_length=255),
    semester: str = Form(min_length=1, max_length=50),
    description: str = Form(default="", max_length=2000),
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    subject = (
        db.query(Subject)
        .filter_by(id=subject_id, teacher_id=teacher.id)
        .first()
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if department not in DEPARTMENTS or semester not in SEMESTERS:
        return RedirectResponse(
            f"/teacher/subjects?edit_id={subject.id}&error=invalid",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    subject.name = name.strip()
    subject.code = code.strip().upper()
    subject.department = department
    subject.semester = semester
    subject.description = description.strip() or None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"/teacher/subjects?edit_id={subject_id}&error=duplicate",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not update subject %s", subject_id)
        raise
    return RedirectResponse(
        "/teacher/subjects?updated=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/teacher/subjects/{subject_id}/status/{action}")
def change_teacher_subject_status(
    subject_id: int,
    action: str,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    if action not in {"activate", "deactivate"}:
        raise HTTPException(status_code=404, detail="Subject action not found")
    subject = (
        db.query(Subject)
        .filter_by(id=subject_id, teacher_id=teacher.id)
        .first()
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    subject.is_active = action == "activate"
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not change subject status for subject %s", subject_id)
        raise
    return RedirectResponse(
        f"/teacher/subjects?subject_status={action}d",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/teacher/enrollments")
def teacher_enrollments(
    request: Request,
    department: str = "",
    semester: str = "",
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    query = (
        db.query(SubjectEnrollment, Subject, Student)
        .join(Subject, Subject.id == SubjectEnrollment.subject_id)
        .join(Student, Student.id == SubjectEnrollment.student_id)
        .filter(Subject.teacher_id == teacher.id)
    )
    if department and department in DEPARTMENTS:
        query = query.filter(Subject.department == department)
    else:
        department = ""
    if semester and semester in SEMESTERS:
        query = query.filter(Subject.semester == semester)
    else:
        semester = ""
    enrollments = query.order_by(SubjectEnrollment.status, Subject.name, Student.name).all()
    return templates.TemplateResponse(
        request=request,
        name="teacher_enrollments.html",
        context={
            "teacher": teacher,
            "enrollments": enrollments,
            "departments": DEPARTMENTS,
            "semesters": SEMESTERS,
            "department": department,
            "semester": semester,
            "updated": request.query_params.get("updated") == "1",
            "status_updated": request.query_params.get("status_updated", "").isdigit()
            and int(request.query_params.get("status_updated", "0")) > 0,
            "status_updated_count": request.query_params.get("status_updated", ""),
            "status_skipped": request.query_params.get("status_skipped", ""),
            "status_error": request.query_params.get("status_error") == "1",
        },
    )


@router.post("/teacher/enrollments/{enrollment_id}/{decision}")
def decide_student_enrollment(
    request: Request,
    enrollment_id: int,
    decision: str,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    if decision not in {"approve", "reject", "activate", "deactivate"}:
        raise HTTPException(status_code=404, detail="Enrollment action not found")
    enrollment = (
        db.query(SubjectEnrollment)
        .join(Subject, Subject.id == SubjectEnrollment.subject_id)
        .filter(
            SubjectEnrollment.id == enrollment_id,
            Subject.teacher_id == teacher.id,
        )
        .first()
    )
    allowed_transitions = {
        "approve": ("pending", "approved"),
        "reject": ("pending", "rejected"),
        "activate": ("inactive", "approved"),
        "deactivate": ("approved", "inactive"),
    }
    filters = {
        key: request.query_params.get(key, "")
        for key in ("department", "semester")
        if request.query_params.get(key)
    }
    if enrollment is None:
        filters["status_error"] = "1"
    else:
        required_status, next_status = allowed_transitions[decision]
        if enrollment.status != required_status:
            filters["status_error"] = "1"
        else:
            enrollment.status = next_status
            try:
                db.commit()
                filters["status_updated"] = "1"
            except SQLAlchemyError:
                db.rollback()
                logger.exception("Could not update enrollment %s", enrollment_id)
                raise
    return RedirectResponse(
        f"/teacher/enrollments?{urlencode(filters)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/teacher/enrollments/bulk-status")
def bulk_update_enrollment_status(
    enrollment_ids: list[int] = Form(default=[]),
    action: str = Form(),
    department: str = Form(default=""),
    semester: str = Form(default=""),
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    filters = {
        key: value
        for key, value in (("department", department), ("semester", semester))
        if value
    }
    if action not in {"activate", "deactivate"} or not enrollment_ids:
        filters["status_error"] = "1"
        return RedirectResponse(
            f"/teacher/enrollments?{urlencode(filters)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    selected_ids = set(enrollment_ids)
    selected_enrollments = (
        db.query(SubjectEnrollment)
        .join(Subject, Subject.id == SubjectEnrollment.subject_id)
        .filter(
            SubjectEnrollment.id.in_(selected_ids),
            Subject.teacher_id == teacher.id,
        )
        .all()
    )
    if len(selected_enrollments) != len(selected_ids):
        filters["status_error"] = "1"
        return RedirectResponse(
            f"/teacher/enrollments?{urlencode(filters)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    expected_status = "inactive" if action == "activate" else "approved"
    next_status = "approved" if action == "activate" else "inactive"
    changed_count = sum(
        enrollment.status == expected_status for enrollment in selected_enrollments
    )
    skipped_count = len(selected_ids) - changed_count
    if changed_count:
        try:
            for enrollment in selected_enrollments:
                if enrollment.status == expected_status:
                    enrollment.status = next_status
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Could not bulk update subject enrollments for teacher %s",
                teacher.id,
            )
            raise
        filters["status_updated"] = str(changed_count)
    if skipped_count:
        filters["status_skipped"] = str(skipped_count)
    if not changed_count:
        filters["status_error"] = "1"
    return RedirectResponse(
        f"/teacher/enrollments?{urlencode(filters)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def valid_presentation_file(filename: str, content: bytes) -> str | None:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "pdf" and content.startswith(b"%PDF-"):
        return "application/pdf"
    if extension == "ppt" and content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return "application/vnd.ms-powerpoint"
    if extension == "pptx" and content.startswith(b"PK"):
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
            if "[Content_Types].xml" in names and any(
                name.startswith("ppt/") for name in names
            ):
                return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        except BadZipFile:
            return None
    return None


@router.get("/teacher/presentations")
def teacher_presentations(
    request: Request,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    items = (
        db.query(SubjectPresentation, Subject)
        .join(Subject, Subject.id == SubjectPresentation.subject_id)
        .filter(SubjectPresentation.teacher_id == teacher.id)
        .order_by(SubjectPresentation.presentation_date.desc(), Subject.name, SubjectPresentation.title)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="teacher_presentations.html",
        context={
            "teacher": teacher,
            "subjects": (
                db.query(Subject)
                .filter_by(teacher_id=teacher.id)
                .order_by(Subject.name)
                .all()
            ),
            "presentations": items,
            "created": request.query_params.get("created") == "1",
            "deleted": request.query_params.get("deleted") == "1",
            "error": request.query_params.get("error"),
            "today": date.today().isoformat(),
        },
    )


@router.post("/teacher/presentations")
async def upload_teacher_presentation(
    subject_id: int = Form(),
    title: str = Form(min_length=1, max_length=255),
    presentation_date: date = Form(),
    presentation_file: UploadFile = File(),
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    subject = (
        db.query(Subject)
        .filter_by(id=subject_id, teacher_id=teacher.id)
        .first()
    )
    if subject is None:
        return RedirectResponse(
            "/teacher/presentations?error=subject",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if presentation_date > date.today() or not presentation_file.filename:
        return RedirectResponse(
            "/teacher/presentations?error=invalid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    content = await presentation_file.read(MAX_PRESENTATION_SIZE + 1)
    if len(content) > MAX_PRESENTATION_SIZE:
        return RedirectResponse(
            "/teacher/presentations?error=size",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    safe_filename = re.sub(
        r"[^A-Za-z0-9._ -]",
        "_",
        presentation_file.filename.replace("\\", "/").rsplit("/", 1)[-1],
    ).strip(" .")
    content_type = valid_presentation_file(safe_filename, content)
    if not content_type:
        return RedirectResponse(
            "/teacher/presentations?error=file",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    db.add(
        SubjectPresentation(
            subject_id=subject.id,
            teacher_id=teacher.id,
            title=title.strip(),
            presentation_date=presentation_date,
            filename=safe_filename,
            content_type=content_type,
            file_data=content,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not save presentation for subject %s", subject.id)
        return RedirectResponse(
            "/teacher/presentations?error=save",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(
        "/teacher/presentations?created=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/teacher/presentations/{presentation_id}/download")
def download_teacher_presentation(
    presentation_id: int,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    presentation = (
        db.query(SubjectPresentation)
        .filter_by(id=presentation_id, teacher_id=teacher.id)
        .first()
    )
    if presentation is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return Response(
        content=presentation.file_data,
        media_type=presentation.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(presentation.filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/teacher/presentations/{presentation_id}/delete")
def delete_teacher_presentation(
    presentation_id: int,
    teacher: TeacherAccount = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    presentation = (
        db.query(SubjectPresentation)
        .filter_by(id=presentation_id, teacher_id=teacher.id)
        .first()
    )
    if presentation is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    db.delete(presentation)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not delete presentation %s", presentation_id)
        raise
    return RedirectResponse(
        "/teacher/presentations?deleted=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/student/presentations")
def student_presentations(
    request: Request,
    subject_id: int | None = None,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    query = (
        db.query(SubjectPresentation, Subject)
        .join(Subject, Subject.id == SubjectPresentation.subject_id)
        .join(
            SubjectEnrollment,
            SubjectEnrollment.subject_id == Subject.id,
        )
        .filter(
            SubjectEnrollment.student_id == student.id,
            SubjectEnrollment.status == "approved",
        )
    )
    if subject_id is not None:
        query = query.filter(Subject.id == subject_id)
    return templates.TemplateResponse(
        request=request,
        name="student_presentations.html",
        context={
            "presentations": query.order_by(
                SubjectPresentation.presentation_date.desc(),
                Subject.name,
                SubjectPresentation.title,
            ).all(),
            "subjects": (
                db.query(Subject)
                .join(SubjectEnrollment, SubjectEnrollment.subject_id == Subject.id)
                .filter(
                    SubjectEnrollment.student_id == student.id,
                    SubjectEnrollment.status == "approved",
                )
                .order_by(Subject.name)
                .all()
            ),
            "subject_id": subject_id,
        },
    )


@router.get("/student/presentations/{presentation_id}/download")
def download_student_presentation(
    presentation_id: int,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    presentation = (
        db.query(SubjectPresentation)
        .join(
            SubjectEnrollment,
            SubjectEnrollment.subject_id == SubjectPresentation.subject_id,
        )
        .filter(
            SubjectPresentation.id == presentation_id,
            SubjectEnrollment.student_id == student.id,
            SubjectEnrollment.status == "approved",
        )
        .first()
    )
    if presentation is None:
        raise HTTPException(status_code=404, detail="Presentation not found")
    return Response(
        content=presentation.file_data,
        media_type=presentation.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(presentation.filename)}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/student/subjects")
def student_subjects(
    request: Request,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    subjects = (
        db.query(Subject, TeacherAccount)
        .join(TeacherAccount, TeacherAccount.id == Subject.teacher_id)
        .filter(
            TeacherAccount.account_status == "approved",
        )
        .order_by(Subject.department, Subject.semester, Subject.name)
        .all()
    )
    enrollments = (
        db.query(SubjectEnrollment)
        .filter(SubjectEnrollment.student_id == student.id)
        .all()
    )
    enrollment_by_subject = {enrollment.subject_id: enrollment for enrollment in enrollments}
    return templates.TemplateResponse(
        request=request,
        name="student_subjects.html",
        context={
            "student": student,
            "subjects": subjects,
            "enrollment_by_subject": enrollment_by_subject,
            "requested": request.query_params.get("requested") == "1",
            "requested_count": request.query_params.get("count", "0"),
            "error": request.query_params.get("error"),
            "enrolled": request.query_params.get("enrolled") == "1",
        },
    )


@router.post("/student/subjects/enroll-selected")
def request_selected_subject_enrollments(
    subject_ids: list[int] = Form(default=[]),
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    selected_ids = list(dict.fromkeys(subject_ids))
    if not selected_ids:
        return RedirectResponse(
            "/student/subjects?error=selection",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    subjects = (
        db.query(Subject)
        .join(TeacherAccount, TeacherAccount.id == Subject.teacher_id)
        .filter(
            Subject.id.in_(selected_ids),
            Subject.is_active.is_(True),
            TeacherAccount.account_status == "approved",
        )
        .all()
    )
    if len(subjects) != len(selected_ids):
        return RedirectResponse(
            "/student/subjects?error=subject",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    enrollments = (
        db.query(SubjectEnrollment)
        .filter(
            SubjectEnrollment.student_id == student.id,
            SubjectEnrollment.subject_id.in_(selected_ids),
        )
        .all()
    )
    enrollment_by_subject = {
        enrollment.subject_id: enrollment for enrollment in enrollments
    }
    requested_count = 0
    for subject in subjects:
        enrollment = enrollment_by_subject.get(subject.id)
        if enrollment is None:
            db.add(
                SubjectEnrollment(
                    subject_id=subject.id,
                    student_id=student.id,
                    status="pending",
                )
            )
            requested_count += 1
        elif enrollment.status == "rejected":
            enrollment.status = "pending"
            requested_count += 1

    if requested_count:
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception(
                "Could not create bulk enrollment requests for student %s",
                student.id,
            )
            raise
    return RedirectResponse(
        f"/student/subjects?requested=1&count={requested_count}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/student/subjects/{subject_id}/enroll")
def request_subject_enrollment(
    subject_id: int,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    subject = (
        db.query(Subject)
        .filter_by(
            id=subject_id,
            department=student.department,
        )
        .first()
    )
    if subject is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    if not subject.is_active:
        raise HTTPException(status_code=404, detail="Subject is not available for enrollment")
    enrollment = (
        db.query(SubjectEnrollment)
        .filter_by(subject_id=subject.id, student_id=student.id)
        .first()
    )
    if enrollment is None:
        db.add(
            SubjectEnrollment(
                subject_id=subject.id,
                student_id=student.id,
                status="pending",
            )
        )
    elif enrollment.status == "rejected":
        enrollment.status = "pending"
    else:
        return RedirectResponse(
            "/student/subjects",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "Could not create enrollment request for student %s and subject %s",
            student.id,
            subject.id,
        )
        raise
    return RedirectResponse(
        "/student/subjects?requested=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )
