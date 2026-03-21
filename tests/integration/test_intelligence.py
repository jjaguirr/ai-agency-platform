"""
Integration tests for conversation intelligence — real Postgres, no mocks.

Covers DelegationRecorder, AnalyticsService, and the new repo extensions
(set_summary, set_quality_signals, get_conversations_needing_summary,
list_conversations with tags filter).

Follows the same pattern as test_conversation_repository.py:
  - Skips if Postgres is unreachable
  - Applies migrations 001 + 002
  - Unique customer_id per test, cleaned up after
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio

asyncpg = pytest.importorskip("asyncpg")

REPO_ROOT = Path(__file__).parents[2]
MIGRATION_001 = REPO_ROOT / "src" / "database" / "migrations" / "001_conversations.sql"
MIGRATION_002 = REPO_ROOT / "src" / "database" / "migrations" / "002_conversation_intelligence.sql"


def _dsn() -> str:
    if explicit := os.getenv("CONVERSATION_REPO_TEST_DSN"):
        return explicit
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "mcphub")
    user = os.getenv("POSTGRES_USER", "mcphub")
    pw = os.getenv("POSTGRES_PASSWORD", "mcphub_password")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


@pytest_asyncio.fixture
async def pool():
    dsn = _dsn()
    try:
        p = await asyncpg.create_pool(dsn, min_size=1, max_size=4, timeout=5)
    except (OSError, asyncpg.PostgresError) as e:
        pytest.skip(f"Postgres unavailable at {dsn!r}: {e}")

    async with p.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  version VARCHAR(50) PRIMARY KEY,"
            "  description TEXT,"
            "  applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)"
        )
        await conn.execute(MIGRATION_001.read_text())
        await conn.execute(MIGRATION_002.read_text())

    yield p
    await p.close()


@pytest_asyncio.fixture
async def cust(pool):
    """Fresh customer_id per test, with post-test cleanup."""
    cid = f"test_intel_{uuid.uuid4().hex[:12]}"
    yield cid
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM delegation_records WHERE customer_id = $1", cid)
        await conn.execute(
            "DELETE FROM conversations WHERE customer_id = $1", cid)


@pytest.fixture
def conv():
    prefix = uuid.uuid4().hex[:8]
    counter = iter(range(1000))
    return lambda name="c": f"{name}_{prefix}_{next(counter)}"


pytestmark = pytest.mark.integration


# Helper: create a conversation with messages
async def _create_conv(pool, cust_id, conv_id, channel="chat", messages=None):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations (id, customer_id, channel) "
            "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            conv_id, cust_id, channel,
        )
        for msg in (messages or []):
            await conn.execute(
                "INSERT INTO messages (conversation_id, role, content) "
                "VALUES ($1, $2, $3)",
                conv_id, msg["role"], msg["content"],
            )


# ─────────────────────────────────────────────────────────────────────────────
# DelegationRecorder
# ─────────────────────────────────────────────────────────────────────────────

class TestDelegationRecorderLifecycle:

    async def test_record_start_and_end(self, pool, cust, conv):
        from src.intelligence.delegation_recorder import DelegationRecorder

        recorder = DelegationRecorder(pool)
        cid = conv("deleg")
        await _create_conv(pool, cust, cid)

        record_id = await recorder.record_start(
            conversation_id=cid, customer_id=cust,
            specialist_domain="finance",
        )
        assert record_id is not None

        await recorder.record_end(
            record_id=record_id, status="completed", turns=3,
            confirmation_requested=True, confirmation_outcome="confirmed",
        )

        # Verify persisted state
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM delegation_records WHERE id = $1::uuid",
                record_id,
            )
        assert row["status"] == "completed"
        assert row["turns"] == 3
        assert row["confirmation_requested"] is True
        assert row["confirmation_outcome"] == "confirmed"
        assert row["completed_at"] is not None
        assert row["specialist_domain"] == "finance"

    async def test_update_tags_from_delegations(self, pool, cust, conv):
        from src.intelligence.delegation_recorder import DelegationRecorder

        recorder = DelegationRecorder(pool)
        cid = conv("tags")
        await _create_conv(pool, cust, cid)

        await recorder.record_start(
            conversation_id=cid, customer_id=cust,
            specialist_domain="finance",
        )
        await recorder.record_start(
            conversation_id=cid, customer_id=cust,
            specialist_domain="scheduling",
        )

        await recorder.update_tags_from_delegations(
            customer_id=cust, conversation_id=cid,
        )

        async with pool.acquire() as conn:
            tags = await conn.fetchval(
                "SELECT tags FROM conversations WHERE id = $1", cid)
        assert set(tags) == {"finance", "scheduling"}

    async def test_update_tags_general_when_no_delegations(self, pool, cust, conv):
        from src.intelligence.delegation_recorder import DelegationRecorder

        recorder = DelegationRecorder(pool)
        cid = conv("notags")
        await _create_conv(pool, cust, cid)

        await recorder.update_tags_from_delegations(
            customer_id=cust, conversation_id=cid,
        )

        async with pool.acquire() as conn:
            tags = await conn.fetchval(
                "SELECT tags FROM conversations WHERE id = $1", cid)
        assert tags == ["general"]

    async def test_gdpr_deletion(self, pool, cust, conv):
        from src.intelligence.delegation_recorder import DelegationRecorder

        recorder = DelegationRecorder(pool)
        cid = conv("gdpr")
        await _create_conv(pool, cust, cid)

        await recorder.record_start(
            conversation_id=cid, customer_id=cust,
            specialist_domain="finance",
        )

        count = await recorder.delete_customer_data(customer_id=cust)
        assert count == 1

        async with pool.acquire() as conn:
            remaining = await conn.fetchval(
                "SELECT count(*) FROM delegation_records "
                "WHERE customer_id = $1", cust)
        assert remaining == 0

    async def test_fk_cascade_deletes_delegation_records(self, pool, cust, conv):
        """Deleting a conversation cascades to delegation_records."""
        from src.intelligence.delegation_recorder import DelegationRecorder

        recorder = DelegationRecorder(pool)
        cid = conv("cascade")
        await _create_conv(pool, cust, cid)

        await recorder.record_start(
            conversation_id=cid, customer_id=cust,
            specialist_domain="workflows",
        )

        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM conversations WHERE id = $1", cid)
            remaining = await conn.fetchval(
                "SELECT count(*) FROM delegation_records "
                "WHERE conversation_id = $1", cid)
        assert remaining == 0


# ─────────────────────────────────────────────────────────────────────────────
# Repository extensions (summary, quality_signals, tags filter)
# ─────────────────────────────────────────────────────────────────────────────

class TestRepoIntelligenceExtensions:

    async def test_set_and_read_summary(self, pool, cust, conv):
        from src.database.conversation_repository import ConversationRepository

        repo = ConversationRepository(pool)
        cid = conv("sum")
        await _create_conv(pool, cust, cid)

        await repo.set_summary(conversation_id=cid, summary="User asked about invoices.")

        convs = await repo.list_conversations(customer_id=cust)
        match = [c for c in convs if c["id"] == cid]
        assert len(match) == 1
        assert match[0]["summary"] == "User asked about invoices."

    async def test_set_and_read_quality_signals(self, pool, cust, conv):
        from src.database.conversation_repository import ConversationRepository

        repo = ConversationRepository(pool)
        cid = conv("qs")
        await _create_conv(pool, cust, cid)

        signals = {"escalation": True, "unresolved": False, "long": False}
        await repo.set_quality_signals(conversation_id=cid, signals=signals)

        convs = await repo.list_conversations(customer_id=cust)
        match = [c for c in convs if c["id"] == cid]
        assert match[0]["quality_signals"]["escalation"] is True
        assert match[0]["quality_signals"]["unresolved"] is False

    async def test_tag_filter(self, pool, cust, conv):
        from src.database.conversation_repository import ConversationRepository

        repo = ConversationRepository(pool)
        cid_a, cid_b = conv("a"), conv("b")
        await _create_conv(pool, cust, cid_a)
        await _create_conv(pool, cust, cid_b)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET tags = $1 WHERE id = $2",
                ["finance", "scheduling"], cid_a,
            )
            await conn.execute(
                "UPDATE conversations SET tags = $1 WHERE id = $2",
                ["social_media"], cid_b,
            )

        finance_convs = await repo.list_conversations(
            customer_id=cust, tags=["finance"])
        assert {c["id"] for c in finance_convs} == {cid_a}

        social_convs = await repo.list_conversations(
            customer_id=cust, tags=["social_media"])
        assert {c["id"] for c in social_convs} == {cid_b}

    async def test_get_conversations_needing_summary(self, pool, cust, conv):
        from src.database.conversation_repository import ConversationRepository

        repo = ConversationRepository(pool)
        cid_idle = conv("idle")
        cid_recent = conv("recent")
        await _create_conv(pool, cust, cid_idle)
        await _create_conv(pool, cust, cid_recent)

        # Backdate idle conversation
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET updated_at = $1 WHERE id = $2",
                datetime.now(timezone.utc) - timedelta(hours=2), cid_idle,
            )

        results = await repo.get_conversations_needing_summary(
            idle_threshold_minutes=30, limit=10,
        )
        result_ids = [r["id"] for r in results]
        assert cid_idle in result_ids
        assert cid_recent not in result_ids


# ─────────────────────────────────────────────────────────────────────────────
# AnalyticsService
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsServiceSQL:

    async def test_overview_aggregation(self, pool, cust, conv):
        from src.intelligence.analytics import AnalyticsService

        svc = AnalyticsService(pool)
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)

        # Create conversations with quality signals
        cid_a, cid_b = conv("a"), conv("b")
        await _create_conv(pool, cust, cid_a, messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ])
        await _create_conv(pool, cust, cid_b, messages=[
            {"role": "user", "content": "help"},
            {"role": "assistant", "content": "sure"},
            {"role": "user", "content": "more"},
        ])
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET quality_signals = $1 WHERE id = $2",
                '{"escalation": true}', cid_a,
            )

        result = await svc.get_analytics(
            customer_id=cust, start=start, end=now + timedelta(minutes=1))

        overview = result["overview"]
        assert overview["total_conversations"] == 2
        assert overview["avg_messages_per_conversation"] == pytest.approx(2.5)
        assert overview["escalation_rate"] == pytest.approx(0.5)

    async def test_topic_breakdown(self, pool, cust, conv):
        from src.intelligence.analytics import AnalyticsService

        svc = AnalyticsService(pool)
        now = datetime.now(timezone.utc)

        cid_a, cid_b, cid_c = conv("a"), conv("b"), conv("c")
        await _create_conv(pool, cust, cid_a)
        await _create_conv(pool, cust, cid_b)
        await _create_conv(pool, cust, cid_c)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET tags = '{finance}' WHERE id = $1", cid_a)
            await conn.execute(
                "UPDATE conversations SET tags = '{finance}' WHERE id = $1", cid_b)
            await conn.execute(
                "UPDATE conversations SET tags = '{scheduling}' WHERE id = $1", cid_c)

        result = await svc.get_analytics(
            customer_id=cust,
            start=now - timedelta(days=1),
            end=now + timedelta(minutes=1),
        )

        topics = result["topics"]["breakdown"]
        by_domain = {t["domain"]: t for t in topics}
        assert by_domain["finance"]["count"] == 2
        assert by_domain["finance"]["percentage"] == pytest.approx(66.7, abs=0.1)
        assert by_domain["scheduling"]["count"] == 1
        assert by_domain["scheduling"]["percentage"] == pytest.approx(33.3, abs=0.1)

    async def test_specialist_performance(self, pool, cust, conv):
        from src.intelligence.analytics import AnalyticsService
        from src.intelligence.delegation_recorder import DelegationRecorder

        svc = AnalyticsService(pool)
        recorder = DelegationRecorder(pool)
        now = datetime.now(timezone.utc)

        cid = conv("perf")
        await _create_conv(pool, cust, cid)

        # 2 finance delegations: 1 completed, 1 failed
        r1 = await recorder.record_start(
            conversation_id=cid, customer_id=cust, specialist_domain="finance")
        await recorder.record_end(
            record_id=r1, status="completed", turns=3,
            confirmation_requested=True, confirmation_outcome="confirmed")

        r2 = await recorder.record_start(
            conversation_id=cid, customer_id=cust, specialist_domain="finance")
        await recorder.record_end(
            record_id=r2, status="failed", turns=1,
            confirmation_requested=False, error_message="timeout")

        result = await svc.get_analytics(
            customer_id=cust,
            start=now - timedelta(days=1),
            end=now + timedelta(minutes=1),
        )

        specs = result["specialist_performance"]
        assert len(specs) == 1
        s = specs[0]
        assert s["domain"] == "finance"
        assert s["delegation_count"] == 2
        assert s["success_rate"] == pytest.approx(50.0)
        assert s["confirmation_rate"] == pytest.approx(50.0)
        assert s["avg_turns"] == pytest.approx(2.0)

    async def test_tenant_isolation(self, pool, cust, conv):
        """Analytics for cust_a must not include cust_b's data."""
        from src.intelligence.analytics import AnalyticsService

        svc = AnalyticsService(pool)
        now = datetime.now(timezone.utc)
        other = f"test_intel_other_{uuid.uuid4().hex[:12]}"

        cid_mine = conv("mine")
        cid_theirs = conv("theirs")
        await _create_conv(pool, cust, cid_mine)
        await _create_conv(pool, other, cid_theirs)

        try:
            result = await svc.get_analytics(
                customer_id=cust,
                start=now - timedelta(days=1),
                end=now + timedelta(minutes=1),
            )
            assert result["overview"]["total_conversations"] == 1
        finally:
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM conversations WHERE customer_id = $1", other)

    async def test_empty_data(self, pool, cust):
        from src.intelligence.analytics import AnalyticsService

        svc = AnalyticsService(pool)
        now = datetime.now(timezone.utc)

        result = await svc.get_analytics(
            customer_id=cust,
            start=now - timedelta(days=1),
            end=now + timedelta(minutes=1),
        )

        assert result["overview"]["total_conversations"] == 0
        assert result["overview"]["escalation_rate"] == 0.0
        assert result["overview"]["unresolved_rate"] == 0.0
        assert result["topics"]["breakdown"] == []
        assert result["specialist_performance"] == []

    async def test_daily_trend(self, pool, cust, conv):
        from src.intelligence.analytics import AnalyticsService

        svc = AnalyticsService(pool)
        now = datetime.now(timezone.utc)

        # Create conversations on different days
        cid_today = conv("today")
        cid_yesterday = conv("yesterday")
        await _create_conv(pool, cust, cid_today)
        await _create_conv(pool, cust, cid_yesterday)

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET created_at = $1 WHERE id = $2",
                now - timedelta(days=1), cid_yesterday,
            )

        result = await svc.get_analytics(
            customer_id=cust,
            start=now - timedelta(days=2),
            end=now + timedelta(minutes=1),
        )

        trend = result["trends"]["conversations_by_day"]
        assert len(trend) == 2
        counts = {t["date"]: t["count"] for t in trend}
        assert sum(counts.values()) == 2
