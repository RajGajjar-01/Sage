import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import _SCHEMA, get_db
from app.core.dependencies import get_llm_service
from app.main import app
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import LlmService


@pytest.fixture
async def db_connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


@pytest.fixture
def client_without_provider(db_connection):
    async def _override_get_db():
        yield db_connection

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_providers(db_connection):
    llm = LlmService(Settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))

    async def _override_get_llm_service():
        return llm

    async def _override_get_db():
        yield db_connection

    app.dependency_overrides[get_llm_service] = _override_get_llm_service
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_list_providers_without_configuration_returns_503(client_without_provider):
    response = client_without_provider.get("/api/v1/providers")
    assert response.status_code == 503
    assert response.json()["error"]["title"] == "NO_PROVIDER_CONFIGURED"


def test_list_providers_redacts_api_key(client_with_providers):
    response = client_with_providers.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["active"] == "GROQ"
    assert all(p["api_key"] == "***" for p in body["providers"])


def test_switch_provider_updates_active(client_with_providers):
    response = client_with_providers.post(
        "/api/v1/providers/switch", json={"name": "ZHIPU"}
    )
    assert response.status_code == 200
    assert response.json()["data"]["active"] == "ZHIPU"


def test_switch_provider_unknown_name_returns_404(client_with_providers):
    response = client_with_providers.post(
        "/api/v1/providers/switch", json={"name": "NOPE"}
    )
    assert response.status_code == 404


def test_connect_bootstraps_llm_service_when_none_configured(client_without_provider):
    response = client_without_provider.post(
        "/api/v1/providers/connect",
        json={
            "name": "GROQ",
            "api_key": "key",
            "model": "llama",
            "endpoint": "https://groq.example/",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["name"] == "GROQ"
    list_response = client_without_provider.get("/api/v1/providers")
    assert list_response.json()["data"]["active"] == "GROQ"


def test_connect_adds_second_provider_to_existing_service(client_without_provider):
    client_without_provider.post(
        "/api/v1/providers/connect",
        json={
            "name": "GROQ",
            "api_key": "key1",
            "model": "llama",
            "endpoint": "https://groq.example/",
        },
    )

    response = client_without_provider.post(
        "/api/v1/providers/connect",
        json={
            "name": "ZHIPU",
            "api_key": "key2",
            "model": "glm",
            "endpoint": "https://zhipu.example/",
        },
    )

    assert response.status_code == 201
    names = [
        p["name"]
        for p in client_without_provider.get("/api/v1/providers").json()["data"][
            "providers"
        ]
    ]
    assert names == ["GROQ", "ZHIPU"]


@pytest.mark.asyncio
async def test_connect_persists_credential_to_database(
    client_without_provider, db_connection
):
    client_without_provider.post(
        "/api/v1/providers/connect",
        json={
            "name": "GROQ",
            "api_key": "key",
            "model": "llama",
            "endpoint": "https://groq.example/",
        },
    )

    stored = await ProviderRepository(db_connection).get("GROQ")
    assert stored is not None
    assert stored.api_key == "key"
