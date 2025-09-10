"""
Executive Assistant Voice Integration
Connects ElevenLabs voice capabilities with existing EA system
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
import uuid

# EA imports
try:
    from .executive_assistant import ExecutiveAssistant, ConversationChannel
    EA_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"Executive Assistant not available: {e}")
    EA_AVAILABLE = False

# Voice integration imports
from ..communication.voice_channel import ElevenLabsVoiceChannel, VoiceLanguage, VoiceConfig
from ..communication.webrtc_voice_handler import WebRTCVoiceManager, handle_voice_websocket

logger = logging.getLogger(__name__)

class VoiceEnabledExecutiveAssistant:
    """
    Executive Assistant enhanced with bilingual voice capabilities
    
    Features:
    - Bilingual Spanish/English voice conversations
    - Premium-casual personality in voice synthesis
    - Seamless integration with existing EA memory and workflows
    - Context-aware voice responses
    - Language detection and automatic switching
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        self.customer_id = customer_id
        self.config = config or {}
        
        # Initialize core EA if available
        if EA_AVAILABLE:
            self.ea = ExecutiveAssistant(customer_id)
            self.has_ea = True
        else:
            self.ea = None
            self.has_ea = False
            logger.warning(f"EA not available for customer {customer_id}, using voice-only mode")
        
        # Initialize voice channel
        voice_config = {
            "elevenlabs_api_key": config.get("elevenlabs_api_key"),
            "whisper_model": config.get("whisper_model", "base"),
            **config.get("voice_settings", {})
        }
        
        self.voice_channel = ElevenLabsVoiceChannel(customer_id, voice_config)
        
        # Voice session management
        self.active_conversations: Dict[str, Dict[str, Any]] = {}
        self.conversation_contexts: Dict[str, Dict[str, Any]] = {}
        
        # Performance tracking
        self.voice_interactions = 0
        self.response_times = []
        
        logger.info(f"Voice-enabled EA initialized for customer {customer_id}")
    
    async def initialize(self) -> bool:
        """Initialize voice-enabled EA system"""
        try:
            # Initialize voice channel
            voice_ready = await self.voice_channel.initialize()
            if not voice_ready:
                logger.error("Voice channel initialization failed")
                return False
            
            logger.info(f"Voice-enabled EA system ready for customer {self.customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize voice-enabled EA: {e}")
            return False
    
    async def handle_voice_message(
        self, 
        message: str, 
        conversation_id: str = None,
        detected_language: VoiceLanguage = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Handle voice message through EA system with bilingual support
        """
        start_time = datetime.now()
        
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        try:
            # Store conversation context
            if conversation_id not in self.conversation_contexts:
                self.conversation_contexts[conversation_id] = {
                    "language_preference": detected_language,
                    "start_time": start_time,
                    "message_count": 0,
                    "context": context or {}
                }
            
            conv_context = self.conversation_contexts[conversation_id]
            conv_context["message_count"] += 1
            conv_context["last_activity"] = start_time
            
            # Update language preference if detected
            if detected_language and detected_language != VoiceLanguage.AUTO_DETECT:
                conv_context["language_preference"] = detected_language
            
            # Process through EA if available
            if self.has_ea:
                ea_response = await self._process_through_ea(message, conversation_id, conv_context)
            else:
                ea_response = self._generate_fallback_response(message, detected_language)
            
            # Enhance response for voice delivery
            voice_response = self._enhance_response_for_voice(
                ea_response, 
                detected_language or conv_context.get("language_preference", VoiceLanguage.ENGLISH),
                conv_context
            )
            
            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds()
            self.response_times.append(response_time)
            self.voice_interactions += 1
            
            # Generate voice audio
            voice_audio = None
            if self.voice_channel:
                voice_audio = await self.voice_channel.generate_voice_response(
                    voice_response,
                    detected_language or conv_context.get("language_preference", VoiceLanguage.ENGLISH),
                    context={
                        "conversation_id": conversation_id,
                        "message_count": conv_context["message_count"],
                        "conversation_type": context.get("conversation_type", "general")
                    }
                )
            
            logger.info(f"Voice message processed in {response_time:.2f}s (language: {detected_language})")
            
            return {
                "text_response": voice_response,
                "original_ea_response": ea_response,
                "voice_audio": voice_audio,
                "detected_language": detected_language.value if detected_language else "en",
                "response_time_seconds": response_time,
                "conversation_id": conversation_id,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error handling voice message: {e}")
            
            # Generate error response
            error_response = self._generate_error_response(detected_language or VoiceLanguage.ENGLISH)
            
            return {
                "text_response": error_response,
                "original_ea_response": error_response,
                "voice_audio": None,
                "detected_language": (detected_language.value if detected_language else "en"),
                "response_time_seconds": (datetime.now() - start_time).total_seconds(),
                "conversation_id": conversation_id,
                "success": False,
                "error": str(e)
            }
    
    async def _process_through_ea(
        self, 
        message: str, 
        conversation_id: str, 
        conv_context: Dict[str, Any]
    ) -> str:
        """Process message through existing EA system"""
        try:
            # Determine channel based on language
            language = conv_context.get("language_preference", VoiceLanguage.ENGLISH)
            channel = ConversationChannel.PHONE  # Voice is treated as phone channel
            
            # Add language context to the message if Spanish
            if language == VoiceLanguage.SPANISH:
                # Add subtle language hint for EA context
                enhanced_message = f"[Conversación en español] {message}"
            else:
                enhanced_message = message
            
            # Process through EA
            ea_response = await self.ea.handle_customer_interaction(
                enhanced_message,
                channel,
                conversation_id
            )
            
            return ea_response
            
        except Exception as e:
            logger.error(f"EA processing failed: {e}")
            return self._generate_fallback_response(message, conv_context.get("language_preference"))
    
    def _generate_fallback_response(self, message: str, language: VoiceLanguage = None) -> str:
        """Generate fallback response when EA is not available"""
        if language == VoiceLanguage.SPANISH:
            return f"""¡Hola! Soy Sarah, tu Asistente Ejecutiva. 
            
            Entendí que dijiste: "{message[:100]}..."
            
            Me encantaría ayudarte con tu negocio. Aunque estoy teniendo algunos problemas técnicos menores, 
            puedo ayudarte con:
            - Automatización de procesos de negocio
            - Creación de flujos de trabajo
            - Gestión de tareas diarias
            - Análisis de oportunidades de negocio
            
            ¿En qué puedo asistirte específicamente hoy?"""
        else:
            return f"""Hi! I'm Sarah, your Executive Assistant.
            
            I heard you say: "{message[:100]}..."
            
            I'd love to help you with your business. While I'm experiencing some minor technical issues,
            I can help you with:
            - Business process automation
            - Workflow creation
            - Daily task management
            - Business opportunity analysis
            
            What specifically can I help you with today?"""
    
    def _enhance_response_for_voice(
        self, 
        response: str, 
        language: VoiceLanguage, 
        context: Dict[str, Any]
    ) -> str:
        """Enhance EA response for natural voice delivery"""
        enhanced = response
        
        # Add premium-casual personality elements
        if language == VoiceLanguage.SPANISH:
            # Spanish conversational enhancements
            enhanced = enhanced.replace("Hola,", "¡Hola!")
            enhanced = enhanced.replace("perfecto", "¡perfecto!")
            enhanced = enhanced.replace("excelente", "¡excelente!")
            
            # Add natural pauses and emphasis
            enhanced = enhanced.replace(". ", ". Um... ")
            enhanced = enhanced.replace("Sin embargo,", "Pero sabes qué,")
            enhanced = enhanced.replace("Adicionalmente,", "También,")
            
        else:
            # English conversational enhancements
            enhanced = enhanced.replace("Hello,", "Hey there!")
            enhanced = enhanced.replace("Excellent", "That's excellent")
            enhanced = enhanced.replace("Perfect", "Perfect!")
            
            # Add natural pauses and casual tone
            enhanced = enhanced.replace(". ", ". So, ")
            enhanced = enhanced.replace("However,", "But here's the thing,")
            enhanced = enhanced.replace("Furthermore,", "Also,")
            enhanced = enhanced.replace("Additionally,", "Plus,")
        
        # Add context-specific enhancements
        message_count = context.get("message_count", 1)
        if message_count == 1:
            # First interaction - more welcoming
            if language == VoiceLanguage.SPANISH:
                enhanced = f"¡Qué gusto hablar contigo! {enhanced}"
            else:
                enhanced = f"So great to talk with you! {enhanced}"
        elif message_count > 5:
            # Ongoing conversation - more familiar
            if language == VoiceLanguage.SPANISH:
                enhanced = f"Vale, {enhanced}"
            else:
                enhanced = f"Alright, {enhanced}"
        
        return enhanced
    
    def _generate_error_response(self, language: VoiceLanguage) -> str:
        """Generate error response in appropriate language"""
        if language == VoiceLanguage.SPANISH:
            return """Disculpa, estoy teniendo algunos problemas técnicos en este momento. 
            Dame un segundito y volvemos a intentarlo. 
            Soy Sarah, tu Asistente Ejecutiva, y estoy aquí para ayudarte."""
        else:
            return """I'm sorry, I'm experiencing some technical difficulties right now. 
            Give me just a moment and let's try again. 
            I'm Sarah, your Executive Assistant, and I'm here to help you."""
    
    async def start_voice_conversation(
        self, 
        conversation_id: str = None,
        language_preference: VoiceLanguage = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Start a new voice conversation with welcome message"""
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        # Determine welcome language
        welcome_language = language_preference or VoiceLanguage.ENGLISH
        
        # Generate welcome message
        if welcome_language == VoiceLanguage.SPANISH:
            welcome_text = """¡Hola! Soy Sarah, tu nueva Asistente Ejecutiva.
            
            Estoy aquí para aprender sobre tu negocio y ayudarte a automatizar tus procesos diarios.
            Me especializo en crear flujos de trabajo mientras conversamos y recordar todo sobre tu negocio para siempre.
            
            Cuéntame, ¿en qué negocio estás y qué haces día a día?"""
        else:
            welcome_text = """Hi there! I'm Sarah, your new Executive Assistant.
            
            I'm here to learn about your business and help you automate your daily processes.
            I specialize in creating workflows while we chat and remembering everything about your business forever.
            
            Tell me, what business are you in and what does your typical day look like?"""
        
        # Generate welcome voice
        welcome_audio = await self.voice_channel.generate_voice_response(
            welcome_text,
            welcome_language,
            context={
                "conversation_id": conversation_id,
                "conversation_type": "welcome",
                **(context or {})
            }
        )
        
        # Store conversation context
        self.conversation_contexts[conversation_id] = {
            "language_preference": welcome_language,
            "start_time": datetime.now(),
            "message_count": 0,
            "context": context or {},
            "conversation_type": "welcome"
        }
        
        logger.info(f"Started voice conversation {conversation_id} (language: {welcome_language.value})")
        
        return {
            "conversation_id": conversation_id,
            "welcome_text": welcome_text,
            "welcome_audio": welcome_audio,
            "language": welcome_language.value,
            "success": True
        }
    
    async def get_conversation_context(self, conversation_id: str) -> Dict[str, Any]:
        """Get conversation context and statistics"""
        if conversation_id not in self.conversation_contexts:
            return {"error": "Conversation not found"}
        
        context = self.conversation_contexts[conversation_id]
        current_time = datetime.now()
        duration = (current_time - context["start_time"]).total_seconds()
        
        return {
            "conversation_id": conversation_id,
            "language_preference": context["language_preference"].value,
            "message_count": context["message_count"],
            "duration_seconds": duration,
            "last_activity": context.get("last_activity", context["start_time"]).isoformat(),
            "conversation_type": context.get("conversation_type", "general"),
            "context": context.get("context", {})
        }
    
    async def get_voice_integration_stats(self) -> Dict[str, Any]:
        """Get voice integration performance statistics"""
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        
        health = await self.voice_channel.health_check()
        
        return {
            "voice_interactions": self.voice_interactions,
            "active_conversations": len(self.conversation_contexts),
            "average_response_time_seconds": avg_response_time,
            "ea_available": self.has_ea,
            "voice_channel_health": health,
            "performance_metrics": {
                "total_response_times": len(self.response_times),
                "fastest_response": min(self.response_times) if self.response_times else 0,
                "slowest_response": max(self.response_times) if self.response_times else 0,
                "target_response_time": 2.0,
                "meeting_target": sum(1 for t in self.response_times if t <= 2.0) / len(self.response_times) if self.response_times else 0
            }
        }

# Integration helper functions

async def create_voice_enabled_ea(customer_id: str, config: Dict[str, Any] = None) -> VoiceEnabledExecutiveAssistant:
    """Create and initialize voice-enabled EA"""
    voice_ea = VoiceEnabledExecutiveAssistant(customer_id, config)
    
    if await voice_ea.initialize():
        logger.info(f"Voice-enabled EA created successfully for customer {customer_id}")
        return voice_ea
    else:
        logger.error(f"Failed to initialize voice-enabled EA for customer {customer_id}")
        raise Exception("Voice-enabled EA initialization failed")

def create_voice_message_handler(voice_ea: VoiceEnabledExecutiveAssistant) -> Callable:
    """Create message handler for WebRTC voice sessions"""
    
    async def handle_message(message_text: str, conversation_id: str) -> str:
        """Handle voice message through voice-enabled EA"""
        try:
            result = await voice_ea.handle_voice_message(
                message_text,
                conversation_id=conversation_id,
                detected_language=VoiceLanguage.AUTO_DETECT
            )
            
            return result.get("text_response", "I'm having trouble processing that request.")
            
        except Exception as e:
            logger.error(f"Voice message handler error: {e}")
            return "I apologize, but I encountered an issue processing your message. Please try again."
    
    return handle_message

# FastAPI integration helpers

async def setup_voice_websocket_handler(customer_id: str, voice_config: Dict[str, Any] = None):
    """Setup WebSocket handler for voice communication"""
    try:
        # Create voice-enabled EA
        voice_ea = await create_voice_enabled_ea(customer_id, voice_config)
        
        # Create message handler
        message_handler = create_voice_message_handler(voice_ea)
        
        return lambda websocket: handle_voice_websocket(websocket, customer_id, message_handler)
        
    except Exception as e:
        logger.error(f"Failed to setup voice WebSocket handler: {e}")
        raise

# Testing utilities

async def test_voice_integration():
    """Test voice-enabled EA integration"""
    print("🎤 Testing Voice-Enabled Executive Assistant")
    
    customer_id = "test-voice-ea-customer"
    config = {
        "elevenlabs_api_key": None,  # Will use env var
        "whisper_model": "base"
    }
    
    try:
        # Create voice-enabled EA
        voice_ea = await create_voice_enabled_ea(customer_id, config)
        
        # Test conversation start
        welcome = await voice_ea.start_voice_conversation(language_preference=VoiceLanguage.ENGLISH)
        print(f"✅ Welcome conversation started: {welcome['conversation_id']}")
        
        # Test bilingual messages
        test_messages = [
            ("Hello! I run a marketing agency and I need help with social media automation.", VoiceLanguage.ENGLISH),
            ("Hola! Tengo una agencia de marketing y necesito ayuda con automatización de redes sociales.", VoiceLanguage.SPANISH),
            ("Can you help me create a workflow for client onboarding?", VoiceLanguage.ENGLISH),
        ]
        
        for message, language in test_messages:
            print(f"\n🗣️ Testing message ({language.value}): {message[:50]}...")
            
            result = await voice_ea.handle_voice_message(
                message,
                conversation_id=welcome['conversation_id'],
                detected_language=language
            )
            
            if result['success']:
                print(f"✅ Response generated in {result['response_time_seconds']:.2f}s")
                print(f"   Text: {result['text_response'][:100]}...")
                print(f"   Audio: {'✅' if result['voice_audio'] else '❌'}")
            else:
                print(f"❌ Failed: {result.get('error', 'Unknown error')}")
        
        # Get stats
        stats = await voice_ea.get_voice_integration_stats()
        print(f"\n📊 Performance Stats:")
        print(f"   Interactions: {stats['voice_interactions']}")
        print(f"   Avg Response Time: {stats['average_response_time_seconds']:.2f}s")
        print(f"   EA Available: {stats['ea_available']}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_voice_integration())