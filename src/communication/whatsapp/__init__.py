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
