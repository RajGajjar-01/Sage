import pytest

from app.core.config import Settings
from app.models.provider import ProviderCredential
from app.services.llm_service import (
    LlmService,
    NoProviderConfiguredError,
    is_rate_limit_error,
    load_providers,
)


def _settings(**overrides) -> Settings:
    base = {"GROQ_API_KEY": None, "ZHIPU_API_KEY": None}
    base.update(overrides)
    return Settings(**base)


def test_load_providers_empty_when_no_keys():
    assert load_providers(_settings()) == []


def test_load_providers_groq_first():
    settings = _settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key")
    providers = load_providers(settings)
    assert [p.name for p in providers] == ["GROQ", "ZHIPU"]


def test_service_raises_without_any_provider():
    with pytest.raises(NoProviderConfiguredError):
        LlmService(_settings())


def test_service_defaults_to_first_provider():
    service = LlmService(_settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))
    assert service.active_provider.name == "GROQ"


@pytest.mark.asyncio
async def test_switch_to_next_provider_round_robins():
    service = LlmService(_settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))

    switched = await service.switch_to_next_provider()

    assert switched is True
    assert service.active_provider.name == "ZHIPU"


@pytest.mark.asyncio
async def test_switch_to_next_provider_returns_false_with_single_provider():
    service = LlmService(_settings(GROQ_API_KEY="groq-key"))
    assert await service.switch_to_next_provider() is False


@pytest.mark.asyncio
async def test_switch_to_next_provider_closes_old_client():
    service = LlmService(_settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))
    old_client = service._client

    await service.switch_to_next_provider()

    assert old_client.is_closed()


@pytest.mark.asyncio
async def test_switch_provider_closes_old_client():
    service = LlmService(_settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))
    old_client = service._client
    zhipu = next(p for p in service.providers if p.name == "ZHIPU")

    await service.switch_provider(zhipu)

    assert old_client.is_closed()
    assert service.active_provider.name == "ZHIPU"


@pytest.mark.parametrize(
    "message",
    [
        "Rate limit exceeded",
        "429 Too Many Requests",
        "Invalid API key",
        "insufficient credits",
    ],
)
def test_is_rate_limit_error_matches_known_markers(message):
    assert is_rate_limit_error(Exception(message)) is True


def test_is_rate_limit_error_ignores_unrelated_errors():
    assert is_rate_limit_error(Exception("connection reset")) is False


def test_load_providers_stored_credential_overrides_env_provider_in_place():
    settings = _settings(GROQ_API_KEY="env-key", ZHIPU_API_KEY="zhipu-key")
    stored = [
        ProviderCredential(
            name="GROQ", api_key="db-key", model="m", endpoint="https://x/"
        )
    ]

    providers = load_providers(settings, stored)

    assert [p.name for p in providers] == ["GROQ", "ZHIPU"]
    assert providers[0].api_key == "db-key"


def test_load_providers_stored_credential_adds_new_provider():
    settings = _settings(GROQ_API_KEY="groq-key")
    stored = [
        ProviderCredential(
            name="OPENAI",
            api_key="k",
            model="gpt-4",
            endpoint="https://api.openai.com/v1/",
        )
    ]

    providers = load_providers(settings, stored)

    assert [p.name for p in providers] == ["GROQ", "OPENAI"]


def test_load_providers_stored_credential_alone_is_enough():
    settings = _settings()
    stored = [
        ProviderCredential(
            name="GROQ", api_key="k", model="llama", endpoint="https://x/"
        )
    ]

    providers = load_providers(settings, stored)

    assert [p.name for p in providers] == ["GROQ"]


@pytest.mark.asyncio
async def test_add_provider_appends_new_provider():
    service = LlmService(_settings(GROQ_API_KEY="groq-key"))

    await service.add_provider(
        ProviderCredential(
            name="OPENAI",
            api_key="k",
            model="gpt-4",
            endpoint="https://api.openai.com/v1/",
        )
    )

    assert [p.name for p in service.providers] == ["GROQ", "OPENAI"]
    assert service.active_provider.name == "GROQ"


@pytest.mark.asyncio
async def test_add_provider_updates_active_provider_and_closes_old_client():
    service = LlmService(_settings(GROQ_API_KEY="old-key"))
    old_client = service._client

    await service.add_provider(
        ProviderCredential(
            name="GROQ", api_key="new-key", model="m", endpoint="https://x/"
        )
    )

    assert service.active_provider.api_key == "new-key"
    assert old_client.is_closed()


@pytest.mark.asyncio
async def test_add_provider_updates_inactive_provider_without_rebuilding_active_client():
    service = LlmService(_settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))
    active_client = service._client

    await service.add_provider(
        ProviderCredential(
            name="ZHIPU", api_key="new-zhipu-key", model="m", endpoint="https://x/"
        )
    )

    zhipu = next(p for p in service.providers if p.name == "ZHIPU")
    assert zhipu.api_key == "new-zhipu-key"
    assert service._client is active_client
    assert not active_client.is_closed()
