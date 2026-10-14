"""N3 pieņemšanas kritēriju testi."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import cli
from app.db import Database
from app.main import create_app

PASSWORD = "drosa-parole-1"


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "auth.db"))


def logged_in(app, email, set_role=None, role=None, name=None):
    client = TestClient(app)
    body = {"email": email, "password": PASSWORD}
    if name is not None:
        body["name"] = name
    client.user_id = client.post("/auth/register", json=body).json()["id"]
    if role:
        set_role(client.user_id, role)
    client.post("/auth/login", json={"email": email, "password": PASSWORD})
    return client


@pytest.fixture
def employee(app):
    return logged_in(app, "janis@example.com")


@pytest.fixture
def colleague(app):
    return logged_in(app, "anna@example.com")


@pytest.fixture
def manager(app, set_role):
    return logged_in(app, "vaditajs@example.com", set_role, "MANAGER")


@pytest.fixture
def admin(app, set_role):
    return logged_in(app, "admin@example.com", set_role, "ADMIN")


def org(client, name, **fields):
    response = client.post("/organizations", json={"name": name, **fields})
    assert response.status_code == 201, response.json()
    return response.json()


def interaction(client, org_id, summary="Zvans."):
    body = {"occurredOn": "2026-10-01", "type": "CALL", "summary": summary}
    response = client.post(f"/organizations/{org_id}/interactions", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def request(client, org_id, title="Pieprasījums"):
    body = {"organizationId": org_id, "title": title, "dueDate": "2026-11-13"}
    response = client.post("/requests", json=body)
    assert response.status_code == 201, response.json()
    return response.json()


def code(response):
    return response.json()["error"]["code"]


def names(response):
    assert response.status_code == 200
    return [item["name"] for item in response.json()]


# N3-1
def test_new_user_is_employee_with_name(app):
    response = TestClient(app).post(
        "/auth/register",
        json={"email": "janis@example.com", "password": PASSWORD, "name": "  Jānis Bērziņš "},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "EMPLOYEE"
    assert response.json()["name"] == "Jānis Bērziņš"


def test_login_returns_role(app, set_role):
    client = logged_in(app, "admin@example.com", set_role, "ADMIN")
    response = client.post("/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    assert response.json()["role"] == "ADMIN"


@pytest.mark.parametrize("name, issue", [("A" * 101, "TOO_LONG"), (5, "INVALID_FORMAT")])
def test_name_validation(app, name, issue):
    response = TestClient(app).post(
        "/auth/register", json={"email": "janis@example.com", "password": PASSWORD, "name": name}
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [{"field": "name", "issue": issue}]


# N3-2
def test_employee_sees_only_own_organizations(employee, colleague):
    org(employee, "Jāņa")
    org(colleague, "Annas")
    assert names(employee.get("/organizations")) == ["Jāņa"]
    assert names(employee.get("/organizations", params={"q": "Annas"})) == []


def test_employee_lists_only_own_interactions_and_requests(employee, colleague):
    annas = org(colleague, "Annas")
    interaction(colleague, annas["id"])
    request(colleague, annas["id"])
    assert employee.get("/interactions").json() == []
    assert employee.get("/requests").json() == []
    assert employee.get("/requests", params={"organizationId": annas["id"]}).json() == []


# N3-3
def test_foreign_records_look_missing(employee, colleague):
    annas = org(colleague, "Annas")
    item = interaction(colleague, annas["id"])
    req = request(colleague, annas["id"])
    for response in [
        employee.get(f"/organizations/{annas['id']}"),
        employee.put(f"/organizations/{annas['id']}", json={"name": "Uzlauzts"}),
        employee.get(f"/organizations/{annas['id']}/interactions"),
        employee.post(f"/organizations/{annas['id']}/interactions", json={}),
        employee.get(f"/interactions/{item['id']}"),
        employee.put(f"/interactions/{item['id']}", json={}),
        employee.get(f"/requests/{req['id']}"),
        employee.put(f"/requests/{req['id']}", json={}),
    ]:
        assert response.status_code == 404
        assert code(response) == "NOT_FOUND"
    assert colleague.get(f"/organizations/{annas['id']}").json()["name"] == "Annas"


# N3-4
def test_employee_cannot_assign_someone_else(employee, colleague):
    response = employee.post("/organizations", json={"name": "X", "responsibleUserId": colleague.user_id})
    assert response.status_code == 403
    assert code(response) == "FORBIDDEN"
    assert employee.get("/organizations").json() == []


def test_employee_cannot_change_responsible(employee, colleague):
    mine = org(employee, "Jāņa")
    response = employee.put(
        f"/organizations/{mine['id']}", json={"name": "Jāņa", "responsibleUserId": colleague.user_id}
    )
    assert response.status_code == 403
    assert employee.get(f"/organizations/{mine['id']}").json() == mine


def test_employee_may_name_himself_as_responsible(employee):
    mine = org(employee, "Jāņa", responsibleUserId=employee.user_id)
    response = employee.put(
        f"/organizations/{mine['id']}", json={"name": "Jauns", "responsibleUserId": employee.user_id}
    )
    assert response.status_code == 200


# N3-5
def test_manager_sees_everything(manager, employee, colleague):
    janis = org(employee, "Jāņa")
    annas = org(colleague, "Annas")
    interaction(employee, janis["id"])
    interaction(colleague, annas["id"])
    request(employee, janis["id"])
    request(colleague, annas["id"])
    assert names(manager.get("/organizations")) == ["Annas", "Jāņa"]
    assert len(manager.get("/interactions").json()) == 2
    assert len(manager.get("/requests").json()) == 2
    assert manager.get(f"/organizations/{annas['id']}/interactions").status_code == 200


def test_manager_manages_all_requests(manager, colleague):
    annas = org(colleague, "Annas")
    req = request(manager, annas["id"], "Vadītāja reģistrēts")
    body = {"title": "Labots", "dueDate": "2026-11-13", "status": "ANSWERED"}
    assert manager.put(f"/requests/{req['id']}", json=body).status_code == 200


# N3-6
def test_manager_changes_responsible(manager, employee, colleague):
    janis = org(employee, "Jāņa")
    response = manager.put(
        f"/organizations/{janis['id']}", json={"name": "Jāņa", "responsibleUserId": colleague.user_id}
    )
    assert response.status_code == 200
    assert response.json()["responsibleUserId"] == colleague.user_id
    assert employee.get(f"/organizations/{janis['id']}").status_code == 404
    assert colleague.get(f"/organizations/{janis['id']}").status_code == 200


def test_admin_cannot_be_responsible(manager, admin):
    response = manager.post("/organizations", json={"name": "X", "responsibleUserId": admin.user_id})
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [{"field": "responsibleUserId", "issue": "NOT_FOUND"}]


# N3-7
def test_manager_cannot_register_interaction_for_foreign_organization(manager, colleague):
    annas = org(colleague, "Annas")
    body = {"occurredOn": "2026-10-01", "type": "CALL", "summary": "Zvans."}
    response = manager.post(f"/organizations/{annas['id']}/interactions", json=body)
    assert response.status_code == 403
    own = org(manager, "Vadītāja")
    assert manager.post(f"/organizations/{own['id']}/interactions", json=body).status_code == 201


def test_author_loses_access_when_organization_reassigned(manager, employee, colleague):
    janis = org(employee, "Jāņa")
    item = interaction(employee, janis["id"])
    manager.put(f"/organizations/{janis['id']}", json={"name": "Jāņa", "responsibleUserId": colleague.user_id})
    assert employee.get(f"/interactions/{item['id']}").status_code == 404


# N3-8
def test_employee_cannot_file_request_for_foreign_organization(employee, colleague):
    annas = org(colleague, "Annas")
    response = employee.post(
        "/requests", json={"organizationId": annas["id"], "title": "X", "dueDate": "2026-11-13"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [{"field": "organizationId", "issue": "NOT_FOUND"}]


# N3-9
@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/organizations"),
        ("post", "/organizations"),
        ("get", "/organizations/1"),
        ("put", "/organizations/1"),
        ("get", "/organizations/1/interactions"),
        ("post", "/organizations/1/interactions"),
        ("get", "/interactions"),
        ("get", "/interactions/1"),
        ("put", "/interactions/1"),
        ("get", "/requests"),
        ("post", "/requests"),
        ("get", "/requests/1"),
        ("put", "/requests/1"),
    ],
)
def test_admin_has_no_access_to_work_data(admin, method, path):
    kwargs = {"json": {}} if method in ("post", "put") else {}
    response = getattr(admin, method)(path, **kwargs)
    assert response.status_code == 403
    assert response.json()["error"] == {"code": "FORBIDDEN", "message": "Not allowed for this role"}


# N3-10
def test_admin_changes_role_effective_immediately(admin, employee):
    assert employee.get("/users").status_code == 403
    response = admin.put(f"/users/{employee.user_id}/role", json={"role": "MANAGER"})
    assert response.status_code == 200
    assert response.json() == {
        "id": employee.user_id,
        "email": "janis@example.com",
        "name": None,
        "role": "MANAGER",
    }
    assert employee.get("/auth/me").json()["role"] == "MANAGER"
    assert employee.get("/users").status_code == 200


def test_users_list(admin, manager, employee):
    users = admin.get("/users").json()
    assert [u["email"] for u in users] == ["admin@example.com", "janis@example.com", "vaditajs@example.com"]
    assert set(users[0]) == {"id", "email", "name", "role"}
    assert manager.get("/users").json() == users


# N3-11
def test_only_admin_changes_roles(manager, employee):
    for client in (manager, employee):
        response = client.put(f"/users/{employee.user_id}/role", json={"role": "ADMIN"})
        assert response.status_code == 403
        assert code(response) == "FORBIDDEN"
    assert employee.get("/auth/me").json()["role"] == "EMPLOYEE"


# N3-12
def test_last_admin_cannot_be_demoted(app, admin, set_role):
    response = admin.put(f"/users/{admin.user_id}/role", json={"role": "EMPLOYEE"})
    assert response.status_code == 409
    assert code(response) == "LAST_ADMIN"
    second = logged_in(app, "otrs@example.com", set_role, "ADMIN")
    assert admin.put(f"/users/{second.user_id}/role", json={"role": "MANAGER"}).status_code == 200
    second_admin = logged_in(app, "tresais@example.com", set_role, "ADMIN")
    assert admin.put(f"/users/{admin.user_id}/role", json={"role": "EMPLOYEE"}).status_code == 200
    assert second_admin.get("/auth/me").json()["role"] == "ADMIN"


# N3-13
@pytest.mark.parametrize("body, issue", [({}, "REQUIRED"), ({"role": "BOSS"}, "INVALID_FORMAT"), ({"role": 1}, "INVALID_FORMAT")])
def test_invalid_role(admin, employee, body, issue):
    response = admin.put(f"/users/{employee.user_id}/role", json=body)
    assert response.status_code == 400
    assert response.json()["error"]["details"] == [{"field": "role", "issue": issue}]


@pytest.mark.parametrize("user_id", [999, 0, 2**70])
def test_unknown_user(admin, user_id):
    response = admin.put(f"/users/{user_id}/role", json={"role": "MANAGER"})
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "NOT_FOUND", "message": "User not found"}


# N3-14
def test_logout(employee):
    cookie = employee.cookies["session"]
    response = employee.post("/auth/logout")
    assert response.status_code == 204
    assert 'session=""' in response.headers["set-cookie"] or "Max-Age=0" in response.headers["set-cookie"]
    stolen = TestClient(employee.app, cookies={"session": cookie})
    assert stolen.get("/auth/me").status_code == 401


def test_logout_without_session(app):
    assert TestClient(app).post("/auth/logout").status_code == 204


# N3-15
def test_cli_set_role(monkeypatch, tmp_path, employee, capsys):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.db"))
    assert cli.main(["set-role", " Janis@Example.com ", "ADMIN"]) == 0
    assert employee.get("/auth/me").json()["role"] == "ADMIN"
    assert cli.main(["set-role", "nav@example.com", "ADMIN"]) == 1
    assert "nav atrasts" in capsys.readouterr().err


def test_cli_rejects_unknown_role(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.db"))
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["set-role", "janis@example.com", "BOSS"])
    assert exit_info.value.code != 0


# N3-16
@pytest.mark.parametrize(
    "who, path, target",
    [
        ("admin", "/organizacijas", "/admin"),
        ("admin", "/pieprasijumi", "/admin"),
        ("admin", "/organizacijas/1", "/admin"),
        ("employee", "/admin", "/organizacijas"),
        ("manager", "/admin", "/organizacijas"),
    ],
)
def test_pages_redirect_by_role(request, who, path, target):
    client = request.getfixturevalue(who)
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == target


def test_admin_page(admin):
    response = admin.get("/admin")
    assert response.status_code == 200
    assert "<caption>Lietotāji</caption>" in response.text
    assert admin.get("/static/admin.js").status_code == 200


def test_admin_page_requires_login(app):
    response = TestClient(app).get("/admin", follow_redirects=False)
    assert response.headers["location"] == "/login"


@pytest.mark.parametrize("page", ["/organizacijas", "/pieprasijumi"])
def test_pages_have_header_with_logout(employee, page):
    html = employee.get(page).text
    assert '<header class="site-header">' in html
    assert 'id="logout"' in html
    assert "/static/nav.js" in html


def test_register_form_has_name_field(app):
    assert 'id="name"' in TestClient(app).get("/register").text


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "vecs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,"
            " password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z')"
        )
        conn.execute("INSERT INTO users (email, password_hash) VALUES ('vecs@example.com', 'x')")
    db = Database(str(path))
    user = db.get_user(1)
    assert (user["name"], user["role"]) == (None, "EMPLOYEE")
