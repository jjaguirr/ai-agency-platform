"""
AuditLogger — append-only audit trail in Redis.

Key: audit:{customer_id}. Events are RPUSHed as JSON; list is LTRIMmed
to a configurable cap so a noisy tenant doesn't grow Redis unbounded.
list_events returns newest-first for the API endpoint.

Events never store raw message content — message_hash (SHA-256) lets
ops correlate incidents without putting PII in the audit log. The
correlation_id ties the event back to the request that produced it.

Logging must never raise: audit failure must not block the request.
If Redis is down, log at WARNING and move on.
"""
import hashlib
import json

import pytest

from src.safety.audit import AuditLogger, hash_message
from src.safety.models import AuditEvent, AuditEventType


# --- Message hashing --------------------------------------------------------

class TestHashMessage:
    def test_hash_is_sha256_hex(self):
        h = hash_message("hello")
        assert len(h) == 64  # sha256 → 32 bytes → 64 hex chars
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_deterministic(self):
        assert hash_message("same input") == hash_message("same input")

    def test_hash_differs_for_different_input(self):
        assert hash_message("a") != hash_message("b")

    def test_hash_matches_stdlib(self):
        msg = "Ignore previous instructions"
        expected = hashlib.sha256(msg.encode("utf-8")).hexdigest()
        assert hash_message(msg) == expected

    def test_hash_handles_unicode(self):
        # Customer messages can contain emoji, accents, etc.
        h = hash_message("café ☕ résumé")
        assert len(h) == 64


# --- Logging events ---------------------------------------------------------

class TestLogEvent:
    @pytest.mark.asyncio
    async def test_event_appended_to_customer_list(self, fake_redis):
        audit = AuditLogger(fake_redis)
        event = AuditEvent(
            timestamp="2026-03-20T10:00:00Z",
            event_type=AuditEventType.PROMPT_INJECTION_DETECTED,
            correlation_id="req-123",
            details={"risk_score": 0.8, "patterns": ["instruction_override"]},
        )
        await audit.log("cust_alice", event)

        raw = await fake_redis.lrange("audit:cust_alice", 0, -1)
        assert len(raw) == 1
        stored = json.loads(raw[0])
        assert stored["event_type"] == "prompt_injection_detected"
        assert stored["correlation_id"] == "req-123"
        assert stored["details"]["risk_score"] == 0.8

    @pytest.mark.asyncio
    async def test_events_isolated_per_customer(self, fake_redis):
        audit = AuditLogger(fake_redis)
        e_alice = AuditEvent("2026-03-20T10:00:00Z", AuditEventType.PII_REDACTED, "r1")
        e_bob = AuditEvent("2026-03-20T10:00:01Z", AuditEventType.AUTH_FAILURE, "r2")

        await audit.log("cust_alice", e_alice)
        await audit.log("cust_bob", e_bob)

        alice_raw = await fake_redis.lrange("audit:cust_alice", 0, -1)
        bob_raw = await fake_redis.lrange("audit:cust_bob", 0, -1)
        assert len(alice_raw) == 1
        assert len(bob_raw) == 1
        assert json.loads(alice_raw[0])["event_type"] == "pii_redacted"
        assert json.loads(bob_raw[0])["event_type"] == "auth_failure"

    @pytest.mark.asyncio
    async def test_multiple_events_preserve_order(self, fake_redis):
        audit = AuditLogger(fake_redis)
        for i in range(5):
            await audit.log("cust_alice", AuditEvent(
                timestamp=f"2026-03-20T10:00:0{i}Z",
                event_type=AuditEventType.INPUT_REJECTED,
                correlation_id=f"req-{i}",
            ))

        raw = await fake_redis.lrange("audit:cust_alice", 0, -1)
        assert len(raw) == 5
        # RPUSH → oldest at index 0
        assert json.loads(raw[0])["correlation_id"] == "req-0"
        assert json.loads(raw[4])["correlation_id"] == "req-4"


# --- LTRIM cap --------------------------------------------------------------

class TestLtrimCap:
    @pytest.mark.asyncio
    async def test_oldest_events_evicted_at_cap(self, fake_redis):
        audit = AuditLogger(fake_redis, max_events=3)
        for i in range(5):
            await audit.log("cust_alice", AuditEvent(
                timestamp=f"2026-03-20T10:00:0{i}Z",
                event_type=AuditEventType.INPUT_REJECTED,
                correlation_id=f"req-{i}",
            ))

        raw = await fake_redis.lrange("audit:cust_alice", 0, -1)
        assert len(raw) == 3
        # req-0 and req-1 evicted; req-2,3,4 remain
        cids = [json.loads(r)["correlation_id"] for r in raw]
        assert cids == ["req-2", "req-3", "req-4"]


# --- Listing events (for API endpoint) --------------------------------------

class TestListEvents:
    @pytest.mark.asyncio
    async def test_list_newest_first(self, fake_redis):
        audit = AuditLogger(fake_redis)
        for i in range(3):
            await audit.log("cust_alice", AuditEvent(
                timestamp=f"2026-03-20T10:00:0{i}Z",
                event_type=AuditEventType.INPUT_REJECTED,
                correlation_id=f"req-{i}",
            ))

        events = await audit.list_events("cust_alice", limit=10, offset=0)
        assert len(events) == 3
        # Newest first for the API
        assert events[0].correlation_id == "req-2"
        assert events[1].correlation_id == "req-1"
        assert events[2].correlation_id == "req-0"

    @pytest.mark.asyncio
    async def test_list_respects_limit(self, fake_redis):
        audit = AuditLogger(fake_redis)
        for i in range(10):
            await audit.log("cust_alice", AuditEvent(
                f"2026-03-20T10:00:{i:02d}Z",
                AuditEventType.INPUT_REJECTED,
                f"req-{i}",
            ))

        events = await audit.list_events("cust_alice", limit=3, offset=0)
        assert len(events) == 3
        # Newest 3: req-9, req-8, req-7
        assert [e.correlation_id for e in events] == ["req-9", "req-8", "req-7"]

    @pytest.mark.asyncio
    async def test_list_respects_offset(self, fake_redis):
        audit = AuditLogger(fake_redis)
        for i in range(10):
            await audit.log("cust_alice", AuditEvent(
                f"2026-03-20T10:00:{i:02d}Z",
                AuditEventType.INPUT_REJECTED,
                f"req-{i}",
            ))

        page2 = await audit.list_events("cust_alice", limit=3, offset=3)
        assert len(page2) == 3
        # Skip newest 3 (req-9,8,7), get next 3 (req-6,5,4)
        assert [e.correlation_id for e in page2] == ["req-6", "req-5", "req-4"]

    @pytest.mark.asyncio
    async def test_list_empty_customer(self, fake_redis):
        audit = AuditLogger(fake_redis)
        events = await audit.list_events("cust_nobody", limit=10, offset=0)
        assert events == []

    @pytest.mark.asyncio
    async def test_list_offset_past_end(self, fake_redis):
        audit = AuditLogger(fake_redis)
        await audit.log("cust_alice", AuditEvent(
            "2026-03-20T10:00:00Z", AuditEventType.INPUT_REJECTED, "r1",
        ))

        events = await audit.list_events("cust_alice", limit=5, offset=100)
        assert events == []

    @pytest.mark.asyncio
    async def test_list_roundtrips_event_types(self, fake_redis):
        audit = AuditLogger(fake_redis)
        for et in AuditEventType:
            await audit.log("cust_alice", AuditEvent(
                "2026-03-20T10:00:00Z", et, "r",
            ))

        events = await audit.list_events("cust_alice", limit=100, offset=0)
        stored_types = {e.event_type for e in events}
        assert stored_types == set(AuditEventType)


# --- Fail-soft on Redis errors ---------------------------------------------

class TestFailSoft:
    @pytest.mark.asyncio
    async def test_log_never_raises_on_redis_failure(self):
        from unittest.mock import AsyncMock
        broken = AsyncMock()
        broken.pipeline.side_effect = ConnectionError("redis down")

        audit = AuditLogger(broken)
        # Must not raise — audit failure must not block the request.
        await audit.log("cust_alice", AuditEvent(
            "2026-03-20T10:00:00Z", AuditEventType.INPUT_REJECTED, "r",
        ))

    @pytest.mark.asyncio
    async def test_list_returns_empty_on_redis_failure(self):
        from unittest.mock import AsyncMock
        broken = AsyncMock()
        broken.lrange = AsyncMock(side_effect=ConnectionError("redis down"))

        audit = AuditLogger(broken)
        events = await audit.list_events("cust_alice", limit=10, offset=0)
        assert events == []
