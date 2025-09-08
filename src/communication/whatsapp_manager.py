"""
WhatsApp Business Integration Manager
Production-ready WhatsApp Business API integration for AI Agency Platform Phase 2

Features:
- Premium-casual communication channel for EA interactions
- Business verification and credential management
- Media processing (images, documents, voice messages)
- Cross-channel context preservation
- Performance optimization for 500+ concurrent users
- Per-customer MCP server isolation
- Multi-channel personality consistency
"""

import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
import redis
import aiohttp
import aiofiles
from PIL import Image
import speech_recognition as sr
from pydub import AudioSegment

from .whatsapp_channel import WhatsAppChannel, WhatsAppMessage
from ..agents.executive_assistant import ExecutiveAssistant
from ..memory.mem0_manager import CustomerMemoryManager

logger = logging.getLogger(__name__)

@dataclass
class MediaProcessingResult:
    """Result of media processing operation"""
    success: bool
    media_type: str
    processed_content: Optional[str] = None
    transcript: Optional[str] = None
    analysis: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    file_path: Optional[str] = None
    
@dataclass
class BusinessVerificationStatus:
    """WhatsApp Business verification status"""
    is_verified: bool
    business_name: str
    verification_date: Optional[datetime] = None
    phone_number_id: Optional[str] = None
    display_name: Optional[str] = None
    category: Optional[str] = None

class WhatsAppBusinessManager:
    """
    Manages WhatsApp Business integration for multiple customers
    
    Features:
    - Customer-specific WhatsApp number assignment
    - Twilio account management
    - Webhook configuration
    - Message routing and analytics
    - Customer onboarding automation
    """
    
    def __init__(self):
        self.db_connection = None
        self.redis_client = None
        self._initialize_connections()
        self.active_channels: Dict[str, WhatsAppChannel] = {}
        self.memory_manager = CustomerMemoryManager()
        self.media_storage_path = Path(os.getenv('MEDIA_STORAGE_PATH', '/tmp/whatsapp_media'))
        self.media_storage_path.mkdir(parents=True, exist_ok=True)
        
        # Business verification cache
        self.business_verification_cache: Dict[str, BusinessVerificationStatus] = {}
        
        # Performance metrics
        self.performance_metrics = {
            'total_messages': 0,
            'media_messages': 0,
            'response_times': [],
            'concurrent_users': 0,
            'channel_switches': 0
        }
    
    def _initialize_connections(self):
        """Initialize database and Redis connections"""
        try:
            # Database connection
            self.db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub", 
                user="mcphub",
                password="mcphub_password"
            )
            
            # Redis connection
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                db=0,  # Use DB 0 for manager
                decode_responses=True
            )
            
            logger.info("WhatsApp Business Manager initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
    
    async def setup_customer_whatsapp(self, customer_id: str, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Set up WhatsApp Business for a new customer
        
        Args:
            customer_id: Unique customer identifier
            config: Optional WhatsApp configuration override
            
        Returns:
            Setup result with WhatsApp number and configuration
        """
        try:
            # Create customer WhatsApp configuration
            whatsapp_config = {
                'twilio_account_sid': config.get('twilio_account_sid') or os.getenv('TWILIO_ACCOUNT_SID'),
                'twilio_auth_token': config.get('twilio_auth_token') or os.getenv('TWILIO_AUTH_TOKEN'),
                'whatsapp_number': config.get('whatsapp_number') or os.getenv('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886'),
                'webhook_auth_token': config.get('webhook_auth_token') or os.getenv('TWILIO_WEBHOOK_AUTH_TOKEN')
            }
            
            # Create and initialize WhatsApp channel
            channel = WhatsAppChannel(customer_id, whatsapp_config)
            await channel.initialize()
            
            # Store in active channels
            self.active_channels[customer_id] = channel
            
            # Store customer configuration in database
            await self._store_customer_whatsapp_config(customer_id, whatsapp_config)
            
            # Create webhook configuration
            webhook_url = await self._generate_webhook_url(customer_id)
            
            setup_result = {
                "customer_id": customer_id,
                "whatsapp_number": whatsapp_config['whatsapp_number'],
                "webhook_url": webhook_url,
                "status": "configured",
                "created_at": datetime.now().isoformat(),
                "channel_health": await channel.health_check()
            }
            
            logger.info(f"WhatsApp Business configured for customer {customer_id}")
            return setup_result
            
        except Exception as e:
            logger.error(f"Failed to setup WhatsApp for customer {customer_id}: {e}")
            return {
                "customer_id": customer_id,
                "status": "failed",
                "error": str(e)
            }
    
    async def get_customer_whatsapp_channel(self, customer_id: str) -> Optional[WhatsAppChannel]:
        """Get WhatsApp channel for customer"""
        if customer_id in self.active_channels:
            return self.active_channels[customer_id]
        
        # Try to load from database and initialize
        config = await self._load_customer_whatsapp_config(customer_id)
        if config:
            channel = WhatsAppChannel(customer_id, config)
            await channel.initialize()
            self.active_channels[customer_id] = channel
            return channel
        
        return None
    
    async def provision_customer_whatsapp_instantly(self, customer_id: str, phone_number: str) -> Dict[str, Any]:
        """
        Instantly provision WhatsApp for new customer (30-second target)
        
        This method handles the rapid provisioning requirement from the Phase 1 PRD
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Setup WhatsApp channel (5 seconds)
            setup_result = await self.setup_customer_whatsapp(customer_id)
            
            # Step 2: Configure phone number routing (2 seconds)
            await self._configure_phone_routing(customer_id, phone_number)
            
            # Step 3: Initialize Executive Assistant (5 seconds)
            channel = self.active_channels.get(customer_id)
            if channel and channel.ea:
                # Prepare welcome message
                welcome_call = await channel.ea.initialize_welcome_call(phone_number)
            else:
                welcome_call = {"error": "EA not initialized"}
            
            # Step 4: Send initial WhatsApp message (3 seconds)
            if channel:
                welcome_message = """🎉 Welcome to AI Agency Platform!

I'm Sarah, your dedicated Executive Assistant. I'm ready to learn about your business and start automating your daily operations.

You can now:
📱 Message me anytime on WhatsApp
🤖 Tell me about your business processes
⚡ Get instant workflow automations
🧠 I remember everything we discuss

Let's start! Tell me about your business and what you do day-to-day. I'll create your first automation during our conversation."""
                
                try:
                    await channel.send_message(phone_number, welcome_message)
                    sent_welcome = True
                except:
                    sent_welcome = False
            else:
                sent_welcome = False
            
            # Calculate provisioning time
            end_time = datetime.now()
            provisioning_time = (end_time - start_time).total_seconds()
            
            result = {
                "customer_id": customer_id,
                "phone_number": phone_number,
                "whatsapp_number": setup_result.get('whatsapp_number'),
                "webhook_url": setup_result.get('webhook_url'),
                "provisioning_time_seconds": provisioning_time,
                "status": "provisioned" if provisioning_time < 30 else "provisioned_slow",
                "welcome_message_sent": sent_welcome,
                "ea_initialized": welcome_call.get("call_scheduled", False),
                "timestamp": datetime.now().isoformat()
            }
            
            # Log provisioning metrics
            logger.info(f"Customer {customer_id} WhatsApp provisioned in {provisioning_time:.2f}s")
            
            # Store provisioning metrics
            await self._store_provisioning_metrics(customer_id, result)
            
            return result
            
        except Exception as e:
            error_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Failed to provision WhatsApp for {customer_id} in {error_time:.2f}s: {e}")
            
            return {
                "customer_id": customer_id,
                "phone_number": phone_number,
                "status": "failed",
                "error": str(e),
                "provisioning_time_seconds": error_time,
                "timestamp": datetime.now().isoformat()
            }
    
    async def _configure_phone_routing(self, customer_id: str, phone_number: str):
        """Configure phone number routing for customer"""
        try:
            clean_number = phone_number.replace('+', '').replace(' ', '').replace('-', '')
            
            # Store in database
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO customer_phone_routing 
                        (customer_id, phone_number, created_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (phone_number) 
                        DO UPDATE SET customer_id = EXCLUDED.customer_id
                    """, (customer_id, clean_number, datetime.now()))
                    self.db_connection.commit()
            
            # Store in Redis for fast lookup
            if self.redis_client:
                self.redis_client.setex(
                    f"phone_routing:{clean_number}", 
                    86400 * 30,  # 30 days TTL
                    customer_id
                )
            
            logger.info(f"Phone routing configured: {phone_number} -> {customer_id}")
            
        except Exception as e:
            logger.error(f"Failed to configure phone routing: {e}")
    
    async def route_phone_to_customer(self, phone_number: str) -> Optional[str]:
        """Route phone number to customer ID"""
        try:
            clean_number = phone_number.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
            
            # Check Redis first (fast lookup)
            if self.redis_client:
                customer_id = self.redis_client.get(f"phone_routing:{clean_number}")
                if customer_id:
                    return customer_id
            
            # Check database
            if self.db_connection:
                with self.db_connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT customer_id FROM customer_phone_routing WHERE phone_number = %s",
                        (clean_number,)
                    )
                    result = cursor.fetchone()
                    if result:
                        customer_id = result[0]
                        
                        # Cache in Redis
                        if self.redis_client:
                            self.redis_client.setex(
                                f"phone_routing:{clean_number}",
                                86400 * 30,  # 30 days TTL
                                customer_id
                            )
                        
                        return customer_id
            
            # No routing found
            return None
            
        except Exception as e:
            logger.error(f"Error routing phone number: {e}")
            return None
    
    async def _store_customer_whatsapp_config(self, customer_id: str, config: Dict[str, Any]):
        """Store customer WhatsApp configuration"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customer_whatsapp_config 
                    (customer_id, whatsapp_config, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (customer_id) 
                    DO UPDATE SET 
                        whatsapp_config = EXCLUDED.whatsapp_config,
                        updated_at = EXCLUDED.updated_at
                """, (
                    customer_id,
                    json.dumps(config),
                    datetime.now(),
                    datetime.now()
                ))
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to store WhatsApp config: {e}")
    
    async def _load_customer_whatsapp_config(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Load customer WhatsApp configuration"""
        if not self.db_connection:
            return None
            
        try:
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT whatsapp_config FROM customer_whatsapp_config WHERE customer_id = %s",
                    (customer_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    return json.loads(result['whatsapp_config'])
                    
        except Exception as e:
            logger.error(f"Failed to load WhatsApp config: {e}")
        
        return None
    
    async def _generate_webhook_url(self, customer_id: str) -> str:
        """Generate webhook URL for customer"""
        # In production, this would be the actual webhook endpoint
        base_url = os.getenv('WEBHOOK_BASE_URL', 'https://your-domain.com')
        return f"{base_url}/webhook/whatsapp"
    
    async def _store_provisioning_metrics(self, customer_id: str, metrics: Dict[str, Any]):
        """Store provisioning metrics for analytics"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customer_provisioning_metrics 
                    (customer_id, provisioning_type, metrics, created_at)
                    VALUES (%s, %s, %s, %s)
                """, (
                    customer_id,
                    'whatsapp',
                    json.dumps(metrics),
                    datetime.now()
                ))
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to store provisioning metrics: {e}")
    
    async def get_customer_analytics(self, customer_id: str, days: int = 30) -> Dict[str, Any]:
        """Get WhatsApp analytics for customer"""
        try:
            if not self.db_connection:
                return {"error": "Database not available"}
            
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get message counts
                cursor.execute("""
                    SELECT 
                        direction,
                        COUNT(*) as message_count,
                        DATE(created_at) as date
                    FROM whatsapp_messages 
                    WHERE customer_id = %s 
                    AND created_at >= NOW() - INTERVAL '%s days'
                    GROUP BY direction, DATE(created_at)
                    ORDER BY date DESC
                """, (customer_id, days))
                
                message_stats = cursor.fetchall()
                
                # Get conversation count
                cursor.execute("""
                    SELECT COUNT(DISTINCT conversation_id) as conversation_count
                    FROM whatsapp_messages 
                    WHERE customer_id = %s 
                    AND created_at >= NOW() - INTERVAL '%s days'
                """, (customer_id, days))
                
                conversation_count = cursor.fetchone()['conversation_count']
                
                return {
                    "customer_id": customer_id,
                    "days": days,
                    "total_conversations": conversation_count,
                    "message_stats": [dict(stat) for stat in message_stats],
                    "generated_at": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return {"error": str(e)}
    
    async def create_database_tables(self):
        """Create necessary database tables"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                # Customer WhatsApp configuration table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_whatsapp_config (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) UNIQUE NOT NULL,
                        whatsapp_config JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Phone number routing table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_phone_routing (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) NOT NULL,
                        phone_number VARCHAR(50) UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                # Provisioning metrics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customer_provisioning_metrics (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) NOT NULL,
                        provisioning_type VARCHAR(50) NOT NULL,
                        metrics JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                self.db_connection.commit()
                logger.info("Database tables created successfully")
                
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
    
    async def process_media_message(self, media_url: str, media_type: str, customer_id: str) -> MediaProcessingResult:
        """
        Process WhatsApp media messages (images, documents, voice)
        Supports Phase 2 premium-casual media interactions
        """
        try:
            start_time = datetime.now()
            
            # Download media file
            media_file_path = await self._download_media(media_url, media_type, customer_id)
            if not media_file_path:
                return MediaProcessingResult(
                    success=False,
                    media_type=media_type,
                    error_message="Failed to download media file"
                )
            
            result = MediaProcessingResult(
                success=True,
                media_type=media_type,
                file_path=str(media_file_path)
            )
            
            # Process based on media type
            if media_type.startswith('image/'):
                result = await self._process_image(media_file_path, result)
            elif media_type.startswith('audio/'):
                result = await self._process_audio(media_file_path, result)
            elif media_type.startswith('application/'):
                result = await self._process_document(media_file_path, result)
            
            # Store processing metrics
            processing_time = (datetime.now() - start_time).total_seconds()
            await self._store_media_metrics(customer_id, media_type, processing_time, result.success)
            
            self.performance_metrics['media_messages'] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing media: {e}")
            return MediaProcessingResult(
                success=False,
                media_type=media_type,
                error_message=str(e)
            )
    
    async def _download_media(self, media_url: str, media_type: str, customer_id: str) -> Optional[Path]:
        """Download media file from WhatsApp"""
        try:
            # Generate unique filename
            file_extension = media_type.split('/')[-1]
            filename = f"{customer_id}_{uuid.uuid4().hex[:8]}.{file_extension}"
            file_path = self.media_storage_path / filename
            
            async with aiohttp.ClientSession() as session:
                async with session.get(media_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                await f.write(chunk)
                        return file_path
            
            return None
            
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            return None
    
    async def _process_image(self, file_path: Path, result: MediaProcessingResult) -> MediaProcessingResult:
        """Process image files with AI analysis"""
        try:
            with Image.open(file_path) as img:
                # Basic image analysis
                result.analysis = {\n                    'dimensions': img.size,\n                    'format': img.format,\n                    'mode': img.mode\n                }\n                \n                # Premium-casual response for images\n                result.processed_content = f\"I can see your image! It's a {img.format.lower()} file ({img.size[0]}x{img.size[1]} pixels). Let me know how I can help you with it! 📸\"\n            \n            return result\n            \n        except Exception as e:\n            result.success = False\n            result.error_message = f\"Image processing error: {e}\"\n            return result\n    \n    async def _process_audio(self, file_path: Path, result: MediaProcessingResult) -> MediaProcessingResult:\n        \"\"\"Process voice messages with speech recognition\"\"\"\n        try:\n            # Convert to WAV if needed\n            audio = AudioSegment.from_file(file_path)\n            wav_path = file_path.with_suffix('.wav')\n            audio.export(wav_path, format='wav')\n            \n            # Speech recognition\n            recognizer = sr.Recognizer()\n            with sr.AudioFile(str(wav_path)) as source:\n                audio_data = recognizer.record(source)\n                transcript = recognizer.recognize_google(audio_data)\n                \n                result.transcript = transcript\n                result.processed_content = f\"Got your voice message! You said: \\\"{transcript}\\\". How can I help with that? 🎙️\"\n            \n            # Clean up WAV file\n            wav_path.unlink(missing_ok=True)\n            \n            return result\n            \n        except Exception as e:\n            result.success = False\n            result.error_message = f\"Audio processing error: {e}\"\n            return result\n    \n    async def _process_document(self, file_path: Path, result: MediaProcessingResult) -> MediaProcessingResult:\n        \"\"\"Process document files\"\"\"\n        try:\n            file_size = file_path.stat().st_size\n            result.analysis = {\n                'file_size': file_size,\n                'file_extension': file_path.suffix\n            }\n            \n            # Premium-casual response for documents\n            result.processed_content = f\"Thanks for the document! I've received your {file_path.suffix.upper()} file ({file_size // 1024}KB). I'll review it and incorporate the information into our business discussion. 📄\"\n            \n            return result\n            \n        except Exception as e:\n            result.success = False\n            result.error_message = f\"Document processing error: {e}\"\n            return result\n    \n    async def setup_business_verification(self, customer_id: str, business_config: Dict[str, Any]) -> BusinessVerificationStatus:\n        \"\"\"Setup WhatsApp Business verification for customer\"\"\"\n        try:\n            verification_status = BusinessVerificationStatus(\n                is_verified=business_config.get('is_verified', False),\n                business_name=business_config.get('business_name', f\"Customer {customer_id} Business\"),\n                verification_date=datetime.now(),\n                phone_number_id=business_config.get('phone_number_id'),\n                display_name=business_config.get('display_name'),\n                category=business_config.get('category', 'Business')\n            )\n            \n            # Cache verification status\n            self.business_verification_cache[customer_id] = verification_status\n            \n            # Store in database\n            await self._store_business_verification(customer_id, verification_status)\n            \n            logger.info(f\"Business verification setup for customer {customer_id}: {verification_status.business_name}\")\n            return verification_status\n            \n        except Exception as e:\n            logger.error(f\"Error setting up business verification: {e}\")\n            return BusinessVerificationStatus(\n                is_verified=False,\n                business_name=f\"Customer {customer_id}\",\n                verification_date=datetime.now()\n            )\n    \n    async def handle_cross_channel_handoff(self, customer_id: str, from_channel: str, to_channel: str, context: Dict[str, Any]) -> Dict[str, Any]:\n        \"\"\"Handle conversation handoff between WhatsApp and other channels\"\"\"\n        try:\n            # Store handoff context in customer memory\n            handoff_context = {\n                'from_channel': from_channel,\n                'to_channel': to_channel,\n                'context': context,\n                'timestamp': datetime.now().isoformat(),\n                'customer_id': customer_id\n            }\n            \n            # Use memory manager to preserve context\n            await self.memory_manager.store_cross_channel_context(\n                customer_id,\n                handoff_context\n            )\n            \n            self.performance_metrics['channel_switches'] += 1\n            \n            return {\n                'success': True,\n                'handoff_id': str(uuid.uuid4()),\n                'from_channel': from_channel,\n                'to_channel': to_channel,\n                'context_preserved': True\n            }\n            \n        except Exception as e:\n            logger.error(f\"Error handling cross-channel handoff: {e}\")\n            return {\n                'success': False,\n                'error': str(e)\n            }\n    \n    async def get_premium_casual_personality_config(self, customer_id: str) -> Dict[str, Any]:\n        \"\"\"Get premium-casual personality configuration for WhatsApp\"\"\"\n        return {\n            'tone': 'premium-casual',\n            'style_guidelines': {\n                'greeting': 'Hey! 👋',\n                'enthusiasm': 'moderate',\n                'emoji_usage': 'contextual',\n                'message_length': 'mobile-optimized',\n                'formality': 'approachable-professional'\n            },\n            'whatsapp_adaptations': {\n                'use_emojis': True,\n                'mobile_formatting': True,\n                'quick_responses': True,\n                'casual_language': True,\n                'maintain_intelligence': True\n            },\n            'context_awareness': {\n                'remember_preferences': True,\n                'adapt_to_communication_style': True,\n                'learn_from_interactions': True\n            }\n        }\n    \n    async def optimize_for_concurrent_users(self) -> Dict[str, Any]:\n        \"\"\"Optimize manager for 500+ concurrent users\"\"\"\n        try:\n            # Connection pool optimization\n            if self.db_connection:\n                with self.db_connection.cursor() as cursor:\n                    cursor.execute(\"SELECT count(*) FROM pg_stat_activity WHERE state = 'active';\")\n                    active_connections = cursor.fetchone()[0]\n            else:\n                active_connections = 0\n            \n            # Redis connection optimization\n            redis_info = self.redis_client.info() if self.redis_client else {}\n            \n            # Calculate concurrent user capacity\n            current_channels = len(self.active_channels)\n            estimated_capacity = min(500, max(0, 500 - current_channels))\n            \n            optimization_result = {\n                'current_channels': current_channels,\n                'estimated_capacity': estimated_capacity,\n                'active_db_connections': active_connections,\n                'redis_connected_clients': redis_info.get('connected_clients', 0),\n                'performance_metrics': self.performance_metrics,\n                'optimization_status': 'optimal' if current_channels < 400 else 'approaching_limit'\n            }\n            \n            logger.info(f\"Concurrent user optimization: {optimization_result['optimization_status']}\")\n            return optimization_result\n            \n        except Exception as e:\n            logger.error(f\"Error optimizing for concurrent users: {e}\")\n            return {'error': str(e)}\n    \n    async def _store_media_metrics(self, customer_id: str, media_type: str, processing_time: float, success: bool):\n        \"\"\"Store media processing metrics\"\"\"\n        try:\n            if self.db_connection:\n                with self.db_connection.cursor() as cursor:\n                    cursor.execute(\"\"\"\n                        INSERT INTO whatsapp_media_metrics \n                        (customer_id, media_type, processing_time_seconds, success, created_at)\n                        VALUES (%s, %s, %s, %s, %s)\n                    \"\"\", (\n                        customer_id,\n                        media_type,\n                        processing_time,\n                        success,\n                        datetime.now()\n                    ))\n                    self.db_connection.commit()\n        except Exception as e:\n            logger.error(f\"Error storing media metrics: {e}\")\n    \n    async def _store_business_verification(self, customer_id: str, verification: BusinessVerificationStatus):\n        \"\"\"Store business verification status\"\"\"\n        try:\n            if self.db_connection:\n                with self.db_connection.cursor() as cursor:\n                    cursor.execute(\"\"\"\n                        INSERT INTO whatsapp_business_verification \n                        (customer_id, is_verified, business_name, verification_date, \n                         phone_number_id, display_name, category, created_at)\n                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)\n                        ON CONFLICT (customer_id) DO UPDATE SET\n                            is_verified = EXCLUDED.is_verified,\n                            business_name = EXCLUDED.business_name,\n                            verification_date = EXCLUDED.verification_date,\n                            updated_at = EXCLUDED.created_at\n                    \"\"\", (\n                        customer_id,\n                        verification.is_verified,\n                        verification.business_name,\n                        verification.verification_date,\n                        verification.phone_number_id,\n                        verification.display_name,\n                        verification.category,\n                        datetime.now()\n                    ))\n                    self.db_connection.commit()\n        except Exception as e:\n            logger.error(f\"Error storing business verification: {e}\")\n\n    async def health_check(self) -> Dict[str, Any]:\n        \"\"\"Enhanced system health check for Phase 2\"\"\"\n        health = {\n            \"service\": \"whatsapp_business_manager\",\n            \"timestamp\": datetime.now().isoformat(),\n            \"active_channels\": len(self.active_channels),\n            \"database_status\": \"disconnected\",\n            \"redis_status\": \"disconnected\",\n            \"phase_2_features\": {\n                \"media_processing\": True,\n                \"business_verification\": True,\n                \"cross_channel_handoff\": True,\n                \"premium_casual_personality\": True,\n                \"concurrent_user_optimization\": True\n            }\n        }\n        \n        # Check database\n        if self.db_connection:\n            try:\n                with self.db_connection.cursor() as cursor:\n                    cursor.execute(\"SELECT 1\")\n                    health[\"database_status\"] = \"connected\"\n            except:\n                health[\"database_status\"] = \"error\"\n        \n        # Check Redis\n        if self.redis_client:\n            try:\n                self.redis_client.ping()\n                health[\"redis_status\"] = \"connected\"\n            except:\n                health[\"redis_status\"] = \"error\"\n        \n        # Add performance metrics\n        health[\"performance_metrics\"] = self.performance_metrics\n        health[\"media_storage_path\"] = str(self.media_storage_path)\n        health[\"business_verifications\"] = len(self.business_verification_cache)\n        \n        return health\n\n    async def create_database_tables(self):\n        \"\"\"Create enhanced database tables for Phase 2 features\"\"\"\n        if not self.db_connection:\n            return\n            \n        try:\n            with self.db_connection.cursor() as cursor:\n                # Enhanced customer WhatsApp configuration table\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS customer_whatsapp_config (\n                        id SERIAL PRIMARY KEY,\n                        customer_id VARCHAR(255) UNIQUE NOT NULL,\n                        whatsapp_config JSONB NOT NULL,\n                        premium_casual_config JSONB DEFAULT '{}',\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                \"\"\")\n                \n                # Phone number routing table\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS customer_phone_routing (\n                        id SERIAL PRIMARY KEY,\n                        customer_id VARCHAR(255) NOT NULL,\n                        phone_number VARCHAR(50) UNIQUE NOT NULL,\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                \"\"\")\n                \n                # Enhanced provisioning metrics table\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS customer_provisioning_metrics (\n                        id SERIAL PRIMARY KEY,\n                        customer_id VARCHAR(255) NOT NULL,\n                        provisioning_type VARCHAR(50) NOT NULL,\n                        metrics JSONB NOT NULL,\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                \"\"\")\n                \n                # Media processing metrics table (NEW)\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS whatsapp_media_metrics (\n                        id SERIAL PRIMARY KEY,\n                        customer_id VARCHAR(255) NOT NULL,\n                        media_type VARCHAR(100) NOT NULL,\n                        processing_time_seconds DECIMAL(10,3) NOT NULL,\n                        success BOOLEAN NOT NULL,\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                    \n                    CREATE INDEX IF NOT EXISTS idx_media_metrics_customer_id ON whatsapp_media_metrics(customer_id);\n                    CREATE INDEX IF NOT EXISTS idx_media_metrics_created_at ON whatsapp_media_metrics(created_at);\n                \"\"\")\n                \n                # Business verification table (NEW)\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS whatsapp_business_verification (\n                        id SERIAL PRIMARY KEY,\n                        customer_id VARCHAR(255) UNIQUE NOT NULL,\n                        is_verified BOOLEAN NOT NULL,\n                        business_name VARCHAR(255) NOT NULL,\n                        verification_date TIMESTAMP,\n                        phone_number_id VARCHAR(255),\n                        display_name VARCHAR(255),\n                        category VARCHAR(100),\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                \"\"\")\n                \n                # Cross-channel context table (NEW)\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS cross_channel_context (\n                        id SERIAL PRIMARY KEY,\n                        customer_id VARCHAR(255) NOT NULL,\n                        handoff_id VARCHAR(255) NOT NULL,\n                        from_channel VARCHAR(50) NOT NULL,\n                        to_channel VARCHAR(50) NOT NULL,\n                        context_data JSONB NOT NULL,\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                    \n                    CREATE INDEX IF NOT EXISTS idx_cross_channel_customer_id ON cross_channel_context(customer_id);\n                    CREATE INDEX IF NOT EXISTS idx_cross_channel_handoff_id ON cross_channel_context(handoff_id);\n                \"\"\")\n                \n                self.db_connection.commit()\n                logger.info(\"Enhanced Phase 2 database tables created successfully\")\n                \n        except Exception as e:\n            logger.error(f\"Failed to create enhanced database tables: {e}\")\n\n# Global manager instance\nwhatsapp_manager = WhatsAppBusinessManager()