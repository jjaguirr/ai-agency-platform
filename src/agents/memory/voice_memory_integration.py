"""
Voice Memory Integration
Connects voice conversations to EA memory system with per-customer isolation
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
import json

# Memory system imports
try:
    from .ea_memory_integration import EAMemoryManager
    from .mcp_memory_client import MCPMemoryClient
    MEMORY_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Memory system not available: {e}")
    MEMORY_AVAILABLE = False

# Voice integration imports
from ..voice_integration import VoiceLanguage

logger = logging.getLogger(__name__)

class VoiceMemoryIntegration:
    """
    Integration layer between voice conversations and EA memory system
    
    Features:
    - Store voice conversation context in customer memory
    - Track language preferences and communication patterns
    - Integrate voice insights with business understanding
    - Maintain per-customer memory isolation
    - Support bilingual context switching
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        self.customer_id = customer_id
        self.config = config or {}
        
        # Memory system integration
        if MEMORY_AVAILABLE:
            self.memory_manager = EAMemoryManager(customer_id)
            self.mcp_client = MCPMemoryClient(customer_id)
            self.has_memory = True
        else:
            self.memory_manager = None
            self.mcp_client = None
            self.has_memory = False
            logger.warning(f"Voice memory integration running without memory system for {customer_id}")
        
        # Voice-specific memory keys
        self.voice_context_key = f"voice_conversations_{customer_id}"
        self.language_preference_key = f"voice_language_preference_{customer_id}"
        self.communication_pattern_key = f"voice_communication_patterns_{customer_id}"
        
        # Local cache for performance
        self.conversation_cache: Dict[str, Dict[str, Any]] = {}
        self.language_history: List[Dict[str, Any]] = []
        
        logger.info(f"Voice memory integration initialized for customer {customer_id}")
    
    async def initialize(self) -> bool:
        """Initialize voice memory integration"""
        try:
            if self.has_memory:
                # Initialize memory connections
                await self.memory_manager.initialize()
                await self.mcp_client.connect()
                
                # Load existing voice context
                await self._load_voice_context()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize voice memory integration: {e}")
            return False
    
    async def _load_voice_context(self):
        """Load existing voice conversation context from memory"""
        try:
            # Load conversation cache
            voice_context = await self.memory_manager.get_context(self.voice_context_key)
            if voice_context:
                self.conversation_cache = voice_context.get("conversations", {})
            
            # Load language preferences
            lang_prefs = await self.memory_manager.get_context(self.language_preference_key)
            if lang_prefs:
                self.language_history = lang_prefs.get("history", [])
            
            logger.debug(f"Loaded voice context for customer {self.customer_id}: "
                        f"{len(self.conversation_cache)} conversations, "
                        f"{len(self.language_history)} language interactions")
            
        except Exception as e:
            logger.error(f"Error loading voice context: {e}")
    
    async def store_voice_interaction(
        self,
        conversation_id: str,
        message_text: str,
        response_text: str,
        detected_language: VoiceLanguage,
        response_language: VoiceLanguage,
        interaction_metadata: Dict[str, Any] = None
    ):
        """Store voice interaction in EA memory system"""
        try:
            timestamp = datetime.now()
            interaction_id = str(uuid.uuid4())
            
            # Create interaction record
            interaction_record = {
                "interaction_id": interaction_id,
                "conversation_id": conversation_id,
                "timestamp": timestamp.isoformat(),
                "customer_message": message_text,
                "ea_response": response_text,
                "detected_language": detected_language.value if detected_language else "en",
                "response_language": response_language.value if response_language else "en",
                "language_switch": detected_language != response_language if both_defined(detected_language, response_language) else False,
                "channel": "voice",
                "metadata": interaction_metadata or {}
            }
            
            # Update conversation cache
            if conversation_id not in self.conversation_cache:
                self.conversation_cache[conversation_id] = {
                    "conversation_id": conversation_id,
                    "start_time": timestamp.isoformat(),
                    "last_activity": timestamp.isoformat(),
                    "message_count": 0,
                    "interactions": [],
                    "languages_used": set(),
                    "primary_language": detected_language.value if detected_language else "en"
                }
            
            conversation = self.conversation_cache[conversation_id]
            conversation["interactions"].append(interaction_record)
            conversation["message_count"] += 1
            conversation["last_activity"] = timestamp.isoformat()
            conversation["languages_used"].add(detected_language.value if detected_language else "en")
            
            # Update language preference tracking
            await self._update_language_preferences(detected_language, response_language, timestamp)
            
            # Store in EA memory if available
            if self.has_memory:
                await self._store_in_ea_memory(interaction_record, conversation)
                await self._update_business_context(message_text, response_text, detected_language)
            
            logger.debug(f"Voice interaction stored: {interaction_id} for conversation {conversation_id}")
            
        except Exception as e:
            logger.error(f"Error storing voice interaction: {e}")
    
    async def _update_language_preferences(
        self, 
        detected_language: VoiceLanguage,
        response_language: VoiceLanguage,
        timestamp: datetime
    ):
        """Update customer language preferences based on voice interactions"""
        try:
            language_entry = {
                "timestamp": timestamp.isoformat(),
                "detected_language": detected_language.value if detected_language else "en",
                "response_language": response_language.value if response_language else "en",
                "language_switch": detected_language != response_language if both_defined(detected_language, response_language) else False
            }
            
            self.language_history.append(language_entry)
            
            # Keep only recent language history (last 100 interactions)
            if len(self.language_history) > 100:
                self.language_history = self.language_history[-100:]
            
            # Analyze language patterns
            recent_languages = [entry["detected_language"] for entry in self.language_history[-20:]]
            primary_language = max(set(recent_languages), key=recent_languages.count)
            
            language_stats = {
                "primary_language": primary_language,
                "languages_used": list(set(recent_languages)),
                "recent_interactions": len(recent_languages),
                "bilingual_user": len(set(recent_languages)) > 1,
                "code_switching_frequency": sum(1 for entry in self.language_history[-20:] if entry["language_switch"]) / len(recent_languages) if recent_languages else 0,
                "last_updated": timestamp.isoformat(),
                "history": self.language_history
            }
            
            # Store language preferences in memory
            if self.has_memory:
                await self.memory_manager.store_context(
                    self.language_preference_key,
                    language_stats
                )
            
        except Exception as e:
            logger.error(f"Error updating language preferences: {e}")
    
    async def _store_in_ea_memory(
        self, 
        interaction_record: Dict[str, Any], 
        conversation: Dict[str, Any]
    ):
        """Store voice interaction in EA memory system"""
        try:
            # Store individual interaction
            await self.memory_manager.add_interaction(
                interaction_id=interaction_record["interaction_id"],
                content=interaction_record["customer_message"],
                response=interaction_record["ea_response"],
                channel="voice",
                metadata={
                    **interaction_record["metadata"],
                    "detected_language": interaction_record["detected_language"],
                    "response_language": interaction_record["response_language"],
                    "conversation_id": interaction_record["conversation_id"]
                }
            )
            
            # Store conversation context
            await self.memory_manager.store_context(
                self.voice_context_key,
                {"conversations": {k: {**v, "languages_used": list(v["languages_used"])} for k, v in self.conversation_cache.items()}}
            )
            
            # Store in MCP memory for advanced querying
            if self.mcp_client:
                await self.mcp_client.store_memory(
                    content=f"Voice conversation: {interaction_record['customer_message']} -> {interaction_record['ea_response']}",
                    metadata={
                        "type": "voice_interaction",
                        "conversation_id": interaction_record["conversation_id"],
                        "language": interaction_record["detected_language"],
                        "channel": "voice",
                        "timestamp": interaction_record["timestamp"]
                    }
                )
            
        except Exception as e:
            logger.error(f"Error storing in EA memory: {e}")
    
    async def _update_business_context(
        self, 
        message_text: str, 
        response_text: str, 
        language: VoiceLanguage
    ):
        """Extract and store business context from voice interaction"""
        try:
            # Extract business-relevant information
            business_keywords = [
                "business", "company", "client", "customer", "revenue", "sales",
                "marketing", "automation", "workflow", "process", "project",
                "negocio", "empresa", "cliente", "ventas", "mercadeo", "automatización"
            ]
            
            message_lower = message_text.lower()
            contains_business_info = any(keyword in message_lower for keyword in business_keywords)
            
            if contains_business_info and self.has_memory:
                # Store business insight
                business_insight = {
                    "source": "voice_conversation",
                    "content": message_text,
                    "ea_response": response_text,
                    "language": language.value if language else "en",
                    "extracted_at": datetime.now().isoformat(),
                    "business_relevance": "high" if any(kw in message_lower for kw in ["revenue", "sales", "client", "project"]) else "medium"
                }
                
                await self.memory_manager.store_business_insight(
                    f"voice_business_insight_{uuid.uuid4()}",
                    business_insight
                )
            
        except Exception as e:
            logger.error(f"Error updating business context: {e}")
    
    async def get_conversation_context(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation context from memory"""
        try:
            # Check local cache first
            if conversation_id in self.conversation_cache:
                conversation = self.conversation_cache[conversation_id].copy()
                conversation["languages_used"] = list(conversation["languages_used"])
                return conversation
            
            # Try to load from memory system
            if self.has_memory:
                voice_context = await self.memory_manager.get_context(self.voice_context_key)
                if voice_context and conversation_id in voice_context.get("conversations", {}):
                    return voice_context["conversations"][conversation_id]
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return None
    
    async def get_customer_voice_profile(self) -> Dict[str, Any]:
        """Get comprehensive customer voice interaction profile"""
        try:
            profile = {
                "customer_id": self.customer_id,
                "total_conversations": len(self.conversation_cache),
                "total_interactions": sum(conv["message_count"] for conv in self.conversation_cache.values()),
                "language_preferences": {},
                "communication_patterns": {},
                "business_topics": [],
                "last_activity": None
            }
            
            if self.language_history:
                # Language analysis
                recent_languages = [entry["detected_language"] for entry in self.language_history[-50:]]
                language_counts = {lang: recent_languages.count(lang) for lang in set(recent_languages)}
                
                profile["language_preferences"] = {
                    "primary_language": max(language_counts.items(), key=lambda x: x[1])[0],
                    "language_distribution": language_counts,
                    "bilingual_user": len(set(recent_languages)) > 1,
                    "code_switching_frequency": sum(1 for entry in self.language_history[-20:] if entry.get("language_switch", False)) / min(20, len(self.language_history))
                }
            
            if self.conversation_cache:
                # Communication pattern analysis
                all_interactions = []
                for conv in self.conversation_cache.values():
                    all_interactions.extend(conv["interactions"])
                
                if all_interactions:
                    profile["communication_patterns"] = {
                        "avg_interactions_per_conversation": sum(conv["message_count"] for conv in self.conversation_cache.values()) / len(self.conversation_cache),
                        "preferred_conversation_length": "short" if profile["communication_patterns"]["avg_interactions_per_conversation"] < 5 else "medium" if profile["communication_patterns"]["avg_interactions_per_conversation"] < 15 else "long",
                        "most_active_times": self._analyze_activity_patterns(all_interactions)
                    }
                    
                    profile["last_activity"] = max(conv["last_activity"] for conv in self.conversation_cache.values())
                
                # Extract business topics
                profile["business_topics"] = await self._extract_business_topics(all_interactions)
            
            # Load additional insights from memory if available
            if self.has_memory:
                business_insights = await self.memory_manager.get_business_insights_by_source("voice_conversation")
                profile["business_insights_count"] = len(business_insights) if business_insights else 0
            
            return profile
            
        except Exception as e:
            logger.error(f"Error getting customer voice profile: {e}")
            return {"error": str(e)}
    
    def _analyze_activity_patterns(self, interactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze customer activity patterns in voice interactions"""
        try:
            from collections import defaultdict
            import datetime as dt
            
            hour_counts = defaultdict(int)
            day_counts = defaultdict(int)
            
            for interaction in interactions:
                timestamp = dt.datetime.fromisoformat(interaction["timestamp"])
                hour_counts[timestamp.hour] += 1
                day_counts[timestamp.strftime("%A")] += 1
            
            most_active_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else 12
            most_active_day = max(day_counts.items(), key=lambda x: x[1])[0] if day_counts else "Monday"
            
            return {
                "most_active_hour": most_active_hour,
                "most_active_day": most_active_day,
                "hourly_distribution": dict(hour_counts),
                "daily_distribution": dict(day_counts)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing activity patterns: {e}")
            return {}
    
    async def _extract_business_topics(self, interactions: List[Dict[str, Any]]) -> List[str]:
        """Extract business topics from voice interactions"""
        try:
            # Simple keyword extraction (could be enhanced with NLP)
            business_terms = {
                "marketing": ["marketing", "social media", "advertising", "campaign", "mercadeo", "publicidad"],
                "sales": ["sales", "revenue", "client", "customer", "deal", "ventas", "cliente"],
                "operations": ["process", "workflow", "automation", "system", "proceso", "automatización"],
                "finance": ["budget", "cost", "investment", "financial", "presupuesto", "financiero"],
                "strategy": ["strategy", "plan", "goal", "growth", "estrategia", "plan", "crecimiento"]
            }
            
            topics_found = set()
            all_text = " ".join([
                f"{interaction['customer_message']} {interaction['ea_response']}"
                for interaction in interactions
            ]).lower()
            
            for topic, keywords in business_terms.items():
                if any(keyword in all_text for keyword in keywords):
                    topics_found.add(topic)
            
            return list(topics_found)
            
        except Exception as e:
            logger.error(f"Error extracting business topics: {e}")
            return []
    
    async def search_voice_history(
        self, 
        query: str, 
        language: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search voice interaction history"""
        try:
            results = []
            query_lower = query.lower()
            
            for conversation in self.conversation_cache.values():
                for interaction in conversation["interactions"]:
                    # Check language filter
                    if language and interaction["detected_language"] != language:
                        continue
                    
                    # Simple text search (could be enhanced with semantic search)
                    if (query_lower in interaction["customer_message"].lower() or 
                        query_lower in interaction["ea_response"].lower()):
                        results.append({
                            "interaction_id": interaction["interaction_id"],
                            "conversation_id": interaction["conversation_id"],
                            "timestamp": interaction["timestamp"],
                            "customer_message": interaction["customer_message"],
                            "ea_response": interaction["ea_response"],
                            "language": interaction["detected_language"],
                            "relevance_score": self._calculate_relevance(query_lower, interaction)
                        })
            
            # Sort by relevance and timestamp
            results.sort(key=lambda x: (x["relevance_score"], x["timestamp"]), reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error searching voice history: {e}")
            return []
    
    def _calculate_relevance(self, query: str, interaction: Dict[str, Any]) -> float:
        """Calculate search relevance score"""
        try:
            combined_text = f"{interaction['customer_message']} {interaction['ea_response']}".lower()
            query_words = query.split()
            
            # Simple relevance scoring
            matches = sum(1 for word in query_words if word in combined_text)
            relevance = matches / len(query_words) if query_words else 0
            
            return relevance
            
        except Exception:
            return 0.0
    
    async def cleanup_old_conversations(self, days_to_keep: int = 30):
        """Clean up old voice conversation data"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days_to_keep)
            conversations_to_remove = []
            
            for conv_id, conversation in self.conversation_cache.items():
                last_activity = datetime.fromisoformat(conversation["last_activity"])
                if last_activity < cutoff_time:
                    conversations_to_remove.append(conv_id)
            
            for conv_id in conversations_to_remove:
                del self.conversation_cache[conv_id]
            
            # Update stored context
            if self.has_memory and conversations_to_remove:
                await self.memory_manager.store_context(
                    self.voice_context_key,
                    {"conversations": {k: {**v, "languages_used": list(v["languages_used"])} for k, v in self.conversation_cache.items()}}
                )
            
            logger.info(f"Cleaned up {len(conversations_to_remove)} old conversations for customer {self.customer_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up old conversations: {e}")

def both_defined(*values):
    """Check if all values are not None"""
    return all(v is not None for v in values)

# Factory function for creating voice memory integration
def create_voice_memory_integration(customer_id: str, config: Dict[str, Any] = None) -> VoiceMemoryIntegration:
    """Create and initialize voice memory integration"""
    return VoiceMemoryIntegration(customer_id, config)