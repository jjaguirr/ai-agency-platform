"""
ElevenLabs Voice Integration Channel
Bilingual Spanish/English voice capabilities with premium-casual EA personality
"""

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from enum import Enum
import json
import io

# Voice processing imports
import whisper
from elevenlabs import ElevenLabs, VoiceSettings
from elevenlabs.client import ElevenLabs as ElevenLabsClient

# Internal imports
from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType

logger = logging.getLogger(__name__)

class VoiceLanguage(Enum):
    ENGLISH = "en"
    SPANISH = "es"
    AUTO_DETECT = "auto"

class VoiceGender(Enum):
    FEMALE = "female"
    MALE = "male" 
    NEUTRAL = "neutral"

@dataclass
class VoiceConfig:
    """Voice synthesis configuration for premium-casual EA personality"""
    language: VoiceLanguage
    gender: VoiceGender
    stability: float = 0.75  # Voice stability (0.0-1.0)
    similarity_boost: float = 0.8  # Voice similarity (0.0-1.0)
    style: float = 0.6  # Premium-casual style
    use_speaker_boost: bool = True

@dataclass
class VoiceMessage(BaseMessage):
    """Enhanced message for voice communications"""
    audio_data: Optional[bytes] = None
    audio_format: str = "mp3"
    duration_seconds: Optional[float] = None
    detected_language: Optional[VoiceLanguage] = None
    confidence_score: Optional[float] = None
    transcript_text: Optional[str] = None
    voice_config: Optional[VoiceConfig] = None

class ElevenLabsVoiceChannel(BaseCommunicationChannel):
    """
    ElevenLabs voice integration with bilingual support and premium-casual personality
    
    Features:
    - Bilingual Spanish/English speech-to-text and text-to-speech
    - Automatic language detection and code-switching support
    - Premium-casual EA personality voices
    - WebRTC browser integration ready
    - Context-aware voice synthesis
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        super().__init__(customer_id, config)
        
        # Initialize ElevenLabs client
        self.elevenlabs_api_key = config.get("elevenlabs_api_key") or os.getenv("ELEVENLABS_API_KEY")
        if not self.elevenlabs_api_key:
            logger.warning(f"No ElevenLabs API key provided for customer {customer_id}")
            self.client = None
        else:
            self.client = ElevenLabsClient(api_key=self.elevenlabs_api_key)
        
        # Initialize Whisper for speech-to-text
        self.whisper_model = config.get("whisper_model", "base")
        self.speech_recognizer = None
        
        # Voice configuration for premium-casual personality
        self.voice_configs = self._initialize_voice_configs()
        self.current_language = VoiceLanguage.AUTO_DETECT
        
        # Performance settings
        self.max_audio_duration = config.get("max_audio_duration", 300)  # 5 minutes max
        self.response_timeout = config.get("response_timeout", 2.0)  # <2s response time
        
        logger.info(f"ElevenLabs voice channel initialized for customer {customer_id}")
    
    def _get_channel_type(self) -> ChannelType:
        return ChannelType.PHONE
    
    def _initialize_voice_configs(self) -> Dict[str, VoiceConfig]:
        """Initialize premium-casual voice configurations for bilingual support"""
        return {
            "en_female_casual": VoiceConfig(
                language=VoiceLanguage.ENGLISH,
                gender=VoiceGender.FEMALE,
                stability=0.75,
                similarity_boost=0.8,
                style=0.65,  # More casual for approachable feel
                use_speaker_boost=True
            ),
            "en_female_professional": VoiceConfig(
                language=VoiceLanguage.ENGLISH,
                gender=VoiceGender.FEMALE,
                stability=0.85,
                similarity_boost=0.75,
                style=0.45,  # Slightly more professional
                use_speaker_boost=True
            ),
            "es_female_casual": VoiceConfig(
                language=VoiceLanguage.SPANISH,
                gender=VoiceGender.FEMALE,
                stability=0.8,
                similarity_boost=0.85,
                style=0.7,  # Warm and approachable Spanish
                use_speaker_boost=True
            ),
            "es_female_professional": VoiceConfig(
                language=VoiceLanguage.SPANISH,
                gender=VoiceGender.FEMALE,
                stability=0.85,
                similarity_boost=0.8,
                style=0.5,  # Professional but warm Spanish
                use_speaker_boost=True
            ),
            "en_male_casual": VoiceConfig(
                language=VoiceLanguage.ENGLISH,
                gender=VoiceGender.MALE,
                stability=0.7,
                similarity_boost=0.8,
                style=0.6,
                use_speaker_boost=True
            ),
            "es_male_casual": VoiceConfig(
                language=VoiceLanguage.SPANISH,
                gender=VoiceGender.MALE,
                stability=0.75,
                similarity_boost=0.85,
                style=0.65,
                use_speaker_boost=True
            )
        }
    
    async def initialize(self) -> bool:
        """Initialize voice processing capabilities"""
        try:
            # Initialize Whisper for speech recognition
            if not self.speech_recognizer:
                logger.info(f"Loading Whisper model '{self.whisper_model}'...")
                self.speech_recognizer = whisper.load_model(self.whisper_model)
                logger.info("Whisper model loaded successfully")
            
            # Test ElevenLabs connection if API key is available
            if self.client:
                try:
                    # Test connection with a simple API call
                    voices = await self._get_available_voices()
                    logger.info(f"ElevenLabs connection successful. {len(voices)} voices available")
                except Exception as e:
                    logger.warning(f"ElevenLabs connection test failed: {e}")
            
            self.is_initialized = True
            logger.info(f"Voice channel initialized successfully for customer {self.customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize voice channel: {e}")
            return False
    
    async def _get_available_voices(self) -> List[Dict]:
        """Get available ElevenLabs voices"""
        if not self.client:
            return []
        
        try:
            voices = self.client.voices.get_all()
            # Handle different response structures
            if hasattr(voices, 'voices'):
                return [{"id": v.voice_id, "name": v.name, "category": getattr(v, 'category', 'unknown')} for v in voices.voices]
            else:
                return [{"id": v.voice_id, "name": v.name, "category": getattr(v, 'category', 'unknown')} for v in voices]
        except Exception as e:
            logger.error(f"Error fetching available voices: {e}")
            return []
    
    async def detect_language(self, audio_data: bytes) -> VoiceLanguage:
        """Detect language from audio data using Whisper"""
        try:
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            # Use Whisper to detect language
            result = self.speech_recognizer.transcribe(temp_file_path, language=None)
            detected_language = result.get("language", "en")
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Map detected language to VoiceLanguage enum
            if detected_language.lower().startswith("es"):
                return VoiceLanguage.SPANISH
            else:
                return VoiceLanguage.ENGLISH
                
        except Exception as e:
            logger.error(f"Language detection failed: {e}")
            return VoiceLanguage.ENGLISH  # Default to English
    
    async def speech_to_text(self, audio_data: bytes, language: VoiceLanguage = VoiceLanguage.AUTO_DETECT) -> Dict[str, Any]:
        """Convert speech to text with bilingual support"""
        try:
            # Save audio data to temporary file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            # Determine language for Whisper
            whisper_language = None
            if language == VoiceLanguage.SPANISH:
                whisper_language = "es"
            elif language == VoiceLanguage.ENGLISH:
                whisper_language = "en"
            # AUTO_DETECT uses None (Whisper auto-detects)
            
            # Transcribe audio
            result = self.speech_recognizer.transcribe(
                temp_file_path,
                language=whisper_language,
                word_timestamps=True
            )
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            # Extract results
            transcript = result["text"].strip()
            detected_language = result.get("language", "en")
            confidence = 0.9  # Whisper doesn't provide confidence scores directly
            
            # Map to our language enum
            lang_enum = VoiceLanguage.SPANISH if detected_language.startswith("es") else VoiceLanguage.ENGLISH
            
            logger.info(f"Speech-to-text completed: '{transcript[:50]}...' (language: {lang_enum.value})")
            
            return {
                "transcript": transcript,
                "detected_language": lang_enum,
                "confidence": confidence,
                "duration": result.get("duration", 0),
                "segments": result.get("segments", [])
            }
            
        except Exception as e:
            logger.error(f"Speech-to-text conversion failed: {e}")
            return {
                "transcript": "",
                "detected_language": VoiceLanguage.ENGLISH,
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _get_voice_id_for_config(self, voice_config: VoiceConfig) -> str:
        """Get appropriate ElevenLabs voice ID for configuration"""
        # Premium-casual voice selections for bilingual support
        voice_mappings = {
            # English voices - premium-casual personality
            "en_female_casual": "21m00Tcm4TlvDq8ikWAM",  # Rachel - Natural and conversational
            "en_female_professional": "AZnzlk1XvdvUeBnXmlld",  # Domi - Professional but warm
            "en_male_casual": "29vD33N1CtxCmqQRPOHJ",  # Drew - Friendly male voice
            
            # Spanish voices - natural and approachable
            "es_female_casual": "VR6AewLTigWG4xSOukaG",  # Spanish female - warm
            "es_female_professional": "pNInz6obpgDQGcFmaJgB",  # Spanish female - professional
            "es_male_casual": "yoZ06aMxZJJ28mfd3POQ"  # Spanish male - friendly
        }
        
        # Create key based on config
        key = f"{voice_config.language.value}_{voice_config.gender.value}_casual"
        if voice_config.style < 0.5:
            key = f"{voice_config.language.value}_{voice_config.gender.value}_professional"
        
        return voice_mappings.get(key, voice_mappings["en_female_casual"])
    
    async def text_to_speech(self, text: str, voice_config: VoiceConfig = None, context: Dict[str, Any] = None) -> bytes:
        """Convert text to speech with premium-casual personality"""
        if not self.client:
            logger.error("ElevenLabs client not initialized")
            return b""
        
        try:
            # Use default voice config if none provided
            if not voice_config:
                voice_config = self.voice_configs["en_female_casual"]
            
            # Enhance text with premium-casual personality markers if needed
            enhanced_text = self._enhance_text_for_voice(text, voice_config, context)
            
            # Get appropriate voice ID
            voice_id = self._get_voice_id_for_config(voice_config)
            
            # Create voice settings
            voice_settings = VoiceSettings(
                stability=voice_config.stability,
                similarity_boost=voice_config.similarity_boost,
                style=voice_config.style,
                use_speaker_boost=voice_config.use_speaker_boost
            )
            
            # Generate speech using the client
            logger.info(f"Generating speech for: '{text[:50]}...' (voice: {voice_id})")
            
            audio_generator = self.client.generate(
                text=enhanced_text,
                voice=voice_id,
                voice_settings=voice_settings,
                model="eleven_multilingual_v2"  # Supports both English and Spanish
            )
            
            # Convert generator to bytes
            audio_data = b"".join(audio_generator)
            
            logger.info(f"Speech generation completed ({len(audio_data)} bytes)")
            return audio_data
            
        except Exception as e:
            logger.error(f"Text-to-speech conversion failed: {e}")
            return b""
    
    def _enhance_text_for_voice(self, text: str, voice_config: VoiceConfig, context: Dict[str, Any] = None) -> str:
        """Enhance text with premium-casual personality markers for natural speech"""
        enhanced_text = text
        
        # Add natural pauses and emphasis for premium-casual delivery
        if context and context.get("conversation_type") == "onboarding":
            enhanced_text = f"Hi there! {enhanced_text}"
        
        # Language-specific enhancements
        if voice_config.language == VoiceLanguage.SPANISH:
            # Add Spanish conversational markers
            if not enhanced_text.startswith(("¡", "Hola", "¿")):
                if "?" in enhanced_text:
                    enhanced_text = f"¿{enhanced_text}"
                elif enhanced_text.endswith("!"):
                    enhanced_text = f"¡{enhanced_text}"
        
        # Premium-casual tone adjustments
        if voice_config.style > 0.6:  # More casual
            # Add conversational fillers for natural flow
            enhanced_text = enhanced_text.replace(". ", ". Um, ")
            enhanced_text = enhanced_text.replace("However,", "But hey,")
            enhanced_text = enhanced_text.replace("Furthermore,", "Also,")
        
        return enhanced_text
    
    async def process_voice_input(self, audio_data: bytes, metadata: Dict[str, Any] = None) -> VoiceMessage:
        """Process incoming voice input with language detection"""
        try:
            # Detect language
            detected_language = await self.detect_language(audio_data)
            
            # Convert speech to text
            stt_result = await self.speech_to_text(audio_data, detected_language)
            
            # Create voice message
            voice_message = VoiceMessage(
                content=stt_result["transcript"],
                from_number=metadata.get("from_number", "voice-input"),
                to_number=metadata.get("to_number", f"customer-{self.customer_id}"),
                channel=ChannelType.PHONE,
                message_id=str(uuid.uuid4()),
                conversation_id=metadata.get("conversation_id", str(uuid.uuid4())),
                timestamp=datetime.now(),
                customer_id=self.customer_id,
                metadata=metadata or {},
                audio_data=audio_data,
                audio_format=metadata.get("audio_format", "wav"),
                duration_seconds=stt_result.get("duration", 0),
                detected_language=detected_language,
                confidence_score=stt_result.get("confidence", 0.0),
                transcript_text=stt_result["transcript"]
            )
            
            logger.info(f"Processed voice input: '{stt_result['transcript'][:50]}...' ({detected_language.value})")
            return voice_message
            
        except Exception as e:
            logger.error(f"Voice input processing failed: {e}")
            # Return empty message with error
            return VoiceMessage(
                content="",
                from_number=metadata.get("from_number", "voice-input"),
                to_number=metadata.get("to_number", f"customer-{self.customer_id}"),
                channel=ChannelType.PHONE,
                message_id=str(uuid.uuid4()),
                conversation_id=metadata.get("conversation_id", str(uuid.uuid4())),
                timestamp=datetime.now(),
                customer_id=self.customer_id,
                metadata={"error": str(e)}
            )
    
    async def generate_voice_response(self, text: str, language: VoiceLanguage = None, context: Dict[str, Any] = None) -> bytes:
        """Generate voice response with automatic language matching"""
        try:
            # Auto-detect response language if not specified
            if not language:
                # Simple language detection based on content
                spanish_indicators = ["sí", "no", "hola", "gracias", "por favor", "cómo", "qué", "dónde", "cuándo"]
                text_lower = text.lower()
                if any(indicator in text_lower for indicator in spanish_indicators):
                    language = VoiceLanguage.SPANISH
                else:
                    language = VoiceLanguage.ENGLISH
            
            # Select appropriate voice configuration
            voice_key = f"{language.value}_female_casual"
            voice_config = self.voice_configs.get(voice_key, self.voice_configs["en_female_casual"])
            
            # Generate speech
            audio_data = await self.text_to_speech(text, voice_config, context)
            
            logger.info(f"Generated voice response ({len(audio_data)} bytes, language: {language.value})")
            return audio_data
            
        except Exception as e:
            logger.error(f"Voice response generation failed: {e}")
            return b""
    
    # Base channel interface implementation
    
    async def send_message(self, to: str, content: str, **kwargs) -> str:
        """Send voice message"""
        try:
            message_id = str(uuid.uuid4())
            
            # Generate voice response
            language = kwargs.get("language")
            context = kwargs.get("context", {})
            
            audio_data = await self.generate_voice_response(content, language, context)
            
            if not audio_data:
                logger.error("Failed to generate voice response")
                return ""
            
            # Store or transmit audio data (implementation depends on delivery method)
            # For now, we'll log the success
            logger.info(f"Voice message generated for {to}: {len(audio_data)} bytes")
            
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to send voice message: {e}")
            return ""
    
    async def handle_incoming_message(self, message_data: Dict[str, Any]) -> VoiceMessage:
        """Handle incoming voice message"""
        try:
            audio_data = message_data.get("audio_data", b"")
            metadata = message_data.get("metadata", {})
            
            if not audio_data:
                raise ValueError("No audio data provided")
            
            # Process voice input
            voice_message = await self.process_voice_input(audio_data, metadata)
            return voice_message
            
        except Exception as e:
            logger.error(f"Failed to handle incoming voice message: {e}")
            # Return empty message with error
            return VoiceMessage(
                content="",
                from_number=message_data.get("from_number", "unknown"),
                to_number=f"customer-{self.customer_id}",
                channel=ChannelType.PHONE,
                message_id=str(uuid.uuid4()),
                conversation_id=message_data.get("conversation_id", str(uuid.uuid4())),
                timestamp=datetime.now(),
                customer_id=self.customer_id,
                metadata={"error": str(e)}
            )
    
    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        """Validate webhook signature (implementation depends on provider)"""
        # TODO: Implement webhook signature validation based on voice provider
        return True
    
    async def health_check(self) -> Dict[str, Any]:
        """Extended health check for voice capabilities"""
        base_health = await super().health_check()
        
        voice_health = {
            "elevenlabs_available": self.client is not None,
            "whisper_model": self.whisper_model,
            "speech_recognition_ready": self.speech_recognizer is not None,
            "supported_languages": ["en", "es"],
            "voice_configs": list(self.voice_configs.keys()),
            "max_audio_duration": self.max_audio_duration,
            "response_timeout": self.response_timeout
        }
        
        return {**base_health, **voice_health}

# Voice Integration Utilities

async def test_voice_integration():
    """Test voice integration capabilities"""
    print("🎤 Testing ElevenLabs Voice Integration")
    
    # Test configuration
    config = {
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "whisper_model": "base"
    }
    
    customer_id = "test-voice-customer"
    voice_channel = ElevenLabsVoiceChannel(customer_id, config)
    
    # Initialize
    if await voice_channel.initialize():
        print("✅ Voice channel initialized successfully")
    else:
        print("❌ Voice channel initialization failed")
        return
    
    # Health check
    health = await voice_channel.health_check()
    print(f"📊 Health Status: {json.dumps(health, indent=2)}")
    
    # Test text-to-speech with bilingual content
    test_texts = [
        ("Hello! I'm Sarah, your Executive Assistant. How can I help you today?", VoiceLanguage.ENGLISH),
        ("¡Hola! Soy Sarah, tu Asistente Ejecutiva. ¿Cómo puedo ayudarte hoy?", VoiceLanguage.SPANISH)
    ]
    
    for text, language in test_texts:
        print(f"\n🔊 Testing TTS ({language.value}): {text}")
        audio_data = await voice_channel.generate_voice_response(text, language)
        if audio_data:
            print(f"✅ Generated {len(audio_data)} bytes of audio")
        else:
            print("❌ Failed to generate audio")
    
    print("\n🎉 Voice integration test completed!")

if __name__ == "__main__":
    asyncio.run(test_voice_integration())