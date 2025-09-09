"""
Channel Adapters

Channel-specific adaptation layers that handle context preservation
and transformation between different communication channels.

This module provides:
- Email ↔ WhatsApp ↔ Voice adaptation
- Content transformation (formal ↔ casual ↔ spoken)
- Personality consistency across channels
- Business context preservation
- Performance-optimized adaptation (<500ms)
"""

import asyncio
import time
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from abc import ABC, abstractmethod

from ..integrations.personality_engine_integration import PersonalityEngineConnector


logger = logging.getLogger(__name__)


class ChannelAdapterError(Exception):
    """Base exception for channel adaptation errors"""
    pass


class ContextTransformationError(ChannelAdapterError):
    """Raised when context transformation fails"""
    pass


class BaseChannelAdapter(ABC):
    """Base class for all channel adapters"""
    
    def __init__(
        self,
        personality_engine: PersonalityEngineConnector = None,
        performance_target_ms: int = 500
    ):
        self.personality_engine = personality_engine
        self.performance_target_ms = performance_target_ms
        
        # Performance tracking
        self.adaptation_stats = {
            "total_adaptations": 0,
            "successful_adaptations": 0,
            "average_adaptation_time_ms": 0,
            "target_channel_counts": {}
        }
    
    async def initialize(self):
        """Initialize adapter resources"""
        pass
    
    @abstractmethod
    async def adapt_to_channel(
        self,
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """
        Adapt context to target channel
        
        Args:
            context: Source context
            target_channel: Target communication channel
            
        Returns:
            Adapted context for target channel
        """
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on adapter"""
        return {
            "status": "healthy",
            "adaptation_stats": self.adaptation_stats,
            "performance_target_ms": self.performance_target_ms
        }
    
    async def close(self):
        """Clean shutdown of adapter resources"""
        pass
    
    def _track_adaptation(self, target_channel: str, adaptation_time_ms: float, success: bool):
        """Track adaptation performance metrics"""
        self.adaptation_stats["total_adaptations"] += 1
        
        if success:
            self.adaptation_stats["successful_adaptations"] += 1
            self.adaptation_stats["average_adaptation_time_ms"] = (
                (self.adaptation_stats["average_adaptation_time_ms"] * 
                 (self.adaptation_stats["successful_adaptations"] - 1) + adaptation_time_ms) /
                self.adaptation_stats["successful_adaptations"]
            )
        
        self.adaptation_stats["target_channel_counts"][target_channel] = (
            self.adaptation_stats["target_channel_counts"].get(target_channel, 0) + 1
        )


class EmailChannelAdapter(BaseChannelAdapter):
    """
    Email channel adapter for formal business communication
    
    Features:
    - Formal tone and structure
    - Professional language adaptation
    - Business context preservation
    - Email-specific formatting
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_name = "email"
    
    async def adapt_to_channel(
        self,
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """
        Adapt email context to target channel
        
        Args:
            context: Email context to adapt
            target_channel: Target channel (whatsapp, voice)
            
        Returns:
            Adapted context for target channel
        """
        start_time = time.time()
        
        try:
            if target_channel == "whatsapp":
                adapted_context = await self._adapt_email_to_whatsapp(context)
            elif target_channel == "voice":
                adapted_context = await self._adapt_email_to_voice(context)
            else:
                raise ContextTransformationError(f"Unsupported target channel: {target_channel}")
            
            adaptation_time = (time.time() - start_time) * 1000
            self._track_adaptation(target_channel, adaptation_time, True)
            
            logger.debug(f"Email→{target_channel} adaptation completed in {adaptation_time:.2f}ms")
            
            return adapted_context
            
        except Exception as e:
            adaptation_time = (time.time() - start_time) * 1000
            self._track_adaptation(target_channel, adaptation_time, False)
            
            logger.error(f"Email→{target_channel} adaptation failed in {adaptation_time:.2f}ms: {e}")
            raise ContextTransformationError(f"Email adaptation failed: {e}")
    
    async def _adapt_email_to_whatsapp(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt email context to WhatsApp (formal → casual)"""
        
        # Extract key information
        content = context.get("content", "")
        metadata = context.get("metadata", {})
        
        # Transform content to casual tone
        casual_content = await self._formalize_to_casual(content)
        
        # Adapt metadata
        adapted_metadata = {
            **metadata,
            "tone": "casual_friendly",
            "formality_level": "approachable_professional",
            "adapted_from": "email",
            "original_tone": metadata.get("tone", "formal_professional")
        }
        
        # Preserve business context
        business_context = await self._extract_business_context(content)
        
        return {
            **context,
            "channel": "whatsapp",
            "content": casual_content,
            "adapted_content": casual_content,
            "metadata": adapted_metadata,
            "business_context_preserved": business_context,
            "adaptation_type": "formal_to_casual"
        }
    
    async def _adapt_email_to_voice(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt email context to voice (written → spoken)"""
        
        content = context.get("content", "")
        metadata = context.get("metadata", {})
        
        # Transform to speech-friendly format
        spoken_content = await self._written_to_spoken(content)
        
        # Adapt metadata for voice
        adapted_metadata = {
            **metadata,
            "tone": "conversational_professional",
            "speech_style": "natural_flowing",
            "formality_level": "professional_approachable",
            "adapted_from": "email"
        }
        
        # Preserve business context
        business_context = await self._extract_business_context(content)
        
        return {
            **context,
            "channel": "voice",
            "content": spoken_content,
            "adapted_content": spoken_content,
            "metadata": adapted_metadata,
            "business_context_preserved": business_context,
            "adaptation_type": "written_to_spoken"
        }
    
    async def _formalize_to_casual(self, content: str) -> str:
        """Transform formal email content to casual WhatsApp style"""
        
        # Common formal → casual transformations
        transformations = [
            (r"Thank you for your", "Thanks for"),
            (r"I would like to", "I'd like to"),
            (r"Could you please", "Can you"),
            (r"I am writing to", ""),
            (r"Please find attached", "Attached is"),
            (r"Please let me know", "Let me know"),
            (r"I look forward to", "Looking forward to"),
            (r"Best regards", "Thanks"),
            (r"Sincerely", "Thanks"),
            (r"Dear ([^,]+),", r"Hey \1,"),
            (r"I hope this email finds you well\.?", "Hope you're doing well!")
        ]
        
        casual_content = content
        for formal_pattern, casual_replacement in transformations:
            casual_content = re.sub(formal_pattern, casual_replacement, casual_content, flags=re.IGNORECASE)
        
        # Remove excessive formality
        casual_content = re.sub(r'\s+', ' ', casual_content)  # Normalize whitespace
        casual_content = casual_content.strip()
        
        # Ensure it doesn't start with formal greetings
        if casual_content.lower().startswith(("dear", "to whom it may concern")):
            lines = casual_content.split('\n')
            casual_content = '\n'.join(lines[1:]).strip()
        
        return casual_content
    
    async def _written_to_spoken(self, content: str) -> str:
        """Transform written email content to natural speech patterns"""
        
        # Break long sentences into speech-friendly segments
        sentences = re.split(r'[.!?]+', content)
        spoken_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            # Transform written patterns to spoken
            spoken_sentence = sentence
            
            # Replace written constructs with spoken equivalents
            spoken_transformations = [
                (r"Please note that", "Just so you know,"),
                (r"It should be noted", "Keep in mind"),
                (r"Furthermore", "Also"),
                (r"However", "But"),
                (r"Nevertheless", "Still"),
                (r"In addition", "Plus"),
                (r"Therefore", "So"),
                (r"Consequently", "As a result")
            ]
            
            for written_pattern, spoken_replacement in spoken_transformations:
                spoken_sentence = re.sub(
                    written_pattern, 
                    spoken_replacement, 
                    spoken_sentence, 
                    flags=re.IGNORECASE
                )
            
            # Break very long sentences
            if len(spoken_sentence) > 100:
                # Find natural break points
                break_points = [", and ", ", but ", ", so ", " because "]
                for break_point in break_points:
                    if break_point in spoken_sentence:
                        parts = spoken_sentence.split(break_point, 1)
                        spoken_sentences.extend([parts[0], break_point.strip() + " " + parts[1]])
                        break
                else:
                    spoken_sentences.append(spoken_sentence)
            else:
                spoken_sentences.append(spoken_sentence)
        
        return ". ".join(spoken_sentences) + "." if spoken_sentences else content
    
    async def _extract_business_context(self, content: str) -> Dict[str, Any]:
        """Extract key business context from email content"""
        
        # Simple keyword-based extraction (would use NLP in production)
        business_keywords = {
            "projects": ["project", "initiative", "campaign", "launch"],
            "financial": ["budget", "cost", "revenue", "profit", "investment"],
            "meetings": ["meeting", "call", "presentation", "demo"],
            "deadlines": ["deadline", "due", "by", "schedule"],
            "people": ["team", "client", "customer", "stakeholder"]
        }
        
        extracted_context = {}
        content_lower = content.lower()
        
        for category, keywords in business_keywords.items():
            for keyword in keywords:
                if keyword in content_lower:
                    if category not in extracted_context:
                        extracted_context[category] = []
                    
                    # Extract context around keyword (simplified)
                    start = max(0, content_lower.find(keyword) - 50)
                    end = min(len(content), content_lower.find(keyword) + 50)
                    context_snippet = content[start:end].strip()
                    
                    if context_snippet not in extracted_context[category]:
                        extracted_context[category].append(context_snippet)
        
        return extracted_context


class WhatsAppChannelAdapter(BaseChannelAdapter):
    """
    WhatsApp channel adapter for casual, quick communication
    
    Features:
    - Casual tone and emoji handling
    - Abbreviation expansion/contraction
    - Informal language adaptation
    - Quick message optimization
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_name = "whatsapp"
        
        # Common WhatsApp abbreviations
        self.abbreviations = {
            "fyi": "for your information",
            "btw": "by the way",
            "lmk": "let me know",
            "imo": "in my opinion",
            "rn": "right now",
            "nvm": "never mind",
            "omg": "oh my god",
            "tbh": "to be honest",
            "idk": "I don't know",
            "jk": "just kidding",
            "ttyl": "talk to you later",
            "brb": "be right back",
            "2morrow": "tomorrow",
            "2day": "today",
            "ur": "your",
            "u": "you",
            "b4": "before",
            "plz": "please",
            "thx": "thanks",
            "np": "no problem",
            "mvp": "minimum viable product",
            "rdy": "ready",
            "qa": "quality assurance"
        }
    
    async def adapt_to_channel(
        self,
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """
        Adapt WhatsApp context to target channel
        
        Args:
            context: WhatsApp context to adapt
            target_channel: Target channel (email, voice)
            
        Returns:
            Adapted context for target channel
        """
        start_time = time.time()
        
        try:
            if target_channel == "email":
                adapted_context = await self._adapt_whatsapp_to_email(context)
            elif target_channel == "voice":
                adapted_context = await self._adapt_whatsapp_to_voice(context)
            else:
                raise ContextTransformationError(f"Unsupported target channel: {target_channel}")
            
            adaptation_time = (time.time() - start_time) * 1000
            self._track_adaptation(target_channel, adaptation_time, True)
            
            logger.debug(f"WhatsApp→{target_channel} adaptation completed in {adaptation_time:.2f}ms")
            
            return adapted_context
            
        except Exception as e:
            adaptation_time = (time.time() - start_time) * 1000
            self._track_adaptation(target_channel, adaptation_time, False)
            
            logger.error(f"WhatsApp→{target_channel} adaptation failed in {adaptation_time:.2f}ms: {e}")
            raise ContextTransformationError(f"WhatsApp adaptation failed: {e}")
    
    async def _adapt_whatsapp_to_email(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt WhatsApp context to email (casual → formal)"""
        
        content = context.get("content", "")
        metadata = context.get("metadata", {})
        
        # Transform to formal tone
        formal_content = await self._casual_to_formal(content)
        
        # Adapt metadata
        adapted_metadata = {
            **metadata,
            "tone": "professional_positive",
            "formality_level": "business_formal",
            "adapted_from": "whatsapp",
            "original_tone": metadata.get("tone", "casual_friendly"),
            "abbreviations_expanded": True,
            "emoji_context_preserved": True
        }
        
        # Preserve emoji context as text descriptions
        emoji_context = await self._preserve_emoji_context(content, metadata)
        
        return {
            **context,
            "channel": "email",
            "content": formal_content,
            "adapted_content": formal_content,
            "metadata": adapted_metadata,
            "emoji_context": emoji_context,
            "adaptation_type": "casual_to_formal"
        }
    
    async def _adapt_whatsapp_to_voice(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt WhatsApp context to voice (text → speech)"""
        
        content = context.get("content", "")
        metadata = context.get("metadata", {})
        
        # Transform to speech patterns
        spoken_content = await self._text_to_speech_patterns(content)
        
        # Adapt metadata for voice
        adapted_metadata = {
            **metadata,
            "tone": "conversational_excited" if "excited" in metadata.get("sentiment", "") else "conversational_natural",
            "speech_style": "natural_enthusiastic",
            "adapted_from": "whatsapp",
            "emoji_emotion_preserved": True
        }
        
        # Preserve emotional context from emojis
        emotion_context = await self._extract_emoji_emotions(content, metadata)
        
        return {
            **context,
            "channel": "voice",
            "content": spoken_content,
            "adapted_content": spoken_content,
            "metadata": adapted_metadata,
            "emotion_continuity": emotion_context,
            "adaptation_type": "text_to_speech"
        }
    
    async def _casual_to_formal(self, content: str) -> str:
        """Transform casual WhatsApp content to formal email style"""
        
        formal_content = content
        
        # Expand abbreviations
        for abbrev, expansion in self.abbreviations.items():
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            formal_content = re.sub(pattern, expansion, formal_content, flags=re.IGNORECASE)
        
        # Remove emojis (preserve context separately)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE
        )
        formal_content = emoji_pattern.sub('', formal_content)
        
        # Formal transformations
        formal_transformations = [
            (r'\bhey\b', 'Hello'),
            (r'\bthanks\b', 'Thank you'),
            (r'\bthx\b', 'Thank you'),
            (r'\bokay\b', 'I understand'),
            (r'\bok\b', 'I understand'),
            (r'\byeah\b', 'Yes'),
            (r'\byep\b', 'Yes'),
            (r'\bnope\b', 'No'),
            (r'\bgonna\b', 'going to'),
            (r'\bwanna\b', 'want to'),
            (r'\bkinda\b', 'somewhat'),
            (r'\bsorta\b', 'somewhat'),
            (r'\btho\b', 'though'),
            (r'\bcuz\b', 'because'),
            (r'\bcause\b', 'because'),
            (r"can't", 'cannot'),
            (r"won't", 'will not'),
            (r"don't", 'do not'),
            (r"didn't", 'did not')
        ]
        
        for casual_pattern, formal_replacement in formal_transformations:
            formal_content = re.sub(
                casual_pattern, 
                formal_replacement, 
                formal_content, 
                flags=re.IGNORECASE
            )
        
        # Capitalize sentences properly
        sentences = re.split(r'[.!?]+', formal_content)
        capitalized_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                capitalized_sentences.append(sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper())
        
        formal_content = '. '.join(capitalized_sentences)
        
        # Add proper email structure if needed
        if formal_content and not formal_content.endswith('.'):
            formal_content += '.'
        
        return formal_content
    
    async def _text_to_speech_patterns(self, content: str) -> str:
        """Transform WhatsApp text to natural speech patterns"""
        
        spoken_content = content
        
        # Remove emojis but preserve emotional context
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags (iOS)
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE
        )
        
        # Replace some emojis with speech equivalents
        emoji_to_speech = {
            "😊": " - I'm happy about this",
            "😢": " - this is concerning",
            "😮": " - this is surprising",
            "👍": " - that sounds good",
            "👎": " - I don't think that's right",
            "🎉": " - this is exciting",
            "🚀": " - let's move fast on this",
            "⚠️": " - we need to be careful here",
            "✅": " - that's completed",
            "❌": " - that's not working"
        }
        
        for emoji, speech_equiv in emoji_to_speech.items():
            spoken_content = spoken_content.replace(emoji, speech_equiv)
        
        # Remove remaining emojis
        spoken_content = emoji_pattern.sub('', spoken_content)
        
        # Expand abbreviations for speech
        for abbrev, expansion in self.abbreviations.items():
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            spoken_content = re.sub(pattern, expansion, spoken_content, flags=re.IGNORECASE)
        
        # Add natural speech connectors
        if len(spoken_content.split()) < 5:  # Short messages
            spoken_content = "Just wanted to say " + spoken_content.lower()
        
        return spoken_content.strip()
    
    async def _preserve_emoji_context(self, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Preserve emoji context for formal adaptation"""
        
        # Extract emojis and their meanings
        emoji_meanings = {
            "😊": "positive_sentiment",
            "😢": "concern",
            "😮": "surprise", 
            "👍": "approval",
            "👎": "disapproval",
            "🎉": "celebration",
            "🚀": "urgency_enthusiasm",
            "⚠️": "warning",
            "✅": "completion",
            "❌": "failure_problem"
        }
        
        found_emojis = []
        emotional_context = []
        
        for emoji, meaning in emoji_meanings.items():
            if emoji in content:
                found_emojis.append(emoji)
                emotional_context.append(meaning)
        
        return {
            "emojis_found": found_emojis,
            "emotional_context": emotional_context,
            "sentiment_preserved": True
        }
    
    async def _extract_emoji_emotions(self, content: str, metadata: Dict[str, Any]) -> str:
        """Extract emotional context from emojis for voice adaptation"""
        
        emoji_emotions = {
            "😊": "happy",
            "😢": "concerned", 
            "😮": "surprised",
            "🎉": "excited",
            "🚀": "enthusiastic",
            "⚠️": "cautious",
            "❌": "frustrated"
        }
        
        emotions = []
        for emoji, emotion in emoji_emotions.items():
            if emoji in content:
                emotions.append(emotion)
        
        if emotions:
            return emotions[0]  # Use primary emotion
        
        # Fallback to metadata sentiment
        return metadata.get("sentiment", "neutral")


class VoiceChannelAdapter(BaseChannelAdapter):
    """
    Voice channel adapter for natural speech communication
    
    Features:
    - Speech pattern optimization
    - Filler word handling
    - Emotional context preservation
    - Natural conversation flow
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channel_name = "voice"
        
        # Common speech disfluencies to clean up
        self.disfluencies = [
            "um", "uh", "er", "ah", "like", "you know", "sort of", "kind of",
            "I mean", "well", "so", "actually", "basically", "literally"
        ]
    
    async def adapt_to_channel(
        self,
        context: Dict[str, Any],
        target_channel: str
    ) -> Dict[str, Any]:
        """
        Adapt voice context to target channel
        
        Args:
            context: Voice context to adapt
            target_channel: Target channel (email, whatsapp)
            
        Returns:
            Adapted context for target channel
        """
        start_time = time.time()
        
        try:
            if target_channel == "email":
                adapted_context = await self._adapt_voice_to_email(context)
            elif target_channel == "whatsapp":
                adapted_context = await self._adapt_voice_to_whatsapp(context)
            else:
                raise ContextTransformationError(f"Unsupported target channel: {target_channel}")
            
            adaptation_time = (time.time() - start_time) * 1000
            self._track_adaptation(target_channel, adaptation_time, True)
            
            logger.debug(f"Voice→{target_channel} adaptation completed in {adaptation_time:.2f}ms")
            
            return adapted_context
            
        except Exception as e:
            adaptation_time = (time.time() - start_time) * 1000
            self._track_adaptation(target_channel, adaptation_time, False)
            
            logger.error(f"Voice→{target_channel} adaptation failed in {adaptation_time:.2f}ms: {e}")
            raise ContextTransformationError(f"Voice adaptation failed: {e}")
    
    async def _adapt_voice_to_email(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt voice context to email (speech → written formal)"""
        
        content = context.get("content", "")
        metadata = context.get("metadata", {})
        
        # Clean up speech disfluencies and formalize
        formal_content = await self._speech_to_formal_written(content)
        
        # Adapt metadata
        adapted_metadata = {
            **metadata,
            "tone": "professional_thoughtful" if "thoughtful" in metadata.get("emotion", "") else "professional_urgent",
            "formality_level": "business_formal",
            "adapted_from": "voice",
            "emotion_preserved": metadata.get("emotion", "neutral"),
            "speech_cleaned": True
        }
        
        # Preserve emotional context
        emotional_context = await self._preserve_voice_emotion(content, metadata)
        
        return {
            **context,
            "channel": "email",
            "content": formal_content,
            "adapted_content": formal_content,
            "metadata": adapted_metadata,
            "emotion_preserved": emotional_context,
            "adaptation_type": "speech_to_written"
        }
    
    async def _adapt_voice_to_whatsapp(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Adapt voice context to WhatsApp (speech → casual text)"""
        
        content = context.get("content", "")
        metadata = context.get("metadata", {})
        
        # Convert to casual text while preserving natural flow
        casual_content = await self._speech_to_casual_text(content)
        
        # Adapt metadata
        adapted_metadata = {
            **metadata,
            "tone": "casual_thoughtful" if "thoughtful" in metadata.get("emotion", "") else "casual_natural",
            "adapted_from": "voice",
            "emotion_preserved": True,
            "natural_flow_maintained": True
        }
        
        # Add appropriate emojis based on emotion
        emoji_enhanced_content = await self._add_contextual_emojis(casual_content, metadata)
        
        return {
            **context,
            "channel": "whatsapp",
            "content": emoji_enhanced_content,
            "adapted_content": emoji_enhanced_content,
            "metadata": adapted_metadata,
            "adaptation_type": "speech_to_casual"
        }
    
    async def _speech_to_formal_written(self, content: str) -> str:
        """Convert speech patterns to formal written communication"""
        
        formal_content = content
        
        # Remove filler words
        for filler in self.disfluencies:
            pattern = r'\b' + re.escape(filler) + r'\b,?\s*'
            formal_content = re.sub(pattern, '', formal_content, flags=re.IGNORECASE)
        
        # Clean up repetitive words and self-corrections
        # Handle "I mean" and corrections
        formal_content = re.sub(r'\b(actually|I mean|well),?\s*', '', formal_content, flags=re.IGNORECASE)
        
        # Handle false starts and corrections
        # "We need to - no wait, I mean we should" → "We should"
        formal_content = re.sub(
            r'(.+?)\s*-\s*(no\s+)?(wait,?\s*)?(I\s+mean\s+)?(.+)', 
            r'\5', 
            formal_content, 
            flags=re.IGNORECASE
        )
        
        # Break run-on sentences into proper sentences
        sentences = self._split_run_on_sentences(formal_content)
        
        # Capitalize and punctuate properly
        formatted_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                # Capitalize first letter
                sentence = sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper()
                
                # Ensure proper punctuation
                if not sentence.endswith(('.', '!', '?')):
                    sentence += '.'
                
                formatted_sentences.append(sentence)
        
        return ' '.join(formatted_sentences)
    
    async def _speech_to_casual_text(self, content: str) -> str:
        """Convert speech to casual text while maintaining natural flow"""
        
        casual_content = content
        
        # Remove excessive filler words but keep some for natural feel
        excessive_fillers = ["um", "uh", "er", "ah"]
        for filler in excessive_fillers:
            # Remove multiple instances but keep occasional ones
            pattern = r'\b' + re.escape(filler) + r'\b\s*'
            occurrences = len(re.findall(pattern, casual_content, flags=re.IGNORECASE))
            if occurrences > 2:
                # Remove most instances, keep 1-2
                for _ in range(occurrences - 1):
                    casual_content = re.sub(pattern, '', casual_content, flags=re.IGNORECASE, count=1)
        
        # Keep natural speech patterns that work in text
        # "So I was thinking..." stays as is
        # "You know what I mean?" → "You know?"
        casual_content = re.sub(r'\byou know what I mean\?', 'you know?', casual_content, flags=re.IGNORECASE)
        
        # Maintain contractions
        contractions = {
            "I am": "I'm",
            "you are": "you're", 
            "we are": "we're",
            "they are": "they're",
            "it is": "it's",
            "that is": "that's",
            "we will": "we'll",
            "I will": "I'll",
            "cannot": "can't",
            "do not": "don't",
            "did not": "didn't",
            "will not": "won't"
        }
        
        for formal, casual in contractions.items():
            casual_content = re.sub(r'\b' + re.escape(formal) + r'\b', casual, casual_content, flags=re.IGNORECASE)
        
        # Ensure it's not too long for WhatsApp
        if len(casual_content) > 200:
            # Break into shorter, more digestible chunks
            sentences = casual_content.split('.')
            if len(sentences) > 1:
                # Take the most important part (usually the main point)
                casual_content = sentences[0].strip() + '.'
                if len(sentences) > 2:
                    casual_content += " " + sentences[1].strip() + '.'
        
        return casual_content.strip()
    
    async def _preserve_voice_emotion(self, content: str, metadata: Dict[str, Any]) -> str:
        """Preserve emotional context from voice for written adaptation"""
        
        emotion = metadata.get("emotion", "neutral")
        stress_indicators = metadata.get("stress_indicators", [])
        
        # Map emotions to written context
        emotion_mappings = {
            "frustration_overwhelm": "This situation is quite challenging and requires immediate attention",
            "excited": "This is an exciting opportunity",
            "concerned": "This requires careful consideration", 
            "thoughtful_uncertainty": "I'm still evaluating the best approach for this",
            "confident": "I'm confident in this direction"
        }
        
        emotional_context = emotion_mappings.get(emotion, emotion)
        
        return emotional_context
    
    async def _add_contextual_emojis(self, content: str, metadata: Dict[str, Any]) -> str:
        """Add appropriate emojis based on voice emotion context"""
        
        emotion = metadata.get("emotion", "neutral")
        
        # Map emotions to appropriate emojis
        emotion_emojis = {
            "excited": " 🎉",
            "frustrated": " 😤", 
            "concerned": " 🤔",
            "thoughtful": " 💭",
            "confident": " 👍",
            "uncertain": " 🤷",
            "happy": " 😊"
        }
        
        emoji = emotion_emojis.get(emotion, "")
        
        # Add emoji at the end if appropriate
        if emoji and not content.endswith(('.', '!', '?')):
            content += emoji
        elif emoji:
            content = content[:-1] + emoji + content[-1]
        
        return content
    
    def _split_run_on_sentences(self, content: str) -> List[str]:
        """Split run-on sentences into proper sentences"""
        
        # Simple sentence boundary detection
        # Look for conjunctions and break there
        conjunctions = [
            " and ", " but ", " or ", " so ", " because ", " since ", " although ", " while "
        ]
        
        sentences = [content]
        
        for conjunction in conjunctions:
            new_sentences = []
            for sentence in sentences:
                if conjunction in sentence and len(sentence) > 100:  # Only split long sentences
                    parts = sentence.split(conjunction, 1)
                    if len(parts) == 2:
                        new_sentences.append(parts[0].strip())
                        new_sentences.append(conjunction.strip().capitalize() + " " + parts[1].strip())
                    else:
                        new_sentences.append(sentence)
                else:
                    new_sentences.append(sentence)
            sentences = new_sentences
        
        return sentences


# Factory function for creating appropriate adapter
def get_channel_adapter(
    channel: str,
    personality_engine: PersonalityEngineConnector = None,
    performance_target_ms: int = 500
) -> BaseChannelAdapter:
    """
    Factory function to get appropriate channel adapter
    
    Args:
        channel: Channel name (email, whatsapp, voice)
        personality_engine: Optional personality engine
        performance_target_ms: Performance target in milliseconds
        
    Returns:
        Appropriate channel adapter instance
    """
    adapters = {
        "email": EmailChannelAdapter,
        "whatsapp": WhatsAppChannelAdapter,
        "voice": VoiceChannelAdapter
    }
    
    adapter_class = adapters.get(channel)
    if not adapter_class:
        raise ValueError(f"Unsupported channel: {channel}")
    
    return adapter_class(
        personality_engine=personality_engine,
        performance_target_ms=performance_target_ms
    )