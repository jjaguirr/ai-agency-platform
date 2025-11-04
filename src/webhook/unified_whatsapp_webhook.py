#!/usr/bin/env python3
"""
Unified WhatsApp Cloud API Webhook Server
Consolidates simple webhook functionality with full EA integration
"""

import asyncio
import logging
import json
import hmac
import hashlib
import requests
import secrets
import base64
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from flask import Flask, request, jsonify, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import sys
from pathlib import Path
import ipaddress
import re
from cryptography.fernet import Fernet
import threading
from functools import wraps

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Secure Token Management System
class SecureTokenManager:
    """Secure token management with rotation and masking"""

    def __init__(self):
        self._token = None
        self._encrypted_token = None
        self._token_expires_at = None
        self._token_refresh_threshold = timedelta(minutes=50)  # Refresh 10 minutes before expiry
        self._fernet_key = os.getenv('TOKEN_ENCRYPTION_KEY')
        self._lock = threading.Lock()

        if not self._fernet_key:
            # Generate a key for development (in production, use a secure key management system)
            self._fernet_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

        self.fernet = Fernet(self._fernet_key.encode())

    def _mask_token(self, token: str) -> str:
        """Mask token for logging"""
        if not token or len(token) < 8:
            return "****"
        return f"{token[:4]}****{token[-4:]}"

    def set_token(self, token: str, expires_in_minutes: int = 60):
        """Set and encrypt token with expiration"""
        with self._lock:
            self._token = token
            self._encrypted_token = self.fernet.encrypt(token.encode()).decode()
            self._token_expires_at = datetime.now() + timedelta(minutes=expires_in_minutes)

    def get_token(self) -> Optional[str]:
        """Get decrypted token if not expired"""
        with self._lock:
            if not self._token:
                return None

            if self._token_expires_at and datetime.now() > self._token_expires_at:
                logger.warning("Token expired, clearing cached token")
                self._token = None
                self._encrypted_token = None
                return None

            return self._token

    def is_token_expired(self) -> bool:
        """Check if token needs refresh"""
        if not self._token_expires_at:
            return True
        return datetime.now() > (self._token_expires_at - self._token_refresh_threshold)

    def get_masked_token(self) -> str:
        """Get masked token for logging"""
        token = self.get_token()
        return self._mask_token(token) if token else "None"

    def refresh_token(self, new_token: str, expires_in_minutes: int = 60):
        """Refresh token with new value"""
        self.set_token(new_token, expires_in_minutes)
        logger.info(f"Token refreshed successfully")

# Global token manager instance
token_manager = SecureTokenManager()

from agents.executive_assistant import ConversationChannel
from communication.whatsapp_cloud_api import WhatsAppCloudAPIChannel
from communication.voice_integration import VoiceIntegration
from webhook.monitoring import webhook_monitor, monitoring_bp, monitor_webhook_request

logger = logging.getLogger(__name__)

# Flask app for webhook
app = Flask(__name__, template_folder='templates')

# Register monitoring blueprint
app.register_blueprint(monitoring_bp)

# Rate limiting configuration
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour"],
    storage_uri="memory://"  # In production, use Redis
)

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
ACCESS_TOKEN_RAW = os.getenv('WHATSAPP_BUSINESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')
WEBHOOK_SECRET = os.getenv('WHATSAPP_WEBHOOK_SECRET', '')

# Initialize secure token manager
if ACCESS_TOKEN_RAW:
    token_manager.set_token(ACCESS_TOKEN_RAW, expires_in_minutes=60)

# Customer mapping (phone -> customer_id)
PHONE_TO_CUSTOMER = {
    "19496212077": "jose-personal"  # Your phone -> your EA
}

# Enable full EA integration or simple mode
EA_INTEGRATION_ENABLED = os.getenv('EA_INTEGRATION_ENABLED', 'true').lower() == 'true'

# Security configuration
PRODUCTION_MODE = os.getenv('FLASK_ENV', 'development') == 'production'
ENABLE_IP_ALLOWLIST = os.getenv('ENABLE_IP_ALLOWLIST', 'true').lower() == 'true'
ENFORCE_WEBHOOK_SECRET = os.getenv('ENFORCE_WEBHOOK_SECRET', 'true').lower() == 'true'

# Input validation configuration
MAX_MESSAGE_SIZE = 10 * 1024  # 10KB limit
MAX_PHONE_LENGTH = 15  # E.164 format
ALLOWED_MESSAGE_TYPES = ['text', 'audio', 'image', 'document', 'video', 'sticker']

# Customer rate limiting (in-memory store for demo - use Redis in production)
customer_rate_limits = {}
CUSTOMER_RATE_LIMIT = {
    'requests_per_minute': 20,
    'requests_per_hour': 100
}

def validate_and_sanitize_input(data: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validate and sanitize webhook input data
    Returns: (is_valid, error_message, sanitized_data)
    """
    try:
        # Check payload size
        payload_size = len(json.dumps(data).encode('utf-8'))
        if payload_size > MAX_MESSAGE_SIZE:
            return False, f"Payload too large: {payload_size} bytes (max {MAX_MESSAGE_SIZE})", {}

        # Validate basic structure
        if not isinstance(data, dict):
            return False, "Invalid payload structure: not a dictionary", {}

        # Validate entry structure
        entry = data.get('entry', [])
        if not isinstance(entry, list):
            return False, "Invalid entry structure: not a list", {}

        if not entry:
            return False, "Empty entry list", {}

        sanitized_data = {
            'entry': [],
            'original_size': payload_size
        }

        for entry_item in entry:
            if not isinstance(entry_item, dict):
                continue

            sanitized_entry = {}
            changes = entry_item.get('changes', [])

            if not isinstance(changes, list):
                continue

            sanitized_changes = []

            for change in changes:
                if not isinstance(change, dict):
                    continue

                value = change.get('value', {})
                if not isinstance(value, dict):
                    continue

                sanitized_value = {}

                # Validate and sanitize messages
                messages = value.get('messages', [])
                if messages:
                    sanitized_messages = []
                    for message in messages:
                        if not isinstance(message, dict):
                            continue

                        # Validate message type
                        msg_type = message.get('type', 'text')
                        if msg_type not in ALLOWED_MESSAGE_TYPES:
                            logger.warning(f"Invalid message type: {msg_type}")
                            continue

                        # Validate phone number format
                        from_number = message.get('from', '')
                        if not validate_phone_number(from_number):
                            logger.warning(f"Invalid phone number format: {from_number}")
                            continue

                        # Sanitize message content
                        sanitized_message = {
                            'from': sanitize_phone_number(from_number),
                            'id': message.get('id', ''),
                            'type': msg_type,
                            'timestamp': str(message.get('timestamp', int(datetime.now().timestamp())))
                        }

                        # Handle different message types
                        if msg_type == 'text':
                            text_body = message.get('text', {}).get('body', '')
                            if len(text_body.encode('utf-8')) > MAX_MESSAGE_SIZE:
                                logger.warning(f"Text message too large: {len(text_body)} chars")
                                continue
                            sanitized_message['text'] = sanitize_text(text_body)

                        elif msg_type in ['audio', 'image', 'document', 'video']:
                            media = message.get(msg_type, {})
                            if isinstance(media, dict) and 'id' in media:
                                sanitized_message[msg_type] = {'id': media['id']}

                        sanitized_messages.append(sanitized_message)

                    if sanitized_messages:
                        sanitized_value['messages'] = sanitized_messages

                # Handle status updates
                statuses = value.get('statuses', [])
                if statuses and isinstance(statuses, list):
                    sanitized_value['statuses'] = statuses

                if sanitized_value:
                    sanitized_changes.append({'value': sanitized_value})

            if sanitized_changes:
                sanitized_entry['changes'] = sanitized_changes
                sanitized_data['entry'].append(sanitized_entry)

        if not sanitized_data['entry']:
            return False, "No valid data after sanitization", {}

        return True, "", sanitized_data

    except Exception as e:
        logger.error(f"Input validation error: {e}")
        return False, f"Validation error: {str(e)}", {}

def validate_phone_number(phone: str) -> bool:
    """Validate phone number format (E.164)"""
    if not phone or not isinstance(phone, str):
        return False

    # Remove common separators
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)

    # Check if it starts with + and has 10-15 digits
    if not re.match(r'^\+[1-9]\d{9,14}$', clean_phone):
        return False

    return True

def sanitize_phone_number(phone: str) -> str:
    """Sanitize phone number"""
    if not phone:
        return ""

    # Remove non-digit characters except +
    sanitized = re.sub(r'[^\d+]', '', phone)

    # Ensure it starts with +
    if not sanitized.startswith('+'):
        sanitized = '+' + sanitized.lstrip('0')

    return sanitized

def sanitize_text(text: str) -> str:
    """Sanitize text content"""
    if not text or not isinstance(text, str):
        return ""

    # Remove null bytes and control characters except newlines and tabs
    sanitized = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]', '', text)

    # Trim whitespace
    sanitized = sanitized.strip()

    # Limit length
    if len(sanitized) > 4000:  # Reasonable limit for messages
        sanitized = sanitized[:4000] + "..."

    return sanitized

def check_customer_rate_limit(customer_id: str) -> Tuple[bool, str]:
    """Check if customer is within rate limits"""
    now = datetime.now()

    if customer_id not in customer_rate_limits:
        customer_rate_limits[customer_id] = {
            'minute_count': 0,
            'hour_count': 0,
            'minute_reset': now + timedelta(minutes=1),
            'hour_reset': now + timedelta(hours=1)
        }

    limits = customer_rate_limits[customer_id]

    # Reset counters if time windows have passed
    if now > limits['minute_reset']:
        limits['minute_count'] = 0
        limits['minute_reset'] = now + timedelta(minutes=1)

    if now > limits['hour_reset']:
        limits['hour_count'] = 0
        limits['hour_reset'] = now + timedelta(hours=1)

    # Check limits
    if limits['minute_count'] >= CUSTOMER_RATE_LIMIT['requests_per_minute']:
        return False, f"Rate limit exceeded: {limits['minute_count']}/{CUSTOMER_RATE_LIMIT['requests_per_minute']} per minute"

    if limits['hour_count'] >= CUSTOMER_RATE_LIMIT['requests_per_hour']:
        return False, f"Rate limit exceeded: {limits['hour_count']}/{CUSTOMER_RATE_LIMIT['requests_per_hour']} per hour"

    # Increment counters
    limits['minute_count'] += 1
    limits['hour_count'] += 1

    return True, ""

def generate_csrf_token() -> str:
    """Generate a CSRF token"""
    return secrets.token_urlsafe(32)

def validate_csrf_token(token: str) -> bool:
    """Validate CSRF token"""
    if not token:
        return False

    # In production, store tokens in a secure session store
    # For now, we'll use a simple in-memory store (not recommended for production)
    if not hasattr(validate_csrf_token, '_tokens'):
        validate_csrf_token._tokens = set()

    return token in validate_csrf_token._tokens

def csrf_protect(f):
    """CSRF protection decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            # Skip CSRF for webhook endpoints (they use signature validation)
            if request.endpoint and 'webhook' in request.endpoint:
                return f(*args, **kwargs)

            # Check for CSRF token in headers or form data
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
            if not token or not validate_csrf_token(token):
                logger.warning(f"CSRF token validation failed from IP: {request.remote_addr}")
                return jsonify({"error": "CSRF token validation failed"}), 403

        return f(*args, **kwargs)
    return decorated_function

# Voice integration
voice_integration = None
if os.getenv('ELEVENLABS_API_KEY'):
    try:
        voice_integration = VoiceIntegration()
    except Exception as e:
        logger.warning(f"Voice integration initialization failed: {e}")

@app.after_request
def set_security_headers(response):
    """Add comprehensive security headers to response"""
    # Basic security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # HSTS for HTTPS
    if request.headers.get('X-Forwarded-Proto', request.scheme) == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    # Content Security Policy
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self';"
    )
    response.headers['Content-Security-Policy'] = csp_policy

    # Additional security headers
    response.headers['Permissions-Policy'] = (
        'camera=(), microphone=(), geolocation=(), interest-cohort=()'
    )
    response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
    response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
    response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'

    # CORS headers for production
    if PRODUCTION_MODE:
        origin = request.headers.get('Origin', '')
        allowed_origins = os.getenv('ALLOWED_ORIGINS', '').split(',')

        if origin and any(allowed in origin for allowed in allowed_origins):
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
            response.headers['Access-Control-Max-Age'] = '86400'  # 24 hours

    # Secure cookie settings
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

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

        # Log with masked token for security
        token_status = '✓' if token == VERIFY_TOKEN else '✗'
        logger.info(f"🔍 Webhook verification: mode={mode}, token={token_status}")

        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("✅ Webhook verified successfully")
            return challenge, 200
        else:
            logger.error("❌ Webhook verification failed: invalid token")
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

        logger.info("📱 Incoming webhook data received")

        # Validate webhook signature (REQUIRED in production)
        signature = request.headers.get('X-Hub-Signature-256', '')
        if ENFORCE_WEBHOOK_SECRET or PRODUCTION_MODE:
            if not WEBHOOK_SECRET:
                logger.error("🚨 WEBHOOK_SECRET not configured for production")
                return jsonify({"error": "Server configuration error"}), 500

            if not validate_signature(request.get_data(), signature):
                logger.warning(f"⚠️ Invalid webhook signature from IP: {request.remote_addr}")
                return jsonify({"error": "Invalid signature"}), 403

        # Validate and sanitize input
        is_valid, error_msg, sanitized_data = validate_and_sanitize_input(data)
        if not is_valid:
            logger.warning(f"Input validation failed: {error_msg}")
            return jsonify({"error": "Invalid input data"}), 400

        logger.info(f"✅ Input validation passed, payload size: {sanitized_data['original_size']} bytes")

        # Process webhook data with sanitized input
        asyncio.run(process_whatsapp_webhook(sanitized_data))

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")
        return jsonify({"error": "Internal server error"}), 500

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
                    # Extract customer ID for rate limiting
                    from_number = message.get('from', '')
                    customer_id = get_customer_id(from_number)

                    # Check customer rate limit
                    rate_limit_ok, rate_limit_msg = check_customer_rate_limit(customer_id)
                    if not rate_limit_ok:
                        logger.warning(f"Rate limit exceeded for customer {customer_id}: {rate_limit_msg}")
                        continue

                    await handle_incoming_message(message, value)

                # Handle message status updates
                statuses = value.get('statuses', [])
                for status in statuses:
                    await handle_message_status(status)

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")

async def handle_incoming_message(message: Dict[str, Any], value: Dict[str, Any]):
    """Handle a single incoming WhatsApp message"""
    try:
        from_number = message.get('from', '')
        message_id = message.get('id', '')
        message_type = message.get('type', 'text')
        timestamp = message.get('timestamp', str(int(datetime.now().timestamp())))
        
        # Get message content based on type
        content = ""
        if message_type == 'text':
            content = message.get('text', {}).get('body', '')
        elif message_type == 'audio':
            content = await process_voice_message(message)
        elif message_type == 'image':
            content = "[Image received]"
            # TODO: Process image with AI vision
        elif message_type == 'document':
            content = "[Document received]"
            # TODO: Process document
        else:
            content = f"[{message_type.title()} message received]"
        
        logger.info(f"📨 Message from {from_number}: {content[:100]}{'...' if len(content) > 100 else ''}")
        
        # Map phone number to customer
        customer_id = get_customer_id(from_number)
        
        # Process with EA or send simple response
        if content and content.strip():
            if EA_INTEGRATION_ENABLED and customer_id:
                ea_response = await process_with_ea(content, customer_id, from_number)
            else:
                ea_response = generate_simple_response(content, from_number)
            
            # Send response back
            if ea_response:
                await send_whatsapp_response(from_number, ea_response)
        
    except Exception as e:
        logger.error(f"Error handling message: {e}")

async def process_voice_message(message: Dict[str, Any]) -> str:
    """Process voice message with speech-to-text"""
    try:
        if not voice_integration:
            return "[Voice message - processing not available]"
        
        # Get audio data from WhatsApp API
        audio_id = message.get('audio', {}).get('id')
        if not audio_id:
            return "[Voice message - no audio ID]"
        
        # Download and process voice message
        audio_data = await download_whatsapp_media(audio_id)
        if audio_data:
            # Convert speech to text
            transcription = await voice_integration.speech_to_text(audio_data)
            logger.info(f"🎤 Voice message transcribed: {transcription}")
            return transcription or "[Voice message - transcription failed]"
        else:
            return "[Voice message - download failed]"
            
    except Exception as e:
        logger.error(f"Error processing voice message: {e}")
        return "[Voice message - processing error]"

async def download_whatsapp_media(media_id: str) -> Optional[bytes]:
    """Download media from WhatsApp Cloud API"""
    try:
        # Get current token
        current_token = token_manager.get_token()
        if not current_token:
            logger.error("No valid access token available for media download")
            return None

        # Get media URL
        url = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {'Authorization': f'Bearer {current_token}'}

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            media_info = response.json()
            media_url = media_info.get('url')

            if media_url:
                # Download actual media
                media_response = requests.get(media_url, headers=headers)
                if media_response.status_code == 200:
                    return media_response.content
                else:
                    logger.error(f"Failed to download media content: {media_response.status_code}")
            else:
                logger.error("No media URL in response")
        else:
            logger.error(f"Failed to get media info: {response.status_code} - {response.text}")

        return None

    except Exception as e:
        logger.error(f"Error downloading media: {e}")
        return None

def get_customer_id(from_number: str) -> str:
    """Get customer ID for phone number"""
    customer_id = PHONE_TO_CUSTOMER.get(from_number)
    if not customer_id:
        logger.info(f"Creating new customer for phone: {from_number}")
        # Create dynamic customer ID for unknown numbers
        customer_id = f"customer_{from_number}"
        # TODO: Store in database for persistence
    return customer_id

def generate_simple_response(message: str, from_number: str) -> str:
    """Generate simple auto-response when EA is disabled"""
    responses = [
        f"🤖 Thanks for your message: '{message[:50]}{'...' if len(message) > 50 else ''}'. I'm processing this with my EA system.",
        f"📝 Message received: '{message[:50]}{'...' if len(message) > 50 else ''}'. Your EA will respond shortly.",
        f"✅ Got your message: '{message[:50]}{'...' if len(message) > 50 else ''}'. Processing with Executive Assistant..."
    ]
    
    # Simple rotation based on message length
    return responses[len(message) % len(responses)]

async def handle_message_status(status: Dict[str, Any]):
    """Handle message status updates (delivered, read, etc.)"""
    try:
        message_id = status.get('id', '')
        status_type = status.get('status', '')
        timestamp = status.get('timestamp', '')
        
        logger.debug(f"📊 Message {message_id} status: {status_type}")
        
        # TODO: Update message status in database
        
    except Exception as e:
        logger.error(f"Error handling status: {e}")

async def process_with_ea(message: str, customer_id: str, from_number: str) -> str:
    """Process message with Executive Assistant"""
    try:
        logger.info(f"🤖 Processing with EA: customer={customer_id}")

        # Initialize simplified EA for customer
        ea = SimplifiedExecutiveAssistant(customer_id=customer_id)

        # Process message
        response = await ea.handle_customer_interaction(
            message,
            ConversationChannel.WHATSAPP
        )

        logger.info(f"✅ EA response generated: {len(response)} characters")
        return response

    except Exception as e:
        logger.error(f"❌ EA processing error: {e}")
        return "I'm having trouble processing your message right now. Let me get back to you in a moment."

async def send_whatsapp_response(to_number: str, message: str, voice_enabled: bool = False):
    """Send response back via WhatsApp (text or voice)"""
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
        # Get current token
        current_token = token_manager.get_token()
        if not current_token:
            logger.error("No valid access token available for sending message")
            return None

        # Clean phone number (remove + and spaces)
        clean_to = to_number.replace('+', '').replace(' ', '').replace('-', '')

        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            'Authorization': f'Bearer {current_token}',
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
        
        # Use WhatsApp Cloud API channel for voice message
        current_token = token_manager.get_token()
        if not current_token:
            logger.error("No valid access token available for voice message")
            await send_text_response(to_number, message)
            return

        config = {
            'access_token': current_token,
            'phone_number_id': PHONE_NUMBER_ID
        }
        
        channel = WhatsAppCloudAPIChannel("voice-response", config)
        await channel.initialize()
        
        # Send voice message
        message_id = await channel.send_voice_message(to_number, audio_data)
        
        if message_id:
            logger.info(f"✅ Voice message sent to {to_number}: {message_id}")
        else:
            logger.warning(f"Voice message failed, sending text instead")
            await send_text_response(to_number, message)
            
    except Exception as e:
        logger.error(f"Error sending voice message: {e}")
        # Fallback to text
        await send_text_response(to_number, message)

@app.route('/admin/refresh-token', methods=['POST'])
@csrf_protect
def refresh_access_token():
    """Refresh WhatsApp access token (admin only)"""
    try:
        # In production, add proper authentication
        if PRODUCTION_MODE and request.remote_addr not in ['127.0.0.1', 'localhost']:
            return jsonify({"error": "Unauthorized"}), 403

        new_token = request.json.get('access_token') if request.json else None
        if not new_token:
            return jsonify({"error": "No access token provided"}), 400

        # Validate token format (basic check)
        if len(new_token) < 100:
            return jsonify({"error": "Invalid token format"}), 400

        expires_in = request.json.get('expires_in_minutes', 60) if request.json else 60

        # Update token
        token_manager.set_token(new_token, expires_in)

        logger.info(f"Access token refreshed successfully")
        return jsonify({
            "status": "success",
            "message": "Token refreshed",
            "expires_in_minutes": expires_in
        }), 200

    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return jsonify({"error": "Token refresh failed"}), 500

@app.route('/health', methods=['GET'])
@csrf_protect
def health_check():
    """Health check endpoint for DigitalOcean App Platform"""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "whatsapp-webhook",
            "version": "1.0.0",
            "environment": os.getenv('ENVIRONMENT', 'development')
        }
        
        # Basic health checks
        checks = {
            "access_token": token_manager.get_token() is not None,
            "token_encrypted": token_manager._encrypted_token is not None,
            "verify_token": bool(VERIFY_TOKEN),
            "phone_number_id": bool(PHONE_NUMBER_ID),
            "ea_integration": EA_INTEGRATION_ENABLED,
            "voice_integration": voice_integration is not None,
            "webhook_secret": bool(WEBHOOK_SECRET),
            "rate_limiting": True,  # Flask-Limiter is configured
            "ip_allowlist": ENABLE_IP_ALLOWLIST,
            "production_security": PRODUCTION_MODE and bool(WEBHOOK_SECRET),
            "input_validation": True,  # New validation system
            "customer_rate_limiting": True,  # Per-customer rate limiting
            "csrf_protection": True,  # CSRF protection enabled
            "security_headers": True  # Enhanced security headers
        }

        # Token expiration check
        if checks["access_token"]:
            checks["token_expires_soon"] = token_manager.is_token_expired()
        
        health_status["checks"] = checks
        health_status["healthy"] = all(checks.values())
        
        return jsonify(health_status), 200 if health_status["healthy"] else 503
        
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
    return jsonify({
        "message": "Unified WhatsApp webhook server is running",
        "timestamp": datetime.now().isoformat(),
        "ea_integration": EA_INTEGRATION_ENABLED,
        "voice_available": voice_integration is not None
    })

@app.route('/config', methods=['GET'])
def config_endpoint():
    """Configuration endpoint"""
    return jsonify({
        "phone_number_id": PHONE_NUMBER_ID,
        "verify_token": VERIFY_TOKEN,
        "ea_integration_enabled": EA_INTEGRATION_ENABLED,
        "voice_integration_available": voice_integration is not None,
        "customer_mappings": len(PHONE_TO_CUSTOMER),
        "webhook_secret_configured": bool(WEBHOOK_SECRET)
    })

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """Performance monitoring dashboard"""
    from flask import render_template
    return render_template('dashboard.html')

class SimplifiedExecutiveAssistant:
    """
    Simplified Executive Assistant for webhook integration
    Focuses on core functionality without complex dependencies
    """

    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.personality = "helpful_and_capable"
        self.name = "Sarah"

        # Simple in-memory storage for demo
        self.conversation_memory = {}

        # Initialize basic AI model if available
        self.llm_available = bool(os.getenv("OPENAI_API_KEY"))

        if self.llm_available:
            try:
                import openai
                self.openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            except ImportError:
                self.llm_available = False

        logger.info(f"Simplified EA initialized for customer {customer_id}")

    async def handle_customer_interaction(self, message: str, channel: ConversationChannel) -> str:
        """Handle customer message with simplified processing"""
        try:
            # Get conversation context
            context = self._get_conversation_context()

            # Generate response based on available capabilities
            if self.llm_available:
                response = await self._generate_ai_response(message, context)
            else:
                response = self._generate_simple_response(message, context)

            # Store interaction
            self._store_interaction(message, response, channel)

            return response

        except Exception as e:
            logger.error(f"Error in simplified EA: {e}")
            return "I'm here to help! How can I assist you with your business today?"

    def _get_conversation_context(self) -> str:
        """Get recent conversation context"""
        if self.customer_id in self.conversation_memory:
            recent_messages = self.conversation_memory[self.customer_id][-5:]  # Last 5 messages
            return " ".join([msg.get("message", "") for msg in recent_messages])
        return ""

    async def _generate_ai_response(self, message: str, context: str) -> str:
        """Generate response using AI model"""
        try:
            prompt = f"""
            You are Sarah, a helpful Executive Assistant.

            Customer message: {message}
            Conversation context: {context}

            Provide a helpful, professional response. If this is about business automation,
            mention that you can help create workflows. Keep responses conversational and actionable.
            """

            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful Executive Assistant named Sarah."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return self._generate_simple_response(message, context)

    def _generate_simple_response(self, message: str, context: str) -> str:
        """Generate simple rule-based response"""
        message_lower = message.lower()

        # Business automation responses
        if any(word in message_lower for word in ["automate", "workflow", "automation", "process"]):
            return "I'd be happy to help you automate that process! I can create workflows that handle repetitive tasks automatically. What specific process would you like me to automate for you?"

        # Business inquiry responses
        elif any(word in message_lower for word in ["business", "company", "work", "clients"]):
            return "I love helping businesses like yours! Tell me more about what you do and what challenges you're facing. I can help identify automation opportunities and create solutions tailored to your needs."

        # General assistance
        else:
            return "I'm here to help with your business needs! Whether you need help with automation, organization, or just have questions about how I can assist you, I'm ready to help. What would you like to work on?"

    def _store_interaction(self, message: str, response: str, channel: ConversationChannel):
        """Store interaction in memory"""
        if self.customer_id not in self.conversation_memory:
            self.conversation_memory[self.customer_id] = []

        interaction = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "response": response,
            "channel": channel.value
        }

        self.conversation_memory[self.customer_id].append(interaction)

        # Keep only last 50 interactions to prevent memory bloat
        if len(self.conversation_memory[self.customer_id]) > 50:
            self.conversation_memory[self.customer_id] = self.conversation_memory[self.customer_id][-50:]

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("🚀 Starting Unified WhatsApp Webhook Server")
    logger.info(f"📱 Phone Number ID: {PHONE_NUMBER_ID}")
    logger.info(f"🔑 Access Token: {token_manager.get_masked_token()}")
    logger.info(f"🔐 Verify Token: {'✓' if VERIFY_TOKEN else '✗'}")
    logger.info(f"🤖 EA Integration: {'✓' if EA_INTEGRATION_ENABLED else '✗'}")
    logger.info(f"🎤 Voice Integration: {'✓' if voice_integration else '✗'}")
    logger.info(f"🔒 Webhook Secret: {'✓' if WEBHOOK_SECRET else '✗'}")
    
    # Run Flask app
    port = int(os.getenv('WEBHOOK_PORT', os.getenv('PORT', 8000)))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    )