from student_repository import StudentRepository
from student_model import Student


class StudentService:
    def __init__(self, student_repository: StudentRepository):
        self.student_repository = student_repository

    def add_student(self, student: Student) -> Student:
        return self.student_repository.add_student(student)

    def get_student_by_id(self, student_id: int) -> Student | None:
        return self.student_repository.get_student_by_id(student_id)

    def get_student_by_roll(self, roll: str) -> Student | None:
        return self.student_repository.get_student_by_roll(roll)

    def get_all_students(self) -> list[Student]:
        return self.student_repository.get_all_students()

    def update_student(
        self,
        student_id: int,
        student_data: dict[str, object],
    ) -> Student | None:
        student = self.get_student_by_id(student_id)
        if student is None:
            return None

        for field, value in student_data.items():
            setattr(student, field, value)

        return self.student_repository.update_student(student)

    def delete_student(self, student_id: int) -> bool:
        student = self.get_student_by_id(student_id)
        if student is None:
            return False

        self.student_repository.delete_student(student)
        return True
    