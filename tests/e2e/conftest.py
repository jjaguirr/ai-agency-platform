"""
Shared E2E fixtures — real component wiring, faked I/O boundaries.

The point of these tests is to prove the *wiring* works: safety pipeline
feeds the EA, the EA's output reaches the output scanner, persistence
fires, counters increment, tenant isolation holds. Individual components
are already unit-tested; here we exercise the chain.

I/O boundaries are faked, not mocked:
  - Redis → fakeredis.aioredis (real Redis semantics, in-memory)
  - Postgres → InMemoryConversationRepo / InMemoryDelegationRecorder
    (same method contracts as the asyncpg-backed originals)
  - LLM → ScriptedEA (deterministic, observable)

Everything else — SafetyPipeline, AuditLogger, ProactiveStateStore,
activity_counters, the route handlers — runs for real.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# JWT_SECRET must exist before src.api.auth imports.
os.environ.setdefault(
    "JWT_SECRET", "test-secret-do-not-use-in-prod-32-chars-min-xxxxxxxx"
)

import fakeredis.aioredis
import httpx

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry
from src.proactive.state import ProactiveStateStore
from src.safety.audit import AuditLogger
from src.safety.config import SafetyConfig
from src.safety.models import AuditEvent, AuditEventType
from src.safety.pipeline import SafetyPipeline


# ─── In-memory repository fakes ──────────────────────────────────────────
# Same method signatures as ConversationRepository / DelegationRecorder
# but store in process memory instead of Postgres. Tenant isolation is
# enforced the same way: every query filters by customer_id.

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InMemoryConversationRepo:
    def __init__(self) -> None:
        # {conversation_id: {id, customer_id, channel, created_at,
        #                    updated_at, summary, tags, quality_signals}}
        self._conversations: dict[str, dict[str, Any]] = {}
        # {conversation_id: [{role, content, timestamp, specialist_domain}]}
        self._messages: dict[str, list[dict[str, Any]]] = {}

    async def create_conversation(
        self, *, customer_id: str, conversation_id: Optional[str], channel: str,
    ) -> str:
        cid = conversation_id or str(uuid.uuid4())
        existing = self._conversations.get(cid)
        if existing is not None:
            # Idempotent re-POST for the same owner; ignore for a
            # different owner (never overwrite ownership).
            return cid
        now = _now_iso()
        self._conversations[cid] = {
            "id": cid,
            "customer_id": customer_id,
            "channel": channel,
            "created_at": now,
            "updated_at": now,
            "summary": None,
            "tags": [],
            "quality_signals": None,
        }
        self._messages[cid] = []
        return cid

    async def append_message(
        self, *, customer_id: str, conversation_id: str,
        role: str, content: str, specialist_domain: Optional[str] = None,
    ) -> None:
        conv = self._conversations.get(conversation_id)
        if conv is None or conv["customer_id"] != customer_id:
            return  # Tenant guard — silent drop, like the SQL subquery.
        self._messages[conversation_id].append({
            "role": role,
            "content": content,
            "timestamp": _now_iso(),
            "specialist_domain": specialist_domain,
        })
        conv["updated_at"] = _now_iso()

    async def get_messages(
        self, *, customer_id: str, conversation_id: str,
    ) -> Optional[list[dict[str, str]]]:
        conv = self._conversations.get(conversation_id)
        if conv is None or conv["customer_id"] != customer_id:
            return None
        return [
            {"role": m["role"], "content": m["content"], "timestamp": m["timestamp"]}
            for m in self._messages[conversation_id]
        ]

    async def list_conversations_enriched(
        self, *, customer_id: str, limit: int = 50, offset: int = 0,
        tags: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        rows = [
            c for c in self._conversations.values()
            if c["customer_id"] == customer_id
            and (not tags or set(tags) & set(c["tags"]))
        ]
        rows.sort(key=lambda c: c["updated_at"], reverse=True)
        out = []
        for c in rows[offset:offset + limit]:
            msgs = self._messages.get(c["id"], [])
            domains = sorted({
                m["specialist_domain"] for m in msgs
                if m.get("specialist_domain")
            })
            out.append({
                **c,
                "message_count": len(msgs),
                "specialist_domains": domains,
            })
        return out

    async def get_conversations_needing_summary(
        self, *, idle_threshold_minutes: int, limit: int,
    ) -> list[dict[str, Any]]:
        # E2E sweep test ignores idle threshold — just return anything
        # without a summary.
        return [
            {"id": c["id"], "customer_id": c["customer_id"]}
            for c in self._conversations.values()
            if c["summary"] is None
        ][:limit]

    async def set_summary(self, *, conversation_id: str, summary: str) -> None:
        if conversation_id in self._conversations:
            self._conversations[conversation_id]["summary"] = summary

    async def set_quality_signals(
        self, *, conversation_id: str, signals: dict,
    ) -> None:
        if conversation_id in self._conversations:
            self._conversations[conversation_id]["quality_signals"] = signals


class InMemoryDelegationRecorder:
    def __init__(self, repo: InMemoryConversationRepo) -> None:
        self._repo = repo
        # {record_id: {conversation_id, customer_id, specialist_domain,
        #              status, turns, confirmation_requested,
        #              confirmation_outcome, error_message}}
        self.records: dict[str, dict[str, Any]] = {}

    async def record_start(
        self, *, conversation_id: str, customer_id: str, specialist_domain: str,
    ) -> str:
        rid = str(uuid.uuid4())
        self.records[rid] = {
            "id": rid,
            "conversation_id": conversation_id,
            "customer_id": customer_id,
            "specialist_domain": specialist_domain,
            "status": "started",
            "turns": 0,
            "confirmation_requested": False,
            "confirmation_outcome": None,
            "error_message": None,
        }
        return rid

    async def record_end(
        self, *, record_id: str, status: str, turns: int,
        confirmation_requested: bool,
        confirmation_outcome: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        r = self.records.get(record_id)
        if r is None:
            return
        r.update({
            "status": status,
            "turns": turns,
            "confirmation_requested": confirmation_requested,
            "confirmation_outcome": confirmation_outcome,
            "error_message": error_message,
        })

    async def update_tags_from_delegations(
        self, *, customer_id: str, conversation_id: str,
    ) -> None:
        domains = sorted({
            r["specialist_domain"] for r in self.records.values()
            if r["conversation_id"] == conversation_id
            and r["customer_id"] == customer_id
        })
        tags = domains or ["general"]
        conv = self._repo._conversations.get(conversation_id)
        if conv and conv["customer_id"] == customer_id:
            conv["tags"] = tags

    async def get_delegation_statuses(
        self, *, conversation_id: str, customer_id: str,
    ) -> list[str]:
        return [
            r["status"] for r in self.records.values()
            if r["conversation_id"] == conversation_id
            and r["customer_id"] == customer_id
        ]


# ─── Scripted EA ─────────────────────────────────────────────────────────
# Stands in for ExecutiveAssistant at the registry boundary. Implements
# handle_customer_interaction and the attributes the conversations route
# reads (last_specialist_domain). Lets tests observe what reached the EA
# after the safety pipeline, and drive specialist-delegation /
# confirmation flows deterministically.

class ScriptedEA:
    def __init__(
        self,
        customer_id: str,
        *,
        audit: Optional[AuditLogger] = None,
        recorder: Optional[InMemoryDelegationRecorder] = None,
    ) -> None:
        self.customer_id = customer_id
        self.last_specialist_domain: Optional[str] = None
        self._audit = audit
        self._recorder = recorder
        # Observability for tests
        self.received: list[str] = []
        # Multi-turn state: {conversation_id: pending_action_dict}
        self._pending: dict[str, dict[str, Any]] = {}
        self._record_ids: dict[str, str] = {}

    async def handle_customer_interaction(
        self, *, message: str, channel, conversation_id: str = None,
    ) -> str:
        self.received.append(message)
        self.last_specialist_domain = None
        cid = conversation_id or "default"

        # Confirmation resumption — mirrors EA._delegate_to_specialist
        pending = self._pending.get(cid)
        if pending is not None:
            affirmative = message.strip().lower() in {
                "yes", "y", "confirm", "go ahead", "do it", "yes please",
            }
            record_id = self._record_ids.pop(cid, None)
            self._pending.pop(cid, None)
            self.last_specialist_domain = pending["domain"]
            if affirmative:
                await self._audit_confirm(
                    AuditEventType.HIGH_RISK_ACTION_CONFIRMED, pending,
                    outcome={"executed": True},
                )
                await self._record_end(
                    record_id, status="completed", turns=2,
                    confirmation_requested=True,
                    confirmation_outcome="confirmed",
                )
                return f"Done — {pending['action']} executed."
            else:
                await self._audit_confirm(
                    AuditEventType.HIGH_RISK_ACTION_DECLINED, pending,
                )
                await self._record_end(
                    record_id, status="cancelled", turns=2,
                    confirmation_requested=True,
                    confirmation_outcome="declined",
                )
                return "Understood — I've cancelled that."

        lower = message.lower()

        # High-risk action → NEEDS_CONFIRMATION
        if "cancel all" in lower:
            domain = "scheduling"
            pending = {"domain": domain, "action": "cancel all meetings"}
            self._pending[cid] = pending
            record_id = await self._record_start(cid, domain)
            self._record_ids[cid] = record_id
            await self._audit_confirm(
                AuditEventType.HIGH_RISK_ACTION_REQUESTED, pending,
            )
            self.last_specialist_domain = domain
            return (
                "This will cancel all meetings on your calendar. "
                "Are you sure? (yes/no)"
            )

        # Scheduling delegation — simple route
        if any(k in lower for k in ("schedule", "meeting", "calendar")):
            domain = "scheduling"
            record_id = await self._record_start(cid, domain)
            await self._record_end(
                record_id, status="completed", turns=1,
                confirmation_requested=False,
            )
            self.last_specialist_domain = domain
            return "I've scheduled that meeting for you. Anything else?"

        # General chat
        return "Happy to help with that."

    async def _record_start(self, conversation_id: str, domain: str) -> Optional[str]:
        if self._recorder is None:
            return None
        return await self._recorder.record_start(
            conversation_id=conversation_id,
            customer_id=self.customer_id,
            specialist_domain=domain,
        )

    async def _record_end(self, record_id: Optional[str], **kw) -> None:
        if self._recorder is None or record_id is None:
            return
        await self._recorder.record_end(record_id=record_id, **kw)

    async def _audit_confirm(
        self, event_type: AuditEventType, pending: dict, *, outcome=None,
    ) -> None:
        if self._audit is None:
            return
        details = {"domain": pending["domain"], "action": pending["action"]}
        if outcome is not None:
            details["outcome"] = outcome
        await self._audit.log(self.customer_id, AuditEvent(
            timestamp=_now_iso(),
            event_type=event_type,
            correlation_id="-",
            details=details,
        ))


# ─── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis()


@pytest.fixture
def safety_config():
    return SafetyConfig()


@pytest.fixture
def audit_logger(fake_redis, safety_config):
    return AuditLogger(fake_redis, max_events=safety_config.audit_max_events)


@pytest.fixture
def safety_pipeline(safety_config, audit_logger):
    return SafetyPipeline(safety_config, audit_logger)


@pytest.fixture
def conversation_repo():
    return InMemoryConversationRepo()


@pytest.fixture
def delegation_recorder(conversation_repo):
    return InMemoryDelegationRecorder(conversation_repo)


@pytest.fixture
def proactive_store(fake_redis):
    return ProactiveStateStore(fake_redis)


@pytest.fixture
def ea_instances():
    """Test-side handle to the ScriptedEA objects the registry built."""
    return {}


@pytest.fixture
def ea_registry(ea_instances, audit_logger, delegation_recorder):
    def factory(customer_id: str) -> ScriptedEA:
        ea = ScriptedEA(
            customer_id,
            audit=audit_logger,
            recorder=delegation_recorder,
        )
        ea_instances[customer_id] = ea
        return ea
    return EARegistry(factory=factory, max_size=32)


@pytest.fixture
def app(
    ea_registry, fake_redis, conversation_repo, proactive_store, safety_pipeline,
):
    return create_app(
        ea_registry=ea_registry,
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(),
        redis_client=fake_redis,
        conversation_repo=conversation_repo,
        proactive_state_store=proactive_store,
        safety_pipeline=safety_pipeline,
    )


@pytest.fixture
async def client(app):
    """httpx AsyncClient over ASGITransport — shares the test event loop
    with fakeredis so awaits line up."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def auth_for(customer_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(customer_id)}"}


@pytest.fixture
def auth_a():
    return auth_for("customer_a")


@pytest.fixture
def auth_b():
    return auth_for("customer_b")
