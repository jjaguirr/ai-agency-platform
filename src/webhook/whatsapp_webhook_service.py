#!/usr/bin/env python3
"""
Centralized WhatsApp Business API Webhook Service
Routes messages to client EA deployments via MCP protocol
"""

import asyncio
import logging
import json
import hmac
import hashlib
import requests
import aiohttp
import redis
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import sys
from pathlib import Path
import ipaddress
from dataclasses import dataclass
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import base64

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from webhook.monitoring import webhook_monitor, monitoring_bp, monitor_webhook_request
from webhook.meta_business_api import meta_business_api
from communication.voice_integration import VoiceIntegration

logger = logging.getLogger(__name__)

# Flask app for webhook
app = Flask(__name__, template_folder='templates')

# Register monitoring blueprint
app.register_blueprint(monitoring_bp)

# Rate limiting configuration will be set up after Redis client initialization

# WhatsApp Business API IP ranges for allowlisting
WHATSAPP_IP_RANGES = [
    "31.13.24.0/21",
    "31.13.64.0/18",
    "45.64.40.0/22",
    "66.220.144.0/20",
    "69.63.176.0/20",
    "69.171.224.0/19",
    "74.119.76.0/22",
    "103.4.96.0/22",
    "129.134.0.0/17",
    "157.240.0.0/17",
    "173.252.64.0/18",
    "179.60.192.0/22",
    "185.60.216.0/22",
    "204.15.20.0/22"
]

# WhatsApp configuration
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')
ACCESS_TOKEN = os.getenv('WHATSAPP_BUSINESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')
WEBHOOK_SECRET = os.getenv('WHATSAPP_WEBHOOK_SECRET', '')

# Meta Embedded Signup configuration
META_APP_ID = os.getenv('META_APP_ID', '')
META_APP_SECRET = os.getenv('META_APP_SECRET', '')
META_WEBHOOK_VERIFY_TOKEN = os.getenv('META_WEBHOOK_VERIFY_TOKEN', 'meta_embedded_signup_verify')
META_API_VERSION = os.getenv('META_API_VERSION', 'v20.0')
META_BUSINESS_TOKEN_TTL = int(os.getenv('META_BUSINESS_TOKEN_TTL', '5184000'))  # 60 days default

# Security configuration
PRODUCTION_MODE = os.getenv('FLASK_ENV', 'development') == 'production'
ENABLE_IP_ALLOWLIST = os.getenv('ENABLE_IP_ALLOWLIST', 'true').lower() == 'true'
ENFORCE_WEBHOOK_SECRET = os.getenv('ENFORCE_WEBHOOK_SECRET', 'true').lower() == 'true'

# Redis connection for client EA registry
redis_client = None
redis_available = False
try:
    if os.getenv('REDIS_URL'):
        redis_client = redis.from_url(os.getenv('REDIS_URL'))
        redis_client.ping()  # Test connection
        redis_available = True
        logger.info("✅ Redis connection established")
except Exception as e:
    logger.warning(f"Redis connection failed: {e}")
    redis_client = None
    redis_available = False

# Voice integration
voice_integration = None
if os.getenv('ELEVENLABS_API_KEY'):
    try:
        voice_integration = VoiceIntegration()
    except Exception as e:
        logger.warning(f"Voice integration initialization failed: {e}")

# Rate limiting configuration - use Redis in production
# Set up after Redis client initialization
rate_limit_storage_uri = 'memory://'
if redis_available:
    rate_limit_storage_uri = os.getenv('REDIS_URL')
    logger.info("✅ Using Redis for rate limiting")
else:
    logger.info("⚠️ Using in-memory storage for rate limiting (Redis not available)")

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri=rate_limit_storage_uri,
    swallow_errors=True  # Don't crash if rate limiting fails
)

@dataclass
class EAClient:
    """EA client registration information with Meta WABA integration"""
    client_id: str
    customer_id: str
    phone_number: str
    mcp_endpoint: str
    auth_token: str
    active: bool = True
    last_seen: Optional[datetime] = None

    # Meta Embedded Signup integration fields
    waba_id: Optional[str] = None
    business_phone_number_id: Optional[str] = None
    business_id: Optional[str] = None
    meta_business_token: Optional[str] = None
    meta_token_expires: Optional[datetime] = None
    embedded_signup_completed: bool = False
    meta_app_id: Optional[str] = None
    meta_webhook_token: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'client_id': self.client_id,
            'customer_id': self.customer_id,
            'phone_number': self.phone_number,
            'mcp_endpoint': self.mcp_endpoint,
            'auth_token': self.auth_token,
            'active': self.active,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'waba_id': self.waba_id,
            'business_phone_number_id': self.business_phone_number_id,
            'business_id': self.business_id,
            'meta_business_token': self._encrypt_token(self.meta_business_token) if self.meta_business_token else None,
            'meta_token_expires': self.meta_token_expires.isoformat() if self.meta_token_expires else None,
            'embedded_signup_completed': self.embedded_signup_completed,
            'meta_app_id': self.meta_app_id,
            'meta_webhook_token': self.meta_webhook_token
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EAClient':
        last_seen = None
        if data.get('last_seen'):
            last_seen = datetime.fromisoformat(data['last_seen'])

        meta_token_expires = None
        if data.get('meta_token_expires'):
            meta_token_expires = datetime.fromisoformat(data['meta_token_expires'])

        return cls(
            client_id=data['client_id'],
            customer_id=data['customer_id'],
            phone_number=data['phone_number'],
            mcp_endpoint=data['mcp_endpoint'],
            auth_token=data['auth_token'],
            active=data.get('active', True),
            last_seen=last_seen,
            waba_id=data.get('waba_id'),
            business_phone_number_id=data.get('business_phone_number_id'),
            business_id=data.get('business_id'),
            meta_business_token=cls._decrypt_token(data.get('meta_business_token')) if data.get('meta_business_token') else None,
            meta_token_expires=meta_token_expires,
            embedded_signup_completed=data.get('embedded_signup_completed', False),
            meta_app_id=data.get('meta_app_id'),
            meta_webhook_token=data.get('meta_webhook_token')
        )

    def _encrypt_token(self, token: str) -> str:
        """Encrypt Meta business token for secure storage"""
        if not token:
            return token

        key = os.getenv('META_TOKEN_ENCRYPTION_KEY', 'default-key-change-in-prod!!').encode()[:32]
        key = key.ljust(32, b'0')  # Pad to 32 bytes if shorter

        cipher = AES.new(key, AES.MODE_CBC)
        encrypted = cipher.encrypt(pad(token.encode(), AES.block_size))

        # Combine IV and encrypted data
        encrypted_data = cipher.iv + encrypted
        return base64.b64encode(encrypted_data).decode()

    @classmethod
    def _decrypt_token(cls, encrypted_token: str) -> Optional[str]:
        """Decrypt Meta business token from storage"""
        if not encrypted_token:
            return encrypted_token

        try:
            key = os.getenv('META_TOKEN_ENCRYPTION_KEY', 'default-key-change-in-prod!!').encode()[:32]
            key = key.ljust(32, b'0')  # Pad to 32 bytes if shorter

            encrypted_data = base64.b64decode(encrypted_token.encode())

            # Extract IV and encrypted content
            iv = encrypted_data[:16]
            encrypted_content = encrypted_data[16:]

            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(encrypted_content), AES.block_size)

            return decrypted.decode()
        except Exception as e:
            logger.error(f"Error decrypting Meta token: {e}")
            return None

class EAClientRegistry:
    """Registry for managing EA client connections"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.local_cache = {}  # Fallback cache if Redis unavailable

    async def register_client(self, client: EAClient) -> bool:
        """Register an EA client with Meta WABA integration support"""
        try:
            client.last_seen = datetime.now()
            client_data = json.dumps(client.to_dict())

            # Store in Redis with comprehensive mappings
            if self.redis_client:
                pipeline = self.redis_client.pipeline()
                pipeline.set(f"ea_client:{client.client_id}", client_data, ex=86400)  # 24h expiry
                pipeline.set(f"phone_mapping:{client.phone_number}", client.client_id, ex=86400)

                # Add Meta WABA mappings if available
                if client.waba_id:
                    pipeline.set(f"waba_mapping:{client.waba_id}", client.client_id, ex=86400)
                if client.business_phone_number_id:
                    pipeline.set(f"business_phone_mapping:{client.business_phone_number_id}", client.client_id, ex=86400)

                pipeline.execute()

            # Store in local cache with comprehensive mappings
            self.local_cache[client.client_id] = client
            self.local_cache[f"phone:{client.phone_number}"] = client.client_id

            # Add Meta WABA mappings to local cache
            if client.waba_id:
                self.local_cache[f"waba:{client.waba_id}"] = client.client_id
            if client.business_phone_number_id:
                self.local_cache[f"business_phone:{client.business_phone_number_id}"] = client.client_id

            meta_status = "with Meta WABA integration" if client.embedded_signup_completed else "standard registration"
            logger.info(f"✅ EA client registered: {client.client_id} for {client.phone_number} ({meta_status})")
            return True

        except Exception as e:
            logger.error(f"Failed to register EA client: {e}")
            return False

    async def get_client_by_waba_id(self, waba_id: str) -> Optional[EAClient]:
        """Get EA client by WhatsApp Business Account ID"""
        try:
            client_id = None

            # Try Redis first
            if self.redis_client:
                client_id = self.redis_client.get(f"waba_mapping:{waba_id}")
                if client_id:
                    client_id = client_id.decode()

            # Try local cache
            if not client_id:
                client_id = self.local_cache.get(f"waba:{waba_id}")

            if client_id:
                return await self.get_client(client_id)

            return None

        except Exception as e:
            logger.error(f"Error getting client by WABA ID: {e}")
            return None

    async def get_client_by_business_phone_id(self, business_phone_number_id: str) -> Optional[EAClient]:
        """Get EA client by business phone number ID"""
        try:
            client_id = None

            # Try Redis first
            if self.redis_client:
                client_id = self.redis_client.get(f"business_phone_mapping:{business_phone_number_id}")
                if client_id:
                    client_id = client_id.decode()

            # Try local cache
            if not client_id:
                client_id = self.local_cache.get(f"business_phone:{business_phone_number_id}")

            if client_id:
                return await self.get_client(client_id)

            return None

        except Exception as e:
            logger.error(f"Error getting client by business phone ID: {e}")
            return None

    async def get_client_by_phone(self, phone_number: str) -> Optional[EAClient]:
        """Get EA client by phone number"""
        try:
            client_id = None

            # Try Redis first
            if self.redis_client:
                client_id = self.redis_client.get(f"phone_mapping:{phone_number}")
                if client_id:
                    client_id = client_id.decode()

            # Try local cache
            if not client_id:
                client_id = self.local_cache.get(f"phone:{phone_number}")

            if client_id:
                return await self.get_client(client_id)

            return None

        except Exception as e:
            logger.error(f"Error getting client by phone: {e}")
            return None

    async def get_client(self, client_id: str) -> Optional[EAClient]:
        """Get EA client by ID"""
        try:
            client_data = None

            # Try Redis first
            if self.redis_client:
                data = self.redis_client.get(f"ea_client:{client_id}")
                if data:
                    client_data = json.loads(data.decode())

            # Try local cache
            if not client_data and client_id in self.local_cache:
                client_data = self.local_cache[client_id].to_dict()

            if client_data:
                return EAClient.from_dict(client_data)

            return None

        except Exception as e:
            logger.error(f"Error getting client: {e}")
            return None

    async def unregister_client(self, client_id: str) -> bool:
        """Unregister an EA client"""
        try:
            # Get client to find phone number
            client = await self.get_client(client_id)
            if not client:
                return False

            # Remove from Redis
            if self.redis_client:
                pipeline = self.redis_client.pipeline()
                pipeline.delete(f"ea_client:{client_id}")
                pipeline.delete(f"phone_mapping:{client.phone_number}")
                pipeline.execute()

            # Remove from local cache
            self.local_cache.pop(client_id, None)
            self.local_cache.pop(f"phone:{client.phone_number}", None)

            logger.info(f"✅ EA client unregistered: {client_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to unregister EA client: {e}")
            return False

    async def list_active_clients(self) -> List[EAClient]:
        """List all active EA clients"""
        clients = []
        try:
            if self.redis_client:
                # Get all client keys from Redis
                keys = self.redis_client.keys("ea_client:*")
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        client_data = json.loads(data.decode())
                        client = EAClient.from_dict(client_data)
                        if client.active:
                            clients.append(client)
            else:
                # Use local cache
                for key, value in self.local_cache.items():
                    if isinstance(value, EAClient) and value.active:
                        clients.append(value)

            return clients

        except Exception as e:
            logger.error(f"Error listing clients: {e}")
            return []

# Global client registry
ea_registry = EAClientRegistry(redis_client)

@app.after_request
def set_security_headers(response):
    """Add security headers to response"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'"
    return response

@app.before_request
def before_request():
    """Security middleware for all requests"""
    # IP allowlisting for webhook endpoints
    if request.endpoint and 'webhook' in request.endpoint:
        if ENABLE_IP_ALLOWLIST and not is_allowed_ip(request.remote_addr):
            logger.warning(f"🚫 Blocked request from unauthorized IP: {request.remote_addr}")
            return jsonify({"error": "Unauthorized IP address"}), 403

def is_allowed_ip(client_ip: str) -> bool:
    """Check if client IP is in WhatsApp Business API allowlist"""
    try:
        if not client_ip or client_ip in ['127.0.0.1', 'localhost']:
            return True  # Allow local development

        client_addr = ipaddress.ip_address(client_ip)

        for ip_range in WHATSAPP_IP_RANGES:
            if client_addr in ipaddress.ip_network(ip_range):
                return True

        return False

    except Exception as e:
        logger.error(f"IP validation error: {e}")
        return False  # Deny on error

@app.route('/webhook/whatsapp', methods=['GET'])
@limiter.limit("10 per minute")
@monitor_webhook_request
def verify_webhook():
    """Verify webhook for WhatsApp"""
    try:
        # Parse verification request
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        logger.info(f"🔍 Webhook verification: mode={mode}, token={'✓' if token == VERIFY_TOKEN else '✗'}")

        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("✅ Webhook verified successfully")
            return challenge, 200
        else:
            logger.error(f"❌ Webhook verification failed: invalid token")
            return 'Forbidden', 403

    except Exception as e:
        logger.error(f"Webhook verification error: {e}")
        return 'Error', 500

@app.route('/webhook/whatsapp', methods=['POST'])
@limiter.limit("60 per minute")
@monitor_webhook_request
def handle_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        # Get request data
        data = request.get_json()

        logger.info(f"📱 Incoming webhook data received")
        logger.debug(f"Webhook payload: {json.dumps(data, indent=2)}")

        # Validate webhook signature (REQUIRED in production)
        signature = request.headers.get('X-Hub-Signature-256', '')
        if ENFORCE_WEBHOOK_SECRET or PRODUCTION_MODE:
            if not WEBHOOK_SECRET:
                logger.error("🚨 WEBHOOK_SECRET not configured for production")
                return jsonify({"error": "Server configuration error"}), 500

            if not validate_signature(request.get_data(), signature):
                logger.warning(f"⚠️ Invalid webhook signature from IP: {request.remote_addr}")
                return jsonify({"error": "Invalid signature"}), 403

        # Process webhook data asynchronously
        asyncio.run(process_whatsapp_webhook(data))

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")
        return jsonify({"error": str(e)}), 500

def validate_signature(payload: bytes, signature: str) -> bool:
    """Validate webhook signature"""
    if not WEBHOOK_SECRET:
        return True  # Skip validation if no secret

    try:
        expected_signature = hmac.new(
            WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        signature = signature.replace('sha256=', '')
        return hmac.compare_digest(expected_signature, signature)

    except Exception as e:
        logger.error(f"Signature validation error: {e}")
        return False

async def process_whatsapp_webhook(data: Dict[str, Any]):
    """Process incoming WhatsApp webhook data"""
    try:
        # Extract message from webhook data
        entry = data.get('entry', [])
        if not entry:
            logger.debug("No entry in webhook data")
            return

        for entry_item in entry:
            changes = entry_item.get('changes', [])

            for change in changes:
                value = change.get('value', {})

                # Handle messages
                messages = value.get('messages', [])
                for message in messages:
                    await handle_incoming_message(message, value)

                # Handle message status updates
                statuses = value.get('statuses', [])
                for status in statuses:
                    await handle_message_status(status)

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")

async def handle_incoming_message(message: Dict[str, Any], value: Dict[str, Any]):
    """Handle a single incoming WhatsApp message with Meta integration support"""
    try:
        from_number = message.get('from', '')
        message_id = message.get('id', '')
        message_type = message.get('type', 'text')
        timestamp = message.get('timestamp', str(int(datetime.now().timestamp())))

        # Extract Meta webhook metadata
        metadata = value.get('metadata', {})
        business_phone_number_id = metadata.get('phone_number_id')
        display_phone_number = metadata.get('display_phone_number')

        # Get message content based on type
        content = ""
        if message_type == 'text':
            content = message.get('text', {}).get('body', '')
        elif message_type == 'audio':
            # We'll find the client first, then process voice message with context
            temp_client = None
            if business_phone_number_id:
                temp_client = await ea_registry.get_client_by_business_phone_id(business_phone_number_id)
            if not temp_client:
                temp_client = await ea_registry.get_client_by_phone(from_number)

            content = await process_voice_message(message, temp_client)
        elif message_type == 'image':
            content = "[Image received]"
            # TODO: Process image with AI vision
        elif message_type == 'document':
            content = "[Document received]"
            # TODO: Process document
        else:
            content = f"[{message_type.title()} message received]"

        logger.info(f"📨 Message from {from_number} (via {display_phone_number}): {content[:100]}{'...' if len(content) > 100 else ''}")

        # Find EA client using multiple lookup strategies
        ea_client = None

        # 1. Try lookup by business phone number ID (Meta integration)
        if business_phone_number_id:
            ea_client = await ea_registry.get_client_by_business_phone_id(business_phone_number_id)
            if ea_client:
                logger.info(f"🔍 Found EA client via business phone number ID: {business_phone_number_id}")

        # 2. Fallback to traditional phone number lookup
        if not ea_client:
            ea_client = await ea_registry.get_client_by_phone(from_number)
            if ea_client:
                logger.info(f"🔍 Found EA client via phone number: {from_number}")

        if ea_client and content and content.strip():
            # Route to EA client via MCP with Meta context
            ea_response = await route_to_ea_client(ea_client, content, message_id, message_type)

            # Send response back using appropriate method
            if ea_response:
                # Use Meta API if client has Meta integration, otherwise fallback
                if ea_client.embedded_signup_completed and ea_client.meta_business_token:
                    sent_via_meta = await send_via_meta_api(ea_client, from_number, ea_response)
                    if not sent_via_meta:
                        # Fallback to legacy method
                        await send_whatsapp_response(from_number, ea_response)
                else:
                    await send_whatsapp_response(from_number, ea_response)
        else:
            # No registered EA client - send instruction message
            await send_registration_message(from_number)

    except Exception as e:
        logger.error(f"Error handling message: {e}")

async def route_to_ea_client(client: EAClient, message: str, message_id: str, message_type: str) -> Optional[str]:
    """Route message to EA client via MCP with Meta integration support"""
    try:
        logger.info(f"🔗 Routing message to EA client: {client.client_id}")

        # Prepare MCP message with Meta integration details
        mcp_message = {
            "method": "handle_whatsapp_message",
            "params": {
                "message": message,
                "message_id": message_id,
                "message_type": message_type,
                "from_number": client.phone_number,
                "customer_id": client.customer_id,
                "timestamp": datetime.now().isoformat(),
                "meta_integration": {
                    "enabled": client.embedded_signup_completed,
                    "waba_id": client.waba_id,
                    "business_phone_number_id": client.business_phone_number_id,
                    "can_send_via_meta_api": bool(client.meta_business_token and client.embedded_signup_completed)
                }
            }
        }

        # Send to EA client via HTTP/MCP
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {client.auth_token}',
                'Content-Type': 'application/json'
            }

            try:
                async with session.post(
                    client.mcp_endpoint,
                    json=mcp_message,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:

                    if response.status == 200:
                        result = await response.json()
                        ea_response = result.get('result', {}).get('response')

                        logger.info(f"✅ EA response received: {len(ea_response)} characters")
                        return ea_response
                    else:
                        logger.error(f"❌ EA client error: {response.status}")
                        return "I'm having trouble processing your message right now."

            except asyncio.TimeoutError:
                logger.error(f"❌ EA client timeout: {client.client_id}")
                return "I'm taking a bit longer to process your message. Please wait a moment."
            except Exception as e:
                logger.error(f"❌ EA client communication error: {e}")
                return "I'm having trouble processing your message right now."

    except Exception as e:
        logger.error(f"Error routing to EA client: {e}")
        return "I'm experiencing technical difficulties. Please try again."

async def send_registration_message(to_number: str):
    """Send message to unregistered phone number"""
    message = (
        "👋 Hello! To use your AI Executive Assistant through WhatsApp, "
        "your business needs to register this phone number with your EA system. "
        "Please contact your administrator or visit our setup guide."
    )
    await send_text_response(to_number, message)

async def process_voice_message(message: Dict[str, Any], client: Optional[EAClient] = None) -> str:
    """Process voice message with speech-to-text and Meta integration support"""
    try:
        if not voice_integration:
            return "[Voice message - processing not available]"

        # Get audio data from WhatsApp API
        audio_id = message.get('audio', {}).get('id')
        if not audio_id:
            return "[Voice message - no audio ID]"

        # Download and process voice message with client context for Meta API
        audio_data = await download_whatsapp_media(audio_id, client)
        if audio_data:
            # Convert speech to text
            transcription = await voice_integration.speech_to_text(audio_data)
            integration_method = "Meta API" if (client and client.embedded_signup_completed) else "Legacy API"
            logger.info(f"🎤 Voice message transcribed via {integration_method}: {transcription}")
            return transcription or "[Voice message - transcription failed]"
        else:
            return "[Voice message - download failed]"

    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        return "[Voice message - processing error]"

async def download_whatsapp_media(media_id: str, client: Optional[EAClient] = None) -> Optional[bytes]:
    """Download media from WhatsApp Cloud API with Meta integration support"""
    try:
        # Try Meta API first if client has integration
        if client and client.meta_business_token and client.embedded_signup_completed:
            logger.info(f"📁 Downloading media via Meta API for client {client.client_id}")

            # Get media URL via Meta API
            media_url = await meta_business_api.get_media_url(client.meta_business_token, media_id)

            if media_url:
                # Download media via Meta API
                media_data = await meta_business_api.download_media(client.meta_business_token, media_url)
                if media_data:
                    logger.info(f"✅ Media downloaded via Meta API: {len(media_data)} bytes")
                    return media_data

            logger.warning(f"⚠️ Failed to download media via Meta API, falling back to legacy method")

        # Fallback to legacy WhatsApp Cloud API
        logger.info(f"📁 Downloading media via legacy WhatsApp API")

        url = f"https://graph.facebook.com/{META_API_VERSION}/{media_id}"
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            media_info = response.json()
            media_url = media_info.get('url')

            if media_url:
                # Download actual media
                media_response = requests.get(media_url, headers=headers)
                if media_response.status_code == 200:
                    logger.info(f"✅ Media downloaded via legacy API: {len(media_response.content)} bytes")
                    return media_response.content

        logger.error(f"❌ Failed to download media {media_id}")
        return None

    except Exception as e:
        logger.error(f"Error downloading media: {e}")
        return None

async def handle_message_status(status: Dict[str, Any]):
    """Handle message status updates (delivered, read, etc.)"""
    try:
        message_id = status.get('id', '')
        status_type = status.get('status', '')
        timestamp = status.get('timestamp', '')

        logger.debug(f"📊 Message {message_id} status: {status_type}")

        # TODO: Forward status updates to relevant EA clients

    except Exception as e:
        logger.error(f"Error handling status: {e}")

async def send_via_meta_api(client: EAClient, to_number: str, message: str) -> bool:
    """Send message via Meta Business API for clients with integration"""
    try:
        if not client.meta_business_token or not client.business_phone_number_id:
            logger.warning(f"⚠️ Meta API credentials missing for client {client.client_id}")
            return False

        # Check if token is still valid
        if client.meta_token_expires and client.meta_token_expires <= datetime.now():
            logger.warning(f"⚠️ Meta business token expired for client {client.client_id}")
            return False

        # Send via Meta Business API
        content = {"text": {"body": message}}
        message_id = await meta_business_api.send_message(
            client.meta_business_token,
            client.business_phone_number_id,
            to_number,
            "text",
            content
        )

        if message_id:
            logger.info(f"✅ Message sent via Meta API: {message_id}")
            return True
        else:
            logger.error(f"❌ Failed to send message via Meta API for client {client.client_id}")
            return False

    except Exception as e:
        logger.error(f"Error sending via Meta API: {e}")
        return False

async def send_whatsapp_response(to_number: str, message: str, voice_enabled: bool = False):
    """Send response back via WhatsApp (text or voice) - Legacy method"""
    try:
        # Check if voice response is requested and available
        if voice_enabled and voice_integration and len(message) < 500:
            await send_voice_response(to_number, message)
        else:
            await send_text_response(to_number, message)

    except Exception as e:
        logger.error(f"Error sending response: {e}")

async def send_text_response(to_number: str, message: str):
    """Send text response via WhatsApp"""
    try:
        # Clean phone number (remove + and spaces)
        clean_to = to_number.replace('+', '').replace(' ', '').replace('-', '')

        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }

        message_data = {
            "messaging_product": "whatsapp",
            "to": clean_to,
            "type": "text",
            "text": {"body": message}
        }

        response = requests.post(url, headers=headers, json=message_data)

        if response.status_code == 200:
            result = response.json()
            message_id = result.get('messages', [{}])[0].get('id', 'unknown')
            logger.info(f"✅ Text message sent to {clean_to}: {message_id}")
            return message_id
        else:
            logger.error(f"❌ Failed to send message: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"❌ Error sending text message: {e}")
        return None

async def send_voice_response(to_number: str, message: str):
    """Send voice response via WhatsApp"""
    try:
        if not voice_integration:
            # Fallback to text
            await send_text_response(to_number, message)
            return

        # Generate voice audio
        audio_data = await voice_integration.text_to_speech(message)
        if not audio_data:
            # Fallback to text
            await send_text_response(to_number, message)
            return

        # TODO: Implement voice message sending via WhatsApp API
        # For now, fallback to text
        await send_text_response(to_number, f"🎤 Voice: {message}")

    except Exception as e:
        logger.error(f"Error sending voice message: {e}")
        # Fallback to text
        await send_text_response(to_number, message)

# ==============================================
# META EMBEDDED SIGNUP ENDPOINTS
# ==============================================

@app.route('/embedded-signup/token-exchange', methods=['POST'])
@limiter.limit("10 per minute")
def exchange_meta_authorization_code():
    """Exchange Meta 30-second authorization code for business token"""
    try:
        data = request.get_json()

        required_fields = ['authorization_code', 'client_id', 'customer_id', 'mcp_endpoint', 'auth_token']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        authorization_code = data['authorization_code']
        client_id = data['client_id']
        customer_id = data['customer_id']
        mcp_endpoint = data['mcp_endpoint']
        auth_token = data['auth_token']

        logger.info(f"🔄 Processing Meta token exchange for client: {client_id}")

        # Exchange authorization code for business token (async operation)
        token_result = asyncio.run(meta_business_api.exchange_authorization_code(authorization_code))

        if not token_result.success:
            logger.error(f"❌ Meta token exchange failed for {client_id}: {token_result.error_message}")
            return jsonify({
                "error": "Token exchange failed",
                "message": token_result.error_message
            }), 400

        # Validate the token and get business info
        business_info = asyncio.run(meta_business_api.validate_business_token(token_result.access_token))

        if 'error' in business_info:
            return jsonify({
                "error": "Token validation failed",
                "message": business_info['error']
            }), 400

        # Get business accounts and WABA info
        business_accounts = asyncio.run(meta_business_api.get_business_accounts(token_result.access_token))

        if not business_accounts:
            return jsonify({
                "error": "No business accounts found",
                "message": "The connected account has no accessible business accounts"
            }), 400

        # Use the first business account (in production, might want to let user choose)
        primary_business = business_accounts[0]
        business_id = primary_business['id']

        # Get WhatsApp Business Accounts
        wabas = asyncio.run(meta_business_api.get_whatsapp_business_accounts(token_result.access_token, business_id))

        if not wabas:
            return jsonify({
                "error": "No WhatsApp Business Accounts found",
                "message": "The business account has no WhatsApp Business Accounts configured"
            }), 400

        # Use primary WABA and phone number
        primary_waba = wabas[0]
        waba_id = primary_waba.waba_id

        if not primary_waba.phone_numbers:
            return jsonify({
                "error": "No phone numbers configured",
                "message": "The WhatsApp Business Account has no phone numbers configured"
            }), 400

        primary_phone = primary_waba.phone_numbers[0]
        business_phone_number_id = primary_phone['id']
        display_phone_number = primary_phone.get('display_phone_number', '')

        # Calculate token expiry
        token_expires = None
        if token_result.expires_in:
            token_expires = datetime.now() + timedelta(seconds=token_result.expires_in)

        # Store the integration result temporarily (to be completed by register-client)
        integration_data = {
            'client_id': client_id,
            'customer_id': customer_id,
            'mcp_endpoint': mcp_endpoint,
            'auth_token': auth_token,
            'waba_id': waba_id,
            'business_phone_number_id': business_phone_number_id,
            'business_id': business_id,
            'meta_business_token': token_result.access_token,
            'meta_token_expires': token_expires.isoformat() if token_expires else None,
            'meta_app_id': META_APP_ID,
            'display_phone_number': display_phone_number,
            'waba_name': primary_waba.name,
            'business_name': primary_business.get('name', ''),
            'timestamp': datetime.now().isoformat()
        }

        # Store in Redis temporarily (30 minutes expiry for completion)
        if redis_client:
            redis_client.set(
                f"meta_integration_pending:{client_id}",
                json.dumps(integration_data),
                ex=1800  # 30 minutes
            )

        logger.info(f"✅ Meta token exchange completed successfully for {client_id}")

        return jsonify({
            "status": "success",
            "message": "Authorization code exchanged successfully",
            "integration_data": {
                "waba_id": waba_id,
                "business_phone_number_id": business_phone_number_id,
                "display_phone_number": display_phone_number,
                "waba_name": primary_waba.name,
                "business_name": primary_business.get('name', ''),
                "token_expires": token_expires.isoformat() if token_expires else None
            }
        }), 200

    except Exception as e:
        logger.error(f"❌ Error in Meta token exchange: {e}")
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

@app.route('/embedded-signup/register-client', methods=['POST'])
@limiter.limit("5 per minute")
def complete_meta_client_registration():
    """Complete Meta Embedded Signup client registration"""
    try:
        data = request.get_json()

        required_fields = ['client_id', 'phone_number']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        client_id = data['client_id']
        phone_number = data['phone_number']

        # Retrieve pending integration data
        integration_data = None
        if redis_client:
            stored_data = redis_client.get(f"meta_integration_pending:{client_id}")
            if stored_data:
                integration_data = json.loads(stored_data.decode())

        if not integration_data:
            return jsonify({
                "error": "Integration data not found",
                "message": "Token exchange must be completed first, or session has expired"
            }), 404

        # Parse token expiry
        meta_token_expires = None
        if integration_data.get('meta_token_expires'):
            meta_token_expires = datetime.fromisoformat(integration_data['meta_token_expires'])

        # Create EA client with Meta integration
        client = EAClient(
            client_id=client_id,
            customer_id=integration_data['customer_id'],
            phone_number=phone_number,
            mcp_endpoint=integration_data['mcp_endpoint'],
            auth_token=integration_data['auth_token'],
            waba_id=integration_data['waba_id'],
            business_phone_number_id=integration_data['business_phone_number_id'],
            business_id=integration_data['business_id'],
            meta_business_token=integration_data['meta_business_token'],
            meta_token_expires=meta_token_expires,
            meta_app_id=integration_data['meta_app_id'],
            embedded_signup_completed=True
        )

        # Subscribe to webhooks
        webhook_url = f"{request.url_root}webhook/whatsapp"
        webhook_subscribed = asyncio.run(meta_business_api.subscribe_to_webhooks(
            integration_data['meta_business_token'],
            integration_data['waba_id'],
            webhook_url,
            META_WEBHOOK_VERIFY_TOKEN
        ))

        if not webhook_subscribed:
            logger.warning(f"⚠️ Failed to subscribe webhooks for WABA {integration_data['waba_id']}")

        # Register client
        success = asyncio.run(ea_registry.register_client(client))

        if success:
            # Clean up pending data
            if redis_client:
                redis_client.delete(f"meta_integration_pending:{client_id}")

            # Notify EA client of successful WhatsApp integration
            asyncio.run(notify_ea_client_integration_complete(client, integration_data))

            logger.info(f"✅ Meta Embedded Signup completed for client: {client_id}")

            return jsonify({
                "status": "success",
                "message": "Meta WhatsApp integration completed successfully",
                "client_id": client_id,
                "integration_details": {
                    "waba_id": integration_data['waba_id'],
                    "business_phone_number_id": integration_data['business_phone_number_id'],
                    "display_phone_number": integration_data['display_phone_number'],
                    "webhook_subscribed": webhook_subscribed,
                    "registration_completed": True
                }
            }), 201
        else:
            return jsonify({"error": "Failed to register EA client"}), 500

    except Exception as e:
        logger.error(f"❌ Error completing Meta client registration: {e}")
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

@app.route('/embedded-signup/client-status/<client_id>', methods=['GET'])
@limiter.limit("10 per minute")
def get_meta_client_status(client_id: str):
    """Get Meta integration status for a client"""
    try:
        # Get client from registry
        client = asyncio.run(ea_registry.get_client(client_id))

        if not client:
            return jsonify({"error": "Client not found"}), 404

        # Check if Meta integration is complete
        meta_status = {
            "client_id": client.client_id,
            "embedded_signup_completed": client.embedded_signup_completed,
            "has_meta_integration": bool(client.waba_id and client.meta_business_token),
            "waba_id": client.waba_id,
            "business_phone_number_id": client.business_phone_number_id,
            "business_id": client.business_id,
            "meta_token_expires": client.meta_token_expires.isoformat() if client.meta_token_expires else None,
            "token_valid": client.meta_token_expires > datetime.now() if client.meta_token_expires else False,
            "active": client.active,
            "last_seen": client.last_seen.isoformat() if client.last_seen else None
        }

        # Check for pending integration
        pending_integration = None
        if redis_client and not client.embedded_signup_completed:
            stored_data = redis_client.get(f"meta_integration_pending:{client_id}")
            if stored_data:
                pending_data = json.loads(stored_data.decode())
                pending_integration = {
                    "token_exchange_completed": True,
                    "awaiting_registration": True,
                    "waba_id": pending_data.get('waba_id'),
                    "display_phone_number": pending_data.get('display_phone_number'),
                    "expires_at": pending_data.get('meta_token_expires')
                }

        return jsonify({
            "status": "success",
            "meta_integration_status": meta_status,
            "pending_integration": pending_integration
        }), 200

    except Exception as e:
        logger.error(f"Error getting Meta client status: {e}")
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

@app.route('/embedded-signup/revoke-client/<client_id>', methods=['DELETE'])
@limiter.limit("5 per minute")
def revoke_meta_client_integration(client_id: str):
    """Revoke Meta integration for a client"""
    try:
        # Get client from registry
        client = asyncio.run(ea_registry.get_client(client_id))

        if not client:
            return jsonify({"error": "Client not found"}), 404

        if not client.embedded_signup_completed:
            return jsonify({"error": "No Meta integration to revoke"}), 400

        # TODO: Implement token revocation via Meta API
        # For now, just disable the integration locally

        # Create updated client without Meta integration
        updated_client = EAClient(
            client_id=client.client_id,
            customer_id=client.customer_id,
            phone_number=client.phone_number,
            mcp_endpoint=client.mcp_endpoint,
            auth_token=client.auth_token,
            active=client.active,
            last_seen=client.last_seen,
            # Reset Meta fields
            waba_id=None,
            business_phone_number_id=None,
            business_id=None,
            meta_business_token=None,
            meta_token_expires=None,
            embedded_signup_completed=False,
            meta_app_id=None
        )

        # Re-register client without Meta integration
        success = asyncio.run(ea_registry.register_client(updated_client))

        if success:
            logger.info(f"✅ Meta integration revoked for client: {client_id}")

            return jsonify({
                "status": "success",
                "message": "Meta WhatsApp integration revoked successfully",
                "client_id": client_id
            }), 200
        else:
            return jsonify({"error": "Failed to update client registration"}), 500

    except Exception as e:
        logger.error(f"Error revoking Meta integration: {e}")
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

@app.route('/webhook/meta-deauth', methods=['POST'])
@limiter.limit("10 per minute")
def handle_meta_deauth():
    """Handle Meta app deauthorization webhook"""
    try:
        data = request.get_json()

        # Validate Meta webhook signature for deauth
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not meta_business_api.validate_webhook_signature(request.get_data(), signature):
            logger.warning("Invalid Meta deauth webhook signature")
            return jsonify({"error": "Invalid signature"}), 403

        logger.info(f"📲 Meta app deauthorization received: {json.dumps(data, indent=2)}")

        # TODO: Handle app deauthorization
        # - Find affected clients
        # - Disable Meta integration
        # - Notify clients

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Error handling Meta deauth: {e}")
        return jsonify({"error": "Internal server error"}), 500

async def notify_ea_client_integration_complete(client: EAClient, integration_data: Dict[str, Any]):
    """Notify EA client that WhatsApp integration is complete"""
    try:
        logger.info(f"🔔 Notifying EA client of successful WhatsApp integration: {client.client_id}")

        # Prepare MCP notification
        mcp_message = {
            "method": "whatsapp_integration_complete",
            "params": {
                "client_id": client.client_id,
                "waba_id": integration_data['waba_id'],
                "business_phone_number_id": integration_data['business_phone_number_id'],
                "display_phone_number": integration_data['display_phone_number'],
                "waba_name": integration_data['waba_name'],
                "business_name": integration_data['business_name'],
                "integration_completed_at": datetime.now().isoformat()
            }
        }

        # Send notification to EA client via MCP
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {client.auth_token}',
                'Content-Type': 'application/json'
            }

            try:
                async with session.post(
                    client.mcp_endpoint,
                    json=mcp_message,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:

                    if response.status == 200:
                        logger.info(f"✅ EA client notified successfully: {client.client_id}")
                    else:
                        logger.warning(f"⚠️ EA client notification failed: {response.status}")

            except asyncio.TimeoutError:
                logger.warning(f"⚠️ EA client notification timeout: {client.client_id}")
            except Exception as e:
                logger.warning(f"⚠️ EA client notification error: {e}")

    except Exception as e:
        logger.error(f"Error notifying EA client: {e}")

# ==============================================
# EA CLIENT MANAGEMENT API
# ==============================================
@app.route('/ea/register', methods=['POST'])
@limiter.limit("5 per minute")
def register_ea_client():
    """Register a new EA client"""
    try:
        data = request.get_json()

        required_fields = ['client_id', 'customer_id', 'phone_number', 'mcp_endpoint', 'auth_token']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        client = EAClient(
            client_id=data['client_id'],
            customer_id=data['customer_id'],
            phone_number=data['phone_number'],
            mcp_endpoint=data['mcp_endpoint'],
            auth_token=data['auth_token']
        )

        # Register client
        success = asyncio.run(ea_registry.register_client(client))

        if success:
            return jsonify({
                "status": "success",
                "message": "EA client registered successfully",
                "client_id": client.client_id
            }), 201
        else:
            return jsonify({"error": "Failed to register EA client"}), 500

    except Exception as e:
        logger.error(f"Error registering EA client: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/ea/unregister/<client_id>', methods=['DELETE'])
@limiter.limit("5 per minute")
def unregister_ea_client(client_id: str):
    """Unregister an EA client"""
    try:
        success = asyncio.run(ea_registry.unregister_client(client_id))

        if success:
            return jsonify({
                "status": "success",
                "message": "EA client unregistered successfully"
            }), 200
        else:
            return jsonify({"error": "EA client not found"}), 404

    except Exception as e:
        logger.error(f"Error unregistering EA client: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/ea/clients', methods=['GET'])
def list_ea_clients():
    """List all registered EA clients"""
    try:
        clients = asyncio.run(ea_registry.list_active_clients())

        return jsonify({
            "status": "success",
            "clients": [
                {
                    "client_id": client.client_id,
                    "customer_id": client.customer_id,
                    "phone_number": client.phone_number,
                    "active": client.active,
                    "last_seen": client.last_seen.isoformat() if client.last_seen else None
                }
                for client in clients
            ],
            "count": len(clients)
        }), 200

    except Exception as e:
        logger.error(f"Error listing EA clients: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for DigitalOcean App Platform"""
    try:
        # Try to get clients, but don't fail health check if registry fails
        clients = []
        try:
            clients = asyncio.run(ea_registry.list_active_clients())
        except Exception as client_error:
            logger.warning(f"Could not retrieve client list for health check: {client_error}")

        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "whatsapp-webhook-service",
            "version": "2.0.0",
            "environment": os.getenv('ENVIRONMENT', 'development')
        }

        # Basic health checks with Meta integration
        meta_clients_count = sum(1 for client in clients if client.embedded_signup_completed)
        legacy_clients_count = len(clients) - meta_clients_count

        checks = {
            "access_token": bool(ACCESS_TOKEN),
            "verify_token": bool(VERIFY_TOKEN),
            "phone_number_id": bool(PHONE_NUMBER_ID),
            "webhook_secret": bool(WEBHOOK_SECRET),
            "redis_connection": redis_client is not None,
            "voice_integration": voice_integration is not None,
            "rate_limiting": True,  # Flask-Limiter is configured
            "ip_allowlist": ENABLE_IP_ALLOWLIST,
            "registered_clients": len(clients),
            "meta_integration_enabled": bool(META_APP_ID and META_APP_SECRET),
            "meta_clients": meta_clients_count,
            "legacy_clients": legacy_clients_count,
            "production_security": PRODUCTION_MODE and bool(WEBHOOK_SECRET)
        }

        health_status["checks"] = checks
        # Basic service health - only require basic Flask functionality
        basic_health = all([
            checks["verify_token"],
            checks["rate_limiting"]
        ])

        # Full production health includes all required tokens
        full_production_health = all([
            checks["access_token"],
            checks["verify_token"],
            checks["phone_number_id"],
            checks["rate_limiting"]
        ])

        health_status["healthy"] = basic_health
        health_status["production_ready"] = full_production_health

        # Always return 200 if basic health is OK, even if not production ready
        # This prevents health check failures during initial deployment
        status_code = 200 if basic_health else 503

        return jsonify(health_status), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint"""
    clients = asyncio.run(ea_registry.list_active_clients())

    return jsonify({
        "message": "WhatsApp Webhook Service is running",
        "timestamp": datetime.now().isoformat(),
        "registered_clients": len(clients),
        "voice_available": voice_integration is not None,
        "redis_available": redis_client is not None
    })

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Performance monitoring dashboard"""
    from flask import render_template
    return render_template('dashboard.html')

@app.route('/embedded-signup/', methods=['GET'])
@app.route('/embedded-signup/<path:path>', methods=['GET'])
def embedded_signup_ui(path=''):
    """Serve Meta Embedded Signup UI"""
    from flask import render_template
    try:
        # Serve the Embedded Signup interface
        # In production, this would serve a React/Vue app for the signup flow
        return render_template('embedded_signup.html',
                             meta_app_id=META_APP_ID,
                             api_base_url=request.url_root)
    except Exception as e:
        logger.error(f"Error serving Embedded Signup UI: {e}")
        return jsonify({
            "error": "Embedded Signup UI not available",
            "message": "Template not found or configuration error"
        }), 500

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("🚀 Starting WhatsApp Webhook Service")
    logger.info(f"📱 Phone Number ID: {PHONE_NUMBER_ID}")
    logger.info(f"🔑 Access Token: {'✓' if ACCESS_TOKEN else '✗'}")
    logger.info(f"🔐 Verify Token: {VERIFY_TOKEN}")
    logger.info(f"🎤 Voice Integration: {'✓' if voice_integration else '✗'}")
    logger.info(f"🔒 Webhook Secret: {'✓' if WEBHOOK_SECRET else '✗'}")
    logger.info(f"📦 Redis Connection: {'✓' if redis_client else '✗'}")
    logger.info(f"🏆 Meta Integration: {'✓' if META_APP_ID and META_APP_SECRET else '✗'}")
    logger.info(f"🔗 Meta App ID: {META_APP_ID[:10] + '...' if META_APP_ID else 'Not configured'}")

    # Run Flask app
    port = int(os.getenv('WEBHOOK_PORT', os.getenv('PORT', 8000)))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    )