"""Tests for QualityAnalyzer — rule-based conversation quality signals."""
import pytest

from src.intelligence.config import IntelligenceConfig
from src.intelligence.quality import QualityAnalyzer, QualitySignals


@pytest.fixture
def analyzer():
    return QualityAnalyzer(IntelligenceConfig())


class TestEscalationDetection:
    def test_detects_talk_to_human(self, analyzer):
        messages = [
            {"role": "user", "content": "I want to talk to a human"},
        ]
        signals = analyzer.analyze(messages=messages, delegation_statuses=[])
        assert signals.escalation is True
        assert "talk to a human" in signals.escalation_phrases

    def test_case_insensitive(self, analyzer):
        messages = [
            {"role": "user", "content": "This is TERRIBLE service"},
        ]
        signals = analyzer.analyze(messages=messages, delegation_statuses=[])
        assert signals.escalation is True

    def test_ignores_assistant_messages(self, analyzer):
        messages = [
            {"role": "assistant", "content": "Would you like to talk to a human?"},
        ]
        signals = analyzer.analyze(messages=messages, delegation_statuses=[])
        assert signals.escalation is False

    def test_multiple_phrases_collected(self, analyzer):
        messages = [
            {"role": "user", "content": "This is useless, I'm frustrated"},
        ]
        signals = analyzer.analyze(messages=messages, delegation_statuses=[])
        assert signals.escalation is True
        assert "useless" in signals.escalation_phrases
        assert "frustrated" in signals.escalation_phrases

    def test_no_escalation_on_normal_conversation(self, analyzer):
        messages = [
            {"role": "user", "content": "Can you check my calendar?"},
            {"role": "assistant", "content": "You have a meeting at 3pm."},
        ]
        signals = analyzer.analyze(messages=messages, delegation_statuses=[])
        assert signals.escalation is False
        assert signals.escalation_phrases == []


class TestUnresolvedDetection:
    def test_unresolved_when_last_message_is_user(self, analyzer):
        messages = [
            {"role": "user", "content": "Can you help me?"},
        ]
        signals = analyzer.analyze(messages=messages, delegation_statuses=[])
        assert signals.unresolved is True

    def test_resolved_when_last_message_is_assistant(self, analyzer):
        messages = [
            {"role": "user", "content": "Help me"},
            {"role": "assistant", "content": "Here you go."},
        ]
        signals = analyzer.analyze(
            messages=messages,
            delegation_statuses=["completed"],
        )
        assert signals.unresolved is False

    def test_unresolved_when_no_delegation_completed(self, analyzer):
        messages = [
            {"role": "user", "content": "Do something"},
            {"role": "assistant", "content": "I tried but failed."},
        ]
        signals = analyzer.analyze(
            messages=messages,
            delegation_statuses=["failed"],
        )
        assert signals.unresolved is True

    def test_resolved_with_completed_delegation(self, analyzer):
        messages = [
            {"role": "user", "content": "Check invoices"},
            {"role": "assistant", "content": "Done."},
        ]
        signals = analyzer.analyze(
            messages=messages,
            delegation_statuses=["completed"],
        )
        assert signals.unresolved is False

    def test_unresolved_on_empty_messages(self, analyzer):
        signals = analyzer.analyze(messages=[], delegation_statuses=[])
        assert signals.unresolved is True


class TestLongConversationDetection:
    def test_long_when_exceeds_multiplier(self, analyzer):
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        signals = analyzer.analyze(
            messages=messages,
            delegation_statuses=[],
            avg_turns=5.0,
        )
        assert signals.long is True

    def test_not_long_when_below_threshold(self, analyzer):
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(3)]
        signals = analyzer.analyze(
            messages=messages,
            delegation_statuses=[],
            avg_turns=5.0,
        )
        assert signals.long is False

    def test_not_long_when_no_average_available(self, analyzer):
        """Without avg_turns, can't determine if long — default to False."""
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(100)]
        signals = analyzer.analyze(
            messages=messages,
            delegation_statuses=[],
            avg_turns=None,
        )
        assert signals.long is False


class TestQualitySignalsSerialization:
    def test_to_dict(self):
        signals = QualitySignals(
            escalation=True,
            escalation_phrases=["frustrated"],
            unresolved=False,
            long=True,
        )
        d = signals.to_dict()
        assert d == {
            "escalation": True,
            "escalation_phrases": ["frustrated"],
            "unresolved": False,
            "long": True,
        }
