"""E2E: Proactive notification lifecycle.

Seed notifications via ProactiveStateStore (real, backed by fakeredis),
then exercise the pull-based API: list, read, snooze, dismiss, snooze
expiry.
"""
from datetime import datetime, timedelta, timezone

import pytest


def _make_notification(*, domain="scheduling", priority="HIGH", title="Meeting reminder"):
    return {
        "domain": domain,
        "trigger_type": "follow_up",
        "priority": priority,
        "title": title,
        "message": f"You have a pending {domain} item.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.e2e
class TestNotificationList:
    """GET /v1/notifications returns pending notifications."""

    async def test_empty_list(self, client, headers_a):
        resp = await client.get("/v1/notifications", headers=headers_a)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_seeded_notification_appears(
        self, client, headers_a, proactive_store,
    ):
        notif = _make_notification()
        notif_id = await proactive_store.add_pending_notification("cust_a", notif)

        resp = await client.get("/v1/notifications", headers=headers_a)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == notif_id
        assert items[0]["domain"] == "scheduling"
        assert items[0]["trigger_type"] == "follow_up"
        assert items[0]["priority"] == "HIGH"
        assert items[0]["title"] == "Meeting reminder"
        assert items[0]["message"] == "You have a pending scheduling item."
        assert items[0]["status"] == "pending"


@pytest.mark.e2e
class TestMarkRead:
    """POST /v1/notifications/{id}/read removes from pending list."""

    async def test_mark_read_removes_from_list(
        self, client, headers_a, proactive_store,
    ):
        notif_id = await proactive_store.add_pending_notification(
            "cust_a", _make_notification(),
        )

        # Mark read
        resp = await client.post(
            f"/v1/notifications/{notif_id}/read", headers=headers_a,
        )
        assert resp.status_code == 204

        # No longer in pending list
        resp = await client.get("/v1/notifications", headers=headers_a)
        assert resp.json() == []

    async def test_mark_read_nonexistent_returns_404(self, client, headers_a):
        resp = await client.post(
            "/v1/notifications/notif_doesnotexist/read", headers=headers_a,
        )
        assert resp.status_code == 404


@pytest.mark.e2e
class TestSnooze:
    """Snoozed notifications are excluded until snooze_until expires."""

    async def test_snoozed_excluded_from_list(
        self, client, headers_a, proactive_store,
    ):
        notif_id = await proactive_store.add_pending_notification(
            "cust_a", _make_notification(),
        )

        resp = await client.post(
            f"/v1/notifications/{notif_id}/snooze",
            json={"minutes": 60},
            headers=headers_a,
        )
        assert resp.status_code == 204

        resp = await client.get("/v1/notifications", headers=headers_a)
        assert resp.json() == []

    async def test_expired_snooze_reappears(
        self, client, headers_a, proactive_store, fake_redis,
    ):
        """Snoozed notification reappears after snooze_until passes.

        We rewrite the Redis hash directly to set snooze_until in the past
        because the store reads datetime.now() at query time.
        """
        notif_id = await proactive_store.add_pending_notification(
            "cust_a", _make_notification(),
        )

        await client.post(
            f"/v1/notifications/{notif_id}/snooze",
            json={"minutes": 1},
            headers=headers_a,
        )

        # Rewrite snooze_until to the past in the underlying Redis hash
        import json
        key = "proactive:cust_a:notifications"
        raw = await fake_redis.hget(key, notif_id)
        data = json.loads(raw)
        data["snooze_until"] = (
            datetime.now(timezone.utc) - timedelta(minutes=5)
        ).isoformat()
        await fake_redis.hset(key, notif_id, json.dumps(data))

        resp = await client.get("/v1/notifications", headers=headers_a)
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == notif_id
        assert items[0]["status"] == "snoozed"
        assert items[0]["domain"] == "scheduling"


@pytest.mark.e2e
class TestDismiss:
    """POST /v1/notifications/{id}/dismiss deletes the notification."""

    async def test_dismiss_removes_permanently(
        self, client, headers_a, proactive_store,
    ):
        notif_id = await proactive_store.add_pending_notification(
            "cust_a", _make_notification(),
        )

        resp = await client.post(
            f"/v1/notifications/{notif_id}/dismiss", headers=headers_a,
        )
        assert resp.status_code == 204

        resp = await client.get("/v1/notifications", headers=headers_a)
        assert resp.json() == []

    async def test_dismiss_nonexistent_returns_404(self, client, headers_a):
        resp = await client.post(
            "/v1/notifications/notif_ghost/dismiss", headers=headers_a,
        )
        assert resp.status_code == 404


@pytest.mark.e2e
class TestNotificationOrdering:
    """Notifications sort by priority descending."""

    async def test_higher_priority_first(
        self, client, headers_a, proactive_store,
    ):
        await proactive_store.add_pending_notification(
            "cust_a", _make_notification(priority="LOW", title="Low prio"),
        )
        await proactive_store.add_pending_notification(
            "cust_a", _make_notification(priority="URGENT", title="Urgent prio"),
        )
        await proactive_store.add_pending_notification(
            "cust_a", _make_notification(priority="MEDIUM", title="Medium prio"),
        )

        resp = await client.get("/v1/notifications", headers=headers_a)
        items = resp.json()
        assert len(items) == 3
        assert items[0]["priority"] == "URGENT"
        assert items[0]["title"] == "Urgent prio"
        assert items[1]["priority"] == "MEDIUM"
        assert items[1]["title"] == "Medium prio"
        assert items[2]["priority"] == "LOW"
        assert items[2]["title"] == "Low prio"
