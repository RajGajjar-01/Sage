import pytest

from app.core.config import Settings
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
