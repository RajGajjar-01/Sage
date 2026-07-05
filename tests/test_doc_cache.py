import asyncio

import aiosqlite
import pytest

from app.core.database import _SCHEMA
from app.services.doc_cache import DocCache


@pytest.fixture
async def connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


@pytest.mark.asyncio
async def test_get_returns_none_when_missing(connection):
    cache = DocCache(connection)
    assert await cache.get("tavily", "fastapi auth") is None


@pytest.mark.asyncio
async def test_set_then_get_returns_cached_value(connection):
    cache = DocCache(connection)
    await cache.set("tavily", "fastapi auth", "some search results")

    assert await cache.get("tavily", "fastapi auth") == "some search results"


@pytest.mark.asyncio
async def test_get_is_case_and_whitespace_insensitive(connection):
    cache = DocCache(connection)
    await cache.set("tavily", "  Fastapi Auth  ", "results")

    assert await cache.get("tavily", "fastapi auth") == "results"


@pytest.mark.asyncio
async def test_set_overwrites_existing_entry(connection):
    cache = DocCache(connection)
    await cache.set("tavily", "query", "first")
    await cache.set("tavily", "query", "second")

    assert await cache.get("tavily", "query") == "second"


@pytest.mark.asyncio
async def test_expired_entry_is_deleted_and_returns_none(connection):
    cache = DocCache(connection)
    await cache.set("tavily", "query", "stale", ttl_hours=0)

    await asyncio.sleep(1.1)
    assert await cache.get("tavily", "query") is None
