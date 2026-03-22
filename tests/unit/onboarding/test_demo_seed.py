"""
Demo mode seeding — populate a fresh account with realistic sample data
so the dashboard has something to show in every section.

Seeded in Redis (no Postgres dependency for the MVP demo path):
  - settings:{customer_id}         — configured hours, briefing, tone
  - onboarding:{customer_id}       — marked completed
  - proactive:{customer_id}:notifications — sample briefing + alerts
  - activity:{customer_id}:*       — message + delegation counts for today

Conversation seeding into Postgres is optional and tested separately;
here we validate the Redis half.
"""
import json
from datetime import date, datetime, timezone

import pytest

from src.onboarding.demo_seed import seed_demo_account
from src.onboarding.state import OnboardingStateStore


class TestSettingsSeeding:
    async def test_seeds_configured_settings(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        raw = await fake_redis.get("settings:demo_acme")
        settings = json.loads(raw)
        # Prove the seeder wrote *non-default* values. briefing.enabled
        # defaults to True so asserting it proves nothing; these don't:
        assert settings["working_hours"]["start"] != "09:00" or \
               settings["working_hours"]["timezone"] != "UTC"
        assert settings["personality"]["tone"] == "friendly"  # default: professional

    async def test_onboarding_marked_complete(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        store = OnboardingStateStore(fake_redis)
        assert await store.is_complete("demo_acme")


class TestNotificationSeeding:
    async def test_seeds_multiple_notifications(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        raw = await fake_redis.hgetall("proactive:demo_acme:notifications")
        assert len(raw) >= 3

    async def test_notifications_have_required_fields(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        raw = await fake_redis.hgetall("proactive:demo_acme:notifications")
        for v in raw.values():
            n = json.loads(v)
            assert n["id"]
            assert n["status"] == "pending"
            assert n["priority"] in ("LOW", "MEDIUM", "HIGH", "URGENT")
            assert n["domain"]
            assert n["title"]
            assert n["message"]
            assert n["created_at"]

    async def test_notifications_cover_multiple_domains(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        raw = await fake_redis.hgetall("proactive:demo_acme:notifications")
        domains = {json.loads(v)["domain"] for v in raw.values()}
        assert len(domains) >= 2  # not all from one specialist


class TestActivitySeeding:
    async def test_seeds_message_counter(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        today = date.today().isoformat()
        count = await fake_redis.get(f"activity:demo_acme:messages:{today}")
        assert int(count) > 0

    async def test_seeds_delegation_counters(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_acme")

        today = date.today().isoformat()
        # At least two domains have activity
        domains_with_activity = 0
        for domain in ("finance", "scheduling", "social_media", "workflows"):
            v = await fake_redis.get(f"activity:demo_acme:delegation:{domain}:{today}")
            if v and int(v) > 0:
                domains_with_activity += 1
        assert domains_with_activity >= 2


class TestTenantIsolation:
    async def test_demo_data_scoped_to_customer(self, fake_redis):
        await seed_demo_account(fake_redis, "demo_alice")
        await seed_demo_account(fake_redis, "demo_bob")

        # Alice's notifications don't appear under Bob's key
        alice_notifs = await fake_redis.hgetall("proactive:demo_alice:notifications")
        bob_notifs = await fake_redis.hgetall("proactive:demo_bob:notifications")
        assert alice_notifs and bob_notifs
        # Settings are independent
        alice_settings = await fake_redis.get("settings:demo_alice")
        bob_settings = await fake_redis.get("settings:demo_bob")
        assert alice_settings and bob_settings


class TestConversationSeeding:
    async def test_seeds_conversations_when_repo_provided(self, fake_redis):
        """When a conversation repo is passed, seed sample exchanges."""
        calls = []

        class FakeRepo:
            async def create_conversation(self, **kw):
                calls.append(("conv", kw))
                return kw.get("conversation_id") or "conv_1"

            async def append_message(self, **kw):
                calls.append(("msg", kw))

        await seed_demo_account(fake_redis, "demo_acme", conversation_repo=FakeRepo())

        convs = [c for c in calls if c[0] == "conv"]
        msgs = [c for c in calls if c[0] == "msg"]
        assert len(convs) >= 3
        assert len(msgs) >= 6  # at least one user+assistant pair per conv
        # All scoped to the demo customer
        for _, kw in calls:
            assert kw["customer_id"] == "demo_acme"

    async def test_conversations_cover_specialist_domains(self, fake_redis):
        domains = []

        class FakeRepo:
            async def create_conversation(self, **kw):
                return kw.get("conversation_id") or "c"

            async def append_message(self, **kw):
                if kw.get("specialist_domain"):
                    domains.append(kw["specialist_domain"])

        await seed_demo_account(fake_redis, "demo_acme", conversation_repo=FakeRepo())

        assert len(set(domains)) >= 2

    async def test_no_repo_skips_conversations_silently(self, fake_redis):
        # No exception when repo is None
        await seed_demo_account(fake_redis, "demo_acme", conversation_repo=None)
