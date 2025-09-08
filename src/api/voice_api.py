"""
Voice API Endpoints
FastAPI endpoints for ElevenLabs voice integration with bilingual support
"""

import asyncio
import logging
import os
import base64
from datetime import datetime
from typing import Dict, Any, Optional, List
import tempfile
import json

from fastapi import FastAPI, WebSocket, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Voice integration imports
from ..agents.voice_integration import (
    VoiceEnabledExecutiveAssistant,
    create_voice_enabled_ea,
    create_voice_message_handler
)
from ..communication.voice_channel import VoiceLanguage
from ..communication.webrtc_voice_handler import voice_manager, handle_voice_websocket

logger = logging.getLogger(__name__)

# Pydantic models for API

class VoiceMessageRequest(BaseModel):
    text: str = Field(..., description="Text message to convert to speech")
    language: str = Field("auto", description="Language: 'en', 'es', or 'auto'")
    voice_style: str = Field("casual", description="Voice style: 'casual' or 'professional'")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")

class VoiceResponseModel(BaseModel):
    success: bool
    text_response: str
    audio_base64: Optional[str] = None
    detected_language: str
    response_time_seconds: float
    conversation_id: str
    error: Optional[str] = None

class ConversationStartRequest(BaseModel):
    language_preference: str = Field("en", description="Preferred language: 'en' or 'es'")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional conversation context")

class VoiceStatsResponse(BaseModel):
    voice_interactions: int
    active_conversations: int
    average_response_time_seconds: float
    ea_available: bool
    performance_metrics: Dict[str, Any]

class HealthCheckResponse(BaseModel):
    status: str
    voice_channel_ready: bool
    elevenlabs_available: bool
    whisper_available: bool
    supported_languages: List[str]
    timestamp: str

# Voice-enabled EA instances per customer
voice_ea_instances: Dict[str, VoiceEnabledExecutiveAssistant] = {}

async def get_voice_ea(customer_id: str) -> VoiceEnabledExecutiveAssistant:
    """Get or create voice-enabled EA instance for customer"""
    if customer_id not in voice_ea_instances:
        config = {
            "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
            "whisper_model": "base"
        }
        
        voice_ea = await create_voice_enabled_ea(customer_id, config)
        voice_ea_instances[customer_id] = voice_ea
        logger.info(f"Created new voice EA instance for customer {customer_id}")
    
    return voice_ea_instances[customer_id]

def create_voice_api() -> FastAPI:
    """Create FastAPI application with voice endpoints"""
    
    app = FastAPI(
        title="AI Agency Platform - Voice API",
        description="ElevenLabs voice integration with bilingual Spanish/English support",
        version="2.0.0"
    )
    
    # CORS middleware for browser access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/health", response_model=HealthCheckResponse)
    async def health_check():
        """Health check endpoint for voice services"""
        try:
            # Test voice EA creation
            test_customer = "health-check-test"
            test_ea = await get_voice_ea(test_customer)
            
            health = await test_ea.voice_channel.health_check()
            
            return HealthCheckResponse(
                status="healthy",
                voice_channel_ready=health.get("initialized", False),
                elevenlabs_available=health.get("elevenlabs_available", False),
                whisper_available=health.get("speech_recognition_ready", False),
                supported_languages=health.get("supported_languages", ["en", "es"]),
                timestamp=datetime.now().isoformat()
            )
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
    
    @app.post("/voice/start-conversation/{customer_id}")
    async def start_voice_conversation(customer_id: str, request: ConversationStartRequest):
        """Start a new voice conversation"""
        try:
            voice_ea = await get_voice_ea(customer_id)
            
            # Map language string to enum
            lang_preference = None
            if request.language_preference == "es":
                lang_preference = VoiceLanguage.SPANISH
            elif request.language_preference == "en":
                lang_preference = VoiceLanguage.ENGLISH
            
            result = await voice_ea.start_voice_conversation(
                language_preference=lang_preference,
                context=request.context
            )
            
            # Encode audio to base64 if available
            welcome_audio_b64 = None
            if result.get("welcome_audio"):
                welcome_audio_b64 = base64.b64encode(result["welcome_audio"]).decode('utf-8')
            
            return {
                "success": True,
                "conversation_id": result["conversation_id"],
                "welcome_text": result["welcome_text"],
                "welcome_audio_base64": welcome_audio_b64,
                "language": result["language"]
            }
            
        except Exception as e:
            logger.error(f"Error starting voice conversation: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/voice/message/{customer_id}", response_model=VoiceResponseModel)
    async def send_voice_message(customer_id: str, request: VoiceMessageRequest):
        """Send text message and get voice response"""
        try:
            voice_ea = await get_voice_ea(customer_id)
            
            # Map language string to enum
            detected_language = None
            if request.language == "es":
                detected_language = VoiceLanguage.SPANISH
            elif request.language == "en":
                detected_language = VoiceLanguage.ENGLISH
            else:
                detected_language = VoiceLanguage.AUTO_DETECT
            
            result = await voice_ea.handle_voice_message(
                message=request.text,
                conversation_id=request.conversation_id,
                detected_language=detected_language,
                context={"voice_style": request.voice_style}
            )
            
            # Encode audio to base64 if available
            audio_b64 = None
            if result.get("voice_audio"):
                audio_b64 = base64.b64encode(result["voice_audio"]).decode('utf-8')
            
            return VoiceResponseModel(
                success=result["success"],
                text_response=result["text_response"],
                audio_base64=audio_b64,
                detected_language=result["detected_language"],
                response_time_seconds=result["response_time_seconds"],
                conversation_id=result["conversation_id"],
                error=result.get("error")
            )
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/voice/audio-upload/{customer_id}")
    async def upload_audio_message(
        customer_id: str,
        audio_file: UploadFile = File(...),
        conversation_id: Optional[str] = Form(None),
        context: Optional[str] = Form("{}")
    ):
        """Upload audio file and get voice response"""
        try:
            voice_ea = await get_voice_ea(customer_id)
            
            # Read audio data
            audio_data = await audio_file.read()
            
            # Parse context
            try:
                context_dict = json.loads(context) if context else {}
            except json.JSONDecodeError:
                context_dict = {}
            
            # Process audio through voice channel
            metadata = {
                "conversation_id": conversation_id,
                "from_number": "audio-upload",
                "to_number": f"customer-{customer_id}",
                "audio_format": audio_file.content_type or "audio/wav"
            }
            
            voice_message = await voice_ea.voice_channel.process_voice_input(audio_data, metadata)
            
            if voice_message.transcript_text:
                # Process transcript through EA
                result = await voice_ea.handle_voice_message(
                    message=voice_message.transcript_text,
                    conversation_id=conversation_id or voice_message.conversation_id,
                    detected_language=voice_message.detected_language,
                    context=context_dict
                )
                
                # Encode audio to base64 if available
                audio_b64 = None
                if result.get("voice_audio"):
                    audio_b64 = base64.b64encode(result["voice_audio"]).decode('utf-8')
                
                return {
                    "success": True,
                    "transcript": voice_message.transcript_text,
                    "detected_language": voice_message.detected_language.value,
                    "confidence": voice_message.confidence_score,
                    "text_response": result["text_response"],
                    "audio_base64": audio_b64,
                    "response_time_seconds": result["response_time_seconds"],
                    "conversation_id": result["conversation_id"]
                }
            else:
                return {
                    "success": False,
                    "error": "Could not transcribe audio",
                    "transcript": "",
                    "detected_language": "unknown",
                    "confidence": 0.0
                }
                
        except Exception as e:
            logger.error(f"Error processing audio upload: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/voice/stats/{customer_id}", response_model=VoiceStatsResponse)
    async def get_voice_stats(customer_id: str):
        """Get voice integration statistics for customer"""
        try:
            if customer_id not in voice_ea_instances:
                raise HTTPException(status_code=404, detail="Customer not found")
            
            voice_ea = voice_ea_instances[customer_id]
            stats = await voice_ea.get_voice_integration_stats()
            
            return VoiceStatsResponse(
                voice_interactions=stats["voice_interactions"],
                active_conversations=stats["active_conversations"],
                average_response_time_seconds=stats["average_response_time_seconds"],
                ea_available=stats["ea_available"],
                performance_metrics=stats["performance_metrics"]
            )
            
        except Exception as e:
            logger.error(f"Error getting voice stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/voice/conversation/{customer_id}/{conversation_id}")
    async def get_conversation_context(customer_id: str, conversation_id: str):
        """Get conversation context and history"""
        try:
            if customer_id not in voice_ea_instances:
                raise HTTPException(status_code=404, detail="Customer not found")
            
            voice_ea = voice_ea_instances[customer_id]
            context = await voice_ea.get_conversation_context(conversation_id)
            
            if "error" in context:
                raise HTTPException(status_code=404, detail=context["error"])
            
            return context
            
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/voice/download-audio/{customer_id}")
    async def download_audio_response(
        customer_id: str,
        text: str,
        language: str = "auto",
        voice_style: str = "casual"
    ):
        """Download audio response as MP3 file"""
        try:
            voice_ea = await get_voice_ea(customer_id)
            
            # Map language string to enum
            lang_enum = None
            if language == "es":
                lang_enum = VoiceLanguage.SPANISH
            elif language == "en":
                lang_enum = VoiceLanguage.ENGLISH
            else:
                lang_enum = VoiceLanguage.AUTO_DETECT
            
            # Generate voice audio
            audio_data = await voice_ea.voice_channel.generate_voice_response(
                text=text,
                language=lang_enum,
                context={"voice_style": voice_style}
            )
            
            if not audio_data:
                raise HTTPException(status_code=500, detail="Failed to generate audio")
            
            # Create streaming response
            def audio_stream():
                yield audio_data
            
            return StreamingResponse(
                audio_stream(),
                media_type="audio/mpeg",
                headers={"Content-Disposition": f"attachment; filename=voice_response_{customer_id}.mp3"}
            )
            
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.websocket("/voice/ws/{customer_id}")
    async def voice_websocket(websocket: WebSocket, customer_id: str):
        """WebSocket endpoint for real-time voice communication"""
        try:
            # Get voice-enabled EA
            voice_ea = await get_voice_ea(customer_id)
            
            # Create message handler
            message_handler = create_voice_message_handler(voice_ea)
            
            # Handle WebSocket connection
            await handle_voice_websocket(websocket, customer_id, message_handler)
            
        except Exception as e:
            logger.error(f"WebSocket error for customer {customer_id}: {e}")
    
    @app.get("/voice/sessions/stats")
    async def get_session_stats():
        """Get overall voice session statistics"""
        try:
            stats = voice_manager.get_session_stats()
            return stats
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.post("/voice/sessions/cleanup")
    async def cleanup_sessions():
        """Clean up inactive voice sessions"""
        try:
            await voice_manager.cleanup_inactive_sessions()
            return {"success": True, "message": "Session cleanup completed"}
            
        except Exception as e:
            logger.error(f"Error cleaning up sessions: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    return app

# Development server
def run_voice_api(host: str = "0.0.0.0", port: int = 8001, debug: bool = True):
    """Run voice API server"""
    app = create_voice_api()
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info" if debug else "warning",
        reload=debug
    )
    
    server = uvicorn.Server(config)
    
    logger.info(f"Starting Voice API server on {host}:{port}")
    asyncio.run(server.serve())

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    # Run server
    run_voice_api(debug=True)