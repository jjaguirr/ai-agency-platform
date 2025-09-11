#!/usr/bin/env python3
"""
WhatsApp Calling Setup Script
Configure voice calling through WhatsApp Cloud API
"""

import asyncio
import os
import logging
import json
from pathlib import Path
import sys
import aiohttp

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_calling_eligibility():
    """Check if your WhatsApp Business number is eligible for calling"""
    logger.info("📞 Checking WhatsApp Calling Eligibility")
    logger.info("=" * 60)
    
    access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
    phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')
    
    if not access_token:
        logger.error("❌ WHATSAPP_BUSINESS_TOKEN not found")
        return False
    
    try:
        # Get phone number info
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"📱 Phone Number: {data.get('display_phone_number', 'N/A')}")
                    logger.info(f"🆔 ID: {data.get('id', 'N/A')}")
                    logger.info(f"✅ Phone number verified: {data.get('verified_name', 'N/A')}")
                    
                    # Check messaging limit (needed for calling)
                    messaging_limit = data.get('messaging_limit_tier', 'unknown')
                    logger.info(f"💬 Messaging Tier: {messaging_limit}")
                    
                    if messaging_limit == 'TIER_1000' or 'UNLIMITED' in str(messaging_limit):
                        logger.info("✅ Messaging tier sufficient for calling (1,000+)")
                        return True
                    else:
                        logger.warning("⚠️ Need 1,000+ message tier for calling")
                        logger.info("📈 Send more messages to increase tier")
                        return False
                else:
                    error_text = await response.text()
                    logger.error(f"❌ API error: {response.status} - {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Error checking eligibility: {e}")
        return False

async def configure_calling_settings():
    """Configure calling settings for WhatsApp Business number"""
    logger.info("\n⚙️ Configuring WhatsApp Calling Settings")
    logger.info("=" * 60)
    
    access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
    phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')
    
    try:
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}/settings"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Calling configuration
        settings_data = {
            "calling": {
                "enabled": True,
                "callback_enabled": True,
                "business_hours": {
                    "timezone": "America/New_York",
                    "hours": {
                        "monday": {"start": "09:00", "end": "17:00"},
                        "tuesday": {"start": "09:00", "end": "17:00"},
                        "wednesday": {"start": "09:00", "end": "17:00"}, 
                        "thursday": {"start": "09:00", "end": "17:00"},
                        "friday": {"start": "09:00", "end": "17:00"}
                    }
                }
            }
        }
        
        logger.info("📞 Enabling calling with business hours...")
        logger.info(f"🕒 Hours: Monday-Friday 9 AM - 5 PM (EST)")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=settings_data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("✅ Calling settings configured successfully!")
                    logger.info(f"📊 Response: {json.dumps(result, indent=2)}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Failed to configure calling: {response.status}")
                    logger.error(f"Error: {error_text}")
                    
                    # Check if it's a permissions issue
                    if "permission" in error_text.lower():
                        logger.info("💡 Possible fix: Your app may need additional permissions")
                        logger.info("   1. Go to Meta Developer Console")
                        logger.info("   2. Add 'whatsapp_business_calling' permission")
                        logger.info("   3. Submit for review if required")
                    
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Error configuring calling: {e}")
        return False

async def test_call_initiation():
    """Test initiating a call"""
    logger.info("\n📞 Testing Call Initiation")
    logger.info("=" * 60)
    
    access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
    phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID', '782822591574136')
    your_phone = "19496212077"  # Your phone number
    
    # Ask for confirmation
    confirm = input(f"📞 Test call to {your_phone} (+1 949 621-2077)? (y/n): ").strip().lower()
    if confirm != 'y':
        logger.info("⏭️ Skipping call test")
        return True
    
    try:
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}/calls"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        # Call data
        call_data = {
            "messaging_product": "whatsapp",
            "to": your_phone,
            "type": "voice"
        }
        
        logger.info(f"📞 Initiating call to {your_phone}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=call_data) as response:
                if response.status == 200:
                    result = await response.json()
                    call_id = result.get('call_id', 'unknown')
                    
                    logger.info("✅ Call initiated successfully!")
                    logger.info(f"📞 Call ID: {call_id}")
                    logger.info("📱 You should receive a WhatsApp call now!")
                    
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Call failed: {response.status}")
                    logger.error(f"Error: {error_text}")
                    
                    # Parse common errors
                    if "geographic restrictions" in error_text.lower():
                        logger.info("🌍 Geographic restriction: Business-initiated calling not available in your region")
                        logger.info("💡 Try user-initiated calling instead (customer calls your WhatsApp)")
                    elif "messaging limit" in error_text.lower():
                        logger.info("📈 Need higher messaging tier for calling")
                    elif "not enabled" in error_text.lower():
                        logger.info("⚙️ Calling not enabled - run configure_calling_settings first")
                    
                    return False
                    
    except Exception as e:
        logger.error(f"❌ Error testing call: {e}")
        return False

async def setup_call_webhook():
    """Setup webhook for call events"""
    logger.info("\n🔗 Call Webhook Setup")
    logger.info("=" * 60)
    
    logger.info("To receive call events, add to your webhook subscription:")
    logger.info("1. Go to Meta Developer Console > WhatsApp > Configuration")
    logger.info("2. Edit your webhook subscription")
    logger.info("3. Subscribe to additional fields:")
    logger.info("   ✓ calls (call events)")
    logger.info("   ✓ call_status_updates (call status)")
    
    logger.info("\nCall webhook events include:")
    logger.info("• call_initiated - Call started")
    logger.info("• call_ringing - Phone ringing")
    logger.info("• call_answered - Call answered")
    logger.info("• call_ended - Call finished")
    logger.info("• call_failed - Call failed")

async def show_calling_features():
    """Show available calling features"""
    logger.info("\n🎤 WhatsApp Calling Features")
    logger.info("=" * 60)
    
    logger.info("Available calling types:")
    logger.info("1. 📞 Business-initiated calls")
    logger.info("   • You call customers directly")
    logger.info("   • Requires 1,000+ message tier")
    logger.info("   • Geographic restrictions apply")
    
    logger.info("\n2. 👤 User-initiated calls") 
    logger.info("   • Customers call your WhatsApp number")
    logger.info("   • Available globally")
    logger.info("   • No message tier requirement")
    
    logger.info("\n3. 🎙️ Voice messages")
    logger.info("   • Send/receive voice recordings")
    logger.info("   • No special requirements")
    logger.info("   • Works with ElevenLabs integration")
    
    logger.info("\nBest practice for your EA:")
    logger.info("• Start with user-initiated calls")
    logger.info("• Use voice messages for responses")  
    logger.info("• Business-initiated calls for urgent follow-ups")

async def create_call_integration():
    """Create calling integration with EA"""
    logger.info("\n🤖 EA Call Integration")
    logger.info("=" * 60)
    
    # Create a simple call handler example
    call_handler_code = '''
# WhatsApp Call Handler for EA
async def handle_incoming_call(call_data):
    """Handle incoming WhatsApp call"""
    from_number = call_data.get('from')
    call_id = call_data.get('call_id')
    call_status = call_data.get('status')
    
    if call_status == 'call_answered':
        # Call answered - start EA conversation
        await start_voice_conversation(from_number, call_id)
    elif call_status == 'call_ended':
        # Call ended - send follow-up message
        await send_call_summary(from_number, call_id)

async def start_voice_conversation(phone_number, call_id):
    """Start voice conversation with EA"""
    # Initialize EA
    ea = ExecutiveAssistant(customer_id=f"customer_{phone_number}")
    
    # Generate welcome message
    welcome = await ea.handle_customer_interaction(
        "Starting voice call conversation", 
        ConversationChannel.WHATSAPP
    )
    
    # Convert to voice and play
    voice_data = await generate_voice_response(welcome)
    await play_voice_in_call(call_id, voice_data)

async def send_call_summary(phone_number, call_id):
    """Send summary after call ends"""
    summary = f"📞 Call Summary\\n\\nThanks for calling! Here\'s what we discussed:\\n\\n[AI will generate summary based on call transcript]\\n\\nNeed anything else? Just message me!"
    
    await send_whatsapp_message(phone_number, summary)
'''
    
    # Save the example code
    call_handler_file = Path(__file__).parent.parent / "src" / "communication" / "whatsapp_call_handler.py"
    call_handler_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(call_handler_file, 'w') as f:
        f.write(call_handler_code)
    
    logger.info(f"💾 Call handler example saved to: {call_handler_file}")
    logger.info("🔧 Features included:")
    logger.info("• Incoming call detection")
    logger.info("• EA voice conversation")
    logger.info("• Call summary generation")
    logger.info("• Follow-up messaging")

async def main():
    """Main calling setup function"""
    logger.info("📞 WhatsApp Calling Setup")
    logger.info("=" * 60)
    
    # Step 1: Check eligibility
    eligible = await check_calling_eligibility()
    
    # Step 2: Configure calling settings
    if eligible:
        configured = await configure_calling_settings()
    else:
        logger.info("⏭️ Skipping configuration - not eligible yet")
        configured = False
    
    # Step 3: Test call (if configured)
    if configured:
        await test_call_initiation()
    
    # Step 4: Setup webhook for calls
    await setup_call_webhook()
    
    # Step 5: Show calling features
    await show_calling_features()
    
    # Step 6: Create EA integration
    await create_call_integration()
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 WhatsApp Calling Setup Summary:")
    logger.info(f"   Eligibility Check: {'✅' if eligible else '❌'}")
    logger.info(f"   Settings Configured: {'✅' if configured else '❌'}")
    logger.info("   Webhook Setup: 📋 Manual step required")
    logger.info("   EA Integration: 💾 Example code created")
    
    if not eligible:
        logger.info("\n📈 To enable calling:")
        logger.info("1. Send 1,000+ WhatsApp messages")
        logger.info("2. Wait for tier upgrade")
        logger.info("3. Re-run this setup")
    elif configured:
        logger.info("\n🎉 WhatsApp calling is configured!")
        logger.info("📞 Test by calling your WhatsApp Business number")
        logger.info("🤖 Your EA can now handle voice conversations")
    else:
        logger.info("\n⚙️ Complete webhook configuration to enable calling")

if __name__ == "__main__":
    asyncio.run(main())