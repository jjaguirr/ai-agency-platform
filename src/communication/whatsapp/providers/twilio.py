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

    # --- Signature validation ---------------------------------------------

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

    # --- Stubs for Tasks 5-6 ----------------------------------------------

    async def send_text(self, to: str, body: str, from_: str) -> SendResult:
        raise NotImplementedError

    def parse_webhook(self, body: bytes, content_type: str) -> list[WebhookEvent]:
        raise NotImplementedError

    async def fetch_status(self, provider_message_id: str) -> MessageStatus:
        raise NotImplementedError
