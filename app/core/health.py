import asyncio

import aiosqlite
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.response import success_response

router = APIRouter(tags=["health"])


async def _check_database(connection: aiosqlite.Connection) -> dict[str, object]:
    try:
        async with asyncio.timeout(3):
            await connection.execute("SELECT 1")
        return {"name": "database", "status": "healthy", "critical": True}
    except Exception as exc:
        return {
            "name": "database",
            "status": "unhealthy",
            "critical": True,
            "error": str(exc),
        }


@router.get("/live")
async def liveness() -> JSONResponse:
    return success_response({"status": "alive"})


@router.get("/health")
async def readiness(request: Request) -> JSONResponse:
    check = await _check_database(request.app.state.db)
    overall = "healthy" if check["status"] == "healthy" else "unhealthy"
    status_code = 200 if overall == "healthy" else 503
    return success_response(
        {"status": overall, "checks": {check["name"]: check["status"]}},
        status_code=status_code,
    )
