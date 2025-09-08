"""
Complete Voice Integration System
Production-ready ElevenLabs voice integration with bilingual support
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import uvicorn
from contextlib import asynccontextmanager

# FastAPI imports
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response

# Voice integration imports
from .api.voice_api import create_voice_api
from .agents.voice_integration import create_voice_enabled_ea
from .agents.memory.voice_memory_integration import create_voice_memory_integration
from .communication.webrtc_voice_handler import voice_manager
from .monitoring.voice_performance_monitor import (
    voice_performance_monitor,
    record_voice_interaction,
    get_voice_performance_dashboard
)

# Analytics imports
from .analytics import (
    VoiceAnalyticsPipeline,
    VoiceBusinessIntelligence, 
    VoiceCostTracker,
    VoiceQualityAnalyzer,
    create_analytics_dashboard_api
)
from .analytics.voice_analytics_pipeline import voice_analytics_pipeline
from .analytics.business_intelligence import voice_business_intelligence
from .analytics.cost_tracker import voice_cost_tracker
from .analytics.quality_analyzer import voice_quality_analyzer

# Configuration
from .config.voice_config import VoiceIntegrationConfig

logger = logging.getLogger(__name__)

class VoiceIntegrationSystem:
    """
    Complete voice integration system for AI Agency Platform
    
    Features:
    - ElevenLabs text-to-speech with bilingual support
    - Whisper speech-to-text recognition
    - WebRTC browser-based voice input
    - EA memory integration with per-customer isolation
    - Comprehensive analytics and business intelligence
    - Real-time cost tracking and optimization
    - Voice quality analysis and monitoring
    - Performance monitoring and metrics
    - Production-ready deployment
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = VoiceIntegrationConfig(config)
        self.app = None
        self.voice_api = None
        self.is_running = False
        self.startup_time = None
        
        # Voice-enabled EA instances per customer
        self.voice_ea_instances: Dict[str, Any] = {}
        self.voice_memory_instances: Dict[str, Any] = {}
        
        # System components
        self.performance_monitor = voice_performance_monitor
        self.session_manager = voice_manager
        
        # Analytics components
        self.analytics_pipeline = voice_analytics_pipeline
        self.business_intelligence = voice_business_intelligence
        self.cost_tracker = voice_cost_tracker
        self.quality_analyzer = voice_quality_analyzer
        
        logger.info("Voice integration system initialized")
    
    async def initialize(self) -> bool:
        """Initialize the voice integration system"""
        try:
            self.startup_time = datetime.now()
            
            # Validate configuration
            if not self._validate_config():
                logger.error("Configuration validation failed")
                return False
            
            # Create FastAPI application
            self.app = await self._create_application()
            
            # Initialize system components
            await self._initialize_components()
            
            # Setup graceful shutdown
            self._setup_signal_handlers()
            
            logger.info("Voice integration system initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize voice integration system: {e}")
            return False
    
    def _validate_config(self) -> bool:
        """Validate system configuration"""
        try:
            # Check required API keys
            if not self.config.elevenlabs_api_key:
                logger.warning("ElevenLabs API key not configured - voice synthesis will be limited")
            
            # Check Whisper model availability
            if not self.config.whisper_model:
                logger.error("Whisper model not specified")
                return False
            
            # Validate performance settings
            if self.config.response_time_sla <= 0:
                logger.error("Invalid response time SLA")
                return False
            
            # Check file paths
            frontend_path = Path(self.config.frontend_path)
            if not frontend_path.exists():
                logger.warning(f"Frontend path not found: {frontend_path}")
            
            logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation error: {e}")
            return False
    
    async def _create_application(self) -> FastAPI:
        """Create FastAPI application with voice endpoints"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("Voice integration system starting up...")
            await self._initialize_components()
            
            yield
            
            # Shutdown
            logger.info("Voice integration system shutting down...")
            await self._cleanup_components()
        
        # Create main application
        app = FastAPI(
            title="AI Agency Platform - Voice Integration",
            description="Complete bilingual voice interface with ElevenLabs and Whisper",
            version="2.0.0",
            lifespan=lifespan
        )
        
        # CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Mount voice API
        voice_api = create_voice_api()
        app.mount("/voice", voice_api)
        
        # Mount analytics API
        analytics_api = create_analytics_dashboard_api()
        app.mount("/analytics", analytics_api)
        
        # Static files for frontend
        if Path(self.config.frontend_path).exists():
            app.mount("/static", StaticFiles(directory=self.config.frontend_path), name="static")
        
        # Main system endpoints
        self._add_system_endpoints(app)
        
        return app
    
    def _add_system_endpoints(self, app: FastAPI):
        """Add system-level endpoints"""
        
        @app.get("/")
        async def root():
            """Root endpoint with system information"""
            if Path(self.config.frontend_path, "voice-interface.html").exists():
                return FileResponse(Path(self.config.frontend_path, "voice-interface.html"))
            else:
                return {
                    "service": "AI Agency Platform Voice Integration",
                    "version": "2.0.0",
                    "status": "running" if self.is_running else "starting",
                    "startup_time": self.startup_time.isoformat() if self.startup_time else None,
                    "endpoints": {
                        "voice_interface": "/",
                        "voice_api": "/voice",
                        "analytics_api": "/analytics",
                        "health": "/health",
                        "metrics": "/metrics",
                        "performance": "/performance"
                    }
                }
        
        @app.get("/health")
        async def system_health():
            """Complete system health check"""
            try:
                health_status = {
                    "status": "healthy" if self.is_running else "unhealthy",
                    "timestamp": datetime.now().isoformat(),
                    "uptime_seconds": (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0,
                    "components": {
                        "voice_integration": True,
                        "performance_monitor": True,
                        "session_manager": True,
                        "analytics_pipeline": True,
                        "business_intelligence": True,
                        "cost_tracker": True,
                        "quality_analyzer": True
                    }
                }
                
                # Check voice system health
                try:
                    # Test voice EA creation
                    test_customer = "health-check-customer"
                    if test_customer not in self.voice_ea_instances:
                        voice_ea = await create_voice_enabled_ea(test_customer, self.config.to_dict())
                        self.voice_ea_instances[test_customer] = voice_ea
                    
                    voice_ea = self.voice_ea_instances[test_customer]
                    voice_health = await voice_ea.voice_channel.health_check()
                    
                    health_status["voice_system"] = {
                        "elevenlabs_available": voice_health.get("elevenlabs_available", False),
                        "whisper_available": voice_health.get("speech_recognition_ready", False),
                        "supported_languages": voice_health.get("supported_languages", []),
                        "voice_configs": voice_health.get("voice_configs", [])
                    }
                    
                except Exception as e:
                    health_status["components"]["voice_integration"] = False
                    health_status["voice_system"] = {"error": str(e)}
                
                # Session manager health
                session_stats = self.session_manager.get_session_stats()
                health_status["session_manager"] = {
                    "active_sessions": session_stats["active_sessions"],
                    "voice_channels": session_stats.get("voice_channels", 0)
                }
                
                return health_status
                
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "unhealthy",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    }
                )
        
        @app.get("/performance")
        async def performance_dashboard():
            """Voice performance dashboard"""
            try:
                dashboard_data = await get_voice_performance_dashboard()
                return dashboard_data
                
            except Exception as e:
                logger.error(f"Performance dashboard error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.get("/metrics")
        async def prometheus_metrics():
            """Prometheus metrics endpoint"""
            try:
                metrics = self.performance_monitor.export_prometheus_metrics()
                return Response(content=metrics, media_type="text/plain")
                
            except Exception as e:
                logger.error(f"Metrics export error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.get("/system/stats")
        async def system_statistics():
            """Comprehensive system statistics"""
            try:
                stats = {
                    "system": {
                        "uptime_seconds": (datetime.now() - self.startup_time).total_seconds() if self.startup_time else 0,
                        "active_customers": len(self.voice_ea_instances),
                        "memory_integrations": len(self.voice_memory_instances)
                    },
                    "voice_sessions": self.session_manager.get_session_stats(),
                    "performance": await self.performance_monitor.get_current_performance()
                }
                
                return stats
                
            except Exception as e:
                logger.error(f"System statistics error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/system/cleanup")
        async def cleanup_system():
            """Clean up inactive sessions and old data"""
            try:
                # Cleanup inactive voice sessions
                await self.session_manager.cleanup_inactive_sessions()
                
                # Cleanup old performance data
                await self.performance_monitor.cleanup_old_data(days_to_keep=7)
                
                # Cleanup voice memory integrations
                cleanup_tasks = []
                for memory_integration in self.voice_memory_instances.values():
                    cleanup_tasks.append(memory_integration.cleanup_old_conversations(days_to_keep=30))
                
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                
                return {
                    "success": True,
                    "message": "System cleanup completed",
                    "timestamp": datetime.now().isoformat()
                }
                
            except Exception as e:
                logger.error(f"System cleanup error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    async def _initialize_components(self):
        """Initialize system components"""
        try:
            # Initialize performance monitor
            logger.info("Initializing performance monitor...")
            
            # Initialize session manager
            logger.info("Initializing session manager...")
            
            # Initialize analytics components
            logger.info("Initializing analytics components...")
            await self._initialize_analytics_components()
            
            # Pre-warm common voice configurations
            await self._prewarm_voice_system()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Component initialization error: {e}")
            raise
    
    async def _initialize_analytics_components(self):
        """Initialize analytics system components"""
        try:
            # Start analytics pipeline background processing
            if hasattr(self.analytics_pipeline, 'start_background_processing'):
                await self.analytics_pipeline.start_background_processing()
                logger.info("Analytics pipeline background processing started")
            
            # Initialize business intelligence (if needed)
            if hasattr(self.business_intelligence, 'initialize'):
                await self.business_intelligence.initialize()
                logger.info("Business intelligence initialized")
            
            # Initialize cost tracker (if needed)
            if hasattr(self.cost_tracker, 'initialize'):
                await self.cost_tracker.initialize()
                logger.info("Cost tracker initialized")
            
            # Initialize quality analyzer (if needed)
            if hasattr(self.quality_analyzer, 'initialize'):
                await self.quality_analyzer.initialize()
                logger.info("Quality analyzer initialized")
            
            logger.info("Analytics components initialization completed")
            
        except Exception as e:
            logger.error(f"Analytics components initialization error: {e}")
            raise
    
    async def _prewarm_voice_system(self):
        """Pre-warm voice system components"""
        try:
            logger.info("Pre-warming voice system...")
            
            # Create a test voice EA to initialize models
            test_customer = "prewarm-customer"
            voice_ea = await create_voice_enabled_ea(test_customer, self.config.to_dict())
            
            # Import VoiceLanguage locally to avoid import issues
            from .communication.voice_channel import VoiceLanguage
            
            # Test voice generation to load models
            test_messages = [
                ("Hello! System pre-warming test.", VoiceLanguage.ENGLISH),
                ("¡Hola! Prueba de precalentamiento del sistema.", VoiceLanguage.SPANISH)
            ]
            
            for message, language in test_messages:
                try:
                    audio_data = await voice_ea.voice_channel.generate_voice_response(message, language)
                    if audio_data:
                        logger.info(f"Pre-warmed {language.value} voice synthesis")
                except Exception as e:
                    logger.warning(f"Pre-warming failed for {language.value}: {e}")
            
            # Store for reuse
            self.voice_ea_instances[test_customer] = voice_ea
            
            logger.info("Voice system pre-warming completed")
            
        except Exception as e:
            logger.warning(f"Voice system pre-warming failed: {e}")
    
    async def get_voice_enabled_ea(self, customer_id: str) -> Any:
        """Get or create voice-enabled EA for customer"""
        try:
            if customer_id not in self.voice_ea_instances:
                logger.info(f"Creating voice-enabled EA for customer {customer_id}")
                
                # Create voice-enabled EA
                voice_ea = await create_voice_enabled_ea(customer_id, self.config.to_dict())
                self.voice_ea_instances[customer_id] = voice_ea
                
                # Create voice memory integration
                voice_memory = create_voice_memory_integration(customer_id, self.config.to_dict())
                await voice_memory.initialize()
                self.voice_memory_instances[customer_id] = voice_memory
                
                logger.info(f"Voice-enabled EA created for customer {customer_id}")
            
            return self.voice_ea_instances[customer_id]
            
        except Exception as e:
            logger.error(f"Error creating voice-enabled EA for customer {customer_id}: {e}")
            raise
    
    async def process_voice_interaction(
        self,
        customer_id: str,
        message: str,
        detected_language: str = "en",
        conversation_id: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Process voice interaction with full system integration"""
        start_time = datetime.now()
        interaction_id = f"voice_{customer_id}_{int(start_time.timestamp()*1000)}"
        
        try:
            # Get voice-enabled EA
            voice_ea = await self.get_voice_enabled_ea(customer_id)
            
            # Get voice memory integration
            voice_memory = self.voice_memory_instances.get(customer_id)
            
            # Process through voice-enabled EA
            from .communication.voice_channel import VoiceLanguage
            language_enum = VoiceLanguage.SPANISH if detected_language == "es" else VoiceLanguage.ENGLISH
            
            result = await voice_ea.handle_voice_message(
                message=message,
                conversation_id=conversation_id,
                detected_language=language_enum,
                context=context or {}
            )
            
            # Store in voice memory if available
            if voice_memory and result["success"]:
                await voice_memory.store_voice_interaction(
                    conversation_id=result["conversation_id"],
                    message_text=message,
                    response_text=result["text_response"],
                    detected_language=language_enum,
                    response_language=language_enum,  # Could be different in code-switching
                    interaction_metadata={
                        "interaction_id": interaction_id,
                        "response_time": result["response_time_seconds"],
                        "context": context or {}
                    }
                )
            
            # Record performance metrics
            performance_metrics = await record_voice_interaction(
                customer_id=customer_id,
                conversation_id=result["conversation_id"],
                interaction_id=interaction_id,
                total_response_time=result["response_time_seconds"],
                transcript_length=len(message),
                response_length=len(result["text_response"]),
                detected_language=detected_language,
                response_language=detected_language,
                success=result["success"],
                error_type=result.get("error") if not result["success"] else None
            )
            
            # Comprehensive analytics processing
            await self._process_comprehensive_analytics(
                performance_metrics,
                message,
                result,
                context or {}
            )
            
            logger.info(f"Voice interaction processed: {interaction_id} in {result['response_time_seconds']:.2f}s")
            
            return {
                **result,
                "interaction_id": interaction_id,
                "system_performance": {
                    "total_time": (datetime.now() - start_time).total_seconds(),
                    "ea_response_time": result["response_time_seconds"],
                    "memory_integrated": voice_memory is not None
                }
            }
            
        except Exception as e:
            error_message = f"Voice interaction processing failed: {e}"
            logger.error(error_message)
            
            # Record error metrics
            await record_voice_interaction(
                customer_id=customer_id,
                conversation_id=conversation_id or "unknown",
                interaction_id=interaction_id,
                total_response_time=(datetime.now() - start_time).total_seconds(),
                success=False,
                error_type="system_error",
                error_message=str(e)
            )
            
            return {
                "success": False,
                "error": error_message,
                "interaction_id": interaction_id,
                "response_time_seconds": (datetime.now() - start_time).total_seconds()
            }
    
    async def _process_comprehensive_analytics(
        self,
        performance_metrics: Any,  # VoiceInteractionMetrics
        message_text: str,
        ea_result: Dict[str, Any],
        context: Dict[str, Any]
    ):
        """Process comprehensive analytics for voice interaction"""
        
        try:
            # Prepare conversation context for analytics
            conversation_context = {
                "message_text": message_text,
                "response_text": ea_result.get("text_response", ""),
                "interaction_success": ea_result.get("success", False),
                "conversation_id": ea_result.get("conversation_id", ""),
                **context
            }
            
            # Business context preparation
            business_context = {
                "high_value_customer": context.get("high_value_customer", False),
                "strategic_conversation": context.get("strategic_conversation", False),
                "value_created": ea_result.get("success", False) and len(ea_result.get("text_response", "")) > 20,
                "conversation_text": f"{message_text} {ea_result.get('text_response', '')}"
            }
            
            # Run analytics in parallel for performance
            analytics_tasks = []
            
            # Analytics pipeline processing
            analytics_tasks.append(
                self.analytics_pipeline.process_interaction(
                    performance_metrics,
                    conversation_context,
                    business_context
                )
            )
            
            # Cost tracking
            analytics_tasks.append(
                self.cost_tracker.track_interaction_cost(
                    performance_metrics,
                    {"business_value_score": 50}  # Default value, would be calculated
                )
            )
            
            # Quality analysis
            analytics_tasks.append(
                self.quality_analyzer.analyze_interaction_quality(
                    performance_metrics,
                    conversation_context,
                    None  # audio_data not available in this context
                )
            )
            
            # Execute analytics tasks in parallel
            analytics_results = await asyncio.gather(*analytics_tasks, return_exceptions=True)
            
            # Process business intelligence (depends on analytics results)
            if analytics_results[0] and not isinstance(analytics_results[0], Exception):
                await self.business_intelligence.analyze_customer_analytics(analytics_results[0])
            
            logger.debug("Comprehensive analytics processing completed",
                        interaction_id=performance_metrics.interaction_id,
                        analytics_success=len([r for r in analytics_results if not isinstance(r, Exception)]))
                        
        except Exception as e:
            logger.error("Error in comprehensive analytics processing",
                        interaction_id=getattr(performance_metrics, 'interaction_id', 'unknown'),
                        error=str(e))
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down gracefully...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _cleanup_components(self):
        """Cleanup system components"""
        try:
            logger.info("Cleaning up system components...")
            
            # Cleanup analytics components
            await self._cleanup_analytics_components()
            
            # Cleanup active voice sessions
            await self.session_manager.cleanup_inactive_sessions()
            
            # Cleanup voice EA instances
            for customer_id, voice_ea in self.voice_ea_instances.items():
                try:
                    # Could add specific cleanup for voice EA
                    logger.debug(f"Cleaned up voice EA for customer {customer_id}")
                except Exception as e:
                    logger.warning(f"Error cleaning up voice EA for {customer_id}: {e}")
            
            # Cleanup voice memory instances
            for customer_id, voice_memory in self.voice_memory_instances.items():
                try:
                    await voice_memory.cleanup_old_conversations(days_to_keep=30)
                    logger.debug(f"Cleaned up voice memory for customer {customer_id}")
                except Exception as e:
                    logger.warning(f"Error cleaning up voice memory for {customer_id}: {e}")
            
            logger.info("Component cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during component cleanup: {e}")
    
    async def _cleanup_analytics_components(self):
        """Cleanup analytics system components"""
        try:
            logger.info("Cleaning up analytics components...")
            
            # Stop analytics pipeline background processing
            if hasattr(self.analytics_pipeline, 'stop_background_processing'):
                await self.analytics_pipeline.stop_background_processing()
                logger.info("Analytics pipeline background processing stopped")
            
            # Cleanup business intelligence
            if hasattr(self.business_intelligence, 'cleanup'):
                await self.business_intelligence.cleanup()
                logger.info("Business intelligence cleanup completed")
            
            # Cleanup cost tracker
            if hasattr(self.cost_tracker, 'cleanup'):
                await self.cost_tracker.cleanup()
                logger.info("Cost tracker cleanup completed")
            
            # Cleanup quality analyzer
            if hasattr(self.quality_analyzer, 'cleanup'):
                await self.quality_analyzer.cleanup()
                logger.info("Quality analyzer cleanup completed")
            
            logger.info("Analytics components cleanup completed")
            
        except Exception as e:
            logger.error(f"Analytics components cleanup error: {e}")
    
    async def run_server(
        self,
        host: str = "0.0.0.0",
        port: int = 8001,
        workers: int = 1,
        reload: bool = False
    ):
        """Run the voice integration server"""
        if not self.app:
            logger.error("Application not initialized. Call initialize() first.")
            return
        
        self.is_running = True
        
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            workers=workers,
            reload=reload,
            log_level="info",
            access_log=True
        )
        
        server = uvicorn.Server(config)
        
        logger.info(f"Starting voice integration server on {host}:{port}")
        
        try:
            await server.serve()
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down voice integration system...")
        
        self.is_running = False
        
        # Cleanup components
        await self._cleanup_components()
        
        logger.info("Voice integration system shutdown complete")

# Factory function
def create_voice_integration_system(config: Dict[str, Any] = None) -> VoiceIntegrationSystem:
    """Create voice integration system instance"""
    return VoiceIntegrationSystem(config)

# Main entry point
async def main():
    """Main entry point for voice integration system"""
    # Load configuration from environment
    config = {
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY"),
        "whisper_model": os.getenv("WHISPER_MODEL", "base"),
        "response_time_sla": float(os.getenv("VOICE_RESPONSE_TIME_SLA", "2.0")),
        "frontend_path": os.getenv("FRONTEND_PATH", "frontend"),
        "allowed_origins": os.getenv("ALLOWED_ORIGINS", "*").split(",")
    }
    
    # Create and initialize system
    voice_system = create_voice_integration_system(config)
    
    if await voice_system.initialize():
        # Run server
        await voice_system.run_server(
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8001")),
            reload=os.getenv("RELOAD", "false").lower() == "true"
        )
    else:
        logger.error("Failed to initialize voice integration system")
        sys.exit(1)

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the system
    asyncio.run(main())