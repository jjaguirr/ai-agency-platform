"""E2E: Action confirmation audit trail.

The confirmation gate itself lives inside the EA's LangGraph (requires
live LLM), so these tests exercise the surrounding API machinery:

- TestConfirmationAuditTrail: Seeds audit events directly via AuditLogger
  and verifies GET /v1/audit returns them with correct types, ordering,
  and detail fields.
- TestConfirmationWithMessageFlow: Sends real messages through the
  pipeline with a stubbed EA. Audit events are seeded manually after
  each turn to simulate what the safety pipeline would log, then
  verified via GET /v1/audit.
"""
import pytest

from src.safety.audit import AuditLogger
from src.safety.models import AuditEvent, AuditEventType


def _make_audit_event(event_type: AuditEventType, **details):
    return AuditEvent(
        timestamp="2026-03-21T10:00:00Z",
        event_type=event_type,
        correlation_id="corr-001",
        details=details,
    )


@pytest.mark.e2e
class TestConfirmationAuditTrail:
    """Seed audit events directly and verify retrieval, ordering, and details."""

    async def test_confirmed_action_audit_trail(
        self, client, headers_a, audit_logger,
    ):
        """REQUESTED → CONFIRMED appears in the audit trail with details."""
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_REQUESTED,
            domain="scheduling",
            action="cancel_all_meetings",
        ))
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_CONFIRMED,
            domain="scheduling",
            action="cancel_all_meetings",
        ))

        resp = await client.get("/v1/audit", headers=headers_a)
        assert resp.status_code == 200
        events = resp.json()["events"]

        assert len(events) == 2
        requested = next(e for e in events if e["event_type"] == "high_risk_action_requested")
        confirmed = next(e for e in events if e["event_type"] == "high_risk_action_confirmed")

        # Both carry the correct domain and action
        assert requested["details"]["domain"] == "scheduling"
        assert requested["details"]["action"] == "cancel_all_meetings"
        assert confirmed["details"]["domain"] == "scheduling"
        assert confirmed["details"]["action"] == "cancel_all_meetings"

        # Ordering: confirmed is newer → lower index (newest-first)
        assert events.index(confirmed) < events.index(requested)

    async def test_declined_action_audit_trail(
        self, client, headers_a, audit_logger,
    ):
        """REQUESTED → DECLINED appears in the audit trail with details."""
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_REQUESTED,
            domain="scheduling",
            action="cancel_all_meetings",
        ))
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_DECLINED,
            domain="scheduling",
            action="cancel_all_meetings",
        ))

        resp = await client.get("/v1/audit", headers=headers_a)
        events = resp.json()["events"]

        assert len(events) == 2
        requested = next(e for e in events if e["event_type"] == "high_risk_action_requested")
        declined = next(e for e in events if e["event_type"] == "high_risk_action_declined")

        assert requested["details"]["domain"] == "scheduling"
        assert declined["details"]["domain"] == "scheduling"
        assert declined["details"]["action"] == "cancel_all_meetings"

    async def test_audit_details_contain_domain_and_action(
        self, client, headers_a, audit_logger,
    ):
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_REQUESTED,
            domain="finance",
            action="delete_all_invoices",
            risk="high",
        ))

        resp = await client.get("/v1/audit", headers=headers_a)
        events = resp.json()["events"]
        requested = [
            e for e in events
            if e["event_type"] == "high_risk_action_requested"
        ]
        assert len(requested) == 1
        assert requested[0]["details"]["domain"] == "finance"
        assert requested[0]["details"]["action"] == "delete_all_invoices"
        assert requested[0]["details"]["risk"] == "high"
        assert requested[0]["correlation_id"] == "corr-001"


@pytest.mark.e2e
class TestConfirmationWithMessageFlow:
    """Multi-turn message flow with manually seeded audit events."""

    async def test_confirm_flow(
        self, client, headers_a, mock_ea, mock_conversation_repo, audit_logger,
    ):
        """Two-turn flow: EA asks for confirmation, customer confirms."""
        # Turn 1: EA asks for confirmation
        mock_ea.handle_customer_interaction.return_value = (
            "This will cancel all your meetings. Are you sure? (yes/no)"
        )

        resp1 = await client.post(
            "/v1/conversations/message",
            json={"message": "Cancel all my meetings", "channel": "chat"},
            headers=headers_a,
        )
        assert resp1.status_code == 200
        assert resp1.json()["response"] == (
            "This will cancel all your meetings. Are you sure? (yes/no)"
        )
        conv_id = resp1.json()["conversation_id"]

        # Simulate the audit event the safety pipeline would log
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_REQUESTED,
            domain="scheduling",
            action="cancel_all_meetings",
        ))

        # Turn 2: Customer confirms
        mock_ea.handle_customer_interaction.return_value = (
            "All meetings cancelled successfully."
        )

        resp2 = await client.post(
            "/v1/conversations/message",
            json={
                "message": "yes",
                "channel": "chat",
                "conversation_id": conv_id,
            },
            headers=headers_a,
        )
        assert resp2.status_code == 200
        assert resp2.json()["response"] == "All meetings cancelled successfully."
        # Same conversation thread
        assert resp2.json()["conversation_id"] == conv_id

        # Log the confirmed event
        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_CONFIRMED,
            domain="scheduling",
            action="cancel_all_meetings",
        ))

        # Verify complete audit trail
        resp = await client.get("/v1/audit", headers=headers_a)
        events = resp.json()["events"]
        assert len(events) == 2
        requested = next(e for e in events if e["event_type"] == "high_risk_action_requested")
        confirmed = next(e for e in events if e["event_type"] == "high_risk_action_confirmed")
        assert requested["details"]["action"] == confirmed["details"]["action"] == "cancel_all_meetings"

    async def test_decline_flow(
        self, client, headers_a, mock_ea, audit_logger,
    ):
        """Two-turn flow: EA asks for confirmation, customer declines."""
        mock_ea.handle_customer_interaction.return_value = (
            "This will delete all invoices. Are you sure? (yes/no)"
        )

        resp1 = await client.post(
            "/v1/conversations/message",
            json={"message": "Delete all invoices", "channel": "chat"},
            headers=headers_a,
        )
        assert resp1.status_code == 200
        conv_id = resp1.json()["conversation_id"]

        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_REQUESTED,
            domain="finance",
            action="delete_all_invoices",
        ))

        # Customer declines
        mock_ea.handle_customer_interaction.return_value = (
            "Action cancelled. Your invoices are safe."
        )

        resp2 = await client.post(
            "/v1/conversations/message",
            json={
                "message": "no",
                "channel": "chat",
                "conversation_id": conv_id,
            },
            headers=headers_a,
        )
        assert resp2.status_code == 200
        assert resp2.json()["response"] == "Action cancelled. Your invoices are safe."
        assert resp2.json()["conversation_id"] == conv_id

        await audit_logger.log("cust_a", _make_audit_event(
            AuditEventType.HIGH_RISK_ACTION_DECLINED,
            domain="finance",
            action="delete_all_invoices",
        ))

        resp = await client.get("/v1/audit", headers=headers_a)
        events = resp.json()["events"]
        assert len(events) == 2
        requested = next(e for e in events if e["event_type"] == "high_risk_action_requested")
        declined = next(e for e in events if e["event_type"] == "high_risk_action_declined")
        assert requested["details"]["action"] == declined["details"]["action"] == "delete_all_invoices"
        assert declined["details"]["domain"] == "finance"
