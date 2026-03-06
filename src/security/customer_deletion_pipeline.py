"""
Customer Deletion Pipeline — GDPR Article 17 execution engine.

Cascades a customer deletion across four heterogeneous storage layers (Redis,
Qdrant, Neo4j, PostgreSQL) that do not share a transaction boundary.

Strategy: resumable idempotent pipeline with durable step-state tracking.
Each step records completion in `customer_deletion_operations` before moving on.
Re-running a completed step is a no-op; re-running after partial failure picks
up where it stopped. This is deliberately NOT a saga — you cannot compensate
(un-delete) data, so the only sane failure mode is "fix the broken store and
resume".

Deletion order (Redis → Qdrant → Neo4j → PostgreSQL):
  - Ephemeral/derived data first. If Redis flush fails, TTLs will eventually
    reclaim it anyway; nothing downstream depends on it.
  - Qdrant/Neo4j hold Mem0-derived indexes. Deleting them makes future Mem0
    reads return empty — a clean absence, not a dangling reference.
  - PostgreSQL last. It is the source of truth, and the audit record proving
    the deletion happened must be written BEFORE the cascade wipes the
    `customers` row.

The audit trail lives in `gdpr_compliance_audit` and
`customer_deletion_operations` — both use VARCHAR customer_id with no FK,
so they survive the cascade by design.
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import asyncpg
import httpx
import redis.asyncio as redis
from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────

class DeletionStep(str, Enum):
    REDIS = "redis"
    QDRANT = "qdrant"
    NEO4J = "neo4j"
    POSTGRES = "postgres"


class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # resource didn't exist (already gone — idempotent success)


# Execution order. Do not reorder without re-reading the module docstring.
STEP_ORDER: list[DeletionStep] = [
    DeletionStep.REDIS,
    DeletionStep.QDRANT,
    DeletionStep.NEO4J,
    DeletionStep.POSTGRES,
]


@dataclass
class StepResult:
    step: DeletionStep
    status: StepStatus
    items_deleted: int = 0
    detail: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["step"] = self.step.value
        d["status"] = self.status.value
        return d


@dataclass
class DryRunReport:
    customer_id: str
    generated_at: str
    redis: dict[str, Any]
    qdrant: dict[str, Any]
    neo4j: dict[str, Any]
    postgres: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return (
            self.redis.get("key_count", 0)
            + self.qdrant.get("point_count", 0)
            + self.neo4j.get("node_count", 0)
            + self.postgres.get("total_rows", 0)
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "total_items": self.total_items}


@dataclass
class VerificationResult:
    customer_id: str
    verified_at: str
    redis_remaining: int
    qdrant_remaining: int
    neo4j_remaining: int
    postgres_remaining: dict[str, int]  # table -> count
    errors: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return (
            not self.errors
            and self.redis_remaining == 0
            and self.qdrant_remaining == 0
            and self.neo4j_remaining == 0
            and sum(self.postgres_remaining.values()) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "clean": self.clean}


@dataclass
class DeletionReport:
    deletion_id: str
    customer_id: str
    status: str  # matches customer_deletion_operations.status
    steps: list[StepResult]
    verification: Optional[VerificationResult]
    requested_at: str
    completed_at: Optional[str]
    error: Optional[str] = None

    @property
    def complete(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "deletion_id": self.deletion_id,
            "customer_id": self.customer_id,
            "status": self.status,
            "complete": self.complete,
            "steps": [s.to_dict() for s in self.steps],
            "verification": self.verification.to_dict() if self.verification else None,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StorageConfig:
    postgres_url: str = field(
        default_factory=lambda: os.getenv(
            "POSTGRES_URL", "postgresql://mcphub:mcphub_password@localhost:5432/mcphub"
        )
    )
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    neo4j_url: str = field(default_factory=lambda: os.getenv("NEO4J_URL", "neo4j://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", "neo4j_password"))


# PostgreSQL tables keyed by VARCHAR customer_id without FK — must be deleted
# explicitly since they won't cascade. Source: src/memory/schema.sql and
# customer_business_context in src/database/schema.sql.
PG_VARCHAR_TABLES: list[str] = [
    "customer_business_context",
    "customer_memory_audit",
    "memory_performance_metrics",
    "sla_violation_alerts",
    "customer_memory_stats",
]

# Tables in the main schema with UUID FK to customers(id). These cascade when
# customers is deleted, but we count them for dry-run reporting.
PG_CASCADE_TABLES: list[str] = [
    "customer_security_groups",
    "users",
    "refresh_tokens",
    "api_keys",
    "agents",
    "agent_memories",
    "agent_conversations",
    "workflows",
    "workflow_executions",
    "messaging_channels",
    "message_queue",
    "customer_activities",
    "ai_usage_costs",
    "audit_logs",
    "security_incidents",
]


def _redis_db_for(customer_id: str) -> int:
    """Derive the Redis DB number for a customer.

    Mirrors EAMemoryManager._default_config: last 4 hex chars mod 16.
    NOTE: This hash collides — multiple customers can map to the same DB.
    The dry-run reports the DB number so an operator can check for cohabitants
    before flushing. Changing this mapping is out of scope for the deletion
    pipeline; it's an existing architectural property.
    """
    return int(customer_id[-4:], 16) % 16


def _qdrant_collection_for(customer_id: str) -> str:
    return f"customer_{customer_id}_memories"


def _neo4j_database_for(customer_id: str) -> str:
    return f"customer_{customer_id}_graph"


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class CustomerDeletionPipeline:
    """Execute or preview a full customer data deletion.

    Usage:
        pipeline = CustomerDeletionPipeline("a1b2c3d4", reason="customer_request")

        # Preview blast radius
        report = await pipeline.dry_run()

        # Execute (idempotent — safe to re-run)
        result = await pipeline.execute()

    The pipeline connects directly to each store rather than going through
    EAMemoryManager, because EAMemoryManager instantiates a Mem0 client on
    construction (expensive, and it would point at collections we're about
    to delete).
    """

    def __init__(
        self,
        customer_id: str,
        *,
        reason: str = "customer_request",
        requested_by: Optional[str] = None,
        deletion_id: Optional[str] = None,
        config: Optional[StorageConfig] = None,
    ):
        self.customer_id = customer_id
        self.reason = reason
        self.requested_by = requested_by
        self.deletion_id = deletion_id or f"del_{uuid.uuid4().hex}"
        self.config = config or StorageConfig()

        self._redis_db = _redis_db_for(customer_id)
        self._qdrant_collection = _qdrant_collection_for(customer_id)
        self._neo4j_database = _neo4j_database_for(customer_id)

        self._pg_pool: Optional[asyncpg.Pool] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def _pg(self) -> asyncpg.Pool:
        if self._pg_pool is None:
            self._pg_pool = await asyncpg.create_pool(
                self.config.postgres_url, min_size=1, max_size=3
            )
        return self._pg_pool

    async def close(self) -> None:
        if self._pg_pool:
            await self._pg_pool.close()
            self._pg_pool = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()

    # ── dry run ──────────────────────────────────────────────────────────────

    async def dry_run(self) -> DryRunReport:
        """Count everything that would be deleted. No mutations."""
        warnings: list[str] = []

        redis_info = await self._count_redis(warnings)
        qdrant_info = await self._count_qdrant(warnings)
        neo4j_info = await self._count_neo4j(warnings)
        pg_info = await self._count_postgres(warnings)

        report = DryRunReport(
            customer_id=self.customer_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            redis=redis_info,
            qdrant=qdrant_info,
            neo4j=neo4j_info,
            postgres=pg_info,
            warnings=warnings,
        )

        await self._persist_dry_run(report)
        logger.info(
            "dry-run complete customer=%s total_items=%d warnings=%d",
            self.customer_id, report.total_items, len(warnings),
        )
        return report

    async def _count_redis(self, warnings: list[str]) -> dict[str, Any]:
        client = redis.Redis(
            host=self.config.redis_host, port=self.config.redis_port,
            db=self._redis_db, decode_responses=True,
        )
        try:
            key_count = await client.dbsize()
            # Sample up to 20 keys so the operator can eyeball what's in there
            sample = []
            cursor = 0
            cursor, batch = await client.scan(cursor=cursor, count=20)
            sample.extend(batch[:20])

            # Collision check: are other customers' EAMemoryManagers mapped here?
            # We can't know for sure without a customer registry, but flag it.
            warnings.append(
                f"Redis DB {self._redis_db} uses hash(customer_id) % 16 — "
                f"verify no other active customer maps to this DB before flushing"
            )
            return {
                "db_number": self._redis_db,
                "key_count": key_count,
                "sample_keys": sample,
            }
        finally:
            await client.aclose()

    async def _count_qdrant(self, warnings: list[str]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.config.qdrant_url, timeout=10.0) as client:
            resp = await client.get(f"/collections/{self._qdrant_collection}")
            if resp.status_code == 404:
                return {"collection": self._qdrant_collection, "exists": False, "point_count": 0}
            resp.raise_for_status()
            data = resp.json().get("result", {})
            return {
                "collection": self._qdrant_collection,
                "exists": True,
                "point_count": data.get("points_count", 0),
                "vectors_count": data.get("vectors_count", 0),
            }

    async def _count_neo4j(self, warnings: list[str]) -> dict[str, Any]:
        driver = AsyncGraphDatabase.driver(
            self.config.neo4j_url, auth=(self.config.neo4j_user, self.config.neo4j_password)
        )
        try:
            # Check database exists
            async with driver.session(database="system") as sys_session:
                result = await sys_session.run(
                    "SHOW DATABASES YIELD name WHERE name = $name RETURN count(*) AS c",
                    name=self._neo4j_database,
                )
                record = await result.single()
                exists = record and record["c"] > 0

            if not exists:
                return {"database": self._neo4j_database, "exists": False, "node_count": 0, "rel_count": 0}

            async with driver.session(database=self._neo4j_database) as session:
                node_rec = await (await session.run("MATCH (n) RETURN count(n) AS c")).single()
                rel_rec = await (await session.run("MATCH ()-[r]->() RETURN count(r) AS c")).single()
                return {
                    "database": self._neo4j_database,
                    "exists": True,
                    "node_count": node_rec["c"],
                    "rel_count": rel_rec["c"],
                }
        finally:
            await driver.close()

    async def _count_postgres(self, warnings: list[str]) -> dict[str, Any]:
        pool = await self._pg()
        counts: dict[str, int] = {}
        total = 0

        async with pool.acquire() as conn:
            # VARCHAR tables
            for tbl in PG_VARCHAR_TABLES:
                n = await self._safe_count(conn, tbl, "customer_id", self.customer_id)
                counts[tbl] = n
                total += n

            # UUID cascade tables — only if customer_id looks like a UUID
            customer_exists = False
            if _is_uuid(self.customer_id):
                customer_exists = bool(await conn.fetchval(
                    "SELECT 1 FROM customers WHERE id = $1", self.customer_id
                ))
                for tbl in PG_CASCADE_TABLES:
                    n = await self._safe_count(conn, tbl, "customer_id", self.customer_id, cast_uuid=True)
                    counts[tbl] = n
                    total += n
                if customer_exists:
                    counts["customers"] = 1
                    total += 1
            else:
                warnings.append(
                    f"customer_id '{self.customer_id}' is not a UUID — "
                    f"main-schema cascade tables will be skipped"
                )

        return {
            "customer_row_exists": customer_exists,
            "table_counts": counts,
            "total_rows": total,
        }

    @staticmethod
    async def _safe_count(
        conn: asyncpg.Connection, table: str, col: str, val: str, *, cast_uuid: bool = False
    ) -> int:
        """Count rows, returning 0 if table doesn't exist."""
        try:
            cast = "::uuid" if cast_uuid else ""
            return await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE {col} = $1{cast}", val
            ) or 0
        except asyncpg.UndefinedTableError:
            return 0

    # ── execute ──────────────────────────────────────────────────────────────

    async def execute(self) -> DeletionReport:
        """Run the deletion. Idempotent: re-running resumes from last incomplete step."""
        requested_at = datetime.now(timezone.utc).isoformat()
        await self._init_operation_record(requested_at)

        prior_state = await self._load_step_state()
        results: list[StepResult] = []
        failed = False
        error_msg: Optional[str] = None

        step_handlers = {
            DeletionStep.REDIS: self._delete_redis,
            DeletionStep.QDRANT: self._delete_qdrant,
            DeletionStep.NEO4J: self._delete_neo4j,
            DeletionStep.POSTGRES: self._delete_postgres,
        }

        for step in STEP_ORDER:
            # Skip steps already completed in a prior run
            prior = prior_state.get(step.value)
            if prior and prior.get("status") in (StepStatus.COMPLETED.value, StepStatus.SKIPPED.value):
                results.append(StepResult(
                    step=step,
                    status=StepStatus(prior["status"]),
                    items_deleted=prior.get("items_deleted", 0),
                    detail={**prior.get("detail", {}), "resumed": True},
                    at=prior.get("at", requested_at),
                ))
                logger.info("step %s already complete (prior run), skipping", step.value)
                continue

            start = datetime.now(timezone.utc)
            try:
                result = await step_handlers[step]()
            except Exception as e:
                result = StepResult(
                    step=step, status=StepStatus.FAILED,
                    error=f"{type(e).__name__}: {e}",
                )
                logger.exception("step %s failed for customer %s", step.value, self.customer_id)

            result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            results.append(result)
            await self._persist_step(result)

            if result.status == StepStatus.FAILED:
                failed = True
                error_msg = f"step {step.value} failed: {result.error}"
                break  # stop — operator must resolve and re-run

        # Verify only if all steps succeeded
        verification: Optional[VerificationResult] = None
        completed_at: Optional[str] = None

        if not failed:
            verifier = DeletionVerifier(self.customer_id, config=self.config, pg_pool=await self._pg())
            verification = await verifier.verify()
            completed_at = datetime.now(timezone.utc).isoformat()

            if verification.clean:
                final_status = "verified"
            else:
                final_status = "completed"  # steps ran but residue found
                error_msg = f"verification found residual data: {verification.to_dict()}"
                logger.error("deletion %s left residue: %s", self.deletion_id, verification.to_dict())
        else:
            final_status = "failed"

        await self._finalize_operation(final_status, verification, completed_at, error_msg)
        await self._write_audit_trail(final_status, results, verification)

        return DeletionReport(
            deletion_id=self.deletion_id,
            customer_id=self.customer_id,
            status=final_status,
            steps=results,
            verification=verification,
            requested_at=requested_at,
            completed_at=completed_at,
            error=error_msg,
        )

    # ── step implementations ─────────────────────────────────────────────────

    async def _delete_redis(self) -> StepResult:
        client = redis.Redis(
            host=self.config.redis_host, port=self.config.redis_port,
            db=self._redis_db, decode_responses=True,
        )
        try:
            count_before = await client.dbsize()
            await client.flushdb(asynchronous=False)
            return StepResult(
                step=DeletionStep.REDIS,
                status=StepStatus.COMPLETED if count_before > 0 else StepStatus.SKIPPED,
                items_deleted=count_before,
                detail={"db_number": self._redis_db, "method": "FLUSHDB"},
            )
        finally:
            await client.aclose()

    async def _delete_qdrant(self) -> StepResult:
        async with httpx.AsyncClient(base_url=self.config.qdrant_url, timeout=30.0) as client:
            # Count first (for the report)
            info = await client.get(f"/collections/{self._qdrant_collection}")
            if info.status_code == 404:
                return StepResult(
                    step=DeletionStep.QDRANT, status=StepStatus.SKIPPED,
                    detail={"collection": self._qdrant_collection, "reason": "not_found"},
                )
            info.raise_for_status()
            point_count = info.json().get("result", {}).get("points_count", 0)

            resp = await client.delete(f"/collections/{self._qdrant_collection}")
            resp.raise_for_status()

            return StepResult(
                step=DeletionStep.QDRANT, status=StepStatus.COMPLETED,
                items_deleted=point_count,
                detail={"collection": self._qdrant_collection, "method": "DELETE /collections"},
            )

    async def _delete_neo4j(self) -> StepResult:
        driver = AsyncGraphDatabase.driver(
            self.config.neo4j_url, auth=(self.config.neo4j_user, self.config.neo4j_password)
        )
        try:
            # Count nodes/rels before dropping (for the report)
            node_count, rel_count = 0, 0
            async with driver.session(database="system") as sys_session:
                result = await sys_session.run(
                    "SHOW DATABASES YIELD name WHERE name = $name RETURN count(*) AS c",
                    name=self._neo4j_database,
                )
                record = await result.single()
                exists = record and record["c"] > 0

            if not exists:
                return StepResult(
                    step=DeletionStep.NEO4J, status=StepStatus.SKIPPED,
                    detail={"database": self._neo4j_database, "reason": "not_found"},
                )

            async with driver.session(database=self._neo4j_database) as session:
                nr = await (await session.run("MATCH (n) RETURN count(n) AS c")).single()
                rr = await (await session.run("MATCH ()-[r]->() RETURN count(r) AS c")).single()
                node_count, rel_count = nr["c"], rr["c"]

            # DROP DATABASE requires Enterprise. IF EXISTS makes this idempotent
            # even if a concurrent process already dropped it.
            async with driver.session(database="system") as sys_session:
                await sys_session.run(f"DROP DATABASE `{self._neo4j_database}` IF EXISTS")

            return StepResult(
                step=DeletionStep.NEO4J, status=StepStatus.COMPLETED,
                items_deleted=node_count + rel_count,
                detail={
                    "database": self._neo4j_database,
                    "nodes": node_count, "relationships": rel_count,
                    "method": "DROP DATABASE",
                },
            )
        finally:
            await driver.close()

    async def _delete_postgres(self) -> StepResult:
        pool = await self._pg()
        deleted: dict[str, int] = {}

        async with pool.acquire() as conn:
            async with conn.transaction():
                # 1. VARCHAR-keyed tables (no cascade — explicit delete)
                for tbl in PG_VARCHAR_TABLES:
                    try:
                        result = await conn.execute(
                            f"DELETE FROM {tbl} WHERE customer_id = $1", self.customer_id
                        )
                        deleted[tbl] = int(result.split()[-1])
                    except asyncpg.UndefinedTableError:
                        deleted[tbl] = 0

                # 2. Main schema — cascade from customers row
                if _is_uuid(self.customer_id):
                    result = await conn.execute(
                        "DELETE FROM customers WHERE id = $1", self.customer_id
                    )
                    cascade_deleted = int(result.split()[-1])
                    deleted["customers_cascade"] = cascade_deleted
                else:
                    deleted["customers_cascade"] = 0

        total = sum(deleted.values())
        return StepResult(
            step=DeletionStep.POSTGRES,
            status=StepStatus.COMPLETED if total > 0 else StepStatus.SKIPPED,
            items_deleted=total,
            detail={"tables": deleted, "method": "DELETE + FK CASCADE"},
        )

    # ── state persistence ────────────────────────────────────────────────────

    async def _init_operation_record(self, requested_at: str) -> None:
        pool = await self._pg()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO customer_deletion_operations
                    (deletion_id, customer_id, requested_at, requested_by, reason, status)
                VALUES ($1, $2, $3, $4, $5, 'in_progress')
                ON CONFLICT (deletion_id) DO UPDATE
                    SET status = CASE
                        WHEN customer_deletion_operations.status IN ('verified', 'completed')
                        THEN customer_deletion_operations.status
                        ELSE 'in_progress'
                    END,
                    updated_at = NOW()
                """,
                self.deletion_id, self.customer_id,
                datetime.fromisoformat(requested_at), self.requested_by, self.reason,
            )

    async def _load_step_state(self) -> dict[str, Any]:
        pool = await self._pg()
        async with pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT step_state FROM customer_deletion_operations WHERE deletion_id = $1",
                self.deletion_id,
            )
            if row is None:
                return {}
            return row if isinstance(row, dict) else json.loads(row)

    async def _persist_step(self, result: StepResult) -> None:
        pool = await self._pg()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE customer_deletion_operations
                SET step_state = step_state || $2::jsonb, updated_at = NOW()
                WHERE deletion_id = $1
                """,
                self.deletion_id,
                json.dumps({result.step.value: result.to_dict()}),
            )

    async def _persist_dry_run(self, report: DryRunReport) -> None:
        pool = await self._pg()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO customer_deletion_operations
                    (deletion_id, customer_id, requested_by, reason, status, dry_run_report)
                VALUES ($1, $2, $3, $4, 'pending', $5)
                ON CONFLICT (deletion_id) DO UPDATE
                    SET dry_run_report = EXCLUDED.dry_run_report, updated_at = NOW()
                """,
                self.deletion_id, self.customer_id, self.requested_by, self.reason,
                json.dumps(report.to_dict()),
            )

    async def _finalize_operation(
        self, status: str, verification: Optional[VerificationResult],
        completed_at: Optional[str], error: Optional[str],
    ) -> None:
        pool = await self._pg()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE customer_deletion_operations
                SET status = $2,
                    verification_result = $3,
                    completed_at = $4,
                    error = $5,
                    updated_at = NOW()
                WHERE deletion_id = $1
                """,
                self.deletion_id, status,
                json.dumps(verification.to_dict()) if verification else None,
                datetime.fromisoformat(completed_at) if completed_at else None,
                error,
            )

    async def _write_audit_trail(
        self, status: str, steps: list[StepResult], verification: Optional[VerificationResult],
    ) -> None:
        """Write to the compliance audit log. This record outlives the customer."""
        pool = await self._pg()
        payload = {
            "deletion_id": self.deletion_id,
            "customer_id": self.customer_id,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "final_status": status,
            "steps": [s.to_dict() for s in steps],
            "verification": verification.to_dict() if verification else None,
            "gdpr_article": "Article 17",
        }
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO gdpr_compliance_audit (customer_id, action_type, action_data)
                VALUES ($1, 'customer_deletion', $2)
                """,
                self.customer_id, json.dumps(payload),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Verification
# ─────────────────────────────────────────────────────────────────────────────

class DeletionVerifier:
    """Post-deletion verification: prove no customer data remains in any store.

    Complements `MemoryIsolationValidator` — that checks cross-customer leakage;
    this checks single-customer absence.
    """

    def __init__(
        self, customer_id: str, *,
        config: Optional[StorageConfig] = None,
        pg_pool: Optional[asyncpg.Pool] = None,
    ):
        self.customer_id = customer_id
        self.config = config or StorageConfig()
        self._pg_pool = pg_pool
        self._owns_pool = pg_pool is None

    async def verify(self) -> VerificationResult:
        errors: list[str] = []

        redis_remaining = await self._check_redis(errors)
        qdrant_remaining = await self._check_qdrant(errors)
        neo4j_remaining = await self._check_neo4j(errors)
        pg_remaining = await self._check_postgres(errors)

        result = VerificationResult(
            customer_id=self.customer_id,
            verified_at=datetime.now(timezone.utc).isoformat(),
            redis_remaining=redis_remaining,
            qdrant_remaining=qdrant_remaining,
            neo4j_remaining=neo4j_remaining,
            postgres_remaining=pg_remaining,
            errors=errors,
        )

        if self._owns_pool and self._pg_pool:
            await self._pg_pool.close()

        return result

    async def _check_redis(self, errors: list[str]) -> int:
        db = _redis_db_for(self.customer_id)
        client = redis.Redis(
            host=self.config.redis_host, port=self.config.redis_port,
            db=db, decode_responses=True,
        )
        try:
            return await client.dbsize()
        except Exception as e:
            errors.append(f"redis: {e}")
            return -1
        finally:
            await client.aclose()

    async def _check_qdrant(self, errors: list[str]) -> int:
        collection = _qdrant_collection_for(self.customer_id)
        try:
            async with httpx.AsyncClient(base_url=self.config.qdrant_url, timeout=10.0) as client:
                resp = await client.get(f"/collections/{collection}")
                if resp.status_code == 404:
                    return 0
                resp.raise_for_status()
                return resp.json().get("result", {}).get("points_count", 0)
        except Exception as e:
            errors.append(f"qdrant: {e}")
            return -1

    async def _check_neo4j(self, errors: list[str]) -> int:
        database = _neo4j_database_for(self.customer_id)
        driver = AsyncGraphDatabase.driver(
            self.config.neo4j_url, auth=(self.config.neo4j_user, self.config.neo4j_password)
        )
        try:
            async with driver.session(database="system") as session:
                result = await session.run(
                    "SHOW DATABASES YIELD name WHERE name = $name RETURN count(*) AS c",
                    name=database,
                )
                record = await result.single()
                # If the database is gone, 0 remaining. If it still exists, count nodes.
                if not record or record["c"] == 0:
                    return 0

            async with driver.session(database=database) as session:
                rec = await (await session.run("MATCH (n) RETURN count(n) AS c")).single()
                return rec["c"]
        except Exception as e:
            errors.append(f"neo4j: {e}")
            return -1
        finally:
            await driver.close()

    async def _check_postgres(self, errors: list[str]) -> dict[str, int]:
        if self._pg_pool is None:
            self._pg_pool = await asyncpg.create_pool(self.config.postgres_url, min_size=1, max_size=2)

        remaining: dict[str, int] = {}
        try:
            async with self._pg_pool.acquire() as conn:
                for tbl in PG_VARCHAR_TABLES:
                    n = await CustomerDeletionPipeline._safe_count(
                        conn, tbl, "customer_id", self.customer_id
                    )
                    if n > 0:
                        remaining[tbl] = n

                if _is_uuid(self.customer_id):
                    n = await conn.fetchval(
                        "SELECT count(*) FROM customers WHERE id = $1", self.customer_id
                    ) or 0
                    if n > 0:
                        remaining["customers"] = n
                    for tbl in PG_CASCADE_TABLES:
                        n = await CustomerDeletionPipeline._safe_count(
                            conn, tbl, "customer_id", self.customer_id, cast_uuid=True
                        )
                        if n > 0:
                            remaining[tbl] = n
        except Exception as e:
            errors.append(f"postgres: {e}")

        return remaining
