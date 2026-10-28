
from sqlalchemy import func
from sqlalchemy.orm import Session

from student_model import Student


class StudentRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_student(self, student: Student) -> Student:
        self.session.add(student)
        self.session.commit()
        self.session.refresh(student)
        return student

    def get_student_by_id(self, student_id: int) -> Student | None:
        return self.session.query(Student).filter_by(id=student_id).first()

    def get_student_by_roll(self, roll: str) -> Student | None:
        return self.session.query(Student).filter(
            func.lower(func.trim(Student.roll)) == roll.strip().lower()
        ).first()

    def get_all_students(self) -> list[Student]:
        return (
            self.session.query(Student)
            .filter(Student.account_status == "approved")
            .all()
        )

    def update_student(self, student: Student) -> Student:
        self.session.commit()
        self.session.refresh(student)
        return student

    def delete_student(self, student: Student) -> None:
        self.session.delete(student)
        self.session.commit()