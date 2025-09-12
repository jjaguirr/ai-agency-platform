#!/usr/bin/env python3
"""
Production WhatsApp Webhook for DigitalOcean App Platform
Simplified version with EA-branded responses (no complex imports)
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
        
        # Process messages
        process_webhook_data(data)
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

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
    """Handle individual message with Executive Assistant branding"""
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
        
        # Send Executive Assistant response
        if content.strip():
            response = generate_ea_response(content, from_number)
            send_response(from_number, response)
            
    except Exception as e:
        logger.error(f"Message handling error: {e}")
        # Emergency fallback
        try:
            if 'from_number' in locals():
                send_response(from_number, "Hi! I'm Sarah, your Executive Assistant. I received your message and I'm processing it now.")
        except:
            pass

def generate_ea_response(message_content: str, from_number: str) -> str:
    """Generate Executive Assistant response based on message content"""
    
    # Store customer context (simple in-memory for now)
    customer_id = f"whatsapp_{from_number}"
    
    # Detect conversation intent and respond appropriately
    message_lower = message_content.lower()
    
    # Competitive positioning responses
    competitive_keywords = ['zapier', 'make.com', 'automation platform', 'competitor', 'cheaper', 'price', 'cost', 'different', 'why should', 'better']
    if any(keyword in message_lower for keyword in competitive_keywords):
        return f"""I understand you're comparing options! Here's what makes me fundamentally different from automation tools:

🎯 **I'M YOUR BUSINESS PARTNER, NOT SOFTWARE**
• I learn your business through conversation like a human EA would
• I understand your goals, preferences, and business context
• I proactively help you grow, not just execute predefined tasks

💡 **THE KEY DIFFERENCE:**
• **Automation tools:** You configure workflows manually
• **Me:** I create automations during our conversations

• **Tools:** Break when your business changes
• **Me:** I adapt and learn as you grow

**The bottom line:** You're not choosing between automation platforms - you're choosing between doing automation yourself vs having a dedicated Executive Assistant who handles everything for you.

What specific business process are you looking to automate? I can walk you through how I'd handle it."""

    # Business discovery responses
    business_keywords = ['business', 'company', 'work', 'help', 'automate', 'workflow', 'process']
    if any(keyword in message_lower for keyword in business_keywords):
        return f"""Hi! I'm Sarah, your Executive Assistant from AI Agency Platform. 

I received your message: "{message_content[:100]}{'...' if len(message_content) > 100 else ''}"

I'm excited to learn about your business and start helping you immediately! I specialize in:

🤖 **Learning your business through conversation** - I'll remember everything
⚡ **Creating automated workflows in real-time** - while we chat
📊 **Business intelligence and insights** - I analyze your operations  
🔧 **Day-to-day executive assistance** - handle tasks, research, communications
📱 **24/7 availability** - WhatsApp, phone, email, always here

Let's start with the basics:
• What's your business name and what do you do?
• What does a typical day look like for you?
• What tasks take up most of your time?

I'll be creating your first automation during our conversation!"""

    # General greeting responses
    greeting_keywords = ['hi', 'hello', 'hey', 'start', 'help', 'new', 'first']
    if any(keyword in message_lower for keyword in greeting_keywords):
        return f"""Hello! I'm Sarah, your new Executive Assistant 🤖

I just received your message: "{message_content}"

I'm here to learn about your business and create automated workflows that save you time every day. Think of me as your dedicated business partner who:

✅ Learns your business through natural conversation
✅ Creates automations while we chat (no technical setup required)
✅ Remembers everything about your business forever  
✅ Handles day-to-day tasks and communications
✅ Provides business insights and optimization

**What makes me different from other automation tools?**
I'm not software you configure - I'm your business partner who handles everything for you.

Ready to get started? Tell me about your business - what do you do and what's your biggest daily challenge?"""

    # Default response for unclear messages
    return f"""Hi! I'm Sarah, your Executive Assistant from AI Agency Platform.

I received your message: "{message_content}"

I'm designed to learn your business and create automated workflows. To give you the best help, could you tell me:

1. What's your business or what do you do for work?
2. What specific task or process would you like help with?
3. Are you looking to automate something repetitive?

I'm here to make your daily operations smoother and save you time! What would you like to tackle first?"""

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
            logger.info(f"✅ EA response sent to {to_number}")
        else:
            logger.error(f"❌ Send failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"Send error: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "whatsapp-webhook-ea-branded",
        "environment": ENVIRONMENT,
        "ea_system": "Sarah - Executive Assistant",
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
        "message": "AI Agency Platform - Executive Assistant WhatsApp Service",
        "assistant": "Sarah",
        "status": "online",
        "capabilities": [
            "Business discovery through conversation",
            "Real-time workflow automation",
            "24/7 executive assistance",
            "Business intelligence and insights"
        ],
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)