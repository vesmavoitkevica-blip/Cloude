"""Lietotāju reģistrācija un pieteikšanās (CR-4) un organizācijas (F1).

Palaišana: `uvicorn --factory app.main:create_app --reload`, tad atver `/register`, `/login`
vai `/organizacijas`.
Datu bāzes fails: vides mainīgais `AUTH_DB_PATH` (noklusējums `auth.db`).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import Database, DuplicateRegNumber
from app.security import (
    DUMMY_HASH,
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
SESSION_COOKIE = "session"
STATIC_DIR = Path(__file__).parent / "static"
REG_NUMBER_PATTERN = re.compile(r"^[0-9]{11}$")
MAX_NAME_LENGTH = 200
MAX_ADDRESS_LENGTH = 300
# Lielāku veselu skaitli SQLite nevar saglabāt; šāda ID noteikti nav.
MAX_ID = 2**63 - 1


class Credentials(BaseModel):
    # Lauku tipus pārbauda paši, lai kļūdas atbilstu līguma Error shēmai.
    email: Any = None
    password: Any = None


class OrganizationInput(BaseModel):
    name: Any = None
    regNumber: Any = None
    address: Any = None
    responsibleUserId: Any = None


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


def optional_text(value: Any) -> str | None:
    """Tukša virkne vai tikai atstarpes neobligātajā laukā nozīmē "nav vērtības"."""
    if value is None:
        return None
    return value.strip() or None


def check_organization(
    data: OrganizationInput, db: Database
) -> tuple[dict[str, Any], list[dict]]:
    details: list[dict] = []

    name = data.name
    if name is None or (isinstance(name, str) and not name.strip()):
        details.append({"field": "name", "issue": "REQUIRED"})
    elif not isinstance(name, str):
        details.append({"field": "name", "issue": "INVALID_FORMAT"})
    elif len(name.strip()) > MAX_NAME_LENGTH:
        details.append({"field": "name", "issue": "TOO_LONG"})

    reg_number = data.regNumber
    if reg_number is not None and not isinstance(reg_number, str):
        details.append({"field": "regNumber", "issue": "INVALID_FORMAT"})
    else:
        reg_number = optional_text(reg_number)
        if reg_number is not None and not REG_NUMBER_PATTERN.match(reg_number):
            details.append({"field": "regNumber", "issue": "INVALID_FORMAT"})

    address = data.address
    if address is not None and not isinstance(address, str):
        details.append({"field": "address", "issue": "INVALID_FORMAT"})
    else:
        address = optional_text(address)
        if address is not None and len(address) > MAX_ADDRESS_LENGTH:
            details.append({"field": "address", "issue": "TOO_LONG"})

    responsible = data.responsibleUserId
    if responsible is not None:
        if not isinstance(responsible, int) or isinstance(responsible, bool):
            details.append({"field": "responsibleUserId", "issue": "INVALID_FORMAT"})
        elif not 0 < responsible <= MAX_ID or not db.user_exists(responsible):
            details.append({"field": "responsibleUserId", "issue": "NOT_FOUND"})

    values = {
        "name": name.strip() if isinstance(name, str) else name,
        "reg_number": reg_number,
        "address": address,
        "responsible_user_id": responsible,
    }
    return values, details


def organization_json(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "regNumber": row["reg_number"],
        "address": row["address"],
        "responsibleUserId": row["responsible_user_id"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def reg_number_conflict() -> JSONResponse:
    return error(
        409,
        "ALREADY_EXISTS",
        "Organization already exists",
        [{"field": "regNumber", "issue": "ALREADY_EXISTS"}],
    )


def organization_not_found() -> JSONResponse:
    return error(404, "NOT_FOUND", "Organization not found")


def create_app(db_path: str | None = None) -> FastAPI:
    db = Database(db_path or os.environ.get("AUTH_DB_PATH", "auth.db"))
    app = FastAPI(title="Ezermalas pieteikumu sistēma · lietotāji (CR-4) un organizācijas (F1)")

    def session_user_id(request: Request) -> int | None:
        token = request.cookies.get(SESSION_COOKIE)
        return db.find_session_user_id(hash_session_token(token)) if token else None

    def require_user(request: Request) -> int:
        # Atkarība izpildās pirms ķermeņa un parametru pārbaudes, tāpēc bez sesijas vienmēr 401.
        user_id = session_user_id(request)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user_id

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(request: Request, exc: RequestValidationError):
        details = []
        for item in exc.errors():
            loc = [str(part) for part in item.get("loc", ()) if part not in ("body", "query", "path")]
            issue = "REQUIRED" if item.get("type") == "missing" else "INVALID_FORMAT"
            details.append({"field": loc[0] if loc else "body", "issue": issue})
        return validation_error(details)

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHORIZED", 404: "NOT_FOUND"}.get(exc.status_code, "HTTP_ERROR")
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

    @app.get("/organizations")
    def list_organizations(q: str | None = None, mine: bool = False, user_id: int = Depends(require_user)):
        rows = db.search_organizations(q.strip() if q else None, user_id if mine else None)
        return [organization_json(row) for row in rows]

    @app.post("/organizations", status_code=201)
    def create_organization(data: OrganizationInput, user_id: int = Depends(require_user)):
        values, details = check_organization(data, db)
        if details:
            return validation_error(details)
        if values["responsible_user_id"] is None:
            values["responsible_user_id"] = user_id
        try:
            row = db.create_organization(**values)
        except DuplicateRegNumber:
            return reg_number_conflict()
        return JSONResponse(status_code=201, content=organization_json(row))

    @app.get("/organizations/{id}")
    def get_organization(id: int, user_id: int = Depends(require_user)):
        row = db.get_organization(id) if 0 < id <= MAX_ID else None
        return organization_json(row) if row else organization_not_found()

    @app.put("/organizations/{id}")
    def update_organization(id: int, data: OrganizationInput, user_id: int = Depends(require_user)):
        # Neesošai organizācijai 404 pirms datu pārbaudes: nav ko pārbaudīt, ja ieraksta nav.
        if not 0 < id <= MAX_ID or db.get_organization(id) is None:
            return organization_not_found()
        values, details = check_organization(data, db)
        if details:
            return validation_error(details)
        try:
            row = db.update_organization(id, **values)
        except DuplicateRegNumber:
            return reg_number_conflict()
        return organization_json(row) if row else organization_not_found()

    @app.get("/organizacijas", include_in_schema=False)
    def organizations_page(request: Request):
        if session_user_id(request) is None:
            return RedirectResponse("/login", status_code=303)
        return FileResponse(STATIC_DIR / "organizations.html")

    @app.get("/register", include_in_schema=False)
    def register_page():
        return FileResponse(STATIC_DIR / "register.html")

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(STATIC_DIR / "login.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
