"""
HeartbeatDaemon — the asyncio background task that drives proactive checks.

Lives inside the FastAPI process: started from the app's lifespan
startup, stopped from its shutdown. No external scheduler, no Celery,
no crontab. The event loop is already running; we just hang one more
task off it.

Shape:
  • start()      — spawn the tick loop as a background task
  • stop()       — cancel the loop task and await it (clean shutdown)
  • tick_once()  — run one tick directly (test hook; the loop calls this)

One tick fans out over every active customer in the EA registry. Each
customer's check runs as an independent task under a timeout — a hung
check for customer A cannot delay customer B's. Exceptions in any
single check are logged and swallowed; the tick always completes.

Design tensions this resolves:

  • Concurrency vs ordering — we DON'T care about order within a tick,
    so all checks run concurrently via gather. This is the only way to
    keep tick duration bounded when one customer's check stalls.

  • Timeout placement — the timeout wraps each individual check, not
    the gather. Wrapping the gather would mean one slow check cancels
    the fast ones that happened to still be in flight when the gather
    times out. Per-task timeouts don't have that problem.

  • Cancellation semantics — stop() cancels the LOOP task, not the
    in-flight checks. The loop task's cancellation propagates into the
    await on gather, which cancels its children. That's the right
    behaviour for shutdown: we don't need to wait for a slow check to
    finish before the process exits.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


CheckFn = Callable[[str], Awaitable[None]]


class HeartbeatDaemon:
    def __init__(
        self,
        *,
        ea_registry: Any,
        check_fn: CheckFn,
        tick_interval: float = 300.0,  # 5 minutes — coarse enough to be cheap
        per_check_timeout: float = 30.0,
    ):
        self._registry = ea_registry
        self._check_fn = check_fn
        self._tick_interval = tick_interval
        self._per_check_timeout = per_check_timeout
        self._task: Optional[asyncio.Task] = None

    # --- Lifecycle ---------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.is_running:
            return  # idempotent — double start in a misbehaving lifespan is harmless
        self._task = asyncio.create_task(self._loop(), name="proactive-heartbeat")
        logger.info("heartbeat daemon started (tick=%.1fs, timeout=%.1fs)",
                    self._tick_interval, self._per_check_timeout)

    async def stop(self) -> None:
        if self._task is None:
            return  # never started → nothing to do
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("heartbeat daemon stopped")

    # --- Tick --------------------------------------------------------------

    async def tick_once(self) -> None:
        """Run one sweep of all active customers. Exposed so tests can
        drive the loop without sleeping through a real tick interval."""
        customers = list(self._registry.active_customers())
        if not customers:
            return

        async def _guarded(cid: str) -> None:
            try:
                await asyncio.wait_for(
                    self._check_fn(cid),
                    timeout=self._per_check_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("proactive check timed out for customer=%s "
                               "after %.1fs", cid, self._per_check_timeout)
            except asyncio.CancelledError:
                # Propagate — this is stop() tearing us down mid-tick,
                # not a check failing. Swallowing here would make
                # shutdown hang until every in-flight timeout expired.
                raise
            except Exception as e:
                logger.warning("proactive check failed for customer=%s: %s",
                               cid, e)

        # gather with return_exceptions=False is fine because _guarded
        # already swallows everything except CancelledError — and we
        # WANT CancelledError to propagate so stop() works.
        await asyncio.gather(*(_guarded(cid) for cid in customers))

    # --- Loop --------------------------------------------------------------

    async def _loop(self) -> None:
        # Loop forever until cancelled. Each iteration is best-effort:
        # a crash in tick_once doesn't kill the loop, because the next
        # tick is a fresh chance to recover. If we let it die the daemon
        # goes silent and nobody notices until customers complain.
        while True:
            try:
                await self.tick_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("heartbeat tick crashed; will retry next interval")
            await asyncio.sleep(self._tick_interval)
