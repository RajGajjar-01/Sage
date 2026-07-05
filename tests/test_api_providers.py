import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.dependencies import get_llm_service
from app.main import app
from app.services.llm_service import LlmService


@pytest.fixture
def client_without_provider():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_with_providers():
    llm = LlmService(Settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))

    async def _override_get_llm_service():
        return llm

    app.dependency_overrides[get_llm_service] = _override_get_llm_service
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
