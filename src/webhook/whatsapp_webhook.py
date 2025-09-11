"""
WhatsApp Cloud API Webhook Server
Receives incoming WhatsApp messages and processes them with EA
"""

import asyncio
import logging
import json
import hmac
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
from flask import Flask, request, jsonify
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.executive_assistant import ExecutiveAssistant, ConversationChannel
from communication.whatsapp_cloud_api import WhatsAppCloudAPIChannel

logger = logging.getLogger(__name__)

# Flask app for webhook
app = Flask(__name__)

# WhatsApp configuration
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')
ACCESS_TOKEN = os.getenv('WHATSAPP_BUSINESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')

# Customer mapping (phone -> customer_id)
PHONE_TO_CUSTOMER = {
    "19496212077": "jose-personal"  # Your phone -> your EA
}

@app.route('/webhook/whatsapp', methods=['GET'])
def verify_webhook():
    """Verify webhook for WhatsApp"""
    try:
        # Parse verification request
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        logger.info(f"Webhook verification: mode={mode}, token={token}")
        
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
def handle_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        # Get request data
        data = request.get_json()
        
        logger.info(f"📱 Incoming webhook: {json.dumps(data, indent=2)}")
        
        # Validate webhook signature (optional but recommended)
        signature = request.headers.get('X-Hub-Signature-256', '')
        if not validate_signature(request.get_data(), signature):
            logger.warning("⚠️ Invalid webhook signature")
            # For testing, we'll proceed anyway - in production, return 403
        
        # Process webhook data
        asyncio.run(process_whatsapp_webhook(data))
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")
        return jsonify({"error": str(e)}), 500

def validate_signature(payload: bytes, signature: str) -> bool:
    """Validate webhook signature"""
    webhook_secret = os.getenv('WHATSAPP_WEBHOOK_SECRET')
    if not webhook_secret:
        return True  # Skip validation if no secret
    
    try:
        expected_signature = hmac.new(
            webhook_secret.encode(),
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
            logger.info("No entry in webhook data")
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
        
        # Get message content
        content = ""
        if message_type == 'text':
            content = message.get('text', {}).get('body', '')
        elif message_type == 'audio':
            content = "[Voice Message]"
            # TODO: Process voice message with speech-to-text
        elif message_type == 'image':
            content = "[Image]"
            # TODO: Process image with AI vision
        elif message_type == 'document':
            content = "[Document]"
            # TODO: Process document
        else:
            content = f"[{message_type.title()} Message]"
        
        logger.info(f"📨 Message from {from_number}: {content}")
        
        # Map phone number to customer
        customer_id = PHONE_TO_CUSTOMER.get(from_number)
        if not customer_id:
            logger.warning(f"Unknown phone number: {from_number}")
            # For now, create a generic customer ID
            customer_id = f"customer_{from_number}"
        
        # Process with EA
        if content and content != "":
            ea_response = await process_with_ea(content, customer_id, from_number)
            
            # Send response back
            if ea_response:
                await send_whatsapp_response(from_number, ea_response)
        
    except Exception as e:
        logger.error(f"Error handling message: {e}")

async def handle_message_status(status: Dict[str, Any]):
    """Handle message status updates (delivered, read, etc.)"""
    try:
        message_id = status.get('id', '')
        status_type = status.get('status', '')
        timestamp = status.get('timestamp', '')
        
        logger.info(f"📊 Message {message_id} status: {status_type}")
        
        # TODO: Update message status in database
        
    except Exception as e:
        logger.error(f"Error handling status: {e}")

async def process_with_ea(message: str, customer_id: str, from_number: str) -> str:
    """Process message with Executive Assistant"""
    try:
        logger.info(f"🤖 Processing with EA: customer={customer_id}, message='{message[:50]}...'")
        
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
        return "I'm having trouble processing your message right now. Please try again in a moment."

async def send_whatsapp_response(to_number: str, message: str):
    """Send response back via WhatsApp"""
    try:
        # Initialize WhatsApp channel
        config = {
            'access_token': ACCESS_TOKEN,
            'phone_number_id': PHONE_NUMBER_ID
        }
        
        channel = WhatsAppCloudAPIChannel("webhook-response", config)
        await channel.initialize()
        
        # Send message
        message_id = await channel.send_message(to_number, message)
        
        if message_id:
            logger.info(f"✅ Response sent to {to_number}: {message_id}")
        else:
            logger.error(f"❌ Failed to send response to {to_number}")
            
    except Exception as e:
        logger.error(f"Error sending response: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "whatsapp_webhook",
        "timestamp": datetime.now().isoformat(),
        "phone_number_id": PHONE_NUMBER_ID,
        "verify_token_configured": bool(VERIFY_TOKEN),
        "access_token_configured": bool(ACCESS_TOKEN)
    })

@app.route('/test', methods=['GET'])
def test_endpoint():
    """Test endpoint"""
    return jsonify({
        "message": "WhatsApp webhook server is running",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("🚀 Starting WhatsApp Webhook Server")
    logger.info(f"📱 Phone Number ID: {PHONE_NUMBER_ID}")
    logger.info(f"🔑 Access Token: {'✓' if ACCESS_TOKEN else '✗'}")
    logger.info(f"🔐 Verify Token: {VERIFY_TOKEN}")
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('WEBHOOK_PORT', 8000)),
        debug=True
    )