#!/usr/bin/env python3
"""
Production WhatsApp Webhook for DigitalOcean App Platform
Minimal dependencies, optimized for container deployment
"""

import logging
import hmac
import hashlib
import requests
import os
import sys
import asyncio
from datetime import datetime
from typing import Dict, Any
from flask import Flask, request, jsonify

# Add src directory to Python path for EA imports
# Try multiple possible paths (local dev vs deployed container)
import os
possible_src_paths = [
    '/Users/jose/Documents/🚀 Projects/⚡ Active/ai-agency-platform/src',  # Local dev
    '../src',  # Relative path in deployment
    '/app/src',  # Common container path
    './src'  # Current directory
]

for path in possible_src_paths:
    if os.path.exists(path):
        sys.path.append(path)
        print(f"Added {path} to Python path")
        break

# Enable EA integration with Customer EA Manager bridge module
try:
    from customer_ea_manager import handle_whatsapp_customer_message, health_check as ea_health_check
    CUSTOMER_EA_AVAILABLE = True
    print("✅ Customer EA Manager imported successfully - EA integration ENABLED")
except ImportError as e:
    print(f"Warning: Could not import Customer EA Manager: {e}")
    handle_whatsapp_customer_message = None
    ea_health_check = None
    CUSTOMER_EA_AVAILABLE = False
    print("🚨 EA integration disabled - using fallback responses")

# Simple Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment configuration
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')
ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '782822591574136')
WEBHOOK_SECRET = os.getenv('WHATSAPP_WEBHOOK_SECRET', '')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')

logger.info(f"🚀 Starting WhatsApp Webhook - Environment: {ENVIRONMENT}")
logger.info(f"📱 Phone ID: {PHONE_NUMBER_ID}")
logger.info(f"🔑 Access Token: {'✓' if ACCESS_TOKEN else '✗'}")
logger.info(f"🔐 Verify Token: {VERIFY_TOKEN}")

@app.route('/webhook/whatsapp', methods=['GET'])
def verify_webhook():
    """Verify webhook for WhatsApp"""
    try:
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        logger.info(f"🔍 Verification: mode={mode}, token_match={token == VERIFY_TOKEN}")
        
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            logger.info("✅ Webhook verified successfully")
            return challenge, 200
        else:
            logger.error("❌ Verification failed")
            return 'Forbidden', 403
            
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return 'Error', 500

@app.route('/webhook/whatsapp', methods=['POST'])
def handle_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        data = request.get_json()
        logger.info("📱 Webhook received")
        
        # Temporarily disable signature validation for debugging
        logger.info("⚠️ Signature validation temporarily disabled for debugging")
        
        # Log signature details for debugging
        signature = request.headers.get('X-Hub-Signature-256', '')
        logger.info(f"🔍 Signature header: {signature[:20] if signature else 'None'}...")
        logger.info(f"🔍 Webhook secret configured: {'Yes' if WEBHOOK_SECRET else 'No'}")
        logger.info(f"🔍 Raw payload length: {len(request.get_data())}")
        
        # Process messages
        process_webhook_data(data)
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

def validate_signature(payload: bytes, signature: str) -> bool:
    """Validate webhook signature"""
    if not WEBHOOK_SECRET:
        return True
    
    try:
        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        signature = signature.replace('sha256=', '')
        return hmac.compare_digest(expected, signature)
        
    except Exception as e:
        logger.error(f"Signature validation error: {e}")
        return False

def process_webhook_data(data: Dict[str, Any]):
    """Process incoming webhook data"""
    try:
        entries = data.get('entry', [])
        
        for entry in entries:
            changes = entry.get('changes', [])
            
            for change in changes:
                value = change.get('value', {})
                messages = value.get('messages', [])
                
                for message in messages:
                    handle_message(message)
                    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")

async def handle_message_with_ea(message: Dict[str, Any]):
    """Handle message with Executive Assistant integration"""
    try:
        from_number = message.get('from', '')
        message_type = message.get('type', 'text')
        
        # Get text content
        content = ""
        if message_type == 'text':
            content = message.get('text', {}).get('body', '')
        else:
            content = f"[{message_type} message received]"
        
        logger.info(f"📨 WhatsApp message from {from_number}: {content[:50]}...")
        
        # Route to Customer EA Management System if available
        if CUSTOMER_EA_AVAILABLE and handle_whatsapp_customer_message and content.strip():
            try:
                # Process message through Customer EA Management System
                # This handles auto-provisioning, tier management, usage limits, etc.
                ea_response = await handle_whatsapp_customer_message(
                    whatsapp_number=from_number,
                    message=content,
                    conversation_id=f"wa_{from_number}_{message.get('id', 'unknown')}"
                )
                
                logger.info(f"🏢 Customer EA response generated for {from_number}: {ea_response[:100]}...")
                send_response(from_number, ea_response)
                
            except Exception as ea_error:
                logger.error(f"Customer EA processing error: {ea_error}")
                # Fallback to simple response
                fallback_response = f"Hi! I'm your Executive Assistant Sarah. I received your message: '{content[:100]}' and I'm processing it now. Let me get back to you in just a moment!"
                send_response(from_number, fallback_response)
        else:
            # Enhanced fallback response for EA service with deployment debugging
            response = f"""Hi! I'm Sarah, your Executive Assistant from AI Agency Platform. 

I received your message: "{content[:100]}{'...' if len(content) > 100 else ''}"

🔧 I'm currently setting up my full conversation system. Here's what I can tell you:

🤖 I'm designed to learn your business and create automated workflows
⚡ I help with daily operations, process automation, and business intelligence  
📱 I'm available 24/7 via WhatsApp, phone, and email
🧠 I remember everything about our conversations

Status: EA System = {'ENABLED' if CUSTOMER_EA_AVAILABLE else 'DEPLOYING'}

I'll have my full capabilities online very soon. Thanks for your patience! 😊"""
            send_response(from_number, response)
            
    except Exception as e:
        logger.error(f"Message handling error: {e}")
        # Emergency fallback
        try:
            if 'from_number' in locals():
                send_response(from_number, "I received your message and I'm working on it. Please give me a moment.")
        except:
            pass

def handle_message(message: Dict[str, Any]):
    """Sync wrapper for async EA message handling"""
    try:
        # Run async EA handling in new event loop
        asyncio.run(handle_message_with_ea(message))
    except Exception as e:
        logger.error(f"Error running async EA handler: {e}")
        # Fallback to simple sync handling
        try:
            from_number = message.get('from', '')
            content = message.get('text', {}).get('body', '') if message.get('type') == 'text' else '[non-text message]'
            response = f"Hi! I received your message: '{content[:100]}' - I'm your Executive Assistant and I'm processing this now."
            send_response(from_number, response)
        except Exception as fallback_error:
            logger.error(f"Fallback handling also failed: {fallback_error}")

def send_response(to_number: str, message: str):
    """Send response via WhatsApp API"""
    try:
        if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
            logger.error("Missing ACCESS_TOKEN or PHONE_NUMBER_ID")
            return
        
        url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
        headers = {
            'Authorization': f'Bearer {ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number.replace('+', ''),
            "type": "text",
            "text": {"body": message}
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            logger.info(f"✅ Response sent to {to_number}")
        else:
            logger.error(f"❌ Send failed: {response.status_code}")
            
    except Exception as e:
        logger.error(f"Send error: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Enhanced health check endpoint with EA system status"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "whatsapp-webhook-ea-integrated",
        "environment": ENVIRONMENT,
        "checks": {
            "access_token": bool(ACCESS_TOKEN),
            "verify_token": bool(VERIFY_TOKEN),
            "phone_number_id": bool(PHONE_NUMBER_ID),
            "ea_integration": CUSTOMER_EA_AVAILABLE
        }
    }
    
    # Add EA system health if available
    if CUSTOMER_EA_AVAILABLE and ea_health_check:
        try:
            import asyncio
            ea_health = asyncio.run(ea_health_check())
            health_status["ea_system"] = ea_health
        except Exception as e:
            health_status["ea_system"] = {"status": "error", "error": str(e)}
    
    # Determine overall health
    if not CUSTOMER_EA_AVAILABLE:
        health_status["status"] = "degraded"
        health_status["warning"] = "EA integration disabled"
    
    return jsonify(health_status), 200

@app.route('/', methods=['GET'])
def root():
    """Root endpoint"""
    return jsonify({
        "message": "WhatsApp Webhook Server",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)