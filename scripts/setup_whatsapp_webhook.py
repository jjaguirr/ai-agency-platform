#!/usr/bin/env python3
"""
WhatsApp Webhook Setup Script
Sets up webhook server and ngrok for local testing
"""

import asyncio
import os
import logging
import subprocess
import time
import requests
import json
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_ngrok_installed():
    """Check if ngrok is installed"""
    try:
        result = subprocess.run(['ngrok', 'version'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"✅ ngrok installed: {result.stdout.strip()}")
            return True
        else:
            return False
    except FileNotFoundError:
        return False

def install_ngrok_macos():
    """Install ngrok on macOS"""
    logger.info("📦 Installing ngrok with Homebrew...")
    try:
        # Check if brew is installed
        subprocess.run(['brew', '--version'], check=True, capture_output=True)
        
        # Install ngrok
        result = subprocess.run(['brew', 'install', 'ngrok'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("✅ ngrok installed successfully")
            return True
        else:
            logger.error(f"❌ Failed to install ngrok: {result.stderr}")
            return False
            
    except subprocess.CalledProcessError:
        logger.error("❌ Homebrew not found. Please install from https://brew.sh/")
        return False
    except FileNotFoundError:
        logger.error("❌ Homebrew not found. Please install from https://brew.sh/")
        return False

def start_webhook_server():
    """Start the WhatsApp webhook server"""
    logger.info("🚀 Starting WhatsApp webhook server...")
    
    webhook_script = Path(__file__).parent.parent / "src" / "webhook" / "whatsapp_webhook.py"
    
    try:
        # Start webhook server in background
        process = subprocess.Popen([
            sys.executable, str(webhook_script)
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Wait a moment for server to start
        time.sleep(3)
        
        # Check if server is running
        try:
            response = requests.get('http://localhost:8000/health', timeout=5)
            if response.status_code == 200:
                logger.info("✅ Webhook server started successfully")
                return process
            else:
                logger.error("❌ Webhook server health check failed")
                return None
        except requests.exceptions.RequestException:
            logger.error("❌ Webhook server not responding")
            return None
            
    except Exception as e:
        logger.error(f"❌ Failed to start webhook server: {e}")
        return None

def start_ngrok():
    """Start ngrok tunnel"""
    logger.info("🌐 Starting ngrok tunnel...")
    
    try:
        # Start ngrok for port 8000
        process = subprocess.Popen([
            'ngrok', 'http', '8000', '--log=stdout'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Wait for ngrok to start
        time.sleep(5)
        
        # Get ngrok URL
        try:
            response = requests.get('http://localhost:4040/api/tunnels', timeout=5)
            if response.status_code == 200:
                tunnels = response.json().get('tunnels', [])
                for tunnel in tunnels:
                    if tunnel.get('proto') == 'https':
                        public_url = tunnel.get('public_url')
                        logger.info(f"✅ ngrok tunnel active: {public_url}")
                        return process, public_url
                        
            logger.error("❌ Could not get ngrok URL")
            return None, None
            
        except requests.exceptions.RequestException:
            logger.error("❌ ngrok API not responding")
            return None, None
            
    except Exception as e:
        logger.error(f"❌ Failed to start ngrok: {e}")
        return None, None

def configure_webhook_in_meta(webhook_url: str):
    """Show instructions to configure webhook in Meta Developer Console"""
    logger.info("\n🔗 Webhook Configuration Instructions")
    logger.info("=" * 60)
    
    logger.info("1. Go to Meta Developer Console:")
    logger.info("   https://developers.facebook.com/apps/")
    
    logger.info("\n2. Select your WhatsApp Business app")
    
    logger.info("\n3. Go to WhatsApp > Configuration")
    
    logger.info("\n4. In the Webhook section, click 'Edit'")
    
    logger.info(f"\n5. Enter webhook URL:")
    logger.info(f"   {webhook_url}/webhook/whatsapp")
    
    logger.info(f"\n6. Enter verify token:")
    logger.info(f"   {os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')}")
    
    logger.info("\n7. Click 'Verify and Save'")
    
    logger.info("\n8. Subscribe to webhook fields:")
    logger.info("   ✓ messages")
    logger.info("   ✓ message_deliveries (optional)")
    logger.info("   ✓ message_reads (optional)")
    
    logger.info("\n9. Click 'Save'")
    
    logger.info("\n🔄 Test your webhook:")
    logger.info(f"   Send a WhatsApp message to: +1 555 149 6402")
    logger.info(f"   From your phone: +1 (949) 621-2077")

def test_webhook_locally():
    """Test webhook with a sample payload"""
    logger.info("\n🧪 Testing webhook locally...")
    
    # Sample WhatsApp message payload
    test_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15551496402",
                        "phone_number_id": "782822591574136"
                    },
                    "messages": [{
                        "from": "19496212077",
                        "id": "wamid.test123",
                        "timestamp": "1234567890",
                        "text": {
                            "body": "Hello EA! This is a test message."
                        },
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    
    try:
        response = requests.post(
            'http://localhost:8000/webhook/whatsapp',
            json=test_payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info("✅ Local webhook test successful")
            logger.info(f"Response: {response.json()}")
            return True
        else:
            logger.error(f"❌ Local webhook test failed: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Local webhook test error: {e}")
        return False

async def main():
    """Main setup function"""
    logger.info("🚀 WhatsApp Webhook Setup")
    logger.info("=" * 60)
    
    # Check prerequisites
    access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
    phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID')
    
    if not access_token or not phone_number_id:
        logger.error("❌ Missing WhatsApp credentials")
        logger.error("Required: WHATSAPP_BUSINESS_TOKEN, WHATSAPP_BUSINESS_PHONE_ID")
        return
    
    logger.info("✅ WhatsApp credentials found")
    
    # Check/install ngrok
    if not check_ngrok_installed():
        logger.info("📦 ngrok not found, installing...")
        if not install_ngrok_macos():
            logger.error("❌ Failed to install ngrok")
            return
    
    # Start webhook server
    webhook_process = start_webhook_server()
    if not webhook_process:
        logger.error("❌ Failed to start webhook server")
        return
    
    # Test webhook locally
    if test_webhook_locally():
        logger.info("✅ Local webhook working")
    else:
        logger.warning("⚠️ Local webhook test failed")
    
    # Start ngrok
    ngrok_process, public_url = start_ngrok()
    if not public_url:
        logger.error("❌ Failed to start ngrok tunnel")
        webhook_process.terminate()
        return
    
    # Show configuration instructions
    configure_webhook_in_meta(public_url)
    
    logger.info("\n" + "=" * 60)
    logger.info("🎉 Webhook setup complete!")
    logger.info(f"🌐 Public URL: {public_url}")
    logger.info(f"🔗 Webhook endpoint: {public_url}/webhook/whatsapp")
    logger.info("📱 Ready to receive WhatsApp messages!")
    
    # Keep running
    try:
        logger.info("\n⏸️ Press Ctrl+C to stop servers...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n🛑 Stopping servers...")
        if webhook_process:
            webhook_process.terminate()
        if ngrok_process:
            ngrok_process.terminate()
        logger.info("✅ Servers stopped")

if __name__ == "__main__":
    asyncio.run(main())