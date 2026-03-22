"""
Onboarding state store — Redis-backed per-customer wizard progress.

Key: onboarding:{customer_id}
State machine: not_started → in_progress → completed
Step tracking so a dropped-off customer resumes where they left off.
"""
import json

import pytest

from src.onboarding.state import (
    OnboardingState,
    OnboardingStateStore,
    OnboardingStep,
)


class TestInitialState:
    async def test_unseen_customer_is_not_started(self, fake_redis):
        store = OnboardingStateStore(fake_redis)

        state = await store.get("cust_new")

        assert state.status == "not_started"
        assert state.step == OnboardingStep.INTRO

    async def test_initialize_sets_not_started(self, fake_redis):
        store = OnboardingStateStore(fake_redis)

        await store.initialize("cust_fresh")
        state = await store.get("cust_fresh")

        assert state.status == "not_started"
        assert state.step == OnboardingStep.INTRO
        assert state.collected == {}


class TestProgression:
    async def test_advance_moves_to_next_step(self, fake_redis):
        store = OnboardingStateStore(fake_redis)
        await store.initialize("cust_a")

        await store.advance("cust_a", OnboardingStep.BUSINESS_CONTEXT)
        state = await store.get("cust_a")

        assert state.status == "in_progress"
        assert state.step == OnboardingStep.BUSINESS_CONTEXT

    async def test_advance_stores_collected_data(self, fake_redis):
        store = OnboardingStateStore(fake_redis)
        await store.initialize("cust_a")

        await store.advance(
            "cust_a",
            OnboardingStep.PREFERENCES,
            collected={"business_context": "small jewelry shop"},
        )
        state = await store.get("cust_a")

        assert state.collected["business_context"] == "small jewelry shop"

    async def test_advance_merges_collected_data(self, fake_redis):
        """Each step adds to collected, not replaces."""
        store = OnboardingStateStore(fake_redis)
        await store.initialize("cust_a")

        await store.advance("cust_a", OnboardingStep.BUSINESS_CONTEXT,
                            collected={"business_context": "restaurant"})
        await store.advance("cust_a", OnboardingStep.PREFERENCES,
                            collected={"timezone": "America/New_York"})

        state = await store.get("cust_a")
        assert state.collected["business_context"] == "restaurant"
        assert state.collected["timezone"] == "America/New_York"

    async def test_complete_marks_done(self, fake_redis):
        store = OnboardingStateStore(fake_redis)
        await store.initialize("cust_a")

        await store.complete("cust_a")
        state = await store.get("cust_a")

        assert state.status == "completed"

    async def test_is_complete_shorthand(self, fake_redis):
        store = OnboardingStateStore(fake_redis)

        assert not await store.is_complete("cust_a")
        await store.complete("cust_a")
        assert await store.is_complete("cust_a")


class TestResume:
    async def test_resumes_at_stored_step(self, fake_redis):
        """Customer drops off mid-flow, comes back — state persists."""
        store = OnboardingStateStore(fake_redis)
        await store.initialize("cust_resume")
        await store.advance("cust_resume", OnboardingStep.PREFERENCES,
                            collected={"business_context": "consulting"})

        # New store instance — simulates process restart
        fresh_store = OnboardingStateStore(fake_redis)
        state = await fresh_store.get("cust_resume")

        assert state.status == "in_progress"
        assert state.step == OnboardingStep.PREFERENCES
        assert state.collected["business_context"] == "consulting"


class TestTenantIsolation:
    async def test_customers_have_independent_state(self, fake_redis):
        store = OnboardingStateStore(fake_redis)

        await store.advance("cust_alice", OnboardingStep.QUICK_WIN)
        await store.complete("cust_bob")

        alice = await store.get("cust_alice")
        bob = await store.get("cust_bob")
        carol = await store.get("cust_carol")

        assert alice.status == "in_progress"
        assert alice.step == OnboardingStep.QUICK_WIN
        assert bob.status == "completed"
        assert carol.status == "not_started"

    async def test_redis_key_is_customer_scoped(self, fake_redis):
        store = OnboardingStateStore(fake_redis)
        await store.advance("cust_xyz", OnboardingStep.BUSINESS_CONTEXT)

        raw = await fake_redis.get("onboarding:cust_xyz")
        assert raw is not None
        parsed = json.loads(raw)
        assert parsed["step"] == OnboardingStep.BUSINESS_CONTEXT.value


class TestCompletionNeverRepeats:
    async def test_completed_stays_completed_after_initialize(self, fake_redis):
        """Re-provisioning a completed customer must not reset onboarding."""
        store = OnboardingStateStore(fake_redis)
        await store.complete("cust_done")

        await store.initialize("cust_done")  # idempotent no-op

        assert await store.is_complete("cust_done")
