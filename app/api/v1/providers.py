from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import get_llm_service, get_provider_repository
from app.core.response import error_response, success_response
from app.repositories.provider_repository import ProviderRepository
from app.schemas.providers import ConnectProviderRequest, SwitchProviderRequest
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
    await llm.switch_provider(match)
    return success_response({"active": llm.active_provider.name})


@router.post("/connect", status_code=201)
async def connect_provider(
    body: ConnectProviderRequest,
    request: Request,
    providers: ProviderRepository = Depends(get_provider_repository),
) -> JSONResponse:
    credential = await providers.upsert(
        body.name, body.api_key, body.model, body.endpoint
    )

    llm: LlmService | None = request.app.state.llm
    if llm is None:
        request.app.state.llm = LlmService(settings, [credential])
    else:
        await llm.add_provider(credential)

    return success_response(
        {"name": credential.name, "model": credential.model}, status_code=201
    )
