import logging
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth_security import require_student
from auth_model import TeacherAccount
from database import get_db
from enrollment_model import Subject, SubjectEnrollment
from image_utils import read_picture
from student_model import SemesterUpdateRequest, Student
from web_controller import SEMESTERS


router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/portal")
@router.get("/student/dashboard")
def student_portal(
    request: Request,
    semester: str | None = None,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    query = db.query(Student).filter(Student.account_status == "approved")
    if student.department:
        query = query.filter(Student.department == student.department)
    else:
        query = query.filter(Student.id == student.id)
    semester_query = db.query(Student.semester).filter(
        Student.account_status == "approved",
        Student.semester.is_not(None),
        Student.semester != "",
    )
    if student.department:
        semester_query = semester_query.filter(Student.department == student.department)
    else:
        semester_query = semester_query.filter(Student.id == student.id)
    available_semesters = sorted(
        {value for (value,) in semester_query.distinct().all()},
        key=lambda value: int("".join(char for char in value if char.isdigit()) or "99"),
    )
    if semester and semester in available_semesters:
        query = query.filter(Student.semester == semester)
    else:
        semester = ""
    classmates = query.order_by(Student.name).all()
    enrolled_subjects = (
        db.query(Subject, TeacherAccount)
        .join(
            SubjectEnrollment,
            SubjectEnrollment.subject_id == Subject.id,
        )
        .join(TeacherAccount, TeacherAccount.id == Subject.teacher_id)
        .filter(
            SubjectEnrollment.student_id == student.id,
            SubjectEnrollment.status == "approved",
        )
        .order_by(Subject.department, Subject.semester, Subject.name)
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="student_portal.html",
        context={
            "student": student,
            "classmates": classmates,
            "semesters": available_semesters,
            "selected_semester": semester,
            "enrolled_subjects": enrolled_subjects,
        },
    )


@router.get("/student/semester-update")
def semester_update_page(
    request: Request,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    pending_request = (
        db.query(SemesterUpdateRequest)
        .filter_by(student_id=student.id, status="pending")
        .order_by(SemesterUpdateRequest.created_at.desc())
        .first()
    )
    current_semester_index = (
        SEMESTERS.index(student.semester)
        if student.semester in SEMESTERS
        else None
    )
    available_semesters = [
        semester
        for index, semester in enumerate(SEMESTERS)
        if current_semester_index is None or index > current_semester_index
    ]
    return templates.TemplateResponse(
        request=request,
        name="student_semester_update.html",
        context={
            "student": student,
            "semesters": available_semesters,
            "pending_request": pending_request,
            "requested": request.query_params.get("requested") == "1",
            "error": request.query_params.get("error"),
        },
    )


@router.post("/student/semester-update")
def submit_semester_update_request(
    requested_semester: str = Form(),
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    if requested_semester not in SEMESTERS:
        return RedirectResponse(
            "/student/semester-update?error=invalid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if requested_semester == student.semester:
        return RedirectResponse(
            "/student/semester-update?error=same",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if (
        student.semester in SEMESTERS
        and SEMESTERS.index(requested_semester) < SEMESTERS.index(student.semester)
    ):
        return RedirectResponse(
            "/student/semester-update?error=lower",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    pending_request = (
        db.query(SemesterUpdateRequest)
        .filter_by(student_id=student.id, status="pending")
        .first()
    )
    if pending_request is not None:
        return RedirectResponse(
            "/student/semester-update?error=pending",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    db.add(
        SemesterUpdateRequest(
            student_id=student.id,
            current_semester=student.semester or "Not set",
            requested_semester=requested_semester,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Could not create semester update request for student %s", student.id)
        raise
    return RedirectResponse(
        "/student/semester-update?requested=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/portal/profile/edit")
def edit_student_profile(
    request: Request,
    student: Student = Depends(require_student),
):
    return templates.TemplateResponse(
        request=request,
        name="student_profile_edit.html",
        context={"student": student, "error": None},
    )


@router.post("/portal/profile/edit")
async def save_student_profile(
    request: Request,
    name: str = Form(max_length=255),
    email: str = Form(max_length=255),
    phone_number: str = Form(default="", max_length=30),
    district: str = Form(default="", max_length=255),
    upazila: str = Form(default="", max_length=255),
    union_name: str = Form(default="", max_length=255),
    village: str = Form(default="", max_length=255),
    experience: str = Form(default="", max_length=2000),
    working_place: str = Form(default="", max_length=255),
    picture: UploadFile | None = File(default=None),
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    values = {
        "name": name.strip(),
        "email": email.strip(),
        "phone_number": phone_number.strip(),
        "district": district.strip(),
        "upazila": upazila.strip(),
        "union_name": union_name.strip(),
        "village": village.strip(),
        "experience": experience.strip(),
        "working_place": working_place.strip(),
    }
    if not values["name"] or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        values["email"],
    ):
        return templates.TemplateResponse(
            request=request,
            name="student_profile_edit.html",
            context={"student": student, "error": "Please provide a name and valid email address."},
            status_code=400,
        )

    picture_data, picture_type = await read_picture(picture)
    for field, value in values.items():
        setattr(student, field, value or None)
    if picture_data is not None:
        student.picture_data = picture_data
        student.picture_type = picture_type
    db.commit()
    return RedirectResponse(
        "/student/dashboard?profile_updated=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/portal/profile/picture")
def student_profile_picture(
    student: Student = Depends(require_student),
):
    if student.picture_data is None or student.picture_type is None:
        raise HTTPException(status_code=404, detail="Profile picture not found")
    return Response(student.picture_data, media_type=student.picture_type)


@router.get("/portal/students/{student_id}/phone")
def reveal_classmate_phone(
    student_id: int,
    student: Student = Depends(require_student),
    db: Session = Depends(get_db),
):
    classmate = (
        db.query(Student)
        .filter_by(id=student_id, account_status="approved")
        .first()
    )
    if (
        classmate is None
        or classmate.id == student.id
        or not student.department
        or classmate.department != student.department
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return JSONResponse({"phone_number": classmate.phone_number or "No phone number"})
