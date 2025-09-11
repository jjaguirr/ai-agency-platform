#!/usr/bin/env python3
"""
Simple WhatsApp Webhook Test
Start webhook server and test locally
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
import logging
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# WhatsApp configuration  
VERIFY_TOKEN = os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')
ACCESS_TOKEN = os.getenv('WHATSAPP_BUSINESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')

@app.route('/webhook/whatsapp', methods=['GET'])
def verify_webhook():
    """Verify webhook for WhatsApp"""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token') 
    challenge = request.args.get('hub.challenge')
    
    logger.info(f"🔍 Webhook verification: mode={mode}, token={token}")
    
    if mode == 'subscribe' and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verified successfully")
        return challenge, 200
    else:
        logger.error("❌ Webhook verification failed")
        return 'Forbidden', 403

@app.route('/webhook/whatsapp', methods=['POST'])
def handle_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        data = request.get_json()
        logger.info(f"📱 Incoming message: {data}")
        
        # Extract message details
        if data and 'entry' in data:
            for entry in data['entry']:
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    
                    for message in messages:
                        from_number = message.get('from')
                        text = message.get('text', {}).get('body', '')
                        
                        logger.info(f"📨 Message from {from_number}: {text}")
                        
                        # Simple auto-reply
                        reply = f"🤖 EA Auto-Reply: I received your message '{text}'. This is a test response!"
                        logger.info(f"🔄 Sending reply: {reply}")
                        
                        # Actually send the reply
                        send_whatsapp_reply(from_number, reply)
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check"""
    return jsonify({
        "status": "healthy",
        "verify_token": VERIFY_TOKEN,
        "access_token_configured": bool(ACCESS_TOKEN)
    })

@app.route('/test')
def test():
    """Test endpoint"""
    return jsonify({"message": "Webhook server is running"})

def send_whatsapp_reply(to_number, message):
    """Send a WhatsApp message via Cloud API"""
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
            logger.info(f"✅ Message sent successfully! ID: {message_id}")
            return message_id
        else:
            logger.error(f"❌ Failed to send message: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error sending WhatsApp message: {e}")
        return None

if __name__ == "__main__":
    logger.info("🚀 Starting Simple WhatsApp Webhook")
    logger.info(f"🔐 Verify Token: {VERIFY_TOKEN}")
    logger.info(f"🔑 Access Token: {'✓' if ACCESS_TOKEN else '✗'}")
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)), debug=False)