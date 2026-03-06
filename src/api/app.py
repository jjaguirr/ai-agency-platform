"""
FastAPI application factory.

All dependencies (EA pool, Redis, orchestrator, WhatsApp manager, JWT secret)
are injected. Production defaults come from the environment; tests pass mocks.
Everything lives on `app.state` so route handlers can reach it via FastAPI
dependencies without module-level globals.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from .dependencies import EAPool
from .errors import register_exception_handlers
from .routes import conversations, health, provisioning, webhooks


def create_app(
    *,
    ea_pool: EAPool | None = None,
    redis_client: Any = None,
    orchestrator: Any = None,
    whatsapp_manager: Any = None,
    jwt_secret: str | None = None,
) -> FastAPI:
    """
    Build the API app with injected dependencies.

    Any unset dependency is left as None on app.state — endpoints that need
    it will fail at call time, not import time. This lets tests wire only
    what they exercise (e.g. health tests don't need an orchestrator).
    """
    app = FastAPI(
        title="AI Agency Platform API",
        version="0.1.0",
    )

    app.state.ea_pool = ea_pool or EAPool()
    app.state.redis = redis_client
    app.state.orchestrator = orchestrator
    app.state.whatsapp_manager = whatsapp_manager
    app.state.jwt_secret = jwt_secret or os.environ.get(
        "API_JWT_SECRET", "dev-secret-change-me"
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(conversations.router)
    app.include_router(provisioning.router)
    app.include_router(webhooks.router)

    return app


# --- Production entrypoint -------------------------------------------------
#
# `uvicorn src.api.app:app` resolves `app` via PEP 562 __getattr__ below.
# The name is deliberately NOT bound at module scope — __getattr__ only fires
# for missing attributes, and we want the heavy default wiring (EA import
# chain, redis client) to happen lazily so `from src.api.app import create_app`
# in tests stays fast.

_app_cache: FastAPI | None = None


def _build_default_app() -> FastAPI:
    import redis.asyncio as aioredis

    from src.communication.whatsapp_manager import WhatsAppManager

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    return create_app(
        redis_client=redis_client,
        whatsapp_manager=WhatsAppManager(),
    )


def __getattr__(name: str) -> Any:
    if name == "app":
        global _app_cache
        if _app_cache is None:
            _app_cache = _build_default_app()
        return _app_cache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
