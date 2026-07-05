from collections.abc import AsyncGenerator

import aiosqlite
from fastapi import Depends

from app.core.database import get_db
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import SessionRepository


async def get_session_repository(
    connection: aiosqlite.Connection = Depends(get_db),
) -> AsyncGenerator[SessionRepository]:
    yield SessionRepository(connection)


async def get_message_repository(
    connection: aiosqlite.Connection = Depends(get_db),
) -> AsyncGenerator[MessageRepository]:
    yield MessageRepository(connection)


async def get_execution_repository(
    connection: aiosqlite.Connection = Depends(get_db),
) -> AsyncGenerator[ExecutionRepository]:
    yield ExecutionRepository(connection)
