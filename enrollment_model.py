from datetime import date

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint

from database import Base


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        UniqueConstraint(
            "code",
            "department",
            "semester",
            name="uq_subject_code_department_semester",
        ),
    )

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teacher_accounts.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False)
    department = Column(String(255), nullable=False, index=True)
    semester = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")


class SubjectEnrollment(Base):
    __tablename__ = "subject_enrollments"
    __table_args__ = (
        UniqueConstraint("subject_id", "student_id", name="uq_subject_student_enrollment"),
    )

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")


class TeacherQualification(Base):
    __tablename__ = "teacher_qualifications"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teacher_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    level = Column(String(50), nullable=False)
    passing_year = Column(String(4), nullable=False)
    institution = Column(String(255), nullable=True)
    subject = Column(String(255), nullable=True)


class TeacherTrainingExperience(Base):
    __tablename__ = "teacher_training_experiences"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teacher_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=True)
    period = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)


class TeacherTrainingArea(Base):
    __tablename__ = "teacher_training_areas"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teacher_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)


class TeacherEmployment(Base):
    __tablename__ = "teacher_employments"

    id = Column(Integer, primary_key=True)
    teacher_id = Column(Integer, ForeignKey("teacher_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    organization = Column(String(255), nullable=False)
    position = Column(String(255), nullable=True)
    period = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)


class SubjectPresentation(Base):
    __tablename__ = "subject_presentations"

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(Integer, ForeignKey("teacher_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    presentation_date = Column(Date, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_data = Column(LargeBinary, nullable=False)
    uploaded_at = Column(Date, nullable=False, default=date.today)
