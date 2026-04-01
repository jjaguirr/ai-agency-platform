"""
E2E: Proactive Notification Lifecycle

Seed → GET returns it → read → gone. Seed → snooze → gone → expires →
back. Dismiss → permanently gone.
"""
import json
import pytest
from datetime import datetime, timedelta, timezone


pytestmark = pytest.mark.e2e


def _notif(nid: str, *, priority: str = "MEDIUM") -> dict:
    return {
        "id": nid,
        "domain": "ea",
        "trigger_type": "test",
        "priority": priority,
        "title": f"Notification {nid}",
        "message": "Something needs your attention",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


class TestNotificationReadLifecycle:

    async def test_seed_list_read_gone(
        self, client, auth_a, proactive_store,
    ):
        # Seed
        await proactive_store.add_pending_notification(
            "customer_a", _notif("n1"),
        )

        # GET returns it
        r = await client.get("/v1/notifications", headers=auth_a)
        assert r.status_code == 200
        assert [n["id"] for n in r.json()] == ["n1"]

        # Mark read
        r = await client.post("/v1/notifications/n1/read", headers=auth_a)
        assert r.status_code == 204

        # GET no longer includes it
        r = await client.get("/v1/notifications", headers=auth_a)
        assert r.json() == []

    async def test_read_nonexistent_404(self, client, auth_a):
        r = await client.post("/v1/notifications/nope/read", headers=auth_a)
        assert r.status_code == 404


class TestNotificationSnoozeLifecycle:

    async def test_snooze_hides_then_reappears(
        self, client, auth_a, proactive_store, fake_redis,
    ):
        await proactive_store.add_pending_notification(
            "customer_a", _notif("n_snooze"),
        )

        # Snooze for 60 minutes
        r = await client.post(
            "/v1/notifications/n_snooze/snooze",
            headers=auth_a,
            json={"minutes": 60},
        )
        assert r.status_code == 204

        # Excluded while snoozed
        r = await client.get("/v1/notifications", headers=auth_a)
        assert r.json() == []

        # Simulate snooze expiry by rewriting snooze_until into the past.
        # (The route computes "now" fresh each GET; we can't time-travel
        # the request, but we can age the stored record.)
        key = "proactive:customer_a:notifications"
        raw = await fake_redis.hget(key, "n_snooze")
        n = json.loads(raw)
        n["snooze_until"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
        ).isoformat()
        await fake_redis.hset(key, "n_snooze", json.dumps(n))

        # Reappears after expiry
        r = await client.get("/v1/notifications", headers=auth_a)
        ids = [n["id"] for n in r.json()]
        assert ids == ["n_snooze"]
        assert r.json()[0]["status"] == "snoozed"


class TestNotificationDismissLifecycle:

    async def test_dismiss_removes_permanently(
        self, client, auth_a, proactive_store, fake_redis,
    ):
        await proactive_store.add_pending_notification(
            "customer_a", _notif("n_dismiss"),
        )

        r = await client.post(
            "/v1/notifications/n_dismiss/dismiss", headers=auth_a,
        )
        assert r.status_code == 204

        # Gone from the endpoint
        r = await client.get("/v1/notifications", headers=auth_a)
        assert r.json() == []

        # And from the underlying hash — dismiss HDELs, unlike read/snooze
        key = "proactive:customer_a:notifications"
        assert await fake_redis.hget(key, "n_dismiss") is None


class TestNotificationOrdering:

    async def test_priority_then_created_at(
        self, client, auth_a, proactive_store,
    ):
        for nid, prio in [("low", "LOW"), ("high", "HIGH"), ("med", "MEDIUM")]:
            await proactive_store.add_pending_notification(
                "customer_a", _notif(nid, priority=prio),
            )

        r = await client.get("/v1/notifications", headers=auth_a)
        ids = [n["id"] for n in r.json()]
        assert ids == ["high", "med", "low"]
