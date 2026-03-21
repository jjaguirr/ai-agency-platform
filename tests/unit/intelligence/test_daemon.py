"""
IntelligenceDaemon — background sweep that turns idle conversations
into tagged, summarized, quality-flagged records.

Lifecycle tests run the real loop with a tiny tick interval; tick
tests call _tick() directly so we can assert on the exact dependency
flow without waiting on the scheduler.

The daemon coordinates four things: IntelligenceRepository (find idle,
write back, fetch delegation statuses), ConversationRepository (fetch
messages), ConversationSummarizer (LLM call), and the pure functions
in tagging/quality. All four are mocked; the pure functions are cheap
enough to exercise for real, so we let them run and assert on the
result that lands in set_intelligence.
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.intelligence.daemon import IntelligenceDaemon


# ─── fixtures ──────────────────────────────────────────────────────────────

def _msgs(*pairs):
    """[("user", "hi"), ("assistant", "hello")] → list of message dicts."""
    return [{"role": r, "content": c} for r, c in pairs]


@pytest.fixture
def intel_repo():
    r = AsyncMock()
    r.find_idle_unsummarized = AsyncMock(return_value=[])
    r.get_delegation_statuses = AsyncMock(return_value=[])
    r.set_intelligence = AsyncMock(return_value=True)
    return r


@pytest.fixture
def conv_repo():
    r = AsyncMock()
    r.get_messages = AsyncMock(return_value=[])
    return r


@pytest.fixture
def summarizer():
    s = MagicMock()
    s.summarize = AsyncMock(return_value="A summary.")
    return s


@pytest.fixture
def daemon(intel_repo, conv_repo, summarizer):
    return IntelligenceDaemon(
        intel_repo=intel_repo,
        conv_repo=conv_repo,
        summarizer=summarizer,
        idle_minutes=30,
        batch_limit=50,
        tick_interval=60.0,
    )


# ─── lifecycle ─────────────────────────────────────────────────────────────

class TestLifecycle:
    async def test_starts_and_stops_cleanly(self, intel_repo, conv_repo, summarizer):
        d = IntelligenceDaemon(
            intel_repo=intel_repo, conv_repo=conv_repo, summarizer=summarizer,
            tick_interval=0.05,
        )
        await d.start()
        assert d.is_running
        await d.stop()
        assert not d.is_running

    async def test_stop_is_idempotent(self, intel_repo, conv_repo, summarizer):
        d = IntelligenceDaemon(
            intel_repo=intel_repo, conv_repo=conv_repo, summarizer=summarizer,
            tick_interval=0.05,
        )
        await d.start()
        await d.stop()
        await d.stop()  # no raise
        assert not d.is_running

    async def test_start_when_running_is_noop(self, intel_repo, conv_repo, summarizer):
        d = IntelligenceDaemon(
            intel_repo=intel_repo, conv_repo=conv_repo, summarizer=summarizer,
            tick_interval=0.05,
        )
        await d.start()
        first_task = d._task
        await d.start()
        assert d._task is first_task  # not replaced
        await d.stop()

    async def test_tick_exception_does_not_kill_loop(
        self, intel_repo, conv_repo, summarizer,
    ):
        # First call raises, second succeeds. The daemon must survive
        # the first tick and reach the second.
        intel_repo.find_idle_unsummarized = AsyncMock(
            side_effect=[ConnectionError("pg gone"), []]
        )
        d = IntelligenceDaemon(
            intel_repo=intel_repo, conv_repo=conv_repo, summarizer=summarizer,
            tick_interval=0.01,
        )
        await d.start()
        await asyncio.sleep(0.05)  # room for two ticks
        await d.stop()
        assert intel_repo.find_idle_unsummarized.await_count >= 2


# ─── tick: empty sweep ─────────────────────────────────────────────────────

class TestTickNoWork:
    async def test_no_idle_conversations_no_writes(self, daemon, intel_repo):
        intel_repo.find_idle_unsummarized.return_value = []

        await daemon._tick()

        intel_repo.set_intelligence.assert_not_awaited()

    async def test_sweep_uses_configured_idle_and_limit(self, intel_repo, conv_repo, summarizer):
        d = IntelligenceDaemon(
            intel_repo=intel_repo, conv_repo=conv_repo, summarizer=summarizer,
            idle_minutes=45, batch_limit=7,
        )
        await d._tick()

        kw = intel_repo.find_idle_unsummarized.await_args.kwargs
        assert kw["idle_minutes"] == 45
        assert kw["limit"] == 7


# ─── tick: happy path ──────────────────────────────────────────────────────

class TestTickProcessing:
    async def test_full_pipeline_for_one_conversation(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        intel_repo.find_idle_unsummarized.return_value = [("conv_a", "cust_1")]
        conv_repo.get_messages.return_value = _msgs(
            ("user", "check my invoices"),
            ("assistant", "You have 3 unpaid."),
        )
        intel_repo.get_delegation_statuses.return_value = [
            ("finance", "completed"),
        ]
        summarizer.summarize.return_value = "Customer asked about invoices."

        await daemon._tick()

        # Messages fetched with tenant guard
        conv_repo.get_messages.assert_awaited_once_with(
            customer_id="cust_1", conversation_id="conv_a",
        )
        # Delegation statuses fetched with tenant guard
        intel_repo.get_delegation_statuses.assert_awaited_once_with(
            customer_id="cust_1", conversation_id="conv_a",
        )
        # Summarizer received the transcript
        summarizer.summarize.assert_awaited_once()
        assert summarizer.summarize.await_args.args[0] == conv_repo.get_messages.return_value
        # Write combines everything
        intel_repo.set_intelligence.assert_awaited_once()
        kw = intel_repo.set_intelligence.await_args.kwargs
        assert kw["customer_id"] == "cust_1"
        assert kw["conversation_id"] == "conv_a"
        assert kw["summary"] == "Customer asked about invoices."
        assert kw["topics"] == ["finance"]
        assert kw["quality_flags"] == []  # assistant replied, completed, short

    async def test_no_delegations_tags_general(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        intel_repo.find_idle_unsummarized.return_value = [("conv_g", "cust_1")]
        conv_repo.get_messages.return_value = _msgs(
            ("user", "what's the weather"),
            ("assistant", "Sunny."),
        )
        intel_repo.get_delegation_statuses.return_value = []

        await daemon._tick()

        kw = intel_repo.set_intelligence.await_args.kwargs
        assert kw["topics"] == ["general"]

    async def test_quality_flags_computed(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        # Last message is user + delegation failed → unresolved.
        # User said "this is useless" → escalation.
        intel_repo.find_idle_unsummarized.return_value = [("conv_q", "cust_1")]
        conv_repo.get_messages.return_value = _msgs(
            ("user", "help me"),
            ("assistant", "let me check"),
            ("user", "this is useless"),
        )
        intel_repo.get_delegation_statuses.return_value = [
            ("finance", "failed"),
        ]

        await daemon._tick()

        kw = intel_repo.set_intelligence.await_args.kwargs
        assert "escalation" in kw["quality_flags"]
        assert "unresolved" in kw["quality_flags"]

    async def test_workflows_domain_becomes_workflow_topic(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        intel_repo.find_idle_unsummarized.return_value = [("conv_w", "cust_1")]
        conv_repo.get_messages.return_value = _msgs(("user", "x"), ("assistant", "y"))
        intel_repo.get_delegation_statuses.return_value = [
            ("workflows", "completed"),
        ]

        await daemon._tick()

        kw = intel_repo.set_intelligence.await_args.kwargs
        assert kw["topics"] == ["workflow"]  # plural → singular


# ─── tick: isolation + failure modes ───────────────────────────────────────

class TestTickIsolation:
    async def test_two_conversations_both_processed(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        intel_repo.find_idle_unsummarized.return_value = [
            ("conv_a", "cust_1"),
            ("conv_b", "cust_2"),
        ]
        conv_repo.get_messages.return_value = _msgs(("user", "x"), ("assistant", "y"))

        await daemon._tick()

        assert intel_repo.set_intelligence.await_count == 2
        targets = {
            (c.kwargs["customer_id"], c.kwargs["conversation_id"])
            for c in intel_repo.set_intelligence.await_args_list
        }
        assert targets == {("cust_1", "conv_a"), ("cust_2", "conv_b")}

    async def test_one_conversation_blows_up_next_still_processed(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        intel_repo.find_idle_unsummarized.return_value = [
            ("conv_bad", "cust_1"),
            ("conv_good", "cust_2"),
        ]

        async def _get(*, customer_id, conversation_id):
            if conversation_id == "conv_bad":
                raise RuntimeError("corrupted row")
            return _msgs(("user", "x"), ("assistant", "y"))
        conv_repo.get_messages = AsyncMock(side_effect=_get)

        await daemon._tick()

        # conv_good still got written
        written = [
            c.kwargs["conversation_id"]
            for c in intel_repo.set_intelligence.await_args_list
        ]
        assert written == ["conv_good"]

    async def test_summarizer_none_skips_write(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        # LLM down → summary None → don't write. summary stays NULL,
        # next sweep picks it up again. This is the retry mechanism.
        intel_repo.find_idle_unsummarized.return_value = [("conv_a", "cust_1")]
        conv_repo.get_messages.return_value = _msgs(("user", "x"), ("assistant", "y"))
        summarizer.summarize.return_value = None

        await daemon._tick()

        intel_repo.set_intelligence.assert_not_awaited()

    async def test_get_messages_returns_none_skips(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        # Race: conversation deleted between find_idle and process.
        # get_messages returns None → skip silently.
        intel_repo.find_idle_unsummarized.return_value = [("conv_gone", "cust_1")]
        conv_repo.get_messages.return_value = None

        await daemon._tick()

        intel_repo.set_intelligence.assert_not_awaited()
        summarizer.summarize.assert_not_awaited()

    async def test_set_intelligence_failure_isolated(
        self, daemon, intel_repo, conv_repo, summarizer,
    ):
        intel_repo.find_idle_unsummarized.return_value = [
            ("conv_a", "cust_1"),
            ("conv_b", "cust_1"),
        ]
        conv_repo.get_messages.return_value = _msgs(("user", "x"), ("assistant", "y"))

        calls = []
        async def _set(**kw):
            calls.append(kw["conversation_id"])
            if kw["conversation_id"] == "conv_a":
                raise ConnectionError("pg hiccup")
            return True
        intel_repo.set_intelligence = AsyncMock(side_effect=_set)

        await daemon._tick()

        assert calls == ["conv_a", "conv_b"]
