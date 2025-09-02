"""
AI Agency Platform - Communication Channels Module
Multi-channel communication system for Executive Assistant interactions
"""

from .whatsapp_channel import WhatsAppChannel, WhatsAppMessage
from .base_channel import BaseCommunicationChannel, ChannelType

__all__ = [
    'WhatsAppChannel',
    'WhatsAppMessage', 
    'BaseCommunicationChannel',
    'ChannelType'
]