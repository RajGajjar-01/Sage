import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app.core.database import _SCHEMA, get_db
from app.main import app


@pytest.fixture
async def db_connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


@pytest.fixture
def client(db_connection):
    async def _override_get_db():
        yield db_connection

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_and_list_sessions(client):
    create_response = client.post("/api/v1/sessions", json={"title": "My session"})
    assert create_response.status_code == 201
    created = create_response.json()["data"]
    assert created["title"] == "My session"

    list_response = client.get("/api/v1/sessions")
    assert list_response.status_code == 200
    assert [s["id"] for s in list_response.json()["data"]] == [created["id"]]


def test_create_session_defaults_title_when_omitted(client):
    response = client.post("/api/v1/sessions", json={})
    assert response.status_code == 201
    assert response.json()["data"]["title"].startswith("Session ")


def test_get_session_not_found(client):
    response = client.get("/api/v1/sessions/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["title"] == "SESSION_NOT_FOUND"


def test_get_session_returns_detail(client):
    created = client.post("/api/v1/sessions", json={"title": "My session"}).json()[
        "data"
    ]

    response = client.get(f"/api/v1/sessions/{created['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


def test_list_messages_for_unknown_session_returns_404(client):
    response = client.get("/api/v1/sessions/does-not-exist/messages")
    assert response.status_code == 404


def test_list_messages_returns_empty_for_new_session(client):
    created = client.post("/api/v1/sessions", json={"title": "My session"}).json()[
        "data"
    ]

    response = client.get(f"/api/v1/sessions/{created['id']}/messages")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_liveness_endpoint():
    with TestClient(app) as test_client:
        response = test_client.get("/live")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"
