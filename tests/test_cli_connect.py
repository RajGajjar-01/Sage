from unittest.mock import patch

import aiosqlite
import pytest
from rich.console import Console

from app.cli.connect import connect_provider
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


@pytest.mark.asyncio
async def test_connect_known_provider_uses_default_model_and_endpoint(providers):
    answers = iter(["GROQ", "my-api-key", "", ""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.name == "GROQ"
    assert credential.api_key == "my-api-key"
    assert credential.model == "llama-3.3-70b-versatile"
    assert credential.endpoint == "https://api.groq.com/openai/v1/"


@pytest.mark.asyncio
async def test_connect_persists_to_repository(providers):
    answers = iter(["ZHIPU", "key-123", "", ""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
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
async def test_connect_unknown_provider_requires_model_and_endpoint(providers):
    answers = iter(["CUSTOM", "key", "", ""])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is None


@pytest.mark.asyncio
async def test_connect_unknown_provider_with_model_and_endpoint_succeeds(providers):
    answers = iter(["CUSTOM", "key", "custom-model", "https://custom.example/v1/"])
    with patch("rich.prompt.Prompt.ask", side_effect=lambda *a, **k: next(answers)):
        credential = await connect_provider(_console(), providers)

    assert credential is not None
    assert credential.name == "CUSTOM"
    assert credential.model == "custom-model"
    assert credential.endpoint == "https://custom.example/v1/"
