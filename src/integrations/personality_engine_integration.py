"""
Personality Engine Integration

Integration with the Personality Engine for context-aware transformations
and personality consistency across communication channels.

This module provides:
- Personality-aware context adaptation
- Cross-channel personality consistency
- Context summary generation
- Customer personality profiling
- Premium-casual personality application
"""

import asyncio
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import httpx
import json

from ..memory.unified_context_store import ContextEntry


logger = logging.getLogger(__name__)


class PersonalityEngineError(Exception):
    """Base exception for personality engine errors"""
    pass


class PersonalityAdaptationError(PersonalityEngineError):
    """Raised when personality adaptation fails"""
    pass


class PersonalityEngineConnector:
    """
    Connector for integrating with the Personality Engine system
    
    Features:
    - Context-aware personality adaptation
    - Cross-channel consistency maintenance
    - Premium-casual personality application
    - Customer personality profiling
    - Performance-optimized adaptation (<500ms)
    """
    
    def __init__(
        self,
        personality_engine_url: str = None,
        api_key: str = None,
        performance_target_ms: int = 500,
        timeout_seconds: float = 2.0
    ):
        self.personality_engine_url = personality_engine_url or "http://localhost:8001"
        self.api_key = api_key or "personality_engine_api_key"
        self.performance_target_ms = performance_target_ms
        self.timeout_seconds = timeout_seconds
        
        self.client = None
        
        # Cache for customer personality profiles
        self.personality_cache = {}
        
        # Performance tracking
        self.adaptation_stats = {
            "total_adaptations": 0,
            "successful_adaptations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_adaptation_time_ms": 0
        }
    
    async def initialize(self):
        """Initialize personality engine connection"""
        try:
            self.client = httpx.AsyncClient(
                base_url=self.personality_engine_url,
                timeout=self.timeout_seconds,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            
            # Test connection
            response = await self.client.get("/health")
            if response.status_code != 200:
                raise PersonalityEngineError(f"Personality engine health check failed: {response.status_code}")
            
            logger.info("PersonalityEngineConnector initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PersonalityEngineConnector: {e}")
            raise PersonalityEngineError(f"Initialization failed: {e}")
    
    async def get_customer_personality(self, customer_id: str) -> Dict[str, Any]:
        """
        Get customer personality profile
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Customer personality profile
        """
        start_time = time.time()
        
        try:
            # Check cache first
            if customer_id in self.personality_cache:
                self.adaptation_stats["cache_hits"] += 1
                retrieval_time = (time.time() - start_time) * 1000
                logger.debug(f"Personality profile retrieved from cache in {retrieval_time:.2f}ms")
                return self.personality_cache[customer_id]
            
            self.adaptation_stats["cache_misses"] += 1
            
            # Fetch from personality engine
            response = await self.client.get(f"/personality/customer/{customer_id}")
            
            if response.status_code == 404:
                # Customer not found, return default premium-casual profile
                default_profile = self._get_default_personality_profile()
                self.personality_cache[customer_id] = default_profile
                return default_profile
            
            if response.status_code != 200:
                raise PersonalityEngineError(f"Failed to get personality profile: {response.status_code}")
            
            personality_profile = response.json()
            
            # Cache the profile
            self.personality_cache[customer_id] = personality_profile
            
            retrieval_time = (time.time() - start_time) * 1000
            logger.debug(f"Personality profile retrieved in {retrieval_time:.2f}ms")
            
            return personality_profile
            
        except Exception as e:
            logger.error(f"Failed to get customer personality: {e}")
            # Return default profile on error
            return self._get_default_personality_profile()
    
    async def adapt_personality_for_channel(
        self,
        personality_profile: Dict[str, Any],
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """
        Adapt personality for specific channel while maintaining consistency
        
        Args:
            personality_profile: Customer personality profile
            context: Current conversation context
            target_channel: Target communication channel
            
        Returns:
            Adapted personality configuration
        """
        start_time = time.time()
        
        try:
            self.adaptation_stats["total_adaptations"] += 1
            
            # Prepare adaptation request
            adaptation_request = {
                "personality_profile": personality_profile,
                "context": {
                    "content": context.get("content", ""),
                    "metadata": context.get("metadata", {}),
                    "business_context": context.get("business_context", {}),
                    "conversation_thread": context.get("conversation_thread", "")
                },
                "target_channel": target_channel,
                "adaptation_requirements": {
                    "maintain_consistency": True,
                    "premium_casual_style": True,
                    "performance_target_ms": self.performance_target_ms
                }
            }
            
            # Call personality engine
            response = await self.client.post(
                "/personality/adapt-for-channel",
                json=adaptation_request
            )
            
            if response.status_code != 200:
                raise PersonalityAdaptationError(f"Adaptation failed: {response.status_code}")
            
            adaptation_result = response.json()
            
            adaptation_time = (time.time() - start_time) * 1000
            
            # Track successful adaptation
            self.adaptation_stats["successful_adaptations"] += 1
            self.adaptation_stats["average_adaptation_time_ms"] = (
                (self.adaptation_stats["average_adaptation_time_ms"] * 
                 (self.adaptation_stats["successful_adaptations"] - 1) + adaptation_time) /
                self.adaptation_stats["successful_adaptations"]
            )
            
            logger.debug(f"Personality adaptation completed in {adaptation_time:.2f}ms")
            
            return adaptation_result
            
        except Exception as e:
            adaptation_time = (time.time() - start_time) * 1000
            logger.error(f"Personality adaptation failed in {adaptation_time:.2f}ms: {e}")
            
            # Return fallback adaptation
            return self._get_fallback_adaptation(target_channel)
    
    async def generate_context_summary(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Generate intelligent context summary using personality engine
        
        Args:
            content: Content to summarize
            metadata: Additional context metadata
            
        Returns:
            Generated context summary
        """
        start_time = time.time()
        
        try:
            # Prepare summary request
            summary_request = {
                "content": content,
                "metadata": metadata or {},
                "summary_requirements": {
                    "max_words": 50,
                    "preserve_key_information": True,
                    "maintain_tone": True
                }
            }
            
            # Call personality engine
            response = await self.client.post(
                "/personality/generate-summary",
                json=summary_request
            )
            
            if response.status_code != 200:
                raise PersonalityEngineError(f"Summary generation failed: {response.status_code}")
            
            result = response.json()
            summary = result.get("summary", "")
            
            generation_time = (time.time() - start_time) * 1000
            logger.debug(f"Context summary generated in {generation_time:.2f}ms")
            
            return summary
            
        except Exception as e:
            logger.error(f"Context summary generation failed: {e}")
            # Fallback to simple truncation
            return content[:100] + "..." if len(content) > 100 else content
    
    async def validate_personality_consistency(
        self,
        customer_id: str,
        channel_contexts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate personality consistency across channels
        
        Args:
            customer_id: Customer identifier
            channel_contexts: List of contexts from different channels
            
        Returns:
            Consistency validation results
        """
        start_time = time.time()
        
        try:
            # Prepare validation request
            validation_request = {
                "customer_id": customer_id,
                "channel_contexts": channel_contexts,
                "consistency_requirements": {
                    "tone_consistency_threshold": 0.8,
                    "style_consistency_threshold": 0.85,
                    "premium_casual_alignment": True
                }
            }
            
            # Call personality engine
            response = await self.client.post(
                "/personality/validate-consistency",
                json=validation_request
            )
            
            if response.status_code != 200:
                raise PersonalityEngineError(f"Consistency validation failed: {response.status_code}")
            
            validation_result = response.json()
            
            validation_time = (time.time() - start_time) * 1000
            logger.debug(f"Personality consistency validated in {validation_time:.2f}ms")
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Personality consistency validation failed: {e}")
            return {
                "consistent": False,
                "error": str(e),
                "validation_time_ms": (time.time() - start_time) * 1000
            }
    
    async def learn_from_interaction(
        self,
        customer_id: str,
        interaction_data: Dict[str, Any]
    ) -> bool:
        """
        Learn from customer interaction to improve personality adaptation
        
        Args:
            customer_id: Customer identifier
            interaction_data: Interaction data for learning
            
        Returns:
            True if learning successful
        """
        try:
            # Prepare learning request
            learning_request = {
                "customer_id": customer_id,
                "interaction_data": interaction_data,
                "learning_objectives": {
                    "improve_tone_matching": True,
                    "enhance_context_awareness": True,
                    "optimize_channel_adaptation": True
                }
            }
            
            # Call personality engine
            response = await self.client.post(
                "/personality/learn-from-interaction",
                json=learning_request
            )
            
            if response.status_code == 200:
                # Invalidate cache to force refresh
                if customer_id in self.personality_cache:
                    del self.personality_cache[customer_id]
                
                logger.debug(f"Personality learning completed for customer {customer_id}")
                return True
            else:
                logger.warning(f"Personality learning failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Personality learning failed: {e}")
            return False
    
    def _get_default_personality_profile(self) -> Dict[str, Any]:
        """Get default premium-casual personality profile"""
        return {
            "customer_id": None,
            "personality_type": "premium_casual",
            "communication_style": {
                "tone": "approachable_professional",
                "formality_level": "premium_casual",
                "enthusiasm_level": "moderate_positive",
                "directness": "clear_and_friendly"
            },
            "channel_preferences": {
                "email": {
                    "tone": "professional_warm",
                    "formality": "business_casual",
                    "structure": "organized_friendly"
                },
                "whatsapp": {
                    "tone": "casual_enthusiastic",
                    "formality": "relaxed_professional",
                    "emoji_usage": "moderate_contextual"
                },
                "voice": {
                    "tone": "conversational_confident",
                    "pace": "natural_flowing",
                    "energy": "warm_engaging"
                }
            },
            "business_focus": {
                "goal_oriented": True,
                "solution_focused": True,
                "supportive_approach": True,
                "growth_mindset": True
            },
            "adaptation_rules": {
                "maintain_authenticity": True,
                "context_sensitive": True,
                "relationship_building": True,
                "professional_boundaries": True
            }
        }
    
    def _get_fallback_adaptation(self, target_channel: str) -> Dict[str, Any]:
        """Get fallback adaptation when personality engine is unavailable"""
        
        channel_adaptations = {
            "email": {
                "tone": "professional_warm",
                "formality_level": "business_casual",
                "adapted_content": None,  # Will be handled by channel adapter
                "style_adjustments": {
                    "structure": "organized",
                    "language": "clear_professional",
                    "closing": "warm_professional"
                }
            },
            "whatsapp": {
                "tone": "casual_friendly",
                "formality_level": "relaxed_professional",
                "adapted_content": None,
                "style_adjustments": {
                    "structure": "conversational",
                    "language": "approachable_casual",
                    "emoji_usage": "moderate"
                }
            },
            "voice": {
                "tone": "conversational_natural",
                "formality_level": "professional_approachable",
                "adapted_content": None,
                "style_adjustments": {
                    "pace": "natural",
                    "energy": "warm",
                    "speech_patterns": "flowing"
                }
            }
        }
        
        return channel_adaptations.get(target_channel, channel_adaptations["email"])
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on personality engine connection"""
        try:
            if not self.client:
                return {"status": "unhealthy", "error": "Client not initialized"}
            
            start_time = time.time()
            response = await self.client.get("/health")
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "response_time_ms": response_time,
                    "adaptation_stats": self.adaptation_stats
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": f"Health check failed: {response.status_code}",
                    "response_time_ms": response_time
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def close(self):
        """Close personality engine connection"""
        if self.client:
            await self.client.aclose()
        
        logger.info("PersonalityEngineConnector closed")


# Mock Personality Engine for Development/Testing
class MockPersonalityEngine:
    """
    Mock personality engine for development and testing
    """
    
    def __init__(self):
        self.adaptation_delay_ms = 50  # Simulate processing time
    
    async def get_customer_personality(self, customer_id: str) -> Dict[str, Any]:
        """Mock personality retrieval"""
        await asyncio.sleep(self.adaptation_delay_ms / 1000)
        
        return {
            "customer_id": customer_id,
            "personality_type": "premium_casual",
            "communication_style": {
                "tone": "approachable_professional",
                "formality_level": "premium_casual",
                "enthusiasm_level": "moderate_positive"
            },
            "channel_preferences": {
                "email": {"tone": "professional_warm"},
                "whatsapp": {"tone": "casual_enthusiastic"},
                "voice": {"tone": "conversational_confident"}
            }
        }
    
    async def adapt_personality_for_channel(
        self,
        personality_profile: Dict[str, Any],
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """Mock personality adaptation"""
        await asyncio.sleep(self.adaptation_delay_ms / 1000)
        
        channel_adaptations = {
            "email": {
                "tone": "professional_warm",
                "formality_level": "business_casual",
                "adapted_content": context.get("content", "").replace("hey", "Hello").replace("thanks", "Thank you")
            },
            "whatsapp": {
                "tone": "casual_friendly",
                "formality_level": "relaxed_professional", 
                "adapted_content": context.get("content", "").replace("Thank you", "thanks").replace("Hello", "hey")
            },
            "voice": {
                "tone": "conversational_natural",
                "formality_level": "professional_approachable",
                "adapted_content": context.get("content", "")
            }
        }
        
        return channel_adaptations.get(target_channel, channel_adaptations["email"])
    
    async def generate_context_summary(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """Mock context summary generation"""
        await asyncio.sleep(self.adaptation_delay_ms / 1000)
        
        # Simple mock summarization
        words = content.split()
        if len(words) <= 15:
            return content
        
        return " ".join(words[:15]) + "..."
    
    async def validate_personality_consistency(
        self,
        customer_id: str,
        channel_contexts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Mock consistency validation"""
        await asyncio.sleep(self.adaptation_delay_ms / 1000)
        
        return {
            "consistent": True,
            "consistency_score": 0.92,
            "channels_analyzed": len(channel_contexts),
            "recommendations": []
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Mock health check"""
        return {
            "status": "healthy",
            "response_time_ms": self.adaptation_delay_ms,
            "mock_engine": True
        }


# Factory function for creating personality engine connector
def create_personality_engine_connector(
    use_mock: bool = False,
    **kwargs
) -> Union[PersonalityEngineConnector, MockPersonalityEngine]:
    """
    Factory function for creating personality engine connector
    
    Args:
        use_mock: Whether to use mock engine for testing
        **kwargs: Additional arguments for connector
        
    Returns:
        Personality engine connector instance
    """
    if use_mock:
        return MockPersonalityEngine()
    else:
        return PersonalityEngineConnector(**kwargs)