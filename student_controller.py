from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from auth_security import require_admin_api
from database import get_db
from schema import StudentCreate, StudentResponse, StudentUpdate
from student_model import Student
from student_repository import StudentRepository
from student_service import StudentService


router = APIRouter(
    prefix="/students",
    tags=["students"],
    dependencies=[Depends(require_admin_api)],
)


@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(data: StudentCreate, db: Session = Depends(get_db)):
    service = StudentService(StudentRepository(db))
    student_data = data.model_dump()
    student_data["roll"] = data.roll.strip()
    if service.get_student_by_roll(student_data["roll"]):
        raise HTTPException(status_code=409, detail="Roll number already exists")
    student = Student(**student_data)
    return service.add_student(student)


@router.get("", response_model=list[StudentResponse])
def get_students(db: Session = Depends(get_db)):
    service = StudentService(StudentRepository(db))
    return service.get_all_students()


@router.get("/{student_id}", response_model=StudentResponse)
def get_student(student_id: int, db: Session = Depends(get_db)):
    service = StudentService(StudentRepository(db))
    student = service.get_student_by_id(student_id)

    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    return student


@router.put("/{student_id}", response_model=StudentResponse)
def update_student(
    student_id: int,
    data: StudentUpdate,
    db: Session = Depends(get_db),
):
    service = StudentService(StudentRepository(db))
    student_data = data.model_dump(exclude_unset=True)
    student_data["roll"] = data.roll.strip()
    existing_student = service.get_student_by_roll(student_data["roll"])
    if existing_student and existing_student.id != student_id:
        raise HTTPException(status_code=409, detail="Roll number already exists")
    student = service.update_student(student_id, student_data)

    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    return student


@router.delete(
    "/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_student(student_id: int, db: Session = Depends(get_db)):
    service = StudentService(StudentRepository(db))

    if not service.delete_student(student_id):
        raise HTTPException(status_code=404, detail="Student not found")
