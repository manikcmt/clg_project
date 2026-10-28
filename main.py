from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from auth_controller import router as auth_router
from database import Base, engine, migrate_database
from student_controller import router as student_router
from student_portal import router as student_portal_router
from teacher_portal import router as teacher_portal_router
from web_controller import router as web_router
from auth_security import session_secret


Base.metadata.create_all(bind=engine)
migrate_database()

app = FastAPI(title="Student Management API")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret(),
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)
app.include_router(student_router)
app.include_router(student_portal_router)
app.include_router(teacher_portal_router)
app.include_router(web_router)