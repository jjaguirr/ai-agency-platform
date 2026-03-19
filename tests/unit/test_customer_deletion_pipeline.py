"""
Unit tests for the customer deletion pipeline.

These mock all four storage clients so the pipeline's control logic
(ordering, idempotency, resume-after-failure, dry-run immutability) is
exercised without live infrastructure. Integration tests live elsewhere.
"""

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# The pipeline module hard-imports asyncpg, neo4j, redis at module level.
# Skip this whole file if those aren't available rather than crashing collection.
pytest.importorskip("asyncpg")
pytest.importorskip("neo4j")
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
    _qdrant_collection_for,
    _neo4j_database_for,
    _is_uuid,
)

REPO_ROOT = Path(__file__).parents[2]
SCHEMA_MAIN = REPO_ROOT / "src" / "database" / "schema.sql"
SCHEMA_MEM = REPO_ROOT / "src" / "memory" / "schema.sql"

# Tables with a customer_id column that are deliberately excluded from
# deletion because they form the compliance audit trail.
AUDIT_SURVIVOR_TABLES = {"gdpr_compliance_audit", "customer_deletion_operations"}


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
    defs.update(_extract_table_defs(SCHEMA_MEM.read_text()))
    # Include migration files
    migrations_dir = REPO_ROOT / "src" / "database" / "migrations"
    if migrations_dir.is_dir():
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            defs.update(_extract_table_defs(sql_file.read_text()))
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
        # Ordered event log: ("persist", step) | ("flush", "redis") | ("drop", store)
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
                return f"DELETE {customer_delete_count}"
            if q.startswith("DELETE FROM"):
                tbl = q.split()[2]
                self.deleted_tables.append(tbl)
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


def make_httpx(*, collection_exists: bool = True, points: int = 42, fail_delete: bool = False, events: list | None = None):
    client = AsyncMock()

    get_resp = MagicMock()
    if collection_exists:
        get_resp.status_code = 200
        get_resp.json = MagicMock(return_value={"result": {"points_count": points, "vectors_count": points}})
        get_resp.raise_for_status = MagicMock()
    else:
        get_resp.status_code = 404
    client.get = AsyncMock(return_value=get_resp)

    del_resp = MagicMock()
    del_resp.status_code = 200
    if fail_delete:
        del_resp.raise_for_status = MagicMock(side_effect=RuntimeError("qdrant timeout"))
    else:
        del_resp.raise_for_status = MagicMock()
    if events is not None:
        async def _delete(*_a, **_k):
            events.append(("drop", "qdrant"))
            return del_resp
        client.delete = AsyncMock(side_effect=_delete)
    else:
        client.delete = AsyncMock(return_value=del_resp)

    # context manager
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm, client


def make_neo4j(*, db_exists: bool = True, nodes: int = 10, rels: int = 7):
    driver = AsyncMock()

    # system session: SHOW DATABASES
    sys_single = AsyncMock(return_value={"c": 1 if db_exists else 0})
    sys_result = AsyncMock()
    sys_result.single = sys_single
    sys_run = AsyncMock(return_value=sys_result)

    sys_session = AsyncMock()
    sys_session.run = sys_run

    # data session: counts
    node_single = AsyncMock(return_value={"c": nodes})
    rel_single = AsyncMock(return_value={"c": rels})
    node_result = AsyncMock(); node_result.single = node_single
    rel_result = AsyncMock(); rel_result.single = rel_single

    data_run_calls = [node_result, rel_result]
    data_session = AsyncMock()
    data_session.run = AsyncMock(side_effect=data_run_calls)

    # session(database=...) routes to sys or data
    def session_router(database=None):
        cm = MagicMock()
        s = sys_session if database == "system" else data_session
        cm.__aenter__ = AsyncMock(return_value=s)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    driver.session = MagicMock(side_effect=session_router)
    driver.close = AsyncMock()
    return driver, sys_session


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

        assert re.search(r"\bcustomer_id\s+(?:VARCHAR|TEXT)", body, re.IGNORECASE), (
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
# Qdrant response contract — pin the JSON path we parse
# ─────────────────────────────────────────────────────────────────────────────

# Shape recorded from Qdrant 1.x GET /collections/{name}. If Qdrant 2.x moves
# points_count, the dry-run/verify silently report 0. This test localizes the
# assumption.
QDRANT_COLLECTION_INFO_RESPONSE = {
    "result": {
        "status": "green",
        "optimizer_status": "ok",
        "vectors_count": 1247,
        "indexed_vectors_count": 1247,
        "points_count": 1247,
        "segments_count": 2,
        "config": {
            "params": {"vectors": {"size": 1536, "distance": "Cosine"}},
            "hnsw_config": {"m": 16, "ef_construct": 100},
        },
        "payload_schema": {},
    },
    "status": "ok",
    "time": 0.000123,
}


def _qdrant_cm(payload: dict, status: int = 200):
    resp = MagicMock(status_code=status)
    resp.json = MagicMock(return_value=payload)
    resp.raise_for_status = MagicMock()
    client = AsyncMock(); client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
class TestQdrantResponseContract:
    """Feed recorded Qdrant payloads through the ACTUAL pipeline methods.
    No re-derived parsing — if the pipeline's JSON path is wrong, these fail."""

    async def test_count_extracts_points_from_real_shape(self):
        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_qshape")
        with patch("src.security.customer_deletion_pipeline.httpx.AsyncClient",
                   return_value=_qdrant_cm(QDRANT_COLLECTION_INFO_RESPONSE)):
            result = await pipeline._count_qdrant(warnings=[])
        assert result["point_count"] == 1247
        assert result["exists"] is True

    async def test_count_handles_empty_result_body(self):
        """Qdrant 200 with {} — unlikely but shouldn't crash dry-run."""
        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_qempty")
        with patch("src.security.customer_deletion_pipeline.httpx.AsyncClient",
                   return_value=_qdrant_cm({})):
            result = await pipeline._count_qdrant(warnings=[])
        assert result["point_count"] == 0

    async def test_verifier_reads_same_path(self):
        """_count_qdrant and DeletionVerifier._check_qdrant must agree —
        both should find 1247. Divergent parsing = verify says clean when it isn't."""
        verifier = DeletionVerifier("deadbeef")
        with patch("src.security.customer_deletion_pipeline.httpx.AsyncClient",
                   return_value=_qdrant_cm(QDRANT_COLLECTION_INFO_RESPONSE)):
            remaining = await verifier._check_qdrant(errors=[])
        assert remaining == 1247


# ─────────────────────────────────────────────────────────────────────────────
# Naming / hashing — pinned against EAMemoryManager, not re-derived
# ─────────────────────────────────────────────────────────────────────────────

def _ea_config(customer_id: str) -> dict:
    """Get EAMemoryManager's config without triggering Mem0 client init."""
    with patch("src.memory.mem0_manager.EAMemoryManager._initialize_mem0", return_value=MagicMock()):
        from src.memory.mem0_manager import EAMemoryManager
        return EAMemoryManager(customer_id).config


class TestResourceNaming:
    """If EAMemoryManager changes its naming, these fail — that's the point.
    Deleting the wrong Redis DB / Qdrant collection is a data-loss bug."""

    @pytest.mark.parametrize("cid", ["abc1234f", "deadbeef", "550e8400e29b41d4a716446655440000"])
    def test_redis_db_matches_mem0_manager(self, cid):
        assert _redis_db_for(cid) == _ea_config(cid)["redis"]["db"]

    @pytest.mark.parametrize("cid", ["abc123", "deadbeef"])
    def test_qdrant_collection_matches_mem0_manager(self, cid):
        expected = _ea_config(cid)["mem0"]["vector_store"]["config"]["collection_name"]
        assert _qdrant_collection_for(cid) == expected

    @pytest.mark.parametrize("cid", ["abc123", "deadbeef"])
    def test_neo4j_database_matches_mem0_manager(self, cid):
        expected = _ea_config(cid)["mem0"]["graph_store"]["config"]["database"]
        assert _neo4j_database_for(cid) == expected

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

    def test_all_four_stores_covered(self):
        assert set(STEP_ORDER) == {
            DeletionStep.REDIS, DeletionStep.QDRANT,
            DeletionStep.NEO4J, DeletionStep.POSTGRES,
        }


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
        httpx_cm, _ = make_httpx(points=42)
        neo4j_driver, _ = make_neo4j(nodes=10, rels=7)

        pipeline = CustomerDeletionPipeline(
            "550e8400-e29b-41d4-a716-446655440000",
            reason="test", deletion_id="del_test1",
        )
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=httpx_cm), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=neo4j_driver):
            report = await pipeline.execute()

        # All four steps ran, in order
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
        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(dbsize=0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
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

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            await pipeline.execute()

        assert len(state.audit_rows) == 1
        audit = state.audit_rows[0]
        assert audit["deletion_id"] == "del_audit"
        assert audit["customer_id"] == "deadbeef"
        assert audit["reason"] == "customer_request"
        assert audit["requested_by"] == "ops@example.com"
        assert audit["gdpr_article"] == "Article 17"
        assert len(audit["steps"]) == 4
        assert audit["verification"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Partial failure & resume
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPartialFailure:

    async def test_qdrant_failure_halts_pipeline(self):
        """When step N fails, steps N+1..end don't run."""
        state = FakePgState()
        pool = make_pool(state.make_conn())
        redis_mock = make_redis(dbsize=3)
        httpx_cm, _ = make_httpx(fail_delete=True)  # Qdrant delete fails
        neo4j_driver, _ = make_neo4j()

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_fail")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=httpx_cm), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=neo4j_driver):
            report = await pipeline.execute()

        assert report.status == "failed"
        assert report.complete is False
        assert report.verification is None  # don't verify on failure

        # Redis ran, Qdrant failed, Neo4j/Postgres never ran
        step_map = {s.step: s for s in report.steps}
        assert step_map[DeletionStep.REDIS].status == StepStatus.COMPLETED
        assert step_map[DeletionStep.QDRANT].status == StepStatus.FAILED
        assert DeletionStep.NEO4J not in step_map
        assert DeletionStep.POSTGRES not in step_map

        # Postgres customer row NOT deleted
        assert "customers" not in state.deleted_tables
        # Neo4j driver never constructed
        neo4j_driver.session.assert_not_called()

    async def test_failure_state_persisted(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_persist")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(3)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(fail_delete=True)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j()[0]):
            await pipeline.execute()

        # Step state recorded for both attempted steps
        assert state.step_state["redis"]["status"] == "completed"
        assert state.step_state["qdrant"]["status"] == "failed"
        assert "neo4j" not in state.step_state
        assert state.op_status == "failed"

    async def test_step_persisted_before_next_step_begins(self):
        """Crash-recovery guarantee: if the process dies between steps, step_state
        already reflects the last completed step. Asserted via event interleaving:
        persist(N) must appear before any destructive op on store N+1."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        redis_mock = make_redis(dbsize=3, events=state.events)
        httpx_cm, _ = make_httpx(points=10, events=state.events)
        neo4j_driver, _ = make_neo4j(db_exists=False)  # skip — simpler event log

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_durable")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=httpx_cm), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=neo4j_driver):
            await pipeline.execute()

        ev = state.events
        persist_r = ev.index(("persist", "redis"))
        drop_q    = ev.index(("drop", "qdrant"))

        # THE invariant: step N's completion is on disk before step N+1's
        # destructive op begins. If execute() ever batched persists or moved
        # _persist_step after the loop, this catches it.
        assert persist_r < drop_q, \
            f"redis completion not durable before qdrant deletion began: {ev}"

    async def test_resume_skips_completed_steps(self):
        """Second run with same deletion_id picks up from failure point."""
        state = FakePgState()
        # Seed: redis + qdrant already done in a prior run
        state.step_state = {
            "redis": {"status": "completed", "items_deleted": 5, "detail": {}, "at": "2026-01-01T00:00:00Z"},
            "qdrant": {"status": "skipped", "items_deleted": 0, "detail": {}, "at": "2026-01-01T00:00:01Z"},
        }
        pool = make_pool(state.make_conn())

        redis_mock = make_redis(dbsize=999)  # should NOT be flushed
        httpx_cm, httpx_client = make_httpx()
        neo4j_driver, _ = make_neo4j(db_exists=False)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_resume")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=httpx_cm), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=neo4j_driver):
            report = await pipeline.execute()

        # Redis flush NOT called — prior completion honoured
        redis_mock.flushdb.assert_not_awaited()
        # Qdrant delete NOT called
        httpx_client.delete.assert_not_awaited()
        # Neo4j and Postgres DID run
        neo4j_driver.session.assert_called()

        # Report shows all 4 steps, first two marked as resumed
        assert len(report.steps) == 4
        assert report.steps[0].detail.get("resumed") is True
        assert report.steps[1].detail.get("resumed") is True
        assert report.steps[2].detail.get("resumed") is not True


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
        httpx_cm, _ = make_httpx(collection_exists=False)
        neo4j_driver, _ = make_neo4j(db_exists=False)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_idem")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=httpx_cm), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=neo4j_driver):
            report = await pipeline.execute()

        # All steps report SKIPPED (nothing to delete)
        assert all(s.status == StepStatus.SKIPPED for s in report.steps)
        assert report.status == "verified"
        assert report.error is None

    async def test_qdrant_404_is_skip_not_failure(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_q404")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            report = await pipeline.execute()

        qdrant_step = next(s for s in report.steps if s.step == DeletionStep.QDRANT)
        assert qdrant_step.status == StepStatus.SKIPPED
        assert qdrant_step.detail.get("reason") == "not_found"

    async def test_neo4j_missing_db_is_skip(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_n404")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            report = await pipeline.execute()

        neo4j_step = next(s for s in report.steps if s.step == DeletionStep.NEO4J)
        assert neo4j_step.status == StepStatus.SKIPPED


# ─────────────────────────────────────────────────────────────────────────────
# Dry run
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDryRun:

    async def test_dry_run_does_not_mutate(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())
        redis_mock = make_redis(dbsize=100)
        httpx_cm, httpx_client = make_httpx(points=200)
        neo4j_driver, sys_session = make_neo4j(nodes=50, rels=30)

        pipeline = CustomerDeletionPipeline("deadbeef", deletion_id="del_dry")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=redis_mock), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=httpx_cm), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=neo4j_driver):
            report = await pipeline.dry_run()

        # No destructive calls
        redis_mock.flushdb.assert_not_awaited()
        httpx_client.delete.assert_not_awaited()
        # System session ran SHOW DATABASES but no DROP
        for call in sys_session.run.await_args_list:
            assert "DROP" not in call.args[0]
        assert state.deleted_tables == []

        # Counts reported correctly
        assert report.redis["key_count"] == 100
        assert report.qdrant["point_count"] == 200
        assert report.neo4j["node_count"] == 50
        assert report.neo4j["rel_count"] == 30

    async def test_dry_run_reports_redis_db_number(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        customer_id = "abcd1234"
        expected_db = _redis_db_for(customer_id)

        pipeline = CustomerDeletionPipeline(customer_id, deletion_id="del_drydb")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(5)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx()[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j()[0]):
            report = await pipeline.dry_run()

        assert report.redis["db_number"] == expected_db
        # Collision warning present
        assert any("Redis DB" in w and "% 16" in w for w in report.warnings)

    async def test_dry_run_flags_non_uuid_customer(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        # Non-UUID but hex-suffix (mem0_manager requires last 4 chars parseable as hex)
        pipeline = CustomerDeletionPipeline("legacy-customer-abcd", deletion_id="del_nouuid")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
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

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            result = await verifier.verify()

        assert result.clean is True
        assert result.redis_remaining == 0
        assert result.qdrant_remaining == 0
        assert result.neo4j_remaining == 0
        assert result.postgres_remaining == {}

    async def test_not_clean_when_redis_has_keys(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        verifier = DeletionVerifier("deadbeef", pg_pool=pool)

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(dbsize=3)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            result = await verifier.verify()

        assert result.clean is False
        assert result.redis_remaining == 3

    async def test_not_clean_when_qdrant_collection_survives(self):
        state = FakePgState()
        pool = make_pool(state.make_conn())

        verifier = DeletionVerifier("deadbeef", pg_pool=pool)

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=True, points=7)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            result = await verifier.verify()

        assert result.clean is False
        assert result.qdrant_remaining == 7

    async def test_store_error_recorded_not_raised(self):
        """Verification must report errors, not crash — partial results still useful."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        bad_redis = AsyncMock()
        bad_redis.dbsize = AsyncMock(side_effect=ConnectionError("down"))
        bad_redis.aclose = AsyncMock()

        verifier = DeletionVerifier("deadbeef", pg_pool=pool)

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=bad_redis), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
            result = await verifier.verify()

        assert result.clean is False
        assert any("redis" in e for e in result.errors)
        assert result.redis_remaining == -1  # sentinel
        # Other stores still checked
        assert result.qdrant_remaining == 0


# ─────────────────────────────────────────────────────────────────────────────
# Postgres handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPostgresDeletion:

    async def test_non_uuid_customer_skips_cascade(self):
        """VARCHAR-only customer: delete memory tables but don't touch customers."""
        state = FakePgState()
        pool = make_pool(state.make_conn())

        pipeline = CustomerDeletionPipeline("text-id-1234", deletion_id="del_varchar")
        pipeline._pg_pool = pool

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
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

        with patch("src.security.customer_deletion_pipeline.redis.Redis", return_value=make_redis(0)), \
             patch("src.security.customer_deletion_pipeline.httpx.AsyncClient", return_value=make_httpx(collection_exists=False)[0]), \
             patch("src.security.customer_deletion_pipeline.AsyncGraphDatabase.driver", return_value=make_neo4j(db_exists=False)[0]):
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
            redis_remaining=0, qdrant_remaining=0, neo4j_remaining=0,
            postgres_remaining={},
        )
        assert v.clean is True
        assert v.to_dict()["clean"] is True

        v2 = VerificationResult(
            customer_id="x", verified_at="t",
            redis_remaining=0, qdrant_remaining=0, neo4j_remaining=0,
            postgres_remaining={"agent_memories": 1},
        )
        assert v2.clean is False
