"""
Personality Engine - Core Premium-Casual Conversation Transformation
Enables "Premium capabilities with your best friend's personality" for AI Agency Platform

This engine transforms AI responses to maintain consistent premium-casual personality
across all communication channels (email, WhatsApp, voice) with <500ms processing time.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal, Union
from dataclasses import dataclass, asdict, field
from enum import Enum

import openai
from openai import AsyncOpenAI

# Import MCP memory client for customer isolation
from ..memory.mcp_memory_client import MCPMemoryServiceClient, MemorySearchResult

logger = logging.getLogger(__name__)


class CommunicationChannel(Enum):
    """Communication channels requiring consistent personality"""
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    VOICE = "voice" 
    WEB_CHAT = "web_chat"
    SMS = "sms"


class PersonalityTone(Enum):
    """Premium-casual personality tone variations"""
    PROFESSIONAL_WARM = "professional_warm"  # Default premium-casual
    MOTIVATIONAL = "motivational"            # For growth-focused conversations
    SUPPORTIVE = "supportive"                # For challenging situations
    STRATEGIC = "strategic"                  # For business planning
    CONVERSATIONAL = "conversational"       # For casual check-ins


class ConversationContext(Enum):
    """Context types that influence personality adaptation"""
    BUSINESS_PLANNING = "business_planning"
    PROBLEM_SOLVING = "problem_solving"
    CASUAL_UPDATE = "casual_update"
    URGENT_MATTER = "urgent_matter"
    CELEBRATION = "celebration"
    FIRST_INTERACTION = "first_interaction"


@dataclass
class PersonalityProfile:
    """Per-customer personality profile and preferences"""
    customer_id: str
    preferred_tone: PersonalityTone = PersonalityTone.PROFESSIONAL_WARM
    communication_style_preferences: Dict[str, Any] = field(default_factory=dict)
    personality_consistency_score: float = 0.0  # Tracks consistency across channels
    successful_patterns: List[str] = field(default_factory=list)
    avoided_patterns: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PersonalityTransformationResult:
    """Result of personality transformation with performance metrics"""
    transformed_content: str
    original_content: str
    personality_tone: PersonalityTone
    channel: CommunicationChannel
    transformation_time_ms: int
    consistency_score: float  # How well it matches established personality
    premium_casual_indicators: List[str]  # Elements that make it premium-casual
    transformation_metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PersonalityConsistencyReport:
    """Cross-channel personality consistency analysis"""
    customer_id: str
    overall_consistency_score: float
    channel_scores: Dict[CommunicationChannel, float]
    consistency_issues: List[str]
    improvement_suggestions: List[str]
    sample_transformations: Dict[str, PersonalityTransformationResult]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class PersonalityEngine:
    """
    Core personality transformation engine for premium-casual EA communication.
    
    Transforms AI responses to maintain consistent "premium capabilities with your 
    best friend's personality" across all channels while meeting <500ms SLA.
    """
    
    def __init__(
        self,
        openai_client: Optional[AsyncOpenAI] = None,
        memory_client: Optional[MCPMemoryServiceClient] = None,
        personality_model: str = "gpt-4o-mini",  # Fast model for personality transformation
        enable_caching: bool = True
    ):
        """
        Initialize personality engine with AI and memory integration.
        
        Args:
            openai_client: AsyncOpenAI client for personality transformation
            memory_client: MCP memory client for customer personality patterns
            personality_model: AI model for personality transformations (optimized for speed)
            enable_caching: Enable transformation pattern caching for performance
        """
        self.openai_client = openai_client or AsyncOpenAI()
        self.memory_client = memory_client
        self.personality_model = personality_model
        self.enable_caching = enable_caching
        
        # Performance optimization: cache common transformation patterns
        self.transformation_cache: Dict[str, PersonalityTransformationResult] = {}
        self.cache_max_size = 1000  # Limit cache size for memory efficiency
        
        # Premium-casual personality framework
        self.personality_framework = self._initialize_personality_framework()
        self.consistency_tracker: Dict[str, List[PersonalityTransformationResult]] = {}
        
        logger.info(f"PersonalityEngine initialized with model: {personality_model}")
    
    async def transform_message(
        self,
        customer_id: str,
        original_content: str,
        channel: CommunicationChannel,
        conversation_context: Optional[ConversationContext] = None,
        target_tone: Optional[PersonalityTone] = None
    ) -> PersonalityTransformationResult:
        """
        Transform message to premium-casual personality with <500ms performance target.
        
        Args:
            customer_id: Customer identifier for personality consistency
            original_content: Original AI response to transform
            channel: Communication channel for context-appropriate adaptation
            conversation_context: Conversation context for tone adjustment
            target_tone: Override default personality tone if needed
            
        Returns:
            PersonalityTransformationResult with transformed content and metrics
        """
        start_time = time.time()
        
        try:
            # 1. Load customer personality profile (parallel with cache check)
            profile_task = self._load_customer_personality_profile(customer_id)
            cache_key = self._generate_cache_key(original_content, channel, conversation_context)
            
            # 2. Check transformation cache for performance optimization
            if self.enable_caching and cache_key in self.transformation_cache:
                cached_result = self.transformation_cache[cache_key]
                cached_result.transformation_time_ms = int((time.time() - start_time) * 1000)
                logger.info(f"Personality transformation cache hit: {cached_result.transformation_time_ms}ms")
                return cached_result
            
            # 3. Get customer profile
            personality_profile = await profile_task
            effective_tone = target_tone or personality_profile.preferred_tone
            
            # 4. Generate personality transformation prompt
            transformation_prompt = self._create_personality_transformation_prompt(
                original_content=original_content,
                personality_profile=personality_profile,
                channel=channel,
                conversation_context=conversation_context,
                target_tone=effective_tone
            )
            
            # 5. Execute AI transformation (optimized for speed)
            response = await self.openai_client.chat.completions.create(
                model=self.personality_model,
                messages=[
                    {
                        "role": "system", 
                        "content": self.personality_framework["system_prompt"]
                    },
                    {
                        "role": "user", 
                        "content": transformation_prompt
                    }
                ],
                temperature=0.3,  # Balanced creativity with consistency
                max_tokens=800,   # Sufficient for most transformations
                timeout=3.0       # Strict timeout for performance SLA
            )
            
            # 6. Parse transformation result
            transformation_text = response.choices[0].message.content
            transformed_content = self._extract_transformed_content(transformation_text)
            
            # 7. Analyze transformation quality
            premium_casual_indicators = self._analyze_premium_casual_indicators(transformed_content)
            consistency_score = await self._calculate_consistency_score(
                customer_id, transformed_content, channel
            )
            
            # 8. Create result object
            transformation_time = int((time.time() - start_time) * 1000)
            result = PersonalityTransformationResult(
                transformed_content=transformed_content,
                original_content=original_content,
                personality_tone=effective_tone,
                channel=channel,
                transformation_time_ms=transformation_time,
                consistency_score=consistency_score,
                premium_casual_indicators=premium_casual_indicators,
                transformation_metadata={
                    "conversation_context": conversation_context.value if hasattr(conversation_context, 'value') else str(conversation_context) if conversation_context else None,
                    "cache_hit": False,
                    "model_used": self.personality_model
                }
            )
            
            # 9. Cache result for future performance optimization
            if self.enable_caching:
                self._cache_transformation_result(cache_key, result)
            
            # 10. Track for consistency analysis
            self._track_transformation_for_consistency(customer_id, result)
            
            # 11. Store transformation pattern in memory for learning
            if self.memory_client:
                await self._store_transformation_pattern(customer_id, result)
            
            logger.info(
                f"Personality transformation completed: {transformation_time}ms, "
                f"consistency: {consistency_score:.2f}, channel: {channel.value}"
            )
            
            return result
            
        except Exception as e:
            # Fallback: return original content with error metadata
            transformation_time = int((time.time() - start_time) * 1000)
            logger.error(f"Personality transformation failed: {e}")
            
            return PersonalityTransformationResult(
                transformed_content=original_content,  # Fallback to original
                original_content=original_content,
                personality_tone=target_tone or PersonalityTone.PROFESSIONAL_WARM,
                channel=channel,
                transformation_time_ms=transformation_time,
                consistency_score=0.0,
                premium_casual_indicators=[],
                transformation_metadata={
                    "error": str(e),
                    "fallback_used": True
                }
            )
    
    async def analyze_personality_consistency(
        self,
        customer_id: str,
        time_window_hours: int = 24
    ) -> PersonalityConsistencyReport:
        """
        Analyze personality consistency across all communication channels.
        
        Args:
            customer_id: Customer identifier
            time_window_hours: Time window for analysis (default 24 hours)
            
        Returns:
            PersonalityConsistencyReport with detailed consistency metrics
        """
        try:
            # Get recent transformations for this customer
            customer_transformations = self.consistency_tracker.get(customer_id, [])
            
            # Filter by time window
            cutoff_time = datetime.now().timestamp() - (time_window_hours * 3600)
            recent_transformations = [
                t for t in customer_transformations
                if datetime.fromisoformat(t.timestamp).timestamp() > cutoff_time
            ]
            
            if not recent_transformations:
                return PersonalityConsistencyReport(
                    customer_id=customer_id,
                    overall_consistency_score=1.0,  # No data = perfect consistency
                    channel_scores={},
                    consistency_issues=[],
                    improvement_suggestions=[],
                    sample_transformations={}
                )
            
            # Group transformations by channel
            channel_groups = {}
            for transformation in recent_transformations:
                channel = transformation.channel
                if channel not in channel_groups:
                    channel_groups[channel] = []
                channel_groups[channel].append(transformation)
            
            # Calculate consistency scores per channel
            channel_scores = {}
            consistency_issues = []
            sample_transformations = {}
            
            for channel, transformations in channel_groups.items():
                # Calculate average consistency score for channel
                scores = [t.consistency_score for t in transformations]
                avg_score = sum(scores) / len(scores) if scores else 1.0
                channel_scores[channel] = avg_score
                
                # Collect sample transformation
                if transformations:
                    sample_transformations[channel.value] = transformations[-1]  # Most recent
                
                # Identify consistency issues
                if avg_score < 0.7:
                    consistency_issues.append(
                        f"{channel.value} channel consistency below target (score: {avg_score:.2f})"
                    )
            
            # Calculate overall consistency score
            if channel_scores:
                overall_score = sum(channel_scores.values()) / len(channel_scores)
            else:
                overall_score = 1.0
            
            # Generate improvement suggestions
            improvement_suggestions = self._generate_consistency_improvement_suggestions(
                channel_scores, consistency_issues
            )
            
            return PersonalityConsistencyReport(
                customer_id=customer_id,
                overall_consistency_score=overall_score,
                channel_scores=channel_scores,
                consistency_issues=consistency_issues,
                improvement_suggestions=improvement_suggestions,
                sample_transformations=sample_transformations
            )
            
        except Exception as e:
            logger.error(f"Personality consistency analysis failed: {e}")
            return PersonalityConsistencyReport(
                customer_id=customer_id,
                overall_consistency_score=0.0,
                channel_scores={},
                consistency_issues=[f"Analysis failed: {str(e)}"],
                improvement_suggestions=["Fix consistency analysis system"],
                sample_transformations={}
            )
    
    async def update_personality_profile(
        self,
        customer_id: str,
        preferences: Dict[str, Any],
        successful_patterns: Optional[List[str]] = None,
        avoided_patterns: Optional[List[str]] = None
    ) -> PersonalityProfile:
        """
        Update customer's personality profile based on feedback and learning.
        
        Args:
            customer_id: Customer identifier
            preferences: Updated personality preferences
            successful_patterns: Communication patterns that worked well
            avoided_patterns: Communication patterns to avoid
            
        Returns:
            Updated PersonalityProfile
        """
        try:
            # Load existing profile
            profile = await self._load_customer_personality_profile(customer_id)
            
            # Update preferences
            profile.communication_style_preferences.update(preferences)
            
            # Update pattern learning
            if successful_patterns:
                profile.successful_patterns.extend(successful_patterns)
                # Keep only recent/most effective patterns (limit size)
                profile.successful_patterns = profile.successful_patterns[-50:]
            
            if avoided_patterns:
                profile.avoided_patterns.extend(avoided_patterns)
                profile.avoided_patterns = profile.avoided_patterns[-50:]
            
            # Update timestamp
            profile.updated_at = datetime.now().isoformat()
            
            # Store updated profile in memory
            if self.memory_client:
                await self._store_personality_profile(profile)
            
            logger.info(f"Updated personality profile for customer {customer_id}")
            return profile
            
        except Exception as e:
            logger.error(f"Failed to update personality profile: {e}")
            # Return current profile or create new one
            return await self._load_customer_personality_profile(customer_id)
    
    async def create_ab_test_variation(
        self,
        customer_id: str,
        original_content: str,
        channel: CommunicationChannel,
        variation_config: Dict[str, Any]
    ) -> Dict[str, PersonalityTransformationResult]:
        """
        Create A/B test variations for personality optimization.
        
        Args:
            customer_id: Customer identifier
            original_content: Original content to transform
            channel: Communication channel
            variation_config: Configuration for A/B test variations
            
        Returns:
            Dictionary mapping variation names to transformation results
        """
        try:
            variations = {}
            
            # Control version (default personality)
            control_result = await self.transform_message(
                customer_id=customer_id,
                original_content=original_content,
                channel=channel
            )
            variations["control"] = control_result
            
            # Generate test variations based on config
            for variation_name, config in variation_config.items():
                test_tone = PersonalityTone(config.get("tone", PersonalityTone.PROFESSIONAL_WARM.value))
                test_context = None
                if "context" in config:
                    test_context = ConversationContext(config["context"])
                
                variation_result = await self.transform_message(
                    customer_id=customer_id,
                    original_content=original_content,
                    channel=channel,
                    conversation_context=test_context,
                    target_tone=test_tone
                )
                variations[variation_name] = variation_result
            
            logger.info(f"Generated {len(variations)} A/B test variations for customer {customer_id}")
            return variations
            
        except Exception as e:
            logger.error(f"A/B test variation generation failed: {e}")
            return {}
    
    def _initialize_personality_framework(self) -> Dict[str, Any]:
        """Initialize the premium-casual personality framework"""
        
        return {
            "system_prompt": """You are a personality transformation specialist focused on creating "premium capabilities with your best friend's personality" communication style.

Transform AI responses to be:
- Sophisticated yet approachable
- Professional but warm and conversational  
- Motivational and encouraging
- Business-focused with friendly delivery
- Confident without being arrogant

PREMIUM-CASUAL CHARACTERISTICS:
- Use "Hey" or "Hi" instead of formal greetings when appropriate
- Include encouraging phrases like "Let's get this done" or "You've got this"
- Mix professional insights with casual, supportive language
- Show genuine interest in the person's success
- Make complex business concepts accessible and actionable

MAINTAIN CONSISTENCY across email, WhatsApp, and voice channels while adapting to each medium's conventions.

Always transform the entire response while preserving all important information and actionable advice.""",
            
            "premium_casual_patterns": [
                "Hey, I noticed...",
                "Let's tackle this together...",
                "Here's what I'm thinking...",
                "You're absolutely right about...",
                "This is exciting - let's...",
                "I've got some ideas that might help...",
                "Want to try this approach?",
                "Let's make this happen...",
                "You're doing great with...",
                "Here's the game plan..."
            ],
            
            "tone_adaptations": {
                "email": "Professional-casual with clear structure",
                "whatsapp": "Conversational and immediate", 
                "voice": "Natural speaking patterns with enthusiasm",
                "web_chat": "Friendly but efficient"
            },
            
            "avoid_patterns": [
                "I am an AI assistant",
                "As an AI, I...",
                "I don't have personal experience",
                "I cannot...",  # (replace with alternatives)
                "Dear Sir/Madam",
                "Sincerely yours",
                "Please be advised"
            ]
        }
    
    def _create_personality_transformation_prompt(
        self,
        original_content: str,
        personality_profile: PersonalityProfile,
        channel: CommunicationChannel,
        conversation_context: Optional[ConversationContext],
        target_tone: PersonalityTone
    ) -> str:
        """Create AI prompt for personality transformation"""
        
        # Channel-specific adaptation guidelines
        channel_guidelines = {
            CommunicationChannel.EMAIL: "Professional structure with casual warmth. Use clear paragraphs and friendly but business-appropriate language.",
            CommunicationChannel.WHATSAPP: "Conversational and immediate. Use shorter sentences, casual connectors, and emoji when appropriate.",
            CommunicationChannel.VOICE: "Natural speaking patterns with enthusiasm. Use conversational flow and speaking rhythms.",
            CommunicationChannel.WEB_CHAT: "Friendly but efficient. Quick to read, actionable, and engaging."
        }
        
        # Context-specific tone adjustments
        context_adjustments = {
            ConversationContext.BUSINESS_PLANNING: "Strategic and motivational - focus on growth and opportunities",
            ConversationContext.PROBLEM_SOLVING: "Supportive and solution-focused - acknowledge challenges with confidence",
            ConversationContext.CASUAL_UPDATE: "Friendly check-in style - casual but still valuable",
            ConversationContext.URGENT_MATTER: "Calm urgency - immediate but not stressed",
            ConversationContext.CELEBRATION: "Enthusiastic and encouraging - celebrate wins together",
            ConversationContext.FIRST_INTERACTION: "Welcoming and confidence-building - establish relationship"
        }
        
        # Include successful patterns from customer profile
        successful_patterns_text = ""
        if personality_profile.successful_patterns:
            successful_patterns_text = f"\nThis customer responds well to: {', '.join(personality_profile.successful_patterns[:3])}"
        
        # Include patterns to avoid
        avoided_patterns_text = ""
        if personality_profile.avoided_patterns:
            avoided_patterns_text = f"\nAvoid these patterns for this customer: {', '.join(personality_profile.avoided_patterns[:3])}"
        
        return f"""Transform this AI response for {channel.value} communication using premium-casual personality:

ORIGINAL RESPONSE:
{original_content}

TRANSFORMATION REQUIREMENTS:
- Target tone: {target_tone.value}
- Channel: {channel.value} - {channel_guidelines.get(channel, "Standard adaptation")}
- Context: {conversation_context.value if hasattr(conversation_context, 'value') else str(conversation_context) if conversation_context else "General"} - {context_adjustments.get(conversation_context, "Standard approach") if conversation_context else "Standard approach"}
{successful_patterns_text}
{avoided_patterns_text}

PREMIUM-CASUAL TRANSFORMATION:
1. Replace formal language with warm, professional tone
2. Add encouraging, motivational elements
3. Make it sound like advice from a brilliant business friend
4. Maintain all important information and actionability
5. Adapt to {channel.value} communication style
6. Keep response length appropriate for channel

Provide ONLY the transformed response - no explanations or meta-commentary."""
    
    def _extract_transformed_content(self, transformation_text: str) -> str:
        """Extract the actual transformed content from AI response"""
        
        # Remove any meta-commentary or system text
        content = transformation_text.strip()
        
        # Remove common prefixes that might appear
        prefixes_to_remove = [
            "Here's the transformed response:",
            "Transformed response:",
            "Premium-casual version:",
            "Here is the transformation:",
        ]
        
        for prefix in prefixes_to_remove:
            if content.lower().startswith(prefix.lower()):
                content = content[len(prefix):].strip()
        
        return content
    
    def _analyze_premium_casual_indicators(self, content: str) -> List[str]:
        """Analyze content for premium-casual personality indicators"""
        
        indicators = []
        content_lower = content.lower()
        
        # Positive indicators of premium-casual style
        premium_casual_patterns = [
            (r"\bhey\b|\bhi there\b", "casual_greeting"),
            (r"let's|let me|we can", "collaborative_language"),
            (r"you've got this|you're doing great|exciting", "encouragement"),
            (r"here's what i'm thinking|my take on this", "personal_perspective"),
            (r"want to try|how about|what if we", "conversational_suggestions"),
            (r"this is going to be|i love that|amazing", "enthusiasm"),
            (r"makes sense|totally|absolutely", "validation"),
        ]
        
        for pattern, indicator_type in premium_casual_patterns:
            if re.search(pattern, content_lower):
                indicators.append(indicator_type)
        
        # Check for business sophistication
        business_patterns = [
            (r"strategy|strategic|optimize|roi|kpi", "business_sophistication"),
            (r"implement|execute|actionable|next steps", "actionable_advice"),
            (r"market|competitive|growth|scale", "business_context"),
        ]
        
        for pattern, indicator_type in business_patterns:
            if re.search(pattern, content_lower):
                indicators.append(indicator_type)
        
        return list(set(indicators))  # Remove duplicates
    
    async def _calculate_consistency_score(
        self,
        customer_id: str,
        current_content: str,
        channel: CommunicationChannel
    ) -> float:
        """Calculate how consistent this transformation is with customer's established personality"""
        
        try:
            # Get recent transformations for this customer
            customer_transformations = self.consistency_tracker.get(customer_id, [])
            
            if not customer_transformations:
                return 1.0  # Perfect consistency with no previous data
            
            # Analyze consistency with previous transformations
            current_indicators = set(self._analyze_premium_casual_indicators(current_content))
            
            # Compare with recent transformations
            similarity_scores = []
            for prev_transformation in customer_transformations[-5:]:  # Last 5 transformations
                prev_indicators = set(prev_transformation.premium_casual_indicators)
                
                if current_indicators and prev_indicators:
                    intersection = len(current_indicators & prev_indicators)
                    union = len(current_indicators | prev_indicators)
                    similarity = intersection / union if union > 0 else 1.0
                    similarity_scores.append(similarity)
            
            if similarity_scores:
                return sum(similarity_scores) / len(similarity_scores)
            else:
                return 1.0
                
        except Exception as e:
            logger.warning(f"Consistency score calculation failed: {e}")
            return 0.5  # Neutral score on error
    
    async def _load_customer_personality_profile(self, customer_id: str) -> PersonalityProfile:
        """Load customer's personality profile from memory or create new one"""
        
        try:
            if self.memory_client:
                # Search for existing personality profile
                memories = await self.memory_client.search_memories(
                    query=f"personality profile customer {customer_id}",
                    limit=1,
                    score_threshold=0.8
                )
                
                if memories:
                    # Parse stored profile
                    profile_data = json.loads(memories[0].content)
                    return PersonalityProfile(**profile_data)
            
            # Create new profile if none found
            return PersonalityProfile(customer_id=customer_id)
            
        except Exception as e:
            logger.warning(f"Failed to load personality profile, using default: {e}")
            return PersonalityProfile(customer_id=customer_id)
    
    async def _store_personality_profile(self, profile: PersonalityProfile) -> None:
        """Store personality profile in memory"""
        
        try:
            if self.memory_client:
                profile_json = json.dumps(asdict(profile), indent=2)
                await self.memory_client.store_memory(
                    content=profile_json,
                    metadata={
                        "type": "personality_profile",
                        "customer_id": profile.customer_id,
                        "updated_at": profile.updated_at
                    }
                )
                
        except Exception as e:
            logger.error(f"Failed to store personality profile: {e}")
    
    async def _store_transformation_pattern(
        self,
        customer_id: str,
        result: PersonalityTransformationResult
    ) -> None:
        """Store successful transformation pattern for future learning"""
        
        try:
            if self.memory_client and result.consistency_score > 0.7:
                pattern_data = {
                    "customer_id": customer_id,
                    "channel": result.channel.value,
                    "personality_tone": result.personality_tone.value,
                    "premium_casual_indicators": result.premium_casual_indicators,
                    "consistency_score": result.consistency_score,
                    "transformation_time_ms": result.transformation_time_ms,
                    "original_length": len(result.original_content),
                    "transformed_length": len(result.transformed_content)
                }
                
                await self.memory_client.store_memory(
                    content=f"Successful personality transformation pattern: {json.dumps(pattern_data)}",
                    metadata={
                        "type": "personality_pattern",
                        "customer_id": customer_id,
                        "channel": result.channel.value,
                        "consistency_score": result.consistency_score
                    }
                )
                
        except Exception as e:
            logger.warning(f"Failed to store transformation pattern: {e}")
    
    def _generate_cache_key(
        self,
        content: str,
        channel: CommunicationChannel,
        context: Optional[ConversationContext]
    ) -> str:
        """Generate cache key for transformation results"""
        
        # Create hash of content + channel + context for caching
        import hashlib
        key_string = f"{content[:200]}:{channel.value}:{context.value if context else 'none'}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _cache_transformation_result(
        self,
        cache_key: str,
        result: PersonalityTransformationResult
    ) -> None:
        """Cache transformation result for performance optimization"""
        
        # Implement LRU cache behavior
        if len(self.transformation_cache) >= self.cache_max_size:
            # Remove oldest entry
            oldest_key = next(iter(self.transformation_cache))
            del self.transformation_cache[oldest_key]
        
        self.transformation_cache[cache_key] = result
    
    def _track_transformation_for_consistency(
        self,
        customer_id: str,
        result: PersonalityTransformationResult
    ) -> None:
        """Track transformation for consistency analysis"""
        
        if customer_id not in self.consistency_tracker:
            self.consistency_tracker[customer_id] = []
        
        self.consistency_tracker[customer_id].append(result)
        
        # Keep only recent transformations (limit memory usage)
        if len(self.consistency_tracker[customer_id]) > 50:
            self.consistency_tracker[customer_id] = self.consistency_tracker[customer_id][-30:]
    
    def _generate_consistency_improvement_suggestions(
        self,
        channel_scores: Dict[CommunicationChannel, float],
        consistency_issues: List[str]
    ) -> List[str]:
        """Generate suggestions for improving personality consistency"""
        
        suggestions = []
        
        # Identify channels needing improvement
        low_score_channels = [
            channel for channel, score in channel_scores.items() 
            if score < 0.8
        ]
        
        if low_score_channels:
            suggestions.append(
                f"Focus on consistency improvement for {', '.join([c.value for c in low_score_channels])} channels"
            )
        
        # Add specific improvement suggestions
        if len(channel_scores) > 1:
            suggestions.append("Cross-reference successful patterns between channels")
        
        if any("below target" in issue for issue in consistency_issues):
            suggestions.append("Review and update personality transformation prompts")
        
        if not suggestions:
            suggestions.append("Maintain current consistency standards")
        
        return suggestions


# Utility functions for personality pattern analysis
def extract_personality_patterns(content: str) -> Dict[str, Any]:
    """Extract personality patterns from text content"""
    
    patterns = {
        "casual_elements": [],
        "professional_elements": [],
        "motivational_elements": [],
        "tone_indicators": []
    }
    
    # Casual elements
    casual_patterns = [r"\bhey\b", r"\byeah\b", r"\btotally\b", r"let's", r"we can"]
    for pattern in casual_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            patterns["casual_elements"].append(pattern)
    
    # Professional elements  
    professional_patterns = [r"strategic", r"implement", r"optimize", r"analysis", r"recommend"]
    for pattern in professional_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            patterns["professional_elements"].append(pattern)
    
    # Motivational elements
    motivational_patterns = [r"you've got", r"excited", r"amazing", r"great job", r"let's make"]
    for pattern in motivational_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            patterns["motivational_elements"].append(pattern)
    
    return patterns


def calculate_premium_casual_score(content: str) -> float:
    """Calculate how well content matches premium-casual personality"""
    
    patterns = extract_personality_patterns(content)
    
    # Score based on balance of casual and professional elements
    casual_count = len(patterns["casual_elements"])
    professional_count = len(patterns["professional_elements"]) 
    motivational_count = len(patterns["motivational_elements"])
    
    # Ideal premium-casual has balance of all elements
    if casual_count > 0 and professional_count > 0:
        base_score = min(casual_count * 0.3 + professional_count * 0.3, 0.8)
        motivation_bonus = min(motivational_count * 0.1, 0.2)
        return min(base_score + motivation_bonus, 1.0)
    
    return 0.3  # Low score without both elements