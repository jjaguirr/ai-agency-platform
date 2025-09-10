"""
Channel Adapters - Unit Tests

Tests for channel-specific adaptation layers that handle context preservation
and transformation between different communication channels.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.communication.channel_adapters import (
    EmailChannelAdapter,
    WhatsAppChannelAdapter, 
    VoiceChannelAdapter,
    ChannelAdapterError,
    ContextTransformationError
)
from src.memory.unified_context_store import ContextEntry


class TestEmailChannelAdapter:
    """Test suite for EmailChannelAdapter"""
    
    @pytest.fixture
    def email_adapter(self):
        """Initialize EmailChannelAdapter with test configuration"""
        return EmailChannelAdapter(
            personality_engine=AsyncMock(),
            performance_target_ms=500
        )
    
    @pytest.fixture
    def sample_email_context(self):
        """Sample email context for testing"""
        return {
            "customer_id": "test_customer_001",
            "channel": "email",
            "conversation_thread": "board_meeting_prep",
            "content": "Thank you for your assistance with the board presentation. Could you please review the financial projections and provide feedback by tomorrow?",
            "metadata": {
                "tone": "formal_professional",
                "urgency": "high",
                "formality_level": "business_formal",
                "recipients": ["board@company.com"],
                "subject": "Board Meeting Preparation - Financial Review"
            }
        }
    
    @pytest.mark.asyncio
    async def test_adapt_to_whatsapp_formal_to_casual(self, email_adapter, sample_email_context):
        """Test Email → WhatsApp adaptation (formal to casual)"""
        # Action
        start_time = time.time()
        adapted_context = await email_adapter.adapt_to_channel(
            context=sample_email_context,
            target_channel="whatsapp"
        )
        adaptation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert adaptation_time < 500, f"Adaptation took {adaptation_time}ms, exceeds 500ms target"
        assert adapted_context["channel"] == "whatsapp"
        assert adapted_context["conversation_thread"] == "board_meeting_prep"
        assert adapted_context["metadata"]["tone"] == "casual_friendly"
        assert adapted_context["metadata"]["formality_level"] == "approachable_professional"
        
        # Verify content transformation
        content = adapted_context["content"].lower()
        assert "thanks" in content or "hey" in content  # More casual greeting
        assert "board presentation" in content  # Context preserved
        assert "financial projections" in content  # Key information preserved
    
    @pytest.mark.asyncio
    async def test_adapt_to_voice_written_to_spoken(self, email_adapter, sample_email_context):
        """Test Email → Voice adaptation (written to spoken)"""
        # Action
        adapted_context = await email_adapter.adapt_to_channel(
            context=sample_email_context,
            target_channel="voice"
        )
        
        # Assertions
        assert adapted_context["channel"] == "voice"
        assert adapted_context["metadata"]["tone"] == "conversational_professional"
        assert adapted_context["metadata"]["speech_style"] == "natural_flowing"
        
        # Verify content suitable for speech
        content = adapted_context["content"]
        assert len(content.split('.')) >= 2  # Broken into speech-friendly segments
        assert "um" not in content.lower()  # No filler words added
        assert "board presentation" in content  # Context preserved
    
    @pytest.mark.asyncio
    async def test_preserve_business_context_across_channels(self, email_adapter, sample_email_context):
        """Test that business context is preserved during channel adaptation"""
        # Action: Adapt to multiple channels
        whatsapp_context = await email_adapter.adapt_to_channel(
            context=sample_email_context,
            target_channel="whatsapp"
        )
        
        voice_context = await email_adapter.adapt_to_channel(
            context=sample_email_context,
            target_channel="voice"
        )
        
        # Assertions - Business context preserved
        for adapted_context in [whatsapp_context, voice_context]:
            assert adapted_context["conversation_thread"] == "board_meeting_prep"
            assert "financial projections" in adapted_context["content"]
            assert adapted_context["metadata"]["urgency"] == "high"
            
            # Context summary should contain key business information
            context_summary = adapted_context.get("context_summary", "")
            assert "board" in context_summary.lower()
            assert "financial" in context_summary.lower()
    
    @pytest.mark.asyncio
    async def test_handle_formatting_preservation(self, email_adapter):
        """Test preservation of important formatting elements"""
        email_context = {
            "customer_id": "test_customer_002",
            "channel": "email",
            "conversation_thread": "project_update",
            "content": """
            Project Update:
            
            1. Database migration - COMPLETED
            2. API integration - IN PROGRESS
            3. Frontend updates - PENDING
            
            Next steps:
            - Complete API integration by Friday
            - Schedule frontend review meeting
            
            Please let me know if you have any questions.
            """,
            "metadata": {
                "tone": "business_update",
                "contains_lists": True,
                "structure": "formal_report"
            }
        }
        
        # Action
        adapted_context = await email_adapter.adapt_to_channel(
            context=email_context,
            target_channel="whatsapp"
        )
        
        # Assertions
        content = adapted_context["content"]
        assert "database migration" in content.lower()
        assert "completed" in content.lower()
        assert "api integration" in content.lower()
        assert "friday" in content.lower()
        
        # Should maintain key information while adapting format
        assert adapted_context["metadata"]["key_points_preserved"] is True


class TestWhatsAppChannelAdapter:
    """Test suite for WhatsAppChannelAdapter"""
    
    @pytest.fixture
    def whatsapp_adapter(self):
        """Initialize WhatsAppChannelAdapter with test configuration"""
        return WhatsAppChannelAdapter(
            personality_engine=AsyncMock(),
            performance_target_ms=500
        )
    
    @pytest.fixture
    def sample_whatsapp_context(self):
        """Sample WhatsApp context for testing"""
        return {
            "customer_id": "test_customer_001",
            "channel": "whatsapp",
            "conversation_thread": "daily_checkin",
            "content": "hey! quick update - closed that big deal we talked about 🎉 team is pumped!",
            "metadata": {
                "tone": "casual_excited",
                "emojis": ["🎉"],
                "urgency": "medium",
                "sentiment": "positive_excited",
                "informal_language": True
            }
        }
    
    @pytest.mark.asyncio
    async def test_adapt_to_email_casual_to_formal(self, whatsapp_adapter, sample_whatsapp_context):
        """Test WhatsApp → Email adaptation (casual to formal)"""
        # Action
        start_time = time.time()
        adapted_context = await whatsapp_adapter.adapt_to_channel(
            context=sample_whatsapp_context,
            target_channel="email"
        )
        adaptation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert adaptation_time < 500, f"Adaptation took {adaptation_time}ms, exceeds 500ms target"
        assert adapted_context["channel"] == "email"
        assert adapted_context["conversation_thread"] == "daily_checkin"
        assert adapted_context["metadata"]["tone"] == "professional_positive"
        assert adapted_context["metadata"]["formality_level"] == "business_formal"
        
        # Verify content transformation
        content = adapted_context["content"]
        assert "closed" in content.lower()  # Key information preserved
        assert "deal" in content.lower()  # Business context preserved
        assert "team" in content.lower()  # Context preserved
        assert "🎉" not in content  # Emojis removed for email
        assert content[0].isupper()  # Proper capitalization
    
    @pytest.mark.asyncio
    async def test_adapt_to_voice_text_to_speech(self, whatsapp_adapter, sample_whatsapp_context):
        """Test WhatsApp → Voice adaptation (text to speech patterns)"""
        # Action
        adapted_context = await whatsapp_adapter.adapt_to_channel(
            context=sample_whatsapp_context,
            target_channel="voice"
        )
        
        # Assertions
        assert adapted_context["channel"] == "voice"
        assert adapted_context["metadata"]["tone"] == "conversational_excited"
        assert adapted_context["metadata"]["speech_style"] == "natural_enthusiastic"
        
        # Verify speech-friendly transformation
        content = adapted_context["content"]
        assert "closed that big deal" in content.lower()  # Key info preserved
        assert "excited" in content.lower() or "great" in content.lower()  # Emotion conveyed
        assert len(content.split('.')) >= 2  # Speech-friendly pacing
    
    @pytest.mark.asyncio
    async def test_preserve_emoji_context_in_adaptation(self, whatsapp_adapter):
        """Test that emoji context is preserved during adaptation"""
        whatsapp_context = {
            "customer_id": "test_customer_003",
            "channel": "whatsapp",
            "conversation_thread": "project_status",
            "content": "project update: api done ✅ frontend stuck ⚠️ need help with database 🆘",
            "metadata": {
                "tone": "urgent_concise",
                "emojis": ["✅", "⚠️", "🆘"],
                "status_indicators": True,
                "urgency": "high"
            }
        }
        
        # Action: Adapt to email
        adapted_context = await whatsapp_adapter.adapt_to_channel(
            context=whatsapp_context,
            target_channel="email"
        )
        
        # Assertions
        content = adapted_context["content"]
        assert "api" in content.lower() and ("complete" in content.lower() or "done" in content.lower())
        assert "frontend" in content.lower() and ("stuck" in content.lower() or "blocked" in content.lower())
        assert "database" in content.lower() and ("help" in content.lower() or "assistance" in content.lower())
        
        # Emoji context should be preserved as text
        assert adapted_context["metadata"]["emoji_context_preserved"] is True
        assert adapted_context["metadata"]["urgency"] == "high"  # Urgency preserved from 🆘
    
    @pytest.mark.asyncio
    async def test_handle_abbreviations_and_slang(self, whatsapp_adapter):
        """Test handling of WhatsApp abbreviations and casual language"""
        whatsapp_context = {
            "customer_id": "test_customer_004",
            "channel": "whatsapp",
            "conversation_thread": "team_coordination",
            "content": "fyi the mvp is rdy for qa, gonna deploy 2morrow. lmk if u need anything b4 that",
            "metadata": {
                "tone": "casual_informative",
                "abbreviations": ["fyi", "mvp", "rdy", "qa", "2morrow", "lmk", "u", "b4"],
                "urgency": "medium"
            }
        }
        
        # Action: Adapt to email
        adapted_context = await whatsapp_adapter.adapt_to_channel(
            context=whatsapp_context,
            target_channel="email"
        )
        
        # Assertions
        content = adapted_context["content"].lower()
        assert "for your information" in content or "fyi" in content
        assert "minimum viable product" in content or "mvp" in content
        assert "ready" in content
        assert "quality assurance" in content or "testing" in content
        assert "tomorrow" in content
        assert "let me know" in content or "please inform" in content
        assert "before" in content
        
        # Should be properly formatted for email
        assert adapted_context["metadata"]["abbreviations_expanded"] is True


class TestVoiceChannelAdapter:
    """Test suite for VoiceChannelAdapter"""
    
    @pytest.fixture
    def voice_adapter(self):
        """Initialize VoiceChannelAdapter with test configuration"""
        return VoiceChannelAdapter(
            personality_engine=AsyncMock(),
            performance_target_ms=500
        )
    
    @pytest.fixture
    def sample_voice_context(self):
        """Sample voice context for testing"""
        return {
            "customer_id": "test_customer_001",
            "channel": "voice",
            "conversation_thread": "strategy_discussion",
            "content": "So I was thinking about our go-to-market strategy and, um, I think we might need to pivot our approach because the current market research shows that, well, our target audience is actually more price-sensitive than we initially thought",
            "metadata": {
                "tone": "thoughtful_uncertain",
                "speech_patterns": ["filler_words", "run_on_sentences", "self_correction"],
                "emotion": "contemplative",
                "transcript_confidence": 0.92,
                "speaker_pace": "moderate"
            }
        }
    
    @pytest.mark.asyncio
    async def test_adapt_to_email_speech_to_written(self, voice_adapter, sample_voice_context):
        """Test Voice → Email adaptation (speech to written format)"""
        # Action
        start_time = time.time()
        adapted_context = await voice_adapter.adapt_to_channel(
            context=sample_voice_context,
            target_channel="email"
        )
        adaptation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert adaptation_time < 500, f"Adaptation took {adaptation_time}ms, exceeds 500ms target"
        assert adapted_context["channel"] == "email"
        assert adapted_context["conversation_thread"] == "strategy_discussion"
        assert adapted_context["metadata"]["tone"] == "professional_thoughtful"
        
        # Verify speech-to-text cleanup
        content = adapted_context["content"]
        assert "um" not in content.lower()  # Filler words removed
        assert "well" not in content.lower() or content.lower().count("well") <= 1  # Excessive fillers removed
        assert "go-to-market strategy" in content.lower()  # Key concepts preserved
        assert "market research" in content.lower()  # Important info preserved
        assert "price-sensitive" in content.lower()  # Insights preserved
        
        # Should be properly structured for written communication
        assert len(content.split('.')) >= 2  # Broken into proper sentences
        assert content[0].isupper()  # Proper capitalization
    
    @pytest.mark.asyncio
    async def test_adapt_to_whatsapp_speech_to_casual_text(self, voice_adapter, sample_voice_context):
        """Test Voice → WhatsApp adaptation (speech to casual text)"""
        # Action
        adapted_context = await voice_adapter.adapt_to_channel(
            context=sample_voice_context,
            target_channel="whatsapp"
        )
        
        # Assertions
        assert adapted_context["channel"] == "whatsapp"
        assert adapted_context["metadata"]["tone"] == "casual_thoughtful"
        
        # Verify casual text transformation
        content = adapted_context["content"]
        assert "thinking about" in content.lower()  # Natural language preserved
        assert "go-to-market" in content.lower() or "gtm" in content.lower()  # Concept preserved
        assert "market research" in content.lower()  # Key info preserved
        assert len(content) < len(sample_voice_context["content"])  # More concise
    
    @pytest.mark.asyncio
    async def test_preserve_emotional_context(self, voice_adapter):
        """Test preservation of emotional context from voice"""
        voice_context = {
            "customer_id": "test_customer_005",
            "channel": "voice",
            "conversation_thread": "difficult_client_situation",
            "content": "I'm really frustrated with this client situation. They keep changing requirements and it's affecting our team's morale. I don't know how to handle this anymore.",
            "metadata": {
                "tone": "frustrated_stressed",
                "emotion": "frustration_overwhelm",
                "stress_indicators": ["really frustrated", "don't know how"],
                "urgency": "high"
            }
        }
        
        # Action: Adapt to email
        adapted_context = await voice_adapter.adapt_to_channel(
            context=voice_context,
            target_channel="email"
        )
        
        # Assertions
        assert adapted_context["metadata"]["emotion_preserved"] == "frustration_overwhelm"
        assert adapted_context["metadata"]["urgency"] == "high"
        
        content = adapted_context["content"]
        assert "client situation" in content.lower()
        assert "requirements" in content.lower() and "changing" in content.lower()
        assert "team" in content.lower() and "morale" in content.lower()
        
        # Should convey urgency professionally
        assert adapted_context["metadata"]["tone"] == "professional_urgent"
    
    @pytest.mark.asyncio
    async def test_handle_speech_disfluencies(self, voice_adapter):
        """Test handling of speech disfluencies and corrections"""
        voice_context = {
            "customer_id": "test_customer_006",
            "channel": "voice",
            "conversation_thread": "technical_discussion",
            "content": "We need to implement the, uh, the authentication system - no wait, I mean the authorization system for the API. Actually, both authentication and authorization. Sorry, let me clarify...",
            "metadata": {
                "tone": "technical_corrective",
                "speech_patterns": ["self_correction", "clarification", "hesitation"],
                "disfluencies": ["uh", "wait", "actually", "sorry"]
            }
        }
        
        # Action: Adapt to email
        adapted_context = await voice_adapter.adapt_to_channel(
            context=voice_context,
            target_channel="email"
        )
        
        # Assertions
        content = adapted_context["content"]
        assert "uh" not in content.lower()
        assert "wait" not in content.lower() or content.lower().count("wait") == 0
        assert "sorry" not in content.lower()
        
        # Should preserve the corrected information
        assert "authentication" in content.lower()
        assert "authorization" in content.lower()
        assert "api" in content.lower()
        
        # Should be clear and concise
        assert content.count("actually") <= 1  # Minimize redundant words
        assert len(content.split('.')) <= 3  # Well-structured sentences


class TestChannelAdapterPerformance:
    """Performance tests for channel adaptation"""
    
    @pytest.mark.asyncio
    async def test_adaptation_performance_under_load(self):
        """Test adaptation performance with high-volume concurrent requests"""
        adapters = {
            "email": EmailChannelAdapter(personality_engine=AsyncMock()),
            "whatsapp": WhatsAppChannelAdapter(personality_engine=AsyncMock()),
            "voice": VoiceChannelAdapter(personality_engine=AsyncMock())
        }
        
        # Setup: Create contexts for adaptation
        contexts = []
        for i in range(100):
            context = {
                "customer_id": f"perf_test_customer_{i}",
                "channel": ["email", "whatsapp", "voice"][i % 3],
                "conversation_thread": f"perf_thread_{i}",
                "content": f"Performance test message {i} with detailed content for adaptation testing",
                "metadata": {"tone": "professional", "urgency": "medium"}
            }
            contexts.append(context)
        
        # Action: Concurrent adaptations
        start_time = time.time()
        tasks = []
        for i, context in enumerate(contexts):
            source_channel = context["channel"]
            target_channel = ["whatsapp", "voice", "email"][i % 3]  # Rotate targets
            
            if source_channel != target_channel:
                adapter = adapters[source_channel]
                task = adapter.adapt_to_channel(context, target_channel)
                tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_adaptation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert total_adaptation_time < 10000, f"Concurrent adaptations took {total_adaptation_time}ms, exceeds 10s threshold"
        
        # Verify successful adaptations
        successful_adaptations = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_adaptations) > 50  # At least 50% success rate
        
        # Average adaptation time should be reasonable
        avg_adaptation_time = total_adaptation_time / len(tasks)
        assert avg_adaptation_time < 1000, f"Average adaptation time {avg_adaptation_time}ms too high"
    
    @pytest.mark.asyncio
    async def test_memory_efficiency_during_adaptation(self):
        """Test memory efficiency during large context adaptations"""
        email_adapter = EmailChannelAdapter(personality_engine=AsyncMock())
        
        # Setup: Large context content
        large_content = "Large conversation content. " * 1000  # ~30KB content
        large_context = {
            "customer_id": "memory_test_customer",
            "channel": "email",
            "conversation_thread": "memory_efficiency_test",
            "content": large_content,
            "metadata": {
                "tone": "professional",
                "conversation_history": [f"Message {i}" for i in range(100)]
            }
        }
        
        # Action: Adapt large context
        start_time = time.time()
        adapted_context = await email_adapter.adapt_to_channel(
            context=large_context,
            target_channel="whatsapp"
        )
        adaptation_time = (time.time() - start_time) * 1000
        
        # Assertions
        assert adaptation_time < 2000, f"Large context adaptation took {adaptation_time}ms, exceeds 2s threshold"
        assert adapted_context["channel"] == "whatsapp"
        assert len(adapted_context["content"]) < len(large_content)  # Should be condensed
        assert adapted_context["conversation_thread"] == "memory_efficiency_test"  # Context preserved