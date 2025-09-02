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
from ..agents.executive_assistant import ExecutiveAssistant, ConversationChannel

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
            # Parse the incoming message
            message = await self.handle_incoming_message(request_data)
            
            # Handle media messages
            if message.num_media > 0:
                media_response = await self._handle_media_message(message)
                if media_response:
                    return media_response
            
            # Process through Executive Assistant
            if not self.ea:
                await self.initialize()
            
            response = await self.ea.handle_customer_interaction(
                message.content,
                ConversationChannel.WHATSAPP,
                conversation_id=message.conversation_id
            )
            
            # Send response back to WhatsApp
            await self.send_message(message.from_number, response)
            
            # Store conversation context
            await self._store_conversation_context(message, response)
            
            logger.info(f"Processed WhatsApp message for customer {self.customer_id}")
            return response
            
        except Exception as e:
            logger.error(f"Error handling WhatsApp webhook: {e}")
            error_response = "I apologize, but I encountered an issue processing your message. Let me get back to you in just a moment."
            
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