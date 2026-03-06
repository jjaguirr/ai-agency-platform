"""
Liveness and readiness probes.

Two separate endpoints with different contracts:

  /health — "is the process alive?"
    Used by: load balancers, container runtimes (restart policy)
    Checks:  nothing. If this handler runs, the process is up.
    Never:   touches Redis, databases, or the EA. A Redis outage must not
             cause a restart loop.

  /ready  — "should I receive traffic?"
    Used by: orchestrators (k8s readinessProbe, rolling deploys)
    Checks:  Redis ping. If downstream deps are unreachable, return 503 so
             the orchestrator stops routing new requests without killing us.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    failed: list[str] = []

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        failed.append("redis")
    else:
        try:
            await redis.ping()
        except Exception as e:
            # Log the real error for ops; don't echo it to the client.
            logger.warning("Readiness: redis ping failed: %s", e)
            failed.append("redis")

    if failed:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "failed": failed},
        )
    return JSONResponse(
        status_code=200,
        content={"status": "ready"},
    )
