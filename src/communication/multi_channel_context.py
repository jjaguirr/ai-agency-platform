"""
Multi-Channel Context Manager

Core system for seamless context handoffs between communication channels
(email, WhatsApp, voice) with unified customer understanding and <500ms performance.

This module provides:
- Seamless context transitions between channels
- Channel-specific adaptation and transformation
- Real-time context synchronization
- Personality-aware context preservation
- Cross-channel conversation threading
"""

import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

from ..memory.unified_context_store import (
    UnifiedContextStore,
    ContextEntry,
    ConversationThread,
    ContextNotFoundError,
    ContextStorageError
)
from .channel_adapters import (
    EmailChannelAdapter,
    WhatsAppChannelAdapter,
    VoiceChannelAdapter,
    ChannelAdapterError
)
from ..integrations.personality_engine_integration import PersonalityEngineConnector


logger = logging.getLogger(__name__)


class ContextTransitionError(Exception):
    """Raised when context transition between channels fails"""
    pass


class ContextRetrievalTimeoutError(Exception):
    """Raised when context retrieval exceeds timeout threshold"""
    pass


@dataclass
class ChannelTransitionResult:
    """Result of channel transition operation"""
    success: bool
    target_channel: str
    conversation_thread: str
    context_summary: str
    adapted_content: str
    personality_applied: Dict[str, Any]
    transition_time_ms: float
    customer_preferences: Dict[str, Any]
    business_context: Dict[str, Any]
    error: Optional[str] = None


@dataclass
class ContextRetrievalResult:
    """Result of context retrieval operation"""
    success: bool
    context: Optional[ContextEntry]
    retrieval_time_ms: float
    source: str  # "cache", "database", "fallback"
    error: Optional[str] = None


class MultiChannelContextManager:
    """
    Multi-channel context preservation and transition system
    
    Features:
    - <500ms context retrieval and injection
    - Seamless channel transitions with personality adaptation
    - Real-time context synchronization across channels
    - Business context preservation
    - Customer preference maintenance
    - Cross-channel conversation threading
    """
    
    def __init__(
        self,
        context_store: UnifiedContextStore = None,
        personality_connector: PersonalityEngineConnector = None,
        performance_target_ms: int = 500
    ):
        self.context_store = context_store or UnifiedContextStore()
        self.personality_connector = personality_connector or PersonalityEngineConnector()
        self.performance_target_ms = performance_target_ms
        
        # Initialize channel adapters
        self.channel_adapters = {
            "email": EmailChannelAdapter(
                personality_engine=self.personality_connector,
                performance_target_ms=performance_target_ms
            ),
            "whatsapp": WhatsAppChannelAdapter(
                personality_engine=self.personality_connector,
                performance_target_ms=performance_target_ms
            ),
            "voice": VoiceChannelAdapter(
                personality_engine=self.personality_connector,
                performance_target_ms=performance_target_ms
            )
        }
        
        # Performance tracking
        self.transition_stats = {
            "total_transitions": 0,
            "successful_transitions": 0,
            "average_transition_time_ms": 0,
            "channel_transition_counts": {
                "email_to_whatsapp": 0,
                "whatsapp_to_email": 0,
                "voice_to_whatsapp": 0,
                "whatsapp_to_voice": 0,
                "email_to_voice": 0,
                "voice_to_email": 0
            }
        }
    
    async def initialize(self):
        """Initialize context manager and dependencies"""
        try:
            # Initialize context store
            await self.context_store.initialize()
            
            # Initialize personality connector
            await self.personality_connector.initialize()
            
            # Initialize channel adapters
            for adapter in self.channel_adapters.values():
                await adapter.initialize()
            
            logger.info("MultiChannelContextManager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize MultiChannelContextManager: {e}")
            raise ContextStorageError(f"Initialization failed: {e}")
    
    async def store_conversation_context(self, context: Dict[str, Any]) -> bool:
        """
        Store conversation context for a specific channel
        
        Args:
            context: Context data including channel, customer_id, content, etc.
            
        Returns:
            True if storage successful
        """
        try:
            # Convert to ContextEntry
            context_entry = ContextEntry(
                customer_id=context["customer_id"],
                channel=context["channel"],
                conversation_thread=context.get("conversation_thread", f"thread_{int(time.time())}"),
                timestamp=context.get("timestamp", datetime.now()),
                content=context["content"],
                metadata=context.get("metadata", {})
            )
            
            # Store in unified context store
            result = await self.context_store.store_context(context_entry)
            
            if result.success:
                logger.debug(f"Context stored for {context['customer_id']} on {context['channel']}")
                return True
            else:
                logger.error(f"Context storage failed: {result.error}")
                return False
                
        except Exception as e:
            logger.error(f"Context storage error: {e}")
            return False
    
    async def get_channel_context(
        self,
        customer_id: str,
        channel: str,
        thread_id: Optional[str] = None,
        timeout: float = None
    ) -> Dict[str, Any]:
        """
        Retrieve context for specific customer and channel
        
        Args:
            customer_id: Customer identifier
            channel: Communication channel
            thread_id: Optional conversation thread ID
            timeout: Optional timeout in seconds
            
        Returns:
            Dictionary with context information
        """
        start_time = time.time()
        timeout = timeout or (self.performance_target_ms / 1000)
        
        try:
            # Get context from store
            context_entry = await self.context_store.get_context(
                customer_id=customer_id,
                channel=channel,
                thread_id=thread_id,
                timeout=timeout
            )
            
            # Get business context
            business_context = await self._get_business_context(customer_id)
            
            # Get customer preferences
            preferences = await self._get_customer_preferences(customer_id)
            
            # Generate context summary
            context_summary = await self._generate_context_summary(context_entry)
            
            retrieval_time = (time.time() - start_time) * 1000
            
            return {
                "customer_id": customer_id,
                "channel": channel,
                "conversation_thread": context_entry.conversation_thread,
                "content": context_entry.content,
                "metadata": context_entry.metadata,
                "context_summary": context_summary,
                "business_context": business_context,
                "customer_preferences": preferences,
                "timestamp": context_entry.timestamp,
                "retrieval_time_ms": retrieval_time
            }
            
        except ContextNotFoundError:
            # Return empty context for new conversations
            return {
                "customer_id": customer_id,
                "channel": channel,
                "conversation_thread": thread_id or f"new_thread_{int(time.time())}",
                "content": "",
                "metadata": {},
                "context_summary": "",
                "business_context": await self._get_business_context(customer_id),
                "customer_preferences": await self._get_customer_preferences(customer_id),
                "timestamp": datetime.now(),
                "retrieval_time_ms": (time.time() - start_time) * 1000
            }
    
    async def transition_channel(
        self,
        customer_id: str,
        from_channel: str,
        to_channel: str,
        new_message: str,
        thread_id: Optional[str] = None,
        personality_adaptation: bool = True
    ) -> Dict[str, Any]:
        """
        Seamlessly transition conversation context between channels
        
        Args:
            customer_id: Customer identifier
            from_channel: Source communication channel
            to_channel: Target communication channel
            new_message: New message in target channel
            thread_id: Optional conversation thread ID
            personality_adaptation: Whether to apply personality adaptation
            
        Returns:
            Adapted context for target channel
        """
        start_time = time.time()
        
        try:
            # Track transition attempt
            transition_key = f"{from_channel}_to_{to_channel}"
            self.transition_stats["total_transitions"] += 1
            self.transition_stats["channel_transition_counts"][transition_key] = (
                self.transition_stats["channel_transition_counts"].get(transition_key, 0) + 1
            )
            
            # Get source context
            source_context = await self.get_channel_context(
                customer_id=customer_id,
                channel=from_channel,
                thread_id=thread_id
            )
            
            # Get appropriate channel adapter
            source_adapter = self.channel_adapters[from_channel]
            
            # Adapt context to target channel
            adapted_context = await source_adapter.adapt_to_channel(
                context=source_context,
                target_channel=to_channel
            )
            
            # Apply personality adaptation if requested
            personality_applied = {}
            if personality_adaptation:
                personality_applied = await self._apply_personality_adaptation(
                    customer_id=customer_id,
                    context=adapted_context,
                    target_channel=to_channel
                )
                adapted_context.update(personality_applied)
            
            # Store new message in target channel
            new_context = {
                "customer_id": customer_id,
                "channel": to_channel,
                "conversation_thread": adapted_context["conversation_thread"],
                "content": new_message,
                "metadata": {
                    **adapted_context["metadata"],
                    "transition_from": from_channel,
                    "adapted_at": datetime.now().isoformat()
                }
            }
            
            await self.store_conversation_context(new_context)
            
            transition_time = (time.time() - start_time) * 1000
            
            # Update performance stats
            self.transition_stats["successful_transitions"] += 1
            self.transition_stats["average_transition_time_ms"] = (
                (self.transition_stats["average_transition_time_ms"] * 
                 (self.transition_stats["successful_transitions"] - 1) + transition_time) /
                self.transition_stats["successful_transitions"]
            )
            
            logger.debug(
                f"Channel transition {from_channel}→{to_channel} completed in {transition_time:.2f}ms"
            )
            
            return {
                "customer_id": customer_id,
                "channel": to_channel,
                "conversation_thread": adapted_context["conversation_thread"],
                "content": adapted_context.get("adapted_content", adapted_context["content"]),
                "context_summary": adapted_context["context_summary"],
                "personality_applied": personality_applied,
                "customer_preferences": adapted_context["customer_preferences"],
                "business_context": adapted_context["business_context"],
                "metadata": adapted_context["metadata"],
                "transition_time_ms": transition_time
            }
            
        except Exception as e:
            transition_time = (time.time() - start_time) * 1000
            logger.error(f"Channel transition failed in {transition_time:.2f}ms: {e}")
            
            raise ContextTransitionError(
                f"Failed to transition from {from_channel} to {to_channel}: {e}"
            )
    
    async def get_conversation_thread(
        self,
        customer_id: str,
        thread_id: str
    ) -> Dict[str, Any]:
        """
        Get complete conversation thread across all channels
        
        Args:
            customer_id: Customer identifier
            thread_id: Conversation thread identifier
            
        Returns:
            Complete conversation thread with cross-channel messages
        """
        start_time = time.time()
        
        try:
            # Get thread from context store
            thread = await self.context_store.get_conversation_thread(
                customer_id=customer_id,
                thread_id=thread_id
            )
            
            # Get chronological entries
            chronological_entries = thread.get_chronological_entries()
            
            # Generate thread summary
            thread_summary = thread.generate_summary()
            
            # Get business context
            business_context = await self._get_business_context(customer_id)
            
            retrieval_time = (time.time() - start_time) * 1000
            
            return {
                "thread_id": thread_id,
                "customer_id": customer_id,
                "channels_involved": thread.channels,
                "messages": [
                    {
                        "message_id": entry.entry_id,
                        "channel": entry.channel,
                        "content": entry.content,
                        "timestamp": entry.timestamp.isoformat(),
                        "metadata": entry.metadata
                    }
                    for entry in chronological_entries
                ],
                "thread_summary": thread_summary,
                "business_context": business_context,
                "retrieval_time_ms": retrieval_time
            }
            
        except Exception as e:
            logger.error(f"Thread retrieval failed: {e}")
            raise ContextStorageError(f"Thread retrieval failed: {e}")
    
    async def update_business_context(
        self,
        customer_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update business context for real-time synchronization
        
        Args:
            customer_id: Customer identifier
            updates: Business context updates
            
        Returns:
            True if successful
        """
        try:
            # Update in context store
            success = await self.context_store.update_business_context(
                customer_id=customer_id,
                updates=updates
            )
            
            if success:
                logger.debug(f"Business context updated for customer {customer_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Business context update failed: {e}")
            return False
    
    async def _get_business_context(self, customer_id: str) -> Dict[str, Any]:
        """Get business context for customer"""
        try:
            # Get from cache or database
            # (Implementation would depend on business context storage)
            return {
                "current_projects": [],
                "priorities": [],
                "goals": [],
                "preferences": {}
            }
        except Exception:
            return {}
    
    async def _get_customer_preferences(self, customer_id: str) -> Dict[str, Any]:
        """Get customer communication preferences"""
        try:
            # Get from customer profile store
            # (Implementation would depend on customer profile storage)
            return {
                "communication_style": "premium_casual",
                "formality_level": "approachable_professional",
                "response_length": "concise_detailed",
                "preferred_channels": ["whatsapp", "email", "voice"]
            }
        except Exception:
            return {}
    
    async def _generate_context_summary(self, context_entry: ContextEntry) -> str:
        """Generate context summary for conversation"""
        try:
            # Use personality engine to generate intelligent summary
            if self.personality_connector:
                summary = await self.personality_connector.generate_context_summary(
                    content=context_entry.content,
                    metadata=context_entry.metadata
                )
                return summary
            
            # Fallback to simple summary
            content = context_entry.content
            if len(content) > 100:
                return content[:97] + "..."
            return content
            
        except Exception:
            return context_entry.content[:100] + "..." if len(context_entry.content) > 100 else context_entry.content
    
    async def _apply_personality_adaptation(
        self,
        customer_id: str,
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """Apply personality-aware adaptation for target channel"""
        try:
            if not self.personality_connector:
                return {}
            
            # Get customer personality profile
            personality_profile = await self.personality_connector.get_customer_personality(
                customer_id=customer_id
            )
            
            # Apply personality adaptation
            adaptation_result = await self.personality_connector.adapt_personality_for_channel(
                personality_profile=personality_profile,
                context=context,
                target_channel=target_channel
            )
            
            return {
                "personality_applied": adaptation_result,
                "tone": adaptation_result.get("tone", "professional"),
                "formality_level": adaptation_result.get("formality_level", "professional"),
                "adapted_content": adaptation_result.get("adapted_content", context["content"])
            }
            
        except Exception as e:
            logger.warning(f"Personality adaptation failed: {e}")
            return {}
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for monitoring"""
        context_store_stats = await self.context_store.get_performance_stats()
        
        return {
            "transition_stats": self.transition_stats,
            "context_store_stats": context_store_stats,
            "performance_target_ms": self.performance_target_ms,
            "sla_compliance": {
                "transition_time_sla_met": (
                    self.transition_stats["average_transition_time_ms"] < self.performance_target_ms
                ),
                "context_retrieval_sla_met": context_store_stats.get("performance_sla_met", False)
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all components"""
        health_status = {
            "overall_status": "healthy",
            "components": {},
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            # Check context store
            try:
                test_context = ContextEntry(
                    customer_id="health_check_customer",
                    channel="email",
                    conversation_thread="health_check",
                    timestamp=datetime.now(),
                    content="Health check test"
                )
                result = await self.context_store.store_context(test_context)
                health_status["components"]["context_store"] = {
                    "status": "healthy" if result.success else "unhealthy",
                    "response_time_ms": result.storage_time_ms
                }
            except Exception as e:
                health_status["components"]["context_store"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
            
            # Check personality connector
            try:
                personality_status = await self.personality_connector.health_check()
                health_status["components"]["personality_engine"] = personality_status
            except Exception as e:
                health_status["components"]["personality_engine"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
            
            # Check channel adapters
            for channel, adapter in self.channel_adapters.items():
                try:
                    adapter_status = await adapter.health_check()
                    health_status["components"][f"{channel}_adapter"] = adapter_status
                except Exception as e:
                    health_status["components"][f"{channel}_adapter"] = {
                        "status": "unhealthy",
                        "error": str(e)
                    }
            
            # Determine overall status
            component_statuses = [
                comp.get("status", "unhealthy") 
                for comp in health_status["components"].values()
            ]
            
            if all(status == "healthy" for status in component_statuses):
                health_status["overall_status"] = "healthy"
            elif any(status == "healthy" for status in component_statuses):
                health_status["overall_status"] = "degraded"
            else:
                health_status["overall_status"] = "unhealthy"
            
        except Exception as e:
            health_status["overall_status"] = "unhealthy"
            health_status["error"] = str(e)
        
        return health_status
    
    async def close(self):
        """Clean shutdown of all components"""
        try:
            # Close context store
            await self.context_store.close()
            
            # Close personality connector
            if self.personality_connector:
                await self.personality_connector.close()
            
            # Close channel adapters
            for adapter in self.channel_adapters.values():
                await adapter.close()
            
            logger.info("MultiChannelContextManager closed successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")


# Convenience functions for common operations
async def quick_channel_transition(
    customer_id: str,
    from_channel: str,
    to_channel: str,
    message: str,
    context_manager: MultiChannelContextManager = None
) -> Dict[str, Any]:
    """
    Quick channel transition helper function
    
    Args:
        customer_id: Customer identifier
        from_channel: Source channel
        to_channel: Target channel
        message: New message
        context_manager: Optional context manager instance
        
    Returns:
        Transition result
    """
    if context_manager is None:
        context_manager = MultiChannelContextManager()
        await context_manager.initialize()
    
    try:
        result = await context_manager.transition_channel(
            customer_id=customer_id,
            from_channel=from_channel,
            to_channel=to_channel,
            new_message=message
        )
        return result
    finally:
        if context_manager:
            await context_manager.close()


async def get_customer_conversation_history(
    customer_id: str,
    hours: int = 24,
    context_manager: MultiChannelContextManager = None
) -> List[Dict[str, Any]]:
    """
    Get recent conversation history across all channels
    
    Args:
        customer_id: Customer identifier
        hours: Number of hours to look back
        context_manager: Optional context manager instance
        
    Returns:
        List of recent conversations
    """
    if context_manager is None:
        context_manager = MultiChannelContextManager()
        await context_manager.initialize()
    
    try:
        # Get customer context
        customer_context = await context_manager.context_store.get_customer_context(customer_id)
        
        # Get recent activity
        recent_activity = customer_context.get_recent_activity(hours=hours)
        
        return [
            {
                "channel": entry.channel,
                "content": entry.content,
                "timestamp": entry.timestamp.isoformat(),
                "thread": entry.conversation_thread,
                "metadata": entry.metadata
            }
            for entry in recent_activity
        ]
        
    finally:
        if context_manager:
            await context_manager.close()