#!/usr/bin/env python3
"""
Production WhatsApp Webhook for DigitalOcean App Platform
Minimal dependencies, optimized for container deployment
"""

import logging
import json
import hmac
import hashlib
import requests
import os
from datetime import datetime
from typing import Dict, Any
from flask import Flask, request, jsonify

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

def handle_message(message: Dict[str, Any]):
    """Handle individual message"""
    try:
        from_number = message.get('from', '')
        message_type = message.get('type', 'text')
        
        # Get text content
        content = ""
        if message_type == 'text':
            content = message.get('text', {}).get('body', '')
        else:
            content = f"[{message_type} message received]"
        
        logger.info(f"📨 Message from {from_number}: {content[:50]}...")
        
        # Send simple response
        if content.strip():
            response = f"Thanks for your message: '{content[:100]}...' I'll get back to you soon!"
            send_response(from_number, response)
            
    except Exception as e:
        logger.error(f"Message handling error: {e}")

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
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "whatsapp-webhook-simple",
        "environment": ENVIRONMENT,
        "checks": {
            "access_token": bool(ACCESS_TOKEN),
            "verify_token": bool(VERIFY_TOKEN),
            "phone_number_id": bool(PHONE_NUMBER_ID)
        }
    }), 200

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