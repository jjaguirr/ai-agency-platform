#!/usr/bin/env python3
"""
WhatsApp Webhook Testing Script
Tests the webhook service with mock WhatsApp payloads
"""

import asyncio
import json
import requests
import time
import sys
from datetime import datetime
from typing import Dict, Any

# Mock WhatsApp webhook payloads
MOCK_PAYLOADS = {
    "text_message": {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "19496212077",
                                "phone_number_id": "782822591574136"
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "19496212077"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "19496212077",
                                    "id": f"wamid.test_{int(time.time())}",
                                    "timestamp": str(int(time.time())),
                                    "text": {"body": "Hello, I need help with my business automation"},
                                    "type": "text"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    },

    "voice_message": {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "19496212077",
                                "phone_number_id": "782822591574136"
                            },
                            "messages": [
                                {
                                    "from": "19496212077",
                                    "id": f"wamid.voice_{int(time.time())}",
                                    "timestamp": str(int(time.time())),
                                    "type": "audio",
                                    "audio": {
                                        "id": "mock_audio_id_123",
                                        "mime_type": "audio/ogg; codecs=opus"
                                    }
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    },

    "status_update": {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "19496212077",
                                "phone_number_id": "782822591574136"
                            },
                            "statuses": [
                                {
                                    "id": f"wamid.status_{int(time.time())}",
                                    "status": "delivered",
                                    "timestamp": str(int(time.time())),
                                    "recipient_id": "19496212077"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }
}

class WhatsAppTester:
    def __init__(self, webhook_url: str = "http://localhost:8000"):
        self.webhook_url = webhook_url
        self.verify_token = "ai_agency_platform_verify"

    def test_webhook_verification(self) -> bool:
        """Test webhook verification endpoint"""
        print("🔍 Testing webhook verification...")

        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": self.verify_token,
            "hub.challenge": "test_challenge_123"
        }

        try:
            response = requests.get(f"{self.webhook_url}/webhook/whatsapp", params=params)

            if response.status_code == 200 and response.text == "test_challenge_123":
                print("✅ Webhook verification successful")
                return True
            else:
                print(f"❌ Webhook verification failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ Webhook verification error: {e}")
            return False

    def test_health_check(self) -> bool:
        """Test health check endpoint"""
        print("💓 Testing health check...")

        try:
            response = requests.get(f"{self.webhook_url}/health")

            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ Health check successful: {health_data.get('status', 'unknown')}")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False

    def send_mock_message(self, message_type: str) -> bool:
        """Send mock WhatsApp message"""
        print(f"📱 Testing {message_type} message...")

        if message_type not in MOCK_PAYLOADS:
            print(f"❌ Unknown message type: {message_type}")
            return False

        payload = MOCK_PAYLOADS[message_type]

        try:
            response = requests.post(
                f"{self.webhook_url}/webhook/whatsapp",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "MockWhatsAppCloudAPI/1.0"
                }
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ {message_type} message processed: {result.get('status', 'unknown')}")
                return True
            else:
                print(f"❌ {message_type} message failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ {message_type} message error: {e}")
            return False

    def test_ea_client_registration(self) -> bool:
        """Test EA client registration"""
        print("🤖 Testing EA client registration...")

        client_data = {
            "client_id": "test-client-123",
            "customer_id": "test-customer",
            "phone_number": "19496212077",
            "mcp_endpoint": "http://localhost:8001/mcp",
            "auth_token": "test-auth-token-123"
        }

        try:
            # Register client
            response = requests.post(
                f"{self.webhook_url}/ea/register",
                json=client_data,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 201:
                result = response.json()
                print(f"✅ EA client registration successful: {result}")

                # List clients
                list_response = requests.get(f"{self.webhook_url}/ea/clients")
                if list_response.status_code == 200:
                    clients = list_response.json()
                    print(f"📋 Active clients: {clients.get('count', 0)}")

                # Unregister client
                unreg_response = requests.delete(f"{self.webhook_url}/ea/unregister/test-client-123")
                if unreg_response.status_code == 200:
                    print("✅ EA client unregistration successful")
                    return True
                else:
                    print(f"⚠️ EA client unregistration failed: {unreg_response.status_code}")
                    return False
            else:
                print(f"❌ EA client registration failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ EA client registration error: {e}")
            return False

    def run_comprehensive_test(self):
        """Run comprehensive test suite"""
        print("🧪 Running Comprehensive WhatsApp Webhook Tests")
        print("=" * 50)

        tests = [
            ("Health Check", self.test_health_check),
            ("Webhook Verification", self.test_webhook_verification),
            ("EA Client Registration", self.test_ea_client_registration),
            ("Text Message", lambda: self.send_mock_message("text_message")),
            ("Voice Message", lambda: self.send_mock_message("voice_message")),
            ("Status Update", lambda: self.send_mock_message("status_update")),
        ]

        results = []

        for test_name, test_func in tests:
            print(f"\n--- {test_name} ---")
            try:
                success = test_func()
                results.append((test_name, success))
            except Exception as e:
                print(f"❌ {test_name} failed with exception: {e}")
                results.append((test_name, False))

            time.sleep(1)  # Brief pause between tests

        # Summary
        print("\n" + "=" * 50)
        print("🎯 Test Summary:")
        print("-" * 20)

        passed = 0
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"  {status} {test_name}")
            if success:
                passed += 1

        print(f"\n📊 Results: {passed}/{len(results)} tests passed")

        if passed == len(results):
            print("🎉 All tests passed! WhatsApp webhook is ready for production.")
            return True
        else:
            print("⚠️ Some tests failed. Please review the output above.")
            return False

def main():
    """Main testing function"""
    import argparse

    parser = argparse.ArgumentParser(description="Test WhatsApp webhook service")
    parser.add_argument("--url", default="http://localhost:8000", help="Webhook service URL")
    parser.add_argument("--test", choices=["health", "verify", "message", "register", "all"],
                       default="all", help="Specific test to run")
    parser.add_argument("--message-type", choices=["text_message", "voice_message", "status_update"],
                       default="text_message", help="Message type for message test")

    args = parser.parse_args()

    tester = WhatsAppTester(args.url)

    if args.test == "health":
        success = tester.test_health_check()
    elif args.test == "verify":
        success = tester.test_webhook_verification()
    elif args.test == "message":
        success = tester.send_mock_message(args.message_type)
    elif args.test == "register":
        success = tester.test_ea_client_registration()
    else:
        success = tester.run_comprehensive_test()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()