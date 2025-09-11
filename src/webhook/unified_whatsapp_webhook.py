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
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import sys
from pathlib import Path
import ipaddress

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agents.executive_assistant import ExecutiveAssistant, ConversationChannel
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
ACCESS_TOKEN = os.getenv('WHATSAPP_BUSINESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')
WEBHOOK_SECRET = os.getenv('WHATSAPP_WEBHOOK_SECRET', '')

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

# Voice integration
voice_integration = None
if os.getenv('ELEVENLABS_API_KEY'):
    try:
        voice_integration = VoiceIntegration()
    except Exception as e:
        logger.warning(f"Voice integration initialization failed: {e}")

@app.before_request
def before_request():
    """Security middleware for all requests"""
    # Add security headers
    if request.endpoint:
        add_security_headers()
    
    # IP allowlisting for webhook endpoints
    if request.endpoint and 'webhook' in request.endpoint:
        if ENABLE_IP_ALLOWLIST and not is_allowed_ip(request.remote_addr):
            logger.warning(f"🚫 Blocked request from unauthorized IP: {request.remote_addr}")
            return jsonify({"error": "Unauthorized IP address"}), 403

def add_security_headers():
    """Add security headers to response"""
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = "default-src 'self'"
        return response

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
        
        # Process webhook data
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
        # Get media URL
        url = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {'Authorization': f'Bearer {ACCESS_TOKEN}'}
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            media_info = response.json()
            media_url = media_info.get('url')
            
            if media_url:
                # Download actual media
                media_response = requests.get(media_url, headers=headers)
                if media_response.status_code == 200:
                    return media_response.content
                    
        logger.error(f"Failed to download media {media_id}")
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
        
        # Initialize EA for customer
        ea = ExecutiveAssistant(customer_id=customer_id)
        
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
        
        # Use WhatsApp Cloud API channel for voice message
        config = {
            'access_token': ACCESS_TOKEN,
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

@app.route('/health', methods=['GET'])
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
            "access_token": bool(ACCESS_TOKEN),
            "verify_token": bool(VERIFY_TOKEN),
            "phone_number_id": bool(PHONE_NUMBER_ID),
            "ea_integration": EA_INTEGRATION_ENABLED,
            "voice_integration": voice_integration is not None,
            "webhook_secret": bool(WEBHOOK_SECRET),
            "rate_limiting": True,  # Flask-Limiter is configured
            "ip_allowlist": ENABLE_IP_ALLOWLIST,
            "production_security": PRODUCTION_MODE and bool(WEBHOOK_SECRET)
        }
        
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

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("🚀 Starting Unified WhatsApp Webhook Server")
    logger.info(f"📱 Phone Number ID: {PHONE_NUMBER_ID}")
    logger.info(f"🔑 Access Token: {'✓' if ACCESS_TOKEN else '✗'}")
    logger.info(f"🔐 Verify Token: {VERIFY_TOKEN}")
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