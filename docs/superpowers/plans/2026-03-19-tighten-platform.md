# Tighten the Platform — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every open seam from the Python consolidation — dead JS, finance wiring, CI, correlation IDs, conversation history, webhook parity.

**Architecture:** Six independent workstreams. Dead-code removal and CI fix are pure housekeeping. Finance wiring, correlation IDs, history endpoint, and webhook parity each add a small feature with TDD. Commits are stacked via jj; each test commit precedes its implementation commit.

**Tech Stack:** FastAPI, pytest, uv, jj. No new dependencies.

**Working directory:** `/Users/jose/Documents/07 WORK/01-PROMETHEUS/tasks-ai-agency-platform/08/model_b`

**Baseline:** 442 tests passing, 41 skipped (verified 2026-03-19).

---

## Task 1: Remove dead JavaScript

**Files:**
- Delete: `src/api/server.js`
- Delete: `src/api/auth.js`
- Delete: `src/api/customer-provisioning-api.js`
- Delete: `src/api/cross-system-bridge.js`
- Delete: `src/api/websocket-poc.js`
- Delete: `src/api/tests/api-validation-suite.js`
- Delete: `src/api/tests/` (directory, now empty)

- [ ] **Step 1.1: Delete the files**

```bash
cd "/Users/jose/Documents/07 WORK/01-PROMETHEUS/tasks-ai-agency-platform/08/model_b"
rm src/api/server.js src/api/auth.js src/api/customer-provisioning-api.js \
   src/api/cross-system-bridge.js src/api/websocket-poc.js \
   src/api/tests/api-validation-suite.js
rmdir src/api/tests
```

- [ ] **Step 1.2: Verify no stray references**

```bash
grep -r "server.js\|auth.js\|customer-provisioning-api\|cross-system-bridge\|websocket-poc\|api-validation-suite" \
  --include="*.py" --include="*.yml" --include="*.yaml" --include="*.toml" \
  --include="*.json" --include="*.md" . 2>/dev/null | grep -v ".git\|node_modules\|.venv"
```

Expected: empty (or only this plan doc).

- [ ] **Step 1.3: Verify no JS left in src/api**

```bash
find src/api -name "*.js"
```

Expected: empty.

- [ ] **Step 1.4: Run tests — confirm nothing broke**

```bash
uv run pytest tests/unit/ -q --timeout=30
```

Expected: 442 passed, 41 skipped.

- [ ] **Step 1.5: Commit**

```bash
jj new -m "chore(api): remove Phase 1 JavaScript artefacts

server.js, auth.js, customer-provisioning-api.js, cross-system-bridge.js,
websocket-poc.js and api-validation-suite.js were replaced by the
FastAPI layer during the Python consolidation. The Express server has
not served traffic since app.py landed."
jj squash --from @- --into @
```

---

## Task 2: Finance specialist — tests

**Files:**
- Create: `tests/unit/test_ea_specialist_registration.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/unit/test_ea_specialist_registration.py`:

```python
"""
Specialist registration at EA init.

The EA's __init__ must register both social_media and finance. The
finance import is guarded — if finance.py fails to import (missing
optional dep, syntax error), the EA degrades to having social_media
only. It does NOT crash.

Routing overlap: finance and social media share vocabulary ("Facebook
ads budget"). The DelegationRegistry.route() must produce ONE match or
None — never crash, never return two.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def ea():
    """EA with infra mocked away. Same pattern as test_ea_delegation.py."""
    with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
         patch("src.agents.executive_assistant.WorkflowCreator"), \
         patch("src.agents.executive_assistant.ChatOpenAI"):
        from src.agents.executive_assistant import ExecutiveAssistant, BusinessContext
        mem = MockMem.return_value
        mem.get_business_context = AsyncMock(return_value=BusinessContext())
        mem.search_business_knowledge = AsyncMock(return_value=[])
        mem.store_conversation_context = AsyncMock()
        mem.get_conversation_context = AsyncMock(return_value={})
        yield ExecutiveAssistant(customer_id="cust_reg")


@pytest.fixture
def retail_ctx():
    from src.agents.executive_assistant import BusinessContext
    return BusinessContext(
        business_name="Sparkle & Shine",
        industry="jewelry",
        current_tools=["Instagram", "Facebook", "QuickBooks"],
        pain_points=["manual expense tracking", "social media"],
    )


class TestSpecialistRegistration:
    def test_social_media_registered(self, ea):
        assert ea.delegation_registry.get("social_media") is not None

    def test_finance_registered(self, ea):
        assert ea.delegation_registry.get("finance") is not None

    def test_finance_import_failure_does_not_crash_ea(self):
        """
        If finance.py can't import (missing dep, syntax error),
        EA init still succeeds. Finance just isn't registered.
        """
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory"), \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"), \
             patch("src.agents.executive_assistant._FINANCE_AVAILABLE", False):
            from src.agents.executive_assistant import ExecutiveAssistant
            ea = ExecutiveAssistant(customer_id="cust_no_finance")
            # EA built, social media still there, finance absent
            assert ea.delegation_registry.get("social_media") is not None
            assert ea.delegation_registry.get("finance") is None


class TestRoutingWithFinance:
    def test_invoice_routes_to_finance(self, ea, retail_ctx):
        match = ea.delegation_registry.route(
            "Track this invoice: $2,400 from Acme Corp", retail_ctx,
        )
        assert match is not None
        assert match.specialist.domain == "finance"

    def test_engagement_still_routes_to_social(self, ea, retail_ctx):
        """
        Adding finance must not break social media routing.
        "Instagram engagement" has no finance signals.
        """
        match = ea.delegation_registry.route(
            "how's my Instagram engagement this week?", retail_ctx,
        )
        assert match is not None
        assert match.specialist.domain == "social_media"

    def test_facebook_roi_overlap_is_coherent(self, ea, retail_ctx):
        """
        "What's my ROI on the Facebook campaign?" is the overlap case.
        Facebook → social signal. ROI → finance signal. "What's my" is
        a strategic-sounding query.

        Acceptable outcomes: routes to one specialist, or returns None
        (strategic — EA keeps it). Not acceptable: crash, exception,
        or undefined behaviour.
        """
        match = ea.delegation_registry.route(
            "What's my ROI on the Facebook campaign?", retail_ctx,
        )
        # No crash. If routed, it's to exactly one specialist.
        if match is not None:
            assert match.specialist.domain in ("finance", "social_media")
            assert 0.0 <= match.assessment.confidence <= 1.0


class TestFinanceDelegationPipeline:
    @pytest.mark.asyncio
    async def test_invoice_message_reaches_finance_via_delegate_node(self, retail_ctx):
        """
        Full delegation pipeline: message → delegation_registry.route →
        specialist.execute_task → EA weaves response. Mocked infra, no
        live services.
        """
        from src.agents.base.specialist import (
            DelegationRegistry, SpecialistResult, SpecialistStatus,
        )
        with patch("src.agents.executive_assistant.ExecutiveAssistantMemory") as MockMem, \
             patch("src.agents.executive_assistant.WorkflowCreator"), \
             patch("src.agents.executive_assistant.ChatOpenAI"):
            from src.agents.executive_assistant import (
                ExecutiveAssistant, ConversationState, ConversationIntent,
            )
            from langchain_core.messages import HumanMessage, AIMessage

            mem = MockMem.return_value
            mem.get_business_context = AsyncMock(return_value=retail_ctx)
            mem.search_business_knowledge = AsyncMock(return_value=[])

            ea = ExecutiveAssistant(customer_id="cust_pipeline")
            ea.llm = None

            # Spy on finance specialist
            finance = ea.delegation_registry.get("finance")
            assert finance is not None, "finance not registered"
            executed = []
            orig_exec = finance.execute_task
            async def spy_exec(task):
                executed.append(task)
                return await orig_exec(task)
            finance.execute_task = spy_exec

            state = ConversationState(
                messages=[HumanMessage(
                    content="Track this invoice: $2,400 from Acme Corp")],
                customer_id="cust_pipeline",
                conversation_id="conv_1",
                business_context=retail_ctx,
                current_intent=ConversationIntent.TASK_DELEGATION,
            )

            out = await ea._delegate_to_specialist(state)

            # Finance specialist was invoked
            assert len(executed) == 1
            assert "$2,400" in executed[0].description or \
                   "2400" in executed[0].description
            # EA produced a response
            assert isinstance(out.messages[-1], AIMessage)
            assert len(out.messages[-1].content) > 0
```

- [ ] **Step 2.2: Run — verify tests fail**

```bash
uv run pytest tests/unit/test_ea_specialist_registration.py -v
```

Expected: `test_finance_registered` FAILS with `assert None is not None`.
`_FINANCE_AVAILABLE` patch target will also fail (AttributeError — name
doesn't exist yet).

- [ ] **Step 2.3: Commit the failing tests**

```bash
jj new -m "test(ea): specialist registration + finance routing

Tests first: both specialists registered at init, finance import
failure is graceful, invoice text routes to finance, Facebook-ROI
overlap doesn't crash."
jj squash --from @- --into @
```

---

## Task 3: Finance specialist — implementation

**Files:**
- Modify: `src/agents/executive_assistant.py:59-60, 598-600`

- [ ] **Step 3.1: Add guarded import**

In `src/agents/executive_assistant.py`, after line 59
(`from .specialists.social_media import SocialMediaSpecialist`), insert:

```python
# Finance is guarded — a missing optional dependency or import failure
# degrades the EA to generalist mode for finance-domain messages. It
# does NOT crash EA init.
try:
    from .specialists.finance import FinanceSpecialist
    _FINANCE_AVAILABLE = True
except Exception as _e:
    logger.warning(f"Finance specialist unavailable: {_e}")
    FinanceSpecialist = None  # type: ignore[assignment]
    _FINANCE_AVAILABLE = False
```

- [ ] **Step 3.2: Register in `__init__`**

At line 599 (after `self.delegation_registry.register(SocialMediaSpecialist())`):

```python
        if _FINANCE_AVAILABLE:
            self.delegation_registry.register(FinanceSpecialist())
```

- [ ] **Step 3.3: Run tests**

```bash
uv run pytest tests/unit/test_ea_specialist_registration.py -v
```

Expected: all PASS.

- [ ] **Step 3.4: Run full suite — verify no regressions**

```bash
uv run pytest tests/unit/ -q --timeout=30
```

Expected: ≥442 passed (new tests add to count).

- [ ] **Step 3.5: Commit**

```bash
jj new -m "feat(ea): register FinanceSpecialist with guarded import

Mirrors SocialMediaSpecialist registration. Import is guarded — if
finance.py fails to import, the EA logs a warning and continues with
social_media only."
jj squash --from @- --into @
```

---

## Task 4: Fix docker-compose.ci.yml

**Files:**
- Modify: `docker-compose.ci.yml`

- [ ] **Step 4.1: Remove phantom services**

Delete the `memory-monitor` block (lines 104-140) and `security-api`
block (lines 142-173) from `docker-compose.ci.yml`. Also trim the
comment block at the end that references them.

Resulting file should contain only: `postgres`, `redis`, `qdrant`, the
`networks` block.

- [ ] **Step 4.2: Validate YAML**

```bash
docker compose -f docker-compose.ci.yml config --quiet
```

Expected: silent exit 0.

- [ ] **Step 4.3: Commit**

```bash
jj new -m "fix(ci): remove phantom Docker services from compose

memory-monitor (./src/memory/Dockerfile.monitor) and security-api
(./src/security/Dockerfile.llamaguard-api) reference Dockerfiles that
don't exist. Compose fails to build them, breaking the depends_on
chain and stalling the CI pipeline at the Qdrant health gate.

Neither is needed for unit or integration tests."
jj squash --from @- --into @
```

---

## Task 5: Rewrite CI workflow

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 5.1: Full rewrite**

Replace `.github/workflows/ci.yml` entirely with:

```yaml
name: CI

on:
  push:
    branches: ['**']
  pull_request:
    branches: ['main']

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          version: "latest"

      - name: Set up Python
        run: uv python install 3.12

      - name: Install dependencies
        run: uv sync

      - name: Start Docker services
        run: |
          docker compose -f docker-compose.ci.yml up -d
          echo "Waiting for Postgres..."
          timeout 60 bash -c 'until docker compose -f docker-compose.ci.yml exec -T postgres pg_isready -U testuser -d testdb; do sleep 2; done'
          echo "Waiting for Redis..."
          timeout 30 bash -c 'until docker compose -f docker-compose.ci.yml exec -T redis redis-cli ping | grep -q PONG; do sleep 2; done'
          echo "Waiting for Qdrant..."
          timeout 60 bash -c 'until curl -sf http://localhost:6333/readyz > /dev/null; do sleep 2; done'

      - name: Run unit tests
        run: uv run pytest tests/unit/ --tb=short -q

      - name: Security check
        continue-on-error: true
        run: |
          if grep -r "password\|secret\|api_key" \
               --include="*.yml" --include="*.yaml" --include="*.json" \
               --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git \
               . | grep -v "#\|//"; then
            echo "::warning::Potential secrets found in config files"
          else
            echo "No obvious secrets in config files"
          fi

      - name: Cleanup
        if: always()
        run: docker compose -f docker-compose.ci.yml down -v
```

- [ ] **Step 5.2: Validate locally**

```bash
uv run pytest tests/unit/ --tb=short -q
```

Expected: all pass (this is the exact command CI will run).

- [ ] **Step 5.3: Commit**

```bash
jj new -m "fix(ci): rewrite workflow — uv, real test suite, working compose

Before: pip install inline, ran test_ea_basic.py (references Phase 1
file layout), checked for schema.sql (irrelevant), never ran pytest.
CI has been silently broken for months.

After: setup-uv, uv sync from lock, pytest tests/unit/. Build fails on
any test failure. Services come from the trimmed docker-compose.ci.yml."
jj squash --from @- --into @
```

---

## Task 6: Correlation ID — tests

**Files:**
- Create: `tests/unit/api/test_correlation.py`

- [ ] **Step 6.1: Write the failing tests**

Create `tests/unit/api/test_correlation.py`:

```python
"""
Request correlation — X-Request-ID header + log injection.

Every HTTP response carries X-Request-ID. Client-provided IDs are
echoed; missing IDs are UUID4-generated. The ID is available to
downstream code via a contextvar and appears in every log record.
"""
import logging
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _app(**overrides):
    return create_app(
        ea_registry=overrides.get("ea_registry")
            or EARegistry(factory=lambda cid: MagicMock(
                handle_customer_interaction=AsyncMock(return_value="ok"))),
        orchestrator=overrides.get("orchestrator") or AsyncMock(),
        whatsapp_manager=overrides.get("whatsapp_manager") or MagicMock(
            get_channel=AsyncMock(return_value=None)),
        redis_client=overrides.get("redis_client") or AsyncMock(
            ping=AsyncMock(return_value=True)),
    )


@pytest.fixture
def client():
    return TestClient(_app())


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {create_token('cust_corr')}"}


class TestHeaderPresence:
    def test_healthz(self, client):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_readyz(self, client):
        r = client.get("/readyz")
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_conversations_200(self, client, auth_headers):
        r = client.post(
            "/v1/conversations/message",
            json={"message": "hi", "channel": "chat"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_provisioning_201(self):
        orch = AsyncMock()
        async def _prov(customer_id, tier="professional", **_):
            env = MagicMock()
            env.customer_id = customer_id
            env.tier = tier
            return env
        orch.provision_customer_environment = AsyncMock(side_effect=_prov)
        client = TestClient(_app(orchestrator=orch))
        r = client.post("/v1/customers/provision", json={"tier": "basic"})
        assert r.status_code == 201
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_webhook_404(self, client):
        r = client.post("/webhook/whatsapp/ghost_customer", content=b"x")
        assert r.status_code == 404
        assert "x-request-id" in (k.lower() for k in r.headers)


class TestErrorPaths:
    def test_401(self, client):
        r = client.post("/v1/conversations/message",
                        json={"message": "hi", "channel": "chat"})
        assert r.status_code == 401
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_422(self, client, auth_headers):
        r = client.post("/v1/conversations/message",
                        json={"channel": "chat"},
                        headers=auth_headers)
        assert r.status_code == 422
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_404_unknown_route(self, client):
        r = client.get("/v1/definitely-not-a-route")
        assert r.status_code == 404
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_500_unhandled(self, auth_headers):
        def bad_factory(cid):
            raise RuntimeError("boom")
        app = _app(ea_registry=EARegistry(factory=bad_factory))
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post("/v1/conversations/message",
                        json={"message": "hi", "channel": "chat"},
                        headers=auth_headers)
        assert r.status_code in (500, 503)
        assert "x-request-id" in (k.lower() for k in r.headers)

    def test_503_service_unavailable(self, auth_headers):
        broken_ea = MagicMock()
        broken_ea.handle_customer_interaction = AsyncMock(
            side_effect=ConnectionError("redis gone"))
        app = _app(ea_registry=EARegistry(factory=lambda cid: broken_ea))
        client = TestClient(app)
        r = client.post("/v1/conversations/message",
                        json={"message": "hi", "channel": "chat"},
                        headers=auth_headers)
        assert r.status_code == 503
        assert "x-request-id" in (k.lower() for k in r.headers)


class TestIdGeneration:
    def test_client_provided_echoed_unchanged(self, client):
        r = client.get("/healthz", headers={"X-Request-ID": "my-trace-abc"})
        assert r.headers["x-request-id"] == "my-trace-abc"

    def test_generated_is_valid_uuid4(self, client):
        r = client.get("/healthz")
        cid = r.headers["x-request-id"]
        parsed = uuid.UUID(cid)
        assert parsed.version == 4

    def test_two_requests_get_distinct_ids(self, client):
        r1 = client.get("/healthz")
        r2 = client.get("/healthz")
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


class TestLogInjection:
    def test_log_records_carry_correlation_id(self, auth_headers, caplog):
        """
        Log lines emitted during request processing have correlation_id
        attached. The route handler logs on error — trigger an error,
        capture the log record, check the attribute.
        """
        broken_ea = MagicMock()
        broken_ea.handle_customer_interaction = AsyncMock(
            side_effect=ConnectionError("redis gone"))
        app = _app(ea_registry=EARegistry(factory=lambda cid: broken_ea))
        client = TestClient(app)

        with caplog.at_level(logging.ERROR, logger="src.api"):
            r = client.post(
                "/v1/conversations/message",
                json={"message": "hi", "channel": "chat"},
                headers={**auth_headers, "X-Request-ID": "trace-xyz"},
            )

        assert r.status_code == 503
        # At least one record from the conversations route
        route_records = [rec for rec in caplog.records
                         if "conversations" in rec.name or "src.api" in rec.name]
        assert route_records, f"no route log records captured; got {caplog.records}"
        assert any(getattr(rec, "correlation_id", None) == "trace-xyz"
                   for rec in route_records), \
            f"no record with correlation_id=trace-xyz; records={[(r.name, getattr(r, 'correlation_id', None)) for r in route_records]}"
```

- [ ] **Step 6.2: Run — verify tests fail**

```bash
uv run pytest tests/unit/api/test_correlation.py -v
```

Expected: all header tests FAIL (no `x-request-id` in response).

- [ ] **Step 6.3: Commit**

```bash
jj new -m "test(api): request correlation ID

Every response (success, 401, 404, 422, 500, 503) carries X-Request-ID.
Client-provided IDs echo; generated IDs are UUID4. Log records during
request processing carry correlation_id."
jj squash --from @- --into @
```

---

## Task 7: Correlation ID — implementation

**Files:**
- Create: `src/api/correlation.py`
- Modify: `src/api/app.py`
- Modify: `src/utils/logging.py`

- [ ] **Step 7.1: Create the middleware module**

Create `src/api/correlation.py`:

```python
"""
Request correlation — X-Request-ID + log injection.

Pure ASGI middleware (not Starlette's BaseHTTPMiddleware) so the header
is injected at the wire level, catching every response including those
generated by exception handlers.

The correlation ID is exposed via a ContextVar so downstream code can
read it without threading it through signatures. A logging.Filter pulls
from the contextvar and attaches correlation_id to every LogRecord.
"""
import logging
import uuid
from contextvars import ContextVar
from typing import Optional

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

_HEADER_NAME = b"x-request-id"


def get_correlation_id() -> str:
    """Current request's correlation ID. '-' outside request context."""
    return _correlation_id.get()


class CorrelationIdFilter(logging.Filter):
    """Injects correlation_id onto every log record.

    Attach to the root logger once at app startup. Filters run before
    formatters, so any handler/formatter that references
    %(correlation_id)s will have the attribute available.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()
        return True


class CorrelationIdMiddleware:
    """Read or generate X-Request-ID; echo on every response.

    Implemented as raw ASGI so it wraps the entire response pipeline —
    including Starlette's exception-handler output. BaseHTTPMiddleware
    sits inside that pipeline and can miss handler-generated responses.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Find client-provided header. ASGI headers are list[tuple[bytes, bytes]].
        cid: Optional[str] = None
        for name, value in scope.get("headers", []):
            if name.lower() == _HEADER_NAME:
                cid = value.decode("latin-1")
                break
        if not cid:
            cid = str(uuid.uuid4())

        token = _correlation_id.set(cid)
        cid_bytes = cid.encode("latin-1")

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((_HEADER_NAME, cid_bytes))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _correlation_id.reset(token)
```

- [ ] **Step 7.2: Wire into app.py**

In `src/api/app.py`, add import after the existing imports:

```python
from .correlation import CorrelationIdFilter, CorrelationIdMiddleware
```

In `create_app()`, after `app = FastAPI(...)`:

```python
    # Request correlation — header + log injection. Must be added
    # LAST so it wraps the entire response pipeline (Starlette
    # middleware runs outside-in; last-added is outermost).
    app.add_middleware(CorrelationIdMiddleware)

    # Attach the filter to the root logger once. Idempotent — filter
    # instances are deduplicated by identity, so repeated create_app()
    # calls in tests don't stack filters if we check.
    _root = logging.getLogger()
    if not any(isinstance(f, CorrelationIdFilter) for f in _root.filters):
        _root.addFilter(CorrelationIdFilter())
```

- [ ] **Step 7.3: Update JSONFormatter**

In `src/utils/logging.py`, inside `JSONFormatter.format()`, after the
`customer_id` check (line 21):

```python
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
```

- [ ] **Step 7.4: Run correlation tests**

```bash
uv run pytest tests/unit/api/test_correlation.py -v
```

Expected: all PASS.

- [ ] **Step 7.5: Run full suite**

```bash
uv run pytest tests/unit/ -q --timeout=30
```

Expected: all pass, no regressions.

- [ ] **Step 7.6: Commit**

```bash
jj new -m "feat(api): correlation-ID middleware + log filter

Pure-ASGI middleware reads X-Request-ID or generates UUID4, sets a
ContextVar, echoes the header on every response including error-handler
output. A logging.Filter attached to the root logger injects
correlation_id onto every LogRecord so %(correlation_id)s works without
restructuring existing log calls."
jj squash --from @- --into @
```

---

## Task 8: Conversation history — tests

**Files:**
- Create: `tests/unit/api/test_conversation_history.py`

- [ ] **Step 8.1: Write the failing tests**

Create `tests/unit/api/test_conversation_history.py`:

```python
"""
GET /v1/conversations/{conversation_id}/messages

Reads message history from the EA's in-memory store via a public
accessor — the route does NOT reach into ConversationState directly.

Tenant isolation: customer A's token cannot read customer B's
conversations. Returns 404 (not 403 — don't confirm the conversation
exists for another tenant).

Known limitation (documented, not solved): history is lost when the
EA is evicted from the LRU cache.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth import create_token
from src.api.ea_registry import EARegistry


def _ea_with_history(history_dict):
    """Mock EA that exposes get_conversation_history."""
    ea = MagicMock()
    ea.handle_customer_interaction = AsyncMock(return_value="ok")
    ea.get_conversation_history = MagicMock(
        side_effect=lambda cid: history_dict.get(cid))
    return ea


def _app(factory):
    return create_app(
        ea_registry=EARegistry(factory=factory),
        orchestrator=AsyncMock(),
        whatsapp_manager=MagicMock(get_channel=AsyncMock(return_value=None)),
        redis_client=AsyncMock(),
    )


def _headers(customer_id):
    return {"Authorization": f"Bearer {create_token(customer_id)}"}


class TestAuth:
    def test_no_token_401(self):
        app = _app(lambda cid: _ea_with_history({}))
        client = TestClient(app)
        r = client.get("/v1/conversations/conv_1/messages")
        assert r.status_code == 401


class TestNotFound:
    def test_unknown_conversation_404(self):
        ea = _ea_with_history({})  # no history for anything
        app = _app(lambda cid: ea)
        client = TestClient(app)
        # Prime the registry by hitting another endpoint first
        client.post("/v1/conversations/message",
                    json={"message": "hi", "channel": "chat"},
                    headers=_headers("cust_a"))

        r = client.get("/v1/conversations/conv_unknown/messages",
                       headers=_headers("cust_a"))
        assert r.status_code == 404

    def test_ea_not_cached_404(self):
        """
        EA was never instantiated (or evicted) — GET returns 404.
        The route must NOT instantiate the EA just to answer a GET.
        """
        built = []
        def factory(cid):
            built.append(cid)
            return _ea_with_history({})

        app = _app(factory)
        client = TestClient(app)
        r = client.get("/v1/conversations/conv_1/messages",
                       headers=_headers("cust_never_seen"))
        assert r.status_code == 404
        # Factory was NOT called — no EA built for a history GET.
        assert built == []


class TestTenantIsolation:
    def test_other_customers_conversation_404(self):
        """
        cust_a POSTs to conv_1. cust_b's token requests conv_1 → 404.
        Not 403 — don't confirm the conversation exists.
        """
        ea_a = _ea_with_history({
            "conv_1": [
                {"role": "user", "content": "hello",
                 "timestamp": "2026-03-19T10:00:00+00:00"},
            ],
        })
        built_for = {}
        def factory(cid):
            if cid == "cust_a":
                built_for["cust_a"] = ea_a
                return ea_a
            ea_b = _ea_with_history({})
            built_for[cid] = ea_b
            return ea_b

        app = _app(factory)
        client = TestClient(app)
        # Prime cust_a's EA
        client.post("/v1/conversations/message",
                    json={"message": "hello", "channel": "chat",
                          "conversation_id": "conv_1"},
                    headers=_headers("cust_a"))

        # cust_b asks for conv_1
        r = client.get("/v1/conversations/conv_1/messages",
                       headers=_headers("cust_b"))
        assert r.status_code == 404


class TestHappyPath:
    def test_empty_conversation_200(self):
        """
        Conversation exists (EA knows the key) but has zero messages.
        Return 200 with empty list, not 404.
        """
        ea = _ea_with_history({"conv_empty": []})
        app = _app(lambda cid: ea)
        client = TestClient(app)
        client.post("/v1/conversations/message",
                    json={"message": "x", "channel": "chat"},
                    headers=_headers("cust_e"))

        r = client.get("/v1/conversations/conv_empty/messages",
                       headers=_headers("cust_e"))
        assert r.status_code == 200
        body = r.json()
        assert body["conversation_id"] == "conv_empty"
        assert body["customer_id"] == "cust_e"
        assert body["messages"] == []

    def test_messages_chronological(self):
        ea = _ea_with_history({
            "conv_1": [
                {"role": "user", "content": "first",
                 "timestamp": "2026-03-19T10:00:00+00:00"},
                {"role": "assistant", "content": "reply one",
                 "timestamp": "2026-03-19T10:00:01+00:00"},
                {"role": "user", "content": "second",
                 "timestamp": "2026-03-19T10:05:00+00:00"},
            ],
        })
        app = _app(lambda cid: ea)
        client = TestClient(app)
        client.post("/v1/conversations/message",
                    json={"message": "x", "channel": "chat"},
                    headers=_headers("cust_h"))

        r = client.get("/v1/conversations/conv_1/messages",
                       headers=_headers("cust_h"))
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert [m["content"] for m in msgs] == ["first", "reply one", "second"]
        timestamps = [m["timestamp"] for m in msgs]
        assert timestamps == sorted(timestamps)

    def test_response_schema(self):
        ea = _ea_with_history({
            "conv_s": [
                {"role": "user", "content": "hello",
                 "timestamp": "2026-03-19T10:00:00+00:00"},
            ],
        })
        app = _app(lambda cid: ea)
        client = TestClient(app)
        client.post("/v1/conversations/message",
                    json={"message": "x", "channel": "whatsapp"},
                    headers=_headers("cust_s"))

        r = client.get("/v1/conversations/conv_s/messages",
                       headers=_headers("cust_s"))
        body = r.json()
        assert set(body.keys()) >= {"conversation_id", "customer_id", "messages"}
        assert set(body["messages"][0].keys()) == {"role", "content", "timestamp"}


class TestRoundtrip:
    @pytest.fixture
    def real_history_ea(self):
        """
        A mock EA that actually accumulates history when
        handle_customer_interaction is called. Closest thing
        to a real EA without building one.
        """
        history = {}

        async def _handle(*, message, channel, conversation_id):
            if conversation_id not in history:
                history[conversation_id] = []
            history[conversation_id].append({
                "role": "user", "content": message,
                "timestamp": "2026-03-19T10:00:00+00:00",
            })
            reply = f"EA reply to {message!r}"
            history[conversation_id].append({
                "role": "assistant", "content": reply,
                "timestamp": "2026-03-19T10:00:01+00:00",
            })
            return reply

        ea = MagicMock()
        ea.handle_customer_interaction = _handle
        ea.get_conversation_history = lambda cid: history.get(cid)
        return ea

    def test_post_then_get_sees_both_messages(self, real_history_ea):
        app = _app(lambda cid: real_history_ea)
        client = TestClient(app)

        post_r = client.post(
            "/v1/conversations/message",
            json={"message": "hello", "channel": "chat",
                  "conversation_id": "conv_rt"},
            headers=_headers("cust_rt"),
        )
        assert post_r.status_code == 200

        get_r = client.get("/v1/conversations/conv_rt/messages",
                           headers=_headers("cust_rt"))
        assert get_r.status_code == 200
        msgs = get_r.json()["messages"]
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"
        assert msgs[1]["role"] == "assistant"
```

- [ ] **Step 8.2: Run — verify tests fail**

```bash
uv run pytest tests/unit/api/test_conversation_history.py -v
```

Expected: 404 on GET (route doesn't exist).

- [ ] **Step 8.3: Commit**

```bash
jj new -m "test(api): GET /v1/conversations/{id}/messages

Auth required, tenant-isolated (404 for wrong customer), unknown
conversation → 404, empty conversation → 200 with empty list,
chronological ordering, roundtrip POST→GET."
jj squash --from @- --into @
```

---

## Task 9: Conversation history — implementation

**Files:**
- Modify: `src/agents/executive_assistant.py:590-600, 1473-1566`
- Modify: `src/api/schemas.py`
- Modify: `src/api/errors.py`
- Modify: `src/api/ea_registry.py`
- Modify: `src/api/routes/conversations.py`

- [ ] **Step 9.1: Add NotFoundError**

In `src/api/errors.py`, after `BadRequestError`:

```python
class NotFoundError(APIError):
    def __init__(self, detail: str):
        super().__init__(status_code=404, error_type="not_found", detail=detail)
```

- [ ] **Step 9.2: Add EARegistry.peek()**

In `src/api/ea_registry.py`, after `get()`:

```python
    def peek(self, customer_id: str) -> Optional[_EALike]:
        """Non-creating lookup. Returns None if the EA isn't cached.

        Use this for read-only endpoints (history GET) where we must
        NOT instantiate an EA — building one opens Redis + mem0 +
        LangGraph just to say "not found."
        """
        return self._instances.get(customer_id)
```

Update `_EALike` protocol to include the new method:

```python
class _EALike(Protocol):
    customer_id: str
    async def handle_customer_interaction(self, *, message: str, **kw) -> str: ...
    def get_conversation_history(self, conversation_id: str) -> Optional[list]: ...
```

- [ ] **Step 9.3: Add history to EA**

In `src/agents/executive_assistant.py`:

After imports (near line 12), add `timezone` to the datetime import:

```python
from datetime import datetime, timezone
```

In `ExecutiveAssistant.__init__` (around line 598, before
`self.delegation_registry = ...`):

```python
        # In-memory conversation history, keyed by conversation_id.
        # Lost on EA eviction from the registry's LRU cache — acceptable
        # for now; persistent storage is a future concern.
        self._history: Dict[str, List[Dict[str, Any]]] = {}
```

Add public accessor (after `__init__`, around line 625, before
`_create_conversation_graph`):

```python
    def get_conversation_history(
        self, conversation_id: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """Return chronological [{role, content, timestamp}, ...] or None.

        None means the conversation doesn't exist in this EA's cache
        (never seen it, or EA was recycled). Empty list means the
        conversation is known but has no messages yet.
        """
        return self._history.get(conversation_id)
```

In `handle_customer_interaction`, after `conversation_id` is resolved
(after line 1483) and before the try block:

```python
        # Record user message to history before processing — even if the
        # graph fails we have a record that the customer asked something.
        if conversation_id not in self._history:
            self._history[conversation_id] = []
        now = datetime.now(timezone.utc).isoformat()
        self._history[conversation_id].append({
            "role": "user",
            "content": message,
            "timestamp": now,
        })
```

Before `return response` (line 1561):

```python
            self._history[conversation_id].append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
```

And in the `except Exception` branch (line 1563), before returning the
apology string, also record it:

```python
            fallback = ("I apologize, but I encountered an issue. "
                        "Let me get back to you in just a moment.")
            self._history[conversation_id].append({
                "role": "assistant",
                "content": fallback,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return fallback
```

- [ ] **Step 9.4: Add schemas**

In `src/api/schemas.py`, at the end:

```python
class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    customer_id: str
    channel: Optional[Channel] = None
    messages: list[HistoryMessage]
```

- [ ] **Step 9.5: Add the GET route**

In `src/api/routes/conversations.py`, add `NotFoundError` to the errors
import and `ConversationHistoryResponse` to the schemas import:

```python
from ..errors import NotFoundError, ServiceUnavailableError
from ..schemas import ConversationHistoryResponse, MessageRequest, MessageResponse
```

Add the route after `post_message`:

```python
@router.get(
    "/{conversation_id}/messages",
    response_model=ConversationHistoryResponse,
)
async def get_history(
    conversation_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    ea_registry = request.app.state.ea_registry
    # Non-creating lookup — do NOT build an EA for a history read.
    ea = ea_registry.peek(customer_id)
    if ea is None:
        raise NotFoundError(detail="Conversation not found.")
    history = ea.get_conversation_history(conversation_id)
    if history is None:
        raise NotFoundError(detail="Conversation not found.")
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        customer_id=customer_id,
        messages=history,
    )
```

- [ ] **Step 9.6: Run history tests**

```bash
uv run pytest tests/unit/api/test_conversation_history.py -v
```

Expected: all PASS.

- [ ] **Step 9.7: Run full suite**

```bash
uv run pytest tests/unit/ -q --timeout=30
```

Expected: all pass.

- [ ] **Step 9.8: Commit**

```bash
jj new -m "feat(api): GET /v1/conversations/{id}/messages

In-memory history on the EA, keyed by conversation_id. Lost on LRU
eviction — documented, not solved. EARegistry.peek() provides a
non-creating lookup so a history GET doesn't build an EA (and its
Redis + mem0 + LangGraph) just to return 404.

Tenant-isolated: wrong customer's token → 404, not 403."
jj squash --from @- --into @
```

---

## Task 10: Webhook parity — tests

**Files:**
- Modify: `tests/unit/api/test_webhooks.py`

- [ ] **Step 10.1: Add failing tests**

Append to `tests/unit/api/test_webhooks.py`:

```python
import asyncio
import logging


class TestWebhookCustomerIdValidation:
    """
    customer_id path parameter is validated against the same pattern
    as the provisioning endpoint's request body — shell metacharacters,
    path traversal, unbounded length must be rejected before hitting
    manager.get_channel().
    """

    def test_path_traversal_422(self):
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)
        r = client.post("/webhook/whatsapp/..%2F..%2Fetc%2Fpasswd", content=b"x")
        assert r.status_code == 422

    def test_oversized_422(self):
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)
        r = client.post(f"/webhook/whatsapp/{'a' * 100}", content=b"x")
        assert r.status_code == 422

    def test_invalid_chars_422(self):
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)
        r = client.post("/webhook/whatsapp/UPPER_CASE", content=b"x")
        assert r.status_code == 422

    def test_valid_but_unprovisioned_still_404(self):
        mgr = WhatsAppManager()
        app = _app_with_manager(mgr)
        client = TestClient(app)
        r = client.post("/webhook/whatsapp/valid_but_ghost", content=b"x")
        assert r.status_code == 404


class TestWebhookTimeout:
    """
    EA calls are bounded by the same timeout as /v1/conversations/message.
    A hung LLM or mem0 connection returns 200 (not 503) — Twilio would
    retry on non-2xx, creating a storm.
    """

    def test_timeout_constant_shared_with_conversations(self):
        from src.api.routes.webhooks import _EA_CALL_TIMEOUT as wh_timeout
        from src.api.routes.conversations import _EA_CALL_TIMEOUT as conv_timeout
        assert wh_timeout is conv_timeout

    def test_hung_ea_returns_200_not_503(self, caplog):
        incoming = IncomingMessage(
            provider_message_id="SM_slow",
            from_number="+15551234567",
            to_number="+14155238886",
            body="hello",
        )
        mgr, provider = _manager_with_mock_provider(
            parse_result=[incoming], signature_valid=True,
        )

        # EA that never returns
        async def _hang(**_):
            await asyncio.sleep(1000)
        hung_ea = MagicMock()
        hung_ea.handle_customer_interaction = _hang

        app = _app_with_manager(mgr, ea_factory=lambda cid: hung_ea)
        # Patch the timeout to something tiny so the test is fast
        import src.api.routes.webhooks as webhooks_mod
        orig_timeout = webhooks_mod._EA_CALL_TIMEOUT
        webhooks_mod._EA_CALL_TIMEOUT = 0.05
        try:
            client = TestClient(app)
            with caplog.at_level(logging.ERROR):
                r = client.post("/webhook/whatsapp/cust_wa", content=b"x")
        finally:
            webhooks_mod._EA_CALL_TIMEOUT = orig_timeout

        assert r.status_code == 200  # NOT 503
        # Timeout was logged
        assert any("timed out" in rec.getMessage().lower()
                   for rec in caplog.records)
```

- [ ] **Step 10.2: Run — verify tests fail**

```bash
uv run pytest tests/unit/api/test_webhooks.py -v
```

Expected: new tests FAIL (validation passes through; timeout hangs or
the symbol doesn't exist).

- [ ] **Step 10.3: Commit**

```bash
jj new -m "test(api): webhook timeout + customer_id validation

Webhook enforces _CUSTOMER_ID_PATTERN on path param (422 on mismatch),
times out after _EA_CALL_TIMEOUT (same constant as conversations), and
returns 200 on timeout — not 503."
jj squash --from @- --into @
```

---

## Task 11: Webhook parity — implementation

**Files:**
- Modify: `src/api/routes/conversations.py:41` (export the constant)
- Modify: `src/api/routes/webhooks.py`

- [ ] **Step 11.1: Share the timeout constant**

No move needed — `conversations._EA_CALL_TIMEOUT` is already a
module-level name. `webhooks.py` imports it.

- [ ] **Step 11.2: Rewrite webhooks.py**

Replace `src/api/routes/webhooks.py` entirely with:

```python
"""
WhatsApp webhook, mounted into the main API.

We don't reimplement webhook handling. The provider abstraction in
src/communication/whatsapp/ already does signature validation, message
parsing, and status-callback routing. We call into it via
webhook_server._handle_incoming, wiring the EA registry as the handler.

Route path matches the standalone webhook server exactly:
  POST /webhook/whatsapp/{customer_id}

Parity with /v1/conversations/message:
  - customer_id validated against _CUSTOMER_ID_PATTERN (422 on mismatch)
  - EA call bounded by _EA_CALL_TIMEOUT
Timeout returns 200 (not 503) — Twilio retries on non-2xx, creating a
storm of duplicates hitting the same hung backend.
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Path, Request, Response

from src.communication.webhook_server import _handle_incoming
from src.communication.whatsapp import IncomingMessage, StatusUpdate
from src.agents.executive_assistant import ConversationChannel

from ..schemas import _CUSTOMER_ID_PATTERN
from .conversations import _EA_CALL_TIMEOUT

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])


@router.post("/webhook/whatsapp/{customer_id}")
async def whatsapp_webhook(
    request: Request,
    customer_id: str = Path(pattern=_CUSTOMER_ID_PATTERN),
):
    manager = request.app.state.whatsapp_manager
    ea_registry = request.app.state.ea_registry

    channel = await manager.get_channel(customer_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Unknown customer")

    body = await request.body()
    headers = dict(request.headers)
    url = channel.webhook_url or str(request.url)

    # Signature check before touching the body. Same ordering as the
    # standalone server — don't parse untrusted payloads.
    if not channel.provider.validate_signature(url=url, body=body, headers=headers):
        logger.warning("Invalid webhook signature for customer=%s", customer_id)
        raise HTTPException(status_code=403, detail="Invalid signature")

    events = channel.provider.parse_webhook(
        body, request.headers.get("content-type", ""),
    )

    # EA handler with the same timeout as /v1/conversations/message.
    # Timeout is CAUGHT inside the handler and re-raised as a plain
    # Exception — _handle_incoming already wraps exceptions and sends
    # a fallback reply, so the customer gets SOMETHING and we return
    # 200 to Twilio.
    async def ea_handler(*, message: str, conversation_id: str) -> str:
        ea = await ea_registry.get(customer_id)
        try:
            return await asyncio.wait_for(
                ea.handle_customer_interaction(
                    message=message,
                    channel=ConversationChannel.WHATSAPP,
                    conversation_id=conversation_id,
                ),
                timeout=_EA_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Webhook EA timed out for customer=%s conv=%s after %.0fs",
                customer_id, conversation_id, _EA_CALL_TIMEOUT,
            )
            # Re-raise so _handle_incoming's exception wrapper fires
            # and sends the fallback reply. We do NOT propagate a 503.
            raise

    for event in events:
        if isinstance(event, IncomingMessage):
            await _handle_incoming(channel, event, ea_handler)
        elif isinstance(event, StatusUpdate):
            await channel.handle_status_callback(event)

    return Response(status_code=200)
```

- [ ] **Step 11.3: Run webhook tests**

```bash
uv run pytest tests/unit/api/test_webhooks.py -v
```

Expected: all PASS.

- [ ] **Step 11.4: Run full suite**

```bash
uv run pytest tests/unit/ -q --timeout=30
```

Expected: all pass.

- [ ] **Step 11.5: Commit**

```bash
jj new -m "fix(api): webhook timeout parity + customer_id validation

Imports _EA_CALL_TIMEOUT from conversations (single source of truth).
Hung EA → timeout → fallback reply sent → 200 returned. Twilio retries
on non-2xx, so 503 would create a storm.

customer_id path parameter now validated against _CUSTOMER_ID_PATTERN
— shell metacharacters, path traversal, oversized strings rejected at
the FastAPI layer before reaching manager.get_channel()."
jj squash --from @- --into @
```

---

## Task 12: Final validation

- [ ] **Step 12.1: Full test run**

```bash
uv run pytest tests/unit/ -q --timeout=30
```

Expected: ≥450 passed (442 baseline + new tests).

- [ ] **Step 12.2: Validation checklist**

```bash
# No JS in src/api
find src/api -name "*.js"  # → empty

# No phantom services
grep -E "memory-monitor|security-api" docker-compose.ci.yml  # → empty

# CI uses uv
grep -E "setup-uv|uv sync|uv run pytest" .github/workflows/ci.yml  # → 3 matches

# Finance registered
uv run python -c "
import unittest.mock as m
with m.patch('src.agents.executive_assistant.ExecutiveAssistantMemory'), \
     m.patch('src.agents.executive_assistant.WorkflowCreator'), \
     m.patch('src.agents.executive_assistant.ChatOpenAI'):
    from src.agents.executive_assistant import ExecutiveAssistant
    ea = ExecutiveAssistant(customer_id='x')
    assert ea.delegation_registry.get('finance') is not None
    print('finance registered ✓')
"
```

- [ ] **Step 12.3: Show the commit stack**

```bash
jj log -r 'main..@' --no-graph \
  -T 'change_id.short() ++ " " ++ description.first_line() ++ "\n"'
```

Expected 10-11 commits.
