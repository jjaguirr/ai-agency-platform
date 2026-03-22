"""
Unit tests for WorkflowSpecialist contextual suggestions.

The specialist already deploys templates; these tests cover the
suggestion layer: usage-based ("you ask about X a lot — want an
automation?"), related templates after deploy, and cooldowns so
suggestions don't fire every turn.

Suggestion state (topic hit counts, cooldowns) lives in
ProactiveStateStore.
"""
from __future__ import annotations

import pytest
import fakeredis.aioredis

from src.agents.specialists.workflows import WorkflowSpecialist
from src.agents.base.specialist import SpecialistTask, SpecialistStatus
from src.agents.context import InteractionContext
from src.agents.executive_assistant import BusinessContext
from src.proactive.state import ProactiveStateStore


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def store(redis):
    return ProactiveStateStore(redis)


@pytest.fixture
def ctx():
    return BusinessContext(business_name="Acme Co")


# Minimal store/catalog doubles — suggestions work from delegation
# history + cooldown state, not from deploy mechanics.

class StubWfStore:
    def __init__(self, workflows=None):
        self._wfs = workflows or []

    async def list_workflows(self, customer_id):
        return list(self._wfs)

    async def find_by_name(self, customer_id, name):
        return None

    async def get_config(self, customer_id):
        return None


def _task(desc, *, customer_id="c1", interaction_ctx=None, ctx=None):
    return SpecialistTask(
        description=desc,
        customer_id=customer_id,
        business_context=ctx or BusinessContext(business_name="Acme Co"),
        domain_memories=[],
        interaction_context=interaction_ctx,
    )


def _interaction_ctx(customer_id="c1", *, delegation_history=(), tone="professional"):
    return InteractionContext(
        customer_id=customer_id,
        recent_turns=(),
        personality={"tone": tone},
        domains={},
        delegation_history=tuple(delegation_history),
    )


# --- Usage-based suggestions ------------------------------------------------

class TestUsageBasedSuggestions:
    @pytest.mark.asyncio
    async def test_repeated_invoice_queries_trigger_suggestion(
        self, store, ctx
    ):
        """Three recent finance delegations mentioning 'invoice' with no
        invoice-tracking workflow → suggest one."""
        spec = WorkflowSpecialist(
            store=StubWfStore(), proactive_state=store,
        )
        ictx = _interaction_ctx(delegation_history=(
            {"domain": "finance", "status": "completed",
             "task": "what invoices are outstanding?"},
            {"domain": "finance", "status": "completed",
             "task": "track invoice from Acme"},
            {"domain": "finance", "status": "completed",
             "task": "has the invoice been paid?"},
        ))

        result = await spec.execute_task(_task(
            "what automations do I have?",
            interaction_ctx=ictx, ctx=ctx,
        ))

        assert result.status == SpecialistStatus.COMPLETED
        text = result.summary_for_ea.lower()
        # Must name the pattern AND offer to act on it. "suggest" alone
        # is too common a substring to be a reliable signal.
        assert "invoice" in text
        assert "want me to set up" in text

    @pytest.mark.asyncio
    async def test_suggestion_has_cooldown(self, store, ctx):
        """Same context twice in a row — second call should NOT repeat
        the suggestion."""
        spec = WorkflowSpecialist(
            store=StubWfStore(), proactive_state=store,
        )
        history = (
            {"domain": "finance", "status": "completed",
             "task": "what invoices are outstanding?"},
        ) * 3
        ictx = _interaction_ctx(delegation_history=history)

        r1 = await spec.execute_task(_task(
            "list my workflows", interaction_ctx=ictx, ctx=ctx,
        ))
        r2 = await spec.execute_task(_task(
            "list my workflows", interaction_ctx=ictx, ctx=ctx,
        ))

        # First mentions it, second doesn't.
        assert "invoice" in r1.summary_for_ea.lower()
        assert "invoice" not in r2.summary_for_ea.lower()

    @pytest.mark.asyncio
    async def test_no_suggestion_when_workflow_exists(self, store, ctx):
        """Customer already has an invoice tracker — don't suggest
        another."""
        spec = WorkflowSpecialist(
            store=StubWfStore(workflows=[
                {"workflow_id": "wf1", "name": "Invoice Tracker",
                 "status": "active"},
            ]),
            proactive_state=store,
        )
        history = (
            {"domain": "finance", "status": "completed",
             "task": "track invoice"},
        ) * 3
        ictx = _interaction_ctx(delegation_history=history)

        result = await spec.execute_task(_task(
            "list my automations", interaction_ctx=ictx, ctx=ctx,
        ))

        text = result.summary_for_ea.lower()
        # The workflow name appears in the listing, but no "want me to"
        # phrasing — it already exists.
        assert not any(w in text for w in ("want me to set up", "could set up"))

    @pytest.mark.asyncio
    async def test_no_suggestion_below_threshold(self, store, ctx):
        """One invoice mention isn't a pattern — don't suggest."""
        spec = WorkflowSpecialist(
            store=StubWfStore(), proactive_state=store,
        )
        ictx = _interaction_ctx(delegation_history=(
            {"domain": "finance", "status": "completed",
             "task": "track invoice"},
        ))

        result = await spec.execute_task(_task(
            "what workflows do I have?", interaction_ctx=ictx, ctx=ctx,
        ))
        assert "invoice" not in result.summary_for_ea.lower()


# --- No context = no suggestions --------------------------------------------

class TestGracefulDegradation:
    @pytest.mark.asyncio
    async def test_no_interaction_context_still_works(self, store, ctx):
        """Old callers that don't pass interaction_context get the old
        behaviour — no suggestions, no crash."""
        spec = WorkflowSpecialist(
            store=StubWfStore(), proactive_state=store,
        )
        result = await spec.execute_task(_task(
            "list my workflows", interaction_ctx=None, ctx=ctx,
        ))
        assert result.status == SpecialistStatus.COMPLETED
