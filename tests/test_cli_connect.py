from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from app.cli.connect import (
    OTHER_PROVIDER,
    Choice,
    connect_provider,
    model_choices,
)
from app.core.database import _SCHEMA
from app.repositories.provider_repository import ProviderRepository
from app.services.llm_service import ModelInfo


@pytest.fixture
async def providers():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield ProviderRepository(conn)


def _scripted(picks: list[str | None], answers: list[str | None]):
    """Fake pick/ask callables that replay canned answers in order."""
    pick_iter, answer_iter = iter(picks), iter(answers)
    seen: list[list[Choice]] = []

    async def pick(title: str, choices: list[Choice]) -> str | None:
        seen.append(choices)
        return next(pick_iter)

    async def ask(
        title: str, *, password: bool = False, default: str = ""
    ) -> str | None:
        answer = next(answer_iter)
        return default if answer == "<default>" else answer

    return pick, ask, seen


def _models(*models: ModelInfo):
    return patch("app.cli.connect.list_models", AsyncMock(return_value=list(models)))


@pytest.mark.asyncio
async def test_connect_known_provider_falls_back_to_default_model(providers):
    pick, ask, _ = _scripted(["GROQ"], ["my-api-key", "<default>"])
    with _models():
        credential = await connect_provider(pick, ask, providers)

    assert credential is not None
    assert credential.name == "GROQ"
    assert credential.api_key == "my-api-key"
    assert credential.model == "llama-3.3-70b-versatile"
    assert credential.endpoint == "https://api.groq.com/openai/v1/"
    assert (await providers.get("GROQ")) is not None


@pytest.mark.asyncio
async def test_connect_picks_from_live_model_list(providers):
    pick, ask, seen = _scripted(["OPENROUTER", "b-paid"], ["my-api-key"])
    with _models(ModelInfo("a-free", True), ModelInfo("b-paid", False)):
        credential = await connect_provider(pick, ask, providers)

    assert credential is not None
    assert credential.endpoint == "https://openrouter.ai/api/v1"
    assert credential.model == "b-paid"
    assert [(c.value, c.section) for c in seen[1]] == [
        ("a-free", "Free"),
        ("b-paid", "Paid"),
    ]


@pytest.mark.parametrize(
    ("picks", "answers"),
    [
        ([None], []),  # esc on the provider list
        (["GROQ"], [""]),  # empty API key
        (["GROQ"], [None]),  # esc on the API key
        (["CLOUDFLARE"], ["key", ""]),  # missing Cloudflare account id
        ([OTHER_PROVIDER], ["CUSTOM", ""]),  # custom provider without endpoint
    ],
)
@pytest.mark.asyncio
async def test_connect_cancels_on_missing_answers(providers, picks, answers):
    pick, ask, _ = _scripted(picks, answers)
    with _models():
        assert await connect_provider(pick, ask, providers) is None


@pytest.mark.asyncio
async def test_connect_cancelled_on_model_list(providers):
    pick, ask, _ = _scripted(["GROQ", None], ["key"])
    with _models(ModelInfo("model-a")):
        assert await connect_provider(pick, ask, providers) is None


@pytest.mark.asyncio
async def test_connect_custom_provider(providers):
    pick, ask, _ = _scripted(
        [OTHER_PROVIDER],
        ["custom", "https://custom.example/v1/", "key", "custom-model"],
    )
    with _models():
        credential = await connect_provider(pick, ask, providers)

    assert credential is not None
    assert credential.name == "CUSTOM"
    assert credential.endpoint == "https://custom.example/v1/"
    assert credential.model == "custom-model"


@pytest.mark.asyncio
async def test_connect_cloudflare_builds_endpoint_from_account_id(providers):
    pick, ask, _ = _scripted(["CLOUDFLARE"], ["key", "acct-1", "<default>"])
    with _models():
        credential = await connect_provider(pick, ask, providers)

    assert credential is not None
    assert (
        credential.endpoint
        == "https://api.cloudflare.com/client/v4/accounts/acct-1/ai/v1"
    )
    assert credential.model == "@cf/meta/llama-3.1-8b-instruct"


def test_model_choices_sections_unknown_pricing_as_models():
    assert model_choices([ModelInfo("x")]) == [Choice("x", "x", section="Models")]
