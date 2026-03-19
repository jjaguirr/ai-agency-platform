"""Tests for the inbound message hook — extraction + interaction tracking."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from src.proactive.inbound import process_inbound_message
from src.proactive.state import ProactiveStateStore


@pytest.fixture
def store(fake_redis):
    return ProactiveStateStore(fake_redis)


CID = "cust_hook_test"

# Thursday 2026-03-19 10:00 UTC
_NOW = datetime(2026, 3, 19, 10, 0, tzinfo=timezone.utc)


class TestProcessInboundMessage:
    async def test_updates_last_interaction_time(self, store):
        await process_inbound_message(CID, "Hello there", store, now=_NOW)
        last = await store.get_last_interaction_time(CID)
        assert last is not None

    async def test_extracts_follow_up_and_stores(self, store):
        await process_inbound_message(
            CID, "Remind me to call John on Friday", store, now=_NOW,
        )
        follow_ups = await store.list_follow_ups(CID)
        assert len(follow_ups) == 1
        assert "call John" in follow_ups[0]["commitment"]
        assert "deadline" in follow_ups[0]

    async def test_no_follow_up_for_plain_message(self, store):
        await process_inbound_message(CID, "What's the weather?", store, now=_NOW)
        follow_ups = await store.list_follow_ups(CID)
        assert len(follow_ups) == 0

    async def test_multiple_follow_ups_from_one_message(self, store):
        # Two commitment sentences
        msg = "Send the proposal by Wednesday. I'll call the client on Friday."
        await process_inbound_message(CID, msg, store, now=_NOW)
        follow_ups = await store.list_follow_ups(CID)
        assert len(follow_ups) == 2

    async def test_does_not_crash_on_empty_message(self, store):
        await process_inbound_message(CID, "", store, now=_NOW)
        assert await store.list_follow_ups(CID) == []

    async def test_does_not_crash_when_store_is_none(self):
        """If proactive_state_store is None (not configured), skip silently."""
        await process_inbound_message(CID, "Remind me to do X by Friday", None, now=_NOW)

    async def test_vague_commitment_not_stored(self, store):
        await process_inbound_message(
            CID, "I should probably call them sometime", store, now=_NOW,
        )
        assert await store.list_follow_ups(CID) == []


class TestInteractionInConversationsRoute:
    """Verify the hook is called from the API conversations endpoint."""

    async def test_post_message_calls_hook(self, fake_redis):
        import os
        os.environ.setdefault(
            "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
        )
        from unittest.mock import MagicMock, patch
        import httpx
        from src.api.app import create_app
        from src.api.auth import create_token
        from src.api.ea_registry import EARegistry

        store = ProactiveStateStore(fake_redis)
        mock_ea = AsyncMock()
        mock_ea.customer_id = "cust_abc"
        mock_ea.handle_customer_interaction = AsyncMock(return_value="Sure thing")

        app = create_app(
            ea_registry=EARegistry(factory=MagicMock(return_value=mock_ea), max_size=10),
            orchestrator=AsyncMock(),
            whatsapp_manager=MagicMock(),
            redis_client=fake_redis,
            proactive_state_store=store,
        )
        token = create_token("cust_abc")

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/conversations/message",
                json={"message": "Remind me to call John on Friday", "channel": "chat"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200

        # Follow-up should be stored
        follow_ups = await store.list_follow_ups("cust_abc")
        assert len(follow_ups) == 1
        assert "call John" in follow_ups[0]["commitment"]

        # Last interaction should be updated
        last = await store.get_last_interaction_time("cust_abc")
        assert last is not None
