# WhatsApp Channel with Provider Abstraction — Design

**Status:** Approved
**Date:** 2026-03-05
**Phase:** 2 (WhatsApp support for Executive Assistant)

## Problem

The Executive Assistant needs WhatsApp as a conversation channel. The platform is multi-tenant — different customers may use different WhatsApp providers (Twilio, Meta Cloud API, others). The existing `whatsapp_channel.py` is hardcoded to Twilio and has direct database/Redis dependencies with hardcoded credentials, making it impossible to test without live infrastructure.

The channel needs a provider abstraction so the concrete messaging API is swappable per customer, and needs to be a pure I/O adapter testable without Redis, Postgres, or live API access.

## Goals

- `WhatsAppChannel` extends `BaseCommunicationChannel` and delegates all provider-specific operations to an injected `WhatsAppProvider`
- One concrete provider: Twilio, implemented with `httpx` (no SDK lock-in)
- A second provider (Meta Cloud API, etc.) can be added by implementing the provider protocol — zero changes to channel code
- Multi-tenant: each customer's config specifies `provider` + `credentials`, resolved at runtime
- Webhook server validates signatures before processing, routes by customer_id, handles both message and status-callback payloads
- All tests run without Docker services or live API access

## Non-Goals

- Voice, email, SMS channels
- Restructuring the EA's LangGraph conversation pipeline
- New Docker services
- Meta Cloud API implementation (interface supports it; implementation is future work)

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Webhook Server │────▶│  WhatsAppManager │────▶│  WhatsAppChannel     │
│  (FastAPI)      │     │  (multi-tenant)  │     │  (BaseCommChannel)   │
└─────────────────┘     └──────────────────┘     └──────────┬───────────┘
      │                        │                            │
      │ resolves               │ loads config               │ delegates to
      │ customer_id            │ per customer_id            │
      │ from path param        │ builds provider            ▼
      │                        ▼                 ┌──────────────────────┐
      │                 ┌──────────────┐         │ WhatsAppProvider     │
      │                 │ WhatsAppConfig│        │ (Protocol)           │
      │                 │ + env / dict  │        └──────────┬───────────┘
      │                 └──────────────┘                    │
      │                                          ┌──────────┴───────────┐
      ▼                                          ▼                      ▼
┌─────────────────┐                   ┌──────────────────┐   ┌──────────────────┐
│ EA.handle_      │◀──────────────────│ TwilioWhatsApp   │   │ (future: Meta    │
│ customer_       │   response text   │ Provider (httpx) │   │  Cloud API)      │
│ interaction()   │                   └──────────────────┘   └──────────────────┘
└─────────────────┘
```

**Dependency direction:** Channel knows nothing about Twilio, Redis, Postgres, or the EA. It receives a provider and optional message store at construction. The manager wires dependencies.

---

## Components

### File Layout

```
src/communication/
├── base_channel.py                    # unchanged
├── whatsapp_channel.py                # thin re-export for backward compat
├── whatsapp_manager.py                # refactored — provider-agnostic
├── webhook_server.py                  # rewritten — sig validation first, per-customer routing
└── whatsapp/
    ├── __init__.py
    ├── channel.py                     # WhatsAppChannel
    ├── provider.py                    # WhatsAppProvider Protocol + result dataclasses
    ├── config.py                      # WhatsAppConfig dataclass (from_env, from_dict)
    ├── store.py                       # MessageStore Protocol + InMemoryMessageStore
    └── providers/
        ├── __init__.py
        ├── _registry.py               # PROVIDER_REGISTRY + create_provider()
        └── twilio.py                  # TwilioWhatsAppProvider (httpx)
```

### Provider Protocol (`whatsapp/provider.py`)

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Protocol, Mapping

class MessageStatus(Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass
class MediaItem:
    content_type: str
    url: str

@dataclass
class SendResult:
    provider_message_id: str
    status: MessageStatus
    raw: dict

@dataclass
class IncomingMessage:
    provider_message_id: str
    from_number: str       # normalized E.164, no "whatsapp:" prefix
    to_number: str
    body: str
    profile_name: str | None = None
    media: list[MediaItem] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

@dataclass
class StatusUpdate:
    provider_message_id: str
    status: MessageStatus
    error_code: str | None = None
    raw: dict = field(default_factory=dict)

WebhookEvent = IncomingMessage | StatusUpdate

class WhatsAppProvider(Protocol):
    provider_name: str

    async def send_text(self, to: str, body: str, from_: str) -> SendResult: ...
    def parse_webhook(self, body: bytes, content_type: str) -> list[WebhookEvent]: ...
    def validate_signature(self, url: str, body: bytes, headers: Mapping[str, str]) -> bool: ...
    async def fetch_status(self, provider_message_id: str) -> MessageStatus: ...
```

`parse_webhook` returns a **list** because Meta Cloud API batches multiple events per webhook. Twilio sends one. Union return type lets one endpoint handle both incoming messages and delivery status callbacks — Twilio can post both to the same URL depending on config, and Meta always interleaves them.

### Twilio Provider (`whatsapp/providers/twilio.py`)

- Constructor: `account_sid`, `auth_token`, optional `http_client: httpx.AsyncClient | None`
- `send_text` → `POST https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json`, Basic auth, form-encoded body (`To=whatsapp:+1...`, `From=whatsapp:+1...`, `Body=...`)
- `parse_webhook` → form-decode; distinguish message (`Body` present) from status callback (`MessageStatus` present, no `Body`); normalize phone numbers by stripping `whatsapp:` prefix
- `validate_signature` → correct Twilio algorithm:
  1. Take the full webhook URL
  2. Sort POST params by key, append `key+value` pairs to URL (no delimiters)
  3. `base64(HMAC-SHA1(auth_token, concatenated_string))`
  4. Constant-time compare with `X-Twilio-Signature` header
- `fetch_status` → `GET /Accounts/{sid}/Messages/{msg_sid}.json`
- HTTP client injection enables `httpx.MockTransport` in tests

### Provider Registry (`whatsapp/providers/_registry.py`)

```python
PROVIDER_REGISTRY: dict[str, Callable[[dict], WhatsAppProvider]] = {
    "twilio": lambda cfg: TwilioWhatsAppProvider(
        account_sid=cfg["account_sid"],
        auth_token=cfg["auth_token"],
    ),
}

def create_provider(provider_name: str, credentials: dict) -> WhatsAppProvider:
    if provider_name not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown WhatsApp provider: {provider_name}")
    return PROVIDER_REGISTRY[provider_name](credentials)
```

### Message Store (`whatsapp/store.py`)

```python
class MessageStore(Protocol):
    async def record_outbound(self, customer_id: str, conversation_id: str,
                              result: SendResult, to: str, body: str) -> None: ...
    async def record_inbound(self, customer_id: str, conversation_id: str,
                             msg: IncomingMessage) -> None: ...
    async def update_status(self, provider_message_id: str, status: MessageStatus) -> None: ...
    async def get_status(self, provider_message_id: str) -> MessageStatus | None: ...

class InMemoryMessageStore:
    """Default store. No external deps. Unbounded — production should inject DB-backed store."""
```

`InMemoryMessageStore` holds two dicts: `{provider_message_id: MessageStatus}` and `{conversation_id: list[MessageRecord]}`. Tests use it directly. Production: `WhatsAppManager` injects a DB-backed implementation (kept in `whatsapp_manager.py`, out of scope for the channel).

### WhatsApp Channel (`whatsapp/channel.py`)

```python
class WhatsAppChannel(BaseCommunicationChannel):
    def __init__(self, customer_id: str, config: dict | None = None, *,
                 provider: WhatsAppProvider,
                 store: MessageStore | None = None):
        super().__init__(customer_id, config)
        self._provider = provider
        self._store = store or InMemoryMessageStore()
        self._from_number = (config or {}).get("from_number", "")

    def _get_channel_type(self) -> ChannelType:
        return ChannelType.WHATSAPP

    async def initialize(self) -> bool:
        self.is_initialized = True
        return True

    async def send_message(self, to: str, content: str, **kwargs) -> str:
        result = await self._provider.send_text(to=to, body=content, from_=self._from_number)
        conv_id = self._conversation_id_for(to)
        await self._store.record_outbound(self.customer_id, conv_id, result, to, content)
        return result.provider_message_id

    async def handle_incoming_message(self, message_data: dict) -> BaseMessage:
        # message_data is an IncomingMessage asdict() — webhook server passes parsed event
        conv_id = self._conversation_id_for(message_data["from_number"])
        msg = BaseMessage(
            content=message_data["body"],
            from_number=message_data["from_number"],
            to_number=message_data["to_number"],
            channel=ChannelType.WHATSAPP,
            message_id=message_data["provider_message_id"],
            conversation_id=conv_id,
            timestamp=datetime.now(),
            customer_id=self.customer_id,
            metadata=message_data.get("raw", {}),
        )
        # record_inbound is called by webhook server with the IncomingMessage object
        return msg

    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        # BaseCommunicationChannel ABC signature is (payload: str, signature: str)
        # Provider needs (url, body, headers) — channel stores webhook_url from config
        # and reconstructs headers from the single signature string
        return self._provider.validate_signature(
            url=self.config.get("webhook_url", ""),
            body=payload.encode() if isinstance(payload, str) else payload,
            headers={"X-Twilio-Signature": signature},  # generalized in webhook server
        )

    async def handle_status_callback(self, update: StatusUpdate) -> None:
        await self._store.update_status(update.provider_message_id, update.status)

    async def get_message_status(self, message_id: str) -> dict:
        status = await self._store.get_status(message_id)
        if status is None:
            status = await self._provider.fetch_status(message_id)
        return {"message_id": message_id, "status": status.value,
                "timestamp": datetime.now().isoformat()}

    def _conversation_id_for(self, phone_number: str) -> str:
        key = f"{self.customer_id}:{phone_number}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
```

No Redis. No psycopg2. No EA import. No Twilio import.

### Config (`whatsapp/config.py`)

Follows `src/utils/config.py` convention:

```python
@dataclass
class WhatsAppConfig:
    provider: str                    # "twilio"
    from_number: str                 # "+14155238886"
    credentials: dict[str, str]      # {"account_sid": ..., "auth_token": ...}
    webhook_base_url: str = ""

    @classmethod
    def from_env(cls, prefix: str = "WHATSAPP_") -> "WhatsAppConfig":
        provider = os.getenv(f"{prefix}PROVIDER", "twilio")
        if provider == "twilio":
            creds = {
                "account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
                "auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
            }
        else:
            creds = {}
        return cls(
            provider=provider,
            from_number=os.getenv(f"{prefix}FROM_NUMBER", ""),
            credentials=creds,
            webhook_base_url=os.getenv(f"{prefix}WEBHOOK_BASE_URL", ""),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "WhatsAppConfig": ...
```

### Webhook Server (`webhook_server.py`) — Rewritten

- `POST /webhook/whatsapp/{customer_id}` — per-customer path. Twilio console lets you set webhook URL per number; each customer's number points to their path. Simpler than reverse-lookup by `To` header.
- Handler flow:
  1. `channel = manager.get_channel(customer_id)` — 404 if unknown customer
  2. `provider.validate_signature(full_url, raw_body, headers)` — **403 if invalid, before any parsing**
  3. `events = provider.parse_webhook(raw_body, content_type)`
  4. For each `IncomingMessage`: `store.record_inbound()` → `base_msg = channel.handle_incoming_message(asdict(event))` → `response_text = await ea_handler(base_msg)` → `await channel.send_message(base_msg.from_number, response_text)`
  5. For each `StatusUpdate`: `await channel.handle_status_callback(event)`
  6. Return `Response(status_code=200)` — Twilio only needs 2xx, body is ignored
- EA is injected via dependency provider function (FastAPI `Depends`) — tests override with a mock
- Drops the double-processing bug (current code runs webhook sync then queues the same work again as a background task)

### Manager (`whatsapp_manager.py`) — Refactored

- Holds `dict[customer_id, WhatsAppConfig]` — loaded from an injectable `ConfigLoader` (default: env vars; production: DB-backed loader retained from current code)
- `get_channel(customer_id)` → lazy-build: resolve `WhatsAppConfig` → `create_provider(cfg.provider, cfg.credentials)` → construct `WhatsAppChannel` → cache
- `register_customer(customer_id, config: WhatsAppConfig)` — in-memory registration for tests + API-driven onboarding
- DB-backed `MessageStore` implementation lives here (moved out of channel)

---

## Data Flow

### Inbound

```
Twilio → POST /webhook/whatsapp/{customer_id}
  ├─ manager.get_channel(customer_id)               [404 if unknown]
  ├─ provider.validate_signature(url, body, hdrs)   [403 if invalid]
  ├─ events = provider.parse_webhook(body, ctype)
  ├─ for IncomingMessage ev:
  │    ├─ store.record_inbound(cid, conv_id, ev)
  │    ├─ base_msg = channel.handle_incoming_message(asdict(ev))
  │    ├─ response = ea.handle_customer_interaction(base_msg.content, WHATSAPP, conv_id)
  │    └─ channel.send_message(base_msg.from_number, response)
  ├─ for StatusUpdate ev:
  │    └─ channel.handle_status_callback(ev) → store.update_status()
  └─ 200 OK (empty body)
```

### Outbound (EA-initiated)

```
ea → manager.get_channel(customer_id).send_message(to, text)
  ├─ provider.send_text(to, text, from_=config.from_number)
  │    └─ httpx POST → Twilio API → {sid, status}
  ├─ store.record_outbound(customer_id, conv_id, result, to, text)
  └─ return result.provider_message_id
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Bad webhook signature | `403 Forbidden` before touching body |
| Unknown `customer_id` | `404 Not Found` |
| `provider.send_text` HTTP 4xx/5xx | Raise `WhatsAppSendError(status_code, error_code, message)` — caller handles retry policy, never silently swallowed |
| `parse_webhook` gets unparseable payload | Return `[]`, log WARNING. Webhook still gets 200 — provider retries non-2xx, we don't want retry storms from malformed input |
| EA raises during message processing | Catch in webhook handler, send generic "I'll get back to you" via `channel.send_message`, log ERROR with message_id, return 200 (prevent Twilio retry; EA bug shouldn't retrigger same failure) |
| `store.*` raises | Log WARNING, continue. Storage is best-effort observability, never blocks message delivery |
| Provider HTTP timeout | `WhatsAppSendError` with timeout indication — no automatic retry in provider, caller decides |

---

## Testing Strategy

### Test Assertion Quality

**All assertions compare against exact expected values.** No `assert result is not None`, no `assert "success" in str(response)`, no `assert len(x) > 0`. Every assertion states the precise expected value:

```python
# Bad
assert result is not None
assert "SM" in result.provider_message_id

# Good
assert result.provider_message_id == "SM1234567890abcdef"
assert result.status == MessageStatus.QUEUED
assert mock_transport.request_log[0].url == "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json"
assert dict(mock_transport.request_log[0].form) == {"To": "whatsapp:+15551234567", "From": "whatsapp:+14155238886", "Body": "hello"}
```

### Unit Tests

**`tests/unit/test_whatsapp_provider_twilio.py`**
- `test_send_text_formats_request_correctly` — MockTransport captures request; assert URL, auth header, form body exactly
- `test_send_text_parses_response` — assert `SendResult.provider_message_id == "SM..."`, `status == QUEUED`
- `test_send_text_raises_on_4xx` — assert `WhatsAppSendError` raised with correct `status_code` and `error_code` extracted from Twilio error JSON
- `test_parse_webhook_incoming_message` — feed real Twilio form-encoded payload, assert every field of `IncomingMessage` matches expected value
- `test_parse_webhook_status_callback` — feed `MessageStatus=delivered` payload, assert `StatusUpdate.status == DELIVERED`
- `test_parse_webhook_with_media` — assert `media[0].content_type == "image/jpeg"` and `media[0].url == "https://..."`
- `test_parse_webhook_unparseable_returns_empty` — assert `parse_webhook(b"garbage", "text/plain") == []`
- `test_validate_signature_valid` — precompute correct signature with known auth_token + URL + params, assert `validate_signature(...) is True`
- `test_validate_signature_tampered_body` — change one param, assert `validate_signature(...) is False`
- `test_validate_signature_wrong_url` — correct body, wrong URL, assert `False`
- `test_validate_signature_missing_header` — assert `False`
- `test_fetch_status_parses_response` — assert returned `MessageStatus == DELIVERED`

**`tests/unit/test_whatsapp_channel.py`**
- `test_channel_type` — assert `channel.channel_type == ChannelType.WHATSAPP`
- `test_send_message_delegates_to_provider` — Mock(spec=WhatsAppProvider); assert `provider.send_text.call_args == call(to="+15551234567", body="hello", from_="+14155238886")`
- `test_send_message_returns_provider_id` — assert returned value `== "SM_mock_123"`
- `test_send_message_records_to_store` — inject Mock store, assert `store.record_outbound` called with exact args
- `test_handle_incoming_message_builds_base_message` — assert every `BaseMessage` field equals expected value
- `test_conversation_id_deterministic` — same customer_id + phone → same conv_id; different phone → different conv_id (assert actual hash values)
- `test_handle_status_callback_updates_store` — assert `store.update_status.call_args == call("SM123", MessageStatus.DELIVERED)`
- `test_get_message_status_prefers_store` — store has status, provider.fetch_status not called (`assert provider.fetch_status.call_count == 0`)
- `test_get_message_status_falls_back_to_provider` — store returns None, assert `provider.fetch_status.call_args == call("SM123")`
- `test_validate_webhook_signature_delegates` — assert provider's `validate_signature` called with correct url/body/headers

**`tests/unit/test_whatsapp_store.py`**
- `test_inmemory_record_outbound_then_get_status` — record, assert `get_status("SM123") == MessageStatus.QUEUED`
- `test_inmemory_update_status` — record → update → assert `get_status("SM123") == MessageStatus.DELIVERED`
- `test_inmemory_unknown_id` — assert `get_status("nonexistent") is None`

**`tests/unit/test_whatsapp_config.py`**
- `test_from_env_twilio` — monkeypatch env vars, assert every `WhatsAppConfig` field
- `test_from_dict` — assert round-trip

**`tests/unit/test_whatsapp_provider_registry.py`**
- `test_create_twilio_provider` — assert `isinstance(p, TwilioWhatsAppProvider)` and `p.provider_name == "twilio"`
- `test_unknown_provider_raises` — assert `ValueError` with specific message

### Integration Tests

**`tests/integration/test_whatsapp_webhook.py`** — FastAPI `TestClient`
- `test_inbound_message_routes_to_ea` — POST Twilio form payload with valid signature; mock EA returns `"ea response"`; mock provider captures send; assert EA called with correct text+channel+conv_id, assert `provider.send_text` called with `(to="+1555...", body="ea response", from_="+1415...")`
- `test_invalid_signature_returns_403_before_ea` — bad signature; assert `response.status_code == 403`; assert `mock_ea.call_count == 0`
- `test_status_callback_updates_store` — POST status payload; assert store has updated status; assert EA not called
- `test_unknown_customer_returns_404` — assert 404
- `test_ea_exception_sends_fallback_and_returns_200` — EA raises; assert `provider.send_text` called with fallback text; assert `response.status_code == 200`

**Tests use `httpx.MockTransport` + `unittest.mock.Mock(spec=...)` + `InMemoryMessageStore`. Zero Docker, zero network, zero DB.**

---

## Backward Compatibility

`src/communication/whatsapp_channel.py` becomes:

```python
from .whatsapp.channel import WhatsAppChannel
from .whatsapp.provider import IncomingMessage as WhatsAppMessage  # closest analog
__all__ = ["WhatsAppChannel", "WhatsAppMessage"]
```

Existing `from src.communication import WhatsAppChannel` keeps working. Existing `WhatsAppMessage` import maps to the new `IncomingMessage` — structurally similar enough for any current caller (there are none in the codebase beyond the webhook server, which is being rewritten anyway).

---

## Sequencing

1. Provider protocol + dataclasses (`provider.py`)
2. Twilio provider + registry (`providers/twilio.py`, `providers/_registry.py`)
3. `InMemoryMessageStore` (`store.py`)
4. `WhatsAppConfig` (`config.py`)
5. `WhatsAppChannel` (`channel.py`)
6. Rewrite `webhook_server.py`
7. Refactor `whatsapp_manager.py`
8. Re-export shim in old `whatsapp_channel.py`
9. Tests (TDD: each step above gets tests-first)

---

## Open Items (Out of Scope for This Phase)

- DB-backed `MessageStore` — production will need it; `InMemoryMessageStore` is sufficient for now and proves the interface
- Media sending (images, documents) — provider protocol allows it via extension (`send_media(...)`) but not in this phase
- Meta Cloud API provider — interface designed for it, implementation later
- Rate limiting / retry policy — caller's responsibility for now; a wrapper provider (`RetryingProvider`) can be added without touching anything else
