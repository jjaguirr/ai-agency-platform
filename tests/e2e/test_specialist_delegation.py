"""E2E: Specialist delegation round-trip.

Send a message that triggers specialist delegation. Verify the EA routes
correctly, the delegation is recorded, the response includes the specialist's
domain, and the activity counter for delegations is incremented.
"""
import pytest
from unittest.mock import AsyncMock

from src.api.routes.analytics import _SPECIALIST_DOMAINS

from .conftest import today_iso


@pytest.mark.e2e
class TestDelegationRoundTrip:
    """EA delegates to a specialist, persistence and counters reflect it."""

    async def test_delegation_sets_specialist_domain(
        self, client, headers_a, mock_ea, mock_conversation_repo,
    ):
        """When the EA delegates, the assistant message records the domain."""
        # Simulate delegation: EA sets last_specialist_domain and returns result
        async def _delegate(*, message, channel, conversation_id):
            mock_ea.last_specialist_domain = "scheduling"
            return "I've scheduled your meeting for tomorrow at 3pm."

        mock_ea.handle_customer_interaction = AsyncMock(side_effect=_delegate)

        resp = await client.post(
            "/v1/conversations/message",
            json={
                "message": "Schedule a meeting tomorrow at 3pm",
                "channel": "chat",
            },
            headers=headers_a,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["response"] == "I've scheduled your meeting for tomorrow at 3pm."
        conv_id = body["conversation_id"]

        # Both user and assistant messages persisted for the correct tenant
        assert mock_conversation_repo.append_message.call_count == 2

        user_call = mock_conversation_repo.append_message.call_args_list[0].kwargs
        assert user_call["customer_id"] == "cust_a"
        assert user_call["conversation_id"] == conv_id
        assert user_call["role"] == "user"

        # The assistant message should have specialist_domain set
        assistant_call = mock_conversation_repo.append_message.call_args_list[-1].kwargs
        assert assistant_call["customer_id"] == "cust_a"
        assert assistant_call["conversation_id"] == conv_id
        assert assistant_call["role"] == "assistant"
        assert assistant_call["content"] == "I've scheduled your meeting for tomorrow at 3pm."
        assert assistant_call.get("specialist_domain") == "scheduling"

    async def test_delegation_counter_incremented(
        self, client, headers_a, mock_ea, fake_redis,
    ):
        """Delegation bumps the domain-specific activity counter."""
        async def _delegate(*, message, channel, conversation_id):
            mock_ea.last_specialist_domain = "scheduling"
            return "Done."

        mock_ea.handle_customer_interaction = AsyncMock(side_effect=_delegate)

        await client.post(
            "/v1/conversations/message",
            json={"message": "Schedule something", "channel": "chat"},
            headers=headers_a,
        )

        key = f"activity:cust_a:delegation:scheduling:{today_iso()}"
        val = await fake_redis.get(key)
        assert val is not None
        assert int(val) == 1

    async def test_message_counter_also_incremented(
        self, client, headers_a, mock_ea, fake_redis,
    ):
        """A delegation still counts as a message."""
        async def _delegate(*, message, channel, conversation_id):
            mock_ea.last_specialist_domain = "finance"
            return "Here's your expense report."

        mock_ea.handle_customer_interaction = AsyncMock(side_effect=_delegate)

        await client.post(
            "/v1/conversations/message",
            json={"message": "Show my expenses", "channel": "chat"},
            headers=headers_a,
        )

        msg_key = f"activity:cust_a:messages:{today_iso()}"
        assert int(await fake_redis.get(msg_key)) == 1

        deleg_key = f"activity:cust_a:delegation:finance:{today_iso()}"
        assert int(await fake_redis.get(deleg_key)) == 1

    async def test_no_delegation_no_domain_counter(
        self, client, headers_a, mock_ea, fake_redis,
    ):
        """General assistance (no specialist) doesn't bump delegation counters."""
        mock_ea.handle_customer_interaction.return_value = "Just a regular reply."
        mock_ea.last_specialist_domain = None

        await client.post(
            "/v1/conversations/message",
            json={"message": "Tell me a joke", "channel": "chat"},
            headers=headers_a,
        )

        # Message counter incremented
        msg_key = f"activity:cust_a:messages:{today_iso()}"
        assert int(await fake_redis.get(msg_key)) == 1

        # No delegation counters for any known specialist domain
        for domain in _SPECIALIST_DOMAINS:
            key = f"activity:cust_a:delegation:{domain}:{today_iso()}"
            assert await fake_redis.get(key) is None


@pytest.mark.e2e
class TestActivityEndpoint:
    """GET /v1/analytics/activity reflects delegation counts."""

    async def test_activity_shows_delegation_counts(
        self, client, headers_a, mock_ea, fake_redis,
    ):
        """Activity endpoint includes delegation counts, message total, and date."""
        async def _delegate(*, message, channel, conversation_id):
            mock_ea.last_specialist_domain = "scheduling"
            return "Scheduled."

        mock_ea.handle_customer_interaction = AsyncMock(side_effect=_delegate)

        # Send two messages that delegate to scheduling
        await client.post(
            "/v1/conversations/message",
            json={"message": "Schedule meeting A", "channel": "chat"},
            headers=headers_a,
        )
        await client.post(
            "/v1/conversations/message",
            json={"message": "Schedule meeting B", "channel": "chat"},
            headers=headers_a,
        )

        resp = await client.get("/v1/analytics/activity", headers=headers_a)
        assert resp.status_code == 200
        body = resp.json()
        assert body["date"] == today_iso()
        assert body["messages_processed"] == 2
        assert body["delegations_by_domain"]["scheduling"] == 2
        assert body["proactive_triggers_sent"] == 0
