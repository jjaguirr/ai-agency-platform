# WhatsApp Provider Abstraction — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a provider-agnostic `WhatsAppChannel` extending `BaseCommunicationChannel`, with a Twilio concrete provider, in-memory message store, per-customer config, and a webhook server — all testable without live APIs or Docker services.

**Architecture:** `WhatsAppChannel` delegates all provider-specific I/O (send, parse webhook, validate signature, fetch status) to a `WhatsAppProvider` Protocol. Twilio implemented via `httpx` (no SDK). Message logging via `MessageStore` Protocol with in-memory default. Webhook server validates signatures *before* parsing, routes per customer via path param.

**Tech Stack:** Python 3.10+, `httpx` (async HTTP), `fastapi` (webhook server), `pytest` + `pytest-asyncio` (auto mode) + `unittest.mock` + `httpx.MockTransport`.

**Reference:** Design doc at `docs/plans/2026-03-05-whatsapp-provider-abstraction-design.md`

**VCS:** This repo uses `jj` (colocated with git). All commits use `jj commit -m "..." <paths>`.

---

## Pre-Flight

Before starting, verify environment:

```bash
cd /Users/jose/Documents/Work/01-PROMETHEUS/tasks-ai-agency-platform/02/model_a
python -c "import httpx, fastapi, pytest; print('deps OK')"
```

Expected: `deps OK`. If imports fail, run `pip install -e ".[dev]"`.

**Note on pytest config:** `pyproject.toml` sets `--cov-fail-under=80` on full runs. When running individual test files during TDD, use `--no-cov` to skip coverage enforcement:

```bash
pytest tests/unit/test_whatsapp_store.py --no-cov -v
```

**Note on conftest:** `tests/conftest.py` imports `ExecutiveAssistant` at module level. If that import fails, ALL tests fail on collection. It should work with deps installed — but if it breaks, don't debug it; that's pre-existing.

---

## Task 1: Provider Protocol & Result Dataclasses

No tests — this is pure type definitions. The protocol is structural; tests come when concrete implementations use it.

**Files:**
- Create: `src/communication/whatsapp/__init__.py`
- Create: `src/communication/whatsapp/provider.py`

**Step 1: Create package init**

```python
# src/communication/whatsapp/__init__.py
```
(Empty file — populated in Task 7 with exports.)

**Step 2: Write provider.py**

```python
# src/communication/whatsapp/provider.py
"""WhatsApp provider abstraction — the seam for swapping messaging backends."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Union


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
    raw: dict = field(default_factory=dict)


@dataclass
class IncomingMessage:
    provider_message_id: str
    from_number: str       # normalized E.164, no "whatsapp:" prefix
    to_number: str         # normalized E.164
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


# Union type for webhook parse results — a single webhook endpoint handles both
WebhookEvent = Union[IncomingMessage, StatusUpdate]


class WhatsAppSendError(Exception):
    """Raised when a provider fails to send a message."""
    def __init__(self, message: str, *, status_code: int | None = None,
                 error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class WhatsAppProvider(Protocol):
    """
    Provider abstraction for WhatsApp messaging backends.

    Implementations: TwilioWhatsAppProvider (this phase), MetaCloudAPIProvider (future).
    """
    provider_name: str

    async def send_text(self, to: str, body: str, from_: str) -> SendResult:
        """Send a text message. `to` and `from_` are E.164 (+14155551234)."""
        ...

    def parse_webhook(self, body: bytes, content_type: str) -> list[WebhookEvent]:
        """
        Parse raw webhook request body into zero or more events.
        Returns empty list for unparseable input (never raises).
        """
        ...

    def validate_signature(self, url: str, body: bytes,
                           headers: Mapping[str, str]) -> bool:
        """
        Validate webhook authenticity. `url` is the full URL the webhook
        was posted to. `headers` is case-sensitive dict of request headers.
        Returns False on any validation failure (never raises).
        """
        ...

    async def fetch_status(self, provider_message_id: str) -> MessageStatus:
        """Fetch current delivery status from provider API."""
        ...
```

**Step 3: Verify imports**

```bash
python -c "from src.communication.whatsapp.provider import WhatsAppProvider, MessageStatus, SendResult, IncomingMessage, StatusUpdate, WhatsAppSendError; print('OK')"
```
Expected: `OK`

**Step 4: Commit**

```bash
jj commit -m "feat(whatsapp): add provider protocol and result dataclasses" src/communication/whatsapp/
```

---

## Task 2: InMemoryMessageStore

**Files:**
- Create: `src/communication/whatsapp/store.py`
- Create: `tests/unit/test_whatsapp_store.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_whatsapp_store.py
"""Unit tests for InMemoryMessageStore."""
import pytest
from src.communication.whatsapp.store import InMemoryMessageStore, MessageRecord
from src.communication.whatsapp.provider import MessageStatus, SendResult, IncomingMessage


class TestInMemoryMessageStore:
    async def test_record_outbound_then_get_status(self):
        store = InMemoryMessageStore()
        result = SendResult(provider_message_id="SM123", status=MessageStatus.QUEUED)
        await store.record_outbound(
            customer_id="cust_a", conversation_id="conv_1",
            result=result, to="+15551234567", body="hello"
        )
        status = await store.get_status("SM123")
        assert status == MessageStatus.QUEUED

    async def test_update_status(self):
        store = InMemoryMessageStore()
        result = SendResult(provider_message_id="SM456", status=MessageStatus.QUEUED)
        await store.record_outbound("cust_a", "conv_1", result, "+15551234567", "hi")
        await store.update_status("SM456", MessageStatus.DELIVERED)
        assert await store.get_status("SM456") == MessageStatus.DELIVERED

    async def test_update_status_unknown_id_creates_entry(self):
        # Status callbacks can arrive for messages we didn't track (e.g. after restart).
        store = InMemoryMessageStore()
        await store.update_status("SM_unknown", MessageStatus.READ)
        assert await store.get_status("SM_unknown") == MessageStatus.READ

    async def test_get_status_unknown_returns_none(self):
        store = InMemoryMessageStore()
        assert await store.get_status("nonexistent") is None

    async def test_record_inbound(self):
        store = InMemoryMessageStore()
        msg = IncomingMessage(
            provider_message_id="SM_in_1",
            from_number="+15551234567",
            to_number="+14155238886",
            body="hello from user",
        )
        await store.record_inbound("cust_a", "conv_1", msg)
        # Inbound messages are recorded but have no delivery status to track.
        # Verify the conversation log captured it.
        records = store.get_conversation_log("conv_1")
        assert len(records) == 1
        assert records[0].direction == "inbound"
        assert records[0].body == "hello from user"
        assert records[0].provider_message_id == "SM_in_1"

    async def test_outbound_appears_in_conversation_log(self):
        store = InMemoryMessageStore()
        result = SendResult(provider_message_id="SM_out_1", status=MessageStatus.SENT)
        await store.record_outbound("cust_a", "conv_1", result, "+15551234567", "reply text")
        records = store.get_conversation_log("conv_1")
        assert len(records) == 1
        assert records[0].direction == "outbound"
        assert records[0].body == "reply text"
        assert records[0].provider_message_id == "SM_out_1"
        assert records[0].customer_id == "cust_a"

    def test_get_conversation_log_unknown_returns_empty(self):
        store = InMemoryMessageStore()
        assert store.get_conversation_log("nope") == []
```

**Step 2: Run tests — verify they fail**

```bash
pytest tests/unit/test_whatsapp_store.py --no-cov -v
```
Expected: `ModuleNotFoundError: No module named 'src.communication.whatsapp.store'` or `ImportError`

**Step 3: Write minimal implementation**

```python
# src/communication/whatsapp/store.py
"""Message store protocol and in-memory default implementation."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .provider import MessageStatus, SendResult, IncomingMessage


@dataclass
class MessageRecord:
    provider_message_id: str
    conversation_id: str
    customer_id: str
    direction: str          # "inbound" | "outbound"
    body: str
    counterparty: str       # E.164 phone number of the other party
    timestamp: datetime = field(default_factory=datetime.now)


class MessageStore(Protocol):
    async def record_outbound(self, customer_id: str, conversation_id: str,
                              result: SendResult, to: str, body: str) -> None: ...

    async def record_inbound(self, customer_id: str, conversation_id: str,
                             msg: IncomingMessage) -> None: ...

    async def update_status(self, provider_message_id: str,
                            status: MessageStatus) -> None: ...

    async def get_status(self, provider_message_id: str) -> MessageStatus | None: ...


class InMemoryMessageStore:
    """
    Default message store. Zero external dependencies.
    Unbounded in-memory — production should inject a DB-backed implementation.
    """

    def __init__(self) -> None:
        self._status: dict[str, MessageStatus] = {}
        self._log: dict[str, list[MessageRecord]] = {}

    async def record_outbound(self, customer_id: str, conversation_id: str,
                              result: SendResult, to: str, body: str) -> None:
        self._status[result.provider_message_id] = result.status
        self._log.setdefault(conversation_id, []).append(MessageRecord(
            provider_message_id=result.provider_message_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            direction="outbound",
            body=body,
            counterparty=to,
        ))

    async def record_inbound(self, customer_id: str, conversation_id: str,
                             msg: IncomingMessage) -> None:
        self._log.setdefault(conversation_id, []).append(MessageRecord(
            provider_message_id=msg.provider_message_id,
            conversation_id=conversation_id,
            customer_id=customer_id,
            direction="inbound",
            body=msg.body,
            counterparty=msg.from_number,
        ))

    async def update_status(self, provider_message_id: str,
                            status: MessageStatus) -> None:
        self._status[provider_message_id] = status

    async def get_status(self, provider_message_id: str) -> MessageStatus | None:
        return self._status.get(provider_message_id)

    def get_conversation_log(self, conversation_id: str) -> list[MessageRecord]:
        """Synchronous accessor for testing & manager-level queries."""
        return list(self._log.get(conversation_id, []))
```

**Step 4: Run tests — verify they pass**

```bash
pytest tests/unit/test_whatsapp_store.py --no-cov -v
```
Expected: `7 passed`

**Step 5: Commit**

```bash
jj commit -m "feat(whatsapp): add MessageStore protocol and in-memory implementation" src/communication/whatsapp/store.py tests/unit/test_whatsapp_store.py
```

---

## Task 3: WhatsAppConfig

**Files:**
- Create: `src/communication/whatsapp/config.py`
- Create: `tests/unit/test_whatsapp_config.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_whatsapp_config.py
"""Unit tests for WhatsAppConfig."""
import pytest
from src.communication.whatsapp.config import WhatsAppConfig


class TestWhatsAppConfigFromEnv:
    def test_from_env_twilio(self, monkeypatch):
        monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
        monkeypatch.setenv("WHATSAPP_FROM_NUMBER", "+14155238886")
        monkeypatch.setenv("WHATSAPP_WEBHOOK_BASE_URL", "https://example.com")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest123")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret_token_abc")

        cfg = WhatsAppConfig.from_env()

        assert cfg.provider == "twilio"
        assert cfg.from_number == "+14155238886"
        assert cfg.webhook_base_url == "https://example.com"
        assert cfg.credentials == {
            "account_sid": "ACtest123",
            "auth_token": "secret_token_abc",
        }

    def test_from_env_defaults_when_unset(self, monkeypatch):
        # Clear any WHATSAPP_* / TWILIO_* from environment
        for var in ("WHATSAPP_PROVIDER", "WHATSAPP_FROM_NUMBER",
                    "WHATSAPP_WEBHOOK_BASE_URL", "TWILIO_ACCOUNT_SID",
                    "TWILIO_AUTH_TOKEN"):
            monkeypatch.delenv(var, raising=False)

        cfg = WhatsAppConfig.from_env()

        assert cfg.provider == "twilio"
        assert cfg.from_number == ""
        assert cfg.webhook_base_url == ""
        assert cfg.credentials == {"account_sid": "", "auth_token": ""}

    def test_from_env_custom_prefix(self, monkeypatch):
        monkeypatch.setenv("TENANT_A_PROVIDER", "twilio")
        monkeypatch.setenv("TENANT_A_FROM_NUMBER", "+19998887777")
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtenant_a")
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok_a")

        cfg = WhatsAppConfig.from_env(prefix="TENANT_A_")

        assert cfg.from_number == "+19998887777"
        assert cfg.credentials["account_sid"] == "ACtenant_a"


class TestWhatsAppConfigFromDict:
    def test_from_dict_full(self):
        cfg = WhatsAppConfig.from_dict({
            "provider": "twilio",
            "from_number": "+14155238886",
            "credentials": {"account_sid": "AC1", "auth_token": "tok1"},
            "webhook_base_url": "https://x.example.com",
        })
        assert cfg.provider == "twilio"
        assert cfg.from_number == "+14155238886"
        assert cfg.credentials == {"account_sid": "AC1", "auth_token": "tok1"}
        assert cfg.webhook_base_url == "https://x.example.com"

    def test_from_dict_missing_optional(self):
        cfg = WhatsAppConfig.from_dict({
            "provider": "twilio",
            "from_number": "+14155238886",
            "credentials": {"account_sid": "AC1", "auth_token": "tok1"},
        })
        assert cfg.webhook_base_url == ""

    def test_webhook_url_for_customer(self):
        cfg = WhatsAppConfig(
            provider="twilio",
            from_number="+14155238886",
            credentials={"account_sid": "AC1", "auth_token": "tok1"},
            webhook_base_url="https://api.example.com",
        )
        assert cfg.webhook_url_for("cust_abc") == "https://api.example.com/webhook/whatsapp/cust_abc"
```

**Step 2: Run tests — verify fail**

```bash
pytest tests/unit/test_whatsapp_config.py --no-cov -v
```
Expected: `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/communication/whatsapp/config.py
"""Per-customer WhatsApp configuration following src/utils/config.py convention."""
import os
from dataclasses import dataclass, field


@dataclass
class WhatsAppConfig:
    provider: str                               # "twilio", "meta_cloud", ...
    from_number: str                            # E.164 WhatsApp sender number
    credentials: dict[str, str] = field(default_factory=dict)
    webhook_base_url: str = ""

    def webhook_url_for(self, customer_id: str) -> str:
        base = self.webhook_base_url.rstrip("/")
        return f"{base}/webhook/whatsapp/{customer_id}"

    @classmethod
    def from_env(cls, prefix: str = "WHATSAPP_") -> "WhatsAppConfig":
        provider = os.getenv(f"{prefix}PROVIDER", "twilio")
        from_number = os.getenv(f"{prefix}FROM_NUMBER", "")
        webhook_base_url = os.getenv(f"{prefix}WEBHOOK_BASE_URL", "")

        credentials: dict[str, str] = {}
        if provider == "twilio":
            credentials = {
                "account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
                "auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
            }

        return cls(
            provider=provider,
            from_number=from_number,
            credentials=credentials,
            webhook_base_url=webhook_base_url,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "WhatsAppConfig":
        return cls(
            provider=d["provider"],
            from_number=d["from_number"],
            credentials=dict(d.get("credentials", {})),
            webhook_base_url=d.get("webhook_base_url", ""),
        )
```

**Step 4: Run tests — verify pass**

```bash
pytest tests/unit/test_whatsapp_config.py --no-cov -v
```
Expected: `6 passed`

**Step 5: Commit**

```bash
jj commit -m "feat(whatsapp): add WhatsAppConfig with env/dict loaders" src/communication/whatsapp/config.py tests/unit/test_whatsapp_config.py
```

---

## Task 4: TwilioWhatsAppProvider — Signature Validation

This is the security-critical piece. Twilio's algorithm: take the full webhook URL, sort POST form params by key, concatenate `key + value` to the URL (no separators), HMAC-SHA1 with auth_token, base64-encode, compare to `X-Twilio-Signature` header.

**Files:**
- Create: `src/communication/whatsapp/providers/__init__.py`
- Create: `src/communication/whatsapp/providers/twilio.py`
- Create: `tests/unit/test_whatsapp_provider_twilio.py`

**Step 1: Write failing signature tests**

```python
# tests/unit/test_whatsapp_provider_twilio.py
"""Unit tests for TwilioWhatsAppProvider."""
import base64
import hashlib
import hmac
from urllib.parse import urlencode

import httpx
import pytest

from src.communication.whatsapp.providers.twilio import TwilioWhatsAppProvider
from src.communication.whatsapp.provider import (
    MessageStatus, SendResult, IncomingMessage, StatusUpdate, WhatsAppSendError
)


# --- Helpers ---------------------------------------------------------------

def _twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Compute the Twilio signature per their official algorithm."""
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("ascii")


def _form_body(params: dict[str, str]) -> bytes:
    return urlencode(params).encode("utf-8")


# --- Signature validation tests -------------------------------------------

class TestTwilioSignatureValidation:
    AUTH_TOKEN = "test_auth_token_12345"
    WEBHOOK_URL = "https://example.com/webhook/whatsapp/cust_a"

    def _provider(self) -> TwilioWhatsAppProvider:
        return TwilioWhatsAppProvider(
            account_sid="ACtest", auth_token=self.AUTH_TOKEN
        )

    def test_valid_signature_accepted(self):
        params = {
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "hello world",
            "MessageSid": "SM1234567890abcdef",
        }
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)
        body = _form_body(params)

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=body,
            headers={"X-Twilio-Signature": sig},
        )
        assert result is True

    def test_tampered_body_rejected(self):
        params = {"From": "whatsapp:+15551234567", "Body": "original"}
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)
        tampered = {"From": "whatsapp:+15551234567", "Body": "tampered"}

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(tampered),
            headers={"X-Twilio-Signature": sig},
        )
        assert result is False

    def test_wrong_url_rejected(self):
        params = {"Body": "hello"}
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)

        result = self._provider().validate_signature(
            url="https://evil.example.com/webhook", body=_form_body(params),
            headers={"X-Twilio-Signature": sig},
        )
        assert result is False

    def test_missing_signature_header_rejected(self):
        params = {"Body": "hello"}
        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(params), headers={},
        )
        assert result is False

    def test_wrong_auth_token_rejected(self):
        params = {"Body": "hello"}
        sig = _twilio_signature("different_token", self.WEBHOOK_URL, params)

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(params),
            headers={"X-Twilio-Signature": sig},
        )
        assert result is False

    def test_case_insensitive_header_lookup(self):
        params = {"Body": "hello"}
        sig = _twilio_signature(self.AUTH_TOKEN, self.WEBHOOK_URL, params)

        result = self._provider().validate_signature(
            url=self.WEBHOOK_URL, body=_form_body(params),
            headers={"x-twilio-signature": sig},  # lowercase
        )
        assert result is True
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py::TestTwilioSignatureValidation --no-cov -v
```
Expected: `ModuleNotFoundError`

**Step 3: Implement signature validation + skeleton**

```python
# src/communication/whatsapp/providers/__init__.py
```
(Empty.)

```python
# src/communication/whatsapp/providers/twilio.py
"""Twilio WhatsApp provider — httpx-based, no SDK dependency."""
import base64
import hashlib
import hmac
from typing import Mapping
from urllib.parse import parse_qsl

import httpx

from ..provider import (
    IncomingMessage, MediaItem, MessageStatus, SendResult,
    StatusUpdate, WebhookEvent, WhatsAppSendError,
)


_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

_STATUS_MAP = {
    "queued": MessageStatus.QUEUED,
    "accepted": MessageStatus.QUEUED,
    "sending": MessageStatus.QUEUED,
    "sent": MessageStatus.SENT,
    "delivered": MessageStatus.DELIVERED,
    "read": MessageStatus.READ,
    "failed": MessageStatus.FAILED,
    "undelivered": MessageStatus.FAILED,
}


def _normalize_phone(raw: str) -> str:
    return raw.removeprefix("whatsapp:")


class TwilioWhatsAppProvider:
    provider_name = "twilio"

    def __init__(self, account_sid: str, auth_token: str,
                 http_client: httpx.AsyncClient | None = None):
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._http = http_client or httpx.AsyncClient(
            auth=(account_sid, auth_token), timeout=10.0
        )
        self._messages_url = f"{_TWILIO_API_BASE}/Accounts/{account_sid}/Messages.json"

    # -- Signature validation ----------------------------------------------

    def validate_signature(self, url: str, body: bytes,
                           headers: Mapping[str, str]) -> bool:
        sig = self._find_header(headers, "X-Twilio-Signature")
        if not sig:
            return False
        try:
            params = dict(parse_qsl(body.decode("utf-8"), keep_blank_values=True))
        except (UnicodeDecodeError, ValueError):
            return False
        expected = self._compute_signature(url, params)
        return hmac.compare_digest(expected, sig)

    def _compute_signature(self, url: str, params: dict[str, str]) -> str:
        s = url
        for key in sorted(params.keys()):
            s += key + params[key]
        mac = hmac.new(self._auth_token.encode("utf-8"),
                       s.encode("utf-8"), hashlib.sha1)
        return base64.b64encode(mac.digest()).decode("ascii")

    @staticmethod
    def _find_header(headers: Mapping[str, str], name: str) -> str | None:
        lname = name.lower()
        for k, v in headers.items():
            if k.lower() == lname:
                return v
        return None

    # -- Stubs for later tasks ---------------------------------------------

    async def send_text(self, to: str, body: str, from_: str) -> SendResult:
        raise NotImplementedError

    def parse_webhook(self, body: bytes, content_type: str) -> list[WebhookEvent]:
        raise NotImplementedError

    async def fetch_status(self, provider_message_id: str) -> MessageStatus:
        raise NotImplementedError
```

**Step 4: Run — verify pass**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py::TestTwilioSignatureValidation --no-cov -v
```
Expected: `6 passed`

**Step 5: Commit**

```bash
jj commit -m "feat(whatsapp): add Twilio provider with signature validation" src/communication/whatsapp/providers/ tests/unit/test_whatsapp_provider_twilio.py
```

---

## Task 5: TwilioWhatsAppProvider — Webhook Parsing

**Files:**
- Modify: `src/communication/whatsapp/providers/twilio.py`
- Modify: `tests/unit/test_whatsapp_provider_twilio.py` (append)

**Step 1: Write failing tests**

Append to `tests/unit/test_whatsapp_provider_twilio.py`:

```python
class TestTwilioParseWebhook:
    def _provider(self) -> TwilioWhatsAppProvider:
        return TwilioWhatsAppProvider(account_sid="ACtest", auth_token="tok")

    def test_parse_incoming_text_message(self):
        body = _form_body({
            "MessageSid": "SM1234567890abcdef",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "Hello I need help with my order",
            "ProfileName": "Jane Doe",
            "WaId": "15551234567",
            "NumMedia": "0",
        })
        events = self._provider().parse_webhook(
            body, "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, IncomingMessage)
        assert ev.provider_message_id == "SM1234567890abcdef"
        assert ev.from_number == "+15551234567"
        assert ev.to_number == "+14155238886"
        assert ev.body == "Hello I need help with my order"
        assert ev.profile_name == "Jane Doe"
        assert ev.media == []
        assert ev.raw["WaId"] == "15551234567"

    def test_parse_incoming_with_media(self):
        body = _form_body({
            "MessageSid": "SM_media_1",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "check this out",
            "NumMedia": "2",
            "MediaContentType0": "image/jpeg",
            "MediaUrl0": "https://api.twilio.com/media/abc",
            "MediaContentType1": "application/pdf",
            "MediaUrl1": "https://api.twilio.com/media/def",
        })
        events = self._provider().parse_webhook(
            body, "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, IncomingMessage)
        assert ev.body == "check this out"
        assert len(ev.media) == 2
        assert ev.media[0].content_type == "image/jpeg"
        assert ev.media[0].url == "https://api.twilio.com/media/abc"
        assert ev.media[1].content_type == "application/pdf"
        assert ev.media[1].url == "https://api.twilio.com/media/def"

    def test_parse_status_callback_delivered(self):
        body = _form_body({
            "MessageSid": "SM_out_99",
            "MessageStatus": "delivered",
            "To": "whatsapp:+15551234567",
            "From": "whatsapp:+14155238886",
        })
        events = self._provider().parse_webhook(
            body, "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, StatusUpdate)
        assert ev.provider_message_id == "SM_out_99"
        assert ev.status == MessageStatus.DELIVERED
        assert ev.error_code is None

    def test_parse_status_callback_failed(self):
        body = _form_body({
            "MessageSid": "SM_out_fail",
            "MessageStatus": "failed",
            "ErrorCode": "30008",
        })
        events = self._provider().parse_webhook(
            body, "application/x-www-form-urlencoded"
        )
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, StatusUpdate)
        assert ev.status == MessageStatus.FAILED
        assert ev.error_code == "30008"

    def test_parse_unknown_status_maps_to_unknown(self):
        body = _form_body({
            "MessageSid": "SM_weird",
            "MessageStatus": "some_future_twilio_status",
        })
        events = self._provider().parse_webhook(
            body, "application/x-www-form-urlencoded"
        )
        ev = events[0]
        assert isinstance(ev, StatusUpdate)
        assert ev.status == MessageStatus.UNKNOWN

    def test_parse_unparseable_returns_empty_list(self):
        events = self._provider().parse_webhook(b"\xff\xfe garbage", "text/plain")
        assert events == []

    def test_parse_missing_message_sid_returns_empty(self):
        body = _form_body({"Body": "no sid here"})
        events = self._provider().parse_webhook(
            body, "application/x-www-form-urlencoded"
        )
        assert events == []

    def test_parse_empty_body_returns_empty(self):
        events = self._provider().parse_webhook(b"", "application/x-www-form-urlencoded")
        assert events == []
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py::TestTwilioParseWebhook --no-cov -v
```
Expected: `NotImplementedError` failures.

**Step 3: Implement parse_webhook**

Replace the `parse_webhook` stub in `twilio.py`:

```python
    def parse_webhook(self, body: bytes, content_type: str) -> list[WebhookEvent]:
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            return []
        if not decoded:
            return []
        try:
            params = dict(parse_qsl(decoded, keep_blank_values=True))
        except ValueError:
            return []

        sid = params.get("MessageSid")
        if not sid:
            return []

        # Status callback: has MessageStatus but no Body
        if "MessageStatus" in params and "Body" not in params:
            raw_status = params.get("MessageStatus", "").lower()
            return [StatusUpdate(
                provider_message_id=sid,
                status=_STATUS_MAP.get(raw_status, MessageStatus.UNKNOWN),
                error_code=params.get("ErrorCode"),
                raw=params,
            )]

        # Incoming message
        num_media = int(params.get("NumMedia", "0") or "0")
        media = []
        for i in range(num_media):
            ctype = params.get(f"MediaContentType{i}")
            url = params.get(f"MediaUrl{i}")
            if ctype and url:
                media.append(MediaItem(content_type=ctype, url=url))

        return [IncomingMessage(
            provider_message_id=sid,
            from_number=_normalize_phone(params.get("From", "")),
            to_number=_normalize_phone(params.get("To", "")),
            body=params.get("Body", ""),
            profile_name=params.get("ProfileName"),
            media=media,
            raw=params,
        )]
```

**Step 4: Run — verify pass**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py::TestTwilioParseWebhook --no-cov -v
```
Expected: `8 passed`

**Step 5: Run signature tests again (regression check)**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py --no-cov -v
```
Expected: `14 passed`

**Step 6: Commit**

```bash
jj commit -m "feat(whatsapp): implement Twilio webhook parsing" src/communication/whatsapp/providers/twilio.py tests/unit/test_whatsapp_provider_twilio.py
```

---

## Task 6: TwilioWhatsAppProvider — send_text & fetch_status

**Files:**
- Modify: `src/communication/whatsapp/providers/twilio.py`
- Modify: `tests/unit/test_whatsapp_provider_twilio.py` (append)

**Step 1: Write failing tests**

Append to `tests/unit/test_whatsapp_provider_twilio.py`:

```python
class TestTwilioSendText:
    async def test_send_text_formats_request(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["auth"] = request.headers.get("authorization")
            captured["form"] = dict(parse_qsl(request.content.decode()))
            return httpx.Response(201, json={
                "sid": "SM_new_abc123", "status": "queued",
            })

        transport = httpx.MockTransport(handler)
        client = httpx.AsyncClient(transport=transport,
                                   auth=("ACtest", "tok"))
        provider = TwilioWhatsAppProvider(
            account_sid="ACtest", auth_token="tok", http_client=client
        )

        result = await provider.send_text(
            to="+15551234567", body="hello there", from_="+14155238886"
        )

        assert captured["method"] == "POST"
        assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages.json"
        assert captured["auth"] == "Basic QUN0ZXN0OnRvaw=="  # base64("ACtest:tok")
        assert captured["form"] == {
            "To": "whatsapp:+15551234567",
            "From": "whatsapp:+14155238886",
            "Body": "hello there",
        }
        assert result.provider_message_id == "SM_new_abc123"
        assert result.status == MessageStatus.QUEUED
        assert result.raw == {"sid": "SM_new_abc123", "status": "queued"}

    async def test_send_text_to_already_prefixed(self):
        """If caller passes 'whatsapp:+1...' don't double-prefix."""
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["form"] = dict(parse_qsl(request.content.decode()))
            return httpx.Response(201, json={"sid": "SM_x", "status": "sent"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   auth=("ACtest", "tok"))
        provider = TwilioWhatsAppProvider("ACtest", "tok", http_client=client)

        await provider.send_text(
            to="whatsapp:+15551234567", body="hi", from_="+14155238886"
        )
        assert captured["form"]["To"] == "whatsapp:+15551234567"

    async def test_send_text_raises_on_twilio_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={
                "code": 21211, "message": "Invalid 'To' Phone Number",
                "status": 400,
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   auth=("ACtest", "tok"))
        provider = TwilioWhatsAppProvider("ACtest", "tok", http_client=client)

        with pytest.raises(WhatsAppSendError) as exc_info:
            await provider.send_text(to="+1bad", body="x", from_="+1415")

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_code == "21211"
        assert "Invalid 'To' Phone Number" in str(exc_info.value)

    async def test_send_text_raises_on_5xx(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"message": "Service Unavailable"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   auth=("ACtest", "tok"))
        provider = TwilioWhatsAppProvider("ACtest", "tok", http_client=client)

        with pytest.raises(WhatsAppSendError) as exc_info:
            await provider.send_text(to="+15551234567", body="x", from_="+1415")
        assert exc_info.value.status_code == 503


class TestTwilioFetchStatus:
    async def test_fetch_status_parses_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert str(request.url) == "https://api.twilio.com/2010-04-01/Accounts/ACtest/Messages/SM_lookup_1.json"
            return httpx.Response(200, json={
                "sid": "SM_lookup_1", "status": "delivered",
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   auth=("ACtest", "tok"))
        provider = TwilioWhatsAppProvider("ACtest", "tok", http_client=client)

        status = await provider.fetch_status("SM_lookup_1")
        assert status == MessageStatus.DELIVERED

    async def test_fetch_status_not_found_returns_unknown(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"code": 20404, "message": "Not Found"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                   auth=("ACtest", "tok"))
        provider = TwilioWhatsAppProvider("ACtest", "tok", http_client=client)

        status = await provider.fetch_status("SM_nonexistent")
        assert status == MessageStatus.UNKNOWN
```

Also add `from urllib.parse import parse_qsl` to the test file's imports (already there? check — it's not, add it):

```python
from urllib.parse import urlencode, parse_qsl
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py::TestTwilioSendText tests/unit/test_whatsapp_provider_twilio.py::TestTwilioFetchStatus --no-cov -v
```
Expected: `NotImplementedError` failures.

**Step 3: Implement send_text & fetch_status**

Replace stubs in `twilio.py`:

```python
    async def send_text(self, to: str, body: str, from_: str) -> SendResult:
        to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
        from_wa = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"
        resp = await self._http.post(self._messages_url, data={
            "To": to_wa, "From": from_wa, "Body": body,
        })
        data = resp.json()
        if resp.status_code >= 400:
            raise WhatsAppSendError(
                data.get("message", f"Twilio returned {resp.status_code}"),
                status_code=resp.status_code,
                error_code=str(data["code"]) if "code" in data else None,
            )
        raw_status = data.get("status", "").lower()
        return SendResult(
            provider_message_id=data["sid"],
            status=_STATUS_MAP.get(raw_status, MessageStatus.UNKNOWN),
            raw=data,
        )

    async def fetch_status(self, provider_message_id: str) -> MessageStatus:
        url = f"{_TWILIO_API_BASE}/Accounts/{self._account_sid}/Messages/{provider_message_id}.json"
        resp = await self._http.get(url)
        if resp.status_code >= 400:
            return MessageStatus.UNKNOWN
        data = resp.json()
        raw_status = data.get("status", "").lower()
        return _STATUS_MAP.get(raw_status, MessageStatus.UNKNOWN)
```

**Step 4: Run — verify pass**

```bash
pytest tests/unit/test_whatsapp_provider_twilio.py --no-cov -v
```
Expected: `20 passed`

**Step 5: Commit**

```bash
jj commit -m "feat(whatsapp): implement Twilio send_text and fetch_status" src/communication/whatsapp/providers/twilio.py tests/unit/test_whatsapp_provider_twilio.py
```

---

## Task 7: Provider Registry

**Files:**
- Create: `src/communication/whatsapp/providers/_registry.py`
- Create: `tests/unit/test_whatsapp_provider_registry.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_whatsapp_provider_registry.py
"""Unit tests for provider registry."""
import pytest
from src.communication.whatsapp.providers._registry import (
    create_provider, PROVIDER_REGISTRY
)
from src.communication.whatsapp.providers.twilio import TwilioWhatsAppProvider


class TestProviderRegistry:
    def test_twilio_registered(self):
        assert "twilio" in PROVIDER_REGISTRY

    def test_create_twilio_provider(self):
        p = create_provider("twilio", {
            "account_sid": "ACtest", "auth_token": "tok123"
        })
        assert isinstance(p, TwilioWhatsAppProvider)
        assert p.provider_name == "twilio"

    def test_unknown_provider_raises_value_error(self):
        with pytest.raises(ValueError) as exc_info:
            create_provider("nonexistent_provider", {})
        assert "nonexistent_provider" in str(exc_info.value)
        assert "Unknown WhatsApp provider" in str(exc_info.value)

    def test_missing_credential_raises_key_error(self):
        with pytest.raises(KeyError):
            create_provider("twilio", {"account_sid": "ACtest"})  # no auth_token
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_whatsapp_provider_registry.py --no-cov -v
```
Expected: `ModuleNotFoundError`

**Step 3: Implement**

```python
# src/communication/whatsapp/providers/_registry.py
"""Provider factory — maps config name to constructor."""
from typing import Callable

from ..provider import WhatsAppProvider
from .twilio import TwilioWhatsAppProvider


PROVIDER_REGISTRY: dict[str, Callable[[dict], WhatsAppProvider]] = {
    "twilio": lambda creds: TwilioWhatsAppProvider(
        account_sid=creds["account_sid"],
        auth_token=creds["auth_token"],
    ),
}


def create_provider(provider_name: str, credentials: dict) -> WhatsAppProvider:
    if provider_name not in PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown WhatsApp provider: {provider_name!r}. "
            f"Available: {list(PROVIDER_REGISTRY.keys())}"
        )
    return PROVIDER_REGISTRY[provider_name](credentials)
```

**Step 4: Run — verify pass**

```bash
pytest tests/unit/test_whatsapp_provider_registry.py --no-cov -v
```
Expected: `4 passed`

**Step 5: Commit**

```bash
jj commit -m "feat(whatsapp): add provider registry factory" src/communication/whatsapp/providers/_registry.py tests/unit/test_whatsapp_provider_registry.py
```

---

## Task 8: WhatsAppChannel

**Files:**
- Create: `src/communication/whatsapp/channel.py`
- Modify: `tests/unit/test_whatsapp_channel.py` (replace stub content)

**Step 1: Write failing tests (replace the skip-stub file)**

```python
# tests/unit/test_whatsapp_channel.py
"""Unit tests for WhatsAppChannel."""
from unittest.mock import AsyncMock, Mock, call

import pytest

from src.communication.base_channel import ChannelType, BaseMessage
from src.communication.whatsapp.channel import WhatsAppChannel
from src.communication.whatsapp.provider import (
    MessageStatus, SendResult, IncomingMessage, StatusUpdate, WhatsAppProvider,
)
from src.communication.whatsapp.store import InMemoryMessageStore


# --- Fixtures --------------------------------------------------------------

def _mock_provider() -> Mock:
    p = Mock(spec=WhatsAppProvider)
    p.provider_name = "mock"
    p.send_text = AsyncMock(return_value=SendResult(
        provider_message_id="SM_mock_123", status=MessageStatus.QUEUED
    ))
    p.fetch_status = AsyncMock(return_value=MessageStatus.DELIVERED)
    p.validate_signature = Mock(return_value=True)
    return p


def _channel(provider: Mock | None = None, store=None,
             from_number: str = "+14155238886",
             customer_id: str = "cust_test") -> WhatsAppChannel:
    return WhatsAppChannel(
        customer_id=customer_id,
        config={"from_number": from_number, "webhook_url": "https://ex.com/wh"},
        provider=provider or _mock_provider(),
        store=store,
    )


# --- Tests -----------------------------------------------------------------

class TestChannelBasics:
    def test_channel_type(self):
        ch = _channel()
        assert ch.channel_type == ChannelType.WHATSAPP

    async def test_initialize_sets_flag(self):
        ch = _channel()
        assert ch.is_initialized is False
        result = await ch.initialize()
        assert result is True
        assert ch.is_initialized is True


class TestSendMessage:
    async def test_delegates_to_provider(self):
        prov = _mock_provider()
        ch = _channel(provider=prov, from_number="+14155238886")

        await ch.send_message("+15551234567", "hello world")

        prov.send_text.assert_called_once_with(
            to="+15551234567", body="hello world", from_="+14155238886"
        )

    async def test_returns_provider_message_id(self):
        ch = _channel()
        msg_id = await ch.send_message("+15551234567", "hi")
        assert msg_id == "SM_mock_123"

    async def test_records_to_store(self):
        store = InMemoryMessageStore()
        ch = _channel(store=store, customer_id="cust_a")

        await ch.send_message("+15551234567", "outbound text")

        status = await store.get_status("SM_mock_123")
        assert status == MessageStatus.QUEUED
        # Conversation log has the record
        conv_id = ch._conversation_id_for("+15551234567")
        log = store.get_conversation_log(conv_id)
        assert len(log) == 1
        assert log[0].direction == "outbound"
        assert log[0].body == "outbound text"
        assert log[0].counterparty == "+15551234567"
        assert log[0].customer_id == "cust_a"

    async def test_send_without_store_still_works(self):
        # Channel with no explicit store uses InMemoryMessageStore default.
        prov = _mock_provider()
        ch = WhatsAppChannel(
            customer_id="c", config={"from_number": "+1"},
            provider=prov, store=None,
        )
        msg_id = await ch.send_message("+15551234567", "x")
        assert msg_id == "SM_mock_123"


class TestHandleIncomingMessage:
    async def test_builds_base_message(self):
        ch = _channel(customer_id="cust_xyz")
        incoming = {
            "provider_message_id": "SM_in_1",
            "from_number": "+15551234567",
            "to_number": "+14155238886",
            "body": "I need help",
            "profile_name": "Jane",
            "media": [],
            "raw": {"WaId": "15551234567"},
        }

        msg = await ch.handle_incoming_message(incoming)

        assert isinstance(msg, BaseMessage)
        assert msg.content == "I need help"
        assert msg.from_number == "+15551234567"
        assert msg.to_number == "+14155238886"
        assert msg.channel == ChannelType.WHATSAPP
        assert msg.message_id == "SM_in_1"
        assert msg.customer_id == "cust_xyz"
        assert msg.metadata == {"WaId": "15551234567"}
        # conversation_id is deterministic hash — assert exact value
        expected_conv_id = ch._conversation_id_for("+15551234567")
        assert msg.conversation_id == expected_conv_id


class TestConversationId:
    def test_deterministic_same_inputs(self):
        ch1 = _channel(customer_id="cust_a")
        ch2 = _channel(customer_id="cust_a")
        assert ch1._conversation_id_for("+15551234567") == ch2._conversation_id_for("+15551234567")

    def test_different_phone_different_id(self):
        ch = _channel(customer_id="cust_a")
        id_1 = ch._conversation_id_for("+15551234567")
        id_2 = ch._conversation_id_for("+15559999999")
        assert id_1 != id_2

    def test_different_customer_different_id(self):
        ch_a = _channel(customer_id="cust_a")
        ch_b = _channel(customer_id="cust_b")
        assert ch_a._conversation_id_for("+15551234567") != ch_b._conversation_id_for("+15551234567")

    def test_id_format(self):
        ch = _channel()
        conv_id = ch._conversation_id_for("+15551234567")
        assert len(conv_id) == 16
        assert all(c in "0123456789abcdef" for c in conv_id)


class TestStatusCallback:
    async def test_updates_store(self):
        store = InMemoryMessageStore()
        ch = _channel(store=store)

        await ch.handle_status_callback(StatusUpdate(
            provider_message_id="SM_out_42",
            status=MessageStatus.DELIVERED,
        ))

        assert await store.get_status("SM_out_42") == MessageStatus.DELIVERED


class TestGetMessageStatus:
    async def test_prefers_store(self):
        store = InMemoryMessageStore()
        await store.update_status("SM_known", MessageStatus.READ)
        prov = _mock_provider()
        ch = _channel(provider=prov, store=store)

        result = await ch.get_message_status("SM_known")

        assert result["message_id"] == "SM_known"
        assert result["status"] == "read"
        assert prov.fetch_status.call_count == 0

    async def test_falls_back_to_provider(self):
        store = InMemoryMessageStore()  # empty
        prov = _mock_provider()
        prov.fetch_status = AsyncMock(return_value=MessageStatus.SENT)
        ch = _channel(provider=prov, store=store)

        result = await ch.get_message_status("SM_unknown")

        assert result["status"] == "sent"
        prov.fetch_status.assert_called_once_with("SM_unknown")


class TestValidateWebhookSignature:
    async def test_delegates_to_provider(self):
        prov = _mock_provider()
        ch = _channel(provider=prov)

        result = await ch.validate_webhook_signature("raw_body", "sig_abc")

        assert result is True
        prov.validate_signature.assert_called_once_with(
            url="https://ex.com/wh",
            body=b"raw_body",
            headers={"X-Twilio-Signature": "sig_abc"},
        )

    async def test_returns_provider_result_false(self):
        prov = _mock_provider()
        prov.validate_signature = Mock(return_value=False)
        ch = _channel(provider=prov)
        assert await ch.validate_webhook_signature("body", "bad_sig") is False
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_whatsapp_channel.py --no-cov -v
```
Expected: `ModuleNotFoundError` for `whatsapp.channel`

**Step 3: Implement channel**

```python
# src/communication/whatsapp/channel.py
"""WhatsApp channel — pure I/O adapter, provider-agnostic."""
import hashlib
from datetime import datetime
from typing import Any

from ..base_channel import BaseCommunicationChannel, BaseMessage, ChannelType
from .provider import MessageStatus, StatusUpdate, WhatsAppProvider
from .store import InMemoryMessageStore, MessageStore


class WhatsAppChannel(BaseCommunicationChannel):
    """
    WhatsApp implementation of BaseCommunicationChannel.

    Delegates all provider-specific I/O (send, parse, validate) to an
    injected WhatsAppProvider. No direct Twilio/Redis/Postgres/EA imports.
    """

    def __init__(self, customer_id: str, config: dict[str, Any] | None = None, *,
                 provider: WhatsAppProvider,
                 store: MessageStore | None = None):
        super().__init__(customer_id, config)
        self._provider = provider
        self._store: MessageStore = store or InMemoryMessageStore()
        self._from_number: str = (config or {}).get("from_number", "")
        self._webhook_url: str = (config or {}).get("webhook_url", "")

    @property
    def provider(self) -> WhatsAppProvider:
        return self._provider

    @property
    def store(self) -> MessageStore:
        return self._store

    def _get_channel_type(self) -> ChannelType:
        return ChannelType.WHATSAPP

    async def initialize(self) -> bool:
        self.is_initialized = True
        return True

    async def send_message(self, to: str, content: str, **kwargs) -> str:
        result = await self._provider.send_text(
            to=to, body=content, from_=self._from_number
        )
        conv_id = self._conversation_id_for(to)
        await self._store.record_outbound(
            customer_id=self.customer_id,
            conversation_id=conv_id,
            result=result, to=to, body=content,
        )
        return result.provider_message_id

    async def handle_incoming_message(self, message_data: dict[str, Any]) -> BaseMessage:
        """
        Convert a parsed IncomingMessage (as dict) into BaseMessage.
        The webhook server calls provider.parse_webhook() first, then passes
        asdict(IncomingMessage) here.
        """
        from_number = message_data["from_number"]
        conv_id = self._conversation_id_for(from_number)
        return BaseMessage(
            content=message_data["body"],
            from_number=from_number,
            to_number=message_data["to_number"],
            channel=ChannelType.WHATSAPP,
            message_id=message_data["provider_message_id"],
            conversation_id=conv_id,
            timestamp=datetime.now(),
            customer_id=self.customer_id,
            metadata=message_data.get("raw", {}),
        )

    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        """
        BaseCommunicationChannel signature is (payload: str, signature: str).
        Provider needs richer context — we supply stored webhook_url and
        reconstruct the header. The webhook server should prefer calling
        provider.validate_signature() directly for more precision.
        """
        body = payload.encode("utf-8") if isinstance(payload, str) else payload
        return self._provider.validate_signature(
            url=self._webhook_url,
            body=body,
            headers={"X-Twilio-Signature": signature},
        )

    async def handle_status_callback(self, update: StatusUpdate) -> None:
        await self._store.update_status(update.provider_message_id, update.status)

    async def get_message_status(self, message_id: str) -> dict[str, Any]:
        status = await self._store.get_status(message_id)
        if status is None:
            status = await self._provider.fetch_status(message_id)
        return {
            "message_id": message_id,
            "status": status.value,
            "timestamp": datetime.now().isoformat(),
        }

    def _conversation_id_for(self, phone_number: str) -> str:
        key = f"{self.customer_id}:{phone_number}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]
```

**Step 4: Run — verify pass**

```bash
pytest tests/unit/test_whatsapp_channel.py --no-cov -v
```
Expected: `17 passed`

**Step 5: Commit**

```bash
jj commit -m "feat(whatsapp): implement provider-agnostic WhatsAppChannel" src/communication/whatsapp/channel.py tests/unit/test_whatsapp_channel.py
```

---

## Task 9: Package Exports + Backward-Compat Shim

**Files:**
- Modify: `src/communication/whatsapp/__init__.py`
- Modify: `src/communication/whatsapp_channel.py` (old file → thin re-export)
- Modify: `src/communication/__init__.py`

**Step 1: Populate whatsapp/__init__.py**

```python
# src/communication/whatsapp/__init__.py
"""WhatsApp channel with swappable provider backends."""
from .channel import WhatsAppChannel
from .config import WhatsAppConfig
from .provider import (
    IncomingMessage, MediaItem, MessageStatus, SendResult,
    StatusUpdate, WebhookEvent, WhatsAppProvider, WhatsAppSendError,
)
from .providers._registry import PROVIDER_REGISTRY, create_provider
from .store import InMemoryMessageStore, MessageRecord, MessageStore

__all__ = [
    "WhatsAppChannel",
    "WhatsAppConfig",
    "WhatsAppProvider",
    "IncomingMessage",
    "StatusUpdate",
    "SendResult",
    "MessageStatus",
    "MediaItem",
    "WebhookEvent",
    "WhatsAppSendError",
    "MessageStore",
    "InMemoryMessageStore",
    "MessageRecord",
    "create_provider",
    "PROVIDER_REGISTRY",
]
```

**Step 2: Replace old whatsapp_channel.py with shim**

The old file has 543 lines of Twilio-coupled code. The only external importers are:
- `src/communication/__init__.py` — imports `WhatsAppChannel`, `WhatsAppMessage`
- `src/communication/webhook_server.py` — will be rewritten in Task 10
- `src/communication/whatsapp_manager.py` — will be refactored in Task 11

Replace `src/communication/whatsapp_channel.py` entirely:

```python
# src/communication/whatsapp_channel.py
"""
Backward-compat shim. All implementation moved to src/communication/whatsapp/.

Old: WhatsAppChannel was Twilio-hardcoded with direct DB/Redis deps.
New: WhatsAppChannel delegates to a WhatsAppProvider; see whatsapp/channel.py.
"""
from .whatsapp.channel import WhatsAppChannel
from .whatsapp.provider import IncomingMessage as WhatsAppMessage

__all__ = ["WhatsAppChannel", "WhatsAppMessage"]
```

**Step 3: Update communication/__init__.py**

The existing file imports `WhatsAppChannel, WhatsAppMessage` from `.whatsapp_channel`. With the shim in place that still works, but let's also expose the new package:

```python
# src/communication/__init__.py
"""
AI Agency Platform - Communication Channels Module
Multi-channel communication system for Executive Assistant interactions
"""

from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType
from .whatsapp_channel import WhatsAppChannel, WhatsAppMessage

__all__ = [
    "BaseCommunicationChannel",
    "BaseMessage",
    "ChannelType",
    "WhatsAppChannel",
    "WhatsAppMessage",
]
```

**Step 4: Verify imports**

```bash
python -c "from src.communication import WhatsAppChannel, WhatsAppMessage, ChannelType; print('shim OK')"
python -c "from src.communication.whatsapp import WhatsAppChannel, create_provider; print('pkg OK')"
```
Expected: `shim OK` then `pkg OK`

**Step 5: Commit**

```bash
jj commit -m "refactor(whatsapp): replace legacy channel with provider-abstraction re-export" src/communication/__init__.py src/communication/whatsapp_channel.py src/communication/whatsapp/__init__.py
```

---

## Task 10: WhatsAppManager Refactor

The existing `whatsapp_manager.py` has hardcoded DB/Redis creds and Twilio-specific env vars. We keep its role (multi-tenant config storage + channel caching) but decouple from Twilio and make DB optional.

**Files:**
- Modify: `src/communication/whatsapp_manager.py` (full rewrite)
- Create: `tests/unit/test_whatsapp_manager.py`

**Step 1: Write failing tests**

```python
# tests/unit/test_whatsapp_manager.py
"""Unit tests for WhatsAppManager."""
import pytest
from unittest.mock import AsyncMock, Mock

from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.whatsapp import WhatsAppConfig, WhatsAppChannel


class TestWhatsAppManagerRegistration:
    def test_register_and_get_config(self):
        mgr = WhatsAppManager()
        cfg = WhatsAppConfig(
            provider="twilio", from_number="+14155238886",
            credentials={"account_sid": "ACtest", "auth_token": "tok"},
        )
        mgr.register_customer("cust_a", cfg)
        assert mgr.get_config("cust_a") == cfg

    def test_get_config_unknown_returns_none(self):
        mgr = WhatsAppManager()
        assert mgr.get_config("unknown") is None

    def test_has_customer(self):
        mgr = WhatsAppManager()
        assert mgr.has_customer("x") is False
        mgr.register_customer("x", WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "a", "auth_token": "b"},
        ))
        assert mgr.has_customer("x") is True


class TestWhatsAppManagerChannelBuilding:
    async def test_get_channel_builds_from_config(self):
        mgr = WhatsAppManager()
        mgr.register_customer("cust_a", WhatsAppConfig(
            provider="twilio", from_number="+14155238886",
            credentials={"account_sid": "ACtest", "auth_token": "tok"},
            webhook_base_url="https://api.example.com",
        ))

        channel = await mgr.get_channel("cust_a")

        assert isinstance(channel, WhatsAppChannel)
        assert channel.customer_id == "cust_a"
        assert channel.provider.provider_name == "twilio"
        assert channel.config["from_number"] == "+14155238886"
        assert channel.config["webhook_url"] == "https://api.example.com/webhook/whatsapp/cust_a"

    async def test_get_channel_caches_instance(self):
        mgr = WhatsAppManager()
        mgr.register_customer("cust_a", WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "a", "auth_token": "b"},
        ))
        ch1 = await mgr.get_channel("cust_a")
        ch2 = await mgr.get_channel("cust_a")
        assert ch1 is ch2

    async def test_get_channel_unknown_returns_none(self):
        mgr = WhatsAppManager()
        assert await mgr.get_channel("unknown") is None

    async def test_get_channel_with_config_loader_fallback(self):
        loader = Mock(return_value=WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "AC_loaded", "auth_token": "tok_loaded"},
        ))
        mgr = WhatsAppManager(config_loader=loader)

        channel = await mgr.get_channel("cust_lazy")

        assert channel is not None
        loader.assert_called_once_with("cust_lazy")
        assert channel.customer_id == "cust_lazy"

    async def test_config_loader_returns_none(self):
        loader = Mock(return_value=None)
        mgr = WhatsAppManager(config_loader=loader)
        assert await mgr.get_channel("unknown") is None


class TestWhatsAppManagerStoreSharing:
    async def test_channels_use_shared_store(self):
        """All channels share the manager's MessageStore."""
        mgr = WhatsAppManager()
        mgr.register_customer("cust_a", WhatsAppConfig(
            provider="twilio", from_number="+1",
            credentials={"account_sid": "a", "auth_token": "b"},
        ))
        mgr.register_customer("cust_b", WhatsAppConfig(
            provider="twilio", from_number="+2",
            credentials={"account_sid": "c", "auth_token": "d"},
        ))

        ch_a = await mgr.get_channel("cust_a")
        ch_b = await mgr.get_channel("cust_b")
        assert ch_a.store is ch_b.store
        assert ch_a.store is mgr.store
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_whatsapp_manager.py --no-cov -v
```
Expected: import errors (old manager has incompatible API + DB/Redis deps that will fail on construction)

**Step 3: Rewrite whatsapp_manager.py**

```python
# src/communication/whatsapp_manager.py
"""
Multi-tenant WhatsApp channel manager.

Holds per-customer WhatsAppConfig, lazily builds WhatsAppChannel instances
with the configured provider. Optionally delegates config lookup to a
pluggable loader (e.g. DB-backed) when a customer isn't registered in memory.
"""
import logging
from typing import Callable, Optional

from .whatsapp import (
    InMemoryMessageStore, MessageStore, WhatsAppChannel,
    WhatsAppConfig, create_provider,
)

logger = logging.getLogger(__name__)

ConfigLoader = Callable[[str], Optional[WhatsAppConfig]]


class WhatsAppManager:
    """
    Manages WhatsApp channels for multiple customers.

    - In-memory registration for tests and API-driven onboarding
    - Optional `config_loader` for lazy loading (e.g. from database)
    - Shared MessageStore across all channels (inject DB-backed store in production)
    """

    def __init__(self, *,
                 store: MessageStore | None = None,
                 config_loader: ConfigLoader | None = None):
        self._configs: dict[str, WhatsAppConfig] = {}
        self._channels: dict[str, WhatsAppChannel] = {}
        self._store: MessageStore = store or InMemoryMessageStore()
        self._config_loader = config_loader

    @property
    def store(self) -> MessageStore:
        return self._store

    def register_customer(self, customer_id: str, config: WhatsAppConfig) -> None:
        self._configs[customer_id] = config
        # Drop cached channel so next get_channel() rebuilds with new config
        self._channels.pop(customer_id, None)

    def get_config(self, customer_id: str) -> WhatsAppConfig | None:
        return self._configs.get(customer_id)

    def has_customer(self, customer_id: str) -> bool:
        return customer_id in self._configs

    async def get_channel(self, customer_id: str) -> WhatsAppChannel | None:
        if customer_id in self._channels:
            return self._channels[customer_id]

        cfg = self._configs.get(customer_id)
        if cfg is None and self._config_loader is not None:
            cfg = self._config_loader(customer_id)
            if cfg is not None:
                self._configs[customer_id] = cfg

        if cfg is None:
            return None

        provider = create_provider(cfg.provider, cfg.credentials)
        channel = WhatsAppChannel(
            customer_id=customer_id,
            config={
                "from_number": cfg.from_number,
                "webhook_url": cfg.webhook_url_for(customer_id),
            },
            provider=provider,
            store=self._store,
        )
        await channel.initialize()
        self._channels[customer_id] = channel
        logger.info(
            "Built WhatsApp channel for customer=%s provider=%s",
            customer_id, cfg.provider,
        )
        return channel
```

**Step 4: Run — verify pass**

```bash
pytest tests/unit/test_whatsapp_manager.py --no-cov -v
```
Expected: `9 passed`

**Step 5: Commit**

```bash
jj commit -m "refactor(whatsapp): rewrite manager as provider-agnostic multi-tenant registry" src/communication/whatsapp_manager.py tests/unit/test_whatsapp_manager.py
```

---

## Task 11: Webhook Server Rewrite

**Files:**
- Modify: `src/communication/webhook_server.py` (full rewrite)
- Modify: `tests/unit/test_webhook_server.py` (replace stub)
- Modify: `tests/integration/test_whatsapp_webhook.py` (replace stub)

**Step 1: Write failing unit tests**

```python
# tests/unit/test_webhook_server.py
"""Unit tests for webhook server factory + routing."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock

from src.communication.webhook_server import build_app
from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.whatsapp import (
    WhatsAppConfig, IncomingMessage, StatusUpdate, MessageStatus,
    SendResult,
)


# --- Fixtures --------------------------------------------------------------

def _manager_with_mock_provider(
    customer_id: str = "cust_a",
    parse_result: list | None = None,
    signature_valid: bool = True,
) -> tuple[WhatsAppManager, Mock]:
    """Build a manager with one registered customer whose provider is mocked."""
    cfg = WhatsAppConfig(
        provider="twilio", from_number="+14155238886",
        credentials={"account_sid": "ACtest", "auth_token": "tok"},
        webhook_base_url="http://testserver",
    )
    mgr = WhatsAppManager()
    mgr.register_customer(customer_id, cfg)

    # Replace the real Twilio provider on the built channel with a mock
    # after first access.
    mock_provider = Mock()
    mock_provider.provider_name = "mock"
    mock_provider.validate_signature = Mock(return_value=signature_valid)
    mock_provider.parse_webhook = Mock(return_value=parse_result or [])
    mock_provider.send_text = AsyncMock(return_value=SendResult(
        provider_message_id="SM_reply", status=MessageStatus.QUEUED,
    ))
    mock_provider.fetch_status = AsyncMock(return_value=MessageStatus.UNKNOWN)

    # Override channel build to inject the mock provider
    original_get_channel = mgr.get_channel

    async def get_channel_with_mock(cid):
        ch = await original_get_channel(cid)
        if ch is not None:
            ch._provider = mock_provider
        return ch

    mgr.get_channel = get_channel_with_mock
    return mgr, mock_provider


def _ea_handler(response: str = "EA response text") -> AsyncMock:
    return AsyncMock(return_value=response)


# --- Tests -----------------------------------------------------------------

class TestWebhookRouting:
    def test_unknown_customer_returns_404(self):
        mgr = WhatsAppManager()
        app = build_app(manager=mgr, ea_handler=_ea_handler())
        client = TestClient(app)

        resp = client.post("/webhook/whatsapp/unknown_customer", content=b"x")
        assert resp.status_code == 404

    def test_invalid_signature_returns_403_before_parsing(self):
        mgr, provider = _manager_with_mock_provider(signature_valid=False)
        ea = _ea_handler()
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"Body=hello",
            headers={"X-Twilio-Signature": "bad_sig"},
        )

        assert resp.status_code == 403
        assert provider.parse_webhook.call_count == 0
        assert ea.call_count == 0

    def test_valid_signature_returns_200(self):
        mgr, _ = _manager_with_mock_provider(signature_valid=True)
        app = build_app(manager=mgr, ea_handler=_ea_handler())
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"Body=x",
            headers={"X-Twilio-Signature": "sig"},
        )
        assert resp.status_code == 200


class TestIncomingMessageFlow:
    def test_message_routes_to_ea_and_sends_reply(self):
        incoming = IncomingMessage(
            provider_message_id="SM_in_1",
            from_number="+15551234567",
            to_number="+14155238886",
            body="Hello I need help",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])
        ea = _ea_handler(response="Sure, I can help!")
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a",
            content=b"From=whatsapp%3A%2B15551234567&Body=Hello+I+need+help",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200

        # EA was called with exact args
        assert ea.call_count == 1
        call_kwargs = ea.call_args
        assert call_kwargs.kwargs["message"] == "Hello I need help"
        assert call_kwargs.kwargs["conversation_id"] is not None
        assert len(call_kwargs.kwargs["conversation_id"]) == 16  # sha256[:16]

        # Reply was sent via provider
        provider.send_text.assert_called_once_with(
            to="+15551234567",
            body="Sure, I can help!",
            from_="+14155238886",
        )

    def test_ea_exception_sends_fallback_and_returns_200(self):
        incoming = IncomingMessage(
            provider_message_id="SM_in_err",
            from_number="+15551234567",
            to_number="+14155238886",
            body="trigger error",
        )
        mgr, provider = _manager_with_mock_provider(parse_result=[incoming])
        ea = AsyncMock(side_effect=RuntimeError("EA blew up"))
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        # Fallback sent to the sender
        assert provider.send_text.call_count == 1
        assert provider.send_text.call_args.kwargs["to"] == "+15551234567"
        # The body is a generic fallback — assert exact text per impl
        sent_body = provider.send_text.call_args.kwargs["body"]
        assert sent_body == "I'm having trouble processing that. Give me a moment."


class TestStatusCallbackFlow:
    def test_status_update_stored_ea_not_called(self):
        update = StatusUpdate(
            provider_message_id="SM_out_99",
            status=MessageStatus.DELIVERED,
        )
        mgr, _ = _manager_with_mock_provider(parse_result=[update])
        ea = _ea_handler()
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        resp = client.post(
            "/webhook/whatsapp/cust_a", content=b"x",
            headers={"X-Twilio-Signature": "sig"},
        )

        assert resp.status_code == 200
        assert ea.call_count == 0
        # The manager's shared store should have the update
        # We need to run async to check — use an event loop
        import asyncio
        status = asyncio.get_event_loop().run_until_complete(
            mgr.store.get_status("SM_out_99")
        )
        assert status == MessageStatus.DELIVERED


class TestHealthEndpoint:
    def test_health_returns_200(self):
        app = build_app(manager=WhatsAppManager(), ea_handler=_ea_handler())
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["service"] == "whatsapp-webhook-server"
```

**Step 2: Run — verify fail**

```bash
pytest tests/unit/test_webhook_server.py --no-cov -v
```
Expected: `ImportError` — `build_app` doesn't exist in current webhook_server.py

**Step 3: Rewrite webhook_server.py**

```python
# src/communication/webhook_server.py
"""
FastAPI webhook server for WhatsApp — provider-agnostic.

Each customer's WhatsApp number is configured (in the provider console) to
POST webhooks to /webhook/whatsapp/{customer_id}. The server:
  1. Resolves the customer's channel via WhatsAppManager
  2. Validates the webhook signature via the provider (403 on failure)
  3. Parses events via the provider (IncomingMessage | StatusUpdate)
  4. Routes IncomingMessage → EA handler → sends reply
  5. Routes StatusUpdate → store update
  6. Returns 200 to acknowledge receipt
"""
import logging
from dataclasses import asdict
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response

from .whatsapp import IncomingMessage, StatusUpdate
from .whatsapp_manager import WhatsAppManager

logger = logging.getLogger(__name__)

# EA handler signature: (message, conversation_id) -> response text
# The real wiring uses ExecutiveAssistant.handle_customer_interaction;
# tests inject a mock.
EAHandler = Callable[..., Awaitable[str]]

_FALLBACK_REPLY = "I'm having trouble processing that. Give me a moment."


def build_app(*, manager: WhatsAppManager, ea_handler: EAHandler) -> FastAPI:
    """
    Build the webhook FastAPI app with injected dependencies.

    `manager`: resolves customer_id → WhatsAppChannel
    `ea_handler`: async callable(message: str, conversation_id: str) -> str
    """
    app = FastAPI(title="WhatsApp Webhook Server", version="2.0.0")

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": "whatsapp-webhook-server",
        }

    @app.post("/webhook/whatsapp/{customer_id}")
    async def handle_webhook(customer_id: str, request: Request):
        channel = await manager.get_channel(customer_id)
        if channel is None:
            raise HTTPException(status_code=404, detail="Unknown customer")

        body = await request.body()
        url = str(request.url)
        headers = dict(request.headers)

        # Signature validation MUST happen before parsing the body.
        if not channel.provider.validate_signature(url=url, body=body, headers=headers):
            logger.warning("Invalid webhook signature for customer=%s", customer_id)
            raise HTTPException(status_code=403, detail="Invalid signature")

        events = channel.provider.parse_webhook(
            body, request.headers.get("content-type", "")
        )

        for event in events:
            if isinstance(event, IncomingMessage):
                await _handle_incoming(channel, event, ea_handler)
            elif isinstance(event, StatusUpdate):
                await channel.handle_status_callback(event)

        return Response(status_code=200)

    return app


async def _handle_incoming(channel, event: IncomingMessage,
                           ea_handler: EAHandler) -> None:
    """Process one incoming message: EA → reply. Errors get a fallback reply."""
    base_msg = await channel.handle_incoming_message(asdict(event))
    await channel.store.record_inbound(
        customer_id=channel.customer_id,
        conversation_id=base_msg.conversation_id,
        msg=event,
    )
    try:
        response_text = await ea_handler(
            message=base_msg.content,
            conversation_id=base_msg.conversation_id,
        )
    except Exception:
        logger.exception(
            "EA handler failed for customer=%s msg=%s",
            channel.customer_id, event.provider_message_id,
        )
        response_text = _FALLBACK_REPLY

    try:
        await channel.send_message(base_msg.from_number, response_text)
    except Exception:
        logger.exception(
            "Failed to send reply for customer=%s to=%s",
            channel.customer_id, base_msg.from_number,
        )


# --- Production entrypoint ------------------------------------------------

def create_default_app() -> FastAPI:
    """
    Build app with real dependencies from environment.
    Used by uvicorn: `uvicorn src.communication.webhook_server:app`
    """
    from .whatsapp import WhatsAppConfig
    from ..agents.executive_assistant import ConversationChannel, ExecutiveAssistant

    mgr = WhatsAppManager()
    # Register default customer from env (for single-tenant dev setup)
    default_cfg = WhatsAppConfig.from_env()
    if default_cfg.from_number and default_cfg.credentials.get("account_sid"):
        mgr.register_customer("default", default_cfg)

    # One EA instance per process for now; multi-tenant EA is manager's concern later
    ea_instances: dict[str, ExecutiveAssistant] = {}

    async def ea_handler(message: str, conversation_id: str) -> str:
        # For now: conversation_id → customer_id is not yet mapped; use "default"
        # This is a seam for future per-customer EA routing.
        if "default" not in ea_instances:
            ea_instances["default"] = ExecutiveAssistant(customer_id="default")
        ea = ea_instances["default"]
        return await ea.handle_customer_interaction(
            message=message,
            channel=ConversationChannel.WHATSAPP,
            conversation_id=conversation_id,
        )

    return build_app(manager=mgr, ea_handler=ea_handler)


# Module-level app for uvicorn — lazy import guard for tests
try:
    app = create_default_app()
except ImportError:
    # EA import fails in minimal test envs — build_app() is used directly in tests
    app = None
```

**Step 4: Run — verify unit tests pass**

```bash
pytest tests/unit/test_webhook_server.py --no-cov -v
```
Expected: `8 passed`

**Step 5: Write integration test (replace stub)**

```python
# tests/integration/test_whatsapp_webhook.py
"""
Integration test: full inbound flow with real Twilio provider parsing,
real signature computation, and mocked EA + outbound HTTP.
"""
import base64
import hashlib
import hmac
from urllib.parse import urlencode, parse_qsl

import httpx
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from src.communication.webhook_server import build_app
from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.whatsapp import WhatsAppConfig, MessageStatus
from src.communication.whatsapp.providers.twilio import TwilioWhatsAppProvider


AUTH_TOKEN = "integration_test_token"
CUSTOMER_ID = "cust_integ"


def _twilio_signature(url: str, params: dict[str, str]) -> str:
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(AUTH_TOKEN.encode(), s.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


@pytest.fixture
def manager_with_twilio():
    """Manager with a real TwilioWhatsAppProvider (httpx mocked for outbound)."""
    sent_requests = []

    def outbound_handler(request: httpx.Request) -> httpx.Response:
        sent_requests.append({
            "url": str(request.url),
            "form": dict(parse_qsl(request.content.decode())),
        })
        return httpx.Response(201, json={"sid": "SM_reply_1", "status": "queued"})

    mock_transport = httpx.MockTransport(outbound_handler)

    cfg = WhatsAppConfig(
        provider="twilio", from_number="+14155238886",
        credentials={"account_sid": "ACinteg", "auth_token": AUTH_TOKEN},
        webhook_base_url="http://testserver",
    )
    mgr = WhatsAppManager()
    mgr.register_customer(CUSTOMER_ID, cfg)

    # Override the provider's http client after channel construction
    original_get_channel = mgr.get_channel

    async def get_channel_patched(cid):
        ch = await original_get_channel(cid)
        if ch is not None and not hasattr(ch.provider, "_http_patched"):
            ch._provider = TwilioWhatsAppProvider(
                account_sid="ACinteg", auth_token=AUTH_TOKEN,
                http_client=httpx.AsyncClient(
                    transport=mock_transport,
                    auth=("ACinteg", AUTH_TOKEN),
                ),
            )
            ch._provider._http_patched = True
        return ch

    mgr.get_channel = get_channel_patched
    return mgr, sent_requests


@pytest.mark.integration
class TestInboundFlowEndToEnd:
    def test_message_in_ea_response_out(self, manager_with_twilio):
        mgr, sent_requests = manager_with_twilio
        ea = AsyncMock(return_value="Hi! I can help with that.")
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        webhook_url = f"http://testserver/webhook/whatsapp/{CUSTOMER_ID}"
        params = {
            "MessageSid": "SM_inbound_test",
            "From": "whatsapp:+15551234567",
            "To": "whatsapp:+14155238886",
            "Body": "I need help with my order",
            "ProfileName": "Jane",
            "NumMedia": "0",
        }
        sig = _twilio_signature(webhook_url, params)
        body = urlencode(params).encode()

        resp = client.post(
            f"/webhook/whatsapp/{CUSTOMER_ID}", content=body,
            headers={"X-Twilio-Signature": sig,
                     "Content-Type": "application/x-www-form-urlencoded"},
        )

        # 1. Webhook accepted
        assert resp.status_code == 200

        # 2. EA called with exact message content
        assert ea.call_count == 1
        assert ea.call_args.kwargs["message"] == "I need help with my order"
        conv_id = ea.call_args.kwargs["conversation_id"]
        assert len(conv_id) == 16

        # 3. Reply sent to Twilio with exact form body
        assert len(sent_requests) == 1
        assert sent_requests[0]["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACinteg/Messages.json"
        assert sent_requests[0]["form"] == {
            "To": "whatsapp:+15551234567",
            "From": "whatsapp:+14155238886",
            "Body": "Hi! I can help with that.",
        }

        # 4. Store has the outbound message status
        import asyncio
        status = asyncio.get_event_loop().run_until_complete(
            mgr.store.get_status("SM_reply_1")
        )
        assert status == MessageStatus.QUEUED

    def test_real_signature_rejected_on_tamper(self, manager_with_twilio):
        mgr, sent_requests = manager_with_twilio
        ea = AsyncMock()
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        webhook_url = f"http://testserver/webhook/whatsapp/{CUSTOMER_ID}"
        original = {"MessageSid": "SM_x", "Body": "original", "From": "whatsapp:+1"}
        sig = _twilio_signature(webhook_url, original)
        tampered = {"MessageSid": "SM_x", "Body": "TAMPERED", "From": "whatsapp:+1"}

        resp = client.post(
            f"/webhook/whatsapp/{CUSTOMER_ID}",
            content=urlencode(tampered).encode(),
            headers={"X-Twilio-Signature": sig},
        )

        assert resp.status_code == 403
        assert ea.call_count == 0
        assert len(sent_requests) == 0

    def test_status_callback_updates_store_no_ea(self, manager_with_twilio):
        mgr, sent_requests = manager_with_twilio
        ea = AsyncMock()
        app = build_app(manager=mgr, ea_handler=ea)
        client = TestClient(app)

        webhook_url = f"http://testserver/webhook/whatsapp/{CUSTOMER_ID}"
        params = {
            "MessageSid": "SM_tracked_out",
            "MessageStatus": "delivered",
            "To": "whatsapp:+15551234567",
        }
        sig = _twilio_signature(webhook_url, params)

        resp = client.post(
            f"/webhook/whatsapp/{CUSTOMER_ID}",
            content=urlencode(params).encode(),
            headers={"X-Twilio-Signature": sig},
        )

        assert resp.status_code == 200
        assert ea.call_count == 0
        assert len(sent_requests) == 0

        import asyncio
        status = asyncio.get_event_loop().run_until_complete(
            mgr.store.get_status("SM_tracked_out")
        )
        assert status == MessageStatus.DELIVERED
```

**Step 6: Run integration tests**

```bash
pytest tests/integration/test_whatsapp_webhook.py --no-cov -v
```
Expected: `3 passed`

**Step 7: Run all new tests together**

```bash
pytest tests/unit/test_whatsapp_store.py tests/unit/test_whatsapp_config.py tests/unit/test_whatsapp_provider_twilio.py tests/unit/test_whatsapp_provider_registry.py tests/unit/test_whatsapp_channel.py tests/unit/test_whatsapp_manager.py tests/unit/test_webhook_server.py tests/integration/test_whatsapp_webhook.py --no-cov -v
```
Expected: all pass, ~70 tests

**Step 8: Commit**

```bash
jj commit -m "feat(whatsapp): rewrite webhook server with signature-first validation and per-customer routing" src/communication/webhook_server.py tests/unit/test_webhook_server.py tests/integration/test_whatsapp_webhook.py
```

---

## Task 12: Coverage & Final Verification

**Step 1: Run the full new-test suite with coverage on**

```bash
pytest tests/unit/test_whatsapp_store.py tests/unit/test_whatsapp_config.py tests/unit/test_whatsapp_provider_twilio.py tests/unit/test_whatsapp_provider_registry.py tests/unit/test_whatsapp_channel.py tests/unit/test_whatsapp_manager.py tests/unit/test_webhook_server.py tests/integration/test_whatsapp_webhook.py --cov=src/communication/whatsapp --cov=src/communication/whatsapp_manager --cov=src/communication/webhook_server --cov-report=term-missing -v
```
Expected: >80% coverage on the new modules. If below, identify uncovered lines and add targeted tests.

**Step 2: Run existing base_channel test (regression check)**

```bash
pytest tests/unit/test_base_channel.py --no-cov -v
```
Expected: `2 passed` (unchanged)

**Step 3: Verify imports work at package level**

```bash
python -c "
from src.communication import WhatsAppChannel, WhatsAppMessage, ChannelType
from src.communication.whatsapp import (
    WhatsAppChannel, WhatsAppConfig, WhatsAppProvider,
    IncomingMessage, StatusUpdate, MessageStatus,
    InMemoryMessageStore, create_provider,
)
from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.webhook_server import build_app
print('All imports OK')
"
```
Expected: `All imports OK`

**Step 4: Commit final verification**

```bash
jj commit -m "test(whatsapp): verify full test suite and coverage" --allow-empty
```
(May be empty if no new files; that's fine — marks the milestone.)

---

## Summary of Commits

| Commit | Message | Files |
|---|---|---|
| 1 | `feat(whatsapp): add provider protocol and result dataclasses` | `provider.py`, `__init__.py` |
| 2 | `feat(whatsapp): add MessageStore protocol and in-memory implementation` | `store.py`, test |
| 3 | `feat(whatsapp): add WhatsAppConfig with env/dict loaders` | `config.py`, test |
| 4 | `feat(whatsapp): add Twilio provider with signature validation` | `providers/twilio.py`, test |
| 5 | `feat(whatsapp): implement Twilio webhook parsing` | `providers/twilio.py`, test |
| 6 | `feat(whatsapp): implement Twilio send_text and fetch_status` | `providers/twilio.py`, test |
| 7 | `feat(whatsapp): add provider registry factory` | `_registry.py`, test |
| 8 | `feat(whatsapp): implement provider-agnostic WhatsAppChannel` | `channel.py`, test |
| 9 | `refactor(whatsapp): replace legacy channel with provider-abstraction re-export` | old `whatsapp_channel.py`, `__init__.py`s |
| 10 | `refactor(whatsapp): rewrite manager as provider-agnostic multi-tenant registry` | `whatsapp_manager.py`, test |
| 11 | `feat(whatsapp): rewrite webhook server with signature-first validation and per-customer routing` | `webhook_server.py`, tests |
| 12 | `test(whatsapp): verify full test suite and coverage` | — |

---

## Known Gotchas

1. **`conftest.py` imports EA at module level.** If `langchain`/`openai`/etc. aren't installed, test collection fails globally. Not introduced by this work; install `pip install -e ".[dev]"` to resolve.

2. **`--cov-fail-under=80` in pyproject.** Full `pytest` runs need 80% global coverage. Run individual test files with `--no-cov` during TDD iterations.

3. **`asyncio.get_event_loop().run_until_complete()` in webhook tests.** FastAPI `TestClient` runs the app in a separate event loop; calling async store methods from the test requires either (a) `asyncio.run(...)` / `run_until_complete`, or (b) making the test itself `async` and using `httpx.AsyncClient` with ASGI transport instead of `TestClient`. The plan uses option (a) for simplicity — if it causes issues (e.g. "no running event loop"), switch to `asyncio.run(mgr.store.get_status(...))` or refactor to async tests with `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))`.

4. **Twilio provider's default `httpx.AsyncClient`** never gets closed. Fine for the webhook server (process-lifetime), acceptable for tests that inject their own clients. If it matters later, add an `async close()` method and call it from a lifespan handler.

5. **The `validate_webhook_signature` on `WhatsAppChannel`** has a limited signature per the ABC (`(payload: str, signature: str)`). The webhook server bypasses it and calls `channel.provider.validate_signature()` directly with full `(url, body, headers)` — which is the correct approach. The channel method is kept for ABC compliance but webhook server doesn't use it.
