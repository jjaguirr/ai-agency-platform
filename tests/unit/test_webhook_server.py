"""
Unit tests for webhook_server (FastAPI app factory).

Tests use FastAPI's TestClient + a WhatsAppManager wired with MockProvider.
No live API calls.

Covers:
- Signature validation: valid → 200, forged → 403, skip-mode → 200
- Inbound webhook routes to channel.process_inbound
- Status webhook routes to channel.handle_status_callback
- Per-customer routing via {customer_id} path param
- Public URL reconstruction via WEBHOOK_PUBLIC_BASE_URL
"""
import os
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.communication.base_channel import BaseMessage
from src.communication.providers.base_provider import (
    DeliveryState,
    InboundMessage,
    MessageStatus,
    WhatsAppProvider,
)


# -------------------------------------------------------------------
# Test fixtures: mock provider, manager, app
# -------------------------------------------------------------------

class RecordingProvider(WhatsAppProvider):
    """Provider that records all calls and has controllable signature result."""

    def __init__(self, **kwargs):
        self.sent = []
        self.sig_valid = True
        self.sig_calls = []

    async def send_text(self, to, body):
        mid = f"MOCK-OUT-{len(self.sent):03d}"
        self.sent.append({"to": to, "body": body, "id": mid})
        return mid

    def parse_incoming_webhook(self, form_data):
        return InboundMessage(
            provider_message_id=form_data.get("MessageSid", "in-1"),
            from_phone=form_data.get("From", "+15551234567").replace("whatsapp:", ""),
            to_phone=form_data.get("To", "+14155238886").replace("whatsapp:", ""),
            body=form_data.get("Body", ""),
            timestamp=datetime(2026, 3, 5, 12, 0, 0),
            raw=dict(form_data),
        )

    def parse_status_callback(self, form_data):
        st = form_data.get("MessageStatus", "delivered")
        return MessageStatus(
            provider_message_id=form_data.get("MessageSid", "MOCK-OUT-000"),
            state=DeliveryState(st),
            timestamp=datetime(2026, 3, 5, 12, 0, 0),
        )

    def validate_signature(self, url, form_data, signature):
        self.sig_calls.append({"url": url, "form_data": dict(form_data), "signature": signature})
        # Realistic: empty/None signatures always fail, regardless of sig_valid override
        if not signature:
            return False
        return self.sig_valid

    async def fetch_message_status(self, message_id):
        return MessageStatus(message_id, DeliveryState.SENT, datetime.now())


@pytest.fixture
def recording_provider():
    return RecordingProvider()


@pytest.fixture
def manager(recording_provider):
    """Manager wired with RecordingProvider via registry + a fake EA handler."""
    from src.communication.providers import PROVIDER_REGISTRY
    from src.communication.whatsapp_manager import WhatsAppManager

    # Register the recording provider
    PROVIDER_REGISTRY["_test_recording"] = lambda **kw: recording_provider

    handler_log = []

    async def fake_handler(msg: BaseMessage) -> str:
        handler_log.append(msg)
        return f"EA reply to: {msg.content}"

    def loader(cid):
        return {"provider": "_test_recording"}

    m = WhatsAppManager(
        config_loader=loader,
        handler_factory=lambda cid: fake_handler,
    )
    m._handler_log = handler_log  # expose for assertions

    yield m

    del PROVIDER_REGISTRY["_test_recording"]


@pytest.fixture
def client(manager):
    from src.communication.webhook_server import create_app
    app = create_app(manager)
    return TestClient(app)


# -------------------------------------------------------------------
# Health endpoint
# -------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert body["service"] == "whatsapp-webhook-server"
        assert body["active_channels"] == 0  # fresh manager, no channels yet


# -------------------------------------------------------------------
# Inbound webhook — signature validation
# -------------------------------------------------------------------

class TestInboundSignatureValidation:
    def test_valid_signature_returns_200(self, client, recording_provider):
        recording_provider.sig_valid = True
        r = client.post(
            "/webhook/whatsapp/cust-001",
            data={"MessageSid": "SM1", "From": "whatsapp:+15551234567", "Body": "hi"},
            headers={"X-Twilio-Signature": "valid-sig"},
        )
        assert r.status_code == 200

    def test_forged_signature_returns_403(self, client, recording_provider, manager):
        recording_provider.sig_valid = False
        r = client.post(
            "/webhook/whatsapp/cust-001",
            data={"MessageSid": "SM1", "From": "whatsapp:+15551234567", "Body": "hi"},
            headers={"X-Twilio-Signature": "forged!"},
        )
        assert r.status_code == 403
        # Critical: handler was NOT called, message was NOT sent
        assert len(manager._handler_log) == 0
        assert len(recording_provider.sent) == 0

    def test_missing_signature_returns_403(self, client, recording_provider, manager):
        r = client.post(
            "/webhook/whatsapp/cust-001",
            data={"MessageSid": "SM1", "Body": "hi"},
            # No signature header
        )
        assert r.status_code == 403
        # Provider's validate_signature saw None (no header)
        assert recording_provider.sig_calls[-1]["signature"] is None
        # Handler never invoked, no reply sent
        assert len(manager._handler_log) == 0
        assert len(recording_provider.sent) == 0

    def test_skip_signature_env_var_bypasses_validation(self, client, recording_provider):
        recording_provider.sig_valid = False  # would normally 403
        with patch.dict(os.environ, {"WHATSAPP_WEBHOOK_SKIP_SIGNATURE": "1"}):
            r = client.post(
                "/webhook/whatsapp/cust-001",
                data={"MessageSid": "SM1", "From": "whatsapp:+1555", "Body": "hi"},
                headers={"X-Twilio-Signature": "doesnt-matter"},
            )
        assert r.status_code == 200


# -------------------------------------------------------------------
# Inbound webhook — message processing
# -------------------------------------------------------------------

class TestInboundProcessing:
    def test_inbound_invokes_handler_and_sends_reply(
        self, client, manager, recording_provider
    ):
        recording_provider.sig_valid = True
        r = client.post(
            "/webhook/whatsapp/cust-process",
            data={
                "MessageSid": "SMin1",
                "From": "whatsapp:+15551234567",
                "To": "whatsapp:+14155238886",
                "Body": "Hello EA",
            },
            headers={"X-Twilio-Signature": "sig"},
        )
        assert r.status_code == 200

        # Handler was called with correct content
        assert len(manager._handler_log) == 1
        assert manager._handler_log[0].content == "Hello EA"
        assert manager._handler_log[0].customer_id == "cust-process"

        # Reply was sent
        assert len(recording_provider.sent) == 1
        assert recording_provider.sent[0]["body"] == "EA reply to: Hello EA"
        assert recording_provider.sent[0]["to"] == "+15551234567"

    def test_inbound_form_data_passed_to_provider(
        self, client, recording_provider
    ):
        recording_provider.sig_valid = True
        client.post(
            "/webhook/whatsapp/cust-001",
            data={
                "MessageSid": "SMcheck",
                "From": "whatsapp:+15551111111",
                "Body": "form check",
                "NumMedia": "0",
            },
            headers={"X-Twilio-Signature": "sig"},
        )
        # Provider's validate_signature saw the form data
        last_call = recording_provider.sig_calls[-1]
        assert last_call["form_data"]["MessageSid"] == "SMcheck"
        assert last_call["form_data"]["Body"] == "form check"

    def test_per_customer_routing(self, client, manager, recording_provider):
        recording_provider.sig_valid = True
        client.post(
            "/webhook/whatsapp/tenant-alpha",
            data={"MessageSid": "SM1", "From": "whatsapp:+1555", "Body": "msg for alpha"},
            headers={"X-Twilio-Signature": "sig"},
        )
        client.post(
            "/webhook/whatsapp/tenant-beta",
            data={"MessageSid": "SM2", "From": "whatsapp:+1555", "Body": "msg for beta"},
            headers={"X-Twilio-Signature": "sig"},
        )

        customers_seen = [m.customer_id for m in manager._handler_log]
        assert "tenant-alpha" in customers_seen
        assert "tenant-beta" in customers_seen


# -------------------------------------------------------------------
# Public URL reconstruction for sig validation
# -------------------------------------------------------------------

class TestPublicUrlReconstruction:
    def test_public_base_url_env_var_used_for_signature(
        self, client, recording_provider
    ):
        """When behind a reverse proxy, request.url is the internal address.
        WEBHOOK_PUBLIC_BASE_URL should override it so sig validation uses
        the same URL Twilio used."""
        recording_provider.sig_valid = True
        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": "https://public.example.com"}):
            client.post(
                "/webhook/whatsapp/cust-proxy",
                data={"MessageSid": "SM1", "Body": "hi"},
                headers={"X-Twilio-Signature": "sig"},
            )

        # Provider saw the public URL, not the TestClient's internal one
        assert recording_provider.sig_calls[-1]["url"].startswith("https://public.example.com")
        assert recording_provider.sig_calls[-1]["url"].endswith("/webhook/whatsapp/cust-proxy")

    def test_without_public_base_url_uses_request_url(
        self, client, recording_provider
    ):
        recording_provider.sig_valid = True
        # Clear the env var if set
        env_backup = os.environ.pop("WEBHOOK_PUBLIC_BASE_URL", None)
        try:
            client.post(
                "/webhook/whatsapp/cust-direct",
                data={"MessageSid": "SM1", "Body": "hi"},
                headers={"X-Twilio-Signature": "sig"},
            )
        finally:
            if env_backup:
                os.environ["WEBHOOK_PUBLIC_BASE_URL"] = env_backup

        # TestClient uses http://testserver as base
        assert "testserver" in recording_provider.sig_calls[-1]["url"]


# -------------------------------------------------------------------
# Status callback endpoint
# -------------------------------------------------------------------

class TestStatusCallback:
    def test_status_callback_updates_channel_tracking(
        self, client, recording_provider, manager
    ):
        recording_provider.sig_valid = True

        # First send a message so there's an id to track
        client.post(
            "/webhook/whatsapp/cust-status",
            data={"MessageSid": "SMin", "From": "whatsapp:+1555", "Body": "trigger"},
            headers={"X-Twilio-Signature": "sig"},
        )
        sent_id = recording_provider.sent[0]["id"]

        # Now deliver a status callback
        r = client.post(
            "/webhook/whatsapp/cust-status/status",
            data={"MessageSid": sent_id, "MessageStatus": "delivered"},
            headers={"X-Twilio-Signature": "sig"},
        )
        assert r.status_code == 200

        # Verify the channel's internal tracking updated
        # (Access via manager since we don't hold the channel directly in test)
        # The channel is cached in manager._channels
        ch = manager._channels["cust-status"]
        assert ch._status[sent_id].state == DeliveryState.DELIVERED

    def test_status_callback_forged_signature_rejected(
        self, client, recording_provider
    ):
        recording_provider.sig_valid = False
        r = client.post(
            "/webhook/whatsapp/cust-001/status",
            data={"MessageSid": "SM1", "MessageStatus": "delivered"},
            headers={"X-Twilio-Signature": "forged"},
        )
        assert r.status_code == 403

    def test_status_callback_for_unknown_customer_creates_channel(
        self, client, recording_provider, manager
    ):
        """Status may arrive before we've seen an inbound — must create the
        channel on demand and record the status."""
        recording_provider.sig_valid = True
        r = client.post(
            "/webhook/whatsapp/never-seen-customer/status",
            data={"MessageSid": "SMext", "MessageStatus": "read"},
            headers={"X-Twilio-Signature": "sig"},
        )
        assert r.status_code == 200
        # Channel was created on demand
        assert "never-seen-customer" in manager._channels
        # Status was actually tracked
        ch = manager._channels["never-seen-customer"]
        assert "SMext" in ch._status
        assert ch._status["SMext"].state == DeliveryState.READ


# -------------------------------------------------------------------
# Signature-first order of operations (security boundary)
# -------------------------------------------------------------------

class TestSignatureFirstOrdering:
    """Signature validation must happen BEFORE get_channel.

    If it doesn't:
    - Attacker with bad sig can trigger handler_factory (expensive, may hit DB)
    - Bogus customer_ids pollute the channel cache pre-auth
    - Unknown customer_id leaks as 500 instead of clean 404
    """

    def test_forged_signature_does_not_build_channel(self, recording_provider):
        """Bad sig → 403 BEFORE handler_factory runs, BEFORE channel cached.

        This is the core fix: sig check uses get_validator (lightweight),
        not get_channel (builds full channel)."""
        from src.communication.providers import PROVIDER_REGISTRY
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.webhook_server import create_app

        PROVIDER_REGISTRY["_test_rec"] = lambda **kw: recording_provider

        factory_calls = []

        async def fake_handler(msg): return "reply"

        def handler_factory(cid):
            factory_calls.append(cid)  # records any call — should stay empty
            return fake_handler

        def loader(cid):
            return {"provider": "_test_rec"}

        m = WhatsAppManager(config_loader=loader, handler_factory=handler_factory)
        app = create_app(m)
        c = TestClient(app)

        try:
            recording_provider.sig_valid = False
            r = c.post(
                "/webhook/whatsapp/cust-forge",
                data={"MessageSid": "SM1", "Body": "attack"},
                headers={"X-Twilio-Signature": "forged"},
            )

            assert r.status_code == 403
            # THE ASSERTION: handler_factory never called → channel never built
            assert factory_calls == []
            assert "cust-forge" not in m._channels
            # But validator WAS consulted (sig check ran)
            assert len(recording_provider.sig_calls) == 1
        finally:
            del PROVIDER_REGISTRY["_test_rec"]

    def test_unknown_customer_returns_404(self):
        """config_loader returns None + no env → 404, not 500.

        Prevents leaking internal RuntimeError messages to callers."""
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.webhook_server import create_app

        def loader(cid):
            return None  # unknown customer

        clear_keys = [
            "WHATSAPP_PROVIDER", "WHATSAPP_ACCOUNT_SID",
            "WHATSAPP_AUTH_TOKEN", "WHATSAPP_NUMBER",
        ]
        env_snapshot = {k: os.environ.pop(k) for k in clear_keys if k in os.environ}
        try:
            m = WhatsAppManager(config_loader=loader)
            app = create_app(m)
            c = TestClient(app)

            r = c.post(
                "/webhook/whatsapp/ghost",
                data={"MessageSid": "SM1", "Body": "hi"},
                headers={"X-Twilio-Signature": "sig"},
            )
            assert r.status_code == 404
            # No cache pollution
            assert "ghost" not in m._channels
        finally:
            os.environ.update(env_snapshot)

    def test_misconfigured_customer_returns_404_not_500(self):
        """Partial config (missing auth_token) → 404, not 500 with traceback.

        Closes the enumeration oracle where:
        - 404 = customer doesn't exist
        - 500 = customer exists but misconfigured  ← leaks which tenants are real
        """
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.webhook_server import create_app

        def loader(cid):
            # Customer IS configured but incompletely — no auth_token, no number
            return {"provider": "twilio", "account_sid": "ACpartial"}

        m = WhatsAppManager(config_loader=loader)
        app = create_app(m)
        c = TestClient(app)

        r = c.post(
            "/webhook/whatsapp/cust-partial",
            data={"MessageSid": "SM1", "Body": "hi"},
            headers={"X-Twilio-Signature": "sig"},
        )
        assert r.status_code == 404
        # Response body must NOT leak the internal error (TypeError text, config keys)
        body = r.text.lower()
        assert "typeerror" not in body
        assert "auth_token" not in body
        assert "account_sid" not in body
        # No cache pollution on failed provider build
        assert "cust-partial" not in m._channels
        assert "cust-partial" not in m._providers

    def test_config_loader_exception_returns_404_not_500(self):
        """config_loader itself raises (DB down, bad query, whatever) → 404.

        The webhook boundary must be defensive: ANY failure in the pre-auth
        path is opaque to the caller. Operator sees it in logs; attacker sees 404."""
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.webhook_server import create_app

        def loader(cid):
            raise KeyError(f"customer {cid} lookup failed")  # simulates DB error

        m = WhatsAppManager(config_loader=loader)
        app = create_app(m)
        c = TestClient(app)

        r = c.post(
            "/webhook/whatsapp/cust-dberr",
            data={"MessageSid": "SM1", "Body": "hi"},
            headers={"X-Twilio-Signature": "sig"},
        )
        assert r.status_code == 404
        # No leak of the KeyError message
        assert "lookup failed" not in r.text
        assert "cust-dberr" not in m._channels
        assert "cust-dberr" not in m._providers

    def test_unknown_customer_status_endpoint_also_404(self):
        """Same 404 behavior for /status endpoint."""
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.webhook_server import create_app

        def loader(cid):
            return None

        clear_keys = [
            "WHATSAPP_PROVIDER", "WHATSAPP_ACCOUNT_SID",
            "WHATSAPP_AUTH_TOKEN", "WHATSAPP_NUMBER",
        ]
        env_snapshot = {k: os.environ.pop(k) for k in clear_keys if k in os.environ}
        try:
            m = WhatsAppManager(config_loader=loader)
            app = create_app(m)
            c = TestClient(app)

            r = c.post(
                "/webhook/whatsapp/ghost/status",
                data={"MessageSid": "SM1", "MessageStatus": "delivered"},
                headers={"X-Twilio-Signature": "sig"},
            )
            assert r.status_code == 404
        finally:
            os.environ.update(env_snapshot)

    def test_valid_signature_still_builds_channel_and_processes(
        self, recording_provider
    ):
        """Regression guard: after reordering, the happy path still works."""
        from src.communication.providers import PROVIDER_REGISTRY
        from src.communication.whatsapp_manager import WhatsAppManager
        from src.communication.webhook_server import create_app

        PROVIDER_REGISTRY["_test_rec2"] = lambda **kw: recording_provider

        factory_calls = []

        async def fake_handler(msg): return f"re: {msg.content}"

        def handler_factory(cid):
            factory_calls.append(cid)
            return fake_handler

        m = WhatsAppManager(
            config_loader=lambda c: {"provider": "_test_rec2"},
            handler_factory=handler_factory,
        )
        app = create_app(m)
        c = TestClient(app)

        try:
            recording_provider.sig_valid = True
            r = c.post(
                "/webhook/whatsapp/cust-ok",
                data={"MessageSid": "SM1", "From": "whatsapp:+1555", "Body": "hi"},
                headers={"X-Twilio-Signature": "valid"},
            )

            assert r.status_code == 200
            # NOW channel built, handler wired, reply sent
            assert factory_calls == ["cust-ok"]
            assert "cust-ok" in m._channels
            assert len(recording_provider.sent) == 1
            assert recording_provider.sent[0]["body"] == "re: hi"
        finally:
            del PROVIDER_REGISTRY["_test_rec2"]


# -------------------------------------------------------------------
# App factory pattern
# -------------------------------------------------------------------

class TestAppFactory:
    def test_create_app_returns_fastapi_instance(self, manager):
        from fastapi import FastAPI
        from src.communication.webhook_server import create_app
        app = create_app(manager)
        assert isinstance(app, FastAPI)

    def test_routes_registered(self, manager):
        from src.communication.webhook_server import create_app
        app = create_app(manager)
        paths = {r.path for r in app.routes}
        assert "/health" in paths
        assert "/webhook/whatsapp/{customer_id}" in paths
        assert "/webhook/whatsapp/{customer_id}/status" in paths

    def test_no_module_level_app(self):
        """Importing the module must not create a global app/manager."""
        import src.communication.webhook_server as mod
        from fastapi import FastAPI
        fastapi_globals = [
            name for name in dir(mod)
            if not name.startswith("_")
            and isinstance(getattr(mod, name, None), FastAPI)
        ]
        assert fastapi_globals == [], (
            f"Found module-level FastAPI instance(s): {fastapi_globals}"
        )
