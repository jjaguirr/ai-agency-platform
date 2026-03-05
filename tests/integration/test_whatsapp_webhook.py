"""
Integration test: full inbound flow with real Twilio provider parsing,
real signature computation, and mocked EA + outbound HTTP.
"""
import asyncio
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

    # Replace provider with one using our mock HTTP transport
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
        status = asyncio.run(mgr.store.get_status("SM_reply_1"))
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

        status = asyncio.run(mgr.store.get_status("SM_tracked_out"))
        assert status == MessageStatus.DELIVERED
