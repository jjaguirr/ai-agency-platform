"""Tests for WorkflowFailureBehavior — poll n8n executions on each tick.

This behavior lives in its own file because it pulls in N8nClient
(→ httpx). Every other behavior is dependency-light and lives in
behaviors.py; this one gets a separate import graph.

The client is injected via a factory: each customer has their own
n8n base_url + api_key in WorkflowStore, so the behavior can't hold a
single client instance. Factory pattern keeps construction per tick
and per customer without the behavior knowing about httpx.
"""
import pytest

from src.proactive.state import ProactiveStateStore
from src.proactive.triggers import Priority
from src.proactive.workflow_behavior import WorkflowFailureBehavior
from src.workflows.client import N8nError
from src.workflows.store import WorkflowStore


CID = "cust_workflows"


# --- Fakes ------------------------------------------------------------------

class FakeN8nClient:
    """Conforms to N8nClient.list_executions by shape. Executions are
    newest-first (n8n default ordering) so executions[0] is the most
    recent run."""

    def __init__(self, executions_by_workflow: dict[str, list[dict]]):
        self._execs = executions_by_workflow
        self.closed = False

    async def list_executions(self, workflow_id: str) -> list[dict]:
        return list(self._execs.get(workflow_id, []))

    async def aclose(self) -> None:
        self.closed = True


def _client_factory(executions_by_workflow: dict[str, list[dict]]):
    """Build a factory that ignores base_url/api_key and returns a fake
    with the given executions."""
    created: list[FakeN8nClient] = []

    def factory(base_url: str, api_key: str) -> FakeN8nClient:
        client = FakeN8nClient(executions_by_workflow)
        created.append(client)
        return client

    factory.created = created  # type: ignore[attr-defined]
    return factory


class RaisingClient:
    def __init__(self, exc: Exception):
        self._exc = exc

    async def list_executions(self, workflow_id: str) -> list[dict]:
        raise self._exc

    async def aclose(self) -> None:
        pass


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def state(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def wf_store(fake_redis):
    return WorkflowStore(fake_redis)


@pytest.fixture
async def seeded_wf_store(wf_store):
    """One customer, one workflow, n8n config present."""
    await wf_store.set_config(CID, base_url="https://n8n.example", api_key="sk_test")
    await wf_store.add_workflow(CID, "wf_100", "Daily sync", "active")
    return wf_store


# --- Happy path: new failure → trigger --------------------------------------

class TestNewFailureTriggers:

    async def test_new_error_execution_yields_high_priority_trigger(
        self, state, seeded_wf_store,
    ):
        factory = _client_factory({
            "wf_100": [
                {"id": "exec_3", "status": "error", "finished": True},
                {"id": "exec_2", "status": "success", "finished": True},
                {"id": "exec_1", "status": "success", "finished": True},
            ],
        })
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)

        triggers = await behavior.check(CID)

        assert len(triggers) == 1
        t = triggers[0]
        assert t.domain == "workflow"
        assert t.trigger_type == "workflow_failure"
        assert t.priority == Priority.HIGH
        assert t.payload["workflow_id"] == "wf_100"
        assert t.payload["execution_id"] == "exec_3"
        # Name in the message so the customer knows which automation broke.
        assert "Daily sync" in t.suggested_message
        # Cooldown keyed per-execution so the same failure doesn't nag.
        assert t.cooldown_key is not None
        assert "exec_3" in t.cooldown_key

    async def test_failed_status_also_triggers(self, state, seeded_wf_store):
        """n8n uses both 'error' and 'failed' depending on the failure
        mode. Either one should fire."""
        factory = _client_factory({
            "wf_100": [{"id": "exec_1", "status": "failed"}],
        })
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        triggers = await behavior.check(CID)
        assert len(triggers) == 1

    async def test_success_executions_do_not_trigger(
        self, state, seeded_wf_store,
    ):
        factory = _client_factory({
            "wf_100": [
                {"id": "exec_2", "status": "success"},
                {"id": "exec_1", "status": "success"},
            ],
        })
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        assert await behavior.check(CID) == []

    async def test_no_executions_yet(self, state, seeded_wf_store):
        factory = _client_factory({"wf_100": []})
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        assert await behavior.check(CID) == []


# --- Last-seen tracking: same failure doesn't re-fire ----------------------

class TestLastSeenTracking:
    """First tick reports the failure; subsequent ticks stay silent until
    a NEW execution fails. Without this the heartbeat would nag about the
    same broken workflow every five minutes."""

    async def test_same_failure_silent_on_second_tick(
        self, state, seeded_wf_store,
    ):
        executions = {
            "wf_100": [{"id": "exec_1", "status": "error"}],
        }
        factory = _client_factory(executions)
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)

        first = await behavior.check(CID)
        assert len(first) == 1

        second = await behavior.check(CID)
        assert second == []

    async def test_new_failure_after_seen_success_triggers(
        self, state, seeded_wf_store,
    ):
        executions = {"wf_100": [{"id": "exec_1", "status": "success"}]}
        factory = _client_factory(executions)
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)

        # Tick 1: one successful run, nothing to report — but it was seen.
        assert await behavior.check(CID) == []

        # Tick 2: a new failure appears at the head of the list.
        executions["wf_100"].insert(0, {"id": "exec_2", "status": "error"})
        triggers = await behavior.check(CID)
        assert len(triggers) == 1
        assert triggers[0].payload["execution_id"] == "exec_2"

    async def test_last_seen_survives_behavior_reinstantiation(
        self, state, seeded_wf_store,
    ):
        """Heartbeat rebuilds behaviors each tick (_get_behaviors returns
        fresh instances). Tracking must live in Redis, not instance state."""
        executions = {"wf_100": [{"id": "exec_1", "status": "error"}]}
        factory = _client_factory(executions)

        b1 = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        assert len(await b1.check(CID)) == 1

        b2 = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        assert await b2.check(CID) == []

    async def test_multiple_new_failures_all_reported(
        self, state, seeded_wf_store,
    ):
        """A workflow that's been dead for a few runs before we noticed —
        report every failure we haven't seen, not just the latest one."""
        factory = _client_factory({
            "wf_100": [
                {"id": "exec_3", "status": "error"},
                {"id": "exec_2", "status": "error"},
                {"id": "exec_1", "status": "success"},
            ],
        })
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        triggers = await behavior.check(CID)
        reported = {t.payload["execution_id"] for t in triggers}
        assert reported == {"exec_3", "exec_2"}


# --- Graceful degradation ---------------------------------------------------

class TestDegradation:

    async def test_no_n8n_config_returns_empty(self, state, wf_store):
        """Customer never set up n8n → nothing to poll. Not an error."""
        await wf_store.add_workflow(CID, "wf_100", "Orphan", "active")
        # Note: no set_config call.
        factory = _client_factory({"wf_100": [{"id": "e1", "status": "error"}]})
        behavior = WorkflowFailureBehavior(wf_store, state, factory)
        assert await behavior.check(CID) == []

    async def test_no_workflows_returns_empty(self, state, wf_store):
        await wf_store.set_config(CID, base_url="https://n8n.example", api_key="k")
        # No add_workflow.
        factory = _client_factory({})
        behavior = WorkflowFailureBehavior(wf_store, state, factory)
        assert await behavior.check(CID) == []

    async def test_n8n_error_logs_and_returns_empty(
        self, state, seeded_wf_store, caplog,
    ):
        """n8n unreachable → degrade to no-trigger, not crash. The
        heartbeat must survive a dead n8n instance."""
        def factory(base_url, api_key):
            return RaisingClient(N8nError("connection refused"))

        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        with caplog.at_level("WARNING"):
            triggers = await behavior.check(CID)
        assert triggers == []
        assert any("wf_100" in r.message for r in caplog.records)

    async def test_one_workflow_failing_does_not_block_others(
        self, state, wf_store,
    ):
        """Per-workflow error isolation. A 401 on workflow A must not
        hide a real failure on workflow B."""
        await wf_store.set_config(CID, base_url="https://n8n.example", api_key="k")
        await wf_store.add_workflow(CID, "wf_bad", "Broken auth", "active")
        await wf_store.add_workflow(CID, "wf_good", "Working", "active")

        class SelectiveClient:
            async def list_executions(self, workflow_id):
                if workflow_id == "wf_bad":
                    raise N8nError("401")
                return [{"id": "e1", "status": "error"}]
            async def aclose(self): pass

        behavior = WorkflowFailureBehavior(
            wf_store, state, lambda u, k: SelectiveClient(),
        )
        triggers = await behavior.check(CID)
        assert len(triggers) == 1
        assert triggers[0].payload["workflow_id"] == "wf_good"

    async def test_client_closed_after_check(
        self, state, seeded_wf_store,
    ):
        """Factory builds a fresh client per tick — must aclose it or
        httpx connections pile up."""
        factory = _client_factory({"wf_100": []})
        behavior = WorkflowFailureBehavior(seeded_wf_store, state, factory)
        await behavior.check(CID)
        assert len(factory.created) == 1
        assert factory.created[0].closed is True

    async def test_client_closed_even_on_error(
        self, state, seeded_wf_store,
    ):
        closed = []

        class TrackingRaiser:
            async def list_executions(self, wf_id):
                raise N8nError("boom")
            async def aclose(self):
                closed.append(True)

        behavior = WorkflowFailureBehavior(
            seeded_wf_store, state, lambda u, k: TrackingRaiser(),
        )
        await behavior.check(CID)
        assert closed == [True]
