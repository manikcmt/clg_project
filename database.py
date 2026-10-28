import os

from sqlalchemy import (
    Date,
    Integer,
    Index,
    LargeBinary,
    String,
    create_engine,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.orm import declarative_base, sessionmaker


# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./students.db")
# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./students.db")

DATABASE_URL = "postgresql+psycopg2://practice_db_sanq_user:goqeMq6RAb5dO8iWXoeN8BGGWB35ERdc@dpg-dbcth7eq1p3s73d8vbtg-a.oregon-postgres.render.com/practice_db_sanq"




engine_options = {"connect_args": {"check_same_thread": False}}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

STUDENT_ADDITIONS = {
    "phone_number": String(30),
    "father_name": String(255),
    "father_phone": String(30),
    "mother_name": String(255),
    "district": String(255),
    "upazila": String(255),
    "union_name": String(255),
    "village": String(255),
    "department": String(255),
    "semester": String(50),
    "academic_session": String(100),
    "student_id": String(100),
    "nid": String(50),
    "date_of_birth": Date(),
    "shift": String(50),
    "experience": String(2000),
    "working_place": String(255),
    "picture_data": LargeBinary(),
    "picture_type": String(50),
    "password_hash": String(255),
    "account_status": String(20),
    "setup_token_hash": String(64),
    "setup_token_expires": Integer(),
}


def migrate_database():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "students" in table_names:
        columns = {column["name"] for column in inspector.get_columns("students")}
        with engine.begin() as connection:
            for name, sql_type in STUDENT_ADDITIONS.items():
                if name not in columns:
                    column_type = sql_type.compile(dialect=engine.dialect)
                    default_clause = " NOT NULL DEFAULT 'approved'" if name == "account_status" else ""
                    connection.execute(
                        text(
                            f'ALTER TABLE students ADD COLUMN "{name}" {column_type}'
                            f"{default_clause}"
                        )
                    )
            connection.execute(
                text("UPDATE students SET account_status = 'approved' WHERE account_status IS NULL")
            )

            students = Base.metadata.tables["students"]
            rows = connection.execute(
                select(students.c.id, students.c.roll).order_by(students.c.id)
            ).all()
            seen_rolls = set()
            used_rolls = {roll for _, roll in rows if roll is not None}
            for row_id, roll in rows:
                if roll not in seen_rolls:
                    seen_rolls.add(roll)
                    continue

                suffix = 2
                replacement = f"{roll}-{suffix}"
                while replacement in used_rolls:
                    suffix += 1
                    replacement = f"{roll}-{suffix}"
                connection.execute(
                    update(students).where(students.c.id == row_id).values(roll=replacement)
                )
                used_rolls.add(replacement)

        inspector = inspect(engine)
        has_unique_roll = any(
            constraint.get("column_names") == ["roll"]
            for constraint in inspector.get_unique_constraints("students")
        ) or any(
            index.get("unique") and index.get("column_names") == ["roll"]
            for index in inspector.get_indexes("students")
        )
        if not has_unique_roll:
            Index(
                "uq_students_roll",
                Base.metadata.tables["students"].c.roll,
                unique=True,
            ).create(bind=engine, checkfirst=True)

    if "teacher_accounts" in table_names:
        teacher_columns = {
            column["name"] for column in inspector.get_columns("teacher_accounts")
        }
        teacher_additions = {
            "department": String(255),
            "designation": String(255),
            "personal_website": String(500),
            "phone": String(50),
            "picture_data": LargeBinary(),
            "picture_type": String(50),
        }
        with engine.begin() as connection:
            for name, sql_type in teacher_additions.items():
                if name not in teacher_columns:
                    column_type = sql_type.compile(dialect=engine.dialect)
                    connection.execute(
                        text(f'ALTER TABLE teacher_accounts ADD COLUMN "{name}" {column_type}')
                    )

    if "subjects" in table_names:
        subject_columns = {
            column["name"] for column in inspector.get_columns("subjects")
        }
        if "is_active" not in subject_columns:
            boolean_type = Base.metadata.tables["subjects"].c.is_active.type.compile(
                dialect=engine.dialect
            )
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f'ALTER TABLE subjects ADD COLUMN "is_active" '
                        f"{boolean_type} NOT NULL DEFAULT 1"
                    )
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
