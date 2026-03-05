"""
WhatsApp provider abstraction.

A WhatsAppProvider is the seam between the channel layer (which knows about
conversations, customers, BaseMessage) and a concrete WhatsApp API backend
(Twilio, Meta Cloud API, etc).

The channel layer talks only to this interface; swapping providers requires
zero changes to WhatsAppChannel / WhatsAppManager / webhook_server.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DeliveryState(Enum):
    """Normalized message delivery lifecycle states across all providers."""

    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class InboundMessage:
    """Provider-normalized inbound WhatsApp message.

    Channel layer converts this to a BaseMessage (which adds channel,
    conversation_id, customer_id). Keeping these separate means providers
    don't need to know about the channel's threading model.
    """

    provider_message_id: str
    from_phone: str
    to_phone: str
    body: str
    timestamp: datetime
    media_urls: List[str] = field(default_factory=list)
    profile_name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MessageStatus:
    """Normalized delivery status for an outbound message."""

    provider_message_id: str
    state: DeliveryState
    timestamp: datetime
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Raised when a provider API call fails."""

    def __init__(self, message: str, provider_code: Optional[str] = None, http_status: Optional[int] = None):
        super().__init__(message)
        self.provider_code = provider_code
        self.http_status = http_status


class WhatsAppProvider(ABC):
    """
    Abstract base for WhatsApp messaging backends.

    Implementations: TwilioWhatsAppProvider (Twilio WhatsApp API),
    future: MetaCloudAPIProvider (Meta WhatsApp Cloud API), etc.

    All methods are provider-specific translation — no business logic.
    """

    @abstractmethod
    async def send_text(self, to: str, body: str) -> str:
        """Send a text message. Returns the provider's message ID.

        Args:
            to: Recipient phone number in E.164 format (+15551234567).
                Provider impl handles any required prefixing.
            body: Message text.

        Returns:
            Provider-issued message ID (e.g. Twilio SID).

        Raises:
            ProviderError: API call failed.
        """
        ...

    @abstractmethod
    def parse_incoming_webhook(self, form_data: Dict[str, Any]) -> InboundMessage:
        """Convert provider-specific webhook payload into normalized InboundMessage.

        Args:
            form_data: Already-parsed form/JSON body from the provider's webhook POST.

        Returns:
            InboundMessage with phone numbers stripped of provider prefixes.
        """
        ...

    @abstractmethod
    def parse_status_callback(self, form_data: Dict[str, Any]) -> MessageStatus:
        """Convert provider-specific status callback payload into MessageStatus.

        Args:
            form_data: Parsed status callback body.

        Returns:
            MessageStatus with normalized DeliveryState.
        """
        ...

    @abstractmethod
    def validate_signature(
        self, url: str, form_data: Dict[str, Any], signature: Optional[str]
    ) -> bool:
        """Validate the provider's webhook signature.

        Args:
            url: The full public URL that the provider POSTed to (including
                 scheme + host — must reflect what the provider sees, not what
                 the app server sees behind a reverse proxy).
            form_data: Parsed POST params (needed by some providers' sig algos).
            signature: Value of the provider's signature header. May be None/empty.

        Returns:
            True if the signature is valid. Must use constant-time comparison.
        """
        ...

    @abstractmethod
    async def fetch_message_status(self, message_id: str) -> MessageStatus:
        """Actively query the provider's API for current delivery status.

        Used for one-off checks when no status callback has arrived yet.

        Raises:
            ProviderError: message not found or API call failed.
        """
        ...
