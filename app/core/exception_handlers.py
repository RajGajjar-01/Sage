import sys
import traceback

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import error_response


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if isinstance(exc.detail, dict):
        return error_response(
            status_code=exc.status_code,
            title=exc.detail.get("title", str(exc.status_code)),
            detail=exc.detail.get("detail", str(exc.detail)),
            error_type=exc.detail.get("type", "about:blank"),
        )
    return error_response(
        status_code=exc.status_code, title=str(exc.status_code), detail=str(exc.detail)
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "type": "about:blank",
                "title": "VALIDATION_ERROR",
                "status": 422,
                "detail": "Request validation failed",
                "details": exc.errors(),
            },
            "meta": None,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    traceback.print_exc(file=sys.stderr)
    return error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        title="INTERNAL_ERROR",
        detail="Internal server error",
    )
