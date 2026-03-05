"""
Backward-compat shim. All implementation moved to src/communication/whatsapp/.

Old: WhatsAppChannel was Twilio-hardcoded with direct DB/Redis deps.
New: WhatsAppChannel delegates to a WhatsAppProvider; see whatsapp/channel.py.
"""
from .whatsapp.channel import WhatsAppChannel
from .whatsapp.provider import IncomingMessage as WhatsAppMessage

__all__ = ["WhatsAppChannel", "WhatsAppMessage"]
