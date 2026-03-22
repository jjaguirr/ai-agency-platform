"""
Unit tests for the specialist agent protocol and delegation registry.

These tests define the contract that all specialist agents must satisfy,
and the routing logic the EA uses to decide whether to delegate.
"""
import asyncio
import pytest
from dataclasses import dataclass, field
from typing import List

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistTask,
    SpecialistResult,
    SpecialistStatus,
    TaskAssessment,
    DelegationRegistry,
)
from src.agents.executive_assistant import BusinessContext


# --- Test doubles -----------------------------------------------------------

@dataclass
class _FakeSpecialist(SpecialistAgent):
    """Configurable specialist for routing tests."""
    _domain: str
    _confidence: float = 0.0
    _strategic: bool = False
    _result: SpecialistResult = None
    _delay: float = 0.0
    _raise: Exception = None
    _received_tasks: List[SpecialistTask] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return self._domain

    def assess_task(self, task_description: str, context: BusinessContext) -> TaskAssessment:
        return TaskAssessment(confidence=self._confidence, is_strategic=self._strategic)

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        self._received_tasks.append(task)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raise:
            raise self._raise
        return self._result or SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self._domain,
            payload={"handled": True},
            confidence=self._confidence,
        )


@pytest.fixture
def ctx():
    return BusinessContext(business_name="Test Co", industry="retail")


# --- TaskAssessment ---------------------------------------------------------

class TestTaskAssessment:
    def test_clamps_confidence_to_unit_range(self):
        assert TaskAssessment(confidence=1.5, is_strategic=False).confidence == 1.0
        assert TaskAssessment(confidence=-0.3, is_strategic=False).confidence == 0.0
        assert TaskAssessment(confidence=0.7, is_strategic=False).confidence == 0.7


# --- SpecialistTask ---------------------------------------------------------

class TestSpecialistTask:
    def test_carries_only_scoped_context(self, ctx):
        """Specialist receives task + business context + pre-scoped memory,
        NOT the full conversation state or raw memory client."""
        task = SpecialistTask(
            description="check instagram engagement",
            customer_id="cust_abc",
            business_context=ctx,
            domain_memories=[{"content": "posts daily at 9am", "score": 0.9}],
        )
        assert task.customer_id == "cust_abc"
        assert task.business_context.business_name == "Test Co"
        assert len(task.domain_memories) == 1
        # No messages, no conversation_id, no memory client — by design

    def test_carries_prior_turns_for_multi_turn_delegation(self, ctx):
        """When a specialist asked for clarification and the customer responded,
        the follow-up task carries prior_turns so the specialist has continuity."""
        task = SpecialistTask(
            description="schedule for 9am weekdays",
            customer_id="cust_abc",
            business_context=ctx,
            domain_memories=[],
            prior_turns=[
                {"role": "specialist", "content": "What time should posts go out?"},
                {"role": "customer", "content": "9am weekdays"},
            ],
        )
        assert len(task.prior_turns) == 2

    def test_interaction_context_defaults_to_none(self, ctx):
        """Existing construction without interaction_context still works."""
        task = SpecialistTask(
            description="check engagement",
            customer_id="cust_abc",
            business_context=ctx,
            domain_memories=[],
        )
        assert task.interaction_context is None

    def test_interaction_context_round_trips(self, ctx):
        """New field carries the assembled context through to the specialist."""
        from src.agents.context import InteractionContext, CustomerPreferences
        ic = InteractionContext(
            recent_conversation_summary="Talked about budgets.",
            customer_preferences=CustomerPreferences(tone="friendly"),
        )
        task = SpecialistTask(
            description="track $500 expense",
            customer_id="cust_abc",
            business_context=ctx,
            domain_memories=[],
            interaction_context=ic,
        )
        assert task.interaction_context is not None
        assert task.interaction_context.customer_preferences.tone == "friendly"
        assert task.interaction_context.recent_conversation_summary == "Talked about budgets."


# --- SpecialistResult -------------------------------------------------------

class TestSpecialistResult:
    def test_completed_result_has_payload(self):
        r = SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain="social_media",
            payload={"engagement_rate": 0.042, "top_post": "product launch"},
            confidence=0.85,
            summary_for_ea="Engagement is healthy at 4.2%",
        )
        assert r.status == SpecialistStatus.COMPLETED
        assert r.payload["engagement_rate"] == 0.042
        assert r.summary_for_ea

    def test_needs_clarification_result_has_question(self):
        r = SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain="social_media",
            payload={},
            confidence=0.3,
            clarification_question="Which platforms do you want me to check?",
        )
        assert r.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert r.clarification_question

    def test_failed_result_has_error(self):
        r = SpecialistResult(
            status=SpecialistStatus.FAILED,
            domain="social_media",
            payload={},
            confidence=0.0,
            error="Instagram API unreachable",
        )
        assert r.status == SpecialistStatus.FAILED
        assert "Instagram" in r.error

    def test_serializes_to_dict_for_redis(self):
        """Results must survive a Redis round-trip for multi-turn persistence."""
        r = SpecialistResult(
            status=SpecialistStatus.NEEDS_CLARIFICATION,
            domain="social_media",
            payload={"partial": "data"},
            confidence=0.5,
            clarification_question="When?",
        )
        d = r.to_dict()
        assert d["status"] == "needs_clarification"
        assert d["domain"] == "social_media"
        restored = SpecialistResult.from_dict(d)
        assert restored.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert restored.clarification_question == "When?"


# --- DelegationRegistry: routing --------------------------------------------

class TestRegistryRouting:
    def test_picks_highest_confidence_specialist(self, ctx):
        reg = DelegationRegistry()
        reg.register(_FakeSpecialist(_domain="finance", _confidence=0.3))
        reg.register(_FakeSpecialist(_domain="social_media", _confidence=0.85))

        match = reg.route("how's my Instagram doing?", ctx)

        assert match is not None
        assert match.specialist.domain == "social_media"
        assert match.assessment.confidence == 0.85

    def test_returns_none_when_all_below_threshold(self, ctx):
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(_FakeSpecialist(_domain="social_media", _confidence=0.4))
        reg.register(_FakeSpecialist(_domain="finance", _confidence=0.2))

        assert reg.route("what's the weather?", ctx) is None

    def test_defers_to_ea_when_specialist_flags_strategic(self, ctx):
        """The key design decision: a specialist can be confident a message is
        in its domain but still flag it as strategic — EA keeps those."""
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(_FakeSpecialist(
            _domain="social_media", _confidence=0.8, _strategic=True
        ))

        # "should I invest more in Instagram ads" — in domain, but advisory
        assert reg.route("should I invest more in Instagram ads?", ctx) is None

    def test_strategic_flag_beats_higher_confidence(self, ctx):
        """Even if the strategic specialist has the highest confidence,
        a lower-confidence non-strategic specialist wins — or nobody does."""
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(_FakeSpecialist(_domain="social_media", _confidence=0.9, _strategic=True))
        reg.register(_FakeSpecialist(_domain="finance", _confidence=0.3))

        # social_media is strategic → filtered; finance below threshold → None
        assert reg.route("some message", ctx) is None

    def test_empty_registry_returns_none(self, ctx):
        reg = DelegationRegistry()
        assert reg.route("anything", ctx) is None

    def test_get_by_domain(self):
        reg = DelegationRegistry()
        sm = _FakeSpecialist(_domain="social_media", _confidence=0.8)
        reg.register(sm)
        assert reg.get("social_media") is sm
        assert reg.get("nonexistent") is None


# --- DelegationRegistry: execution ------------------------------------------

class TestRegistryExecution:
    @pytest.mark.asyncio
    async def test_execute_passes_task_to_specialist(self, ctx):
        sm = _FakeSpecialist(_domain="social_media", _confidence=0.8)
        reg = DelegationRegistry()
        reg.register(sm)

        task = SpecialistTask(
            description="check engagement",
            customer_id="cust_1",
            business_context=ctx,
            domain_memories=[{"content": "posts to IG", "score": 0.9}],
        )
        result = await reg.execute(sm, task, timeout=5.0)

        assert result.status == SpecialistStatus.COMPLETED
        assert len(sm._received_tasks) == 1
        assert sm._received_tasks[0].customer_id == "cust_1"
        assert sm._received_tasks[0].domain_memories[0]["content"] == "posts to IG"

    @pytest.mark.asyncio
    async def test_execute_returns_failed_on_timeout(self, ctx):
        """Hung specialist must not take down the conversation."""
        slow = _FakeSpecialist(_domain="social_media", _confidence=0.8, _delay=10.0)
        reg = DelegationRegistry()
        reg.register(slow)

        task = SpecialistTask(
            description="x", customer_id="c", business_context=ctx, domain_memories=[]
        )
        result = await reg.execute(slow, task, timeout=0.05)

        assert result.status == SpecialistStatus.FAILED
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_failed_on_exception(self, ctx):
        """Crashed specialist must not propagate — EA falls back gracefully."""
        broken = _FakeSpecialist(
            _domain="social_media", _confidence=0.8,
            _raise=RuntimeError("integration blew up"),
        )
        reg = DelegationRegistry()
        reg.register(broken)

        task = SpecialistTask(
            description="x", customer_id="c", business_context=ctx, domain_memories=[]
        )
        result = await reg.execute(broken, task, timeout=5.0)

        assert result.status == SpecialistStatus.FAILED
        assert "integration blew up" in result.error

    @pytest.mark.asyncio
    async def test_execute_propagates_clarification_status(self, ctx):
        clarifier = _FakeSpecialist(
            _domain="social_media", _confidence=0.8,
            _result=SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain="social_media",
                payload={},
                confidence=0.4,
                clarification_question="Which platforms?",
            ),
        )
        reg = DelegationRegistry()
        reg.register(clarifier)

        task = SpecialistTask(
            description="x", customer_id="c", business_context=ctx, domain_memories=[]
        )
        result = await reg.execute(clarifier, task, timeout=5.0)

        assert result.status == SpecialistStatus.NEEDS_CLARIFICATION
        assert result.clarification_question == "Which platforms?"


# --- Extensibility ----------------------------------------------------------

class TestExtensibility:
    def test_adding_second_specialist_requires_only_register_call(self, ctx):
        """Validation criterion from the spec: adding a new specialist
        should not require changing the framework."""
        reg = DelegationRegistry(confidence_threshold=0.6)
        reg.register(_FakeSpecialist(_domain="social_media", _confidence=0.2))

        # Before: no match for a finance question
        assert reg.route("what's my cash flow?", ctx) is None

        # After: just register — no framework changes
        reg.register(_FakeSpecialist(_domain="finance", _confidence=0.85))
        match = reg.route("what's my cash flow?", ctx)

        assert match is not None
        assert match.specialist.domain == "finance"
