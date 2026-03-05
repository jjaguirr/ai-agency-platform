"""
Integration tests: full WhatsApp webhook flow with real Twilio-format payloads
and real TwilioWhatsAppProvider (httpx mocked).

Differs from unit tests:
- Uses the actual TwilioWhatsAppProvider (not a mock provider)
- Uses real Twilio webhook form-data shapes
- Computes real Twilio signatures
- httpx is mocked via MockTransport so no live API calls

This validates the wire contract end-to-end without hitting Twilio.
"""
import base64
import hashlib
import hmac
import os
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from src.communication.base_channel import BaseMessage
from src.communication.providers import PROVIDER_REGISTRY
from src.communication.providers.twilio_provider import TwilioWhatsAppProvider
from src.communication.whatsapp_manager import WhatsAppManager
from src.communication.webhook_server import create_app


pytestmark = pytest.mark.integration

# Test credentials (fake but structurally valid)
TEST_SID = "ACaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
TEST_TOKEN = "test_auth_token_for_integration"
TEST_WA_NUMBER = "+14155238886"
PUBLIC_BASE = "https://webhook.test.example.com"


def twilio_sign(url: str, params: dict) -> str:
    """Compute a real Twilio signature."""
    data = url
    for k in sorted(params.keys()):
        data += k + str(params[k])
    mac = hmac.new(TEST_TOKEN.encode(), data.encode(), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode()


# -------------------------------------------------------------------
# Fixture: real Twilio provider with mocked httpx transport
# -------------------------------------------------------------------

@pytest.fixture
def httpx_capture():
    """Records outbound Twilio API calls and returns synthetic success responses."""
    captured = {"requests": []}

    async def handler(request: httpx.Request):
        captured["requests"].append(
            {
                "method": request.method,
                "url": str(request.url),
                "body": request.content.decode(),
            }
        )
        # Synthesize a Twilio Messages API response
        msg_num = len(captured["requests"])
        return httpx.Response(
            201,
            json={"sid": f"SMout{msg_num:04d}", "status": "queued"},
        )

    captured["transport"] = httpx.MockTransport(handler)
    return captured


@pytest.fixture
def twilio_provider_factory(httpx_capture):
    """Factory that produces real TwilioWhatsAppProvider with mocked transport."""

    def make_provider(**kwargs):
        # All customers use the same test creds in this integration test
        client = httpx.AsyncClient(transport=httpx_capture["transport"])
        return TwilioWhatsAppProvider(
            account_sid=TEST_SID,
            auth_token=TEST_TOKEN,
            whatsapp_number=TEST_WA_NUMBER,
            http_client=client,
        )

    return make_provider


@pytest.fixture
def handler_log():
    return []


@pytest.fixture
def manager(twilio_provider_factory, handler_log):
    """Manager wired with the real TwilioWhatsAppProvider (mocked transport)."""
    PROVIDER_REGISTRY["_test_twilio"] = twilio_provider_factory

    async def fake_ea(msg: BaseMessage) -> str:
        handler_log.append(msg)
        return f"Got it: {msg.content}"

    m = WhatsAppManager(
        config_loader=lambda cid: {"provider": "_test_twilio"},
        handler_factory=lambda cid: fake_ea,
    )
    yield m
    del PROVIDER_REGISTRY["_test_twilio"]


@pytest.fixture
def client(manager):
    app = create_app(manager)
    return TestClient(app)


# -------------------------------------------------------------------
# Full inbound flow: Twilio POST → parse → handler → Twilio send
# -------------------------------------------------------------------

@pytest.mark.integration
class TestFullInboundFlow:
    def test_valid_twilio_webhook_triggers_ea_and_replies(
        self, client, handler_log, httpx_capture
    ):
        path = "/webhook/whatsapp/cust-integ-001"
        form_data = {
            "MessageSid": "SMinbound001",
            "AccountSid": TEST_SID,
            "From": "whatsapp:+15551234567",
            "To": f"whatsapp:{TEST_WA_NUMBER}",
            "Body": "Hello, I need help with my order",
            "NumMedia": "0",
            "ProfileName": "Jane Doe",
            "WaId": "15551234567",
        }
        url_for_sig = f"{PUBLIC_BASE}{path}"
        sig = twilio_sign(url_for_sig, form_data)

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(
                path,
                data=form_data,
                headers={"X-Twilio-Signature": sig},
            )

        assert r.status_code == 200

        # EA handler received the parsed message
        assert len(handler_log) == 1
        msg = handler_log[0]
        assert msg.content == "Hello, I need help with my order"
        assert msg.from_number == "+15551234567"
        assert msg.customer_id == "cust-integ-001"
        assert msg.channel.value == "whatsapp"
        assert msg.conversation_id  # non-empty

        # Outbound reply was sent to Twilio API
        assert len(httpx_capture["requests"]) == 1
        out_req = httpx_capture["requests"][0]
        assert out_req["method"] == "POST"
        assert TEST_SID in out_req["url"]
        assert out_req["url"].endswith("/Messages.json")
        # Body contains the EA reply and the sender's phone
        assert "Got+it" in out_req["body"] or "Got%20it" in out_req["body"]
        assert "15551234567" in out_req["body"]

    def test_forged_signature_rejected_no_handler_invoked(
        self, client, handler_log, httpx_capture
    ):
        path = "/webhook/whatsapp/cust-integ-001"
        form_data = {
            "MessageSid": "SMforged",
            "From": "whatsapp:+15551234567",
            "Body": "Attacker message",
        }

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(
                path,
                data=form_data,
                headers={"X-Twilio-Signature": "this-is-forged"},
            )

        assert r.status_code == 403
        # Handler never called, nothing sent
        assert len(handler_log) == 0
        assert len(httpx_capture["requests"]) == 0

    def test_tampered_body_rejected(self, client, handler_log):
        """Sign valid payload, then tamper with body — must 403."""
        path = "/webhook/whatsapp/cust-integ-001"
        original = {
            "MessageSid": "SMtamper",
            "From": "whatsapp:+15551234567",
            "Body": "original text",
        }
        url_for_sig = f"{PUBLIC_BASE}{path}"
        sig = twilio_sign(url_for_sig, original)

        tampered = dict(original)
        tampered["Body"] = "ATTACKER INJECTED"

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(
                path,
                data=tampered,
                headers={"X-Twilio-Signature": sig},
            )

        assert r.status_code == 403
        assert len(handler_log) == 0


# -------------------------------------------------------------------
# Status callback flow
# -------------------------------------------------------------------

@pytest.mark.integration
class TestStatusCallbackFlow:
    def test_delivery_lifecycle_tracked_end_to_end(
        self, client, manager, httpx_capture
    ):
        from src.communication.providers.base_provider import DeliveryState

        cust = "cust-status-flow"
        inbound_path = f"/webhook/whatsapp/{cust}"
        status_path = f"/webhook/whatsapp/{cust}/status"

        # 1. Receive inbound → EA replies → message queued
        in_data = {
            "MessageSid": "SMin",
            "From": "whatsapp:+15559999999",
            "To": f"whatsapp:{TEST_WA_NUMBER}",
            "Body": "start",
        }
        in_sig = twilio_sign(f"{PUBLIC_BASE}{inbound_path}", in_data)

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(inbound_path, data=in_data, headers={"X-Twilio-Signature": in_sig})
        assert r.status_code == 200

        # Grab the outbound message id from channel tracking
        ch = manager._channels[cust]
        assert len(ch._status) == 1
        out_id = next(iter(ch._status.keys()))
        assert ch._status[out_id].state == DeliveryState.QUEUED

        # 2. Twilio sends status: sent
        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            st_data = {"MessageSid": out_id, "MessageStatus": "sent"}
            st_sig = twilio_sign(f"{PUBLIC_BASE}{status_path}", st_data)
            client.post(status_path, data=st_data, headers={"X-Twilio-Signature": st_sig})

        assert ch._status[out_id].state == DeliveryState.SENT

        # 3. Twilio sends status: delivered
        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            st_data = {"MessageSid": out_id, "MessageStatus": "delivered"}
            st_sig = twilio_sign(f"{PUBLIC_BASE}{status_path}", st_data)
            client.post(status_path, data=st_data, headers={"X-Twilio-Signature": st_sig})

        assert ch._status[out_id].state == DeliveryState.DELIVERED

        # 4. Twilio sends status: read
        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            st_data = {"MessageSid": out_id, "MessageStatus": "read"}
            st_sig = twilio_sign(f"{PUBLIC_BASE}{status_path}", st_data)
            client.post(status_path, data=st_data, headers={"X-Twilio-Signature": st_sig})

        assert ch._status[out_id].state == DeliveryState.READ

    def test_status_callback_signature_validated(self, client):
        path = "/webhook/whatsapp/cust-x/status"
        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(
                path,
                data={"MessageSid": "SM1", "MessageStatus": "delivered"},
                headers={"X-Twilio-Signature": "forged"},
            )
        assert r.status_code == 403


# -------------------------------------------------------------------
# Multi-tenant isolation
# -------------------------------------------------------------------

@pytest.mark.integration
class TestMultiTenantIsolation:
    def test_same_phone_different_customers_get_different_conversations(
        self, client, handler_log
    ):
        phone = "+15557777777"
        form_a = {
            "MessageSid": "SMa", "From": f"whatsapp:{phone}",
            "To": f"whatsapp:{TEST_WA_NUMBER}", "Body": "msg to A",
        }
        form_b = {
            "MessageSid": "SMb", "From": f"whatsapp:{phone}",
            "To": f"whatsapp:{TEST_WA_NUMBER}", "Body": "msg to B",
        }

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            sig_a = twilio_sign(f"{PUBLIC_BASE}/webhook/whatsapp/tenant-A", form_a)
            client.post("/webhook/whatsapp/tenant-A", data=form_a,
                        headers={"X-Twilio-Signature": sig_a})

            sig_b = twilio_sign(f"{PUBLIC_BASE}/webhook/whatsapp/tenant-B", form_b)
            client.post("/webhook/whatsapp/tenant-B", data=form_b,
                        headers={"X-Twilio-Signature": sig_b})

        assert len(handler_log) == 2
        msg_a, msg_b = handler_log
        assert msg_a.customer_id == "tenant-A"
        assert msg_b.customer_id == "tenant-B"
        assert msg_a.conversation_id != msg_b.conversation_id
        # Same phone though
        assert msg_a.from_number == msg_b.from_number == phone


# -------------------------------------------------------------------
# Wire contract: Twilio form data shape
# -------------------------------------------------------------------

@pytest.mark.integration
class TestTwilioWireContract:
    def test_media_message_parsed(self, client, handler_log):
        path = "/webhook/whatsapp/cust-media"
        form_data = {
            "MessageSid": "MMmedia001",
            "From": "whatsapp:+15551234567",
            "To": f"whatsapp:{TEST_WA_NUMBER}",
            "Body": "",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/img123.jpg",
            "MediaContentType0": "image/jpeg",
        }
        sig = twilio_sign(f"{PUBLIC_BASE}{path}", form_data)

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(path, data=form_data, headers={"X-Twilio-Signature": sig})

        assert r.status_code == 200
        assert len(handler_log) == 1
        assert "https://api.twilio.com/media/img123.jpg" in handler_log[0].metadata["media_urls"]

    def test_empty_body_still_reaches_handler(self, client, handler_log):
        """Empty Body is a valid Twilio payload (e.g. media-only message).
        Must still route to the handler; handler decides what to do."""
        path = "/webhook/whatsapp/cust-empty"
        form_data = {
            "MessageSid": "SMempty",
            "From": "whatsapp:+15551234567",
            "To": f"whatsapp:{TEST_WA_NUMBER}",
            "Body": "",
            "NumMedia": "0",
        }
        sig = twilio_sign(f"{PUBLIC_BASE}{path}", form_data)

        with patch.dict(os.environ, {"WEBHOOK_PUBLIC_BASE_URL": PUBLIC_BASE}):
            r = client.post(path, data=form_data, headers={"X-Twilio-Signature": sig})

        assert r.status_code == 200
        # Handler WAS called — empty body is the handler's decision, not the channel's
        assert len(handler_log) == 1
        assert handler_log[0].content == ""
        assert handler_log[0].from_number == "+15551234567"
        assert handler_log[0].message_id == "SMempty"
