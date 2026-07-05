from fastapi import APIRouter

from app.api.v1.providers import router as providers_router
from app.api.v1.sessions import router as sessions_router

router = APIRouter(prefix="/api/v1")
router.include_router(sessions_router, prefix="/sessions")
router.include_router(providers_router, prefix="/providers")
