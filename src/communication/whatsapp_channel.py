"""
WhatsApp Business Channel Implementation using Twilio
Real WhatsApp Business API integration for Executive Assistant conversations
"""

import asyncio
import json
import logging
import hmac
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from urllib.parse import quote_plus, parse_qs

import redis
from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioException
import psycopg2
from psycopg2.extras import RealDictCursor

from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel

logger = logging.getLogger(__name__)

@dataclass
class WhatsAppMessage(BaseMessage):
    """WhatsApp-specific message structure"""
    media_content_type: Optional[str] = None
    media_url: Optional[str] = None
    num_media: int = 0
    profile_name: Optional[str] = None
    wa_id: Optional[str] = None
    button_text: Optional[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.channel = ChannelType.WHATSAPP

class WhatsAppChannel(BaseCommunicationChannel):
    """
    Production-ready WhatsApp Business channel using Twilio WhatsApp Business API
    
    Features:
    - Real Twilio WhatsApp Business API integration
    - Webhook handling for incoming messages
    - Media message support (images, documents, etc.)
    - Conversation continuity across sessions
    - Customer routing and identification
    - Message status tracking and delivery reports
    - Security with webhook signature validation
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        super().__init__(customer_id, config)
        
        # Twilio configuration
        self.account_sid = self.config.get('twilio_account_sid')
        self.auth_token = self.config.get('twilio_auth_token')
        self.whatsapp_number = self.config.get('whatsapp_number', 'whatsapp:+14155238886')  # Twilio Sandbox
        self.webhook_auth_token = self.config.get('webhook_auth_token')
        
        # Initialize Twilio client
        if self.account_sid and self.auth_token:
            self.twilio_client = TwilioClient(self.account_sid, self.auth_token)
        else:
            self.twilio_client = None
            logger.warning(f"Twilio credentials not provided for customer {customer_id}")
        
        # Redis for conversation state management
        self.redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=int(customer_id.split('-')[-1]) % 16,  # Customer-specific DB
            decode_responses=True
        )
        
        # Database connection for persistent storage
        self.db_connection = None
        self._initialize_db_connection()
        
        # Initialize Executive Assistant for this customer
        self.ea = None
    
    def _get_channel_type(self) -> ChannelType:
        return ChannelType.WHATSAPP
    
    def _initialize_db_connection(self):
        """Initialize database connection for message logging"""
        try:
            self.db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub",
                user="mcphub",
                password="mcphub_password"
            )
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
    
    async def initialize(self) -> bool:
        """Initialize WhatsApp channel and Executive Assistant"""
        try:
            # Initialize Executive Assistant for this customer
            self.ea = ExecutiveAssistant(self.customer_id)
            
            # Test Twilio connection
            if self.twilio_client:
                # Verify WhatsApp number and permissions
                try:
                    # Test by getting account info (doesn't send a message)
                    account = self.twilio_client.api.account.fetch()
                    logger.info(f"Twilio account verified: {account.friendly_name}")
                    self.is_initialized = True
                except TwilioException as e:
                    logger.error(f"Twilio verification failed: {e}")
                    self.is_initialized = False
            else:
                # Initialize in demo mode without actual Twilio
                logger.info("Initializing WhatsApp channel in demo mode")
                self.is_initialized = True
                
            # Create database tables if needed
            await self._create_message_tables()
                
            logger.info(f"WhatsApp channel initialized for customer {self.customer_id}")
            return self.is_initialized
            
        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp channel: {e}")
            self.is_initialized = False
            return False
    
    async def _create_message_tables(self):
        """Create database tables for message logging"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS whatsapp_messages (
                        id SERIAL PRIMARY KEY,
                        customer_id VARCHAR(255) NOT NULL,
                        message_id VARCHAR(255) UNIQUE NOT NULL,
                        conversation_id VARCHAR(255) NOT NULL,
                        from_number VARCHAR(50) NOT NULL,
                        to_number VARCHAR(50) NOT NULL,
                        content TEXT NOT NULL,
                        direction VARCHAR(10) NOT NULL, -- 'inbound' or 'outbound'
                        message_status VARCHAR(50) DEFAULT 'sent',
                        media_url TEXT,
                        media_content_type VARCHAR(100),
                        profile_name VARCHAR(255),
                        wa_id VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata JSONB DEFAULT '{}'
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_whatsapp_customer_id ON whatsapp_messages(customer_id);
                    CREATE INDEX IF NOT EXISTS idx_whatsapp_conversation_id ON whatsapp_messages(conversation_id);
                    CREATE INDEX IF NOT EXISTS idx_whatsapp_from_number ON whatsapp_messages(from_number);
                """)
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to create message tables: {e}")
    
    async def send_message(self, to: str, content: str, **kwargs) -> str:
        """
        Send WhatsApp message via Twilio WhatsApp Business API
        
        Args:
            to: Recipient WhatsApp number (format: +1234567890)
            content: Message content text
            **kwargs: Additional message options (media_url, etc.)
            
        Returns:
            message_sid: Twilio message SID for tracking
        """
        try:
            # Format WhatsApp number
            to_whatsapp = f"whatsapp:{to}" if not to.startswith('whatsapp:') else to
            
            # Prepare message parameters
            message_params = {
                'body': content,
                'from_': self.whatsapp_number,
                'to': to_whatsapp
            }
            
            # Add media if provided
            media_url = kwargs.get('media_url')
            if media_url:
                message_params['media_url'] = [media_url]
            
            # Send via Twilio (or simulate in demo mode)
            if self.twilio_client:
                message = self.twilio_client.messages.create(**message_params)
                message_sid = message.sid
                message_status = message.status
            else:
                # Demo mode - generate fake message ID
                message_sid = f"demo_msg_{uuid.uuid4().hex[:10]}"
                message_status = "sent"
                logger.info(f"DEMO: WhatsApp message sent to {to}: {content[:100]}...")
            
            # Log outbound message
            await self._log_message({
                'message_id': message_sid,
                'from_number': self.whatsapp_number.replace('whatsapp:', ''),
                'to_number': to.replace('whatsapp:', ''),
                'content': content,
                'direction': 'outbound',
                'message_status': message_status,
                'media_url': media_url,
                'metadata': kwargs
            })
            
            logger.info(f"WhatsApp message sent successfully: {message_sid}")
            return message_sid
            
        except TwilioException as e:
            logger.error(f"Twilio error sending message: {e}")
            raise Exception(f"Failed to send WhatsApp message: {e}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            raise Exception(f"WhatsApp send error: {e}")
    
    async def handle_incoming_message(self, message_data: Dict[str, Any]) -> WhatsAppMessage:
        """
        Parse Twilio WhatsApp webhook data into WhatsAppMessage
        
        Args:
            message_data: Raw webhook data from Twilio
            
        Returns:
            WhatsAppMessage: Structured message object
        """
        try:
            # Extract message details from Twilio webhook format
            message_id = message_data.get('MessageSid', str(uuid.uuid4()))
            from_number = message_data.get('From', '').replace('whatsapp:', '')
            to_number = message_data.get('To', '').replace('whatsapp:', '')
            content = message_data.get('Body', '')
            
            # Generate conversation ID based on customer's phone number
            conversation_id = self._get_conversation_id(from_number)
            
            # Extract WhatsApp-specific data
            media_content_type = message_data.get('MediaContentType0')
            media_url = message_data.get('MediaUrl0')
            num_media = int(message_data.get('NumMedia', 0))
            profile_name = message_data.get('ProfileName')
            wa_id = message_data.get('WaId')
            button_text = message_data.get('ButtonText')
            
            # Create WhatsApp message object
            whatsapp_message = WhatsAppMessage(
                content=content,
                from_number=from_number,
                to_number=to_number,
                channel=ChannelType.WHATSAPP,
                message_id=message_id,
                conversation_id=conversation_id,
                timestamp=datetime.now(),
                customer_id=self.customer_id,
                metadata=message_data,
                media_content_type=media_content_type,
                media_url=media_url,
                num_media=num_media,
                profile_name=profile_name,
                wa_id=wa_id,
                button_text=button_text
            )
            
            # Log inbound message
            await self._log_message({
                'message_id': message_id,
                'from_number': from_number,
                'to_number': to_number,
                'content': content,
                'direction': 'inbound',
                'media_url': media_url,
                'media_content_type': media_content_type,
                'profile_name': profile_name,
                'wa_id': wa_id,
                'metadata': message_data
            })
            
            logger.info(f"Parsed incoming WhatsApp message: {message_id} from {from_number}")
            return whatsapp_message
            
        except Exception as e:
            logger.error(f"Error parsing WhatsApp message: {e}")
            raise Exception(f"Failed to parse WhatsApp message: {e}")
    
    async def handle_webhook(self, request_data: Dict[str, Any]) -> str:
        """
        Handle incoming WhatsApp webhook from Twilio
        
        Args:
            request_data: Full webhook request data
            
        Returns:
            response: Message content sent back to user
        """
        try:
            start_time = datetime.now()
            
            # Parse the incoming message
            message = await self.handle_incoming_message(request_data)
            
            # Handle media messages with enhanced Phase 2 processing
            if message.num_media > 0:
                media_response = await self._handle_enhanced_media_message(message)
                if media_response:
                    # Apply premium-casual tone to media response
                    casual_response = await self._apply_premium_casual_tone(media_response)
                    await self.send_message(message.from_number, casual_response)
                    return casual_response
            
            # Get premium-casual personality configuration
            personality_config = await self._get_personality_config()
            
            # Process through Executive Assistant with WhatsApp context
            if not self.ea:
                await self.initialize()
            
            # Enhanced EA interaction with context preservation
            response = await self.ea.handle_customer_interaction(
                message.content,
                ConversationChannel.WHATSAPP,
                conversation_id=message.conversation_id,
                channel_context={
                    'platform': 'whatsapp',
                    'personality': 'premium-casual',
                    'mobile_optimized': True,
                    'emoji_friendly': True,
                    'profile_name': message.profile_name
                }
            )
            
            # Apply premium-casual tone adaptation
            casual_response = await self._apply_premium_casual_tone(response)
            
            # Send response back to WhatsApp
            await self.send_message(message.from_number, casual_response)
            
            # Store enhanced conversation context
            await self._store_enhanced_conversation_context(message, casual_response, start_time)
            
            # Update performance metrics
            processing_time = (datetime.now() - start_time).total_seconds()
            await self._track_response_time(processing_time)
            
            logger.info(f"Processed premium-casual WhatsApp message for customer {self.customer_id} in {processing_time:.2f}s")
            return casual_response
            
        except Exception as e:
            logger.error(f"Error handling WhatsApp webhook: {e}")
            
            # Premium-casual error response
            error_response = "Hey! 😅 I hit a small snag processing your message. Give me just a moment to sort this out - I'll be right back with you!"
            
            # Try to send error response
            try:
                if 'From' in request_data:
                    from_number = request_data['From'].replace('whatsapp:', '')
                    await self.send_message(from_number, error_response)
            except:
                pass  # Fail silently if we can't send error response
                
            return error_response
    
    async def _handle_media_message(self, message: WhatsAppMessage) -> Optional[str]:
        """Handle media messages (images, documents, etc.)"""
        try:
            if message.media_content_type and message.media_url:
                media_type = message.media_content_type.split('/')[0]
                
                if media_type == 'image':
                    return "I can see you've sent me an image! I'll analyze it and get back to you with relevant information or suggestions."
                elif media_type == 'application':  # Documents
                    return "Thank you for the document! I'll review it and incorporate the information into our business discussion."
                elif media_type == 'audio':
                    return "I received your voice message. I'll process it and respond accordingly."
                else:
                    return "I received your media file. Let me know how I can help you with it!"
            
            return None
            
        except Exception as e:
            logger.error(f"Error handling media message: {e}")
            return "I received your media but encountered an issue processing it. Please try again or describe what you'd like me to help with."
    
    def _get_conversation_id(self, phone_number: str) -> str:
        """Generate consistent conversation ID for a phone number"""
        # Use customer_id + phone_number for unique conversation ID
        conversation_key = f"{self.customer_id}:{phone_number}"
        return hashlib.md5(conversation_key.encode()).hexdigest()
    
    async def _log_message(self, message_data: Dict[str, Any]):
        """Log message to database for audit trail"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO whatsapp_messages 
                    (customer_id, message_id, conversation_id, from_number, to_number, 
                     content, direction, message_status, media_url, media_content_type, 
                     profile_name, wa_id, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    self.customer_id,
                    message_data.get('message_id'),
                    self._get_conversation_id(message_data.get('from_number', '')),
                    message_data.get('from_number'),
                    message_data.get('to_number'),
                    message_data.get('content'),
                    message_data.get('direction'),
                    message_data.get('message_status', 'received'),
                    message_data.get('media_url'),
                    message_data.get('media_content_type'),
                    message_data.get('profile_name'),
                    message_data.get('wa_id'),
                    json.dumps(message_data.get('metadata', {}))
                ))
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Failed to log message: {e}")
    
    async def _store_conversation_context(self, message: WhatsAppMessage, response: str):
        """Store conversation context in Redis for session continuity"""
        try:
            context_key = f"whatsapp_conv:{message.conversation_id}"
            context_data = {
                "last_message": message.content,
                "last_response": response,
                "from_number": message.from_number,
                "profile_name": message.profile_name,
                "timestamp": message.timestamp.isoformat(),
                "customer_id": self.customer_id
            }
            
            # Store with 24-hour TTL
            self.redis_client.setex(context_key, 86400, json.dumps(context_data))
            
        except Exception as e:
            logger.error(f"Failed to store conversation context: {e}")
    
    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        """
        Validate Twilio webhook signature for security
        
        Args:
            payload: Raw webhook payload
            signature: X-Twilio-Signature header value
            
        Returns:
            bool: True if signature is valid
        """
        if not self.webhook_auth_token:
            logger.warning("Webhook auth token not configured - skipping signature validation")
            return True
            
        try:
            # Compute expected signature
            expected_signature = hmac.new(
                self.webhook_auth_token.encode('utf-8'),
                payload.encode('utf-8'),
                hashlib.sha1
            ).digest()
            
            # Compare with provided signature (remove 'sha1=' prefix)
            provided_signature = signature.replace('sha1=', '')
            expected_signature_hex = expected_signature.hex()
            
            return hmac.compare_digest(expected_signature_hex, provided_signature)
            
        except Exception as e:
            logger.error(f"Error validating webhook signature: {e}")
            return False
    
    async def get_conversation_history(self, from_number: str, limit: int = 50) -> List[Dict]:
        """Get conversation history for a phone number"""
        if not self.db_connection:
            return []
            
        try:
            conversation_id = self._get_conversation_id(from_number)
            
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT message_id, from_number, to_number, content, direction, 
                           message_status, media_url, media_content_type, profile_name,
                           created_at, metadata
                    FROM whatsapp_messages 
                    WHERE customer_id = %s AND conversation_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (self.customer_id, conversation_id, limit))
                
                messages = cursor.fetchall()
                return [dict(message) for message in messages]
                
        except Exception as e:
            logger.error(f"Error getting conversation history: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Enhanced health check for WhatsApp channel"""
        base_health = await super().health_check()
        
        # Check Twilio connectivity
        twilio_status = "connected" if self.twilio_client else "demo_mode"
        if self.twilio_client:
            try:
                account = self.twilio_client.api.account.fetch()
                twilio_status = "active"
            except TwilioException:
                twilio_status = "error"
        
        # Check database connectivity
        db_status = "connected" if self.db_connection else "disconnected"
        
        # Check Redis connectivity
        redis_status = "disconnected"
        try:
            self.redis_client.ping()
            redis_status = "connected"
        except:
            pass
        
        base_health.update({
            "twilio_status": twilio_status,
            "database_status": db_status,
            "redis_status": redis_status,
            "whatsapp_number": self.whatsapp_number,
            "ea_initialized": self.ea is not None
        })
        
        return base_health
    
    async def get_message_status(self, message_id: str) -> Dict[str, Any]:
        """Get detailed status of a WhatsApp message"""
        base_status = await super().get_message_status(message_id)
        
        # Get status from Twilio
        if self.twilio_client and message_id.startswith('SM'):
            try:
                message = self.twilio_client.messages(message_id).fetch()
                base_status.update({
                    "status": message.status,
                    "error_code": message.error_code,
                    "error_message": message.error_message,
                    "date_sent": message.date_sent.isoformat() if message.date_sent else None,
                    "date_updated": message.date_updated.isoformat() if message.date_updated else None
                })
            except TwilioException as e:
                base_status["error"] = str(e)
        
        return base_status
    
    async def _handle_enhanced_media_message(self, message: WhatsAppMessage) -> Optional[str]:
        """Enhanced media message handling for Phase 2 premium-casual interactions"""
        try:
            if message.media_content_type and message.media_url:
                # Import media processing from manager
                from .whatsapp_manager import whatsapp_manager
                
                # Process media with advanced capabilities
                media_result = await whatsapp_manager.process_media_message(
                    message.media_url,
                    message.media_content_type,
                    self.customer_id
                )
                
                if media_result.success:
                    return media_result.processed_content
                else:
                    return f"I received your media but ran into a small issue processing it. {media_result.error_message} Could you try sending it again? 📱"
            
            return None
            
        except Exception as e:
            logger.error(f"Error handling enhanced media message: {e}")
            return "I can see you sent me something but I'm having trouble viewing it right now. Could you try again or tell me what it is? 🤔"
    
    async def _apply_premium_casual_tone(self, content: str) -> str:
        """Apply premium-casual tone adaptation for WhatsApp"""
        try:
            # Get personality configuration
            config = await self._get_personality_config()
            
            # Simple tone adaptations for WhatsApp
            adaptations = {
                # Make greetings more casual
                'Hello': 'Hey',
                'Good morning': 'Morning',
                'Good afternoon': 'Hey there',
                'Good evening': 'Evening',
                
                # Add casual connectors
                'I will': "I'll",
                'I am': "I'm",
                'You are': "You're",
                'We will': "We'll",
                'That is': "That's",
                'It is': "It's",
                'Cannot': "Can't",
                
                # Professional but approachable
                'I apologize': 'Sorry about that',
                'Thank you very much': 'Thanks so much',
                'I understand': 'Got it',
                'Please let me know': 'Let me know',
                'I would be happy to': "I'd love to",
                'I recommend': "I'd suggest"
            }
            
            # Apply adaptations
            adapted_content = content
            for formal, casual in adaptations.items():
                adapted_content = adapted_content.replace(formal, casual)
            
            # Ensure mobile-friendly formatting
            if len(adapted_content) > 200:
                # Break into shorter paragraphs for mobile
                sentences = adapted_content.split('. ')
                if len(sentences) > 2:
                    mid_point = len(sentences) // 2
                    adapted_content = '. '.join(sentences[:mid_point]) + '.\\n\\n' + '. '.join(sentences[mid_point:])
            
            return adapted_content
            
        except Exception as e:
            logger.error(f"Error applying premium-casual tone: {e}")
            return content  # Return original if adaptation fails
    
    async def _get_personality_config(self) -> Dict[str, Any]:
        """Get premium-casual personality configuration"""
        try:
            from .whatsapp_manager import whatsapp_manager
            return await whatsapp_manager.get_premium_casual_personality_config(self.customer_id)
        except Exception as e:
            logger.error(f"Error getting personality config: {e}")
            return {
                'tone': 'premium-casual',
                'whatsapp_adaptations': {
                    'use_emojis': True,
                    'mobile_formatting': True,
                    'casual_language': True
                }
            }
    
    async def _store_enhanced_conversation_context(self, message: WhatsAppMessage, response: str, start_time: datetime):
        """Store enhanced conversation context with performance metrics"""
        try:
            processing_time = (datetime.now() - start_time).total_seconds()
            
            context_key = f"whatsapp_conv:{message.conversation_id}"
            enhanced_context = {
                "last_message": message.content,
                "last_response": response,
                "from_number": message.from_number,
                "profile_name": message.profile_name,
                "timestamp": message.timestamp.isoformat(),
                "customer_id": self.customer_id,
                "processing_time_seconds": processing_time,
                "media_attached": message.num_media > 0,
                "personality_applied": "premium-casual",
                "channel_context": {
                    "platform": "whatsapp",
                    "mobile_optimized": True,
                    "emoji_friendly": True
                }
            }
            
            # Store with 48-hour TTL for enhanced context
            self.redis_client.setex(context_key, 86400 * 2, json.dumps(enhanced_context))
            
            # Store cross-channel context for handoffs
            await self._store_cross_channel_context(message, response)
            
        except Exception as e:
            logger.error(f"Failed to store enhanced conversation context: {e}")
    
    async def _store_cross_channel_context(self, message: WhatsAppMessage, response: str):
        """Store context for cross-channel handoffs"""
        try:
            cross_channel_key = f"cross_channel:{self.customer_id}"
            context_data = {
                "last_channel": "whatsapp",
                "last_interaction": {
                    "message": message.content,
                    "response": response,
                    "timestamp": message.timestamp.isoformat(),
                    "profile_name": message.profile_name
                },
                "conversation_id": message.conversation_id,
                "personality_state": "premium-casual",
                "context_metadata": {
                    "platform_preferences": "mobile-friendly",
                    "communication_style": "informal-professional",
                    "emoji_usage": True
                }
            }
            
            # Store for cross-channel access (24 hour TTL)
            self.redis_client.setex(cross_channel_key, 86400, json.dumps(context_data))
            
        except Exception as e:
            logger.error(f"Failed to store cross-channel context: {e}")
    
    async def _track_response_time(self, processing_time: float):
        """Track response times for performance monitoring"""
        try:
            # Store individual response time
            response_time_key = f"response_times:{self.customer_id}"
            self.redis_client.lpush(response_time_key, processing_time)
            
            # Keep only last 100 response times
            self.redis_client.ltrim(response_time_key, 0, 99)
            
            # Set TTL on the list
            self.redis_client.expire(response_time_key, 86400)  # 24 hours
            
            # Update global performance metrics if available
            try:
                from .whatsapp_manager import whatsapp_manager
                whatsapp_manager.performance_metrics['response_times'].append(processing_time)
                whatsapp_manager.performance_metrics['total_messages'] += 1
                
                # Keep only last 1000 response times for memory management
                if len(whatsapp_manager.performance_metrics['response_times']) > 1000:
                    whatsapp_manager.performance_metrics['response_times'] = whatsapp_manager.performance_metrics['response_times'][-1000:]
            except:
                pass  # Don't fail if manager not available
            
        except Exception as e:
            logger.error(f"Error tracking response time: {e}")
    
    async def enable_cross_channel_handoff(self, target_channel: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Enable handoff to other communication channels"""
        try:
            from .whatsapp_manager import whatsapp_manager
            
            handoff_result = await whatsapp_manager.handle_cross_channel_handoff(
                self.customer_id,
                'whatsapp',
                target_channel,
                context
            )
            
            return handoff_result
            
        except Exception as e:
            logger.error(f"Error enabling cross-channel handoff: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get channel performance metrics"""
        try:
            # Get response times from Redis
            response_time_key = f"response_times:{self.customer_id}"
            response_times = [float(rt) for rt in self.redis_client.lrange(response_time_key, 0, -1)]
            
            metrics = {
                'customer_id': self.customer_id,
                'channel': 'whatsapp',
                'response_times': {
                    'count': len(response_times),
                    'average': sum(response_times) / len(response_times) if response_times else 0,
                    'min': min(response_times) if response_times else 0,
                    'max': max(response_times) if response_times else 0
                },
                'sla_compliance': {
                    'target_response_time': 3.0,  # 3 seconds
                    'within_sla': len([rt for rt in response_times if rt <= 3.0]),
                    'sla_percentage': (len([rt for rt in response_times if rt <= 3.0]) / len(response_times) * 100) if response_times else 100
                },
                'features_enabled': {
                    'premium_casual_personality': True,
                    'media_processing': True,
                    'cross_channel_handoff': True,
                    'context_preservation': True
                }
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {'error': str(e)}