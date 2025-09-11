#!/usr/bin/env python3
"""
Simple Voice EA Test
Test your personal EA with ElevenLabs voice integration
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

async def test_voice_ea():
    """Test your personal voice EA"""
    
    # Check ElevenLabs credentials
    elevenlabs_key = os.getenv('ELEVENLABS_API_KEY')
    if not elevenlabs_key or elevenlabs_key.startswith('sk_'):
        logger.info("✅ ElevenLabs API key found!")
    else:
        logger.error("❌ ElevenLabs API key not found. Check your .env file.")
        return
    
    try:
        # Test ElevenLabs connection
        from elevenlabs import ElevenLabs
        
        client = ElevenLabs(api_key=elevenlabs_key)
        
        # Get available voices
        logger.info("🎤 Testing ElevenLabs connection...")
        voices_response = client.voices.get_all()
        
        if hasattr(voices_response, 'voices'):
            voices = voices_response.voices
        else:
            voices = voices_response
        
        if voices:
            logger.info(f"✅ Connected! Found {len(voices)} voices available")
            logger.info("🎭 Available voices:")
            for voice in voices[:5]:  # Show first 5
                logger.info(f"   - {voice.name} ({voice.voice_id})")
        
        # Test voice generation
        logger.info("\n🗣️ Testing voice generation...")
        
        test_message = "Hey there! I'm your personal Executive Assistant. I'm ready to help you with business strategy, content creation, financial planning, marketing, and so much more. Just tell me what you need and let's get productive together!"
        
        # Generate audio
        audio_generator = client.text_to_speech.convert(
            voice_id="21m00Tcm4TlvDq8ikWAM",  # Default voice (Rachel)
            text=test_message,
            model_id="eleven_multilingual_v2"
        )
        
        # Save audio to file
        audio_file = "/tmp/ea_voice_test.mp3"
        with open(audio_file, "wb") as f:
            for chunk in audio_generator:
                f.write(chunk)
        
        logger.info(f"✅ Voice generated! Audio saved to: {audio_file}")
        logger.info("🎧 You can play this file to hear your EA's voice!")
        
        # Try to play automatically on macOS
        try:
            import subprocess
            subprocess.run(["afplay", audio_file], check=True)
            logger.info("🔊 Playing audio now...")
        except:
            logger.info(f"💡 Run this to hear your EA: afplay {audio_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing voice: {e}")
        return False

async def setup_personal_ea():
    """Setup your personal Executive Assistant"""
    
    logger.info("🤖 Setting up your Personal Executive Assistant...")
    
    try:
        # Import EA components
        from agents.executive_assistant import ExecutiveAssistant, ConversationChannel
        
        # Create your personal EA (no personality_mode parameter)
        ea = ExecutiveAssistant(customer_id="jose-personal")
        
        logger.info("✅ Personal EA initialized!")
        logger.info("🎯 Personality: Premium-Casual")
        logger.info("💼 Ready for: Business Strategy, Content, Finance, Marketing")
        logger.info("🗣️ Voice: ElevenLabs integration active")
        
        # Test a quick conversation
        test_message = "Hey EA, introduce yourself and tell me what you can help with."
        
        logger.info(f"\n💬 Testing conversation...")
        logger.info(f"You: {test_message}")
        
        # Process message
        response = await ea.handle_customer_interaction(
            test_message,
            ConversationChannel.CHAT
        )
        
        logger.info(f"🤖 EA: {response}")
        
        return ea
        
    except Exception as e:
        logger.error(f"❌ Error setting up EA: {e}")
        return None

async def main():
    """Main test function"""
    
    logger.info("🚀 Testing Personal EA with Voice Integration")
    logger.info("=" * 60)
    
    # Test 1: Voice system
    if await test_voice_ea():
        logger.info("✅ Voice system test passed!")
    else:
        logger.error("❌ Voice system test failed!")
        return
    
    logger.info("\n" + "=" * 60)
    
    # Test 2: EA setup
    ea = await setup_personal_ea()
    if ea:
        logger.info("✅ EA setup complete!")
    else:
        logger.error("❌ EA setup failed!")
        return
    
    logger.info("\n" + "=" * 60)
    logger.info("🎉 All tests passed! Your Personal EA is ready!")
    logger.info("\n🔧 Next steps:")
    logger.info("1. 🗣️ Your voice EA can generate speech with ElevenLabs")
    logger.info("2. 💬 Test more conversations with your EA")
    logger.info("3. 🚀 Start using it for real work!")
    logger.info("4. 📱 Add WhatsApp later if you want mobile access")

if __name__ == "__main__":
    asyncio.run(main())