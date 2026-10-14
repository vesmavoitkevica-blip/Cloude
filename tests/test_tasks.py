"""F5 pieņemšanas kritēriju testi."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import create_app

PASSWORD = "drosa-parole-1"
TODAY = date(2026, 10, 14)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(main, "today", lambda: TODAY)


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "auth.db"))


def logged_in(app, email, set_role=None, role=None):
    client = TestClient(app)
    client.user_id = client.post("/auth/register", json={"email": email, "password": PASSWORD}).json()["id"]
    if role:
        set_role(client.user_id, role)
    client.post("/auth/login", json={"email": email, "password": PASSWORD})
    return client


@pytest.fixture
def client(app):
    return logged_in(app, "janis@example.com")


@pytest.fixture
def colleague(app):
    return logged_in(app, "anna@example.com")


@pytest.fixture
def manager(app, set_role):
    return logged_in(app, "vaditajs@example.com", set_role, "MANAGER")


@pytest.fixture
def org(client):
    return client.post("/organizations", json={"name": "SIA Ezermalas Ūdens"}).json()


def add(client, **fields):
    response = client.post("/tasks", json={"title": "Nosūtīt projektu", "dueDate": "2026-10-20", **fields})
    return response


def detail(response):
    return response.json()["error"]["details"]


def titles(response):
    assert response.status_code == 200
    return [task["title"] for task in response.json()]


# F5-1
def test_create_task(client):
    response = add(client, title="  Nosūtīt projektu ")
    assert response.status_code == 201
    body = response.json()
    assert body["ownerId"] == client.user_id
    assert body["title"] == "Nosūtīt projektu"
    assert body["dueDate"] == "2026-10-20"
    assert body["done"] is False
    assert body["completedAt"] is None
    for key in ("remindOn", "organizationId", "organizationName", "requestId", "requestTitle", "interactionId"):
        assert body[key] is None
    assert (body["overdue"], body["dueToday"], body["reminderDue"]) == (False, False, False)


def test_create_already_done(client):
    body = add(client, done=True).json()
    assert body["done"] is True
    assert body["completedAt"] is not None


# F5-2
def test_required_fields(client):
    response = client.post("/tasks", json={})
    assert response.status_code == 400
    assert detail(response) == [
        {"field": "title", "issue": "REQUIRED"},
        {"field": "dueDate", "issue": "REQUIRED"},
    ]


# F5-3
def test_invalid_dates(client):
    response = add(client, dueDate="2026-02-30", remindOn="16.10.2026")
    assert detail(response) == [
        {"field": "dueDate", "issue": "INVALID_FORMAT"},
        {"field": "remindOn", "issue": "INVALID_FORMAT"},
    ]


def test_reminder_after_due_date(client):
    response = add(client, dueDate="2026-10-20", remindOn="2026-10-21")
    assert detail(response) == [{"field": "remindOn", "issue": "AFTER_DUE_DATE"}]
    assert add(client, dueDate="2026-10-20", remindOn="2026-10-20").status_code == 201


@pytest.mark.parametrize("field, value", [("title", "A" * 201), ("done", "jā"), ("organizationId", "1")])
def test_field_formats(client, field, value):
    response = add(client, **{field: value})
    assert response.status_code == 400
    assert detail(response)[0]["field"] == field


# F5-4
def test_link_to_request_fills_organization(client, org):
    req = client.post(
        "/requests", json={"organizationId": org["id"], "title": "Mērījumi", "dueDate": "2026-11-13"}
    ).json()
    body = add(client, requestId=req["id"]).json()
    assert (body["requestId"], body["requestTitle"]) == (req["id"], "Mērījumi")
    assert (body["organizationId"], body["organizationName"]) == (org["id"], "SIA Ezermalas Ūdens")


def test_link_to_interaction_next_step(client, org):
    item = client.post(
        f"/organizations/{org['id']}/interactions",
        json={"occurredOn": "2026-10-01", "type": "CALL", "summary": "Zvans.", "nextStep": "Nosūtīt projektu"},
    ).json()
    body = add(client, interactionId=item["id"], organizationId=org["id"]).json()
    assert body["interactionId"] == item["id"]
    assert body["organizationId"] == org["id"]
    assert titles(client.get("/tasks", params={"interactionId": item["id"]})) == ["Nosūtīt projektu"]


# F5-5
def test_organization_mismatch(client, org):
    other = client.post("/organizations", json={"name": "Cita"}).json()
    req = client.post(
        "/requests", json={"organizationId": org["id"], "title": "Mērījumi", "dueDate": "2026-11-13"}
    ).json()
    response = add(client, requestId=req["id"], organizationId=other["id"])
    assert response.status_code == 400
    assert detail(response) == [{"field": "organizationId", "issue": "MISMATCH"}]


# F5-6
@pytest.mark.parametrize("field", ["organizationId", "requestId", "interactionId"])
def test_unknown_links(client, field):
    for value in (999, 2**70):
        response = add(client, **{field: value})
        assert response.status_code == 400
        assert detail(response) == [{"field": field, "issue": "NOT_FOUND"}]


def test_foreign_links_look_missing(client, colleague):
    annas = colleague.post("/organizations", json={"name": "Annas"}).json()
    req = colleague.post(
        "/requests", json={"organizationId": annas["id"], "title": "X", "dueDate": "2026-11-13"}
    ).json()
    assert detail(add(client, organizationId=annas["id"])) == [{"field": "organizationId", "issue": "NOT_FOUND"}]
    assert detail(add(client, requestId=req["id"])) == [{"field": "requestId", "issue": "NOT_FOUND"}]


# F5-7
def test_overdue_and_due_today(client):
    late = add(client, title="vakar", dueDate="2026-10-13").json()
    now = add(client, title="šodien", dueDate="2026-10-14").json()
    assert (late["overdue"], late["overdueDays"], late["dueToday"]) == (True, 1, False)
    assert (now["overdue"], now["overdueDays"], now["dueToday"]) == (False, 0, True)
    done = add(client, title="izpildīts", dueDate="2026-10-13", done=True).json()
    assert (done["overdue"], done["dueToday"]) == (False, False)


# F5-8
def test_reminder_due(client):
    task = add(client, dueDate="2026-10-20", remindOn="2026-10-14").json()
    later = add(client, title="vēlāk", dueDate="2026-10-20", remindOn="2026-10-15").json()
    assert task["reminderDue"] is True
    assert later["reminderDue"] is False
    assert titles(client.get("/tasks", params={"remindersDue": "true"})) == ["Nosūtīt projektu"]
    client.post(f"/tasks/{task['id']}/complete")
    assert client.get(f"/tasks/{task['id']}").json()["reminderDue"] is False
    assert client.get("/tasks", params={"remindersDue": "true"}).json() == []
    assert len(client.get("/tasks", params={"remindersDue": "false"}).json()) == 2


# F5-9
def test_complete(client):
    task = add(client).json()
    response = client.post(f"/tasks/{task['id']}/complete")
    assert response.status_code == 200
    body = response.json()
    assert body["done"] is True
    assert body["completedAt"] is not None
    assert client.get("/tasks", params={"done": "false"}).json() == []
    again = client.post(f"/tasks/{task['id']}/complete").json()
    assert again["completedAt"] == body["completedAt"]


# F5-10
def test_reopen_clears_completed_at(client):
    task = add(client, done=True).json()
    body = {"title": "Atkal", "dueDate": "2026-10-20", "remindOn": None, "done": False}
    response = client.put(f"/tasks/{task['id']}", json=body)
    assert response.status_code == 200
    assert (response.json()["done"], response.json()["completedAt"]) == (False, None)


def test_update_keeps_completed_at_and_links(client, org):
    task = add(client, organizationId=org["id"], done=True).json()
    body = {"title": "Pārdēvēts", "dueDate": "2026-10-21", "done": True, "organizationId": None}
    updated = client.put(f"/tasks/{task['id']}", json=body).json()
    assert updated["completedAt"] == task["completedAt"]
    assert updated["organizationId"] == org["id"]
    assert (updated["title"], updated["dueDate"]) == ("Pārdēvēts", "2026-10-21")


def test_update_requires_done(client):
    task = add(client).json()
    response = client.put(f"/tasks/{task['id']}", json={"title": "X", "dueDate": "2026-10-20"})
    assert detail(response) == [{"field": "done", "issue": "REQUIRED"}]


# F5-11
def test_today_and_overdue_open_tasks(client):
    add(client, title="kavēts", dueDate="2026-10-10")
    add(client, title="šodien", dueDate="2026-10-14")
    add(client, title="rīt", dueDate="2026-10-15")
    add(client, title="izpildīts", dueDate="2026-10-12", done=True)
    response = client.get("/tasks", params={"done": "false", "dueWithinDays": 0})
    assert titles(response) == ["kavēts", "šodien"]
    assert titles(client.get("/tasks", params={"done": "true"})) == ["izpildīts"]


def test_organization_filter(client, org):
    add(client, title="saistīts", organizationId=org["id"])
    add(client, title="bez organizācijas")
    assert titles(client.get("/tasks", params={"organizationId": org["id"]})) == ["saistīts"]
    assert client.get("/tasks", params={"organizationId": 2**70}).json() == []


# F5-12
def test_employee_sees_only_own_tasks(client, colleague):
    annas = add(colleague, title="Annas").json()
    add(client, title="mans")
    assert titles(client.get("/tasks")) == ["mans"]
    for response in [
        client.get(f"/tasks/{annas['id']}"),
        client.put(f"/tasks/{annas['id']}", json={}),
        client.post(f"/tasks/{annas['id']}/complete"),
    ]:
        assert response.status_code == 404
        assert response.json()["error"] == {"code": "NOT_FOUND", "message": "Task not found"}
    response = client.get("/tasks", params={"team": "true"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# F5-13
def test_manager_views_team_but_edits_only_own(manager, client):
    janis = add(client, title="Jāņa").json()
    add(manager, title="Vadītāja")
    assert titles(manager.get("/tasks")) == ["Vadītāja"]
    assert sorted(titles(manager.get("/tasks", params={"team": "true"}))) == ["Jāņa", "Vadītāja"]
    assert manager.get(f"/tasks/{janis['id']}").status_code == 200
    body = {"title": "X", "dueDate": "2026-10-20", "done": True}
    assert manager.put(f"/tasks/{janis['id']}", json=body).status_code == 403
    assert manager.post(f"/tasks/{janis['id']}/complete").status_code == 403
    assert client.get(f"/tasks/{janis['id']}").json()["done"] is False


@pytest.mark.parametrize("task_id", [999, 0, 2**70])
def test_unknown_task(client, task_id):
    assert client.get(f"/tasks/{task_id}").status_code == 404
    assert client.post(f"/tasks/{task_id}/complete").status_code == 404


# F5-14
@pytest.mark.parametrize(
    "method, path",
    [("get", "/tasks"), ("post", "/tasks"), ("get", "/tasks/1"), ("put", "/tasks/1"), ("post", "/tasks/1/complete")],
)
def test_admin_and_anonymous(app, set_role, method, path):
    admin = logged_in(app, "admin@example.com", set_role, "ADMIN")
    kwargs = {"json": {}} if method in ("post", "put") else {}
    assert getattr(admin, method)(path, **kwargs).status_code == 403
    assert getattr(TestClient(app), method)(path, **kwargs).status_code == 401


# F5-15
def test_page(app, client, set_role):
    assert TestClient(app).get("/uzdevumi", follow_redirects=False).headers["location"] == "/login"
    admin = logged_in(app, "admin@example.com", set_role, "ADMIN")
    assert admin.get("/uzdevumi", follow_redirects=False).headers["location"] == "/admin"
    html = client.get("/uzdevumi").text
    assert "<caption>Uzdevumi pēc termiņa</caption>" in html
    assert 'id="form"' in html
    assert 'role="status"' in html
    assert client.get("/static/tasks.js").status_code == 200


@pytest.mark.parametrize("page", ["/organizacijas", "/pieprasijumi", "/uzdevumi"])
def test_navigation_links_to_tasks(client, page):
    assert '<a href="/uzdevumi">Uzdevumi</a>' in client.get(page).text


def test_next_step_links_to_task_form(client):
    assert "/uzdevumi?" in client.get("/static/organization.js").text
