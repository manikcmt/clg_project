from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, LargeBinary, String
from database import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    roll = Column(String(255), nullable=False, unique=True)
    registration = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    age = Column(Integer, nullable=False)
    phone_number = Column(String(30), nullable=True)
    father_name = Column(String(255), nullable=True)
    father_phone = Column(String(30), nullable=True)
    mother_name = Column(String(255), nullable=True)
    district = Column(String(255), nullable=True)
    upazila = Column(String(255), nullable=True)
    union_name = Column(String(255), nullable=True)
    village = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    semester = Column(String(50), nullable=True)
    academic_session = Column(String(100), nullable=True)
    student_id = Column(String(100), nullable=True)
    nid = Column(String(50), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    shift = Column(String(50), nullable=True)
    experience = Column(String(2000), nullable=True)
    working_place = Column(String(255), nullable=True)
    picture_data = Column(LargeBinary, nullable=True)
    picture_type = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=True)
    account_status = Column(String(20), nullable=False, default="approved")
    setup_token_hash = Column(String(64), nullable=True)
    setup_token_expires = Column(Integer, nullable=True)


class SemesterUpdateRequest(Base):
    __tablename__ = "semester_update_requests"

    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False, index=True)
    current_semester = Column(String(50), nullable=False)
    requested_semester = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)