from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.response import success_response

app = FastAPI(title="DotAgent")


@app.get("/live")
async def liveness() -> JSONResponse:
    return success_response({"status": "alive"})
