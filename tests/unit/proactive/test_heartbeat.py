"""
HeartbeatDaemon — the asyncio background task that drives proactive checks.

Contract under test:
  - start() spawns a background task; stop() cancels it cleanly and awaits
  - One tick iterates all active customers in the EARegistry
  - Each customer's check is an independent task with a timeout
  - A slow/hung check for cust_a does NOT block cust_b's check
  - A raising check for cust_a does NOT abort the tick
  - tick_once() is exposed so tests can drive the loop without sleeping

The daemon does not sleep in tests — tick interval is irrelevant here because
we call tick_once() directly. The real loop (start/stop) is tested only for
lifecycle semantics.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.proactive.heartbeat import HeartbeatDaemon


pytestmark = pytest.mark.asyncio


def _registry_with(*customer_ids):
    """Fake EARegistry exposing active_customers() and iteration."""
    reg = MagicMock()
    reg.active_customers = MagicMock(return_value=list(customer_ids))
    return reg


class TestLifecycle:
    async def test_start_and_stop_clean(self):
        daemon = HeartbeatDaemon(
            ea_registry=_registry_with(),
            check_fn=AsyncMock(),
            tick_interval=100.0,  # won't fire during this short test
        )
        await daemon.start()
        assert daemon.is_running
        await daemon.stop()
        assert not daemon.is_running

    async def test_double_start_is_idempotent(self):
        daemon = HeartbeatDaemon(
            ea_registry=_registry_with(),
            check_fn=AsyncMock(),
            tick_interval=100.0,
        )
        await daemon.start()
        await daemon.start()  # no-op
        await daemon.stop()

    async def test_stop_before_start_is_noop(self):
        daemon = HeartbeatDaemon(
            ea_registry=_registry_with(),
            check_fn=AsyncMock(),
        )
        await daemon.stop()  # must not raise

    async def test_stop_awaits_inflight_tick(self):
        """
        stop() during an in-flight tick cancels the task and awaits it.
        No orphaned tasks after stop() returns.
        """
        entered = asyncio.Event()
        hold = asyncio.Event()

        async def slow_check(cid):
            entered.set()
            await hold.wait()

        daemon = HeartbeatDaemon(
            ea_registry=_registry_with("cust"),
            check_fn=slow_check,
            tick_interval=0.001,
        )
        await daemon.start()
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        # Now the tick is blocked on hold — stop() should cancel it.
        await daemon.stop()
        # Release hold to clean up (but task is already cancelled)
        hold.set()
        assert not daemon.is_running


class TestTickConcurrency:
    async def test_tick_runs_all_customers(self):
        check_fn = AsyncMock()
        daemon = HeartbeatDaemon(
            ea_registry=_registry_with("a", "b", "c"),
            check_fn=check_fn,
        )
        await daemon.tick_once()
        assert check_fn.call_count == 3
        called_with = {c.args[0] for c in check_fn.call_args_list}
        assert called_with == {"a", "b", "c"}

    async def test_slow_check_does_not_block_others(self):
        """
        cust_a's check sleeps past the per-check timeout. cust_b's check
        must still complete within the tick, not wait for a's timeout
        serially.
        """
        order = []

        async def check(cid):
            if cid == "a":
                await asyncio.sleep(10)  # way past timeout
            order.append(cid)

        daemon = HeartbeatDaemon(
            ea_registry=_registry_with("a", "b", "c"),
            check_fn=check,
            per_check_timeout=0.1,
        )
        # Tick should complete quickly — a times out, b and c run.
        await asyncio.wait_for(daemon.tick_once(), timeout=1.0)
        assert "b" in order
        assert "c" in order
        # a never appended because it was cancelled mid-sleep
        assert "a" not in order

    async def test_raising_check_does_not_abort_tick(self):
        """One customer's check raises → logged and swallowed, others proceed."""
        completed = []

        async def check(cid):
            if cid == "a":
                raise RuntimeError("boom")
            completed.append(cid)

        daemon = HeartbeatDaemon(
            ea_registry=_registry_with("a", "b", "c"),
            check_fn=check,
        )
        await daemon.tick_once()
        assert set(completed) == {"b", "c"}

    async def test_empty_registry_tick_is_noop(self):
        check_fn = AsyncMock()
        daemon = HeartbeatDaemon(
            ea_registry=_registry_with(),
            check_fn=check_fn,
        )
        await daemon.tick_once()
        check_fn.assert_not_called()


class TestSpecialistProactiveCheck:
    """
    The specialist interface gains an optional proactive_check — specialists
    that don't implement it are skipped.
    """
    async def test_specialist_without_proactive_check_is_skipped(self):
        from src.agents.base.specialist import SpecialistAgent

        # SpecialistAgent.proactive_check default returns None — calling it
        # on a subclass that didn't override it is safe.
        class DumbSpecialist(SpecialistAgent):
            @property
            def domain(self): return "dumb"
            def assess_task(self, *a, **kw):
                from src.agents.base.specialist import TaskAssessment
                return TaskAssessment(confidence=0.0)
            async def execute_task(self, *a, **kw):
                raise NotImplementedError

        s = DumbSpecialist()
        result = await s.proactive_check("cust", None)
        assert result is None

    async def test_specialist_with_proactive_check_returns_trigger(self):
        from src.agents.base.specialist import SpecialistAgent, TaskAssessment
        from src.agents.proactive.triggers import Priority, ProactiveTrigger

        class SmartSpecialist(SpecialistAgent):
            @property
            def domain(self): return "smart"
            def assess_task(self, *a, **kw): return TaskAssessment(confidence=0.0)
            async def execute_task(self, *a, **kw): raise NotImplementedError
            async def proactive_check(self, customer_id, context):
                return ProactiveTrigger(
                    domain=self.domain, trigger_type="anomaly",
                    priority=Priority.HIGH, title="t",
                    payload={}, suggested_message="m",
                )

        s = SmartSpecialist()
        t = await s.proactive_check("cust", None)
        assert t is not None
        assert t.domain == "smart"
