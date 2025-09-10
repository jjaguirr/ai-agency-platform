# Multi-Channel Context Preservation System

"""
Multi-Channel Context Preservation System

Implementation of seamless context handoffs between communication channels
(email, WhatsApp, voice) with unified customer understanding.

Core Features:
- Unified conversation context store
- Channel-specific adaptation layer  
- Real-time context synchronization
- Context retrieval and injection system
- Cross-channel conversation threading
- <500ms performance target

Architecture Components:
- UnifiedContextStore: High-performance context storage and retrieval
- MultiChannelContextManager: Core context preservation and transition system
- ChannelAdapters: Channel-specific content transformation
- PersonalityEngineIntegration: Context-aware personality adaptation
"""

from .memory.unified_context_store import (
    UnifiedContextStore,
    ContextEntry,
    ConversationThread,
    CustomerContext
)

from .communication.multi_channel_context import (
    MultiChannelContextManager,
    ContextTransitionError,
    ContextRetrievalTimeoutError
)

from .communication.channel_adapters import (
    EmailChannelAdapter,
    WhatsAppChannelAdapter,
    VoiceChannelAdapter,
    get_channel_adapter
)

from .integrations.personality_engine_integration import (
    PersonalityEngineConnector,
    MockPersonalityEngine,
    create_personality_engine_connector
)

__version__ = "1.0.0"
__all__ = [
    # Core context management
    "UnifiedContextStore",
    "ContextEntry", 
    "ConversationThread",
    "CustomerContext",
    "MultiChannelContextManager",
    
    # Channel adapters
    "EmailChannelAdapter",
    "WhatsAppChannelAdapter", 
    "VoiceChannelAdapter",
    "get_channel_adapter",
    
    # Personality integration
    "PersonalityEngineConnector",
    "MockPersonalityEngine",
    "create_personality_engine_connector",
    
    # Exceptions
    "ContextTransitionError",
    "ContextRetrievalTimeoutError"
]