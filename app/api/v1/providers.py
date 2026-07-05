from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.dependencies import get_llm_service
from app.core.response import error_response, success_response
from app.schemas.providers import SwitchProviderRequest
from app.services.llm_service import LlmService

router = APIRouter(tags=["providers"])


@router.get("")
async def list_providers(llm: LlmService = Depends(get_llm_service)) -> JSONResponse:
    return success_response(
        {
            "active": llm.active_provider.name,
            "providers": [asdict(p) | {"api_key": "***"} for p in llm.providers],
        }
    )


@router.post("/switch")
async def switch_provider(
    body: SwitchProviderRequest,
    llm: LlmService = Depends(get_llm_service),
) -> JSONResponse:
    match = next((p for p in llm.providers if p.name == body.name), None)
    if match is None:
        return error_response(
            404, "PROVIDER_NOT_FOUND", f"Provider {body.name} is not configured"
        )
    llm.switch_provider(match)
    return success_response({"active": llm.active_provider.name})
