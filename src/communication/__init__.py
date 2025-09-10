"""
AI Agency Platform - Communication Channels Module
Multi-channel communication system for Executive Assistant interactions
"""

from .base_channel import BaseCommunicationChannel, ChannelType

# Import voice-specific modules
try:
    from .voice_channel import ElevenLabsVoiceChannel, VoiceLanguage, VoiceConfig, VoiceMessage
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

# Import WhatsApp functionality if available
try:
    from .whatsapp_channel import WhatsAppChannel, WhatsAppMessage
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False

__all__ = [
    'BaseCommunicationChannel',
    'ChannelType'
]

if VOICE_AVAILABLE:
    __all__.extend([
        'ElevenLabsVoiceChannel',
        'VoiceLanguage', 
        'VoiceConfig',
        'VoiceMessage'
    ])

if WHATSAPP_AVAILABLE:
    __all__.extend([
        'WhatsAppChannel',
        'WhatsAppMessage'
    ])