"""
Tests for WorkflowTracker: Redis-backed per-customer workflow ownership.

Uses fakeredis — no live Redis required.
"""
from __future__ import annotations

import pytest

from src.integrations.n8n.tracking import TrackedWorkflow, WorkflowTracker


@pytest.fixture
def redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def tracker(redis):
    return WorkflowTracker(redis)


class TestTrackAndList:
    async def test_roundtrip(self, tracker):
        wf = TrackedWorkflow(
            workflow_id="w1", name="Weekly Report",
            status="active", created_at="2026-03-20T09:00:00Z",
        )
        await tracker.track("cust_a", wf)
        listed = await tracker.list_workflows("cust_a")
        assert len(listed) == 1
        assert listed[0].workflow_id == "w1"
        assert listed[0].name == "Weekly Report"
        assert listed[0].status == "active"

    async def test_list_returns_empty_for_new_customer(self, tracker):
        result = await tracker.list_workflows("nobody")
        assert result == []

    async def test_track_multiple(self, tracker):
        await tracker.track("c", TrackedWorkflow("w1", "A", "active", "2026-01-01"))
        await tracker.track("c", TrackedWorkflow("w2", "B", "active", "2026-01-02"))
        listed = await tracker.list_workflows("c")
        assert len(listed) == 2


class TestUpdateStatus:
    async def test_changes_persisted_state(self, tracker):
        await tracker.track("c", TrackedWorkflow("w1", "Flow", "active", "2026-01-01"))
        await tracker.update_status("c", "w1", "inactive")
        listed = await tracker.list_workflows("c")
        assert listed[0].status == "inactive"


class TestRemove:
    async def test_deletes_from_hash(self, tracker):
        await tracker.track("c", TrackedWorkflow("w1", "Flow", "active", "2026-01-01"))
        await tracker.remove("c", "w1")
        assert await tracker.list_workflows("c") == []


class TestOverwrite:
    async def test_overwrites_existing_entry(self, tracker):
        await tracker.track("c", TrackedWorkflow("w1", "Old", "active", "2026-01-01"))
        await tracker.track("c", TrackedWorkflow("w1", "New", "active", "2026-01-02"))
        listed = await tracker.list_workflows("c")
        assert len(listed) == 1
        assert listed[0].name == "New"


class TestCustomerIsolation:
    async def test_separate_customers(self, tracker):
        await tracker.track("alice", TrackedWorkflow("w1", "A", "active", "2026-01-01"))
        await tracker.track("bob", TrackedWorkflow("w2", "B", "active", "2026-01-01"))
        alice_wfs = await tracker.list_workflows("alice")
        bob_wfs = await tracker.list_workflows("bob")
        assert len(alice_wfs) == 1
        assert alice_wfs[0].workflow_id == "w1"
        assert len(bob_wfs) == 1
        assert bob_wfs[0].workflow_id == "w2"


class TestFindByName:
    async def test_finds_by_name(self, tracker):
        await tracker.track("c", TrackedWorkflow("w1", "Weekly Report", "active", "2026-01-01"))
        await tracker.track("c", TrackedWorkflow("w2", "Invoice Tracker", "active", "2026-01-02"))
        found = await tracker.find_by_name("c", "invoice")
        assert len(found) == 1
        assert found[0].workflow_id == "w2"

    async def test_find_returns_empty_on_no_match(self, tracker):
        await tracker.track("c", TrackedWorkflow("w1", "Report", "active", "2026-01-01"))
        assert await tracker.find_by_name("c", "xyz") == []
