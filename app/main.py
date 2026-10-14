"""Lietotāji un lomas (CR-4, N3), organizācijas (F1), mijiedarbības (F3), pieprasījumi (F4)
un uzdevumi (F5).

Palaišana: `uvicorn --factory app.main:create_app --reload`, tad atver `/register`, `/login`,
`/organizacijas`, `/pieprasijumi`, `/uzdevumi` vai `/admin`.
Datu bāzes fails: vides mainīgais `AUTH_DB_PATH` (noklusējums `auth.db`).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.db import Database, DuplicateRegNumber, LastAdmin
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
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
INTERACTION_TYPES = ("CALL", "EMAIL", "MEETING")
MAX_SUMMARY_LENGTH = 2000
MAX_NEXT_STEP_LENGTH = 500
REQUEST_STATUSES = ("NEW", "IN_PROGRESS", "ANSWERED")
RequestStatus = Literal["NEW", "IN_PROGRESS", "ANSWERED"]
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 2000
LOCAL_TIMEZONE = ZoneInfo("Europe/Riga")
ROLES = ("EMPLOYEE", "MANAGER", "ADMIN")
STAFF_ROLES = ("EMPLOYEE", "MANAGER")
MAX_USER_NAME_LENGTH = 100


def today() -> date:
    """Šodiena pēc Latvijas laika (F9 datu noteikumi)."""
    return datetime.now(LOCAL_TIMEZONE).date()


def is_valid_id(value: int) -> bool:
    return 0 < value <= MAX_ID


class Credentials(BaseModel):
    # Lauku tipus pārbauda paši, lai kļūdas atbilstu līguma Error shēmai.
    email: Any = None
    password: Any = None


class Registration(Credentials):
    name: Any = None


class RoleChange(BaseModel):
    role: Any = None


@dataclass(frozen=True)
class User:
    """Pieslēgtais lietotājs ar lomu, kas nolasīta šajā pieprasījumā (N3)."""

    id: int
    email: str
    name: str | None
    role: str

    @property
    def sees_all(self) -> bool:
        """Vadītājs redz visu organizāciju datus; darbinieks tikai savu organizāciju."""
        return self.role == "MANAGER"

    def can_see(self, responsible_user_id: int) -> bool:
        return self.sees_all or responsible_user_id == self.id


class OrganizationInput(BaseModel):
    name: Any = None
    regNumber: Any = None
    address: Any = None
    responsibleUserId: Any = None


class InteractionInput(BaseModel):
    occurredOn: Any = None
    type: Any = None
    summary: Any = None
    nextStep: Any = None


class RequestInput(BaseModel):
    organizationId: Any = None
    title: Any = None
    description: Any = None
    dueDate: Any = None
    status: Any = None


class TaskInput(BaseModel):
    title: Any = None
    dueDate: Any = None
    remindOn: Any = None
    done: Any = None
    organizationId: Any = None
    requestId: Any = None
    interactionId: Any = None


def error(status: int, code: str, message: str, details: list[dict] | None = None):
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body})


def validation_error(details: list[dict]) -> JSONResponse:
    return error(400, "VALIDATION_ERROR", "Request validation failed", details)


def forbidden() -> JSONResponse:
    return error(403, "FORBIDDEN", "Not allowed for this role")


def user_json(row) -> dict[str, Any]:
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}


def check_user_name(value: Any) -> tuple[str | None, list[dict]]:
    if value is not None and not isinstance(value, str):
        return None, [{"field": "name", "issue": "INVALID_FORMAT"}]
    name = optional_text(value)
    if name is not None and len(name) > MAX_USER_NAME_LENGTH:
        return None, [{"field": "name", "issue": "TOO_LONG"}]
    return name, []


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
        else:
            # Atbildīgais var būt darbinieks vai vadītājs, ne administrators (N3).
            user = db.get_user(responsible) if is_valid_id(responsible) else None
            if user is None or user["role"] not in STAFF_ROLES:
                details.append({"field": "responsibleUserId", "issue": "NOT_FOUND"})

    values = {
        "name": name.strip() if isinstance(name, str) else name,
        "reg_number": reg_number,
        "address": address,
        "responsible_user_id": responsible,
    }
    return values, details


def parse_date(value: Any) -> date | None:
    """ISO datums `GGGG-MM-DD` vai None, ja formāts vai pats datums nav derīgs."""
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def check_interaction(data: InteractionInput) -> tuple[dict[str, Any], list[dict]]:
    details: list[dict] = []

    occurred_on = data.occurredOn
    if occurred_on is None or occurred_on == "":
        details.append({"field": "occurredOn", "issue": "REQUIRED"})
    elif (parsed := parse_date(occurred_on)) is None:
        details.append({"field": "occurredOn", "issue": "INVALID_FORMAT"})
    elif parsed > today():
        details.append({"field": "occurredOn", "issue": "IN_FUTURE"})

    kind = data.type
    if kind is None or kind == "":
        details.append({"field": "type", "issue": "REQUIRED"})
    elif kind not in INTERACTION_TYPES:
        details.append({"field": "type", "issue": "INVALID_FORMAT"})

    summary = data.summary
    if summary is None or (isinstance(summary, str) and not summary.strip()):
        details.append({"field": "summary", "issue": "REQUIRED"})
    elif not isinstance(summary, str):
        details.append({"field": "summary", "issue": "INVALID_FORMAT"})
    elif len(summary.strip()) > MAX_SUMMARY_LENGTH:
        details.append({"field": "summary", "issue": "TOO_LONG"})

    next_step = data.nextStep
    if next_step is not None and not isinstance(next_step, str):
        details.append({"field": "nextStep", "issue": "INVALID_FORMAT"})
    else:
        next_step = optional_text(next_step)
        if next_step is not None and len(next_step) > MAX_NEXT_STEP_LENGTH:
            details.append({"field": "nextStep", "issue": "TOO_LONG"})

    values = {
        "occurred_on": occurred_on,
        "type": kind,
        "summary": summary.strip() if isinstance(summary, str) else summary,
        "next_step": next_step,
    }
    return values, details


def interaction_json(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "organizationId": row["organization_id"],
        "organizationName": row["organization_name"],
        "authorId": row["author_id"],
        "occurredOn": row["occurred_on"],
        "type": row["type"],
        "summary": row["summary"],
        "nextStep": row["next_step"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def check_request(
    data: RequestInput, find_organization: Callable[[int], Any], creating: bool
) -> tuple[dict[str, Any], list[dict]]:
    """`find_organization` atgriež organizāciju tikai tad, ja lietotājs to redz (N3)."""
    details: list[dict] = []

    if creating:
        org_id = data.organizationId
        if org_id is None:
            details.append({"field": "organizationId", "issue": "REQUIRED"})
        elif not isinstance(org_id, int) or isinstance(org_id, bool):
            details.append({"field": "organizationId", "issue": "INVALID_FORMAT"})
        elif find_organization(org_id) is None:
            details.append({"field": "organizationId", "issue": "NOT_FOUND"})

    title = check_title(data.title, details)

    description = data.description
    if description is not None and not isinstance(description, str):
        details.append({"field": "description", "issue": "INVALID_FORMAT"})
    else:
        description = optional_text(description)
        if description is not None and len(description) > MAX_DESCRIPTION_LENGTH:
            details.append({"field": "description", "issue": "TOO_LONG"})

    due_date = data.dueDate
    if due_date is None or due_date == "":
        details.append({"field": "dueDate", "issue": "REQUIRED"})
    elif parse_date(due_date) is None:
        details.append({"field": "dueDate", "issue": "INVALID_FORMAT"})

    status = data.status
    if status is None or status == "":
        if creating:
            status = "NEW"
        else:
            details.append({"field": "status", "issue": "REQUIRED"})
    elif status not in REQUEST_STATUSES:
        details.append({"field": "status", "issue": "INVALID_FORMAT"})

    values = {
        "title": title,
        "description": description,
        "due_date": due_date,
        "status": status,
    }
    if creating:
        values["organization_id"] = data.organizationId
    return values, details


def request_json(row, on: date) -> dict[str, Any]:
    due = date.fromisoformat(row["due_date"])
    overdue_days = (on - due).days if row["status"] != "ANSWERED" and due < on else 0
    return {
        "id": row["id"],
        "organizationId": row["organization_id"],
        "organizationName": row["organization_name"],
        "title": row["title"],
        "description": row["description"],
        "dueDate": row["due_date"],
        "status": row["status"],
        "overdue": overdue_days > 0,
        "overdueDays": overdue_days,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def check_title(value: Any, details: list[dict]) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        details.append({"field": "title", "issue": "REQUIRED"})
    elif not isinstance(value, str):
        details.append({"field": "title", "issue": "INVALID_FORMAT"})
    elif len(value.strip()) > MAX_TITLE_LENGTH:
        details.append({"field": "title", "issue": "TOO_LONG"})
    else:
        return value.strip()
    return value


def check_task_fields(data: TaskInput, creating: bool) -> tuple[dict[str, Any], list[dict]]:
    """Uzdevuma pamatlauki (F5); saites pārbauda maršruts, jo tām vajag lietotāja tiesības."""
    details: list[dict] = []
    title = check_title(data.title, details)

    due_date = data.dueDate
    due = None
    if due_date is None or due_date == "":
        details.append({"field": "dueDate", "issue": "REQUIRED"})
    elif (due := parse_date(due_date)) is None:
        details.append({"field": "dueDate", "issue": "INVALID_FORMAT"})

    remind_on = data.remindOn
    if remind_on == "":
        remind_on = None
    if remind_on is not None:
        if (remind := parse_date(remind_on)) is None:
            details.append({"field": "remindOn", "issue": "INVALID_FORMAT"})
        elif due is not None and remind > due:
            details.append({"field": "remindOn", "issue": "AFTER_DUE_DATE"})

    done = data.done
    if done is None:
        if creating:
            done = False
        else:
            details.append({"field": "done", "issue": "REQUIRED"})
    elif not isinstance(done, bool):
        details.append({"field": "done", "issue": "INVALID_FORMAT"})

    values = {"title": title, "due_date": due_date, "remind_on": remind_on, "done": done}
    return values, details


def task_json(row, on: date) -> dict[str, Any]:
    due = date.fromisoformat(row["due_date"])
    done = bool(row["done"])
    overdue_days = (on - due).days if not done and due < on else 0
    remind = row["remind_on"]
    return {
        "id": row["id"],
        "ownerId": row["owner_id"],
        "title": row["title"],
        "dueDate": row["due_date"],
        "remindOn": remind,
        "done": done,
        "completedAt": row["completed_at"],
        "organizationId": row["organization_id"],
        "organizationName": row["organization_name"],
        "requestId": row["request_id"],
        "requestTitle": row["request_title"],
        "interactionId": row["interaction_id"],
        "overdue": overdue_days > 0,
        "overdueDays": overdue_days,
        "dueToday": not done and due == on,
        "reminderDue": not done and remind is not None and date.fromisoformat(remind) <= on,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def task_not_found() -> JSONResponse:
    return error(404, "NOT_FOUND", "Task not found")


def request_not_found() -> JSONResponse:
    return error(404, "NOT_FOUND", "Request not found")


def interaction_not_found() -> JSONResponse:
    return error(404, "NOT_FOUND", "Interaction not found")


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
    app = FastAPI(title="Ezermalas CRM · lietotāji, lomas, organizācijas, mijiedarbības, pieprasījumi")

    def session_user(request: Request) -> User | None:
        token = request.cookies.get(SESSION_COOKIE)
        row = db.find_session_user(hash_session_token(token)) if token else None
        return User(row["id"], row["email"], row["name"], row["role"]) if row else None

    def require_user(request: Request) -> User:
        # Atkarība izpildās pirms ķermeņa un parametru pārbaudes, tāpēc bez sesijas vienmēr 401.
        user = session_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    def require_roles(*roles: str):
        def dependency(user: User = Depends(require_user)) -> User:
            if user.role not in roles:
                raise HTTPException(status_code=403, detail="Not allowed for this role")
            return user

        return dependency

    # Darba dati (organizācijas, mijiedarbības, pieprasījumi) nav pieejami administratoram.
    require_staff = require_roles(*STAFF_ROLES)

    def visible_organization(user: User, org_id: int):
        row = db.get_organization(org_id) if is_valid_id(org_id) else None
        return row if row and user.can_see(row["responsible_user_id"]) else None

    def visible_interaction(user: User, interaction_id: int):
        row = db.get_interaction(interaction_id) if is_valid_id(interaction_id) else None
        return row if row and user.can_see(row["organization_responsible_id"]) else None

    def visible_request(user: User, request_id: int):
        row = db.get_request(request_id) if is_valid_id(request_id) else None
        return row if row and user.can_see(row["organization_responsible_id"]) else None

    def visible_task(user: User, task_id: int):
        row = db.get_task(task_id) if is_valid_id(task_id) else None
        return row if row and (user.sees_all or row["owner_id"] == user.id) else None

    def check_task_links(user: User, data: TaskInput) -> tuple[dict[str, Any], list[dict]]:
        """Saites uz organizāciju, pieprasījumu, mijiedarbību; tām jābūt lietotājam redzamām."""
        details: list[dict] = []
        found: dict[str, Any] = {}
        lookups = {
            "organizationId": visible_organization,
            "requestId": visible_request,
            "interactionId": visible_interaction,
        }
        for field, lookup in lookups.items():
            value = getattr(data, field)
            if value is None:
                continue
            if not isinstance(value, int) or isinstance(value, bool):
                details.append({"field": field, "issue": "INVALID_FORMAT"})
            elif (row := lookup(user, value)) is None:
                details.append({"field": field, "issue": "NOT_FOUND"})
            else:
                found[field] = row

        org_id = found["organizationId"]["id"] if "organizationId" in found else None
        for field in ("requestId", "interactionId"):
            if field in found:
                linked_org = found[field]["organization_id"]
                if org_id is not None and org_id != linked_org:
                    details.append({"field": "organizationId", "issue": "MISMATCH"})
                    break
                org_id = linked_org

        links = {
            "organization_id": org_id,
            "request_id": data.requestId if "requestId" in found else None,
            "interaction_id": data.interactionId if "interactionId" in found else None,
        }
        return links, details

    def own_scope(user: User, mine: bool) -> int | None:
        """Atbildīgā filtrs sarakstiem: darbiniekam vienmēr savs, vadītājam pēc `mine`."""
        return user.id if mine or not user.sees_all else None

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
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def on_unexpected_error(request: Request, exc: Exception):
        return error(500, "INTERNAL_ERROR", "Unexpected server error")

    # --- Lietotāji un lomas (CR-4, N3) ---

    @app.post("/auth/register", status_code=201)
    def register(data: Registration):
        email, password, details = check_credentials(data, check_length=True)
        name, name_details = check_user_name(data.name)
        details += name_details
        if details:
            return validation_error(details)

        user = db.create_user(email, hash_password(password), name)
        if user is None:
            return error(
                409,
                "ALREADY_EXISTS",
                "User already exists",
                [{"field": "email", "issue": "ALREADY_EXISTS"}],
            )
        return JSONResponse(status_code=201, content=user_json(user))

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
        result = JSONResponse(content=user_json(user))
        result.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
        return result

    @app.post("/auth/logout", status_code=204)
    def logout(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            db.delete_session(hash_session_token(token))
        result = Response(status_code=204)
        result.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax")
        return result

    @app.get("/auth/me")
    def current_user(user: User = Depends(require_user)):
        return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}

    @app.get("/users")
    def list_users(user: User = Depends(require_roles("MANAGER", "ADMIN"))):
        return [user_json(row) for row in db.list_users()]

    @app.put("/users/{id}/role")
    def change_role(id: int, data: RoleChange, user: User = Depends(require_roles("ADMIN"))):
        if data.role is None or data.role == "":
            return validation_error([{"field": "role", "issue": "REQUIRED"}])
        if data.role not in ROLES:
            return validation_error([{"field": "role", "issue": "INVALID_FORMAT"}])
        try:
            row = db.set_role(id, data.role) if is_valid_id(id) else None
        except LastAdmin:
            return error(409, "LAST_ADMIN", "At least one administrator is required")
        if row is None:
            return error(404, "NOT_FOUND", "User not found")
        return user_json(row)

    # --- Organizācijas (F1) ---

    @app.get("/organizations")
    def list_organizations(q: str | None = None, mine: bool = False, user: User = Depends(require_staff)):
        rows = db.search_organizations(q.strip() if q else None, own_scope(user, mine))
        return [organization_json(row) for row in rows]

    @app.post("/organizations", status_code=201)
    def create_organization(data: OrganizationInput, user: User = Depends(require_staff)):
        values, details = check_organization(data, db)
        if details:
            return validation_error(details)
        responsible = values["responsible_user_id"]
        if responsible is None:
            values["responsible_user_id"] = user.id
        elif responsible != user.id and not user.sees_all:
            return forbidden()
        try:
            row = db.create_organization(**values)
        except DuplicateRegNumber:
            return reg_number_conflict()
        return JSONResponse(status_code=201, content=organization_json(row))

    @app.get("/organizations/{id}")
    def get_organization(id: int, user: User = Depends(require_staff)):
        row = visible_organization(user, id)
        return organization_json(row) if row else organization_not_found()

    @app.put("/organizations/{id}")
    def update_organization(id: int, data: OrganizationInput, user: User = Depends(require_staff)):
        # Neesošai organizācijai 404 pirms datu pārbaudes: nav ko pārbaudīt, ja ieraksta nav.
        existing = visible_organization(user, id)
        if existing is None:
            return organization_not_found()
        values, details = check_organization(data, db)
        if details:
            return validation_error(details)
        responsible = values["responsible_user_id"]
        if responsible not in (None, existing["responsible_user_id"]) and not user.sees_all:
            return forbidden()
        try:
            row = db.update_organization(id, **values)
        except DuplicateRegNumber:
            return reg_number_conflict()
        return organization_json(row) if row else organization_not_found()

    # --- Mijiedarbības (F3) ---

    @app.get("/organizations/{id}/interactions")
    def list_organization_interactions(id: int, user: User = Depends(require_staff)):
        if visible_organization(user, id) is None:
            return organization_not_found()
        return [interaction_json(row) for row in db.organization_interactions(id)]

    @app.post("/organizations/{id}/interactions", status_code=201)
    def create_interaction(id: int, data: InteractionInput, user: User = Depends(require_staff)):
        org = visible_organization(user, id)
        if org is None:
            return organization_not_found()
        # Reģistrē tikai organizācijas atbildīgais; vadītājs citām tikai skatās (N3).
        if org["responsible_user_id"] != user.id:
            return forbidden()
        values, details = check_interaction(data)
        if details:
            return validation_error(details)
        row = db.create_interaction(organization_id=id, author_id=user.id, **values)
        return JSONResponse(status_code=201, content=interaction_json(row))

    @app.get("/interactions")
    def list_interactions(
        mine: bool = False,
        limit: int = Query(50, ge=1, le=100),
        user: User = Depends(require_staff),
    ):
        rows = db.latest_interactions(
            user.id if mine else None, limit, None if user.sees_all else user.id
        )
        return [interaction_json(row) for row in rows]

    @app.get("/interactions/{id}")
    def get_interaction(id: int, user: User = Depends(require_staff)):
        row = visible_interaction(user, id)
        return interaction_json(row) if row else interaction_not_found()

    @app.put("/interactions/{id}")
    def update_interaction(id: int, data: InteractionInput, user: User = Depends(require_staff)):
        existing = visible_interaction(user, id)
        if existing is None:
            return interaction_not_found()
        if existing["author_id"] != user.id:
            return forbidden()
        values, details = check_interaction(data)
        if details:
            return validation_error(details)
        return interaction_json(db.update_interaction(id, **values))

    # --- Pieprasījumi (F4) ---

    @app.get("/requests")
    def list_requests(
        status: list[RequestStatus] | None = Query(None),
        overdue: bool | None = None,
        dueWithinDays: int | None = Query(None, ge=0, le=365),
        mine: bool = False,
        organizationId: int | None = None,
        user: User = Depends(require_staff),
    ):
        if organizationId is not None and not is_valid_id(organizationId):
            return []
        on = today()
        rows = db.search_requests(
            today=on.isoformat(),
            statuses=status,
            overdue=overdue,
            due_until=(on + timedelta(days=dueWithinDays)).isoformat()
            if dueWithinDays is not None
            else None,
            responsible_user_id=own_scope(user, mine),
            organization_id=organizationId,
        )
        return [request_json(row, on) for row in rows]

    @app.post("/requests", status_code=201)
    def create_request(data: RequestInput, user: User = Depends(require_staff)):
        values, details = check_request(
            data, lambda org_id: visible_organization(user, org_id), creating=True
        )
        if details:
            return validation_error(details)
        row = db.create_request(**values)
        return JSONResponse(status_code=201, content=request_json(row, today()))

    @app.get("/requests/{id}")
    def get_request(id: int, user: User = Depends(require_staff)):
        row = visible_request(user, id)
        return request_json(row, today()) if row else request_not_found()

    @app.put("/requests/{id}")
    def update_request(id: int, data: RequestInput, user: User = Depends(require_staff)):
        if visible_request(user, id) is None:
            return request_not_found()
        values, details = check_request(data, lambda org_id: None, creating=False)
        if details:
            return validation_error(details)
        return request_json(db.update_request(id, **values), today())

    # --- Uzdevumi (F5) ---

    @app.get("/tasks")
    def list_tasks(
        team: bool = False,
        done: bool | None = None,
        dueWithinDays: int | None = Query(None, ge=0, le=365),
        remindersDue: bool | None = None,
        organizationId: int | None = None,
        interactionId: int | None = None,
        user: User = Depends(require_staff),
    ):
        if team and not user.sees_all:
            return forbidden()
        if any(v is not None and not is_valid_id(v) for v in (organizationId, interactionId)):
            return []
        on = today()
        rows = db.search_tasks(
            today=on.isoformat(),
            owner_id=None if team else user.id,
            done=done,
            due_until=(on + timedelta(days=dueWithinDays)).isoformat()
            if dueWithinDays is not None
            else None,
            reminders_due=remindersDue,
            organization_id=organizationId,
            interaction_id=interactionId,
        )
        return [task_json(row, on) for row in rows]

    @app.post("/tasks", status_code=201)
    def create_task(data: TaskInput, user: User = Depends(require_staff)):
        values, details = check_task_fields(data, creating=True)
        links, link_details = check_task_links(user, data)
        details += link_details
        if details:
            return validation_error(details)
        row = db.create_task(owner_id=user.id, **values, **links)
        return JSONResponse(status_code=201, content=task_json(row, today()))

    @app.get("/tasks/{id}")
    def get_task(id: int, user: User = Depends(require_staff)):
        row = visible_task(user, id)
        return task_json(row, today()) if row else task_not_found()

    @app.put("/tasks/{id}")
    def update_task(id: int, data: TaskInput, user: User = Depends(require_staff)):
        existing = visible_task(user, id)
        if existing is None:
            return task_not_found()
        if existing["owner_id"] != user.id:
            return forbidden()
        values, details = check_task_fields(data, creating=False)
        if details:
            return validation_error(details)
        return task_json(db.update_task(id, **values), today())

    @app.post("/tasks/{id}/complete")
    def complete_task(id: int, user: User = Depends(require_staff)):
        existing = visible_task(user, id)
        if existing is None:
            return task_not_found()
        if existing["owner_id"] != user.id:
            return forbidden()
        return task_json(db.complete_task(id), today())

    # --- Lapas ---

    def page(request: Request, filename: str, roles: tuple[str, ...]):
        user = session_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if user.role not in roles:
            home = "/admin" if user.role == "ADMIN" else "/organizacijas"
            return RedirectResponse(home, status_code=303)
        return FileResponse(STATIC_DIR / filename)

    @app.get("/pieprasijumi", include_in_schema=False)
    def requests_page(request: Request):
        return page(request, "requests.html", STAFF_ROLES)

    @app.get("/organizacijas/{org_id:int}", include_in_schema=False)
    def organization_page(request: Request, org_id: int):
        return page(request, "organization.html", STAFF_ROLES)

    @app.get("/organizacijas", include_in_schema=False)
    def organizations_page(request: Request):
        return page(request, "organizations.html", STAFF_ROLES)

    @app.get("/uzdevumi", include_in_schema=False)
    def tasks_page(request: Request):
        return page(request, "tasks.html", STAFF_ROLES)

    @app.get("/admin", include_in_schema=False)
    def admin_page(request: Request):
        return page(request, "admin.html", ("ADMIN",))

    @app.get("/register", include_in_schema=False)
    def register_page():
        return FileResponse(STATIC_DIR / "register.html")

    @app.get("/login", include_in_schema=False)
    def login_page():
        return FileResponse(STATIC_DIR / "login.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
