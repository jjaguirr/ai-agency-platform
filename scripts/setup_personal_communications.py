#!/usr/bin/env python3
"""
Personal EA Communication Setup
Setup WhatsApp, Email, and Voice calling for your personal EA
"""

import asyncio
import os
import logging
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def setup_whatsapp_communication():
    """Setup WhatsApp for your personal EA"""
    logger.info("🟢 Setting up WhatsApp Communication...")
    
    try:
        from communication.whatsapp_manager import WhatsAppBusinessManager
        
        # Initialize manager
        manager = WhatsAppBusinessManager()
        
        # Create database tables if needed
        await manager.create_database_tables()
        
        # Setup for your personal account
        your_phone = input("📱 Enter your phone number (e.g., +1234567890): ").strip()
        if not your_phone:
            logger.error("Phone number required for WhatsApp setup")
            return False
        
        # Provision WhatsApp instantly
        result = await manager.provision_customer_whatsapp_instantly(
            customer_id="jose-personal",
            phone_number=your_phone
        )
        
        if result.get("status") == "provisioned" or result.get("status") == "provisioned_slow":
            logger.info(f"✅ WhatsApp provisioned successfully!")
            logger.info(f"📱 Your number: {your_phone}")
            logger.info(f"🤖 WhatsApp number: {result.get('whatsapp_number')}")
            logger.info(f"🌐 Webhook URL: {result.get('webhook_url')}")
            logger.info(f"⏱️ Setup time: {result.get('provisioning_time_seconds'):.2f}s")
            
            if result.get("welcome_message_sent"):
                logger.info("💬 Welcome message sent to your WhatsApp!")
            
            return True
        else:
            logger.error(f"❌ WhatsApp setup failed: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"❌ WhatsApp setup error: {e}")
        return False

async def setup_email_communication():
    """Setup email for your personal EA"""
    logger.info("📧 Setting up Email Communication...")
    
    try:
        from communication.email_channel import EmailChannel
        
        # Get your email configuration
        your_email = input("📧 Enter your email address: ").strip()
        if not your_email:
            logger.error("Email address required")
            return False
        
        # Email configuration
        email_config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'smtp_username': your_email,
            'smtp_password': os.getenv('GMAIL_APP_PASSWORD'),  # Use app password for Gmail
            'smtp_use_tls': True,
            'imap_server': 'imap.gmail.com',
            'imap_port': 993,
            'from_email': your_email
        }
        
        # If no Gmail app password, prompt for it
        if not email_config['smtp_password']:
            print("\n⚠️  Gmail App Password required!")
            print("1. Go to Google Account Settings > Security > 2-Step Verification")
            print("2. Generate an 'App Password' for this application")
            print("3. Add GMAIL_APP_PASSWORD=your_app_password to your .env file")
            
            app_password = input("📧 Enter Gmail App Password (or press Enter to skip): ").strip()
            if app_password:
                email_config['smtp_password'] = app_password
            else:
                logger.info("⏭️ Email setup skipped - configure GMAIL_APP_PASSWORD later")
                return True
        
        # Initialize email channel
        email_channel = EmailChannel("jose-personal", email_config)
        
        # Test connection
        if await email_channel.initialize():
            logger.info("✅ Email channel initialized successfully!")
            
            # Send test email to yourself
            test_message = """Hi! This is your personal Executive Assistant testing email communication.

I'm ready to help you with:
• 📅 Calendar management and scheduling
• 📧 Email organization and responses  
• 📊 Business strategy and planning
• 💰 Financial analysis and reporting
• 📝 Content creation and marketing
• 🤖 Workflow automation

Reply to this email to start a conversation with your EA!

Best regards,
Sarah - Your Personal Executive Assistant"""
            
            try:
                message_id = await email_channel.send_message(
                    to_email=your_email,
                    content=test_message,
                    subject="🤖 Your Personal EA is Ready! - Email Test"
                )
                logger.info(f"✅ Test email sent! Message ID: {message_id}")
                logger.info(f"📧 Check your inbox at: {your_email}")
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to send test email: {e}")
                return False
        else:
            logger.error("❌ Failed to initialize email channel")
            return False
            
    except Exception as e:
        logger.error(f"❌ Email setup error: {e}")
        return False

async def setup_voice_calling():
    """Setup voice calling for your personal EA"""
    logger.info("🎤 Setting up Voice Calling...")
    
    try:
        from communication.voice_channel import ElevenLabsVoiceChannel
        from communication.voice_channel import VoiceLanguage
        
        # Check if ElevenLabs is available
        elevenlabs_key = os.getenv('ELEVENLABS_API_KEY')
        if not elevenlabs_key:
            logger.error("❌ ELEVENLABS_API_KEY not found in environment")
            return False
        
        # Initialize voice channel
        voice_config = {
            "elevenlabs_api_key": elevenlabs_key,
            "whisper_model": "base"
        }
        
        voice_channel = ElevenLabsVoiceChannel("jose-personal", voice_config)
        
        if await voice_channel.initialize():
            logger.info("✅ Voice channel initialized successfully!")
            
            # Test voice generation
            test_message = "Hi Jose! This is your personal Executive Assistant. Voice calling is now set up and ready. I can help you with business tasks through voice conversations. Just call me anytime!"
            
            logger.info("🎤 Generating test voice message...")
            audio_data = await voice_channel.generate_voice_response(
                test_message, 
                VoiceLanguage.ENGLISH,
                {"conversation_type": "onboarding"}
            )
            
            if audio_data:
                # Save test audio
                audio_file = "/tmp/ea_voice_calling_test.mp3"
                with open(audio_file, "wb") as f:
                    f.write(audio_data)
                
                logger.info(f"✅ Voice test generated! ({len(audio_data)} bytes)")
                logger.info(f"🎧 Audio saved to: {audio_file}")
                
                # Try to play on macOS
                try:
                    import subprocess
                    subprocess.run(["afplay", audio_file], check=True)
                    logger.info("🔊 Playing voice test...")
                except:
                    logger.info(f"💡 Run this to hear the test: afplay {audio_file}")
                
                return True
            else:
                logger.error("❌ Failed to generate test voice")
                return False
        else:
            logger.error("❌ Failed to initialize voice channel")
            return False
            
    except Exception as e:
        logger.error(f"❌ Voice setup error: {e}")
        return False

async def test_ea_integration():
    """Test EA integration with all communication channels"""
    logger.info("🤖 Testing EA Integration...")
    
    try:
        from agents.executive_assistant import ExecutiveAssistant, ConversationChannel
        
        # Initialize your personal EA
        ea = ExecutiveAssistant(customer_id="jose-personal")
        
        # Test conversation
        test_message = "Hey EA! I just set up WhatsApp, email, and voice calling. Can you confirm all communication channels are working and tell me how to contact you?"
        
        logger.info(f"💬 Testing EA conversation...")
        logger.info(f"You: {test_message}")
        
        response = await ea.handle_customer_interaction(
            test_message,
            ConversationChannel.CHAT
        )
        
        logger.info(f"🤖 EA: {response}")
        
        # Show available communication methods
        logger.info("\n📞 Available Communication Channels:")
        logger.info("1. 📱 WhatsApp - Send messages to your configured WhatsApp number")
        logger.info("2. 📧 Email - Send emails to your configured email address")  
        logger.info("3. 🎤 Voice - Voice calls and voice messages")
        logger.info("4. 💬 Chat - Direct chat interface (existing)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ EA integration test failed: {e}")
        return False

async def main():
    """Main setup function"""
    logger.info("🚀 Setting up Personal EA Communications")
    logger.info("=" * 60)
    
    # Setup results
    results = {
        "whatsapp": False,
        "email": False, 
        "voice": False,
        "ea_integration": False
    }
    
    # 1. WhatsApp Setup
    results["whatsapp"] = await setup_whatsapp_communication()
    
    logger.info("\n" + "=" * 60)
    
    # 2. Email Setup  
    results["email"] = await setup_email_communication()
    
    logger.info("\n" + "=" * 60)
    
    # 3. Voice Setup
    results["voice"] = await setup_voice_calling()
    
    logger.info("\n" + "=" * 60)
    
    # 4. EA Integration Test
    results["ea_integration"] = await test_ea_integration()
    
    # Final Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 Setup Summary:")
    
    for channel, success in results.items():
        status = "✅ Ready" if success else "❌ Failed"
        logger.info(f"   {channel.title()}: {status}")
    
    successful_channels = sum(results.values())
    
    if successful_channels >= 3:
        logger.info("\n🎉 Personal EA Communications Setup Complete!")
        logger.info("🚀 Your EA is ready for multi-channel communication!")
        
        logger.info("\n📞 How to contact your EA:")
        if results["whatsapp"]:
            logger.info("• 📱 WhatsApp: Message your configured number")
        if results["email"]:
            logger.info("• 📧 Email: Send emails to your configured address")
        if results["voice"]:
            logger.info("• 🎤 Voice: Voice calls and messages")
        if results["ea_integration"]:
            logger.info("• 💬 Chat: Direct chat interface")
        
    else:
        logger.info(f"\n⚠️ Only {successful_channels}/4 channels configured")
        logger.info("Check the errors above and try running the setup again")

if __name__ == "__main__":
    asyncio.run(main())