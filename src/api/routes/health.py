"""
Liveness + readiness probes.

/healthz — load-balancer liveness check. Always 200 if process is running.
/readyz  — orchestrator readiness check. 503 if any dependency is down.
"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..schemas import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request):
    checks: dict[str, str] = {}
    ready = True

    # --- Redis ping ---
    redis_client = request.app.state.redis_client
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"
        ready = False

    # --- EA importable ---
    # We're already importing it at process startup (app factory pulls it
    # in), so by the time a request arrives this is essentially tautological.
    # But it gives a named check in the response, which operators like.
    try:
        from src.agents.executive_assistant import ExecutiveAssistant  # noqa: F401
        checks["ea"] = "ok"
    except Exception as e:
        checks["ea"] = f"error: {type(e).__name__}"
        ready = False

    body = ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks=checks,
    )
    status_code = 200 if ready else 503
    return JSONResponse(status_code=status_code, content=body.model_dump())
