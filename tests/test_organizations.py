"""F1 pieņemšanas kritēriju testi."""

import time

import pytest
from fastapi.testclient import TestClient

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


def create(client, **fields):
    return client.post("/organizations", json={"name": "SIA Ezermalas Ūdens", **fields})


def detail(response):
    return response.json()["error"]["details"]


def names(response):
    return [org["name"] for org in response.json()]


# F1-1
def test_create_with_name_only(client):
    response = create(client, name="  SIA Ezermalas Ūdens  ")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "SIA Ezermalas Ūdens"
    assert body["regNumber"] is None
    assert body["address"] is None
    assert body["responsibleUserId"] == client.user_id
    assert isinstance(body["id"], int)
    assert body["createdAt"] == body["updatedAt"]


def test_create_with_all_fields(app, client, set_role):
    other = logged_in(app, "anna@example.com")
    set_role(client.user_id, "MANAGER")  # citu atbildīgo norāda vadītājs (N3)
    response = create(
        client, regNumber="40003000001", address="Ezera iela 1", responsibleUserId=other.user_id
    )
    assert response.status_code == 201
    body = response.json()
    assert body["regNumber"] == "40003000001"
    assert body["address"] == "Ezera iela 1"
    assert body["responsibleUserId"] == other.user_id


def test_empty_optional_fields_are_stored_as_null(client):
    body = create(client, regNumber="", address="   ").json()
    assert body["regNumber"] is None
    assert body["address"] is None


# F1-2
@pytest.mark.parametrize("payload", [{}, {"name": None}, {"name": ""}, {"name": "   "}])
def test_name_is_required(client, payload):
    response = client.post("/organizations", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert detail(response) == [{"field": "name", "issue": "REQUIRED"}]


def test_name_must_be_text(client):
    response = client.post("/organizations", json={"name": 123})
    assert detail(response) == [{"field": "name", "issue": "INVALID_FORMAT"}]


# F1-3
def test_name_too_long(client):
    assert create(client, name="A" * 200).status_code == 201
    response = create(client, name="A" * 201)
    assert response.status_code == 400
    assert detail(response) == [{"field": "name", "issue": "TOO_LONG"}]


def test_address_too_long(client):
    response = create(client, address="A" * 301)
    assert detail(response) == [{"field": "address", "issue": "TOO_LONG"}]


# F1-4
@pytest.mark.parametrize("reg_number", ["123", "4000300000A", "400030000011", 40003000001])
def test_reg_number_format(client, reg_number):
    response = create(client, regNumber=reg_number)
    assert response.status_code == 400
    assert detail(response) == [{"field": "regNumber", "issue": "INVALID_FORMAT"}]


def test_several_errors_are_reported_together(client):
    response = client.post("/organizations", json={"regNumber": "123"})
    assert detail(response) == [
        {"field": "name", "issue": "REQUIRED"},
        {"field": "regNumber", "issue": "INVALID_FORMAT"},
    ]


# F1-5
def test_duplicate_reg_number_on_create(client):
    create(client, regNumber="40003000001")
    response = create(client, name="Cita", regNumber="40003000001")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_EXISTS"
    assert detail(response) == [{"field": "regNumber", "issue": "ALREADY_EXISTS"}]


def test_duplicate_reg_number_on_update(client):
    create(client, regNumber="40003000001")
    other = create(client, name="Cita", regNumber="40003000002").json()
    response = client.put(
        f"/organizations/{other['id']}", json={"name": "Cita", "regNumber": "40003000001"}
    )
    assert response.status_code == 409
    assert client.get(f"/organizations/{other['id']}").json()["regNumber"] == "40003000002"


def test_update_keeps_own_reg_number(client):
    org = create(client, regNumber="40003000001").json()
    response = client.put(
        f"/organizations/{org['id']}", json={"name": "Jauns", "regNumber": "40003000001"}
    )
    assert response.status_code == 200


# F1-6
@pytest.mark.parametrize(
    "user_id, issue",
    [
        (999, "NOT_FOUND"),
        (0, "NOT_FOUND"),
        (2**70, "NOT_FOUND"),
        ("1", "INVALID_FORMAT"),
        (True, "INVALID_FORMAT"),
    ],
)
def test_responsible_user_must_exist(client, user_id, issue):
    response = create(client, responsibleUserId=user_id)
    assert response.status_code == 400
    assert detail(response) == [{"field": "responsibleUserId", "issue": issue}]


# F1-7
def test_update(app, client, set_role):
    other = logged_in(app, "anna@example.com")
    set_role(client.user_id, "MANAGER")  # atbildīgo maina vadītājs (N3)
    org = create(client, regNumber="40003000001", address="Ezera iela 1").json()
    time.sleep(0.01)
    response = client.put(
        f"/organizations/{org['id']}",
        json={"name": "SIA Jaunais", "address": "Krasta iela 5", "responsibleUserId": other.user_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "SIA Jaunais"
    assert body["regNumber"] is None
    assert body["address"] == "Krasta iela 5"
    assert body["responsibleUserId"] == other.user_id
    assert body["createdAt"] == org["createdAt"]
    assert body["updatedAt"] > org["updatedAt"]
    assert client.get(f"/organizations/{org['id']}").json() == body


def test_update_without_responsible_user_keeps_it(client):
    org = create(client).json()
    body = client.put(f"/organizations/{org['id']}", json={"name": "Cits"}).json()
    assert body["responsibleUserId"] == client.user_id


def test_update_validation_error_changes_nothing(client):
    org = create(client).json()
    response = client.put(f"/organizations/{org['id']}", json={"name": ""})
    assert response.status_code == 400
    assert client.get(f"/organizations/{org['id']}").json() == org


# F1-8
def test_get_existing(client):
    org = create(client).json()
    response = client.get(f"/organizations/{org['id']}")
    assert response.status_code == 200
    assert response.json() == org


@pytest.mark.parametrize("method", ["get", "put"])
@pytest.mark.parametrize("org_id", [999, 0, -1, 2**70])
def test_unknown_organization(client, method, org_id):
    kwargs = {"json": {"name": "X"}} if method == "put" else {}
    response = getattr(client, method)(f"/organizations/{org_id}", **kwargs)
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "NOT_FOUND", "message": "Organization not found"}


def test_non_numeric_id(client):
    response = client.get("/organizations/abc")
    assert response.status_code == 400
    assert detail(response) == [{"field": "id", "issue": "INVALID_FORMAT"}]


# F1-9
def test_search_by_name_ignores_case_including_latvian_letters(client):
    for name in ["SIA Rīgas Ūdens", "RĪGAS DOME", "Ogres pils", "Rigas tirgus"]:
        create(client, name=name)
    response = client.get("/organizations", params={"q": "rīga"})
    assert response.status_code == 200
    assert names(response) == ["RĪGAS DOME", "SIA Rīgas Ūdens"]
    assert names(client.get("/organizations", params={"q": "ŪDENS"})) == ["SIA Rīgas Ūdens"]


def test_search_treats_wildcards_literally(client):
    create(client, name="100% Bio")
    create(client, name="Bio fonds")
    assert names(client.get("/organizations", params={"q": "%"})) == ["100% Bio"]


# F1-10
def test_search_by_reg_number(client):
    create(client, name="A", regNumber="40003000001")
    create(client, name="B", regNumber="50009999999")
    assert names(client.get("/organizations", params={"q": "4000"})) == ["A"]


def test_list_sorted_by_latvian_alphabet(client):
    for name in ["Zīle", "ceļi", "Čiekurs", "Ābele", "Bērzi", "abols"]:
        create(client, name=name)
    assert names(client.get("/organizations")) == ["abols", "Ābele", "Bērzi", "ceļi", "Čiekurs", "Zīle"]


def test_search_without_results(client):
    create(client)
    response = client.get("/organizations", params={"q": "nekas"})
    assert response.status_code == 200
    assert response.json() == []


# F1-11
def test_mine_filter(app, client, set_role):
    anna = logged_in(app, "anna@example.com")
    set_role(client.user_id, "MANAGER")
    create(client, name="Mana")
    create(client, name="Annai", responsibleUserId=anna.user_id)
    create(anna, name="Annas")
    assert names(client.get("/organizations", params={"mine": "true"})) == ["Mana"]
    assert len(client.get("/organizations").json()) == 3
    assert names(anna.get("/organizations")) == ["Annai", "Annas"]


def test_mine_must_be_boolean(client):
    response = client.get("/organizations", params={"mine": "varbūt"})
    assert response.status_code == 400
    assert detail(response) == [{"field": "mine", "issue": "INVALID_FORMAT"}]


# F1-12
@pytest.mark.parametrize(
    "method, path, body",
    [
        ("get", "/organizations", None),
        ("post", "/organizations", {"name": "X"}),
        ("post", "/organizations", {}),
        ("get", "/organizations/1", None),
        ("put", "/organizations/1", {"name": "X"}),
        ("get", "/organizations/abc", None),
    ],
)
def test_requires_session(app, method, path, body):
    anonymous = TestClient(app)
    kwargs = {"json": body} if body is not None else {}
    response = getattr(anonymous, method)(path, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_invalid_session_token(app, client):
    create(client)
    stranger = TestClient(app, cookies={"session": "viltots"})
    assert stranger.get("/organizations").status_code == 401


def test_anonymous_cannot_change_data(app, client):
    org = create(client).json()
    TestClient(app).put(f"/organizations/{org['id']}", json={"name": "Uzlauzts"})
    assert client.get(f"/organizations/{org['id']}").json()["name"] == org["name"]


# F1-13
def test_page_redirects_to_login_without_session(app):
    response = TestClient(app).get("/organizacijas", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# F1-14
def test_page_with_session(client):
    response = client.get("/organizacijas")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert 'role="search"' in html
    assert "<caption>" in html
    assert '<th scope="col">' in html
    assert 'id="form"' in html
    assert 'role="status"' in html


def test_page_script_is_served(client):
    assert client.get("/static/organizations.js").status_code == 200
