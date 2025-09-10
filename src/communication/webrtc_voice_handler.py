"""
WebRTC Voice Handler for Real-time Voice Communication
Browser-based voice input/output with ElevenLabs integration
"""

import asyncio
import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
import base64

# FastAPI and WebSocket imports
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

# Internal imports
from .voice_channel import ElevenLabsVoiceChannel, VoiceMessage, VoiceLanguage

logger = logging.getLogger(__name__)

class WebRTCVoiceSession:
    """Manages a single WebRTC voice session for a customer"""
    
    def __init__(
        self, 
        customer_id: str, 
        session_id: str, 
        websocket: WebSocket,
        voice_channel: ElevenLabsVoiceChannel,
        message_handler: Callable[[str, str], str] = None
    ):
        self.customer_id = customer_id
        self.session_id = session_id
        self.websocket = websocket
        self.voice_channel = voice_channel
        self.message_handler = message_handler  # EA message handler
        
        # Session state
        self.is_active = False
        self.conversation_id = str(uuid.uuid4())
        self.current_language = VoiceLanguage.AUTO_DETECT
        self.session_metadata = {}
        
        # Performance tracking
        self.start_time = datetime.now()
        self.messages_processed = 0
        self.audio_chunks_received = 0
        
        logger.info(f"WebRTC voice session created: {session_id} for customer {customer_id}")
    
    async def start_session(self):
        """Start the WebRTC voice session"""
        try:
            self.is_active = True
            
            # Send session initialization
            await self.send_message({
                "type": "session_started",
                "session_id": self.session_id,
                "conversation_id": self.conversation_id,
                "supported_languages": ["en", "es"],
                "capabilities": {
                    "speech_to_text": True,
                    "text_to_speech": True,
                    "language_detection": True,
                    "real_time_processing": True
                }
            })
            
            # Start processing loop
            await self._message_processing_loop()
            
        except Exception as e:
            logger.error(f"Error starting WebRTC session {self.session_id}: {e}")
            await self.end_session()
    
    async def _message_processing_loop(self):
        """Main message processing loop for WebRTC session"""
        try:
            while self.is_active and self.websocket.client_state == WebSocketState.CONNECTED:
                try:
                    # Receive message from client
                    message = await self.websocket.receive_text()
                    data = json.loads(message)
                    
                    # Process different message types
                    await self._handle_client_message(data)
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for session {self.session_id}")
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received in session {self.session_id}: {e}")
                    await self.send_error("Invalid message format")
                except Exception as e:
                    logger.error(f"Error processing message in session {self.session_id}: {e}")
                    await self.send_error(f"Processing error: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Fatal error in message processing loop: {e}")
        finally:
            await self.end_session()
    
    async def _handle_client_message(self, data: Dict[str, Any]):
        """Handle different types of client messages"""
        message_type = data.get("type")
        
        if message_type == "audio_chunk":
            await self._handle_audio_chunk(data)
        elif message_type == "text_message":
            await self._handle_text_message(data)
        elif message_type == "language_preference":
            await self._handle_language_preference(data)
        elif message_type == "session_config":
            await self._handle_session_config(data)
        elif message_type == "ping":
            await self.send_message({"type": "pong", "timestamp": datetime.now().isoformat()})
        else:
            logger.warning(f"Unknown message type: {message_type}")
            await self.send_error(f"Unknown message type: {message_type}")
    
    async def _handle_audio_chunk(self, data: Dict[str, Any]):
        """Handle incoming audio chunk from browser"""
        try:
            # Extract audio data
            audio_b64 = data.get("audio_data", "")
            audio_format = data.get("format", "wav")
            is_final = data.get("is_final", False)
            
            if not audio_b64:
                await self.send_error("No audio data provided")
                return
            
            # Decode base64 audio
            try:
                audio_data = base64.b64decode(audio_b64)
            except Exception as e:
                logger.error(f"Failed to decode audio data: {e}")
                await self.send_error("Invalid audio data encoding")
                return
            
            self.audio_chunks_received += 1
            
            # Process audio if final chunk
            if is_final:
                await self._process_complete_audio(audio_data, audio_format)
            
            # Send acknowledgment
            await self.send_message({
                "type": "audio_received",
                "chunk_id": data.get("chunk_id", "unknown"),
                "processed": is_final
            })
            
        except Exception as e:
            logger.error(f"Error handling audio chunk: {e}")
            await self.send_error("Audio processing failed")
    
    async def _process_complete_audio(self, audio_data: bytes, audio_format: str):
        """Process complete audio segment"""
        try:
            start_time = datetime.now()
            
            # Create metadata
            metadata = {
                "conversation_id": self.conversation_id,
                "session_id": self.session_id,
                "from_number": "webrtc-client",
                "to_number": f"customer-{self.customer_id}",
                "audio_format": audio_format
            }
            
            # Process voice input
            voice_message = await self.voice_channel.process_voice_input(audio_data, metadata)
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            if voice_message.transcript_text:
                # Send transcript to client
                await self.send_message({
                    "type": "speech_to_text_result",
                    "transcript": voice_message.transcript_text,
                    "detected_language": voice_message.detected_language.value if voice_message.detected_language else "en",
                    "confidence": voice_message.confidence_score or 0.0,
                    "processing_time_seconds": processing_time
                })
                
                # Process with EA if handler is available
                if self.message_handler and voice_message.transcript_text.strip():
                    await self._process_ea_response(voice_message.transcript_text, voice_message.detected_language)
            
        except Exception as e:
            logger.error(f"Error processing complete audio: {e}")
            await self.send_error("Audio processing failed")
    
    async def _process_ea_response(self, message_text: str, detected_language: VoiceLanguage):
        """Process message through EA and generate voice response"""
        try:
            start_time = datetime.now()
            
            # Get EA response (this would integrate with the EA system)
            if self.message_handler:
                ea_response = await self._call_ea_handler(message_text)
            else:
                # Fallback response
                ea_response = self._get_fallback_response(message_text, detected_language)
            
            # Generate voice response
            voice_audio = await self.voice_channel.generate_voice_response(
                ea_response, 
                detected_language,
                context={
                    "conversation_id": self.conversation_id,
                    "session_type": "webrtc"
                }
            )
            
            # Calculate total response time
            response_time = (datetime.now() - start_time).total_seconds()
            
            # Send response to client
            await self.send_message({
                "type": "ea_response",
                "text": ea_response,
                "language": detected_language.value if detected_language else "en",
                "response_time_seconds": response_time,
                "has_audio": bool(voice_audio)
            })
            
            # Send voice response if generated
            if voice_audio:
                audio_b64 = base64.b64encode(voice_audio).decode('utf-8')
                await self.send_message({
                    "type": "voice_response",
                    "audio_data": audio_b64,
                    "format": "mp3",
                    "language": detected_language.value if detected_language else "en"
                })
            
            self.messages_processed += 1
            logger.info(f"EA response processed in {response_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Error processing EA response: {e}")
            await self.send_error("EA response processing failed")
    
    async def _call_ea_handler(self, message_text: str) -> str:
        """Call the EA message handler (async wrapper if needed)"""
        try:
            if asyncio.iscoroutinefunction(self.message_handler):
                return await self.message_handler(message_text, self.conversation_id)
            else:
                return self.message_handler(message_text, self.conversation_id)
        except Exception as e:
            logger.error(f"EA handler call failed: {e}")
            return "I apologize, but I'm having trouble processing your request right now. Let me try again."
    
    def _get_fallback_response(self, message_text: str, language: VoiceLanguage) -> str:
        """Generate fallback response when EA handler is not available"""
        if language == VoiceLanguage.SPANISH:
            return f"Hola, recibí tu mensaje: '{message_text[:50]}...'. Soy Sarah, tu Asistente Ejecutiva. ¿Cómo puedo ayudarte?"
        else:
            return f"Hello, I received your message: '{message_text[:50]}...'. I'm Sarah, your Executive Assistant. How can I help you?"
    
    async def _handle_text_message(self, data: Dict[str, Any]):
        """Handle text message from client"""
        try:
            text = data.get("text", "")
            language = data.get("language", "auto")
            
            if not text.strip():
                await self.send_error("Empty text message")
                return
            
            # Convert language string to enum
            if language == "es":
                lang_enum = VoiceLanguage.SPANISH
            elif language == "en":
                lang_enum = VoiceLanguage.ENGLISH
            else:
                lang_enum = VoiceLanguage.AUTO_DETECT
            
            # Process through EA
            await self._process_ea_response(text, lang_enum)
            
        except Exception as e:
            logger.error(f"Error handling text message: {e}")
            await self.send_error("Text message processing failed")
    
    async def _handle_language_preference(self, data: Dict[str, Any]):
        """Handle language preference update"""
        try:
            language = data.get("language", "auto")
            
            if language == "es":
                self.current_language = VoiceLanguage.SPANISH
            elif language == "en":
                self.current_language = VoiceLanguage.ENGLISH
            else:
                self.current_language = VoiceLanguage.AUTO_DETECT
            
            await self.send_message({
                "type": "language_updated",
                "language": self.current_language.value
            })
            
        except Exception as e:
            logger.error(f"Error handling language preference: {e}")
            await self.send_error("Language preference update failed")
    
    async def _handle_session_config(self, data: Dict[str, Any]):
        """Handle session configuration update"""
        try:
            config = data.get("config", {})
            
            # Update session metadata
            self.session_metadata.update(config)
            
            await self.send_message({
                "type": "config_updated",
                "config": self.session_metadata
            })
            
        except Exception as e:
            logger.error(f"Error handling session config: {e}")
            await self.send_error("Session config update failed")
    
    async def send_message(self, message: Dict[str, Any]):
        """Send message to client"""
        try:
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")
    
    async def send_error(self, error_message: str):
        """Send error message to client"""
        await self.send_message({
            "type": "error",
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        })
    
    async def end_session(self):
        """End the WebRTC voice session"""
        try:
            self.is_active = False
            
            # Calculate session statistics
            duration = (datetime.now() - self.start_time).total_seconds()
            
            # Send session ended message
            await self.send_message({
                "type": "session_ended",
                "session_id": self.session_id,
                "duration_seconds": duration,
                "messages_processed": self.messages_processed,
                "audio_chunks_received": self.audio_chunks_received
            })
            
            # Close WebSocket if still connected
            if self.websocket.client_state == WebSocketState.CONNECTED:
                await self.websocket.close()
            
            logger.info(f"WebRTC session {self.session_id} ended after {duration:.1f}s")
            
        except Exception as e:
            logger.error(f"Error ending session {self.session_id}: {e}")

class WebRTCVoiceManager:
    """Manages multiple WebRTC voice sessions"""
    
    def __init__(self):
        self.active_sessions: Dict[str, WebRTCVoiceSession] = {}
        self.voice_channels: Dict[str, ElevenLabsVoiceChannel] = {}
    
    async def create_session(
        self, 
        customer_id: str, 
        websocket: WebSocket,
        message_handler: Callable[[str, str], str] = None,
        voice_config: Dict[str, Any] = None
    ) -> WebRTCVoiceSession:
        """Create new WebRTC voice session"""
        try:
            session_id = str(uuid.uuid4())
            
            # Initialize voice channel for customer if not exists
            if customer_id not in self.voice_channels:
                voice_channel = ElevenLabsVoiceChannel(customer_id, voice_config or {})
                await voice_channel.initialize()
                self.voice_channels[customer_id] = voice_channel
            else:
                voice_channel = self.voice_channels[customer_id]
            
            # Create session
            session = WebRTCVoiceSession(
                customer_id=customer_id,
                session_id=session_id,
                websocket=websocket,
                voice_channel=voice_channel,
                message_handler=message_handler
            )
            
            # Store active session
            self.active_sessions[session_id] = session
            
            logger.info(f"Created WebRTC session {session_id} for customer {customer_id}")
            return session
            
        except Exception as e:
            logger.error(f"Error creating WebRTC session: {e}")
            raise
    
    async def remove_session(self, session_id: str):
        """Remove WebRTC voice session"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            await session.end_session()
            del self.active_sessions[session_id]
            logger.info(f"Removed WebRTC session {session_id}")
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics about active sessions"""
        return {
            "active_sessions": len(self.active_sessions),
            "sessions_by_customer": len(set(s.customer_id for s in self.active_sessions.values())),
            "voice_channels": len(self.voice_channels),
            "session_details": [
                {
                    "session_id": s.session_id,
                    "customer_id": s.customer_id,
                    "duration_seconds": (datetime.now() - s.start_time).total_seconds(),
                    "messages_processed": s.messages_processed,
                    "audio_chunks_received": s.audio_chunks_received
                }
                for s in self.active_sessions.values()
            ]
        }
    
    async def cleanup_inactive_sessions(self):
        """Clean up inactive sessions"""
        to_remove = []
        for session_id, session in self.active_sessions.items():
            if not session.is_active or session.websocket.client_state == WebSocketState.DISCONNECTED:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            await self.remove_session(session_id)
        
        logger.info(f"Cleaned up {len(to_remove)} inactive sessions")

# Global voice manager instance
voice_manager = WebRTCVoiceManager()

# FastAPI WebSocket endpoint integration
async def handle_voice_websocket(websocket: WebSocket, customer_id: str, message_handler: Callable = None):
    """Handle WebRTC voice WebSocket connection"""
    await websocket.accept()
    
    session = None
    try:
        # Create voice session
        session = await voice_manager.create_session(
            customer_id=customer_id,
            websocket=websocket,
            message_handler=message_handler
        )
        
        # Start session
        await session.start_session()
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for customer {customer_id}")
    except Exception as e:
        logger.error(f"Error in voice WebSocket handler: {e}")
    finally:
        if session:
            await voice_manager.remove_session(session.session_id)