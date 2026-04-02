"""
Tests for InteractionContext and ContextAssembler.

The shared context layer is assembled once per interaction and passed
read-only to whichever specialist handles the delegation. It aggregates
lightweight snapshots from each domain (calendar, finance, workflows,
notifications) with per-source timeouts so a slow domain never blocks
the response.

Tests first — implementation follows.
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock

from src.agents.context import (
    CalendarSnapshot,
    ContextAssembler,
    CustomerPreferences,
    DelegationRecord,
    FinanceSnapshot,
    InteractionContext,
    WorkflowSnapshot,
)
from src.proactive.state import ProactiveStateStore


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def proactive_store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def settings_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def calendar_client():
    """Mock calendar client returning two events with real datetimes."""
    client = AsyncMock()
    client.list_events = AsyncMock(return_value=[
        MagicMock(
            id="evt1", title="Standup",
            start=datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, 9, 30, tzinfo=timezone.utc),
            attendees=("Alice",), location=None,
        ),
        MagicMock(
            id="evt2", title="Client Call",
            start=datetime(2026, 3, 21, 14, 0, tzinfo=timezone.utc),
            end=datetime(2026, 3, 21, 15, 0, tzinfo=timezone.utc),
            attendees=("Bob",), location="Zoom",
        ),
    ])
    client.is_free = AsyncMock(return_value=True)
    return client


@pytest.fixture
def workflow_store():
    """Mock workflow store with two active workflows."""
    store = AsyncMock()
    store.list_workflows = AsyncMock(return_value=[
        {"workflow_id": "wf1", "name": "Monday Reports", "status": "active"},
        {"workflow_id": "wf2", "name": "Invoice Tracker", "status": "active"},
    ])
    return store


@pytest.fixture
def assembler(proactive_store, settings_redis):
    return ContextAssembler(
        proactive_store=proactive_store,
        settings_redis=settings_redis,
        source_timeout=2.0,
    )


CUSTOMER_ID = "cust_ctx_test"


# --- InteractionContext dataclass -------------------------------------------

class TestInteractionContextDataclass:
    def test_default_construction(self):
        """All fields have sensible defaults."""
        ctx = InteractionContext()
        assert ctx.recent_conversation_summary is None
        assert ctx.calendar_snapshot is None
        assert ctx.finance_snapshot is None
        assert ctx.workflow_snapshot is None
        assert ctx.pending_notifications == []
        assert isinstance(ctx.customer_preferences, CustomerPreferences)
        assert ctx.customer_preferences.tone == "professional"
        assert ctx.delegation_history == []

    def test_calendar_snapshot_fields(self):
        snap = CalendarSnapshot(events_next_24h=[{"id": "e1"}], has_conflicts=True)
        assert snap.has_conflicts is True
        assert len(snap.events_next_24h) == 1

    def test_finance_snapshot_fields(self):
        snap = FinanceSnapshot(
            transaction_baseline=250.0,
            recent_expense_total=1200.0,
            top_category="marketing",
            budget_status={"marketing": {"limit": 3000, "spent": 1200}},
        )
        assert snap.transaction_baseline == 250.0
        assert snap.budget_status["marketing"]["limit"] == 3000

    def test_workflow_snapshot_fields(self):
        snap = WorkflowSnapshot(
            active_count=2,
            workflow_names=["A", "B"],
            recent_failures=[{"wf": "A", "error": "timeout"}],
        )
        assert snap.active_count == 2
        assert len(snap.recent_failures) == 1

    def test_customer_preferences_defaults(self):
        prefs = CustomerPreferences()
        assert prefs.tone == "professional"
        assert prefs.language == "en"
        assert prefs.business_type == ""

    def test_delegation_record_fields(self):
        rec = DelegationRecord(domain="finance", status="completed", timestamp="2026-03-21T10:00:00Z")
        assert rec.domain == "finance"


# --- ContextAssembler: happy path -------------------------------------------

class TestAssemblerHappyPath:
    @pytest.mark.asyncio
    async def test_assembles_with_all_sources(
        self, assembler, proactive_store, settings_redis, calendar_client, workflow_store,
    ):
        """All sources wired and healthy → full context."""
        # Seed finance data
        for _ in range(4):
            await proactive_store.record_transaction(CUSTOMER_ID, 200.0)

        # Seed personality settings
        await settings_redis.set(f"settings:{CUSTOMER_ID}", json.dumps({
            "personality": {"tone": "friendly", "name": "Aria", "language": "en"},
            "working_hours": {"start": "09:00", "end": "17:00", "timezone": "US/Eastern"},
        }))

        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"scheduling", "finance", "workflows"},
            calendar_client=calendar_client,
            workflow_store=workflow_store,
            conversation_summary="Discussed marketing budget earlier.",
        )

        assert ctx.recent_conversation_summary == "Discussed marketing budget earlier."
        assert ctx.calendar_snapshot is not None
        assert len(ctx.calendar_snapshot.events_next_24h) == 2
        assert ctx.finance_snapshot is not None
        assert ctx.finance_snapshot.transaction_baseline is not None
        assert ctx.workflow_snapshot is not None
        assert ctx.workflow_snapshot.active_count == 2
        assert ctx.customer_preferences.tone == "friendly"

    @pytest.mark.asyncio
    async def test_conversation_summary_passthrough(self, assembler):
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains=set(),
            conversation_summary="Talked about invoices.",
        )
        assert ctx.recent_conversation_summary == "Talked about invoices."


# --- ContextAssembler: missing sources → graceful degradation ---------------

class TestAssemblerDegradation:
    @pytest.mark.asyncio
    async def test_calendar_snapshot_none_when_no_client(self, assembler):
        """No calendar client → snapshot is None, not an error."""
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"scheduling"},
            calendar_client=None,
        )
        assert ctx.calendar_snapshot is None

    @pytest.mark.asyncio
    async def test_workflow_snapshot_none_when_no_store(self, assembler):
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"workflows"},
            workflow_store=None,
        )
        assert ctx.workflow_snapshot is None

    @pytest.mark.asyncio
    async def test_finance_snapshot_none_when_no_transactions(self, assembler):
        """No transaction history → baseline is None."""
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"finance"},
        )
        assert ctx.finance_snapshot is not None
        assert ctx.finance_snapshot.transaction_baseline is None

    @pytest.mark.asyncio
    async def test_preferences_defaults_when_settings_missing(self, assembler):
        """No settings in Redis → defaults."""
        ctx = await assembler.assemble(CUSTOMER_ID, relevant_domains=set())
        assert ctx.customer_preferences.tone == "professional"
        assert ctx.customer_preferences.language == "en"


# --- ContextAssembler: lazy loading (relevant_domains) ----------------------

class TestAssemblerLazyLoading:
    @pytest.mark.asyncio
    async def test_irrelevant_domain_not_queried(self, assembler, calendar_client):
        """When relevant_domains is {'finance'}, calendar client not called."""
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"finance"},
            calendar_client=calendar_client,
        )
        assert ctx.calendar_snapshot is None
        calendar_client.list_events.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_relevant_domain_queried(self, assembler, calendar_client):
        """When relevant_domains includes 'scheduling', calendar client IS called."""
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"scheduling"},
            calendar_client=calendar_client,
        )
        assert ctx.calendar_snapshot is not None
        calendar_client.list_events.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_domains_fetches_all_lightweight(
        self, assembler, calendar_client, workflow_store,
    ):
        """Empty relevant_domains → all sources queried (ambiguous message)."""
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains=set(),
            calendar_client=calendar_client,
            workflow_store=workflow_store,
        )
        # All snapshots populated (or at least attempted)
        assert ctx.calendar_snapshot is not None
        assert ctx.workflow_snapshot is not None
        assert ctx.finance_snapshot is not None


# --- ContextAssembler: timeouts ---------------------------------------------

class TestAssemblerTimeouts:
    @pytest.mark.asyncio
    async def test_slow_calendar_times_out(self, proactive_store, settings_redis):
        """Calendar source hangs → times out → None, other sources populated."""
        slow_calendar = AsyncMock()

        async def slow_list(*a, **kw):
            await asyncio.sleep(10)  # way past timeout
            return []

        slow_calendar.list_events = slow_list
        slow_calendar.is_free = AsyncMock(return_value=True)

        asm = ContextAssembler(
            proactive_store=proactive_store,
            settings_redis=settings_redis,
            source_timeout=0.1,  # very short
        )
        ctx = await asm.assemble(
            CUSTOMER_ID,
            relevant_domains={"scheduling", "finance"},
            calendar_client=slow_calendar,
        )

        assert ctx.calendar_snapshot is None  # timed out
        assert ctx.finance_snapshot is not None  # other source still works

    @pytest.mark.asyncio
    async def test_slow_workflow_store_times_out(self, proactive_store, settings_redis):
        slow_store = AsyncMock()

        async def slow_list(*a, **kw):
            await asyncio.sleep(10)
            return []

        slow_store.list_workflows = slow_list

        asm = ContextAssembler(
            proactive_store=proactive_store,
            settings_redis=settings_redis,
            source_timeout=0.1,
        )
        ctx = await asm.assemble(
            CUSTOMER_ID,
            relevant_domains={"workflows"},
            workflow_store=slow_store,
        )
        assert ctx.workflow_snapshot is None


# --- ContextAssembler: error tolerance --------------------------------------

class TestAssemblerErrorTolerance:
    @pytest.mark.asyncio
    async def test_calendar_error_yields_none(self, assembler):
        broken_cal = AsyncMock()
        broken_cal.list_events = AsyncMock(side_effect=ConnectionError("calendar down"))

        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"scheduling"},
            calendar_client=broken_cal,
        )
        assert ctx.calendar_snapshot is None

    @pytest.mark.asyncio
    async def test_workflow_store_error_yields_none(self, assembler):
        broken_store = AsyncMock()
        broken_store.list_workflows = AsyncMock(side_effect=RuntimeError("redis down"))

        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains={"workflows"},
            workflow_store=broken_store,
        )
        assert ctx.workflow_snapshot is None

    @pytest.mark.asyncio
    async def test_settings_redis_error_yields_defaults(self, proactive_store):
        broken_redis = AsyncMock()
        broken_redis.get = AsyncMock(side_effect=ConnectionError("redis down"))

        asm = ContextAssembler(
            proactive_store=proactive_store,
            settings_redis=broken_redis,
        )
        ctx = await asm.assemble(CUSTOMER_ID, relevant_domains=set())
        assert ctx.customer_preferences.tone == "professional"


# --- ContextAssembler: delegation history -----------------------------------

class TestAssemblerDelegationHistory:
    @pytest.mark.asyncio
    async def test_delegation_history_passed_through(self, assembler):
        history = [
            DelegationRecord(domain="finance", status="completed", timestamp="2026-03-21T09:00:00Z"),
            DelegationRecord(domain="scheduling", status="completed", timestamp="2026-03-21T09:05:00Z"),
        ]
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains=set(),
            delegation_history=history,
        )
        assert len(ctx.delegation_history) == 2
        assert ctx.delegation_history[0].domain == "finance"

    @pytest.mark.asyncio
    async def test_delegation_history_defaults_empty(self, assembler):
        ctx = await assembler.assemble(CUSTOMER_ID, relevant_domains=set())
        assert ctx.delegation_history == []


# --- ContextAssembler: pending notifications --------------------------------

class TestAssemblerNotifications:
    @pytest.mark.asyncio
    async def test_includes_pending_notifications(self, assembler, proactive_store):
        from datetime import datetime, timezone
        await proactive_store.add_pending_notification(CUSTOMER_ID, {
            "domain": "finance",
            "trigger_type": "finance_anomaly",
            "priority": 3,
            "title": "Unusual expense",
            "message": "$5000 on marketing",
        })
        ctx = await assembler.assemble(
            CUSTOMER_ID,
            relevant_domains=set(),
        )
        assert len(ctx.pending_notifications) == 1
        assert ctx.pending_notifications[0]["domain"] == "finance"
        assert ctx.pending_notifications[0]["title"] == "Unusual expense"
