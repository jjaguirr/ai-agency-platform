"""Tests that _delegate_to_specialist calls DelegationRecorder at delegation boundaries.

Recorder is optional (like audit_logger) — None must not crash.
"""
import pytest
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.specialist import (
    DelegationRegistry,
    SpecialistResult,
    SpecialistStatus,
    SpecialistTask,
)


@dataclass
class FakeConversationState:
    """Minimal ConversationState stand-in for delegation tests."""
    messages: list = field(default_factory=list)
    customer_id: str = "cust_test"
    conversation_id: str = "conv_test"
    business_context: object = field(default_factory=lambda: MagicMock(
        business_name="Test Co", industry="tech",
    ))
    active_delegation: dict = None
    delegation_target: str = None


class FakeMessage:
    def __init__(self, content):
        self.content = content


def _make_ea_with_recorder(recorder=None, specialist_result=None):
    """Build a minimal EA-like object to test delegation recording.

    We don't instantiate the real EA (it pulls in LLM, mem0, etc.).
    Instead we import and patch just the delegation method.
    """
    from src.agents.executive_assistant import ExecutiveAssistant

    with patch.object(ExecutiveAssistant, "__init__", lambda self, **kw: None):
        ea = ExecutiveAssistant.__new__(ExecutiveAssistant)

    ea.customer_id = "cust_test"
    ea.delegation_recorder = recorder
    ea.audit_logger = None
    ea.specialist_timeout = 15.0

    # Minimal memory mock
    ea.memory = AsyncMock()
    ea.memory.search_business_knowledge = AsyncMock(return_value=[])

    # LLM mock for synthesis
    ea.llm = None

    # Registry with a single specialist
    specialist = MagicMock()
    specialist.domain = "finance"
    result = specialist_result or SpecialistResult(
        status=SpecialistStatus.COMPLETED,
        domain="finance",
        payload={"amount": 100},
        confidence=0.9,
        summary_for_ea="Done.",
    )
    registry = MagicMock(spec=DelegationRegistry)
    match = MagicMock()
    match.specialist = specialist
    registry.route = MagicMock(return_value=match)
    registry.get = MagicMock(return_value=specialist)
    registry.execute = AsyncMock(return_value=result)
    ea.delegation_registry = registry

    return ea


class TestRecorderCalledOnFreshDelegation:
    async def test_record_start_called_on_fresh_delegation(self):
        recorder = AsyncMock()
        recorder.record_start = AsyncMock(return_value="rec_123")
        ea = _make_ea_with_recorder(recorder=recorder)

        state = FakeConversationState(
            messages=[FakeMessage("check my invoices")],
        )

        await ea._delegate_to_specialist(state)

        recorder.record_start.assert_awaited_once_with(
            conversation_id="conv_test",
            customer_id="cust_test",
            specialist_domain="finance",
        )

    async def test_record_end_called_on_completed(self):
        recorder = AsyncMock()
        recorder.record_start = AsyncMock(return_value="rec_123")
        ea = _make_ea_with_recorder(recorder=recorder)

        state = FakeConversationState(
            messages=[FakeMessage("check my invoices")],
        )

        await ea._delegate_to_specialist(state)

        recorder.record_end.assert_awaited_once()
        kwargs = recorder.record_end.await_args.kwargs
        assert kwargs["record_id"] == "rec_123"
        assert kwargs["status"] == "completed"
        assert kwargs["confirmation_requested"] is False

    async def test_record_end_called_on_failed(self):
        result = SpecialistResult(
            status=SpecialistStatus.FAILED,
            domain="finance",
            payload={},
            confidence=0.9,
            error="timeout",
        )
        recorder = AsyncMock()
        recorder.record_start = AsyncMock(return_value="rec_456")
        ea = _make_ea_with_recorder(recorder=recorder, specialist_result=result)

        # Need to mock _handle_general_assistance since FAILED falls back
        ea._handle_general_assistance = AsyncMock(return_value=FakeConversationState())

        state = FakeConversationState(
            messages=[FakeMessage("do something")],
        )

        await ea._delegate_to_specialist(state)

        recorder.record_end.assert_awaited_once()
        kwargs = recorder.record_end.await_args.kwargs
        assert kwargs["status"] == "failed"
        assert kwargs["error_message"] == "timeout"


class TestRecorderOnConfirmationFlow:
    async def test_no_record_end_on_needs_confirmation(self):
        """NEEDS_CONFIRMATION doesn't end the delegation — it's mid-flight."""
        result = SpecialistResult(
            status=SpecialistStatus.NEEDS_CONFIRMATION,
            domain="finance",
            payload={"invoice_id": "inv_1"},
            confidence=0.9,
            confirmation_prompt="Delete invoice inv_1?",
            action_risk=MagicMock(value="HIGH"),
        )
        recorder = AsyncMock()
        recorder.record_start = AsyncMock(return_value="rec_789")
        ea = _make_ea_with_recorder(recorder=recorder, specialist_result=result)

        state = FakeConversationState(
            messages=[FakeMessage("delete that invoice")],
        )

        await ea._delegate_to_specialist(state)

        recorder.record_start.assert_awaited_once()
        recorder.record_end.assert_not_awaited()
        # record_id should be stashed in active_delegation
        assert state.active_delegation["record_id"] == "rec_789"

    async def test_record_end_on_confirmation_declined(self):
        recorder = AsyncMock()
        ea = _make_ea_with_recorder(recorder=recorder)

        state = FakeConversationState(
            messages=[FakeMessage("no")],
            active_delegation={
                "domain": "finance",
                "original_task": "delete invoice",
                "prior_turns": [],
                "pending_action": {"invoice_id": "inv_1"},
                "record_id": "rec_789",
            },
        )

        await ea._delegate_to_specialist(state)

        recorder.record_end.assert_awaited_once()
        kwargs = recorder.record_end.await_args.kwargs
        assert kwargs["record_id"] == "rec_789"
        assert kwargs["status"] == "cancelled"
        assert kwargs["confirmation_requested"] is True
        assert kwargs["confirmation_outcome"] == "declined"


class TestRecorderNoneIsSafe:
    async def test_no_crash_when_recorder_is_none(self):
        ea = _make_ea_with_recorder(recorder=None)

        state = FakeConversationState(
            messages=[FakeMessage("check invoices")],
        )

        # Should not raise
        await ea._delegate_to_specialist(state)

    async def test_no_crash_on_confirmation_decline_without_recorder(self):
        ea = _make_ea_with_recorder(recorder=None)

        state = FakeConversationState(
            messages=[FakeMessage("no")],
            active_delegation={
                "domain": "finance",
                "original_task": "delete invoice",
                "prior_turns": [],
                "pending_action": {"invoice_id": "inv_1"},
            },
        )

        # Should not raise
        await ea._delegate_to_specialist(state)
