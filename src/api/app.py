"""
FastAPI app factory.

Two entrypoints:
  create_app(...)         — dependency-injected, for tests and composition
  create_default_app()    — reads env, builds real deps, for `uvicorn src.api.app:app`
"""
import logging
from contextlib import AbstractAsyncContextManager
from typing import Any, Callable, Optional

from fastapi import FastAPI

from fastapi.exceptions import RequestValidationError

from .ea_registry import EARegistry
from .errors import (
    APIError,
    handle_api_error,
    handle_unexpected,
    handle_validation_error,
)
from .middleware import CorrelationMiddleware, install_correlation_logging
from .routes import conversations, health, history, notifications, provisioning, webhooks

logger = logging.getLogger(__name__)

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    *,
    ea_registry: EARegistry,
    orchestrator: Any,
    whatsapp_manager: Any,
    redis_client: Any,
    lifespan: Optional[Lifespan] = None,
) -> FastAPI:
    """
    Build the API with all dependencies injected.

    Dependencies are stored on app.state and pulled by route handlers via
    request.app.state.<dep>. No module-level singletons — keeps tests
    hermetic.

    `lifespan` is passed straight to FastAPI's constructor (the documented
    mechanism) rather than patching router internals after construction.
    Tests omit it; production supplies one that initialises the port
    allocator and closes Redis on shutdown.
    """
    app = FastAPI(
        title="AI Agency Platform API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # State container — routes pull deps from here
    app.state.ea_registry = ea_registry
    app.state.orchestrator = orchestrator
    app.state.whatsapp_manager = whatsapp_manager
    app.state.redis_client = redis_client

    # Structured error handling. All paths converge on {type, detail}.
    # Order: specific-first so the Exception catch-all doesn't shadow
    # more precise matches (Starlette walks the MRO; Exception wins
    # if registered first and nothing narrower matches).
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(APIError, handle_api_error)
    app.add_exception_handler(Exception, handle_unexpected)

    # Request correlation — ASGI middleware + log-record factory
    app.add_middleware(CorrelationMiddleware)
    install_correlation_logging()

    # Routers
    app.include_router(health.router)
    app.include_router(conversations.router)
    app.include_router(history.router)
    app.include_router(notifications.router)
    app.include_router(provisioning.router)
    app.include_router(webhooks.router)

    return app


def create_default_app() -> FastAPI:  # pragma: no cover
    """
    Production entrypoint. Reads env config, builds real dependencies.

    Used by: `uvicorn src.api.app:create_default_app --factory`

    Deliberately NOT called at import time — building the orchestrator
    touches Docker, the port allocator touches Redis/Postgres, and
    ExecutiveAssistant connects to mem0. None of that should happen
    because someone imported this module.
    """
    from contextlib import asynccontextmanager

    import redis.asyncio as aioredis

    from src.agents.executive_assistant import ExecutiveAssistant
    from src.communication.whatsapp import WhatsAppConfig
    from src.communication.whatsapp_manager import WhatsAppManager
    from src.infrastructure.infrastructure_orchestrator import InfrastructureOrchestrator
    from src.infrastructure.port_allocator import create_port_allocator
    from src.utils.config import RedisConfig

    # --- Redis ---
    redis_cfg = RedisConfig.from_env()
    redis_client = aioredis.from_url(redis_cfg.url)

    # --- EA registry ---
    # Size-bound caps worst-case EA memory at max × sizeof(one EA).
    # 128 is a reasonable per-worker default; scale horizontally or
    # raise this after profiling if you see thrash (evictions logged
    # at INFO). Env-configurable so ops don't need a code change.
    import os as _os
    ea_max = int(_os.environ.get("EA_REGISTRY_MAX_SIZE", "128"))
    ea_registry = EARegistry(
        factory=lambda cid: ExecutiveAssistant(customer_id=cid),
        max_size=ea_max,
    )

    # --- WhatsApp manager ---
    wa_manager = WhatsAppManager()
    default_wa_cfg = WhatsAppConfig.from_env()
    if default_wa_cfg.from_number and default_wa_cfg.credentials.get("account_sid"):
        wa_manager.register_customer("default", default_wa_cfg)

    # --- Orchestrator ---
    # Port allocator needs async init. We construct it bare and run
    # initialize() inside the FastAPI lifespan so it happens under the
    # server's event loop, not at import time.
    from src.infrastructure.port_allocator import PortAllocator
    allocator = PortAllocator()
    orchestrator = InfrastructureOrchestrator(port_allocator=allocator)

    # --- Proactive heartbeat ---
    # One daemon per process, ticking over every cached EA. No external
    # scheduler — it rides the FastAPI event loop via lifespan.
    from src.agents.proactive.engine import ProactiveEngine
    from src.agents.proactive.gate import NoiseGate, ProactivePrefs
    from src.agents.proactive.heartbeat import HeartbeatDaemon
    from src.agents.proactive.outbound import OutboundRouter
    from src.agents.proactive.state import ProactiveStateStore
    from src.agents.proactive.triggers import Priority
    from datetime import datetime, timezone

    _clock = lambda: datetime.now(timezone.utc)
    _store = ProactiveStateStore(redis=redis_client, clock=_clock)
    _gate = NoiseGate(_store, clock=_clock)
    _router = OutboundRouter(whatsapp_manager=wa_manager, state_store=_store)
    _engine = ProactiveEngine(state_store=_store, gate=_gate,
                              router=_router, clock=_clock)

    # Platform-wide fallback prefs. Real per-customer prefs would come
    # from a settings store keyed on customer_id — today there's one
    # dial set for everyone. The hook point is the check_fn closure.
    _default_prefs = ProactivePrefs(
        timezone="UTC", min_priority=Priority.MEDIUM,
        quiet_start_hour=22, quiet_end_hour=7,
        daily_cap=5, cooldown_hours=24,
    )

    async def _check(customer_id: str) -> None:
        ea = await ea_registry.get(customer_id)
        ctx = getattr(ea, "business_context", None)
        specs = list(getattr(
            getattr(ea, "delegation_registry", None), "_specialists", {}
        ).values())
        await _engine.check_customer(customer_id, ctx,
                                     specialists=specs, prefs=_default_prefs)

    heartbeat = HeartbeatDaemon(ea_registry=ea_registry, check_fn=_check)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            await allocator.initialize()
        except Exception:
            logger.exception("Port allocator init failed; provisioning will degrade")
        await heartbeat.start()
        yield
        await heartbeat.stop()
        await redis_client.aclose()

    return create_app(
        ea_registry=ea_registry,
        orchestrator=orchestrator,
        whatsapp_manager=wa_manager,
        redis_client=redis_client,
        lifespan=lifespan,
    )
