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
