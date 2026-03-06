"""
Shared API dependencies.

The EA pool is the main piece: per-customer instance caching with safe
concurrent creation. FastAPI dependency functions extract wired objects
from app.state so routes don't reach into global module state.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import Request

# --- EA pool ---------------------------------------------------------------


class EAPool:
    """
    Per-customer ExecutiveAssistant cache.

    The EA is expensive to construct (initializes langchain graph, memory
    clients, LLM) and is designed to be reused across requests for the same
    customer. One instance per customer, for the process lifetime.

    Concurrency model: single lock for the creation path. The fast path
    (instance already cached) is lock-free. The slow path acquires the lock,
    re-checks the cache (another coroutine may have finished creating while
    we waited), then constructs if still missing.

    A single lock serializes creation across all customers. This is acceptable
    because (a) creation is sync and brief relative to request handling, and
    (b) it only happens once per customer per process. Per-customer locks
    would add bookkeeping overhead for a race that's rare in practice.

    Failed construction is not cached — the next request retries.
    """

    def __init__(self, ea_factory: Callable[[str], Any] | None = None):
        # Lazy default: only import ExecutiveAssistant if no factory is
        # injected. Keeps API tests fast (no langchain/openai import cascade).
        if ea_factory is None:
            from src.agents.executive_assistant import ExecutiveAssistant
            ea_factory = ExecutiveAssistant

        self._factory = ea_factory
        self._instances: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def get(self, customer_id: str) -> Any:
        # Fast path: already cached, no lock needed.
        existing = self._instances.get(customer_id)
        if existing is not None:
            return existing

        # Slow path: serialize creation.
        async with self._lock:
            # Re-check: someone else may have created it while we waited.
            existing = self._instances.get(customer_id)
            if existing is not None:
                return existing

            # Factory may raise — only cache on success.
            instance = self._factory(customer_id)
            self._instances[customer_id] = instance
            return instance

    def size(self) -> int:
        return len(self._instances)


# --- FastAPI dependency accessors -----------------------------------------


def get_ea_pool(request: Request) -> EAPool:
    return request.app.state.ea_pool


def get_orchestrator(request: Request) -> Any:
    return request.app.state.orchestrator


def get_whatsapp_manager(request: Request) -> Any:
    return request.app.state.whatsapp_manager
