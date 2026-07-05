from typing import Any

from fastapi.responses import JSONResponse


def success_response(data: Any, meta: Any = None, status_code: int = 200) -> JSONResponse:
    """Wrap successful endpoint output in the {data, meta} envelope."""
    return JSONResponse(status_code=status_code, content={"data": data, "meta": meta})


def error_response(status_code: int, title: str, detail: str, error_type: str = "about:blank") -> JSONResponse:
    """Wrap a failure in the {error, meta} envelope."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"type": error_type, "title": title, "status": status_code, "detail": detail},
            "meta": None,
        },
    )
