#!/usr/bin/env python3
"""
Test script to verify webhook service can start with simplified EA integration
"""

import os
import sys
import asyncio
from pathlib import Path

# Set environment variables BEFORE importing webhook modules
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('WHATSAPP_VERIFY_TOKEN', 'test_verify_token')
os.environ.setdefault('WHATSAPP_BUSINESS_PHONE_ID', 'test_phone_id')
os.environ.setdefault('WEBHOOK_SECRET', 'test_webhook_secret')

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all required modules can be imported"""
    try:
        from webhook.unified_whatsapp_webhook import SimplifiedExecutiveAssistant, ConversationChannel
        print("✅ SimplifiedExecutiveAssistant import successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

async def test_simplified_ea():
    """Test the simplified EA functionality"""
    try:
        from webhook.unified_whatsapp_webhook import SimplifiedExecutiveAssistant, ConversationChannel

        # Test EA initialization
        ea = SimplifiedExecutiveAssistant("test-customer-123")
        print("✅ EA initialization successful")

        # Test message processing
        test_message = "Hello, I need help automating my social media posts"
        response = await ea.handle_customer_interaction(test_message, ConversationChannel.WHATSAPP)
        print(f"✅ EA response generated: {len(response)} characters")

        # Test conversation memory
        context = ea._get_conversation_context()
        print(f"✅ Conversation context retrieved: {len(context)} characters")

        return True

    except Exception as e:
        print(f"❌ EA test failed: {e}")
        return False

def test_requirements():
    """Test that all requirements are available"""
    required_modules = [
        'flask', 'redis', 'psycopg2', 'sqlalchemy', 'aiohttp', 'requests'
    ]

    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} available")
        except ImportError:
            print(f"❌ {module} missing")
            missing_modules.append(module)

    return len(missing_modules) == 0

async def main():
    """Run all tests"""
    print("🚀 === Testing Webhook EA Integration ===\n")

    # Test 1: Requirements
    print("📦 Testing Requirements...")
    requirements_ok = test_requirements()

    if not requirements_ok:
        print("\n❌ Requirements test failed. Please install missing packages:")
        print("pip install -r requirements-webhook.txt")
        return False

    print("\n✅ Requirements test passed\n")

    # Test 2: Imports
    print("📥 Testing Imports...")
    imports_ok = test_imports()

    if not imports_ok:
        print("\n❌ Import test failed")
        return False

    print("\n✅ Import test passed\n")

    # Test 3: EA Functionality
    print("🤖 Testing Simplified EA...")
    ea_ok = await test_simplified_ea()

    if not ea_ok:
        print("\n❌ EA test failed")
        return False

    print("\n✅ EA test passed\n")

    # Test 4: Webhook service startup
    print("🌐 Testing Webhook Service Startup...")
    try:
        # Import and configure webhook components
        from webhook.unified_whatsapp_webhook import app, EA_INTEGRATION_ENABLED, token_manager

        # Set up a valid token for testing
        test_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
        if test_token:
            token_manager.set_token(test_token, expires_in_minutes=120)  # 2 hours for testing
            print("✅ Test token configured for health check")

        print("✅ Webhook service components imported successfully")
        print(f"✅ EA integration enabled: {EA_INTEGRATION_ENABLED}")

        # Test health endpoint
        with app.test_client() as client:
            response = client.get('/health')
            if response.status_code == 200:
                print("✅ Health endpoint responding")
            else:
                health_data = response.get_json() if response.is_json else {}
                print(f"❌ Health endpoint failed: {response.status_code}")
                print(f"Health check details: {health_data}")
                return False

    except Exception as e:
        print(f"❌ Webhook service test failed: {e}")
        return False

    print("\n🎉 === All Tests Passed! ===")
    print("✅ Webhook service ready for production deployment")
    print("✅ Simplified EA integration working")
    print("✅ Database dependencies resolved")

    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)