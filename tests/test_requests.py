"""F4 pieņemšanas kritēriju testi."""

import time
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


def logged_in(app, email="janis@example.com"):
    client = TestClient(app)
    user_id = client.post("/auth/register", json={"email": email, "password": PASSWORD}).json()["id"]
    client.post("/auth/login", json={"email": email, "password": PASSWORD})
    client.user_id = user_id
    return client


@pytest.fixture
def client(app):
    return logged_in(app)


@pytest.fixture
def org(client):
    return client.post("/organizations", json={"name": "SIA Ezermalas Ūdens"}).json()


def add(client, org_id, **fields):
    body = {"organizationId": org_id, "title": "Mērījumu dati", "dueDate": "2026-11-13", **fields}
    return client.post("/requests", json=body)


def update(client, request_id, **fields):
    body = {"title": "Mērījumu dati", "dueDate": "2026-11-13", "status": "NEW", **fields}
    return client.put(f"/requests/{request_id}", json=body)


def detail(response):
    return response.json()["error"]["details"]


def titles(response):
    assert response.status_code == 200
    return [item["title"] for item in response.json()]


# F4-1
def test_register_request(client, org):
    response = add(client, org["id"], title="  Mērījumu dati  ", description="Lūdz 2026. gada datus.")
    assert response.status_code == 201
    body = response.json()
    assert body["organizationId"] == org["id"]
    assert body["organizationName"] == "SIA Ezermalas Ūdens"
    assert body["title"] == "Mērījumu dati"
    assert body["description"] == "Lūdz 2026. gada datus."
    assert body["dueDate"] == "2026-11-13"
    assert body["status"] == "NEW"
    assert body["overdue"] is False
    assert body["overdueDays"] == 0
    assert body["createdAt"] == body["updatedAt"]


def test_register_with_status_and_empty_description(client, org):
    body = add(client, org["id"], status="IN_PROGRESS", description="  ").json()
    assert body["status"] == "IN_PROGRESS"
    assert body["description"] is None


# F4-2
def test_required_fields(client):
    response = client.post("/requests", json={"title": " "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert detail(response) == [
        {"field": "organizationId", "issue": "REQUIRED"},
        {"field": "title", "issue": "REQUIRED"},
        {"field": "dueDate", "issue": "REQUIRED"},
    ]


# F4-3
@pytest.mark.parametrize("org_id, issue", [(999, "NOT_FOUND"), (2**70, "NOT_FOUND"), ("1", "INVALID_FORMAT")])
def test_unknown_organization(client, org_id, issue):
    response = add(client, org_id)
    assert response.status_code == 400
    assert detail(response) == [{"field": "organizationId", "issue": issue}]


# F4-4
@pytest.mark.parametrize("due", ["2026-02-30", "13.11.2026", 20261113])
def test_invalid_due_date(client, org, due):
    assert detail(add(client, org["id"], dueDate=due)) == [{"field": "dueDate", "issue": "INVALID_FORMAT"}]


@pytest.mark.parametrize("status", ["DONE", "new", 1])
def test_invalid_status(client, org, status):
    assert detail(add(client, org["id"], status=status)) == [{"field": "status", "issue": "INVALID_FORMAT"}]


def test_past_due_date_allowed(client, org):
    assert add(client, org["id"], dueDate="2026-01-01").status_code == 201


# F4-5
def test_length_limits(client, org):
    assert add(client, org["id"], title="A" * 200, description="B" * 2000).status_code == 201
    response = add(client, org["id"], title="A" * 201, description="B" * 2001)
    assert detail(response) == [
        {"field": "title", "issue": "TOO_LONG"},
        {"field": "description", "issue": "TOO_LONG"},
    ]


# F4-6
@pytest.mark.parametrize("status", ["NEW", "IN_PROGRESS"])
def test_open_request_past_due_is_overdue(client, org, status):
    body = add(client, org["id"], dueDate="2026-10-13", status=status).json()
    assert (body["overdue"], body["overdueDays"]) == (True, 1)


def test_overdue_days_count(client, org):
    assert add(client, org["id"], dueDate="2026-09-14").json()["overdueDays"] == 30


# F4-7
def test_answered_or_due_today_is_not_overdue(client, org):
    answered = add(client, org["id"], dueDate="2026-10-13", status="ANSWERED").json()
    due_today = add(client, org["id"], dueDate="2026-10-14").json()
    for body in (answered, due_today):
        assert (body["overdue"], body["overdueDays"]) == (False, 0)


def test_overdue_follows_today(monkeypatch, client, org):
    item = add(client, org["id"], dueDate="2026-10-14").json()
    monkeypatch.setattr(main, "today", lambda: date(2026, 10, 17))
    body = client.get(f"/requests/{item['id']}").json()
    assert (body["overdue"], body["overdueDays"]) == (True, 3)


# F4-8
def test_update_request(app, client, org):
    item = add(client, org["id"]).json()
    other = client.post("/organizations", json={"name": "Cita"}).json()
    time.sleep(0.01)
    anna = logged_in(app, "anna@example.com")
    response = anna.put(
        f"/requests/{item['id']}",
        json={
            "title": "Precizēts",
            "description": None,
            "dueDate": "2026-10-10",
            "status": "IN_PROGRESS",
            "organizationId": other["id"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["description"], body["dueDate"], body["status"]) == (
        "Precizēts",
        None,
        "2026-10-10",
        "IN_PROGRESS",
    )
    assert (body["overdue"], body["overdueDays"]) == (True, 4)
    assert body["organizationId"] == org["id"]
    assert body["createdAt"] == item["createdAt"]
    assert body["updatedAt"] > item["updatedAt"]
    assert client.get(f"/requests/{item['id']}").json() == body


def test_reopen_answered_request(client, org):
    item = add(client, org["id"], status="ANSWERED").json()
    assert update(client, item["id"], status="NEW").json()["status"] == "NEW"


# F4-9
def test_update_requires_status(client, org):
    item = add(client, org["id"]).json()
    response = client.put(f"/requests/{item['id']}", json={"title": "X", "dueDate": "2026-11-13"})
    assert response.status_code == 400
    assert detail(response) == [{"field": "status", "issue": "REQUIRED"}]
    assert client.get(f"/requests/{item['id']}").json() == item


# F4-10
@pytest.mark.parametrize("method", ["get", "put"])
@pytest.mark.parametrize("request_id", [999, 0, 2**70])
def test_unknown_request(client, method, request_id):
    kwargs = {"json": {}} if method == "put" else {}
    response = getattr(client, method)(f"/requests/{request_id}", **kwargs)
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "NOT_FOUND", "message": "Request not found"}


@pytest.fixture
def sample(app, client, org):
    """Pieprasījumi ar dažādiem statusiem un termiņiem; šodiena ir 2026-10-14."""
    anna = logged_in(app, "anna@example.com")
    annas_org = anna.post("/organizations", json={"name": "Annas organizācija"}).json()
    add(client, org["id"], title="kavēts 5 d.", dueDate="2026-10-09", status="IN_PROGRESS")
    add(client, org["id"], title="šodien", dueDate="2026-10-14")
    add(client, org["id"], title="pēc 7 d.", dueDate="2026-10-21")
    add(client, org["id"], title="pēc 8 d.", dueDate="2026-10-22")
    add(client, org["id"], title="atbildēts, termiņš pagājis", dueDate="2026-10-01", status="ANSWERED")
    add(client, annas_org["id"], title="Annas kavēts", dueDate="2026-10-12")
    return annas_org


def test_list_sorted_by_due_date(client, sample):
    assert titles(client.get("/requests")) == [
        "atbildēts, termiņš pagājis",
        "kavēts 5 d.",
        "Annas kavēts",
        "šodien",
        "pēc 7 d.",
        "pēc 8 d.",
    ]


# F4-11
def test_filter_open_statuses(client, sample):
    response = client.get("/requests", params=[("status", "NEW"), ("status", "IN_PROGRESS")])
    assert titles(response) == ["kavēts 5 d.", "Annas kavēts", "šodien", "pēc 7 d.", "pēc 8 d."]
    assert titles(client.get("/requests", params={"status": "ANSWERED"})) == ["atbildēts, termiņš pagājis"]


# F4-12
def test_filter_overdue(client, sample):
    overdue = titles(client.get("/requests", params={"overdue": "true"}))
    assert overdue == ["kavēts 5 d.", "Annas kavēts"]
    everything = client.get("/requests").json()
    assert len(overdue) == sum(item["overdue"] for item in everything)
    not_overdue = titles(client.get("/requests", params={"overdue": "false"}))
    assert len(overdue) + len(not_overdue) == len(everything)


# F4-13
def test_filter_due_within_days(client, sample):
    assert titles(client.get("/requests", params={"dueWithinDays": 7})) == [
        "kavēts 5 d.",
        "Annas kavēts",
        "šodien",
        "pēc 7 d.",
    ]
    assert titles(client.get("/requests", params={"dueWithinDays": 0})) == [
        "kavēts 5 d.",
        "Annas kavēts",
        "šodien",
    ]


# F4-14
def test_filter_mine(client, sample):
    assert "Annas kavēts" not in titles(client.get("/requests", params={"mine": "true"}))
    combined = client.get("/requests", params={"mine": "true", "overdue": "true"})
    assert titles(combined) == ["kavēts 5 d."]


# F4-15
def test_filter_organization(client, sample):
    assert titles(client.get("/requests", params={"organizationId": sample["id"]})) == ["Annas kavēts"]
    assert titles(client.get("/requests", params={"organizationId": 999})) == []
    assert titles(client.get("/requests", params={"organizationId": 2**70})) == []


# F4-16
@pytest.mark.parametrize(
    "params, field",
    [
        ({"status": "DONE"}, "status"),
        ({"dueWithinDays": -1}, "dueWithinDays"),
        ({"dueWithinDays": 366}, "dueWithinDays"),
        ({"overdue": "varbūt"}, "overdue"),
        ({"organizationId": "abc"}, "organizationId"),
    ],
)
def test_invalid_filters(client, params, field):
    response = client.get("/requests", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert detail(response)[0]["field"] == field


# F4-17
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/requests", None),
        ("post", "/requests", {}),
        ("get", "/requests/1", None),
        ("put", "/requests/1", {}),
    ],
)
def test_requires_session(app, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    response = getattr(TestClient(app), method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# F4-18
def test_page_redirects_to_login_without_session(app):
    response = TestClient(app).get("/pieprasijumi", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_page_with_session(client):
    response = client.get("/pieprasijumi")
    assert response.status_code == 200
    html = response.text
    assert 'id="filters"' in html
    assert "<caption>" in html
    assert '<th scope="col">' in html
    assert 'id="form"' in html
    assert 'role="status"' in html
    assert client.get("/static/requests.js").status_code == 200


def test_organization_card_has_requests_section(client, org):
    assert 'id="requests-heading"' in client.get(f"/organizacijas/{org['id']}").text
