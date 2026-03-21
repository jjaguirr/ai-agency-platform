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
    conversation_repo: Optional[Any] = None,
    lifespan: Optional[Lifespan] = None,
    proactive_state_store: Any = None,
) -> FastAPI:
    """
    Build the API with all dependencies injected.

    Dependencies are stored on app.state and pulled by route handlers via
    request.app.state.<dep>. No module-level singletons — keeps tests
    hermetic.

    `conversation_repo` is Optional so pre-storage tests (webhooks,
    provisioning, errors) don't need to construct one. Routes that
    require it check for None and degrade to in-memory behaviour or
    skip the persistence side effect. Production always supplies one.

    `lifespan` is passed straight to FastAPI's constructor (the documented
    mechanism) rather than patching router internals after construction.
    Tests omit it; production supplies one that initialises the port
    allocator, verifies conversation tables exist, and closes Redis +
    Postgres on shutdown.
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
    app.state.conversation_repo = conversation_repo
    app.state.proactive_state_store = proactive_state_store

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
    app.include_router(provisioning.router)
    app.include_router(webhooks.router)
    app.include_router(notifications.router)

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

    import asyncpg
    import redis.asyncio as aioredis

    from src.agents.executive_assistant import ExecutiveAssistant
    from src.communication.whatsapp import WhatsAppConfig
    from src.communication.whatsapp_manager import WhatsAppManager
    from src.database.conversation_repository import (
        ConversationRepository, SchemaNotReadyError,
    )
    from src.infrastructure.infrastructure_orchestrator import InfrastructureOrchestrator
    from src.infrastructure.port_allocator import create_port_allocator
    from src.utils.config import DatabaseConfig, RedisConfig

    # --- Redis ---
    redis_cfg = RedisConfig.from_env()
    redis_client = aioredis.from_url(redis_cfg.url)

    # --- Postgres (conversation storage) ---
    db_cfg = DatabaseConfig.from_env()

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

    # Pool is created inside the lifespan — asyncpg needs a running
    # event loop. Stash it in a one-slot list so the shutdown branch
    # can close what the startup branch opened.
    pg_pool_box: list[asyncpg.Pool] = []

    # --- Proactive intelligence ---
    from src.proactive.state import ProactiveStateStore
    from src.proactive.gate import NoiseGate
    from src.proactive.heartbeat import HeartbeatDaemon, DefaultOutboundDispatcher

    proactive_store = ProactiveStateStore(redis_client)
    noise_gate = NoiseGate(proactive_store)
    dispatcher = DefaultOutboundDispatcher(wa_manager, proactive_store)
    heartbeat = HeartbeatDaemon(
        ea_registry, proactive_store, noise_gate, dispatcher,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Postgres pool + schema check. A missing table is fatal: the
        # API can't serve /v1/conversations without it, and silently
        # dropping messages is worse than refusing to start.
        pool = await asyncpg.create_pool(db_cfg.url, min_size=2, max_size=10)
        pg_pool_box.append(pool)
        repo = ConversationRepository(pool)
        try:
            await repo.check_schema()
        except SchemaNotReadyError as e:
            await pool.close()
            raise RuntimeError(
                f"Conversation storage not ready: {e}"
            ) from e
        _app.state.conversation_repo = repo

        try:
            await allocator.initialize()
        except Exception:
            logger.exception("Port allocator init failed; provisioning will degrade")

        try:
            await heartbeat.start()
            _app.state.heartbeat = heartbeat
        except Exception:
            logger.exception("Heartbeat daemon failed to start; proactive features disabled")

        yield

        await heartbeat.stop()
        await redis_client.aclose()
        if pg_pool_box:
            await pg_pool_box[0].close()

    return create_app(
        ea_registry=ea_registry,
        orchestrator=orchestrator,
        whatsapp_manager=wa_manager,
        redis_client=redis_client,
        # Placeholder — lifespan swaps in the real repo once the pool
        # is up. Routes tolerate None during the startup window.
        conversation_repo=None,
        proactive_state_store=proactive_store,
        lifespan=lifespan,
    )
