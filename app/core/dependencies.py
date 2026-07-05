from collections.abc import AsyncGenerator

import aiosqlite
from fastapi import Depends, HTTPException, Request, status

from app.core.database import get_db
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.provider_repository import ProviderRepository
from app.repositories.session_repository import SessionRepository
from app.services.llm_service import LlmService


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


async def get_provider_repository(
    connection: aiosqlite.Connection = Depends(get_db),
) -> AsyncGenerator[ProviderRepository]:
    yield ProviderRepository(connection)


async def get_llm_service(request: Request) -> LlmService:
    llm: LlmService | None = request.app.state.llm
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "title": "NO_PROVIDER_CONFIGURED",
                "detail": "No LLM provider is configured on this server.",
                "type": "about:blank",
                "status": 503,
            },
        )
    return llm
