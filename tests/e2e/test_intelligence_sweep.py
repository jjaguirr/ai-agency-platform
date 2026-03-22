"""E2E: Conversation intelligence sweep.

The IntelligenceSweep runs as a background process. It finds idle
conversations, generates summaries, derives topic tags, and computes
quality signals.  Tests verify the sweep orchestration and that the
enriched data surfaces through the API.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.intelligence.config import IntelligenceConfig
from src.intelligence.quality import QualityAnalyzer
from src.intelligence.sweep import IntelligenceSweep

_SUMMARY = "Customer scheduled a meeting. Resolved successfully."


@pytest.mark.e2e
class TestIntelligenceSweepExecution:
    """IntelligenceSweep.run() orchestrates summarize → tag → quality."""

    @pytest.fixture
    def config(self):
        return IntelligenceConfig(
            summary_idle_threshold_minutes=1,
            sweep_batch_size=5,
        )

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.get_conversations_needing_summary = AsyncMock(return_value=[
            {"id": "conv-001", "customer_id": "cust_a"},
            {"id": "conv-002", "customer_id": "cust_a"},
        ])
        repo.get_messages = AsyncMock(return_value=[
            {"role": "user", "content": "Schedule a meeting tomorrow"},
            {"role": "assistant", "content": "I've scheduled it for 3pm."},
        ])
        repo.set_summary = AsyncMock()
        repo.set_quality_signals = AsyncMock()
        return repo

    @pytest.fixture
    def mock_recorder(self):
        recorder = AsyncMock()
        recorder.update_tags_from_delegations = AsyncMock()
        recorder.get_delegation_statuses = AsyncMock(return_value=["completed"])
        return recorder

    @pytest.fixture
    def mock_summarizer(self):
        summarizer = AsyncMock()
        summarizer.summarize = AsyncMock(return_value=_SUMMARY)
        return summarizer

    @pytest.fixture
    def quality_analyzer(self, config):
        return QualityAnalyzer(config)

    @pytest.fixture
    def sweep(self, mock_repo, mock_recorder, mock_summarizer, quality_analyzer, config):
        return IntelligenceSweep(
            conversation_repo=mock_repo,
            delegation_recorder=mock_recorder,
            summarizer=mock_summarizer,
            quality_analyzer=quality_analyzer,
            config=config,
        )

    async def test_processes_all_conversations(self, sweep, mock_repo):
        count = await sweep.run()
        assert count == 2

    async def test_generates_summaries(self, sweep, mock_repo, mock_summarizer):
        await sweep.run()

        assert mock_summarizer.summarize.call_count == 2
        assert mock_repo.set_summary.call_count == 2

        first_call = mock_repo.set_summary.call_args_list[0]
        assert first_call.kwargs["conversation_id"] == "conv-001"
        assert first_call.kwargs["summary"] == _SUMMARY

        second_call = mock_repo.set_summary.call_args_list[1]
        assert second_call.kwargs["conversation_id"] == "conv-002"
        assert second_call.kwargs["summary"] == _SUMMARY

    async def test_derives_tags(self, sweep, mock_recorder):
        await sweep.run()

        assert mock_recorder.update_tags_from_delegations.call_count == 2

        first_call = mock_recorder.update_tags_from_delegations.call_args_list[0]
        assert first_call.kwargs["customer_id"] == "cust_a"
        assert first_call.kwargs["conversation_id"] == "conv-001"

        second_call = mock_recorder.update_tags_from_delegations.call_args_list[1]
        assert second_call.kwargs["customer_id"] == "cust_a"
        assert second_call.kwargs["conversation_id"] == "conv-002"

    async def test_computes_quality_signals(self, sweep, mock_repo):
        await sweep.run()

        assert mock_repo.set_quality_signals.call_count == 2
        signals = mock_repo.set_quality_signals.call_args_list[0].kwargs["signals"]
        assert signals["escalation"] is False
        assert signals["escalation_phrases"] == []
        assert signals["unresolved"] is False
        assert signals["long"] is False

    async def test_unresolved_when_last_message_from_user(
        self, sweep, mock_repo, mock_recorder,
    ):
        """If the customer's last message has no reply, signal unresolved."""
        mock_repo.get_messages.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "This isn't working"},
        ]
        mock_recorder.get_delegation_statuses.return_value = ["failed"]

        await sweep.run()

        signals = mock_repo.set_quality_signals.call_args_list[0].kwargs["signals"]
        assert signals["unresolved"] is True
        # "this isn't working" is a configured escalation phrase
        assert signals["escalation"] is True
        assert signals["escalation_phrases"] == ["this isn't working"]

    async def test_escalation_detected(self, sweep, mock_repo, mock_recorder):
        """Escalation phrases in user messages trigger the signal."""
        mock_repo.get_messages.return_value = [
            {"role": "user", "content": "I want to talk to a human"},
            {"role": "assistant", "content": "Let me help you."},
        ]
        mock_recorder.get_delegation_statuses.return_value = []

        await sweep.run()

        signals = mock_repo.set_quality_signals.call_args_list[0].kwargs["signals"]
        assert signals["escalation"] is True
        assert signals["escalation_phrases"] == ["talk to a human"]

    async def test_skips_empty_messages(
        self, sweep, mock_repo, mock_summarizer, mock_recorder,
    ):
        """Conversations where get_messages returns None skip summarize/tag/quality."""
        mock_repo.get_messages.return_value = None

        count = await sweep.run()
        assert count == 2  # both conversations attempted

        mock_summarizer.summarize.assert_not_called()
        mock_repo.set_summary.assert_not_called()
        mock_repo.set_quality_signals.assert_not_called()
        mock_recorder.update_tags_from_delegations.assert_not_called()


@pytest.mark.e2e
class TestEnrichedConversationList:
    """GET /v1/conversations returns enriched fields from mocked repo."""

    async def test_conversations_include_summary_and_tags(
        self, client, headers_a, mock_conversation_repo,
    ):
        """The list endpoint returns all enriched fields."""
        mock_conversation_repo.list_conversations_enriched.return_value = [
            {
                "id": "conv-001",
                "channel": "chat",
                "created_at": "2026-03-21T10:00:00Z",
                "updated_at": "2026-03-21T10:05:00Z",
                "message_count": 4,
                "specialist_domains": ["scheduling"],
                "summary": "Customer scheduled a meeting.",
                "tags": ["scheduling"],
                "quality_signals": {
                    "escalation": False,
                    "unresolved": False,
                    "long": False,
                },
            },
        ]

        resp = await client.get("/v1/conversations", headers=headers_a)
        assert resp.status_code == 200
        convs = resp.json()["conversations"]
        assert len(convs) == 1

        conv = convs[0]
        assert conv["id"] == "conv-001"
        assert conv["channel"] == "chat"
        assert conv["message_count"] == 4
        assert conv["specialist_domains"] == ["scheduling"]
        assert conv["summary"] == "Customer scheduled a meeting."
        assert conv["tags"] == ["scheduling"]
        assert conv["quality_signals"]["escalation"] is False
        assert conv["quality_signals"]["unresolved"] is False
        assert conv["quality_signals"]["long"] is False

    async def test_empty_when_no_conversations(
        self, client, headers_a, mock_conversation_repo,
    ):
        mock_conversation_repo.list_conversations_enriched.return_value = []

        resp = await client.get("/v1/conversations", headers=headers_a)
        assert resp.status_code == 200
        assert resp.json()["conversations"] == []
