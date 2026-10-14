"""CR-4 pieņemšanas kritēriju testi."""

import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

EMAIL = "janis@example.com"
PASSWORD = "drosa-parole-1"


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "auth.db")


@pytest.fixture
def client(db_path):
    return TestClient(create_app(db_path))


def register(client, email=EMAIL, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def detail(response):
    return response.json()["error"]["details"]


# 1
def test_register_valid_returns_user_without_password(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "email": EMAIL, "name": None, "role": "EMPLOYEE"}


# 2
def test_register_duplicate_email(client):
    register(client)
    response = register(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_EXISTS"
    assert detail(response) == [{"field": "email", "issue": "ALREADY_EXISTS"}]


# 3
def test_register_invalid_email(client):
    response = register(client, email="janis@")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert detail(response) == [{"field": "email", "issue": "INVALID_FORMAT"}]


# 4
def test_register_short_password(client):
    response = register(client, password="1234567")
    assert response.status_code == 400
    assert detail(response) == [{"field": "password", "issue": "TOO_SHORT"}]


def test_register_password_of_exactly_eight_characters(client):
    assert register(client, password="12345678").status_code == 201


def test_register_missing_fields(client):
    response = client.post("/auth/register", json={})
    assert response.status_code == 400
    assert detail(response) == [
        {"field": "email", "issue": "REQUIRED"},
        {"field": "password", "issue": "REQUIRED"},
    ]


def test_register_invalid_json(client):
    response = client.post(
        "/auth/register", content="nav json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# 5
def test_register_normalizes_email(client):
    response = register(client, email="  Janis@Example.COM ")
    assert response.status_code == 201
    assert response.json()["email"] == EMAIL
    assert register(client).status_code == 409


# 6
def test_login_valid_sets_session_cookie(client):
    register(client)
    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("session=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_login_accepts_email_in_different_case(client):
    register(client)
    response = client.post("/auth/login", json={"email": "JANIS@example.com", "password": PASSWORD})
    assert response.status_code == 200


# 7
def test_login_wrong_password_and_unknown_email_look_the_same(client):
    register(client)
    wrong = client.post("/auth/login", json={"email": EMAIL, "password": "nepareiza-parole"})
    unknown = client.post("/auth/login", json={"email": "cits@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in wrong.headers


# 8
def test_password_stored_only_as_hash(client, db_path):
    register(client)
    with sqlite3.connect(db_path) as conn:
        (stored,) = conn.execute("SELECT password_hash FROM users").fetchone()
    assert PASSWORD not in stored
    assert stored.startswith("scrypt$")


def test_session_token_stored_only_as_hash(client, db_path):
    register(client)
    token = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD}).cookies["session"]
    with sqlite3.connect(db_path) as conn:
        (stored,) = conn.execute("SELECT token_hash FROM sessions").fetchone()
    assert stored != token


# 9
def test_logs_contain_no_email_or_password(client, caplog):
    caplog.set_level(logging.DEBUG)
    register(client)
    register(client)
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    client.post("/auth/login", json={"email": EMAIL, "password": "nepareiza-parole"})
    assert EMAIL not in caplog.text
    assert PASSWORD not in caplog.text


# 10
@pytest.mark.parametrize("path, endpoint", [("/register", "/auth/register"), ("/login", "/auth/login")])
def test_html_forms(client, path, endpoint):
    response = client.get(path)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'type="password"' in response.text
    assert f'data-endpoint="{endpoint}"' in response.text


@pytest.mark.parametrize("path", ["/static/form.js", "/static/style.css"])
def test_form_assets_are_served(client, path):
    assert client.get(path).status_code == 200


def test_unknown_route_uses_error_schema(client):
    response = client.get("/nav-tada")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
