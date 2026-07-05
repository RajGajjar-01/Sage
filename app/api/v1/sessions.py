from dataclasses import asdict
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.dependencies import get_message_repository, get_session_repository
from app.core.response import error_response, success_response
from app.repositories.message_repository import MessageRepository
from app.repositories.session_repository import SessionRepository
from app.schemas.sessions import CreateSessionRequest

router = APIRouter(tags=["sessions"])


@router.get("")
async def list_sessions(
    limit: int = 20,
    sessions: SessionRepository = Depends(get_session_repository),
) -> JSONResponse:
    found = await sessions.list(limit=limit)
    return success_response([asdict(s) for s in found])


@router.post("", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    sessions: SessionRepository = Depends(get_session_repository),
) -> JSONResponse:
    title = body.title or f"Session {datetime.now():%b %d %H:%M}"
    session = await sessions.create(title)
    return success_response(asdict(session), status_code=201)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    sessions: SessionRepository = Depends(get_session_repository),
) -> JSONResponse:
    session = await sessions.get(session_id)
    if session is None:
        return error_response(
            404, "SESSION_NOT_FOUND", f"Session {session_id} not found"
        )
    return success_response(asdict(session))


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    sessions: SessionRepository = Depends(get_session_repository),
    messages: MessageRepository = Depends(get_message_repository),
) -> JSONResponse:
    session = await sessions.get(session_id)
    if session is None:
        return error_response(
            404, "SESSION_NOT_FOUND", f"Session {session_id} not found"
        )
    found = await messages.list_by_session(session_id)
    return success_response([asdict(m) for m in found])
