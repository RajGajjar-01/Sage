import json

import httpx
import pytest

from app.core.config import Settings
from app.models.agent import Message
from app.models.provider import ProviderCredential
from app.services.llm_service import (
    LlmProvider,
    LlmService,
    ModelInfo,
    NoProviderConfiguredError,
    ProvidersExhaustedError,
    is_rate_limit_error,
    list_models,
    load_providers,
)


def _credential(name: str, endpoint: str) -> ProviderCredential:
    return ProviderCredential(name=name, api_key="k", model="m", endpoint=endpoint)


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

    assert old_client.is_closed


@pytest.mark.asyncio
async def test_switch_provider_closes_old_client():
    service = LlmService(_settings(GROQ_API_KEY="groq-key", ZHIPU_API_KEY="zhipu-key"))
    old_client = service._client
    zhipu = next(p for p in service.providers if p.name == "ZHIPU")

    await service.switch_provider(zhipu)

    assert old_client.is_closed
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
    assert old_client.is_closed


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
    assert not active_client.is_closed


def _mock_http(monkeypatch, handler):
    """Route every httpx.AsyncClient built by llm_service through a mock transport."""
    real = httpx.AsyncClient
    monkeypatch.setattr(
        "app.services.llm_service.httpx.AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_list_models_returns_sorted_ids(monkeypatch):
    def handler(request):
        assert str(request.url) == "https://example.com/v1/models"
        assert request.headers["authorization"] == "Bearer key"
        return httpx.Response(200, json={"data": [{"id": "llama-b"}, {"id": "llama-a"}]})

    _mock_http(monkeypatch, handler)

    assert await list_models("key", "https://example.com/v1") == [
        ModelInfo("llama-a"),
        ModelInfo("llama-b"),
    ]


@pytest.mark.asyncio
async def test_list_models_flags_free_and_paid_from_pricing(monkeypatch):
    free = {"prompt": "0", "completion": "0"}
    paid = {"prompt": "0.000001", "completion": "0.000002"}
    data = [
        {"id": "b-paid", "pricing": paid},
        {"id": "z-free", "pricing": free},
        {"id": "a-unknown"},
    ]
    _mock_http(monkeypatch, lambda request: httpx.Response(200, json={"data": data}))

    assert await list_models("key", "https://example.com/v1") == [
        ModelInfo("z-free", True),
        ModelInfo("a-unknown", None),
        ModelInfo("b-paid", False),
    ]


@pytest.mark.asyncio
async def test_list_models_returns_empty_when_unsupported(monkeypatch):
    _mock_http(monkeypatch, lambda request: httpx.Response(404))

    assert await list_models("key", "https://example.com/v1/") == []


def _sse(*events: dict | str) -> bytes:
    lines = [e if isinstance(e, str) else json.dumps(e) for e in events]
    return "".join(f"data: {line}\n\n" for line in lines).encode()


@pytest.mark.asyncio
async def test_complete_streams_tokens_and_usage(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert body["stream"] is True and body["messages"][0]["role"] == "system"
        return httpx.Response(
            200,
            content=_sse(
                {"choices": [{"delta": {"content": "Hel"}}]},
                {"choices": [{"delta": {"content": "lo"}}]},
                {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
                "[DONE]",
            ),
        )

    _mock_http(monkeypatch, handler)
    service = LlmService(_settings(GROQ_API_KEY="k"), [_credential("OTHER", "https://x/")])
    seen: list[str] = []

    async def on_token(token: str) -> None:
        seen.append(token)

    text, usage, metrics = await service.complete(
        [Message(session_id="s", role="user", content="hi")], "sys", on_token
    )

    assert text == "Hello" and seen == ["Hel", "lo"]
    assert (usage.prompt_tokens, usage.completion_tokens) == (3, 2)
    assert metrics.provider == "GROQ"


@pytest.mark.asyncio
async def test_complete_falls_back_on_rate_limit(monkeypatch):
    def handler(request):
        if "groq" in request.url.host:
            return httpx.Response(429, text="rate limit exceeded")
        return httpx.Response(200, content=_sse({"choices": [{"delta": {"content": "ok"}}]}))

    _mock_http(monkeypatch, handler)
    service = LlmService(_settings(GROQ_API_KEY="k", ZHIPU_API_KEY="z"))
    service.providers[1] = LlmProvider("ZHIPU", "z", "m", "https://zhipu.example/v1/")

    text, _, metrics = await service.complete([Message(session_id="s", role="user", content="hi")], "sys")

    assert text == "ok" and metrics.provider == "ZHIPU"


@pytest.mark.asyncio
async def test_complete_raises_exhausted_on_non_retryable_error(monkeypatch):
    _mock_http(monkeypatch, lambda request: httpx.Response(500, text="boom"))
    service = LlmService(_settings(GROQ_API_KEY="k"))

    with pytest.raises(ProvidersExhaustedError, match="500"):
        await service.complete([Message(session_id="s", role="user", content="hi")], "sys")
