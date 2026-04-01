"""
E2E: Conversation Intelligence Sweep

Build a conversation with messages and a delegation, run the sweep,
verify summary + tags + quality signals are computed and surfaced
through GET /v1/conversations.
"""
import pytest
from unittest.mock import AsyncMock

from src.intelligence.config import IntelligenceConfig
from src.intelligence.quality import QualityAnalyzer
from src.intelligence.sweep import IntelligenceSweep


pytestmark = pytest.mark.e2e


@pytest.fixture
def mock_summarizer():
    s = AsyncMock()
    s.summarize = AsyncMock(
        return_value="Customer scheduled a meeting for Friday.",
    )
    return s


@pytest.fixture
def intelligence_sweep(
    conversation_repo, delegation_recorder, mock_summarizer,
):
    config = IntelligenceConfig()
    return IntelligenceSweep(
        conversation_repo=conversation_repo,
        delegation_recorder=delegation_recorder,
        summarizer=mock_summarizer,
        quality_analyzer=QualityAnalyzer(config),
        config=config,
    )


class TestIntelligenceSweep:

    async def test_sweep_enriches_conversation(
        self, client, auth_a, intelligence_sweep,
        conversation_repo, mock_summarizer,
    ):
        # Create a conversation via the real message route — this gives
        # us messages + a completed scheduling delegation.
        r = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "Schedule a meeting for Friday at 2pm",
                "channel": "chat",
            },
        )
        conv_id = r.json()["conversation_id"]

        # Follow-up in the same conversation so there are >2 messages.
        await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "Thanks!",
                "channel": "chat",
                "conversation_id": conv_id,
            },
        )

        # Run the sweep
        processed = await intelligence_sweep.run()
        assert processed == 1

        # 1. Summary was generated (LLM summarizer called with messages)
        mock_summarizer.summarize.assert_awaited_once()
        call_msgs = mock_summarizer.summarize.await_args.args[0]
        assert len(call_msgs) == 4  # 2 user + 2 assistant
        conv = conversation_repo._conversations[conv_id]
        assert conv["summary"] == "Customer scheduled a meeting for Friday."

        # 2. Topic tags derived from delegation history
        assert conv["tags"] == ["scheduling"]

        # 3. Quality signals computed
        signals = conv["quality_signals"]
        assert signals is not None
        assert signals["escalation"] is False
        # Delegation completed → not unresolved
        assert signals["unresolved"] is False

    async def test_enriched_data_via_list_endpoint(
        self, client, auth_a, intelligence_sweep,
    ):
        r = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Schedule a meeting", "channel": "chat"},
        )
        assert r.status_code == 200

        await intelligence_sweep.run()

        # 4. GET /v1/conversations returns the enriched data
        r = await client.get("/v1/conversations", headers=auth_a)
        assert r.status_code == 200
        convs = r.json()["conversations"]
        assert len(convs) == 1
        c = convs[0]
        assert c["summary"] == "Customer scheduled a meeting for Friday."
        assert c["tags"] == ["scheduling"]
        assert c["quality_signals"]["escalation"] is False
        assert c["message_count"] == 2
        assert c["specialist_domains"] == ["scheduling"]

    async def test_quality_signals_detect_escalation(
        self, client, auth_a, intelligence_sweep, conversation_repo,
    ):
        r = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "This is terrible, I want to talk to a human",
                "channel": "chat",
            },
        )
        conv_id = r.json()["conversation_id"]

        await intelligence_sweep.run()

        signals = conversation_repo._conversations[conv_id]["quality_signals"]
        assert signals["escalation"] is True
        assert "terrible" in signals["escalation_phrases"]
        assert "talk to a human" in signals["escalation_phrases"]

    async def test_tags_general_when_no_delegation(
        self, client, auth_a, intelligence_sweep, conversation_repo,
    ):
        r = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Just saying hi", "channel": "chat"},
        )
        conv_id = r.json()["conversation_id"]

        await intelligence_sweep.run()

        assert conversation_repo._conversations[conv_id]["tags"] == ["general"]
