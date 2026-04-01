"""
E2E: Specialist Delegation Round-Trip + Action Confirmation Flow

A message like "schedule a meeting" should route to the scheduling
specialist, complete, get recorded, tag the conversation, and bump the
delegation counter.

A HIGH-risk action like "cancel all my meetings" should pause for
confirmation, then either execute (yes) or cancel (no), with the full
REQUESTED→CONFIRMED / REQUESTED→DECLINED audit trail.
"""
import pytest
from datetime import date


pytestmark = pytest.mark.e2e


class TestSpecialistDelegation:
    """Simple scheduling request → completed delegation."""

    async def test_routes_to_scheduling_not_finance(
        self, client, auth_a, ea_instances,
    ):
        resp = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "Schedule a meeting tomorrow at 3pm",
                "channel": "chat",
            },
        )
        assert resp.status_code == 200

        ea = ea_instances["customer_a"]
        assert ea.last_specialist_domain == "scheduling"
        # Confirmation language in the reply
        assert "scheduled" in resp.json()["response"].lower()

    async def test_delegation_recorded(
        self, client, auth_a, delegation_recorder,
    ):
        await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "Schedule a meeting tomorrow at 3pm",
                "channel": "chat",
            },
        )

        records = list(delegation_recorder.records.values())
        assert len(records) == 1
        r = records[0]
        assert r["customer_id"] == "customer_a"
        assert r["specialist_domain"] == "scheduling"
        assert r["status"] == "completed"
        assert r["confirmation_requested"] is False

    async def test_conversation_tagged_with_domain(
        self, client, auth_a, conversation_repo,
    ):
        resp = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "Put a meeting on my calendar for Friday",
                "channel": "chat",
            },
        )
        conv_id = resp.json()["conversation_id"]

        # The assistant message was persisted with specialist_domain set.
        msgs = conversation_repo._messages[conv_id]
        assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
        assert assistant_msgs[0]["specialist_domain"] == "scheduling"

        # And the enriched list view surfaces that domain.
        convs = await conversation_repo.list_conversations_enriched(
            customer_id="customer_a",
        )
        assert convs[0]["specialist_domains"] == ["scheduling"]

    async def test_delegation_counter_incremented(
        self, client, auth_a, fake_redis,
    ):
        await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Schedule a meeting", "channel": "chat"},
        )

        today = date.today().isoformat()
        key = f"activity:customer_a:delegation:scheduling:{today}"
        raw = await fake_redis.get(key)
        assert raw is not None and int(raw) == 1

        # And the activity endpoint reflects it.
        act = await client.get("/v1/analytics/activity", headers=auth_a)
        assert act.status_code == 200
        body = act.json()
        assert body["messages_processed"] == 1
        assert body["delegations_by_domain"].get("scheduling") == 1


class TestActionConfirmationConfirm:
    """Customer says yes to a HIGH-risk action."""

    async def test_full_confirm_flow(
        self, client, auth_a, delegation_recorder,
    ):
        # Turn 1 — specialist returns NEEDS_CONFIRMATION
        r1 = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Cancel all my meetings", "channel": "chat"},
        )
        assert r1.status_code == 200
        conv_id = r1.json()["conversation_id"]
        assert "are you sure" in r1.json()["response"].lower()

        # Delegation record exists, still "started"
        records = list(delegation_recorder.records.values())
        assert len(records) == 1
        assert records[0]["status"] == "started"

        # Turn 2 — customer confirms
        r2 = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={
                "message": "yes",
                "channel": "chat",
                "conversation_id": conv_id,
            },
        )
        assert r2.status_code == 200
        assert "done" in r2.json()["response"].lower()

        # Delegation record closed with confirmation_outcome="confirmed"
        records = list(delegation_recorder.records.values())
        assert len(records) == 1
        r = records[0]
        assert r["status"] == "completed"
        assert r["confirmation_requested"] is True
        assert r["confirmation_outcome"] == "confirmed"

    async def test_audit_trail_requested_then_confirmed(
        self, client, auth_a, audit_logger,
    ):
        r1 = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Cancel all my meetings", "channel": "chat"},
        )
        conv_id = r1.json()["conversation_id"]

        await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "yes", "channel": "chat",
                  "conversation_id": conv_id},
        )

        events = await audit_logger.list_events(
            "customer_a", limit=10, offset=0,
        )
        types = [e.event_type.value for e in events]
        # Newest-first ordering from list_events
        assert "high_risk_action_confirmed" in types
        assert "high_risk_action_requested" in types
        assert types.index("high_risk_action_confirmed") < \
            types.index("high_risk_action_requested")


class TestActionConfirmationDecline:
    """Customer says no — action cancelled, DECLINED audited."""

    async def test_full_decline_flow(
        self, client, auth_a, delegation_recorder,
    ):
        r1 = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Cancel all my meetings", "channel": "chat"},
        )
        conv_id = r1.json()["conversation_id"]

        r2 = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "no", "channel": "chat",
                  "conversation_id": conv_id},
        )
        assert r2.status_code == 200
        assert "cancelled" in r2.json()["response"].lower()

        r = list(delegation_recorder.records.values())[0]
        assert r["status"] == "cancelled"
        assert r["confirmation_requested"] is True
        assert r["confirmation_outcome"] == "declined"

    async def test_audit_trail_requested_then_declined(
        self, client, auth_a,
    ):
        r1 = await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "Cancel all my meetings", "channel": "chat"},
        )
        conv_id = r1.json()["conversation_id"]

        await client.post(
            "/v1/conversations/message",
            headers=auth_a,
            json={"message": "no", "channel": "chat",
                  "conversation_id": conv_id},
        )

        audit = await client.get("/v1/audit", headers=auth_a)
        events = audit.json()["events"]
        types = [e["event_type"] for e in events]
        assert "high_risk_action_requested" in types
        assert "high_risk_action_declined" in types
        assert "high_risk_action_confirmed" not in types
