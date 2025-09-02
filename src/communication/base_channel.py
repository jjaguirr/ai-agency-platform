"""
Base Communication Channel Interface
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

class ChannelType(Enum):
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CHAT = "chat"
    SMS = "sms"

@dataclass
class BaseMessage:
    """Base message structure for all communication channels"""
    content: str
    from_number: str
    to_number: str
    channel: ChannelType
    message_id: str
    conversation_id: str
    timestamp: datetime
    customer_id: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

class BaseCommunicationChannel(ABC):
    """Base interface for all communication channels"""
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        self.customer_id = customer_id
        self.config = config or {}
        self.channel_type = self._get_channel_type()
        self.is_initialized = False
        
        logger.info(f"Initializing {self.channel_type.value} channel for customer {customer_id}")
    
    @abstractmethod
    def _get_channel_type(self) -> ChannelType:
        """Return the channel type for this implementation"""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the channel with necessary configurations"""
        pass
    
    @abstractmethod
    async def send_message(self, to: str, content: str, **kwargs) -> str:
        """Send a message through this channel"""
        pass
    
    @abstractmethod
    async def handle_incoming_message(self, message_data: Dict[str, Any]) -> BaseMessage:
        """Parse incoming message data into standardized format"""
        pass
    
    @abstractmethod
    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        """Validate webhook signature for security"""
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """Check channel health status"""
        return {
            "channel": self.channel_type.value,
            "customer_id": self.customer_id,
            "initialized": self.is_initialized,
            "timestamp": datetime.now().isoformat()
        }
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """Get status of a sent message"""
        return {
            "message_id": message_id,
            "status": "unknown",
            "timestamp": datetime.now().isoformat()
        }