from sqlalchemy import Column, Integer, LargeBinary, String

from database import Base


TEACHER_DESIGNATIONS = (
    "Principal",
    "Vice Principal",
    "Chief Instructor",
    "Instructor",
    "Junior Instructor",
    "Craft Instructor",
)


class AdminAccount(Base):
    __tablename__ = "admin_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)


class TeacherAccount(Base):
    __tablename__ = "teacher_accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    department = Column(String(255), nullable=True)
    designation = Column(String(255), nullable=True)
    personal_website = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    picture_data = Column(LargeBinary, nullable=True)
    picture_type = Column(String(50), nullable=True)
    password_hash = Column(String(255), nullable=False)
    account_status = Column(String(20), nullable=False, default="pending")
