"""F3 pieņemšanas kritēriju testi."""

import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import create_app

PASSWORD = "drosa-parole-1"


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
    body = {"occurredOn": "2026-10-01", "type": "CALL", "summary": "Pārrunāts projekts.", **fields}
    return client.post(f"/organizations/{org_id}/interactions", json=body)


def detail(response):
    return response.json()["error"]["details"]


def summaries(response):
    return [item["summary"] for item in response.json()]


# F3-1
def test_add_interaction(client, org):
    response = add(client, org["id"], summary="  Zvans par līgumu.  ", nextStep="Nosūtīt projektu.")
    assert response.status_code == 201
    body = response.json()
    assert body["organizationId"] == org["id"]
    assert body["organizationName"] == "SIA Ezermalas Ūdens"
    assert body["authorId"] == client.user_id
    assert body["occurredOn"] == "2026-10-01"
    assert body["type"] == "CALL"
    assert body["summary"] == "Zvans par līgumu."
    assert body["nextStep"] == "Nosūtīt projektu."
    assert body["createdAt"] == body["updatedAt"]


@pytest.mark.parametrize("next_step", [None, "", "   "])
def test_next_step_is_optional(client, org, next_step):
    assert add(client, org["id"], nextStep=next_step).json()["nextStep"] is None


@pytest.mark.parametrize("kind", ["CALL", "EMAIL", "MEETING"])
def test_all_types_accepted(client, org, kind):
    assert add(client, org["id"], type=kind).status_code == 201


# F3-2
def test_required_fields(client, org):
    response = client.post(f"/organizations/{org['id']}/interactions", json={"summary": "  "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert detail(response) == [
        {"field": "occurredOn", "issue": "REQUIRED"},
        {"field": "type", "issue": "REQUIRED"},
        {"field": "summary", "issue": "REQUIRED"},
    ]


# F3-3
@pytest.mark.parametrize("value", ["14.10.2026", "2026-02-30", "2026-1-5", 20261001, "nav datums"])
def test_invalid_date(client, org, value):
    response = add(client, org["id"], occurredOn=value)
    assert response.status_code == 400
    assert detail(response) == [{"field": "occurredOn", "issue": "INVALID_FORMAT"}]


# F3-4
def test_future_date_rejected_today_accepted(client, org):
    today = main.today()
    response = add(client, org["id"], occurredOn=(today + timedelta(days=1)).isoformat())
    assert response.status_code == 400
    assert detail(response) == [{"field": "occurredOn", "issue": "IN_FUTURE"}]
    assert add(client, org["id"], occurredOn=today.isoformat()).status_code == 201


def test_future_check_uses_server_today(monkeypatch, client, org):
    from datetime import date

    monkeypatch.setattr(main, "today", lambda: date(2026, 10, 1))
    assert add(client, org["id"], occurredOn="2026-10-02").status_code == 400
    assert add(client, org["id"], occurredOn="2026-10-01").status_code == 201


# F3-5
@pytest.mark.parametrize("kind", ["SMS", "call", 1])
def test_unknown_type(client, org, kind):
    response = add(client, org["id"], type=kind)
    assert detail(response) == [{"field": "type", "issue": "INVALID_FORMAT"}]


# F3-6
def test_length_limits(client, org):
    assert add(client, org["id"], summary="A" * 2000, nextStep="B" * 500).status_code == 201
    response = add(client, org["id"], summary="A" * 2001, nextStep="B" * 501)
    assert detail(response) == [
        {"field": "summary", "issue": "TOO_LONG"},
        {"field": "nextStep", "issue": "TOO_LONG"},
    ]


# F3-7
@pytest.mark.parametrize("org_id", [999, 0, 2**70])
def test_unknown_organization(client, org_id):
    for response in [add(client, org_id), client.get(f"/organizations/{org_id}/interactions")]:
        assert response.status_code == 404
        assert response.json()["error"] == {"code": "NOT_FOUND", "message": "Organization not found"}


def test_unknown_organization_checked_before_body(client):
    response = client.post("/organizations/999/interactions", json={})
    assert response.status_code == 404


# F3-8
def test_organization_history_newest_first(client, org):
    other = client.post("/organizations", json={"name": "Cita"}).json()
    add(client, org["id"], occurredOn="2026-09-01", summary="vecākais")
    add(client, org["id"], occurredOn="2026-10-05", summary="jaunākais")
    add(client, org["id"], occurredOn="2026-09-01", summary="tajā pašā dienā, vēlāk pievienots")
    add(client, other["id"], summary="citai organizācijai")
    response = client.get(f"/organizations/{org['id']}/interactions")
    assert response.status_code == 200
    assert summaries(response) == ["jaunākais", "tajā pašā dienā, vēlāk pievienots", "vecākais"]


def test_empty_history(client, org):
    assert client.get(f"/organizations/{org['id']}/interactions").json() == []


# F3-9
def test_latest_mine_with_limit(app, client, org, set_role):
    anna = logged_in(app, "anna@example.com")
    annas_org = anna.post("/organizations", json={"name": "Annas"}).json()
    for day in range(1, 8):
        add(client, org["id"], occurredOn=f"2026-10-0{day}", summary=f"mans {day}")
    add(anna, annas_org["id"], occurredOn="2026-10-09", summary="Annas")
    set_role(client.user_id, "MANAGER")  # vadītājs redz arī Annas ierakstus (N3)
    response = client.get("/interactions", params={"mine": "true", "limit": 5})
    assert response.status_code == 200
    assert summaries(response) == ["mans 7", "mans 6", "mans 5", "mans 4", "mans 3"]
    assert summaries(client.get("/interactions", params={"limit": 2})) == ["Annas", "mans 7"]
    assert len(client.get("/interactions").json()) == 8


@pytest.mark.parametrize("limit", [0, 101, "daudz"])
def test_limit_bounds(client, limit):
    response = client.get("/interactions", params={"limit": limit})
    assert response.status_code == 400
    assert detail(response) == [{"field": "limit", "issue": "INVALID_FORMAT"}]


# F3-10
def test_author_edits_own_interaction(client, org):
    item = add(client, org["id"], nextStep="Zvanīt vēlreiz.").json()
    time.sleep(0.01)
    response = client.put(
        f"/interactions/{item['id']}",
        json={"occurredOn": "2026-09-30", "type": "MEETING", "summary": "Tikšanās.", "nextStep": ""},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["occurredOn"], body["type"], body["summary"], body["nextStep"]) == (
        "2026-09-30",
        "MEETING",
        "Tikšanās.",
        None,
    )
    assert body["organizationId"] == item["organizationId"]
    assert body["authorId"] == item["authorId"]
    assert body["createdAt"] == item["createdAt"]
    assert body["updatedAt"] > item["updatedAt"]
    assert client.get(f"/interactions/{item['id']}").json() == body


def test_edit_validation_error_changes_nothing(client, org):
    item = add(client, org["id"]).json()
    response = client.put(f"/interactions/{item['id']}", json={"type": "SMS"})
    assert response.status_code == 400
    assert client.get(f"/interactions/{item['id']}").json() == item


# F3-11
def test_other_user_cannot_edit(app, client, org, set_role):
    item = add(client, org["id"]).json()
    anna = logged_in(app, "anna@example.com")
    set_role(anna.user_id, "MANAGER")  # redz ierakstu, bet nav autore
    response = anna.put(
        f"/interactions/{item['id']}",
        json={"occurredOn": "2026-10-01", "type": "CALL", "summary": "Pārrakstīts."},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert anna.get(f"/interactions/{item['id']}").json() == item


# F3-12
@pytest.mark.parametrize("method", ["get", "put"])
@pytest.mark.parametrize("item_id", [999, 0, 2**70])
def test_unknown_interaction(client, method, item_id):
    kwargs = {"json": {"summary": "X"}} if method == "put" else {}
    response = getattr(client, method)(f"/interactions/{item_id}", **kwargs)
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "NOT_FOUND", "message": "Interaction not found"}


def test_non_numeric_id(client):
    response = client.get("/interactions/abc")
    assert response.status_code == 400
    assert detail(response) == [{"field": "id", "issue": "INVALID_FORMAT"}]


# F3-13
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/auth/me", None),
        ("get", "/organizations/1/interactions", None),
        ("post", "/organizations/1/interactions", {}),
        ("get", "/interactions", None),
        ("get", "/interactions/1", None),
        ("put", "/interactions/1", {}),
    ],
)
def test_requires_session(app, method, path, body):
    kwargs = {"json": body} if body is not None else {}
    response = getattr(TestClient(app), method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_current_user(client):
    assert client.get("/auth/me").json() == {
        "id": client.user_id,
        "email": "janis@example.com",
        "name": None,
        "role": "EMPLOYEE",
    }


# F3-14
def test_card_redirects_to_login_without_session(app, org):
    response = TestClient(app).get(f"/organizacijas/{org['id']}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_card_with_session(client, org):
    response = client.get(f"/organizacijas/{org['id']}")
    assert response.status_code == 200
    html = response.text
    assert 'id="form"' in html
    assert "Mijiedarbību vēsture" in html
    assert "Nerakstiet personas kodus" in html
    assert 'role="status"' in html
    assert client.get("/static/organization.js").status_code == 200


def test_organization_list_links_to_card(client):
    assert "/organizacijas/${org.id}" in client.get("/static/organizations.js").text
