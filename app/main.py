"""Lietotāju reģistrācija un pieteikšanās (CR-4).

Palaišana: `uvicorn --factory app.main:create_app --reload`, tad atver `/register` vai `/login`.
Datu bāzes fails: vides mainīgais `AUTH_DB_PATH` (noklusējums `auth.db`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import Database
from app.security import DUMMY_HASH, hash_password, new_session_token, verify_password

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
SESSION_COOKIE = "session"
STATIC_DIR = Path(__file__).parent / "static"


class Credentials(BaseModel):
    # Lauku tipus pārbauda paši, lai kļūdas atbilstu līguma Error shēmai.
    email: Any = None
    password: Any = None


def error(status: int, code: str, message: str, details: list[dict] | None = None):
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def validation_error(details: list[dict]) -> JSONResponse:
    return error(400, "VALIDATION_ERROR", "Request validation failed", details)


def check_credentials(data: Credentials, check_length: bool) -> tuple[str, str, list[dict]]:
    details: list[dict] = []

    email = data.email
    if email is None or (isinstance(email, str) and not email.strip()):
        details.append({"field": "email", "issue": "REQUIRED"})
    elif not isinstance(email, str) or not EMAIL_PATTERN.match(email.strip()):
        details.append({"field": "email", "issue": "INVALID_FORMAT"})
    else:
        email = email.strip().lower()

    password = data.password
    if password is None or password == "":
        details.append({"field": "password", "issue": "REQUIRED"})
    elif not isinstance(password, str):
        details.append({"field": "password", "issue": "INVALID_FORMAT"})
    elif check_length and len(password) < MIN_PASSWORD_LENGTH:
        details.append({"field": "password", "issue": "TOO_SHORT"})

    return email, password, details


def create_app(db_path: str | None = None) -> FastAPI:
    db = Database(db_path or os.environ.get("AUTH_DB_PATH", "auth.db"))
    app = FastAPI(title="Ezermalas pieteikumu sistēma · lietotāji (CR-4)")

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        details = []
        for item in exc.errors():
            loc = [str(part) for part in item.get("loc", ()) if part != "body"]
            issue = "REQUIRED" if item.get("type") == "missing" else "INVALID_FORMAT"
            details.append({"field": loc[0] if loc else "body", "issue": issue})
        return validation_error(details)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def on_unexpected_error(request: Request, exc: Exception):
        return error(500, "INTERNAL_ERROR", "Unexpected server error")

    @app.post("/auth/register", status_code=201)
    def register(data: Credentials):
        email, password, details = check_credentials(data, check_length=True)
        if details:
            return validation_error(details)

        user_id = db.create_user(email, hash_password(password))
        if user_id is None:
            return error(
                409,
                "ALREADY_EXISTS",
                "User already exists",
                [{"field": "email", "issue": "ALREADY_EXISTS"}],
            )
        return JSONResponse(status_code=201, content={"id": user_id, "email": email})

    @app.post("/auth/login")
    def login(data: Credentials):
        email, password, details = check_credentials(data, check_length=False)
        if details:
            return validation_error(details)

        user = db.find_user(email)
        valid = verify_password(password, user["password_hash"] if user else DUMMY_HASH)
        if not user or not valid:
            return error(401, "INVALID_CREDENTIALS", "Invalid email or password")

        token, token_hash = new_session_token()
        db.create_session(token_hash, user["id"])
        result = JSONResponse(content={"id": user["id"], "email": user["email"]})
        result.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
        return result

    @app.get("/register", include_in_schema=False)
    def register_page():
        return FileResponse(STATIC_DIR / "register.html")

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(STATIC_DIR / "login.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
