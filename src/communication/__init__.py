"""
AI Agency Platform - Communication Channels Module
Multi-channel communication system for Executive Assistant interactions
"""

from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType
from .whatsapp_channel import WhatsAppChannel

__all__ = [
    "BaseCommunicationChannel",
    "BaseMessage",
    "ChannelType",
    "WhatsAppChannel",
]
