"""
IntelligenceRepository unit tests — asyncpg pool mocked.

Same strategy as the API route tests: mock at the connection boundary,
assert on the SQL that flows through. Real Postgres coverage lives in
tests/integration/test_conversation_repository.py (which can be extended
for the new tables once integration CI is wired).

What matters here: the tenant-isolation clause is in every query, the
analytics aggregates are structured for chart consumption, and the idle
sweep query has the right predicate.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.intelligence.repository import IntelligenceRepository, DelegationRecord


# ─── fixtures ──────────────────────────────────────────────────────────────

def _conn(fetch=None, fetchrow=None, fetchval=None, execute="UPDATE 1"):
    """Build a mock asyncpg connection usable in `async with pool.acquire()`."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetchval = AsyncMock(return_value=fetchval)
    conn.execute = AsyncMock(return_value=execute)
    return conn


def _pool(conn):
    """Wrap a connection mock in a pool whose acquire() context manager yields it."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


def _row(**kw):
    """asyncpg Row is dict-like; a real dict is enough for __getitem__ access."""
    return kw


REF = datetime(2026, 3, 20, 12, 0, tzinfo=timezone.utc)


# ─── idle sweep ────────────────────────────────────────────────────────────

class TestFindIdleUnsummarized:
    async def test_query_filters_on_summary_null_and_age(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))

        await repo.find_idle_unsummarized(idle_minutes=30, limit=50)

        sql = conn.fetch.await_args.args[0].lower()
        assert "summary is null" in sql
        assert "updated_at <" in sql
        # Must select enough to process: id, customer_id at minimum
        assert "customer_id" in sql

    async def test_idle_minutes_parameterized(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))

        await repo.find_idle_unsummarized(idle_minutes=45, limit=10)

        # The cutoff timestamp or interval should be a bind param, not
        # string-interpolated. We can't inspect the value easily with
        # a mock, but we can assert the arg count matches the $-refs.
        sql = conn.fetch.await_args.args[0]
        n_params = sql.count("$")
        assert len(conn.fetch.await_args.args) >= n_params + 1  # sql + params

    async def test_limit_applied(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))

        await repo.find_idle_unsummarized(idle_minutes=30, limit=7)

        sql = conn.fetch.await_args.args[0].lower()
        assert "limit" in sql
        # 7 appears somewhere in the args
        assert 7 in conn.fetch.await_args.args

    async def test_returns_id_customer_pairs(self):
        conn = _conn(fetch=[
            _row(id="conv_a", customer_id="cust_1"),
            _row(id="conv_b", customer_id="cust_2"),
        ])
        repo = IntelligenceRepository(_pool(conn))

        out = await repo.find_idle_unsummarized(idle_minutes=30, limit=50)

        assert out == [("conv_a", "cust_1"), ("conv_b", "cust_2")]


# ─── intelligence writes ───────────────────────────────────────────────────

class TestSetIntelligence:
    async def test_set_summary_tenant_scoped(self):
        conn = _conn()
        repo = IntelligenceRepository(_pool(conn))

        await repo.set_intelligence(
            customer_id="cust_1",
            conversation_id="conv_a",
            summary="Customer asked about invoices.",
            topics=["finance"],
            quality_flags=[],
        )

        sql = conn.execute.await_args.args[0].lower()
        args = conn.execute.await_args.args
        # Tenant guard: UPDATE must filter on customer_id, not just conv id.
        assert "customer_id" in sql
        assert "cust_1" in args
        assert "conv_a" in args
        assert "Customer asked about invoices." in args

    async def test_topics_and_flags_passed_as_arrays(self):
        conn = _conn()
        repo = IntelligenceRepository(_pool(conn))

        await repo.set_intelligence(
            customer_id="cust_1",
            conversation_id="conv_a",
            summary="s",
            topics=["finance", "scheduling"],
            quality_flags=["escalation", "long"],
        )

        args = conn.execute.await_args.args
        assert ["finance", "scheduling"] in args
        assert ["escalation", "long"] in args

    async def test_returns_true_on_match(self):
        conn = _conn(execute="UPDATE 1")
        repo = IntelligenceRepository(_pool(conn))
        ok = await repo.set_intelligence(
            customer_id="c", conversation_id="x",
            summary="s", topics=[], quality_flags=[],
        )
        assert ok is True

    async def test_returns_false_on_no_match(self):
        # Wrong tenant or conversation gone — UPDATE 0 rows.
        conn = _conn(execute="UPDATE 0")
        repo = IntelligenceRepository(_pool(conn))
        ok = await repo.set_intelligence(
            customer_id="c", conversation_id="x",
            summary="s", topics=[], quality_flags=[],
        )
        assert ok is False


# ─── delegation records ────────────────────────────────────────────────────

class TestRecordDelegation:
    async def test_insert_shape(self):
        conn = _conn()
        repo = IntelligenceRepository(_pool(conn))

        rec = DelegationRecord(
            conversation_id="conv_a",
            customer_id="cust_1",
            domain="finance",
            status="completed",
            turns=2,
            confirmation_requested=True,
            confirmation_outcome="confirmed",
            started_at=REF,
            ended_at=REF + timedelta(seconds=8),
        )
        await repo.record_delegation(rec)

        sql = conn.execute.await_args.args[0].lower()
        args = conn.execute.await_args.args
        assert "insert into delegations" in sql
        assert "cust_1" in args
        assert "conv_a" in args
        assert "finance" in args
        assert "completed" in args
        assert 2 in args
        assert True in args
        assert "confirmed" in args

    async def test_confirmation_not_requested_outcome_none(self):
        conn = _conn()
        repo = IntelligenceRepository(_pool(conn))

        rec = DelegationRecord(
            conversation_id="c", customer_id="cust",
            domain="scheduling", status="completed", turns=1,
            confirmation_requested=False, confirmation_outcome=None,
            started_at=REF, ended_at=REF,
        )
        await repo.record_delegation(rec)

        args = conn.execute.await_args.args
        assert False in args
        assert None in args


# ─── delegation query ──────────────────────────────────────────────────────

class TestGetDelegationStatuses:
    async def test_tenant_scoped(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))

        await repo.get_delegation_statuses(
            customer_id="cust_1", conversation_id="conv_a",
        )

        sql = conn.fetch.await_args.args[0].lower()
        args = conn.fetch.await_args.args
        assert "customer_id" in sql
        assert "cust_1" in args
        assert "conv_a" in args

    async def test_returns_domain_status_pairs(self):
        conn = _conn(fetch=[
            _row(domain="finance", status="completed"),
            _row(domain="scheduling", status="failed"),
        ])
        repo = IntelligenceRepository(_pool(conn))

        out = await repo.get_delegation_statuses(
            customer_id="c", conversation_id="x",
        )
        assert out == [("finance", "completed"), ("scheduling", "failed")]


# ─── analytics ─────────────────────────────────────────────────────────────

class TestTopicBreakdown:
    async def test_tenant_and_time_scoped(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))

        since = REF - timedelta(days=7)
        await repo.topic_breakdown(customer_id="cust_1", since=since, until=REF)

        sql = conn.fetch.await_args.args[0].lower()
        args = conn.fetch.await_args.args
        assert "customer_id" in sql
        assert "cust_1" in args
        assert since in args
        assert REF in args

    async def test_chart_shape(self):
        # unnest(topics) → group by → count. Result is label/value pairs.
        conn = _conn(fetch=[
            _row(topic="finance", count=12),
            _row(topic="scheduling", count=5),
            _row(topic="general", count=3),
        ])
        repo = IntelligenceRepository(_pool(conn))

        out = await repo.topic_breakdown(customer_id="c", since=REF, until=REF)
        assert out == [
            {"label": "finance", "value": 12},
            {"label": "scheduling", "value": 5},
            {"label": "general", "value": 3},
        ]


class TestSpecialistMetrics:
    async def test_tenant_and_time_scoped(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))

        await repo.specialist_metrics(
            customer_id="cust_1",
            since=REF - timedelta(days=7),
            until=REF,
        )

        sql = conn.fetch.await_args.args[0].lower()
        args = conn.fetch.await_args.args
        assert "customer_id" in sql
        assert "cust_1" in args
        # Aggregates on the delegations table
        assert "delegations" in sql
        assert "group by" in sql

    async def test_metric_shape(self):
        conn = _conn(fetch=[
            _row(
                domain="finance",
                delegation_count=20,
                success_count=18,
                avg_turns=1.5,
                confirm_requested=4,
                confirm_accepted=3,
            ),
            _row(
                domain="scheduling",
                delegation_count=10,
                success_count=10,
                avg_turns=1.0,
                confirm_requested=0,
                confirm_accepted=0,
            ),
        ])
        repo = IntelligenceRepository(_pool(conn))

        out = await repo.specialist_metrics(customer_id="c", since=REF, until=REF)

        assert len(out) == 2
        fin = out[0]
        assert fin["domain"] == "finance"
        assert fin["delegation_count"] == 20
        assert fin["success_rate"] == pytest.approx(0.9)
        assert fin["avg_turns"] == pytest.approx(1.5)
        assert fin["confirmation_rate"] == pytest.approx(0.75)  # 3/4

        sched = out[1]
        # No confirmations requested → rate is None, not a div-by-zero.
        assert sched["confirmation_rate"] is None
        assert sched["success_rate"] == pytest.approx(1.0)


class TestQualityCounts:
    async def test_counts_shape(self):
        conn = _conn(fetch=[
            _row(flag="escalation", count=3),
            _row(flag="unresolved", count=7),
            _row(flag="long", count=2),
        ])
        repo = IntelligenceRepository(_pool(conn))

        out = await repo.quality_counts(customer_id="c", since=REF, until=REF)
        assert out == {"escalation": 3, "unresolved": 7, "long": 2}

    async def test_tenant_scoped(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))
        await repo.quality_counts(customer_id="cust_1", since=REF, until=REF)
        assert "cust_1" in conn.fetch.await_args.args

    async def test_empty_is_empty_dict(self):
        conn = _conn(fetch=[])
        repo = IntelligenceRepository(_pool(conn))
        out = await repo.quality_counts(customer_id="c", since=REF, until=REF)
        assert out == {}


class TestConversationCount:
    async def test_scalar(self):
        conn = _conn(fetchval=42)
        repo = IntelligenceRepository(_pool(conn))
        out = await repo.conversation_count(customer_id="c", since=REF, until=REF)
        assert out == 42

    async def test_tenant_scoped(self):
        conn = _conn(fetchval=0)
        repo = IntelligenceRepository(_pool(conn))
        await repo.conversation_count(customer_id="cust_x", since=REF, until=REF)
        assert "cust_x" in conn.fetchval.await_args.args
