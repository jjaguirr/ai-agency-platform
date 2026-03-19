"""
ProactiveEngine — the glue that runs per-customer checks during a heartbeat
tick. This is what the HeartbeatDaemon's check_fn actually is in production.

Flow for one customer:
  1. Gather triggers: specialist proactive_checks + built-in behaviors
     (briefing, idle nudge, due followups)
  2. For each trigger: evaluate through NoiseGate
  3. If allowed: deliver via OutboundRouter, then gate.record_sent

Testing this is mostly about wiring — the components are tested in isolation
elsewhere. Here we verify the plumbing calls the right things and swallows
errors at each stage.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.agents.proactive.triggers import Priority, ProactiveTrigger


pytestmark = pytest.mark.asyncio


def _ctx(tz="UTC"):
    from src.agents.executive_assistant import BusinessContext
    return BusinessContext(business_name="Acme", timezone=tz)


@pytest.fixture
def engine_deps(state_store, clock):
    from src.agents.proactive.gate import NoiseGate, ProactivePrefs
    from src.agents.proactive.outbound import OutboundRouter

    prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                           quiet_start_hour=22, quiet_end_hour=7,
                           daily_cap=10, cooldown_hours=24)
    gate = NoiseGate(state_store, clock=clock)
    # Outbound with no WhatsApp → everything enqueues
    router = OutboundRouter(whatsapp_manager=None, state_store=state_store)
    return {
        "state_store": state_store,
        "gate": gate,
        "router": router,
        "prefs": prefs,
        "clock": clock,
    }


class TestEngineCheck:
    async def test_followup_due_is_delivered(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine
        from src.agents.proactive.followups import Commitment

        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))
        # Briefing already sent today — isolate this test to the followup path
        await state_store.set_last_briefing("cust", clock())
        # Followup due an hour ago
        await state_store.add_followup("cust", Commitment(
            text="call John", due=clock() - timedelta(hours=1),
            raw="remind me to call John",
        ))

        engine = ProactiveEngine(
            state_store=state_store,
            gate=engine_deps["gate"],
            router=engine_deps["router"],
            clock=clock,
        )
        await engine.check_customer("cust", _ctx(), specialists=[],
                                    prefs=engine_deps["prefs"])

        # Delivered → enqueued in notifications (no WhatsApp)
        delivered = await state_store.drain_notifications("cust")
        assert len(delivered) == 1
        assert "call John" in delivered[0].suggested_message

    async def test_gate_suppression_blocks_delivery(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine
        from src.agents.proactive.gate import ProactivePrefs

        # Quiet hours: move to 23:00 UTC
        clock.set(datetime(2026, 3, 18, 23, 0, tzinfo=ZoneInfo("UTC")))
        prefs = ProactivePrefs(timezone="UTC", min_priority=Priority.LOW,
                               quiet_start_hour=22, quiet_end_hour=7,
                               daily_cap=10, cooldown_hours=24)

        from src.agents.proactive.followups import Commitment
        await state_store.add_followup("cust", Commitment(
            text="x", due=clock() - timedelta(hours=1), raw="r"))

        engine = ProactiveEngine(
            state_store=state_store, gate=engine_deps["gate"],
            router=engine_deps["router"], clock=clock,
        )
        await engine.check_customer("cust", _ctx(), specialists=[], prefs=prefs)

        # Gate suppressed → nothing delivered
        assert await state_store.drain_notifications("cust") == []

    async def test_specialist_trigger_delivered(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine

        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))
        specialist = MagicMock()
        specialist.domain = "finance"
        specialist.proactive_check = AsyncMock(return_value=ProactiveTrigger(
            domain="finance", trigger_type="anomaly", priority=Priority.HIGH,
            title="Spend spike", payload={}, suggested_message="Spending is up.",
        ))

        engine = ProactiveEngine(
            state_store=state_store, gate=engine_deps["gate"],
            router=engine_deps["router"], clock=clock,
        )
        await engine.check_customer("cust", _ctx(), specialists=[specialist],
                                    prefs=engine_deps["prefs"])

        delivered = await state_store.drain_notifications("cust")
        assert any(d.title == "Spend spike" for d in delivered)

    async def test_specialist_without_proactive_check_is_skipped(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine

        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))

        # Specialist that returns None from proactive_check (default impl)
        specialist = MagicMock()
        specialist.domain = "social_media"
        specialist.proactive_check = AsyncMock(return_value=None)

        engine = ProactiveEngine(
            state_store=state_store, gate=engine_deps["gate"],
            router=engine_deps["router"], clock=clock,
        )
        await engine.check_customer("cust", _ctx(), specialists=[specialist],
                                    prefs=engine_deps["prefs"])

        assert await state_store.drain_notifications("cust") == []

    async def test_specialist_crash_does_not_abort_check(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine
        from src.agents.proactive.followups import Commitment

        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))

        bad = MagicMock()
        bad.domain = "bad"
        bad.proactive_check = AsyncMock(side_effect=RuntimeError("oops"))

        # Briefing already sent — isolate to specialist-crash + followup path
        await state_store.set_last_briefing("cust", clock())
        # Followup should still deliver even though specialist crashed
        await state_store.add_followup("cust", Commitment(
            text="call John", due=clock() - timedelta(hours=1), raw="r"))

        engine = ProactiveEngine(
            state_store=state_store, gate=engine_deps["gate"],
            router=engine_deps["router"], clock=clock,
        )
        await engine.check_customer("cust", _ctx(), specialists=[bad],
                                    prefs=engine_deps["prefs"])

        delivered = await state_store.drain_notifications("cust")
        assert len(delivered) == 1  # the followup, not the crashed specialist


class TestInteractionCapture:
    async def test_capture_records_last_interaction(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine
        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))

        engine = ProactiveEngine(
            state_store=state_store, gate=engine_deps["gate"],
            router=engine_deps["router"], clock=clock,
        )
        await engine.capture_interaction("cust", "hello world")
        assert await state_store.get_last_interaction("cust") == clock()

    async def test_capture_extracts_commitments(self, engine_deps, state_store, clock):
        from src.agents.proactive.engine import ProactiveEngine
        clock.set(datetime(2026, 3, 18, 10, 0, tzinfo=ZoneInfo("UTC")))

        engine = ProactiveEngine(
            state_store=state_store, gate=engine_deps["gate"],
            router=engine_deps["router"], clock=clock,
        )
        await engine.capture_interaction("cust", "remind me to call John by Thursday")

        followups = await state_store.list_followups("cust")
        assert len(followups) == 1
        assert "call John" in followups[0].text
