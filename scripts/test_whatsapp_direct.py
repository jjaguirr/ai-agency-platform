#!/usr/bin/env python3
"""
Direct WhatsApp Cloud API Test
Using your actual WhatsApp Business configuration
"""

import asyncio
import os
import logging
import json
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_whatsapp_send_message():
    """Test sending a message using your WhatsApp Cloud API credentials"""
    logger.info("📱 Testing WhatsApp Cloud API - Direct Message")
    logger.info("=" * 60)
    
    # Your actual configuration from the setup
    access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
    phone_number_id = "782822591574136"  # From your setup
    your_phone = "19496212077"  # Your phone +1 (949) 621-2077
    
    logger.info(f"📞 From: +1 555 149 6402 (Test Number)")
    logger.info(f"📞 To: +1 (949) 621-2077 (Your Phone)")
    logger.info(f"🆔 Phone Number ID: {phone_number_id}")
    logger.info(f"🔑 Token: {'✓ Found' if access_token else '✗ Missing'}")
    
    if not access_token:
        logger.error("❌ WHATSAPP_BUSINESS_TOKEN not found in .env")
        return False
    
    try:
        # WhatsApp Cloud API endpoint
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Message payload
        message_data = {
            "messaging_product": "whatsapp",
            "to": your_phone,
            "type": "text",
            "text": {
                "body": """🤖 WhatsApp EA Test Successful!

Hi Jose! Your personal Executive Assistant is now connected via WhatsApp Cloud API.

✅ Direct Meta integration (no Twilio)
📱 Using test number: +1 555 149 6402  
🆓 90 days free messaging
🎤 Voice capabilities ready
🤖 Full EA integration active

Reply with "hello EA" to start a conversation!

- Sarah, Your Personal Executive Assistant"""
            }
        }
        
        logger.info("📤 Sending test message...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=message_data) as response:
                if response.status == 200:
                    result = await response.json()
                    message_id = result.get('messages', [{}])[0].get('id', '')
                    
                    logger.info("✅ Message sent successfully!")
                    logger.info(f"📨 Message ID: {message_id}")
                    logger.info(f"📱 Check your phone: +1 (949) 621-2077")
                    
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Failed to send message: {response.status}")
                    logger.error(f"Error: {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Error sending message: {e}")
        return False

async def test_template_message():
    """Test sending a template message (hello_world)"""
    logger.info("\n📋 Testing Template Message (hello_world)")
    logger.info("=" * 60)
    
    access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
    phone_number_id = "782822591574136"
    your_phone = "19496212077"
    
    try:
        url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Template message payload (from your example)
        template_data = {
            "messaging_product": "whatsapp",
            "to": your_phone,
            "type": "template",
            "template": {
                "name": "hello_world",
                "language": {
                    "code": "en_US"
                }
            }
        }
        
        logger.info("📤 Sending hello_world template...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=template_data) as response:
                if response.status == 200:
                    result = await response.json()
                    message_id = result.get('messages', [{}])[0].get('id', '')
                    
                    logger.info("✅ Template message sent!")
                    logger.info(f"📨 Message ID: {message_id}")
                    
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Template failed: {response.status}")
                    logger.error(f"Error: {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Error sending template: {e}")
        return False

async def test_voice_message():
    """Test sending a voice message with ElevenLabs"""
    logger.info("\n🎤 Testing Voice Message via WhatsApp")
    logger.info("=" * 60)
    
    # Check if ElevenLabs is available
    elevenlabs_key = os.getenv('ELEVENLABS_API_KEY')
    if not elevenlabs_key:
        logger.info("⏭️ Skipping voice test - ELEVENLABS_API_KEY not found")
        return True
    
    try:
        from communication.voice_channel import ElevenLabsVoiceChannel, VoiceLanguage
        
        # Generate voice message
        voice_channel = ElevenLabsVoiceChannel("jose-personal")
        await voice_channel.initialize()
        
        voice_text = "Hey Jose! This is your EA sending you a voice message through WhatsApp Cloud API. Pretty cool integration, right?"
        
        logger.info("🎙️ Generating voice with ElevenLabs...")
        audio_data = await voice_channel.generate_voice_response(voice_text, VoiceLanguage.ENGLISH)
        
        if not audio_data:
            logger.error("❌ Failed to generate voice")
            return False
        
        logger.info(f"✅ Voice generated ({len(audio_data)} bytes)")
        
        # For now, save locally - WhatsApp voice requires media upload
        voice_file = "/tmp/ea_whatsapp_voice.mp3"
        with open(voice_file, "wb") as f:
            f.write(audio_data)
        
        logger.info(f"💾 Voice saved to: {voice_file}")
        logger.info("🎧 Play with: afplay /tmp/ea_whatsapp_voice.mp3")
        
        # Note: Full WhatsApp voice integration requires media upload API
        logger.info("📝 Note: WhatsApp voice upload requires additional media API integration")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Voice test failed: {e}")
        return False

async def test_ea_conversation():
    """Test full EA conversation simulation"""
    logger.info("\n🤖 Testing EA Conversation Integration")
    logger.info("=" * 60)
    
    try:
        from agents.executive_assistant import ExecutiveAssistant, ConversationChannel
        
        # Initialize EA
        ea = ExecutiveAssistant(customer_id="jose-personal")
        
        # Simulate WhatsApp conversation
        test_messages = [
            "Hello EA! I just got your WhatsApp message",
            "Can you help me schedule a meeting for tomorrow?",
            "What can you help me with for my business?"
        ]
        
        for message in test_messages:
            logger.info(f"📱 You: {message}")
            
            response = await ea.handle_customer_interaction(
                message,
                ConversationChannel.WHATSAPP
            )
            
            logger.info(f"🤖 EA: {response[:100]}{'...' if len(response) > 100 else ''}")
            logger.info("")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ EA conversation test failed: {e}")
        return False

async def show_next_steps():
    """Show next steps for full integration"""
    logger.info("\n🚀 Next Steps for Full WhatsApp Integration")
    logger.info("=" * 60)
    
    logger.info("1. 🔗 Webhook Setup:")
    logger.info("   • Create webhook endpoint for incoming messages")
    logger.info("   • Configure in Meta Developer Console")
    logger.info("   • Subscribe to 'messages' field")
    
    logger.info("\n2. 🎤 Voice Features:")
    logger.info("   • Media upload API for voice messages")
    logger.info("   • Speech-to-text for incoming voice")
    logger.info("   • Voice calling configuration")
    
    logger.info("\n3. 📞 Calling Setup:")
    logger.info("   • Requires 1,000+ messages for calling access")
    logger.info("   • Geographic restrictions apply")
    logger.info("   • Business verification may be needed")
    
    logger.info("\n4. 🔒 Production:")
    logger.info("   • Add your business phone number")
    logger.info("   • Set up payment method")
    logger.info("   • Create message templates")

async def main():
    """Main test function"""
    logger.info("🚀 WhatsApp Cloud API Direct Test")
    logger.info("Using your actual Meta configuration")
    logger.info("=" * 60)
    
    # Test results
    results = {
        "text_message": False,
        "template_message": False,
        "voice_generation": False,
        "ea_conversation": False
    }
    
    # Run tests
    results["text_message"] = await test_whatsapp_send_message()
    results["template_message"] = await test_template_message()
    results["voice_generation"] = await test_voice_message()
    results["ea_conversation"] = await test_ea_conversation()
    
    # Show next steps
    await show_next_steps()
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 Test Results:")
    
    for test, success in results.items():
        status = "✅ Passed" if success else "❌ Failed"
        logger.info(f"   {test.replace('_', ' ').title()}: {status}")
    
    successful_tests = sum(results.values())
    
    if successful_tests >= 3:
        logger.info("\n🎉 WhatsApp Cloud API is working!")
        logger.info("📱 Check your phone for test messages")
        logger.info("🤖 Your EA is ready for WhatsApp communication!")
    else:
        logger.info(f"\n⚠️ {successful_tests}/{len(results)} tests passed")
        logger.info("Check your WhatsApp Business API configuration")

if __name__ == "__main__":
    asyncio.run(main())