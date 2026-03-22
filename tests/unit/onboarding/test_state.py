"""Tests for OnboardingStateStore — Redis-backed onboarding state machine."""
import json

import pytest

from .conftest import CID, CID_B


class TestInitialize:
    @pytest.mark.asyncio
    async def test_sets_not_started(self, store):
        await store.initialize(CID)
        state = await store.get(CID)
        assert state.status == "not_started"

    @pytest.mark.asyncio
    async def test_step_zero(self, store):
        await store.initialize(CID)
        state = await store.get(CID)
        assert state.current_step == 0

    @pytest.mark.asyncio
    async def test_empty_collected(self, store):
        await store.initialize(CID)
        state = await store.get(CID)
        assert state.collected == {}

    @pytest.mark.asyncio
    async def test_idempotent(self, store):
        await store.initialize(CID)
        await store.initialize(CID)
        state = await store.get(CID)
        assert state.status == "not_started"
        assert state.current_step == 0


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_unknown_when_no_key(self, store):
        status = await store.get_status(CID)
        assert status == "unknown"

    @pytest.mark.asyncio
    async def test_returns_not_started_after_init(self, store):
        await store.initialize(CID)
        assert await store.get_status(CID) == "not_started"

    @pytest.mark.asyncio
    async def test_returns_in_progress_after_advance(self, store):
        await store.initialize(CID)
        await store.advance(CID)
        assert await store.get_status(CID) == "in_progress"

    @pytest.mark.asyncio
    async def test_returns_completed_after_mark(self, store):
        await store.initialize(CID)
        await store.mark_completed(CID)
        assert await store.get_status(CID) == "completed"


class TestGet:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_key(self, store):
        assert await store.get(CID) is None

    @pytest.mark.asyncio
    async def test_returns_state_after_init(self, store):
        await store.initialize(CID)
        state = await store.get(CID)
        assert state is not None
        assert state.status == "not_started"


class TestAdvance:
    @pytest.mark.asyncio
    async def test_first_advance_transitions_to_in_progress(self, store):
        await store.initialize(CID)
        state = await store.advance(CID)
        assert state.status == "in_progress"

    @pytest.mark.asyncio
    async def test_increments_step(self, store):
        await store.initialize(CID)
        state = await store.advance(CID)
        assert state.current_step == 1
        state = await store.advance(CID)
        assert state.current_step == 2

    @pytest.mark.asyncio
    async def test_merges_collected_data(self, store):
        await store.initialize(CID)
        await store.advance(CID, {"business_type": "restaurant"})
        state = await store.advance(CID, {"timezone": "US/Eastern"})
        assert state.collected["business_type"] == "restaurant"
        assert state.collected["timezone"] == "US/Eastern"

    @pytest.mark.asyncio
    async def test_advance_past_last_step_marks_completed(self, store):
        await store.initialize(CID)
        # Advance through all 5 steps (0→1, 1→2, 2→3, 3→4, 4→completed)
        for _ in range(5):
            state = await store.advance(CID)
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_advance_sets_completed_at(self, store):
        await store.initialize(CID)
        for _ in range(5):
            state = await store.advance(CID)
        assert state.completed_at is not None

    @pytest.mark.asyncio
    async def test_advance_sets_started_at_on_first(self, store):
        await store.initialize(CID)
        state = await store.advance(CID)
        assert state.started_at is not None

    @pytest.mark.asyncio
    async def test_advance_preserves_started_at(self, store):
        await store.initialize(CID)
        state1 = await store.advance(CID)
        state2 = await store.advance(CID)
        assert state2.started_at == state1.started_at


class TestMarkCompleted:
    @pytest.mark.asyncio
    async def test_force_completes(self, store):
        await store.initialize(CID)
        await store.mark_completed(CID)
        state = await store.get(CID)
        assert state.status == "completed"
        assert state.completed_at is not None

    @pytest.mark.asyncio
    async def test_idempotent(self, store):
        await store.initialize(CID)
        await store.mark_completed(CID)
        await store.mark_completed(CID)
        assert await store.get_status(CID) == "completed"


class TestMarkInterrupted:
    @pytest.mark.asyncio
    async def test_sets_interrupted_flag(self, store):
        await store.initialize(CID)
        await store.advance(CID)
        await store.mark_interrupted(CID)
        state = await store.get(CID)
        assert state.interrupted is True

    @pytest.mark.asyncio
    async def test_preserves_current_step(self, store):
        await store.initialize(CID)
        await store.advance(CID)  # step → 1
        await store.advance(CID)  # step → 2
        await store.mark_interrupted(CID)
        state = await store.get(CID)
        assert state.current_step == 2


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_different_customers_independent(self, store):
        await store.initialize(CID)
        await store.initialize(CID_B)
        await store.advance(CID, {"business_type": "restaurant"})
        await store.advance(CID)

        state_a = await store.get(CID)
        state_b = await store.get(CID_B)

        assert state_a.current_step == 2
        assert state_a.collected.get("business_type") == "restaurant"
        assert state_b.current_step == 0
        assert state_b.collected == {}
