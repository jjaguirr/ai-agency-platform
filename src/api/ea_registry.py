"""
Per-customer EA instance cache.

ExecutiveAssistant.__init__ is expensive — it connects to Redis, initialises
mem0, compiles the LangGraph, wires specialists. We build once per customer
per process and reuse.

Concurrency contract: two requests for the same customer arriving at the
same time while no EA is cached must result in ONE build, not two. We use
a per-customer asyncio.Lock around the build path (not a global lock —
different customers can build in parallel).
"""
import asyncio
from typing import Callable, Protocol


class _EALike(Protocol):
    customer_id: str
    async def handle_customer_interaction(self, *, message: str, **kw) -> str: ...


EAFactory = Callable[[str], _EALike]


class EARegistry:
    def __init__(self, *, factory: EAFactory):
        self._factory = factory
        self._instances: dict[str, _EALike] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # Guards creation of per-customer locks — cheap, no contention.
        self._locks_guard = asyncio.Lock()

    async def _lock_for(self, customer_id: str) -> asyncio.Lock:
        # Fast path: lock already exists
        if customer_id in self._locks:
            return self._locks[customer_id]
        async with self._locks_guard:
            # Re-check after acquiring guard (another task may have created it)
            if customer_id not in self._locks:
                self._locks[customer_id] = asyncio.Lock()
            return self._locks[customer_id]

    async def get(self, customer_id: str) -> _EALike:
        # Fast path: already built
        if customer_id in self._instances:
            return self._instances[customer_id]

        lock = await self._lock_for(customer_id)
        async with lock:
            # Double-check: another task may have built while we waited
            if customer_id in self._instances:
                return self._instances[customer_id]
            # Factory is sync (EA.__init__ does blocking I/O internally).
            # For now, call directly; if this becomes a latency problem
            # push to an executor.
            ea = self._factory(customer_id)
            self._instances[customer_id] = ea
            return ea

    def clear(self, customer_id: str) -> None:
        """Evict a cached EA (e.g. on customer config change)."""
        self._instances.pop(customer_id, None)

    def __contains__(self, customer_id: str) -> bool:
        return customer_id in self._instances
