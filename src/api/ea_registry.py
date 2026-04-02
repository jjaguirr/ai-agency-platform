"""
Per-customer EA instance cache with LRU eviction.

ExecutiveAssistant.__init__ is expensive — it connects to Redis, compiles
the LangGraph, wires specialists. We build once per customer per process
and reuse.

Concurrency contract: two requests for the same customer arriving at the
same time while no EA is cached must result in ONE build, not two. We use
a per-customer asyncio.Lock around the build path (not a global lock —
different customers can build in parallel).

Memory bound: size-capped LRU. Without this, a long tail of occasional
customers accumulates forever — each EA holds open Redis connections,
a compiled LangGraph, specialist wiring. Under the default
cap a worker's EA memory is deterministically bounded at
max_size × sizeof(one EA). Eviction happens synchronously on insert; no
background sweeper, no extra failure modes.

Known limitation: ExecutiveAssistant has no close()/shutdown(). Evicted
instances orphan their connections until GC. Fixing that requires
modifying EA — out of scope for the API layer.
"""
import asyncio
import logging
from collections import OrderedDict
from typing import Callable, Optional, Protocol

logger = logging.getLogger(__name__)


class _EALike(Protocol):
    customer_id: str
    async def handle_customer_interaction(self, *, message: str, **kw) -> str: ...


EAFactory = Callable[[str], _EALike]


class EARegistry:
    def __init__(self, *, factory: EAFactory, max_size: Optional[int] = None):
        """
        max_size: cap on cached EA instances. When a miss would push
          past this, the least-recently-used entry is evicted. None
          means unbounded (legacy behaviour — only safe for tests).
          Production callers MUST set this.
        """
        if max_size is not None and max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._factory = factory
        self._max_size = max_size
        self._post_create_hook: Optional[Callable[[_EALike], None]] = None
        # OrderedDict gives O(1) move_to_end + popitem — the two LRU
        # primitives. Iteration order = insertion/access order; rightmost
        # is MRU, leftmost is LRU (eviction victim).
        self._instances: OrderedDict[str, _EALike] = OrderedDict()
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

    def _touch(self, customer_id: str) -> None:
        # Mark as most-recently-used. No await between the `in` check
        # and this call in either fast or slow path, so the key is
        # guaranteed present (asyncio tasks don't preempt between
        # non-await statements).
        self._instances.move_to_end(customer_id)

    def _evict_if_full(self) -> None:
        # Called under the build lock, right before insert. No await
        # between this and the insert, so the size check is stable.
        if self._max_size is None:
            return
        while len(self._instances) >= self._max_size:
            evicted_cid, _ = self._instances.popitem(last=False)
            # EA has no close() — we just drop the reference. Its Redis
            # connection will close when GC collects it. Log
            # so thrash is visible if max_size is tuned too low.
            logger.info("EA registry evicted customer=%s (LRU, cap=%d)",
                        evicted_cid, self._max_size)

    async def get(self, customer_id: str) -> _EALike:
        # Fast path: already built. move_to_end is O(1) and there's no
        # await between the membership check and the touch — atomic
        # from asyncio's perspective.
        if customer_id in self._instances:
            self._touch(customer_id)
            return self._instances[customer_id]

        lock = await self._lock_for(customer_id)
        async with lock:
            # Double-check: another task may have built while we waited
            if customer_id in self._instances:
                self._touch(customer_id)
                return self._instances[customer_id]
            # Factory is sync and does blocking I/O (EA.__init__ connects
            # to Redis, compiles LangGraph). Run it off-loop so a
            # slow build for customer A doesn't stall requests for B.
            loop = asyncio.get_running_loop()
            ea = await loop.run_in_executor(None, self._factory, customer_id)
            if self._post_create_hook is not None:
                self._post_create_hook(ea)
            # Evict-then-insert, both synchronous: no window for a
            # concurrent task to observe an over-cap dict.
            self._evict_if_full()
            self._instances[customer_id] = ea
            return ea

    def set_post_create_hook(self, hook: Callable[[_EALike], None]) -> None:
        """Register a callback invoked on every newly-built EA."""
        self._post_create_hook = hook

    def clear(self, customer_id: str) -> None:
        """Evict a cached EA (e.g. on customer config change)."""
        self._instances.pop(customer_id, None)

    def active_customer_ids(self) -> list[str]:
        """Snapshot of currently cached customer IDs for heartbeat iteration."""
        return list(self._instances.keys())

    def __contains__(self, customer_id: str) -> bool:
        return customer_id in self._instances

    def __len__(self) -> int:
        return len(self._instances)
