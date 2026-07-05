import aiosqlite
import pytest

from app.core.database import _SCHEMA
from app.repositories.provider_repository import ProviderRepository


@pytest.fixture
async def connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


@pytest.mark.asyncio
async def test_upsert_creates_new_credential(connection):
    repo = ProviderRepository(connection)

    credential = await repo.upsert(
        "GROQ", "key-1", "llama-3.3-70b-versatile", "https://api.groq.com/openai/v1/"
    )

    assert credential.name == "GROQ"
    assert credential.api_key == "key-1"


@pytest.mark.asyncio
async def test_upsert_updates_existing_credential(connection):
    repo = ProviderRepository(connection)
    await repo.upsert("GROQ", "key-1", "model-a", "https://a.example/")

    updated = await repo.upsert("GROQ", "key-2", "model-b", "https://b.example/")

    assert updated.api_key == "key-2"
    assert updated.model == "model-b"
    all_rows = await repo.list()
    assert len(all_rows) == 1


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(connection):
    repo = ProviderRepository(connection)
    assert await repo.get("MISSING") is None


@pytest.mark.asyncio
async def test_list_returns_all_credentials_sorted_by_name(connection):
    repo = ProviderRepository(connection)
    await repo.upsert("ZHIPU", "key-z", "glm-4.7-flash", "https://z.example/")
    await repo.upsert("GROQ", "key-g", "llama", "https://g.example/")

    names = [c.name for c in await repo.list()]

    assert names == ["GROQ", "ZHIPU"]


@pytest.mark.asyncio
async def test_delete_removes_credential(connection):
    repo = ProviderRepository(connection)
    await repo.upsert("GROQ", "key-1", "model-a", "https://a.example/")

    await repo.delete("GROQ")

    assert await repo.get("GROQ") is None
