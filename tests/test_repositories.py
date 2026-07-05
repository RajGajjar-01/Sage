import aiosqlite
import pytest

from app.core.database import _SCHEMA
from app.models.agent import Execution, Message
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import SessionRepository


@pytest.fixture
async def connection():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(_SCHEMA)
        await conn.commit()
        yield conn


@pytest.mark.asyncio
async def test_session_create_and_list(connection):
    repo = SessionRepository(connection)
    session = await repo.create("My session")

    sessions = await repo.list()

    assert sessions == [session]


@pytest.mark.asyncio
async def test_session_get_missing_returns_none(connection):
    repo = SessionRepository(connection)
    assert await repo.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_session_update_status(connection):
    repo = SessionRepository(connection)
    session = await repo.create("My session")

    await repo.update_status(session.id, "completed")

    updated = await repo.get(session.id)
    assert updated is not None
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_message_save_and_list_by_session(connection):
    session_repo = SessionRepository(connection)
    message_repo = MessageRepository(connection)
    session = await session_repo.create("My session")

    saved = await message_repo.save(
        Message(session_id=session.id, role="user", content="hello")
    )

    assert saved.id is not None
    messages = await message_repo.list_by_session(session.id)
    assert [m.content for m in messages] == ["hello"]


@pytest.mark.asyncio
async def test_execution_save(connection):
    session_repo = SessionRepository(connection)
    execution_repo = ExecutionRepository(connection)
    session = await session_repo.create("My session")

    saved = await execution_repo.save(
        Execution(
            session_id=session.id,
            command="ls",
            output="a.txt",
            exit_code=0,
            duration_ms=12,
        )
    )

    assert saved.id is not None
