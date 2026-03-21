"""Tests for AuditLogger — Redis-backed audit event stream."""
import pytest

from src.safety.audit import AuditEventType, AuditEvent, AuditLogger


@pytest.fixture
def fake_redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def audit_logger(fake_redis):
    return AuditLogger(fake_redis, ttl=3600)


class TestAuditLog:
    async def test_log_and_retrieve(self, audit_logger):
        event = AuditEvent(
            event_type=AuditEventType.INJECTION_DETECTED,
            customer_id="cust_test",
            correlation_id="req-123",
            details={"risk": 0.8, "patterns": ["instruction_override"]},
        )
        await audit_logger.log(event)
        events = await audit_logger.list_events("cust_test")
        assert len(events) == 1
        assert events[0]["event_type"] == "injection_detected"
        assert events[0]["correlation_id"] == "req-123"
        assert events[0]["details"]["risk"] == 0.8

    async def test_timestamp_auto_set(self, audit_logger):
        from datetime import datetime, timezone
        before = datetime.now(timezone.utc)
        event = AuditEvent(
            event_type=AuditEventType.INPUT_REJECTED,
            customer_id="cust_test",
            details={"reason": "too_long"},
        )
        await audit_logger.log(event)
        after = datetime.now(timezone.utc)
        events = await audit_logger.list_events("cust_test")
        ts_str = events[0]["timestamp"]
        # Must be a parseable ISO datetime
        ts = datetime.fromisoformat(ts_str)
        assert ts.tzinfo is not None, "Timestamp must be timezone-aware"
        assert before <= ts <= after, f"Timestamp {ts} not between {before} and {after}"

    async def test_events_ordered_chronologically(self, audit_logger):
        for i in range(5):
            await audit_logger.log(AuditEvent(
                event_type=AuditEventType.INJECTION_DETECTED,
                customer_id="cust_test",
                details={"index": i},
            ))
        events = await audit_logger.list_events("cust_test")
        assert len(events) == 5
        indices = [e["details"]["index"] for e in events]
        assert indices == [0, 1, 2, 3, 4]

    async def test_customer_isolation(self, audit_logger):
        await audit_logger.log(AuditEvent(
            event_type=AuditEventType.PII_REDACTION,
            customer_id="cust_alice",
            details={"count": 1},
        ))
        await audit_logger.log(AuditEvent(
            event_type=AuditEventType.INPUT_REJECTED,
            customer_id="cust_bob",
            details={"reason": "length"},
        ))
        alice_events = await audit_logger.list_events("cust_alice")
        bob_events = await audit_logger.list_events("cust_bob")
        assert len(alice_events) == 1
        assert len(bob_events) == 1
        assert alice_events[0]["event_type"] == "pii_redaction"
        assert bob_events[0]["event_type"] == "input_rejected"


class TestAuditPagination:
    async def test_offset_and_limit(self, audit_logger):
        for i in range(20):
            await audit_logger.log(AuditEvent(
                event_type=AuditEventType.INJECTION_DETECTED,
                customer_id="cust_test",
                details={"index": i},
            ))
        page = await audit_logger.list_events("cust_test", offset=5, limit=3)
        assert len(page) == 3
        assert page[0]["details"]["index"] == 5
        assert page[2]["details"]["index"] == 7

    async def test_offset_beyond_end(self, audit_logger):
        await audit_logger.log(AuditEvent(
            event_type=AuditEventType.INPUT_REJECTED,
            customer_id="cust_test",
            details={},
        ))
        events = await audit_logger.list_events("cust_test", offset=100)
        assert events == []

    async def test_empty_list(self, audit_logger):
        events = await audit_logger.list_events("cust_nonexistent")
        assert events == []

    async def test_default_limit(self, audit_logger):
        for i in range(60):
            await audit_logger.log(AuditEvent(
                event_type=AuditEventType.INJECTION_DETECTED,
                customer_id="cust_test",
                details={"i": i},
            ))
        events = await audit_logger.list_events("cust_test")
        assert len(events) == 50  # default limit


class TestAuditEventTypes:
    @pytest.mark.parametrize("event_type", list(AuditEventType))
    async def test_all_event_types_loggable(self, audit_logger, event_type):
        await audit_logger.log(AuditEvent(
            event_type=event_type,
            customer_id="cust_test",
            details={"type": event_type.value},
        ))
        events = await audit_logger.list_events("cust_test")
        assert len(events) == 1
        assert events[0]["event_type"] == event_type.value
