"""
WhatsApp channel implementation.

Implements BaseCommunicationChannel; delegates all provider-specific work
(API calls, webhook parsing, signature validation) to an injected
WhatsAppProvider. The channel owns:

- Conversation threading (phone + customer → deterministic conversation_id)
- Outbound message status tracking (in-memory)
- The parse → handler → reply pipeline

This makes the provider swappable without touching channel code.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType
from .providers.base_provider import (
    DeliveryState,
    MessageStatus,
    WhatsAppProvider,
)

logger = logging.getLogger(__name__)

# A message_handler takes a parsed BaseMessage and returns the reply text.
# Typically wraps ExecutiveAssistant.handle_customer_interaction.
MessageHandler = Callable[[BaseMessage], Awaitable[str]]


class WhatsAppChannel(BaseCommunicationChannel):
    """
    WhatsApp channel backed by a pluggable WhatsAppProvider.

    Args:
        customer_id: Tenant identifier. Part of the conversation threading key.
        provider: Concrete WhatsAppProvider (Twilio, Meta, etc). Required.
        message_handler: Optional async callback invoked for each inbound
            message. Receives a BaseMessage, returns the reply text. If not
            provided, process_inbound() only parses and returns the message.
        config: Passed through to BaseCommunicationChannel.
    """

    def __init__(
        self,
        customer_id: str,
        provider: WhatsAppProvider,
        message_handler: Optional[MessageHandler] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        if provider is None:
            raise ValueError("WhatsAppChannel requires a provider")
        super().__init__(customer_id, config)
        self.provider = provider
        self.message_handler = message_handler
        # In-memory status store: message_id → MessageStatus
        self._status: Dict[str, MessageStatus] = {}

    def _get_channel_type(self) -> ChannelType:
        return ChannelType.WHATSAPP

    async def initialize(self) -> bool:
        self.is_initialized = True
        return True

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send_message(self, to: str, content: str, **kwargs) -> str:
        msg_id = await self.provider.send_text(to, content)
        self._status[msg_id] = MessageStatus(
            provider_message_id=msg_id,
            state=DeliveryState.QUEUED,
            timestamp=datetime.now(),
        )
        logger.debug(
            "WhatsApp out: customer=%s id=%s to=%s", self.customer_id, msg_id, to
        )
        return msg_id

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    async def handle_incoming_message(
        self, message_data: Dict[str, Any]
    ) -> BaseMessage:
        """Parse a provider webhook payload into a BaseMessage.

        Does NOT call the handler or send a reply — that's process_inbound().
        Use this when you only need the parsed message.
        """
        inbound = self.provider.parse_incoming_webhook(message_data)
        conversation_id = self._conversation_id_for(inbound.from_phone)

        return BaseMessage(
            content=inbound.body,
            from_number=inbound.from_phone,
            to_number=inbound.to_phone,
            channel=ChannelType.WHATSAPP,
            message_id=inbound.provider_message_id,
            conversation_id=conversation_id,
            timestamp=inbound.timestamp,
            customer_id=self.customer_id,
            metadata={
                "media_urls": inbound.media_urls,
                "profile_name": inbound.profile_name,
                "raw": inbound.raw,
            },
        )

    async def process_inbound(self, message_data: Dict[str, Any]) -> BaseMessage:
        """Full pipeline: parse → invoke handler → send reply.

        If no message_handler is set, parses and returns the message without
        replying. If handler returns an empty/None response, no reply is sent.
        """
        base_msg = await self.handle_incoming_message(message_data)

        if self.message_handler is None:
            return base_msg

        reply = await self.message_handler(base_msg)
        if reply:
            await self.send_message(base_msg.from_number, reply)

        return base_msg

    # ------------------------------------------------------------------
    # Conversation threading
    # ------------------------------------------------------------------

    def _conversation_id_for(self, phone: str) -> str:
        """Deterministic conversation ID from customer_id + phone.

        Using a hash means:
        - Same phone + customer always maps to the same conversation
        - Raw phone number is not exposed in the conversation_id
        - Cross-tenant isolation (same phone, different customer → different id)
        """
        key = f"{self.customer_id}:{phone}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]

    # ------------------------------------------------------------------
    # Signature validation
    # ------------------------------------------------------------------

    async def validate_webhook_signature(
        self,
        url: str = "",
        form_data: Optional[Dict[str, Any]] = None,
        signature: Optional[str] = None,
        # Legacy BaseCommunicationChannel signature (payload: str, signature: str)
        # is satisfied by named args above; we accept the richer form because
        # real signature algorithms (Twilio) need the URL and parsed params.
        **_: Any,
    ) -> bool:
        return self.provider.validate_signature(
            url=url, form_data=form_data or {}, signature=signature
        )

    # ------------------------------------------------------------------
    # Status tracking
    # ------------------------------------------------------------------

    async def handle_status_callback(
        self, callback_data: Dict[str, Any]
    ) -> MessageStatus:
        """Parse a delivery status callback and update internal tracking."""
        status = self.provider.parse_status_callback(callback_data)
        self._status[status.provider_message_id] = status
        logger.debug(
            "WhatsApp status: customer=%s id=%s state=%s",
            self.customer_id,
            status.provider_message_id,
            status.state.value,
        )
        return status

    async def get_message_status(
        self, message_id: str, fetch: bool = False
    ) -> Dict[str, Any]:
        """Get delivery status for a sent message.

        Args:
            message_id: Provider message ID.
            fetch: If True and no cached status, actively query the provider.
        """
        status = self._status.get(message_id)
        if status is None and fetch:
            status = await self.provider.fetch_message_status(message_id)
            self._status[message_id] = status

        if status is None:
            return {
                "message_id": message_id,
                "status": "unknown",
                "timestamp": datetime.now().isoformat(),
            }

        return {
            "message_id": status.provider_message_id,
            "status": status.state.value,
            "timestamp": status.timestamp.isoformat(),
            "error_code": status.error_code,
            "error_message": status.error_message,
        }

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> Dict[str, Any]:
        base = await super().health_check()
        base["provider"] = type(self.provider).__name__
        base["tracked_messages"] = len(self._status)
        return base
