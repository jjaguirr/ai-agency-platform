"""
Twilio WhatsApp provider implementation.

Uses httpx directly rather than the Twilio SDK:
- Native async (Twilio SDK's messages.create is sync)
- No vendor lock at the dependency level
- Easier to mock in tests

Twilio WhatsApp specifics handled here:
- Phone numbers require `whatsapp:` prefix in API calls
- Webhooks arrive as application/x-www-form-urlencoded
- Signature header is X-Twilio-Signature
- Signature algorithm: base64(HMAC-SHA1(auth_token, url + sorted(k+v)))
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from .base_provider import (
    DeliveryState,
    InboundMessage,
    MessageStatus,
    ProviderError,
    WhatsAppProvider,
)

logger = logging.getLogger(__name__)

_TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

# Twilio uses both 'failed' and 'undelivered' for failures
_STATUS_MAP: Dict[str, DeliveryState] = {
    "queued": DeliveryState.QUEUED,
    "accepted": DeliveryState.QUEUED,
    "sending": DeliveryState.QUEUED,
    "sent": DeliveryState.SENT,
    "delivered": DeliveryState.DELIVERED,
    "read": DeliveryState.READ,
    "failed": DeliveryState.FAILED,
    "undelivered": DeliveryState.FAILED,
}


def _ensure_whatsapp_prefix(phone: str) -> str:
    phone = phone.strip()
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


def _strip_whatsapp_prefix(phone: str) -> str:
    if phone.startswith("whatsapp:"):
        return phone[len("whatsapp:"):]
    return phone


class TwilioWhatsAppProvider(WhatsAppProvider):
    """WhatsApp via Twilio's WhatsApp Business API."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        whatsapp_number: str,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        if not account_sid or not auth_token or not whatsapp_number:
            raise ValueError(
                "TwilioWhatsAppProvider requires account_sid, auth_token, whatsapp_number"
            )
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.whatsapp_number = _strip_whatsapp_prefix(whatsapp_number)
        # Allow injecting a client for tests; otherwise create on first use
        self._client = http_client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                auth=(self.account_sid, self.auth_token),
                timeout=httpx.Timeout(15.0),
            )
        return self._client

    # ------------------------------------------------------------------
    # send_text
    # ------------------------------------------------------------------

    async def send_text(self, to: str, body: str) -> str:
        url = f"{_TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": _ensure_whatsapp_prefix(self.whatsapp_number),
            "To": _ensure_whatsapp_prefix(to),
            "Body": body,
        }

        client = self._get_client()
        # If client has no auth configured (injected test client), add it per-request
        auth = None if client.auth else (self.account_sid, self.auth_token)
        resp = await client.post(url, data=data, auth=auth)

        if resp.status_code >= 400:
            payload = _safe_json(resp)
            code = str(payload.get("code", "")) if payload else None
            msg = payload.get("message", resp.text) if payload else resp.text
            raise ProviderError(
                f"Twilio send failed: {msg} (code={code})",
                provider_code=code,
                http_status=resp.status_code,
            )

        result = resp.json()
        sid = result.get("sid")
        if not sid:
            raise ProviderError(f"Twilio response missing sid: {result}")
        logger.debug("Twilio send ok: sid=%s status=%s", sid, result.get("status"))
        return sid

    # ------------------------------------------------------------------
    # parse_incoming_webhook
    # ------------------------------------------------------------------

    def parse_incoming_webhook(self, form_data: Dict[str, Any]) -> InboundMessage:
        num_media = int(form_data.get("NumMedia", 0) or 0)
        media_urls = []
        for i in range(num_media):
            url = form_data.get(f"MediaUrl{i}")
            if url:
                media_urls.append(url)

        return InboundMessage(
            provider_message_id=form_data.get("MessageSid", ""),
            from_phone=_strip_whatsapp_prefix(form_data.get("From", "")),
            to_phone=_strip_whatsapp_prefix(form_data.get("To", "")),
            body=form_data.get("Body", ""),
            timestamp=datetime.now(),
            media_urls=media_urls,
            profile_name=form_data.get("ProfileName"),
            raw=dict(form_data),
        )

    # ------------------------------------------------------------------
    # parse_status_callback
    # ------------------------------------------------------------------

    def parse_status_callback(self, form_data: Dict[str, Any]) -> MessageStatus:
        twilio_status = form_data.get("MessageStatus", "").lower()
        state = _STATUS_MAP.get(twilio_status, DeliveryState.UNKNOWN)

        error_code = form_data.get("ErrorCode")
        error_msg = form_data.get("ErrorMessage")

        return MessageStatus(
            provider_message_id=form_data.get("MessageSid", ""),
            state=state,
            timestamp=datetime.now(),
            error_code=str(error_code) if error_code else None,
            error_message=error_msg,
            raw=dict(form_data),
        )

    # ------------------------------------------------------------------
    # validate_signature
    # ------------------------------------------------------------------

    def validate_signature(
        self, url: str, form_data: Dict[str, Any], signature: Optional[str]
    ) -> bool:
        """
        Twilio signature algorithm:
        1. Take the full URL that Twilio POSTed to (scheme + host + path + query)
        2. Sort POST params by key, append each key then value (no separator)
        3. HMAC-SHA1 the concatenated string using the auth_token as key
        4. Base64-encode the digest
        5. Compare against X-Twilio-Signature using constant-time comparison
        """
        if not signature:
            return False

        data = url
        for key in sorted(form_data.keys()):
            data += key + str(form_data[key])

        mac = hmac.new(
            self.auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        )
        expected = base64.b64encode(mac.digest()).decode("utf-8")

        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # fetch_message_status
    # ------------------------------------------------------------------

    async def fetch_message_status(self, message_id: str) -> MessageStatus:
        url = f"{_TWILIO_API_BASE}/Accounts/{self.account_sid}/Messages/{message_id}.json"
        client = self._get_client()
        auth = None if client.auth else (self.account_sid, self.auth_token)
        resp = await client.get(url, auth=auth)

        if resp.status_code >= 400:
            payload = _safe_json(resp)
            code = str(payload.get("code", "")) if payload else None
            msg = payload.get("message", resp.text) if payload else resp.text
            raise ProviderError(
                f"Twilio fetch status failed: {msg}",
                provider_code=code,
                http_status=resp.status_code,
            )

        result = resp.json()
        twilio_status = (result.get("status") or "").lower()
        state = _STATUS_MAP.get(twilio_status, DeliveryState.UNKNOWN)
        err = result.get("error_code")

        return MessageStatus(
            provider_message_id=result.get("sid", message_id),
            state=state,
            timestamp=datetime.now(),
            error_code=str(err) if err else None,
            error_message=result.get("error_message"),
            raw=result,
        )

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def _safe_json(resp: httpx.Response) -> Optional[Dict[str, Any]]:
    try:
        return resp.json()
    except Exception:
        return None
