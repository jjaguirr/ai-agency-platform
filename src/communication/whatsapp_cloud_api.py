"""
WhatsApp Cloud API Direct Integration
Direct integration with Meta's WhatsApp Cloud API for messaging and calling
"""

import asyncio
import logging
import json
import os
from datetime import datetime, time
from typing import Dict, Any, Optional, List
import aiohttp
import hmac
import hashlib
from pytz import timezone
import pytz

from .base_channel import BaseCommunicationChannel, BaseMessage, ChannelType

logger = logging.getLogger(__name__)

class WhatsAppCloudMessage(BaseMessage):
    """WhatsApp Cloud API message format"""
    
    def __init__(self, content: str, from_number: str, to_number: str,
                 message_id: str = "", conversation_id: str = "",
                 customer_id: Optional[str] = None, message_type: str = "text",
                 **kwargs):
        super().__init__(
            content=content,
            from_number=from_number,
            to_number=to_number,
            channel=ChannelType.WHATSAPP,
            message_id=message_id,
            conversation_id=conversation_id,
            timestamp=datetime.now(),
            customer_id=customer_id,
            metadata=kwargs
        )
        self.message_type = message_type

class WhatsAppCloudAPIChannel(BaseCommunicationChannel):
    """
    Direct WhatsApp Cloud API integration
    
    Features:
    - Direct messaging via Meta's Cloud API
    - Voice calling capabilities  
    - Media message support
    - Webhook handling
    - No third-party dependencies (Twilio-free)
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any] = None):
        super().__init__(customer_id, config)
        
        # Ensure config is not None
        if config is None:
            config = {}
        
        # WhatsApp Cloud API credentials
        self.access_token = config.get('access_token') or os.getenv('WHATSAPP_BUSINESS_TOKEN')
        self.phone_number_id = config.get('phone_number_id') or os.getenv('WHATSAPP_BUSINESS_PHONE_ID')
        self.verify_token = config.get('verify_token') or os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')
        
        # API endpoints
        self.base_url = "https://graph.facebook.com/v18.0"
        self.webhook_secret = config.get('webhook_secret') or os.getenv('WHATSAPP_WEBHOOK_SECRET', '')
        
        # Validate required credentials
        if not self.access_token or not self.phone_number_id:
            logger.error(f"Missing WhatsApp Cloud API credentials for customer {customer_id}")
            logger.error(f"access_token: {'✓' if self.access_token else '✗'}")
            logger.error(f"phone_number_id: {'✓' if self.phone_number_id else '✗'}")
        
        # Call settings
        self.calling_enabled = config.get('calling_enabled', True)
        
        # Flexible business hours - can be disabled via environment variable
        disable_hours_check = os.getenv('DISABLE_BUSINESS_HOURS_CHECK', 'false').lower() == 'true'
        
        if disable_hours_check:
            self.business_hours = None  # Calling available 24/7
            logger.info("Business hours checking disabled - calling available 24/7")
        else:
            self.business_hours = config.get('business_hours', {
                'timezone': 'America/New_York',
                'hours': {
                    'monday': {'start': '09:00', 'end': '17:00'},
                    'tuesday': {'start': '09:00', 'end': '17:00'},
                    'wednesday': {'start': '09:00', 'end': '17:00'},
                    'thursday': {'start': '09:00', 'end': '17:00'},
                    'friday': {'start': '09:00', 'end': '17:00'},
                    'saturday': {'start': '10:00', 'end': '16:00'},  # Added weekend hours
                    'sunday': {'start': '12:00', 'end': '16:00'}
                }
            })
        
        logger.info(f"WhatsApp Cloud API channel initialized for customer {customer_id}")
    
    def _get_channel_type(self) -> ChannelType:
        return ChannelType.WHATSAPP
    
    async def initialize(self) -> bool:
        """Initialize WhatsApp Cloud API channel"""
        try:
            if not self.access_token or not self.phone_number_id:
                logger.error("Missing required WhatsApp Cloud API credentials")
                return False
            
            # Test API connection
            if await self._test_api_connection():
                logger.info("✅ WhatsApp Cloud API connection successful")
                
                # Configure calling if enabled
                if self.calling_enabled:
                    await self._configure_calling_settings()
                
                self.is_initialized = True
                return True
            else:
                logger.error("❌ WhatsApp Cloud API connection failed")
                return False
                
        except Exception as e:
            logger.error(f"Failed to initialize WhatsApp Cloud API: {e}")
            return False
    
    async def _test_api_connection(self) -> bool:
        """Test connection to WhatsApp Cloud API"""
        try:
            url = f"{self.base_url}/{self.phone_number_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Phone number info: {data}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"API test failed: {response.status} - {error_text}")
                        return False
                        
        except Exception as e:
            logger.error(f"API connection test error: {e}")
            return False
    
    async def _configure_calling_settings(self) -> bool:
        """Configure voice calling settings according to Meta's official documentation"""
        try:
            # First check if we're eligible for calling (1000+ messages requirement)
            eligibility = await self._check_calling_eligibility()
            if not eligibility["eligible"]:
                logger.warning(f"Calling not eligible: {eligibility['reason']}")
                return True  # Don't fail initialization
            
            url = f"{self.base_url}/{self.phone_number_id}/settings"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Official Meta calling configuration
            settings_data = {
                "calling": {
                    "status": "ENABLED",
                    "call_icon_visibility": "DEFAULT",  # Show call button to users
                    "callback_permission_status": "ENABLED",  # Request permission after calls
                    "call_hours": {
                        "status": "DISABLED" if self.business_hours is None else "ENABLED"
                    }
                }
            }
            
            # Add business hours configuration if enabled
            if self.business_hours and not os.getenv('DISABLE_BUSINESS_HOURS_CHECK', 'false').lower() == 'true':
                settings_data["calling"]["call_hours"].update({
                    "timezone_id": self.business_hours.get('timezone', 'America/New_York'),
                    "weekly_operating_hours": self._format_business_hours()
                })
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=settings_data) as response:
                    if response.status == 200:
                        logger.info("✅ Voice calling configured successfully with Meta standards")
                        return True
                    else:
                        error_text = await response.text()
                        logger.warning(f"Call settings update failed: {response.status} - {error_text}")
                        
                        # Check if it's a messaging volume restriction
                        if "messaging limit" in error_text.lower():
                            logger.error("❌ CALLING BLOCKED: Need 1,000+ business-initiated conversations in 24hrs")
                            await self._log_calling_restriction("insufficient_messaging_volume", error_text)
                        
                        return True  # Don't fail initialization
                        
        except Exception as e:
            logger.error(f"Error configuring calling settings: {e}")
            return True  # Don't fail initialization
    
    async def _check_calling_eligibility(self) -> Dict[str, Any]:
        """Check if business meets Meta's calling requirements (1000+ messages/24hrs)"""
        try:
            # Get current calling settings to check restrictions
            url = f"{self.base_url}/{self.phone_number_id}/settings"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        calling_config = data.get('calling', {})
                        
                        # Check for active restrictions
                        restrictions = calling_config.get('restrictions', {})
                        if restrictions.get('restrictions_list'):
                            restriction = restrictions['restrictions_list'][0]
                            return {
                                "eligible": False,
                                "reason": f"Calling restricted: {restriction.get('reason', 'Unknown restriction')}",
                                "restriction_type": restriction.get('type'),
                                "expiration": restriction.get('expiration')
                            }
                        
                        # Check if calling is already enabled (implies we meet volume requirements)
                        if calling_config.get('status') == 'ENABLED':
                            return {
                                "eligible": True,
                                "reason": "Calling already enabled - volume requirements met",
                                "current_status": "enabled"
                            }
                        
                        # If calling is disabled, we need to check why
                        return {
                            "eligible": False,
                            "reason": "Calling not enabled - may not meet 1,000+ message volume requirement",
                            "current_status": "disabled",
                            "requirements": "Need 1,000+ business-initiated conversations in rolling 24-hour period"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "eligible": False,
                            "reason": f"Cannot check eligibility: {error_text}",
                            "api_error": True
                        }
                        
        except Exception as e:
            logger.error(f"Error checking calling eligibility: {e}")
            return {
                "eligible": False,
                "reason": f"Eligibility check failed: {str(e)}",
                "error": True
            }
    
    def _format_business_hours(self) -> List[Dict[str, str]]:
        """Format business hours for Meta's API format"""
        if not self.business_hours or not self.business_hours.get('hours'):
            return []
        
        formatted_hours = []
        day_mapping = {
            'monday': 'MONDAY',
            'tuesday': 'TUESDAY', 
            'wednesday': 'WEDNESDAY',
            'thursday': 'THURSDAY',
            'friday': 'FRIDAY',
            'saturday': 'SATURDAY',
            'sunday': 'SUNDAY'
        }
        
        for day, hours in self.business_hours['hours'].items():
            if day.lower() in day_mapping and hours:
                # Convert "09:00" to "0900" format
                open_time = hours.get('start', '09:00').replace(':', '')
                close_time = hours.get('end', '17:00').replace(':', '')
                
                formatted_hours.append({
                    "day_of_week": day_mapping[day.lower()],
                    "open_time": open_time,
                    "close_time": close_time
                })
        
        return formatted_hours
    
    async def _log_calling_restriction(self, restriction_type: str, details: str):
        """Log calling restrictions for monitoring"""
        try:
            restriction_log = {
                "timestamp": datetime.now().isoformat(),
                "customer_id": self.customer_id,
                "phone_number_id": self.phone_number_id,
                "restriction_type": restriction_type,
                "details": details,
                "system": "whatsapp_calling"
            }
            
            logger.error(f"Calling restriction logged: {json.dumps(restriction_log)}")
            
            # Store in memory for tracking
            from ..memory import memory_store
            if memory_store:
                await memory_store.store_memory(
                    content=f"WhatsApp calling restriction: {restriction_type} - {details}",
                    metadata={
                        "tags": ["whatsapp", "calling", "restriction"],
                        "type": "system_alert"
                    }
                )
                
        except Exception as e:
            logger.error(f"Error logging calling restriction: {e}")
    
    async def send_message(self, to_number: str, content: str, **kwargs) -> str:
        """Send message via WhatsApp Cloud API"""
        try:
            # Clean phone number format
            clean_to = to_number.replace('+', '').replace(' ', '').replace('-', '')
            
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Message payload
            message_data = {
                "messaging_product": "whatsapp",
                "to": clean_to,
                "type": "text",
                "text": {
                    "body": content
                }
            }
            
            # Add template support if specified
            if kwargs.get('template_name'):
                message_data = {
                    "messaging_product": "whatsapp", 
                    "to": clean_to,
                    "type": "template",
                    "template": {
                        "name": kwargs['template_name'],
                        "language": {"code": kwargs.get('language_code', 'en_US')},
                        "components": kwargs.get('template_components', [])
                    }
                }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=message_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get('messages', [{}])[0].get('id', '')
                        logger.info(f"✅ Message sent to {clean_to}, ID: {message_id}")
                        return message_id
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to send message: {response.status} - {error_text}")
                        return ""
                        
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            return ""
    
    async def send_voice_message(self, to_number: str, audio_data: bytes, **kwargs) -> str:
        """Send voice message via WhatsApp Cloud API"""
        try:
            # First upload the audio file
            media_id = await self._upload_media(audio_data, "audio/mp3")
            if not media_id:
                return ""
            
            # Clean phone number
            clean_to = to_number.replace('+', '').replace(' ', '').replace('-', '')
            
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Voice message payload
            message_data = {
                "messaging_product": "whatsapp",
                "to": clean_to,
                "type": "audio",
                "audio": {
                    "id": media_id
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=message_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get('messages', [{}])[0].get('id', '')
                        logger.info(f"✅ Voice message sent to {clean_to}, ID: {message_id}")
                        return message_id
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to send voice message: {response.status} - {error_text}")
                        return ""
                        
        except Exception as e:
            logger.error(f"Error sending voice message: {e}")
            return ""
    
    async def _upload_media(self, media_data: bytes, mime_type: str) -> str:
        """Upload media to WhatsApp Cloud API"""
        try:
            url = f"{self.base_url}/{self.phone_number_id}/media"
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            # Create form data
            data = aiohttp.FormData()
            data.add_field('messaging_product', 'whatsapp')
            data.add_field('file', media_data, filename='audio.mp3', content_type=mime_type)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        media_id = result.get('id', '')
                        logger.info(f"✅ Media uploaded, ID: {media_id}")
                        return media_id
                    else:
                        error_text = await response.text()
                        logger.error(f"Media upload failed: {response.status} - {error_text}")
                        return ""
                        
        except Exception as e:
            logger.error(f"Error uploading media: {e}")
            return ""
    
    async def send_call_button_message(self, to_number: str, message_text: str = None, **kwargs) -> Dict[str, Any]:
        """Send interactive call button message (much more practical than direct calling)"""
        try:
            # Validate calling eligibility
            validation_result = await self._validate_calling_eligibility(to_number)
            if not validation_result["eligible"]:
                return {
                    "success": False,
                    "error": validation_result["reason"],
                    "status": "validation_failed"
                }
            
            clean_to = to_number.replace('+', '').replace(' ', '').replace('-', '')
            
            url = f"{self.base_url}/{self.phone_number_id}/messages"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Interactive call button message payload (based on official documentation)
            call_button_data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual", 
                "to": clean_to,
                "type": "interactive",
                "interactive": {
                    "type": "voice_call",
                    "body": {
                        "text": message_text or "You can call us on WhatsApp now for faster service!"
                    },
                    "action": {
                        "name": "voice_call",
                        "parameters": {
                            "display_text": kwargs.get('button_text', 'Call Now')[:20],  # Max 20 chars
                            "ttl_minutes": kwargs.get('ttl_minutes', 10080)  # Default: 7 days
                        }
                    }
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=call_button_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        message_id = result.get('messages', [{}])[0].get('id', '')
                        logger.info(f"✅ Call button message sent to {clean_to}, Message ID: {message_id}")
                        
                        # Log call button attempt for tracking
                        await self._log_call_attempt(clean_to, message_id, "call_button_sent")
                        
                        return {
                            "success": True,
                            "message_id": message_id,
                            "to_number": clean_to,
                            "status": "call_button_sent",
                            "sent_at": datetime.now().isoformat(),
                            "type": "call_button_message"
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Call button message failed: {response.status} - {error_text}")
                        
                        # Log failed attempt
                        await self._log_call_attempt(clean_to, None, "call_button_failed", error_text)
                        
                        return {
                            "success": False,
                            "error": error_text,
                            "status": "api_failed",
                            "http_status": response.status
                        }
                        
        except Exception as e:
            logger.error(f"Error sending call button message: {e}")
            await self._log_call_attempt(to_number, None, "error", str(e))
            return {
                "success": False,
                "error": str(e),
                "status": "error"
            }

    async def initiate_call(self, to_number: str, **kwargs) -> Dict[str, Any]:
        """
        Initiate direct WhatsApp call using Meta's Calling API
        Requires WebRTC SDP offer and 1,000+ message volume eligibility
        """
        try:
            # Comprehensive eligibility check
            eligibility = await self._validate_calling_eligibility(to_number)
            if not eligibility["eligible"]:
                return {
                    "success": False,
                    "error": eligibility["reason"],
                    "status": "not_eligible",
                    "eligibility_details": eligibility
                }
            
            # Generate WebRTC SDP offer
            sdp_offer = kwargs.get('sdp_offer')
            if not sdp_offer:
                # Generate basic SDP offer for voice calling
                sdp_offer = await self._generate_sdp_offer()
                if not sdp_offer:
                    return {
                        "success": False,
                        "error": "Failed to generate WebRTC SDP offer",
                        "status": "sdp_generation_failed"
                    }
            
            clean_to = to_number.replace('+', '').replace(' ', '').replace('-', '')
            
            url = f"{self.base_url}/{self.phone_number_id}/calls"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Direct call payload according to Meta documentation
            call_data = {
                "to": clean_to,
                "from": self.phone_number_id,
                "sdp": {
                    "type": "offer",
                    "sdp": sdp_offer
                },
                "audio": {
                    "codec": "opus",
                    "sample_rate": 48000
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=call_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        call_id = result.get('call_id')
                        
                        logger.info(f"✅ Direct call initiated to {clean_to}, Call ID: {call_id}")
                        
                        # Log call initiation
                        await self._log_call_attempt(clean_to, call_id, "direct_call_initiated")
                        
                        return {
                            "success": True,
                            "call_id": call_id,
                            "to_number": clean_to,
                            "status": "call_initiated",
                            "type": "direct_call",
                            "sdp_answer_expected": True,
                            "initiated_at": datetime.now().isoformat()
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Direct call failed: {response.status} - {error_text}")
                        
                        # Check for specific errors
                        if "messaging limit" in error_text.lower():
                            await self._log_calling_restriction("insufficient_volume", error_text)
                        
                        return {
                            "success": False,
                            "error": error_text,
                            "status": "call_failed",
                            "http_status": response.status
                        }
                        
        except Exception as e:
            logger.error(f"Error initiating direct call: {e}")
            return {
                "success": False,
                "error": str(e),
                "status": "error"
            }
    
    async def _generate_sdp_offer(self) -> str:
        """Generate WebRTC SDP offer for voice calling"""
        try:
            # Basic SDP offer template for voice calling
            # In production, use proper WebRTC library
            sdp_template = f"""v=0
o=- {int(datetime.now().timestamp())} 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=msid-semantic: WMS
m=audio 9 UDP/TLS/RTP/SAVPF 111 103 104 9 0 8 106 105 13 110 112 113 126
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:4ZcD
a=ice-pwd:2/1muCWoOi3uHTWmSqs7rJQJoy
a=ice-options:trickle
a=fingerprint:sha-256 20:14:7E:78:3C:15:A2:85:C0:4B:72:4C:96:E6:74:62:C2:28:35:75:97:38:76:37:4C:F0:81:53:E2:DD:18:91
a=setup:actpass
a=mid:0
a=extmap:1 urn:ietf:params:rtp-hdrext:ssrc-audio-level
a=extmap:2 http://www.webrtc.org/experiments/rtp-hdrext/abs-send-time
a=extmap:3 http://www.ietf.org/id/draft-holmer-rmcat-transport-wide-cc-extensions-01
a=extmap:4 urn:ietf:params:rtp-hdrext:sdes:mid
a=extmap:5 urn:ietf:params:rtp-hdrext:sdes:rtp-stream-id
a=extmap:6 urn:ietf:params:rtp-hdrext:sdes:repaired-rtp-stream-id
a=sendrecv
a=msid:- a0
a=rtcp-mux
a=rtpmap:111 opus/48000/2
a=rtcp-fb:111 transport-cc
a=fmtp:111 minptime=10;useinbandfec=1
a=rtpmap:103 ISAC/16000
a=rtpmap:104 ISAC/32000
a=rtpmap:9 G722/8000
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=rtpmap:106 CN/32000
a=rtpmap:105 CN/16000
a=rtpmap:13 CN/8000
a=rtpmap:110 telephone-event/48000
a=rtpmap:112 telephone-event/32000
a=rtpmap:113 telephone-event/16000
a=rtpmap:126 telephone-event/8000
a=ssrc:1001 cname:CNAME
"""
            return sdp_template.strip()
            
        except Exception as e:
            logger.error(f"Error generating SDP offer: {e}")
            return ""
    
    async def handle_incoming_message(self, message_data: Dict[str, Any]) -> WhatsAppCloudMessage:
        """Parse incoming WhatsApp Cloud API message"""
        try:
            # Extract message fields from webhook payload
            entry = message_data.get('entry', [{}])[0]
            changes = entry.get('changes', [{}])[0]
            value = changes.get('value', {})
            
            # Get message details
            messages = value.get('messages', [])
            if not messages:
                raise ValueError("No messages in webhook payload")
            
            message = messages[0]
            
            from_number = message.get('from', '')
            message_id = message.get('id', '')
            message_type = message.get('type', 'text')
            timestamp = message.get('timestamp', str(int(datetime.now().timestamp())))
            
            # Extract content based on message type
            content = ""
            if message_type == 'text':
                content = message.get('text', {}).get('body', '')
            elif message_type == 'audio':
                content = "[Voice Message]"
            elif message_type == 'image':
                content = "[Image]"
            elif message_type == 'document':
                content = "[Document]"
            
            # Create conversation ID
            conversation_id = f"wa_{from_number}_{self.customer_id}"
            
            return WhatsAppCloudMessage(
                content=content,
                from_number=from_number,
                to_number=self.phone_number_id,
                message_id=message_id,
                conversation_id=conversation_id,
                customer_id=self.customer_id,
                message_type=message_type,
                webhook_data=message_data
            )
            
        except Exception as e:
            logger.error(f"Failed to parse incoming WhatsApp message: {e}")
            raise
    
    async def validate_webhook_signature(self, payload: str, signature: str) -> bool:
        """Validate WhatsApp webhook signature"""
        if not self.webhook_secret:
            logger.warning("No webhook secret configured")
            return True
        
        try:
            # WhatsApp uses SHA256 HMAC
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # WhatsApp sends signature as sha256=<hash>
            signature = signature.replace('sha256=', '')
            
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            logger.error(f"Webhook signature validation failed: {e}")
            return False
    
    def verify_webhook_token(self, token: str) -> bool:
        """Verify webhook verification token"""
        return token == self.verify_token
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for WhatsApp Cloud API"""
        base_health = await super().health_check()
        
        # Test API connection
        api_healthy = await self._test_api_connection()
        
        base_health.update({
            "api_healthy": api_healthy,
            "phone_number_id": self.phone_number_id,
            "calling_enabled": self.calling_enabled,
            "business_hours": self.business_hours,
            "api_version": "v18.0"
        })
        
        return base_health
    
    async def _validate_calling_eligibility(self, to_number: str) -> Dict[str, Any]:
        """Validate if calling is eligible for this number with comprehensive checks"""
        try:
            # Check if WhatsApp Business Account has calling enabled
            if not self.calling_enabled:
                return {
                    "eligible": False,
                    "reason": "Calling is disabled for this account"
                }
            
            # Check business-level calling eligibility (Meta's requirements)
            business_eligibility = await self._check_calling_eligibility()
            if not business_eligibility["eligible"]:
                return business_eligibility
            
            # Check messaging volume requirement
            volume_check = await self._check_messaging_volume()
            if not volume_check["sufficient"]:
                return {
                    "eligible": False,
                    "reason": f"Insufficient messaging volume: {volume_check['current']}/1000 required",
                    "requirements": "Need 1,000+ business-initiated conversations in rolling 24-hour period",
                    "volume_data": volume_check
                }
            
            # Geographic restrictions check
            clean_number = to_number.replace('+', '').replace(' ', '').replace('-', '')
            country_code = self._get_country_code(clean_number)
            restricted_countries = ['CN', 'RU']  # Example restricted countries
            
            if country_code in restricted_countries:
                return {
                    "eligible": False,
                    "reason": f"Calling not available in country: {country_code}"
                }
            
            # Check user call permissions for this number
            user_permissions = await self._check_user_call_permissions(clean_number)
            if not user_permissions["permitted"]:
                return {
                    "eligible": False,
                    "reason": f"User permissions required: {user_permissions['reason']}",
                    "permission_status": user_permissions
                }
            
            return {
                "eligible": True,
                "reason": "All calling requirements met",
                "volume_sufficient": True,
                "permissions_granted": True
            }
            
        except Exception as e:
            logger.error(f"Error validating calling eligibility: {e}")
            return {
                "eligible": False,
                "reason": f"Validation error: {str(e)}"
            }
    
    async def _check_messaging_volume(self) -> Dict[str, Any]:
        """Check if business meets 1,000+ messages in 24hrs requirement"""
        try:
            # Note: Meta doesn't provide a direct API to check message volume
            # This would need to be tracked internally or estimated
            
            # For now, we'll make a reasonable assumption based on account status
            # In production, implement proper tracking of business-initiated conversations
            
            # Check account status and quality rating as proxy indicators
            url = f"{self.base_url}/{self.phone_number_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        quality_rating = data.get('quality_rating', 'UNKNOWN')
                        
                        # GREEN quality rating often indicates good message volume
                        if quality_rating == 'GREEN':
                            return {
                                "sufficient": True,
                                "estimated": True,
                                "current": "1000+",
                                "indicator": "GREEN quality rating suggests good volume",
                                "method": "quality_rating_proxy"
                            }
                        else:
                            return {
                                "sufficient": False,
                                "estimated": True,
                                "current": "<1000",
                                "indicator": f"Quality rating {quality_rating} suggests low volume",
                                "method": "quality_rating_proxy",
                                "recommendation": "Increase business-initiated conversations"
                            }
                    else:
                        return {
                            "sufficient": False,
                            "current": "unknown",
                            "error": "Cannot verify message volume",
                            "recommendation": "Verify account status"
                        }
                        
        except Exception as e:
            logger.error(f"Error checking messaging volume: {e}")
            return {
                "sufficient": False,
                "current": "unknown",
                "error": str(e)
            }
    
    async def _check_user_call_permissions(self, phone_number: str) -> Dict[str, Any]:
        """Check if user has granted call permissions"""
        try:
            # Note: Meta doesn't provide API to check individual user permissions
            # This would need to be tracked based on webhook responses
            
            # For now, assume permission is needed (conservative approach)
            # In production, track permission grants/denials from webhooks
            
            return {
                "permitted": False,  # Conservative default
                "reason": "Call permission required from user",
                "status": "permission_needed",
                "validity": "7_days_if_granted",
                "request_limit": "1 per 24 hours, 2 per 7 days",
                "method": "conservative_default"
            }
            
        except Exception as e:
            logger.error(f"Error checking user call permissions: {e}")
            return {
                "permitted": False,
                "reason": f"Permission check failed: {str(e)}",
                "error": True
            }
    
    def _get_country_code(self, phone_number: str) -> str:
        """Get country code from phone number"""
        # Simplified country code detection
        # In production, use a proper phone number parsing library
        if phone_number.startswith('1'):
            return 'US'  # US/Canada
        elif phone_number.startswith('44'):
            return 'GB'  # UK
        elif phone_number.startswith('49'):
            return 'DE'  # Germany
        elif phone_number.startswith('33'):
            return 'FR'  # France
        else:
            return 'UNKNOWN'
    
    def _is_within_business_hours(self) -> bool:
        """Check if current time is within business hours"""
        try:
            # If business_hours is None, calling is available 24/7
            if self.business_hours is None:
                return True
                
            if not self.business_hours:
                return True  # Always available if no hours configured
            
            # Get current time in business timezone
            business_tz = timezone(self.business_hours.get('timezone', 'UTC'))
            current_time = datetime.now(business_tz)
            current_day = current_time.strftime('%A').lower()
            current_hour_minute = current_time.strftime('%H:%M')
            
            # Check if current day has business hours
            day_hours = self.business_hours.get('hours', {}).get(current_day)
            if not day_hours:
                logger.info(f"No business hours configured for {current_day}")
                return False  # No business hours for this day
            
            start_time = day_hours.get('start', '09:00')
            end_time = day_hours.get('end', '17:00')
            
            # Simple time comparison (assumes same day)
            is_within_hours = start_time <= current_hour_minute <= end_time
            
            if not is_within_hours:
                logger.info(f"Outside business hours: {current_hour_minute} not between {start_time} and {end_time} on {current_day}")
            
            return is_within_hours
            
        except Exception as e:
            logger.error(f"Error checking business hours: {e}")
            return True  # Default to available on error
    
    async def _log_call_attempt(self, to_number: str, call_id: Optional[str], 
                              status: str, error: Optional[str] = None):
        """Log call attempt for tracking and analytics"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "customer_id": self.customer_id,
                "to_number": to_number,
                "call_id": call_id,
                "status": status,
                "error": error
            }
            
            # Log to file/database/analytics service
            logger.info(f"Call log: {json.dumps(log_entry)}")
            
            # TODO: Store in database for analytics
            
        except Exception as e:
            logger.error(f"Error logging call attempt: {e}")
    
    async def get_call_status(self, call_id: str) -> Dict[str, Any]:
        """Get status of a WhatsApp call"""
        try:
            url = f"{self.base_url}/calls/{call_id}"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Call status retrieved for {call_id}")
                        return {
                            "success": True,
                            "status": result.get('status', 'unknown'),
                            "duration": result.get('duration', 0),
                            "call_data": result
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to get call status: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": error_text
                        }
                        
        except Exception as e:
            logger.error(f"Error getting call status: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """End an active WhatsApp call"""
        try:
            url = f"{self.base_url}/calls/{call_id}/end"
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Call {call_id} ended successfully")
                        return {
                            "success": True,
                            "call_id": call_id,
                            "status": "ended"
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to end call: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": error_text
                        }
                        
        except Exception as e:
            logger.error(f"Error ending call: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Webhook handler for WhatsApp Cloud API
async def handle_whatsapp_webhook(request_data: Dict[str, Any], customer_id: str) -> Dict[str, Any]:
    """Handle incoming WhatsApp webhook"""
    try:
        # Initialize channel
        channel = WhatsAppCloudAPIChannel(customer_id)
        
        # Parse message
        message = await channel.handle_incoming_message(request_data)
        
        # Process with EA (this would integrate with your EA system)
        response = await process_with_ea(message)
        
        # Send response
        if response:
            await channel.send_message(message.from_number, response)
        
        return {"status": "success", "message_id": message.message_id}
        
    except Exception as e:
        logger.error(f"Webhook handling failed: {e}")
        return {"status": "error", "error": str(e)}

async def process_with_ea(message: WhatsAppCloudMessage) -> str:
    """Process message with Executive Assistant"""
    try:
        from ..agents.executive_assistant import ExecutiveAssistant, ConversationChannel
        
        # Initialize EA for customer
        ea = ExecutiveAssistant(customer_id=message.customer_id)
        
        # Process message
        response = await ea.handle_customer_interaction(
            message.content,
            ConversationChannel.WHATSAPP
        )
        
        return response
        
    except Exception as e:
        logger.error(f"EA processing failed: {e}")
        return "I'm having trouble processing your message right now. Please try again in a moment."