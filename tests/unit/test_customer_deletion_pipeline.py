"""
Unit tests for the customer deletion pipeline.

These mock both storage clients so the pipeline's control logic
(ordering, idempotency, resume-after-failure, dry-run immutability) is
exercised without live infrastructure. Integration tests live elsewhere.
"""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The pipeline module hard-imports asyncpg and redis at module level.
# Skip this whole file if those aren't available rather than crashing collection.
pytest.importorskip("asyncpg")
pytest.importorskip("redis")

from src.security.customer_deletion_pipeline import (
    CustomerDeletionPipeline,
    DeletionVerifier,
    DeletionStep,
    StepStatus,
    StepResult,
    VerificationResult,
    STEP_ORDER,
    PG_VARCHAR_TABLES,
    PG_CASCADE_TABLES,
    _redis_db_for,
    _is_uuid,
)

REPO_ROOT = Path(__file__).parents[2]
SCHEMA_MAIN = REPO_ROOT / "src" / "database" / "schema.sql"
MIGRATIONS_DIR = REPO_ROOT / "src" / "database" / "migrations"

# Tables with a customer_id column that are deliberately excluded from
# deletion because they form the compliance audit trail.
AUDIT_SURVIVOR_TABLES = {"gdpr_compliance_audit", "customer_deletion_operations"}

# Tables with a customer_id column that are deleted via ON DELETE CASCADE
# from *another* customer-keyed table, not directly by the pipeline. These
# need exemption from the "every customer_id table must be in a pipeline
# list" check. Messages cascades from conversations; conversations itself
# IS in PG_VARCHAR_TABLES.
FK_CASCADE_COVERED_TABLES: set[str] = set()


def _extract_table_defs(sql: str) -> dict[str, str]:
    """Extract CREATE TABLE bodies. Regex is good enough: schema files are
    hand-written DDL, not arbitrary SQL."""
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\);",
        re.IGNORECASE | re.DOTALL,
    )
    return {m.group(1).lower(): m.group(2) for m in pattern.finditer(sql)}


@pytest.fixture(scope="module")
def schema_tables() -> dict[str, str]:
    defs = _extract_table_defs(SCHEMA_MAIN.read_text())
    # Migrations can introduce new tables; they must also be covered.
    for mig in sorted(MIGRATIONS_DIR.glob("*.sql")):
        defs.update(_extract_table_defs(mig.read_text()))
    return defs


# ─────────────────────────────────────────────────────────────────────────────
# Helpers: one AsyncMock asyncpg connection that emulates INSERT/UPDATE/SELECT
# on the step_state JSONB column, so resume logic can be tested.
# ─────────────────────────────────────────────────────────────────────────────

class FakePgState:
    """Minimal in-memory stand-in for customer_deletion_operations.step_state."""

    def __init__(self):
        self.step_state: dict = {}
        self.audit_rows: list = []
        self.deleted_tables: list[str] = []
        self.op_status: str | None = None
        # Ordered event log: ("persist", step) | ("flush", "redis") | ("delete", table)
        # Lets tests assert interleaving of step execution and durability writes.
        self.events: list[tuple[str, str]] = []

    def make_conn(self, *, varchar_delete_count: int = 2, customer_delete_count: int = 1):
        """Build an AsyncMock connection wired to this state."""
        conn = AsyncMock()

        async def execute(query, *args):
            q = " ".join(query.split())
            if "INSERT INTO customer_deletion_operations" in q:
                return "INSERT 0 1"
            if "UPDATE customer_deletion_operations SET step_state" in q:
                # args[1] is the JSON patch
                patch_dict = json.loads(args[1])
                self.step_state.update(patch_dict)
                for step_name in patch_dict:
                    self.events.append(("persist", step_name))
                return "UPDATE 1"
            if "UPDATE customer_deletion_operations SET status" in q:
                self.op_status = args[1]
                return "UPDATE 1"
            if "INSERT INTO gdpr_compliance_audit" in q:
                self.audit_rows.append(json.loads(args[1]))
                return "INSERT 0 1"
            if q.startswith("DELETE FROM customers"):
                self.deleted_tables.append("customers")
                self.events.append(("delete", "customers"))
                return f"DELETE {customer_delete_count}"
            if q.startswith("DELETE FROM"):
                tbl = q.split()[2]
                self.deleted_tables.append(tbl)
                self.events.append(("delete", tbl))
                return f"DELETE {varchar_delete_count}"
            return "OK"

        async def fetchval(query, *args):
            q = " ".join(query.split())
            if "SELECT step_state FROM customer_deletion_operations" in q:
                return dict(self.step_state)  # copy
            if "SELECT 1 FROM customers" in q:
                return 1
            if "count(*)" in q.lower():
                return 0  # verification / dry-run counts
            return None

        conn.execute = execute
        conn.fetchval = fetchval
        conn.transaction = MagicMock(return_value=AsyncMock())
        conn.transaction.return_value.__aenter__ = AsyncMock()
        conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
        return conn


def make_pool(conn):
    pool = AsyncMock()
    pool.acquire = MagicMock(return_value=AsyncMock())
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def make_redis(dbsize: int = 5, *, fail_flush: bool = False, events: list | None = None):
    r = AsyncMock()
    r.dbsize = AsyncMock(return_value=dbsize)
    if fail_flush:
        r.flushdb = AsyncMock(side_effect=ConnectionError("redis unreachable"))
    elif events is not None:
        async def _flush(**_):
            events.append(("flush", "redis"))
            return True
        r.flushdb = AsyncMock(side_effect=_flush)
    else:
        r.flushdb = AsyncMock(return_value=True)
    r.scan = AsyncMock(return_value=(0, ["key1", "key2"]))
    r.aclose = AsyncMock()
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Schema contract — table lists in the pipeline must match schema.sql
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaContract:
    """The pipeline hardcodes table lists. These pin them to the DDL.

    The completeness test is the one that matters: if someone adds a new
    table with a customer_id column and doesn't update the pipeline, that
    table silently survives deletion. GDPR violation in production.
    """

    def test_no_customer_id_table_escapes_deletion(self, schema_tables):
        """Every table with a customer_id column is either deleted or a
        declared audit survivor. No silent gaps."""
        covered = (
            set(PG_VARCHAR_TABLES)
            | set(PG_CASCADE_TABLES)
            | AUDIT_SURVIVOR_TABLES
            | {"customers"}  # root — the cascade anchor
        )
        uncovered = []
        for name, body in schema_tables.items():
            if re.search(r"\bcustomer_id\b", body, re.IGNORECASE) and name not in covered:
                uncovered.append(name)

        assert not uncovered, (
            f"Tables with customer_id not covered by deletion pipeline: {uncovered}. "
            f"Add to PG_VARCHAR_TABLES or PG_CASCADE_TABLES in customer_deletion_pipeline.py, "
            f"or to AUDIT_SURVIVOR_TABLES here if the omission is deliberate."
        )

    @pytest.mark.parametrize("table", PG_CASCADE_TABLES)
    def test_cascade_table_has_on_delete_cascade(self, schema_tables, table):
        """Pipeline relies on FK cascade from customers. If a table lacks
        ON DELETE CASCADE, deleting the customers row FK-violates instead
        of cascading — the pipeline would report success on a failed txn."""
        assert table in schema_tables, f"{table} not found in schema.sql"
        body = schema_tables[table]

        # customer_id ... REFERENCES customers(id) ON DELETE CASCADE
        fk_line = re.search(
            r"customer_id\s+UUID\b[^,]*?REFERENCES\s+customers\s*\(\s*id\s*\)[^,]*",
            body, re.IGNORECASE | re.DOTALL,
        )
        assert fk_line, f"{table}.customer_id has no FK to customers(id)"
        assert re.search(r"ON\s+DELETE\s+CASCADE", fk_line.group(0), re.IGNORECASE), (
            f"{table}.customer_id FK lacks ON DELETE CASCADE — cascade delete will fail"
        )

    @pytest.mark.parametrize("table", PG_VARCHAR_TABLES)
    def test_varchar_table_needs_explicit_delete(self, schema_tables, table):
        """These tables have no FK, so cascade won't touch them. Verify
        that's actually true — if someone adds an FK later, the explicit
        delete becomes redundant (harmless) but the categorization is wrong."""
        assert table in schema_tables, f"{table} not found in schema.sql"
        body = schema_tables[table]

        # Pipeline passes a Python str. TEXT and VARCHAR both accept that;
        # what we're guarding against is a UUID-typed customer_id that
        # would need a cast.
        assert re.search(r"\bcustomer_id\s+(VARCHAR|TEXT)", body, re.IGNORECASE), (
            f"{table}.customer_id is not VARCHAR/TEXT — pipeline passes str, may type-mismatch"
        )
        # No FK to customers on the customer_id column
        cid_decl = re.search(r"customer_id\b[^,\n]*", body, re.IGNORECASE).group(0)
        assert "REFERENCES" not in cid_decl.upper(), (
            f"{table}.customer_id has FK — belongs in PG_CASCADE_TABLES, not PG_VARCHAR_TABLES"
        )

    @pytest.mark.parametrize("table", sorted(AUDIT_SURVIVOR_TABLES))
    def test_audit_table_survives_cascade(self, schema_tables, table):
        """Audit tables MUST NOT have an FK to customers. If they do, the
        cascade wipes the proof that the deletion happened — the one record
        GDPR requires us to keep."""
        assert table in schema_tables, f"{table} not found in schema.sql"
        body = schema_tables[table]
        assert not re.search(
            r"customer_id\b[^,]*REFERENCES\s+customers", body, re.IGNORECASE
        ), (
            f"{table}.customer_id has FK to customers — "
            f"audit trail would be destroyed by the cascade it records"
        )

    def test_customers_table_exists(self, schema_tables):
        """The cascade anchor. If renamed, DELETE FROM customers does nothing."""
        assert "customers" in schema_tables
        assert re.search(r"\bid\s+UUID\s+PRIMARY\s+KEY", schema_tables["customers"], re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# Naming / hashing
# ─────────────────────────────────────────────────────────────────────────────

class TestResourceNaming:
    @pytest.mark.parametrize("cid,expected", [
        ("abc1234f", int("234f", 16) % 16),
        ("deadbeef", int("beef", 16) % 16),
        ("550e8400e29b41d4a716446655440000", 0),
    ])
    def test_redis_db_hash(self, cid, expected):
        assert _redis_db_for(cid) == expected

    def test_uuid_detection(self):
        assert _is_uuid("550e8400-e29b-41d4-a716-446655440000")
        assert not _is_uuid("not-a-uuid")
        assert not _is_uuid("abc123")


# ─────────────────────────────────────────────────────────────────────────────
# Step ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestStepOrder:
    def test_postgres_is_last(self):
        """Audit record must be written before customers cascade fires."""
        assert STEP_ORDER[-1] == DeletionStep.POSTGRES

    def test_redis_is_first(self):
        """Ephemeral data first — lowest cost on failure."""
        assert STEP_ORDER[0] == DeletionStep.REDIS

    def test_all_stores_covered(self):
        assert set(STEP_ORDER) == {DeletionStep.REDIS, DeletionStep.POSTGRES}


# ─────────────────────────────────────────────────────────────────────────────
# Execute: happy path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestExecuteHappyPath:

    async def test_all_steps_run_in_order(self):
        state = FakePgState()
        conn = state.make_conn()
        pool = make_pool(conn)
        redis_mock = make_redis(dbsize=5)

        pipeline = CustomerDeletionPipeline(
            "550e8400-e29b-41d4-a716-446655440000",
            reason="test", deletion_id="del_test1",
        )
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock):
            report = await pipeline.execute()

        # Both steps ran, in order
        assert [s.step for s in report.steps] == STEP_ORDER
        assert all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in report.steps)

        # Redis flushed
        redis_mock.flushdb.assert_awaited_once()
        # Postgres deleted varchar tables + customers
        assert "customers" in state.deleted_tables
        for tbl in PG_VARCHAR_TABLES:
            assert tbl in state.deleted_tables

    async def test_final_status_verified_when_clean(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_clean")
        pipeline._pg_pool = pool

        # All stores report empty on verification
        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(dbsize=0)):
            report = await pipeline.execute()

        assert report.status == "verified"
        assert report.complete is True
        assert report.verification is not None
        assert report.verification.clean is True
        assert state.op_status == "verified"

    async def test_audit_trail_written(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline(
            "deadbeef", reason="customer_request",
            requested_by="ops@example.com", deletion_id="del_audit",
        )
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)):
            await pipeline.execute()

        assert len(state.audit_rows) == 1
        audit = state.audit_rows[0]
        assert audit["deletion_id"] == "del_audit"
        assert audit["customer_id"] == "deadbeef"
        assert audit["reason"] == "customer_request"
        assert audit["requested_by"] == "ops@example.com"
        assert audit["gdpr_article"] == "Article 17"
        assert len(audit["steps"]) == len(STEP_ORDER)
        assert audit["verification"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Partial failure & resume
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPartialFailure:

    async def test_redis_failure_halts_pipeline(self):
        """When step N fails, steps N+1..end don't run."""
        state = FakePgState()
        pool = make_pool(state.make_conn())
        redis_mock = make_redis(dbsize=3, fail_flush=True)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_fail")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock):
            report = await pipeline.execute()

        assert report.status == "failed"
        assert report.complete is False
        assert report.verification is None  # don't verify on failure

        # Redis failed, Postgres never ran
        step_map = {s.step: s for s in report.steps}
        assert step_map[DeletionStep.REDIS].status == StepStatus.FAILED
        assert DeletionStep.POSTGRES not in step_map

        # Postgres customer row NOT deleted
        assert "customers" not in state.deleted_tables
        assert state.deleted_tables == []

    async def test_failure_state_persisted(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_persist")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis",
                   return_value=make_redis(3, fail_flush=True)):
            await pipeline.execute()

        # Failed step recorded; downstream step never written
        assert state.step_state["redis"]["status"] == "failed"
        assert "postgres" not in state.step_state
        assert state.op_status == "failed"

    async def test_step_persisted_before_next_step_begins(self):
        """Crash-recovery guarantee: if the process dies between steps, step_state
        already reflects the last completed step. Asserted via event interleaving:
        persist(N) must appear before any destructive op on store N+1."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        redis_mock = make_redis(dbsize=3, events=state.events)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_durable")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock):
            await pipeline.execute()

        ev = state.events
        persist_r = ev.index(("persist", "redis"))
        first_pg_delete = next(i for i, e in enumerate(ev) if e[0] == "delete")

        # THE invariant: step N's completion is on disk before step N+1's
        # destructive op begins. If execute() ever batched persists or moved
        # _persist_step after the loop, this catches it.
        assert persist_r < first_pg_delete, \
            f"redis completion not durable before postgres deletion began: {ev}"

    async def test_resume_skips_completed_steps(self):
        """Second run with same deletion_id picks up from failure point."""
        state = FakePgState()
        # Seed: redis already done in a prior run
        state.step_state = {
            "redis": {"status": "completed", "items_deleted": 5, "detail": {}, "at": "2026-01-01T00:00:00Z"},
        }
        pool = make_pool(state.make_conn())

        redis_mock = make_redis(dbsize=999)  # should NOT be flushed

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_resume")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock):
            report = await pipeline.execute()

        # Redis flush NOT called — prior completion honoured
        redis_mock.flushdb.assert_not_awaited()
        # Postgres DID run
        assert state.deleted_tables  # tables were deleted this run

        # Report shows both steps, first marked as resumed
        assert len(report.steps) == 2
        assert report.steps[0].detail.get("resumed") is True
        assert report.steps[1].detail.get("resumed") is not True


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestIdempotency:

    async def test_second_run_on_completed_customer_is_noop(self):
        """Running deletion twice: second run finds all stores empty, no errors."""
        state = FakePgState()
        pool = make_pool(state.make_conn(varchar_delete_count=0, customer_delete_count=0))

        # Every store reports "already gone"
        redis_mock = make_redis(dbsize=0)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_idem")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock):
            report = await pipeline.execute()

        # All steps report SKIPPED (nothing to delete)
        assert all(s.status == StepStatus.SKIPPED for s in report.steps)
        assert report.status == "verified"
        assert report.error is None


# ─────────────────────────────────────────────────────────────────────────────
# Dry run
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDryRun:

    async def test_dry_run_does_not_mutate(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())
        redis_mock = make_redis(dbsize=100)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_dry")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock):
            report = await pipeline.dry_run()

        # No destructive calls
        redis_mock.flushdb.assert_not_awaited()
        assert state.deleted_tables == []

        # Counts reported correctly
        assert report.redis["key_count"] == 100

    async def test_dry_run_reports_redis_db_number(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        customer_id = "abcd1234"
        expected_db = _redis_db_for(customer_id)

        pipeline = CustomerDeletionPipeline(customer_id, deletion_id="del_drydb")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(5)):
            report = await pipeline.dry_run()

        assert report.redis["db_number"] == expected_db
        # Collision warning present
        assert any("Redis DB" in w and "% 16" in w for w in report.warnings)

    async def test_dry_run_flags_non_uuid_customer(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        # Non-UUID but hex-suffix (_redis_db_for requires last 4 chars parseable as hex)
        pipeline = CustomerDeletionPipeline("legacy-customer-abcd", deletion_id="del_nouuid")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)):
            report = await pipeline.dry_run()

        assert any("not a UUID" in w for w in report.warnings)
        assert report.postgres["customer_row_exists"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Verifier
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDeletionVerifier:

    async def test_clean_when_all_stores_empty(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        verifier = DeletionVerifier("deadbeef", pg_pool=pool)

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)):
            result = await verifier.verify()

        assert result.clean is True
        assert result.redis_remaining == 0
        assert result.postgres_remaining == {}

    async def test_not_clean_when_redis_has_keys(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        verifier = DeletionVerifier("deadbeef", pg_pool=pool)

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(dbsize=3)):
            result = await verifier.verify()

        assert result.clean is False
        assert result.redis_remaining == 3

    async def test_store_error_recorded_not_raised(self):
        """Verification must report errors, not crash — partial results still useful."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        bad_redis = AsyncMock()
        bad_redis.dbsize = AsyncMock(side_effect=ConnectionError("down"))
        bad_redis.aclose = AsyncMock()

        verifier = DeletionVerifier("deadbeef", pg_pool=pool)

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=bad_redis):
            result = await verifier.verify()

        assert result.clean is False
        assert any("redis" in e for e in result.errors)
        assert result.redis_remaining == -1  # sentinel
        # Other stores still checked
        assert result.postgres_remaining == {}


# ─────────────────────────────────────────────────────────────────────────────
# Postgres handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPostgresDeletion:

    async def test_non_uuid_customer_skips_cascade(self):
        """VARCHAR-only customer: delete varchar tables but don't touch customers."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("text-id-1234", deletion_id="del_varchar")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)):
            report = await pipeline.execute()

        pg_step = next(s for s in report.steps if s.step == DeletionStep.POSTGRES)
        assert pg_step.detail["tables"]["customers_cascade"] == 0
        assert "customers" not in state.deleted_tables
        # VARCHAR tables still deleted
        for tbl in PG_VARCHAR_TABLES:
            assert tbl in state.deleted_tables

    async def test_varchar_tables_deleted_before_cascade(self):
        """Order within the Postgres step: explicit deletes first, cascade last."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline(
            "550e8400-e29b-41d4-a716-446655440000", deletion_id="del_order"
        )
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)):
            await pipeline.execute()

        # customers is last in the delete order
        assert state.deleted_tables[-1] == "customers"
        customers_idx = state.deleted_tables.index("customers")
        for tbl in PG_VARCHAR_TABLES:
            assert state.deleted_tables.index(tbl) < customers_idx


# ─────────────────────────────────────────────────────────────────────────────
# Report serialization
# ─────────────────────────────────────────────────────────────────────────────

class TestSerialization:
    def test_step_result_to_dict_uses_string_enums(self):
        r = StepResult(step=DeletionStep.REDIS, status=StepStatus.COMPLETED, items_deleted=5)
        d = r.to_dict()
        assert d["step"] == "redis"
        assert d["status"] == "completed"
        # Round-trips through JSON
        json.dumps(d)

    def test_verification_result_clean_computed(self):
        v = VerificationResult(
            customer_id="x", verified_at="t",
            redis_remaining=0, postgres_remaining={},
        )
        assert v.clean is True
        assert v.to_dict()["clean"] is True

        v2 = VerificationResult(
            customer_id="x", verified_at="t",
            redis_remaining=0, postgres_remaining={"agent_memories": 1},
        )
        assert v2.clean is False
