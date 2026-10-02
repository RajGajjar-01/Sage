from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from rich.console import Console

from app.cli.connect import _shortlist, connect_provider, pick_number
from app.core.database import _SCHEMA
from app.repositories.provider_repository import ProviderRepository


@pytest.fixture
async def providers():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield ProviderRepository(conn)


def _console() -> Console:
    return Console(quiet=True)


def _no_models():
    return patch("app.cli.connect.list_models", AsyncMock(return_value=[]))


@pytest.mark.asyncio
async def test_connect_known_provider_uses_default_model_and_endpoint(providers):
    answers = iter(["GROQ", "my-api-key", "", ""])
    with (
        _no_models(),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
    ):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.name == "GROQ"
    assert credential.api_key == "my-api-key"
    assert credential.model == "llama-3.3-70b-versatile"
    assert credential.endpoint == "https://api.groq.com/openai/v1/"


@pytest.mark.asyncio
async def test_connect_persists_to_repository(providers):
    answers = iter(["ZHIPU", "key-123", "", ""])
    with (
        _no_models(),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
    ):
        await connect_provider(_console(), providers)

    stored = await providers.get("ZHIPU")
    assert stored is not None
    assert stored.api_key == "key-123"


@pytest.mark.asyncio
async def test_connect_cancelled_with_empty_name_returns_none(providers):
    answers = iter([""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is None


@pytest.mark.asyncio
async def test_connect_rejects_empty_api_key(providers):
    answers = iter(["GROQ", ""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is None


@pytest.mark.asyncio
async def test_connect_unknown_provider_requires_endpoint(providers):
    answers = iter(["CUSTOM", "key", ""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is None


@pytest.mark.asyncio
async def test_connect_unknown_provider_with_model_and_endpoint_succeeds(providers):
    answers = iter(["CUSTOM", "key", "https://custom.example/v1/", "custom-model"])
    with (
        _no_models(),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
    ):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.name == "CUSTOM"
    assert credential.model == "custom-model"
    assert credential.endpoint == "https://custom.example/v1/"


@pytest.mark.asyncio
async def test_connect_lets_user_pick_from_live_model_list(providers):
    answers = iter(["GROQ", "my-api-key", ""])
    with (
        patch(
            "app.cli.connect.list_models",
            AsyncMock(return_value=["model-a", "model-b"]),
        ),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
        patch("rich.prompt.IntPrompt.ask", return_value=2),
    ):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.model == "model-b"


@pytest.mark.asyncio
async def test_connect_cancelled_by_zero_model_pick(providers):
    answers = iter(["GROQ", "my-api-key", ""])
    with (
        patch("app.cli.connect.list_models", AsyncMock(return_value=["model-a"])),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
        patch("rich.prompt.IntPrompt.ask", return_value=0),
    ):
        credential = await connect_provider(_console(), providers)

    assert credential is None


@pytest.mark.asyncio
async def test_connect_cloudflare_builds_endpoint_from_account_id(providers):
    answers = iter(["CLOUDFLARE", "my-api-key", "my-account-id", "", ""])
    with (
        _no_models(),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
    ):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.name == "CLOUDFLARE"
    assert (
        credential.endpoint
        == "https://api.cloudflare.com/client/v4/accounts/my-account-id/ai/v1"
    )
    assert credential.model == "@cf/meta/llama-3.1-8b-instruct"


@pytest.mark.asyncio
async def test_connect_cloudflare_requires_account_id(providers):
    answers = iter(["CLOUDFLARE", "my-api-key", ""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is None


def test_pick_number_only_accepts_zero_through_count():
    with patch("rich.prompt.IntPrompt.ask", return_value=2) as ask:
        assert pick_number(_console(), "pick", 3) == 2

    assert ask.call_args.kwargs["choices"] == ["0", "1", "2", "3"]


@pytest.mark.asyncio
async def test_connect_openrouter_uses_default_endpoint(providers):
    answers = iter(["OPENROUTER", "my-api-key", "", "openai/gpt-4o-mini"])
    with (
        _no_models(),
        patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)),
    ):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.endpoint == "https://openrouter.ai/api/v1"
    assert credential.model == "openai/gpt-4o-mini"


def test_shortlist_filters_a_large_catalogue():
    models = [f"vendor/model-{i}" for i in range(400)] + ["openai/gpt-4o-mini"]

    with patch("rich.prompt.Prompt.ask", return_value="gpt-4o"):
        shortlisted = _shortlist(_console(), models)

    assert shortlisted == ["openai/gpt-4o-mini"]


def test_shortlist_caps_when_filter_is_skipped():
    models = [f"vendor/model-{i}" for i in range(400)]

    with patch("rich.prompt.Prompt.ask", return_value=""):
        shortlisted = _shortlist(_console(), models)

    assert len(shortlisted) == 30


def test_shortlist_leaves_a_small_catalogue_alone():
    models = ["a", "b", "c"]
    assert _shortlist(_console(), models) == models
