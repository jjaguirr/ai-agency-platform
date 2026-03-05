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

    @property
    def webhook_url(self) -> str:
        """Canonical public URL that Twilio/provider is configured to call.

        Used for signature validation — the server must validate against the
        URL the provider signed, not whatever FastAPI reconstructs behind a
        proxy. Empty string means 'not configured, fall back to request URL'.
        """
        return self._webhook_url

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
