# Platform Tightening — Design Spec

Closes every open seam: dead code removal, specialist wiring, CI repair, request correlation, conversation history endpoint, and webhook parity fixes.

## 1. Dead JS Cleanup

Delete five legacy JavaScript files from `src/api/`:

- `server.js` — Express server, replaced by FastAPI `app.py`
- `auth.js` — JWT middleware, replaced by `auth.py`
- `customer-provisioning-api.js` — replaced by `routes/provisioning.py`
- `cross-system-bridge.js` — MCP bridge referencing non-existent infrastructure
- `websocket-poc.js` — proof-of-concept, never used

Sweep for stray Node artifacts (`package.json`, `node_modules` in `.gitignore`, npm scripts in Makefiles). Remove any found. No Python files touched.

## 2. Finance Specialist Wiring

### Registration

`FinanceSpecialist` from `src/agents/specialists/finance.py` gets registered in `ExecutiveAssistant.__init__` alongside `SocialMediaSpecialist`, via `self.delegation_registry.register(FinanceSpecialist())`.

### Import guards

The existing `SocialMediaSpecialist` import on line 59 of `executive_assistant.py` is currently a bare, unguarded import. It must be refactored into a guarded try/except block alongside the new `FinanceSpecialist` import, matching the existing `competitive_positioning` pattern:

```python
try:
    from .specialists.social_media import SocialMediaSpecialist
    _SOCIAL_MEDIA_AVAILABLE = True
except ImportError:
    _SOCIAL_MEDIA_AVAILABLE = False

try:
    from .specialists.finance import FinanceSpecialist
    _FINANCE_AVAILABLE = True
except ImportError:
    _FINANCE_AVAILABLE = False
```

Registration in `__init__` is conditional on the availability flag. If either import fails, the EA degrades to generalist mode for that domain — it does not crash.

### Tests (written before implementation)

- Both specialists registered when imports succeed
- EA initializes when finance import fails (mocked `ImportError`)
- EA initializes when social media import fails
- "Track this invoice: $2,400 from Acme Corp" routes through the EA delegation pipeline to the finance specialist (mocked LLM, mocked memory)
- "What's my ROI on the Facebook campaign?" does not crash and produces a coherent routing decision (cross-domain overlap test)

## 3. Request Correlation

### Implementation: pure ASGI middleware

A class implementing the ASGI protocol directly (`__call__(self, scope, receive, send)`). No `BaseHTTPMiddleware` — avoids known issues with streaming responses and gives uniform control over both success and exception paths.

Behavior:
1. Read `X-Request-ID` from request headers; if absent, generate UUID4
2. Set a `contextvars.ContextVar[str]` (`correlation_id`) for the duration of the request
3. On response (both normal and exception paths), set `X-Request-ID` header

The `logging.Filter` that reads the `ContextVar` and injects `correlation_id` into every `LogRecord` is installed **once at app startup** in `create_app()` — not added/removed per-request. The middleware only sets/resets the `ContextVar` value per request. This avoids data races on the root logger's filter list under concurrent async requests.

The logging format in app config is updated to include `%(correlation_id)s`. Existing log calls are not modified — the filter injects the field automatically.

### Tests (written before implementation)

- Client-provided `X-Request-ID` is echoed back unchanged
- Auto-generated ID is a valid UUID4
- ID appears in response headers for every route (health, readiness, conversations, provisioning, webhooks)
- ID appears in captured log records during request processing
- Error responses (401, 422, 500, 503) carry the header
- Two concurrent requests get distinct correlation IDs

## 4. Conversation History

### Endpoint

`GET /v1/conversations/{conversation_id}/messages`

- Auth: Bearer JWT (same `get_current_customer` dependency)
- Tenant-isolated: wrong customer → 404 (not 403, don't confirm existence)
- Response: `{ conversation_id, customer_id, messages: [{ role, content, timestamp }], channel }`
- Messages ordered chronologically
- Unknown conversation → 404
- Empty conversation (provisioned, never used) → 200 with empty message list

### Architecture

The EA currently builds `ConversationState` per-invocation and does not persist the full message list between calls. To support history retrieval, add a `self._conversation_histories: dict[str, list[dict]]` on the EA instance. `handle_customer_interaction` appends `{role, content, timestamp}` entries to this dict (keyed by `conversation_id`) for each user message and EA response.

The API layer does not reach into `ConversationState` or `_conversation_histories` directly. A new public method on `ExecutiveAssistant`:

```python
def get_conversation_history(self, conversation_id: str) -> Optional[list[dict]]
```

Returns the message list from `_conversation_histories`, or `None` if the conversation doesn't exist. The route handler uses `EARegistry.get(customer_id)` to retrieve the EA instance, then calls this method.

LRU eviction: when the EA is evicted from cache, `_conversation_histories` is lost with it. This is acceptable for now — documented in a code comment, not solved.

### Tests (written before implementation)

- 401 without auth token
- 404 for wrong customer's conversation (tenant isolation)
- 404 for unknown conversation
- Message ordering is chronological
- Response schema matches spec
- Empty conversation → 200 with empty list
- Roundtrip: send a message, fetch history, see both user message and EA response

## 5. Webhook Parity

### Timeout

The `ea_handler` closure is not called directly by `webhooks.py` — it's passed as a callback to `_handle_incoming`. The timeout must be applied **inside the closure itself**: `ea_handler` wraps the `ea.handle_customer_interaction(...)` call with `asyncio.wait_for` using the shared timeout constant.

The timeout constant `EA_CALL_TIMEOUT` is extracted from `routes/conversations.py` into a shared location (e.g. `src/api/constants.py`) so both `conversations.py` and `webhooks.py` import from there. No cross-import of private symbols between sibling route modules.

Key difference from conversations: timeout returns **200** (not 503). Twilio interprets non-2xx as failure and retries, creating duplicate message storms against a hung backend. Log at ERROR level, return 200.

### Input validation

Validate `customer_id` path parameter with `fastapi.Path(pattern=_CUSTOMER_ID_PATTERN)`. Import the pattern from `schemas.py` — no duplication.

### Tests (written before implementation)

- Webhook times out gracefully: mock EA that sleeps forever, verify 200 response (not 503), verify timeout logged
- Invalid `customer_id` format (`../../etc/passwd`, empty string, 100-char string) → 422
- Valid but unprovisioned `customer_id` → 404 (existing behavior preserved with new validation)
- Timeout duration matches conversations endpoint (shared constant, not duplicated)

## 6. CI Fix

### docker-compose.ci.yml

Remove `memory-monitor` and `security-api` services entirely — both reference non-existent Dockerfiles (`src/memory/Dockerfile.monitor`, `src/security/Dockerfile.llamaguard-api`). Keep Postgres, Redis, and Qdrant.

### ci.yml rewrite

- Install uv via `astral-sh/setup-uv@v5`
- Set up Python 3.12
- `uv sync` to install deps from lock
- `uv run pytest tests/unit/ --tb=short -q` as primary test step — build fails on any test failure
- Keep docker-compose up for Postgres/Redis/Qdrant (integration tests will need them)
- Gate CI on unit test step, not on health checks for services that don't exist
- Remove: `test_ea_basic.py` step, `executive-assistant.py` check, `schema.sql` check, `pip install` step
- Keep: security check step

## Validation Criteria

- No `.js` files in `src/api/`
- `uv run pytest tests/unit/ -q` passes with zero failures
- CI workflow installs uv, runs `uv sync`, runs unit test suite
- `docker-compose.ci.yml` contains no services referencing non-existent Dockerfiles
- Finance specialist auto-registers on EA init
- EA initializes without finance specialist when import fails
- Finance-domain messages route through EA to finance specialist
- Cross-domain messages don't crash
- Every HTTP response includes `X-Request-ID` (including errors)
- Log records contain correlation ID during request processing
- `GET /v1/conversations/{id}/messages` returns tenant-scoped history
- Wrong customer's conversation → 404
- Webhook enforces same timeout and `customer_id` validation as conversations/provisioning
- Webhook timeout → 200 (not 503)
- All new functionality has tests committed before implementation
