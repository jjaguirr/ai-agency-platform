"""E2E: Cross-tenant isolation.

Two customers send messages, trigger delegations, create notifications.
Verify each customer can only see their own data across all endpoints.
"""
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock

from src.safety.models import AuditEvent, AuditEventType

from .conftest import today_iso


@pytest.mark.e2e
class TestConversationIsolation:
    """Conversation list and message access are scoped to the authenticated customer."""

    async def test_list_shows_only_own_conversations(
        self, client, headers_a, headers_b, mock_conversation_repo,
    ):
        """Each customer sees only their own conversations."""
        async def _enriched(*, customer_id, limit, offset, tags=None):
            if customer_id == "cust_a":
                return [{"id": "conv-a1", "channel": "chat",
                         "created_at": "2026-03-21T10:00:00Z",
                         "updated_at": "2026-03-21T10:01:00Z",
                         "message_count": 2, "specialist_domains": [],
                         "summary": None, "tags": [], "quality_signals": None}]
            elif customer_id == "cust_b":
                return [{"id": "conv-b1", "channel": "whatsapp",
                         "created_at": "2026-03-21T11:00:00Z",
                         "updated_at": "2026-03-21T11:01:00Z",
                         "message_count": 3, "specialist_domains": ["finance"],
                         "summary": None, "tags": ["finance"], "quality_signals": None}]
            return []

        mock_conversation_repo.list_conversations_enriched = AsyncMock(
            side_effect=_enriched,
        )

        resp_a = await client.get("/v1/conversations", headers=headers_a)
        resp_b = await client.get("/v1/conversations", headers=headers_b)

        convs_a = resp_a.json()["conversations"]
        convs_b = resp_b.json()["conversations"]

        # A sees only A's data
        assert len(convs_a) == 1
        assert convs_a[0]["id"] == "conv-a1"
        assert convs_a[0]["channel"] == "chat"
        assert not any(c["id"] == "conv-b1" for c in convs_a)

        # B sees only B's data
        assert len(convs_b) == 1
        assert convs_b[0]["id"] == "conv-b1"
        assert convs_b[0]["channel"] == "whatsapp"
        assert not any(c["id"] == "conv-a1" for c in convs_b)

        # Verify the repo was called with the correct customer_id each time
        calls = mock_conversation_repo.list_conversations_enriched.call_args_list
        customer_ids_queried = [c.kwargs["customer_id"] for c in calls]
        assert "cust_a" in customer_ids_queried
        assert "cust_b" in customer_ids_queried

    async def test_cross_access_returns_404(
        self, client, headers_a, mock_conversation_repo,
    ):
        """customer_a trying to access customer_b's conversation gets 404."""
        mock_conversation_repo.get_messages.return_value = None

        resp = await client.get(
            "/v1/conversations/conv-b1/messages", headers=headers_a,
        )
        assert resp.status_code == 404
        # Verify repo was queried with cust_a (not cust_b)
        mock_conversation_repo.get_messages.assert_called_once()
        assert mock_conversation_repo.get_messages.call_args.kwargs["customer_id"] == "cust_a"


@pytest.mark.e2e
class TestActivityIsolation:
    """Activity counters are keyed per customer in Redis."""

    async def test_activity_counts_are_per_customer(
        self, client, headers_a, headers_b, mock_ea, fake_redis,
    ):
        """Each customer's activity counter is independent."""
        mock_ea.handle_customer_interaction.return_value = "Ok"
        mock_ea.last_specialist_domain = None

        # customer_a sends 3 messages
        for _ in range(3):
            await client.post(
                "/v1/conversations/message",
                json={"message": "hi", "channel": "chat"},
                headers=headers_a,
            )

        # customer_b sends 1 message
        await client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat"},
            headers=headers_b,
        )

        resp_a = await client.get("/v1/analytics/activity", headers=headers_a)
        resp_b = await client.get("/v1/analytics/activity", headers=headers_b)

        body_a = resp_a.json()
        body_b = resp_b.json()

        assert body_a["messages_processed"] == 3
        assert body_a["date"] == today_iso()
        assert body_b["messages_processed"] == 1
        assert body_b["date"] == today_iso()

        # Verify Redis key-per-customer scheme (not just the API response)
        assert int(await fake_redis.get(f"activity:cust_a:messages:{today_iso()}")) == 3
        assert int(await fake_redis.get(f"activity:cust_b:messages:{today_iso()}")) == 1


@pytest.mark.e2e
class TestNotificationIsolation:
    """Notifications are scoped per customer via ProactiveStateStore."""

    async def test_notifications_scoped_to_customer(
        self, client, headers_a, headers_b, proactive_store,
    ):
        """Each customer sees only their own notifications."""
        await proactive_store.add_pending_notification("cust_a", {
            "domain": "scheduling", "trigger_type": "reminder",
            "priority": "HIGH", "title": "A's reminder",
            "message": "For customer A only",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await proactive_store.add_pending_notification("cust_b", {
            "domain": "finance", "trigger_type": "alert",
            "priority": "URGENT", "title": "B's alert",
            "message": "For customer B only",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        resp_a = await client.get("/v1/notifications", headers=headers_a)
        resp_b = await client.get("/v1/notifications", headers=headers_b)

        notifs_a = resp_a.json()
        notifs_b = resp_b.json()

        assert len(notifs_a) == 1
        assert notifs_a[0]["title"] == "A's reminder"
        assert notifs_a[0]["domain"] == "scheduling"
        assert not any(n["title"] == "B's alert" for n in notifs_a)

        assert len(notifs_b) == 1
        assert notifs_b[0]["title"] == "B's alert"
        assert notifs_b[0]["domain"] == "finance"
        assert not any(n["title"] == "A's reminder" for n in notifs_b)


@pytest.mark.e2e
class TestAuditIsolation:
    """Audit events are scoped per customer via AuditLogger."""

    async def test_audit_events_scoped_to_customer(
        self, client, headers_a, headers_b, audit_logger,
    ):
        """Each customer sees only their own audit events."""
        await audit_logger.log("cust_a", AuditEvent(
            timestamp="2026-03-21T10:00:00Z",
            event_type=AuditEventType.PROMPT_INJECTION_DETECTED,
            correlation_id="corr-a",
            details={"risk_level": "high", "patterns": ["instruction_override"]},
        ))
        await audit_logger.log("cust_b", AuditEvent(
            timestamp="2026-03-21T11:00:00Z",
            event_type=AuditEventType.PII_REDACTED,
            correlation_id="corr-b",
            details={"patterns": ["api_key"]},
        ))

        resp_a = await client.get("/v1/audit", headers=headers_a)
        resp_b = await client.get("/v1/audit", headers=headers_b)

        events_a = resp_a.json()["events"]
        events_b = resp_b.json()["events"]

        assert len(events_a) == 1
        assert events_a[0]["event_type"] == "prompt_injection_detected"
        assert events_a[0]["correlation_id"] == "corr-a"
        assert not any(e["event_type"] == "pii_redacted" for e in events_a)

        assert len(events_b) == 1
        assert events_b[0]["event_type"] == "pii_redacted"
        assert events_b[0]["correlation_id"] == "corr-b"
        assert not any(e["event_type"] == "prompt_injection_detected" for e in events_b)

    async def test_customer_a_cannot_see_customer_b_audit(
        self, client, headers_a, audit_logger,
    ):
        """Audit events for cust_b are invisible to cust_a."""
        await audit_logger.log("cust_b", AuditEvent(
            timestamp="2026-03-21T11:00:00Z",
            event_type=AuditEventType.HIGH_RISK_ACTION_REQUESTED,
            correlation_id="corr-b-secret",
            details={"domain": "finance"},
        ))

        resp = await client.get("/v1/audit", headers=headers_a)
        events = resp.json()["events"]
        assert len(events) == 0


@pytest.mark.e2e
class TestSettingsIsolation:
    """Settings are stored per customer in Redis."""

    async def test_settings_do_not_leak(
        self, client, headers_a, headers_b,
    ):
        """customer_a's settings are invisible to customer_b."""
        put_resp = await client.put(
            "/v1/settings",
            json={
                "working_hours": {"start": "06:00", "end": "22:00", "timezone": "UTC"},
                "briefing": {"enabled": True, "time": "08:00"},
                "proactive": {"priority_threshold": "LOW", "daily_cap": 50,
                              "idle_nudge_minutes": 120},
                "personality": {"tone": "friendly", "language": "en", "name": "A-Bot"},
                "connected_services": {"calendar": True, "n8n": False},
            },
            headers=headers_a,
        )
        assert put_resp.status_code == 200

        resp_b = await client.get("/v1/settings", headers=headers_b)
        body_b = resp_b.json()
        # B gets defaults, not A's settings
        assert body_b["working_hours"]["start"] == "09:00"
        assert body_b["working_hours"]["end"] == "18:00"
        assert body_b["personality"]["name"] == "Assistant"
        assert body_b["personality"]["tone"] == "professional"
        assert body_b["briefing"]["enabled"] is True
