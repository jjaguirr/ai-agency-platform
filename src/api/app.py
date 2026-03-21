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
from .routes import (
    audit, auth_login, conversations, health, history, notifications,
    provisioning, settings, webhooks, workflows,
)

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
    safety_pipeline: Optional[Any] = None,
    safety_config: Optional[Any] = None,
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
    # Safety pipeline is optional — pre-safety tests construct apps
    # without one and the conversation/webhook routes guard for None.
    # safety_config is separate: it gates the rate-limit middleware
    # below, which is an independent concern from input/output scanning.
    app.state.safety_pipeline = safety_pipeline

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

    # Rate limiter — pure ASGI, added after CorrelationMiddleware so it
    # runs *outermost* (Starlette builds the stack in reverse add order).
    # An unauthenticated flood should hit the global bucket before any
    # correlation-ID allocation or auth parsing. Gated on safety_config
    # rather than safety_pipeline because the limiter is independent of
    # the scan pipeline: tests that want rate limiting pass a config +
    # real-ish redis; tests that don't omit the config and never throttle.
    if safety_config is not None:
        from src.safety.rate_limiter import RateLimitMiddleware
        app.add_middleware(
            RateLimitMiddleware,
            redis_client=redis_client,
            config=safety_config,
        )

    # Routers
    app.include_router(health.router)
    app.include_router(conversations.router)
    app.include_router(history.router)
    app.include_router(provisioning.router)
    app.include_router(webhooks.router)
    app.include_router(notifications.router)
    app.include_router(auth_login.router)
    app.include_router(settings.router)
    app.include_router(workflows.router)
    app.include_router(audit.router)

    # Dashboard static assets at / — mounted AFTER routers so /v1/*
    # resolves to API handlers before StaticFiles' catch-all kicks in.
    # Conditional on the build existing: tests and API-only deploys
    # don't ship dashboard/dist.
    _mount_dashboard(app)

    return app


def _mount_dashboard(app: FastAPI) -> None:
    import pathlib
    from fastapi.staticfiles import StaticFiles

    dist = pathlib.Path(__file__).resolve().parents[2] / "dashboard" / "dist"
    if not dist.is_dir():
        logger.debug("dashboard/dist not found at %s; skipping static mount", dist)
        return

    # html=True serves index.html for directory requests. The dashboard
    # uses hash-based routing so all client-side routes resolve to /
    # and we don't need SPA history-mode fallback.
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="dashboard")


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

    # --- Safety layer ---
    # Built before the EA registry so the factory can hand each new EA
    # the same AuditLogger instance for confirmation-event logging.
    from src.safety.audit import AuditLogger
    from src.safety.config import SafetyConfig
    from src.safety.pipeline import SafetyPipeline

    safety_cfg = SafetyConfig.from_env()
    audit_logger = AuditLogger(redis_client, max_events=safety_cfg.audit_max_events)
    safety_pipeline = SafetyPipeline(safety_cfg, audit_logger)

    # --- EA registry ---
    # Size-bound caps worst-case EA memory at max × sizeof(one EA).
    # 128 is a reasonable per-worker default; scale horizontally or
    # raise this after profiling if you see thrash (evictions logged
    # at INFO). Env-configurable so ops don't need a code change.
    import os as _os
    ea_max = int(_os.environ.get("EA_REGISTRY_MAX_SIZE", "128"))

    def _ea_factory(cid: str) -> ExecutiveAssistant:
        ea = ExecutiveAssistant(customer_id=cid)
        # audit_logger is optional on the EA; when present,
        # NEEDS_CONFIRMATION lifecycle events land in the same
        # Redis trail as the pipeline's injection/redaction events.
        ea.audit_logger = audit_logger
        return ea

    ea_registry = EARegistry(factory=_ea_factory, max_size=ea_max)

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
    from src.proactive.settings_cache import CustomerSettingsCache
    from src.workflows.store import WorkflowStore

    proactive_store = ProactiveStateStore(redis_client)
    noise_gate = NoiseGate(proactive_store)
    dispatcher = DefaultOutboundDispatcher(wa_manager, proactive_store)
    settings_cache = CustomerSettingsCache(redis_client)
    workflow_store = WorkflowStore(redis_client)
    heartbeat = HeartbeatDaemon(
        ea_registry, proactive_store, noise_gate, dispatcher,
        settings_cache=settings_cache,
    )
    heartbeat.set_workflow_store(workflow_store)

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
        safety_pipeline=safety_pipeline,
        safety_config=safety_cfg,
        lifespan=lifespan,
    )
