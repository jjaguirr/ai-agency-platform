"""
Lightweight dev server for dashboard development.

Only needs Redis (no Postgres, Docker, mem0, etc.).
Stubs out orchestrator and WhatsApp so the dashboard endpoints work.

Usage:
    uv run python scripts/dev_server.py
"""
import os
import sys

# Ensure JWT_SECRET is set
os.environ.setdefault(
    "JWT_SECRET", "dev-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import asyncio
import logging
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI

from src.api.app import create_app
from src.api.ea_registry import EARegistry
from src.proactive.state import ProactiveStateStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger("dev_server")


def main():
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = aioredis.from_url(redis_url)
    proactive_store = ProactiveStateStore(redis_client)

    ea = AsyncMock()
    ea.customer_id = "dev"
    ea.handle_customer_interaction = AsyncMock(return_value="(dev stub)")

    ea_registry = EARegistry(
        factory=lambda cid: AsyncMock(
            customer_id=cid,
            handle_customer_interaction=AsyncMock(return_value="(dev stub)"),
        ),
        max_size=16,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("Dev server starting — Redis only, no Postgres/Docker/mem0")
        yield
        await redis_client.aclose()

    app = create_app(
        ea_registry=ea_registry,
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=redis_client,
        proactive_state_store=proactive_store,
        lifespan=lifespan,
    )

    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
