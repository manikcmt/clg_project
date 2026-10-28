from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudentFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    roll: str = Field(min_length=1, max_length=255)
    registration: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=255)
    age: int = Field(gt=0)
    phone_number: str | None = Field(default=None, max_length=30)
    father_name: str | None = Field(default=None, max_length=255)
    father_phone: str | None = Field(default=None, max_length=30)
    mother_name: str | None = Field(default=None, max_length=255)
    district: str | None = Field(default=None, max_length=255)
    upazila: str | None = Field(default=None, max_length=255)
    union_name: str | None = Field(default=None, max_length=255)
    village: str | None = Field(default=None, max_length=255)
    department: str | None = Field(default=None, max_length=255)
    semester: str | None = Field(default=None, max_length=50)
    academic_session: str | None = Field(default=None, max_length=100)
    student_id: str | None = Field(default=None, max_length=100)
    nid: str | None = Field(default=None, max_length=50)
    date_of_birth: date | None = None
    shift: str | None = Field(default=None, max_length=50)

    @field_validator("roll", mode="before")
    @classmethod
    def clean_roll(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("date_of_birth")
    @classmethod
    def check_date_of_birth(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return value


class StudentCreate(StudentFields):
    pass


class StudentUpdate(StudentFields):
    pass


class StudentResponse(StudentFields):
    id: int

    model_config = ConfigDict(from_attributes=True)
