"""
WhatsApp provider registry + factory.

Adding a new provider:
1. Implement WhatsAppProvider (see base_provider.py)
2. Add to PROVIDER_REGISTRY below

No channel/manager/webhook changes required.
"""
from typing import Any, Dict, Type

from .base_provider import (
    DeliveryState,
    InboundMessage,
    MessageStatus,
    ProviderError,
    WhatsAppProvider,
)
from .twilio_provider import TwilioWhatsAppProvider

PROVIDER_REGISTRY: Dict[str, Type[WhatsAppProvider]] = {
    "twilio": TwilioWhatsAppProvider,
}


def create_provider(name: str, config: Dict[str, Any]) -> WhatsAppProvider:
    """Instantiate a provider by name.

    Args:
        name: Provider key (case-insensitive). See PROVIDER_REGISTRY.
        config: Kwargs passed to the provider's __init__.

    Raises:
        ValueError: Unknown provider name.
    """
    key = name.lower().strip()
    if key not in PROVIDER_REGISTRY:
        known = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(f"Unknown WhatsApp provider '{name}'. Known: {known}")
    provider_cls = PROVIDER_REGISTRY[key]
    return provider_cls(**config)


__all__ = [
    "WhatsAppProvider",
    "InboundMessage",
    "MessageStatus",
    "DeliveryState",
    "ProviderError",
    "TwilioWhatsAppProvider",
    "PROVIDER_REGISTRY",
    "create_provider",
]
