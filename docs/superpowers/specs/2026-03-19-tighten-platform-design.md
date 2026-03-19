# Tighten the Platform — Design

Status: approved
Date: 2026-03-19

## Scope

Close every open seam left by the Python consolidation: dead JS removal,
finance-specialist wiring, CI repair, request correlation, conversation
history, webhook parity. Tests before implementation. Commits via jj.

## Subtasks

### 1. Dead code in `src/api/`

Delete:
- `src/api/server.js`
- `src/api/auth.js`
- `src/api/customer-provisioning-api.js`
- `src/api/cross-system-bridge.js`
- `src/api/websocket-poc.js`
- `src/api/tests/api-validation-suite.js` (and `src/api/tests/` dir)

Sweep: no `package.json` at repo root, `.gitignore` retains generic
`node_modules/` entries (harmless), no Makefile. No other Node artefacts.

### 2. Wire FinanceSpecialist

`executive_assistant.py:59` imports `SocialMediaSpecialist` unguarded;
`:599` registers it. Finance gets the same treatment but **guarded**:

```python
# Module level — guard the import so a broken finance.py doesn't take
# the whole EA down. Social media stays unguarded (established baseline).
try:
    from .specialists.finance import FinanceSpecialist
    _FINANCE_AVAILABLE = True
except Exception as e:
    logger.warning(f"Finance specialist unavailable: {e}")
    _FINANCE_AVAILABLE = False
```

`__init__`:

```python
self.delegation_registry.register(SocialMediaSpecialist())
if _FINANCE_AVAILABLE:
    self.delegation_registry.register(FinanceSpecialist())
```

Tests (`tests/unit/test_ea_specialist_registration.py`, new file):
- both specialists registered when imports succeed
- EA still initializes when `_FINANCE_AVAILABLE = False` (monkeypatch)
- "Track this invoice: $2,400 from Acme Corp" routes to finance via
  `delegation_registry.route()` → domain `"finance"`
- "What's my ROI on the Facebook campaign?" doesn't crash; routing
  produces a coherent decision (strategic or routes to one specialist —
  not both, not an exception)

### 3. Fix CI

`docker-compose.ci.yml`: remove `memory-monitor` and `security-api`
services. Keep postgres, redis, qdrant.

`.github/workflows/ci.yml`: full rewrite.

```yaml
name: CI
on:
  push: {branches: ['**']}
  pull_request: {branches: ['main']}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: {version: "latest"}
      - name: Set up Python
        run: uv python install 3.12
      - name: Install deps
        run: uv sync
      - name: Start services
        run: |
          docker compose -f docker-compose.ci.yml up -d
          timeout 60 bash -c 'until docker compose -f docker-compose.ci.yml exec -T postgres pg_isready -U testuser; do sleep 2; done'
          timeout 30 bash -c 'until docker compose -f docker-compose.ci.yml exec -T redis redis-cli ping; do sleep 2; done'
      - name: Run unit tests
        run: uv run pytest tests/unit/ --tb=short -q
      - name: Security check
        continue-on-error: true
        run: |
          if grep -r "password\|secret\|api_key" --include="*.yml" --include="*.yaml" --include="*.json" . | grep -v "#\|//"; then
            echo "⚠️  Potential secrets in config"
          fi
      - if: always()
        run: docker compose -f docker-compose.ci.yml down -v
```

### 4. Request correlation

New file: `src/api/correlation.py`

```python
import logging
import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

def get_correlation_id() -> str:
    return _correlation_id.get()

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = _correlation_id.get()
        return True

class CorrelationIdMiddleware:
    """Pure ASGI middleware. Sets contextvar before dispatch, injects
    X-Request-ID on every response including error handlers."""
    HEADER = "x-request-id"

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Extract or generate
        hdrs = dict(scope.get("headers", []))
        raw = hdrs.get(self.HEADER.encode())
        cid = raw.decode() if raw else str(uuid.uuid4())
        token = _correlation_id.set(cid)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self.HEADER.encode(), cid.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            _correlation_id.reset(token)
```

Wired in `app.py`:

```python
from .correlation import CorrelationIdMiddleware, CorrelationIdFilter
# after FastAPI() construction:
app.add_middleware(CorrelationIdMiddleware)
# and install the filter on the root logger:
logging.getLogger().addFilter(CorrelationIdFilter())
```

`src/utils/logging.py`: `JSONFormatter.format` picks up
`record.correlation_id` (via `getattr(record, "correlation_id", "-")`).

Tests (`tests/unit/api/test_correlation.py`, new file):
- client-provided `X-Request-ID` echoed unchanged
- auto-generated is valid UUID4
- header present on: `/healthz`, `/readyz`, `/v1/conversations/message`,
  `/v1/customers/provision`, `/webhook/whatsapp/{id}`
- header present on 401, 422, 404, 500, 503
- two concurrent requests get distinct IDs
- log records captured during a request carry `correlation_id`

### 5. Conversation history

`ExecutiveAssistant` gains an in-memory history store:

```python
# In __init__
self._history: Dict[str, List[Dict[str, Any]]] = {}

# New public method
def get_conversation_history(self, conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    """Return chronological message list, or None if unknown conversation.
    In-memory only — lost on EA eviction from the registry's LRU cache."""
    return self._history.get(conversation_id)
```

`handle_customer_interaction` appends both the user message and the EA
response with server timestamps (`datetime.now(timezone.utc).isoformat()`).

New schema in `src/api/schemas.py`:

```python
class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str

class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    customer_id: str
    channel: Optional[Channel]
    messages: List[HistoryMessage]
```

Route `src/api/routes/conversations.py`:

```python
@router.get("/{conversation_id}/messages", response_model=ConversationHistoryResponse)
async def get_history(
    conversation_id: str,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    ea_registry = request.app.state.ea_registry
    # Do NOT call .get() — that would create an EA for an unknown customer.
    # Use peek (non-creating lookup).
    ea = ea_registry.peek(customer_id)
    if ea is None:
        raise NotFoundError(detail="Conversation not found.")
    history = ea.get_conversation_history(conversation_id)
    if history is None:
        raise NotFoundError(detail="Conversation not found.")
    # Empty list → 200 with empty messages
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        customer_id=customer_id,
        channel=history[0].get("channel") if history else None,
        messages=[HistoryMessage(**m) for m in history],
    )
```

`EARegistry.peek(customer_id)` — new non-creating lookup so a GET
doesn't instantiate an EA (and its Redis/mem0/LangGraph) just to say
"not found."

Tests (`tests/unit/api/test_conversation_history.py`, new file):
- 401 without token
- 404 for unknown conversation
- 404 for another customer's conversation (tenant isolation)
- 200 with empty list for existing-but-empty conversation
- chronological ordering
- roundtrip: POST message → GET history → see user + assistant messages

### 6. Webhook parity

**Timeout.** Import `_EA_CALL_TIMEOUT` from conversations (or lift to a
shared module — `src/api/routes/__init__.py` gets the constant, both
routes import it). Wrap the `ea_handler` call:

```python
async def ea_handler(*, message: str, conversation_id: str) -> str:
    ea = await ea_registry.get(customer_id)
    return await asyncio.wait_for(
        ea.handle_customer_interaction(...),
        timeout=_EA_CALL_TIMEOUT,
    )
```

Timeout inside the event loop raises `asyncio.TimeoutError` →
`_handle_incoming` in `webhook_server.py` already catches `Exception` and
sends a fallback reply. The route returns 200. Log at ERROR.

**Validation.** `fastapi.Path` with the shared pattern:

```python
from ..schemas import _CUSTOMER_ID_PATTERN
@router.post("/webhook/whatsapp/{customer_id}")
async def whatsapp_webhook(
    customer_id: str = Path(pattern=_CUSTOMER_ID_PATTERN),
    request: Request = ...,
):
```

Tests (append to `tests/unit/api/test_webhooks.py`):
- `../../etc/passwd` → 422
- 100-char string → 422
- valid-but-unprovisioned → 404 (existing behaviour preserved)
- EA handler that sleeps forever → response still 200, timeout logged
- timeout constant matches conversations' (import the same symbol)

### 7. Error class

Add `NotFoundError(APIError)` in `src/api/errors.py` (status 404, type
`"not_found"`). Existing handler covers it.

## Commit sequence (jj)

Each commit is tests-then-impl or self-contained.

1. `chore(api): remove Phase 1 JavaScript artefacts`
2. `test(ea): specialist registration + finance routing`
3. `feat(ea): register FinanceSpecialist with guarded import`
4. `fix(ci): remove phantom Docker services, switch to uv + pytest`
5. `test(api): request correlation ID`
6. `feat(api): correlation-ID middleware + logging filter`
7. `test(api): GET /v1/conversations/{id}/messages`
8. `feat(ea): in-memory conversation history + read endpoint`
9. `test(api): webhook timeout + customer_id validation`
10. `fix(api): webhook timeout parity + path validation`

## Validation checklist

- `find src/api -name '*.js'` → empty
- `uv run pytest tests/unit/ -q` → 0 failures
- `docker-compose.ci.yml` has no `memory-monitor`/`security-api`
- `ci.yml` uses `setup-uv`, `uv sync`, `pytest tests/unit/`
- `ea.delegation_registry.get("finance")` is not None after init
- `_FINANCE_AVAILABLE = False` → EA still initializes
- Every HTTP response carries `X-Request-ID`
- Log records during request processing have `correlation_id`
- `GET /v1/conversations/{id}/messages` tenant-isolated
- Webhook: invalid `customer_id` → 422, timeout → 200
