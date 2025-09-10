"""
Comprehensive test suite for ElevenLabs voice integration
Tests bilingual capabilities, performance requirements, and EA integration
"""

import pytest
import asyncio
import os
import tempfile
import wave
import json
from datetime import datetime
from typing import Dict, Any
from unittest.mock import Mock, patch, AsyncMock

# Voice integration imports
from src.communication.voice_channel import (
    ElevenLabsVoiceChannel,
    VoiceLanguage,
    VoiceConfig,
    VoiceMessage
)
from src.agents.voice_integration import (
    VoiceEnabledExecutiveAssistant,
    create_voice_enabled_ea
)
from src.api.voice_api import create_voice_api
from fastapi.testclient import TestClient

@pytest.fixture
async def voice_channel():
    """Create test voice channel"""
    config = {
        "elevenlabs_api_key": "test-key",
        "whisper_model": "base"
    }
    channel = ElevenLabsVoiceChannel("test-customer", config)
    yield channel

@pytest.fixture
async def voice_ea():
    """Create test voice-enabled EA"""
    config = {
        "elevenlabs_api_key": "test-key",
        "whisper_model": "base"
    }
    ea = VoiceEnabledExecutiveAssistant("test-customer", config)
    yield ea

@pytest.fixture
def api_client():
    """Create test API client"""
    app = create_voice_api()
    return TestClient(app)

class TestElevenLabsVoiceChannel:
    """Test ElevenLabs voice channel functionality"""
    
    @pytest.mark.asyncio
    async def test_channel_initialization(self, voice_channel):
        """Test voice channel initialization"""
        # Mock the external dependencies
        with patch('whisper.load_model') as mock_whisper:
            mock_whisper.return_value = Mock()
            
            success = await voice_channel.initialize()
            assert success is True
            assert voice_channel.is_initialized is True
    
    @pytest.mark.asyncio
    async def test_language_detection(self, voice_channel):
        """Test automatic language detection"""
        # Create mock audio data
        audio_data = b"mock_audio_data"
        
        # Mock Whisper transcription
        with patch.object(voice_channel, 'speech_recognizer') as mock_whisper:
            mock_whisper.transcribe.return_value = {
                "text": "Hola, ¿cómo estás?",
                "language": "es"
            }
            
            # Mock temp file operations
            with patch('tempfile.NamedTemporaryFile'), \
                 patch('os.unlink'):
                
                language = await voice_channel.detect_language(audio_data)
                assert language == VoiceLanguage.SPANISH
    
    @pytest.mark.asyncio
    async def test_speech_to_text_english(self, voice_channel):
        """Test English speech-to-text conversion"""
        audio_data = b"mock_audio_data"
        
        with patch.object(voice_channel, 'speech_recognizer') as mock_whisper:
            mock_whisper.transcribe.return_value = {
                "text": "Hello, I need help with my business",
                "language": "en",
                "duration": 3.5,
                "segments": []
            }
            
            with patch('tempfile.NamedTemporaryFile'), \
                 patch('os.unlink'):
                
                result = await voice_channel.speech_to_text(audio_data, VoiceLanguage.ENGLISH)
                
                assert result["transcript"] == "Hello, I need help with my business"
                assert result["detected_language"] == VoiceLanguage.ENGLISH
                assert result["confidence"] > 0.8
    
    @pytest.mark.asyncio
    async def test_speech_to_text_spanish(self, voice_channel):
        """Test Spanish speech-to-text conversion"""
        audio_data = b"mock_audio_data"
        
        with patch.object(voice_channel, 'speech_recognizer') as mock_whisper:
            mock_whisper.transcribe.return_value = {
                "text": "Hola, necesito ayuda con mi negocio",
                "language": "es",
                "duration": 4.2,
                "segments": []
            }
            
            with patch('tempfile.NamedTemporaryFile'), \
                 patch('os.unlink'):
                
                result = await voice_channel.speech_to_text(audio_data, VoiceLanguage.SPANISH)
                
                assert result["transcript"] == "Hola, necesito ayuda con mi negocio"
                assert result["detected_language"] == VoiceLanguage.SPANISH
                assert result["confidence"] > 0.8
    
    @pytest.mark.asyncio
    async def test_text_to_speech_english(self, voice_channel):
        """Test English text-to-speech synthesis"""
        text = "Hello! I'm Sarah, your Executive Assistant. How can I help you today?"
        voice_config = VoiceConfig(
            language=VoiceLanguage.ENGLISH,
            gender=voice_channel.voice_configs["en_female_casual"].gender
        )
        
        # Mock ElevenLabs client
        with patch.object(voice_channel, 'client') as mock_client:
            with patch('elevenlabs.generate') as mock_generate:
                mock_generate.return_value = [b"mock_audio_data"]
                
                audio_data = await voice_channel.text_to_speech(text, voice_config)
                
                assert audio_data == b"mock_audio_data"
                mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_text_to_speech_spanish(self, voice_channel):
        """Test Spanish text-to-speech synthesis"""
        text = "¡Hola! Soy Sarah, tu Asistente Ejecutiva. ¿Cómo puedo ayudarte hoy?"
        voice_config = VoiceConfig(
            language=VoiceLanguage.SPANISH,
            gender=voice_channel.voice_configs["es_female_casual"].gender
        )
        
        # Mock ElevenLabs client
        with patch.object(voice_channel, 'client') as mock_client:
            with patch('elevenlabs.generate') as mock_generate:
                mock_generate.return_value = [b"mock_spanish_audio"]
                
                audio_data = await voice_channel.text_to_speech(text, voice_config)
                
                assert audio_data == b"mock_spanish_audio"
    
    @pytest.mark.asyncio
    async def test_voice_response_generation_auto_detect(self, voice_channel):
        """Test automatic language detection in voice response generation"""
        # Test Spanish content detection
        spanish_text = "¡Hola! Soy Sarah. ¿Cómo puedo ayudarte?"
        
        with patch.object(voice_channel, 'client'):
            with patch('elevenlabs.generate') as mock_generate:
                mock_generate.return_value = [b"spanish_audio"]
                
                audio_data = await voice_channel.generate_voice_response(spanish_text)
                assert audio_data == b"spanish_audio"
        
        # Test English content (default)
        english_text = "Hello! I'm Sarah. How can I help you?"
        
        with patch.object(voice_channel, 'client'):
            with patch('elevenlabs.generate') as mock_generate:
                mock_generate.return_value = [b"english_audio"]
                
                audio_data = await voice_channel.generate_voice_response(english_text)
                assert audio_data == b"english_audio"
    
    @pytest.mark.asyncio
    async def test_voice_message_processing(self, voice_channel):
        """Test complete voice message processing pipeline"""
        audio_data = b"mock_audio_data"
        metadata = {
            "from_number": "test-user",
            "conversation_id": "test-conversation",
            "audio_format": "wav"
        }
        
        # Mock speech recognition
        with patch.object(voice_channel, 'detect_language') as mock_detect:
            mock_detect.return_value = VoiceLanguage.ENGLISH
            
            with patch.object(voice_channel, 'speech_to_text') as mock_stt:
                mock_stt.return_value = {
                    "transcript": "Hello, I need business help",
                    "detected_language": VoiceLanguage.ENGLISH,
                    "confidence": 0.95,
                    "duration": 2.5
                }
                
                voice_message = await voice_channel.process_voice_input(audio_data, metadata)
                
                assert voice_message.content == "Hello, I need business help"
                assert voice_message.detected_language == VoiceLanguage.ENGLISH
                assert voice_message.confidence_score == 0.95
                assert voice_message.conversation_id == "test-conversation"

class TestVoiceEnabledExecutiveAssistant:
    """Test voice-enabled EA functionality"""
    
    @pytest.mark.asyncio
    async def test_ea_initialization(self, voice_ea):
        """Test voice-enabled EA initialization"""
        with patch.object(voice_ea.voice_channel, 'initialize') as mock_init:
            mock_init.return_value = True
            
            success = await voice_ea.initialize()
            assert success is True
    
    @pytest.mark.asyncio
    async def test_voice_conversation_start_english(self, voice_ea):
        """Test starting English voice conversation"""
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"welcome_audio_data"
            
            result = await voice_ea.start_voice_conversation(
                language_preference=VoiceLanguage.ENGLISH
            )
            
            assert result["success"] is True
            assert "conversation_id" in result
            assert "Hi there! I'm Sarah" in result["welcome_text"]
            assert result["language"] == "en"
            assert result["welcome_audio"] == b"welcome_audio_data"
    
    @pytest.mark.asyncio
    async def test_voice_conversation_start_spanish(self, voice_ea):
        """Test starting Spanish voice conversation"""
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"welcome_spanish_audio"
            
            result = await voice_ea.start_voice_conversation(
                language_preference=VoiceLanguage.SPANISH
            )
            
            assert result["success"] is True
            assert "¡Hola! Soy Sarah" in result["welcome_text"]
            assert result["language"] == "es"
    
    @pytest.mark.asyncio
    async def test_voice_message_handling_with_ea(self, voice_ea):
        """Test voice message handling with EA integration"""
        # Mock EA availability
        voice_ea.has_ea = True
        voice_ea.ea = Mock()
        voice_ea.ea.handle_customer_interaction = AsyncMock(
            return_value="I'll help you set up business automation workflows."
        )
        
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"ea_response_audio"
            
            result = await voice_ea.handle_voice_message(
                message="I need help automating my business processes",
                detected_language=VoiceLanguage.ENGLISH
            )
            
            assert result["success"] is True
            assert "automation workflows" in result["text_response"]
            assert result["voice_audio"] == b"ea_response_audio"
            assert result["response_time_seconds"] < 2.0  # Performance requirement
    
    @pytest.mark.asyncio
    async def test_voice_message_fallback_mode(self, voice_ea):
        """Test voice message handling without EA (fallback mode)"""
        # Simulate EA not available
        voice_ea.has_ea = False
        voice_ea.ea = None
        
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"fallback_audio"
            
            result = await voice_ea.handle_voice_message(
                message="Help me with my business",
                detected_language=VoiceLanguage.ENGLISH
            )
            
            assert result["success"] is True
            assert "I'm Sarah, your Executive Assistant" in result["text_response"]
            assert "business process automation" in result["text_response"]
    
    @pytest.mark.asyncio
    async def test_bilingual_conversation_context(self, voice_ea):
        """Test context preservation across bilingual conversation"""
        conversation_id = "test-bilingual-conversation"
        
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"response_audio"
            
            # Start in English
            result1 = await voice_ea.handle_voice_message(
                message="I run a marketing agency",
                conversation_id=conversation_id,
                detected_language=VoiceLanguage.ENGLISH
            )
            
            # Switch to Spanish
            result2 = await voice_ea.handle_voice_message(
                message="Necesito ayuda con redes sociales",
                conversation_id=conversation_id,
                detected_language=VoiceLanguage.SPANISH
            )
            
            # Verify context preservation
            context = await voice_ea.get_conversation_context(conversation_id)
            assert context["message_count"] == 2
            assert context["language_preference"] == "es"  # Last detected language
    
    @pytest.mark.asyncio
    async def test_performance_requirements(self, voice_ea):
        """Test response time performance requirements (<2s)"""
        start_time = datetime.now()
        
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"fast_response_audio"
            
            result = await voice_ea.handle_voice_message(
                message="Quick test message",
                detected_language=VoiceLanguage.ENGLISH
            )
            
            response_time = result["response_time_seconds"]
            assert response_time < 2.0, f"Response time {response_time}s exceeds 2s requirement"
    
    @pytest.mark.asyncio
    async def test_conversation_statistics(self, voice_ea):
        """Test conversation statistics and monitoring"""
        # Simulate some interactions
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"audio_data"
            
            for i in range(5):
                await voice_ea.handle_voice_message(
                    message=f"Test message {i}",
                    detected_language=VoiceLanguage.ENGLISH
                )
        
        stats = await voice_ea.get_voice_integration_stats()
        
        assert stats["voice_interactions"] == 5
        assert stats["average_response_time_seconds"] >= 0
        assert "performance_metrics" in stats
        assert stats["performance_metrics"]["target_response_time"] == 2.0

class TestVoiceAPI:
    """Test voice API endpoints"""
    
    def test_health_check_endpoint(self, api_client):
        """Test voice API health check"""
        with patch('src.api.voice_api.get_voice_ea') as mock_get_ea:
            mock_ea = Mock()
            mock_ea.voice_channel.health_check = AsyncMock(return_value={
                "initialized": True,
                "elevenlabs_available": True,
                "speech_recognition_ready": True,
                "supported_languages": ["en", "es"]
            })
            mock_get_ea.return_value = mock_ea
            
            response = api_client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "healthy"
            assert data["voice_channel_ready"] is True
            assert data["elevenlabs_available"] is True
            assert "en" in data["supported_languages"]
            assert "es" in data["supported_languages"]
    
    def test_start_conversation_endpoint(self, api_client):
        """Test conversation start endpoint"""
        with patch('src.api.voice_api.get_voice_ea') as mock_get_ea:
            mock_ea = Mock()
            mock_ea.start_voice_conversation = AsyncMock(return_value={
                "success": True,
                "conversation_id": "test-conversation-id",
                "welcome_text": "Hello! I'm Sarah",
                "welcome_audio": b"audio_data",
                "language": "en"
            })
            mock_get_ea.return_value = mock_ea
            
            response = api_client.post(
                "/voice/start-conversation/test-customer",
                json={"language_preference": "en", "context": {}}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["conversation_id"] == "test-conversation-id"
    
    def test_voice_message_endpoint(self, api_client):
        """Test voice message processing endpoint"""
        with patch('src.api.voice_api.get_voice_ea') as mock_get_ea:
            mock_ea = Mock()
            mock_ea.handle_voice_message = AsyncMock(return_value={
                "success": True,
                "text_response": "I'll help you with that",
                "voice_audio": b"response_audio",
                "detected_language": "en",
                "response_time_seconds": 1.5,
                "conversation_id": "test-conversation"
            })
            mock_get_ea.return_value = mock_ea
            
            response = api_client.post(
                "/voice/message/test-customer",
                json={
                    "text": "I need help with my business",
                    "language": "en",
                    "voice_style": "casual",
                    "conversation_id": "test-conversation"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["response_time_seconds"] < 2.0

class TestVoicePerformance:
    """Test voice integration performance requirements"""
    
    @pytest.mark.asyncio
    async def test_concurrent_voice_sessions(self):
        """Test handling multiple concurrent voice sessions"""
        from src.communication.webrtc_voice_handler import WebRTCVoiceManager
        
        manager = WebRTCVoiceManager()
        sessions = []
        
        # Create multiple mock sessions
        for i in range(10):
            mock_websocket = Mock()
            mock_websocket.client_state = "CONNECTED"
            
            with patch('src.agents.voice_integration.create_voice_enabled_ea') as mock_create:
                mock_ea = Mock()
                mock_ea.initialize = AsyncMock(return_value=True)
                mock_create.return_value = mock_ea
                
                session = await manager.create_session(
                    customer_id=f"test-customer-{i}",
                    websocket=mock_websocket
                )
                sessions.append(session)
        
        # Verify session management
        stats = manager.get_session_stats()
        assert stats["active_sessions"] == 10
        assert stats["sessions_by_customer"] == 10
    
    @pytest.mark.asyncio
    async def test_response_time_sla(self, voice_ea):
        """Test that voice responses meet SLA requirements"""
        response_times = []
        
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"audio_data"
            
            # Test multiple messages
            for i in range(20):
                start_time = datetime.now()
                
                result = await voice_ea.handle_voice_message(
                    message=f"Test message {i}",
                    detected_language=VoiceLanguage.ENGLISH
                )
                
                response_time = result["response_time_seconds"]
                response_times.append(response_time)
        
        # Check SLA compliance
        avg_response_time = sum(response_times) / len(response_times)
        p95_response_time = sorted(response_times)[int(0.95 * len(response_times))]
        
        assert avg_response_time < 1.0, f"Average response time {avg_response_time}s exceeds 1s target"
        assert p95_response_time < 2.0, f"95th percentile response time {p95_response_time}s exceeds 2s SLA"
        
        # Check that >90% of responses meet the 2s target
        meeting_target = sum(1 for t in response_times if t <= 2.0) / len(response_times)
        assert meeting_target >= 0.90, f"Only {meeting_target*100}% of responses meet 2s target"
    
    @pytest.mark.asyncio
    async def test_memory_usage_efficiency(self, voice_ea):
        """Test memory usage during voice processing"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process many voice messages
        with patch.object(voice_ea.voice_channel, 'generate_voice_response') as mock_tts:
            mock_tts.return_value = b"audio_data" * 1000  # Larger audio data
            
            for i in range(100):
                await voice_ea.handle_voice_message(
                    message=f"Memory test message {i}",
                    detected_language=VoiceLanguage.ENGLISH
                )
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (less than 100MB for 100 messages)
        assert memory_increase < 100, f"Memory usage increased by {memory_increase}MB"

class TestVoiceSecurity:
    """Test voice integration security features"""
    
    @pytest.mark.asyncio
    async def test_customer_isolation(self):
        """Test that customer voice data is properly isolated"""
        # Create two voice EAs for different customers
        ea1 = VoiceEnabledExecutiveAssistant("customer-1")
        ea2 = VoiceEnabledExecutiveAssistant("customer-2")
        
        # Simulate conversations
        conv1_id = "conversation-1"
        conv2_id = "conversation-2"
        
        with patch.object(ea1.voice_channel, 'generate_voice_response'), \
             patch.object(ea2.voice_channel, 'generate_voice_response'):
            
            await ea1.handle_voice_message("Private message 1", conv1_id)
            await ea2.handle_voice_message("Private message 2", conv2_id)
        
        # Verify isolation - EA1 should not have access to EA2's conversations
        ea1_context = await ea1.get_conversation_context(conv1_id)
        assert ea1_context["conversation_id"] == conv1_id
        
        # EA1 should not find EA2's conversation
        ea1_context_2 = await ea1.get_conversation_context(conv2_id)
        assert "error" in ea1_context_2
    
    @pytest.mark.asyncio
    async def test_audio_data_sanitization(self, voice_channel):
        """Test that audio data is properly sanitized"""
        # Test with potentially malicious audio metadata
        malicious_metadata = {
            "from_number": "<script>alert('xss')</script>",
            "conversation_id": "'; DROP TABLE conversations; --",
            "audio_format": "wav"
        }
        
        with patch.object(voice_channel, 'detect_language') as mock_detect, \
             patch.object(voice_channel, 'speech_to_text') as mock_stt:
            
            mock_detect.return_value = VoiceLanguage.ENGLISH
            mock_stt.return_value = {
                "transcript": "Clean transcript",
                "detected_language": VoiceLanguage.ENGLISH,
                "confidence": 0.9,
                "duration": 2.0
            }
            
            voice_message = await voice_channel.process_voice_input(
                b"audio_data", 
                malicious_metadata
            )
            
            # Verify that malicious content doesn't propagate
            assert voice_message.content == "Clean transcript"
            assert "<script>" not in voice_message.from_number
            assert "DROP TABLE" not in voice_message.conversation_id

if __name__ == "__main__":
    pytest.main([__file__, "-v"])