import os
import smtplib
import ssl
from email.message import EmailMessage


def send_student_setup_email(email: str, roll: str, setup_url: str) -> None:
    login_url = setup_url.split("/student/setup-password", 1)[0] + "/login/student"
    message = EmailMessage()
    message["Subject"] = "Your Pabna Govt. Polytechnic Institute student account"
    message["To"] = email
    message.set_content(
        f"Your student registration has been approved.\n\n"
        f"Login ID (your student roll): {roll}\n\n"
        f"First, create your password using this one-time link (valid for 24 hours):\n"
        f"{setup_url}\n\n"
        f"After creating your password, sign in with your Login ID and password here:\n"
        f"{login_url}\n\n"
        "If you did not submit this registration, please contact the institute."
    )
    _send_email(message)


def send_student_credentials_email(email: str, roll: str, password: str) -> None:
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    message = EmailMessage()
    message["Subject"] = "Your Pabna Govt. Polytechnic Institute login details"
    message["To"] = email
    message.set_content(
        f"Your student registration has been approved.\n\n"
        f"Login ID (your student roll): {roll}\n"
        f"Temporary password: {password}\n\n"
        f"Student login page: {base_url}/login/student\n\n"
        "This password was set by your Admin. Keep it private and contact your Admin if you need it reset."
    )
    _send_email(message)


def _send_email(message: EmailMessage) -> None:
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM")
    port_value = os.getenv("SMTP_PORT", "587")
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", host),
            ("SMTP_USERNAME", username),
            ("SMTP_PASSWORD", password),
            ("SMTP_FROM", sender),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Configure email settings: {', '.join(missing)}.")

    message["From"] = sender
    try:
        port = int(port_value)
    except ValueError as error:
        raise RuntimeError("SMTP_PORT must be a valid port number.") from error

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
            server.login(username, password)
            server.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(username, password)
        server.send_message(message)
