import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.response import success_response

router = APIRouter(tags=["health"])


@router.get("/live")
async def liveness() -> JSONResponse:
    return success_response({"status": "alive"})


@router.get("/health")
async def readiness(request: Request) -> JSONResponse:
    try:
        async with asyncio.timeout(3):
            await request.app.state.db.execute("SELECT 1")
    except Exception:
        return success_response(
            {"status": "unhealthy", "checks": {"database": "unhealthy"}},
            status_code=503,
        )
    return success_response({"status": "healthy", "checks": {"database": "healthy"}})
