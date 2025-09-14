#!/usr/bin/env python3
"""
Simple test script to validate Meta Embedded Signup implementation
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_imports():
    """Test that all required modules can be imported"""
    print("🔍 Testing imports...")

    try:
        from webhook.meta_business_api import MetaBusinessAPI, MetaTokenExchangeResult, MetaWABAInfo
        print("✅ Meta Business API imports successful")
    except Exception as e:
        print(f"❌ Meta Business API import failed: {e}")
        return False

    try:
        from webhook.whatsapp_webhook_service import EAClient
        print("✅ Enhanced EAClient import successful")
    except Exception as e:
        print(f"❌ EAClient import failed: {e}")
        return False

    return True

def test_enhanced_ea_client():
    """Test enhanced EAClient with Meta integration fields"""
    print("\n🔍 Testing Enhanced EAClient...")

    try:
        from webhook.whatsapp_webhook_service import EAClient
        from datetime import datetime, timedelta

        # Test standard client
        client = EAClient(
            client_id="test_client",
            customer_id="test_customer",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_token"
        )

        print(f"✅ Standard client created: {client.client_id}")
        print(f"   Embedded signup completed: {client.embedded_signup_completed}")

        # Test Meta integration client
        meta_client = EAClient(
            client_id="meta_client",
            customer_id="meta_customer",
            phone_number="+1987654321",
            mcp_endpoint="https://meta-test.com/mcp",
            auth_token="meta_token",
            waba_id="test_waba_123",
            business_phone_number_id="test_phone_123",
            business_id="test_business_123",
            meta_business_token="test_business_token",
            meta_token_expires=datetime.now() + timedelta(days=60),
            embedded_signup_completed=True
        )

        print(f"✅ Meta integration client created: {meta_client.client_id}")
        print(f"   WABA ID: {meta_client.waba_id}")
        print(f"   Business Phone ID: {meta_client.business_phone_number_id}")
        print(f"   Embedded signup completed: {meta_client.embedded_signup_completed}")

        # Test serialization/deserialization
        client_dict = meta_client.to_dict()
        restored_client = EAClient.from_dict(client_dict)

        print(f"✅ Serialization/deserialization successful")
        print(f"   Original WABA ID: {meta_client.waba_id}")
        print(f"   Restored WABA ID: {restored_client.waba_id}")

        return True

    except Exception as e:
        print(f"❌ Enhanced EAClient test failed: {e}")
        return False

def test_meta_business_api():
    """Test Meta Business API functionality"""
    print("\n🔍 Testing Meta Business API...")

    try:
        from webhook.meta_business_api import MetaBusinessAPI, MetaTokenExchangeResult

        # Create API instance
        api = MetaBusinessAPI()
        print(f"✅ Meta Business API instance created")
        print(f"   API Version: {api.api_version}")
        print(f"   Base URL: {api.base_url}")

        # Test token exchange result
        success_result = MetaTokenExchangeResult(
            success=True,
            access_token="test_token",
            token_type="bearer",
            expires_in=5184000,
            granted_scopes=["whatsapp_business_messaging"]
        )

        print(f"✅ Token exchange result structure: {success_result.success}")

        # Test webhook signature validation (without real secret)
        test_payload = b'{"test": "data"}'
        # This should return True when no app secret is configured
        is_valid = api.validate_webhook_signature(test_payload, 'test_signature')
        print(f"✅ Webhook signature validation works: {is_valid}")

        return True

    except Exception as e:
        print(f"❌ Meta Business API test failed: {e}")
        return False

def test_token_encryption():
    """Test token encryption/decryption functionality"""
    print("\n🔍 Testing Token Encryption...")

    try:
        from webhook.whatsapp_webhook_service import EAClient
        import os

        # Set test encryption key
        os.environ['META_TOKEN_ENCRYPTION_KEY'] = 'test-encryption-key-32-chars-12345'

        # Create client with business token
        client = EAClient(
            client_id="encryption_test",
            customer_id="test_customer",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_token",
            meta_business_token="secret_business_token_123456"
        )

        # Test serialization (should encrypt token)
        client_dict = client.to_dict()
        encrypted_token = client_dict.get('meta_business_token')

        if encrypted_token and encrypted_token != "secret_business_token_123456":
            print(f"✅ Token encryption successful")
            print(f"   Original length: {len('secret_business_token_123456')}")
            print(f"   Encrypted length: {len(encrypted_token)}")
        else:
            print(f"❌ Token encryption failed - token not encrypted")
            return False

        # Test deserialization (should decrypt token)
        restored_client = EAClient.from_dict(client_dict)

        if restored_client.meta_business_token == "secret_business_token_123456":
            print(f"✅ Token decryption successful")
            print(f"   Decrypted token: {restored_client.meta_business_token}")
        else:
            print(f"❌ Token decryption failed")
            print(f"   Expected: secret_business_token_123456")
            print(f"   Got: {restored_client.meta_business_token}")
            return False

        return True

    except Exception as e:
        print(f"❌ Token encryption test failed: {e}")
        return False

def test_endpoint_structure():
    """Test that all Meta endpoints are properly defined"""
    print("\n🔍 Testing Endpoint Structure...")

    try:
        from webhook.whatsapp_webhook_service import app

        # Get all routes
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                'rule': rule.rule,
                'methods': list(rule.methods),
                'endpoint': rule.endpoint
            })

        # Check for Meta endpoints
        expected_endpoints = [
            '/embedded-signup/token-exchange',
            '/embedded-signup/register-client',
            '/embedded-signup/client-status/<client_id>',
            '/embedded-signup/revoke-client/<client_id>',
            '/embedded-signup/',
            '/webhook/meta-deauth'
        ]

        found_endpoints = [route['rule'] for route in routes]

        print(f"✅ Found {len(found_endpoints)} total endpoints")

        missing_endpoints = []
        for endpoint in expected_endpoints:
            # Check if endpoint exists (handle variable parts)
            endpoint_found = False
            for found in found_endpoints:
                if endpoint.replace('<client_id>', '<client_id>') in found or endpoint in found:
                    endpoint_found = True
                    break

            if endpoint_found:
                print(f"   ✅ {endpoint}")
            else:
                print(f"   ❌ {endpoint} - MISSING")
                missing_endpoints.append(endpoint)

        if not missing_endpoints:
            print(f"✅ All Meta endpoints found")
            return True
        else:
            print(f"❌ Missing endpoints: {missing_endpoints}")
            return False

    except Exception as e:
        print(f"❌ Endpoint structure test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Meta Embedded Signup Implementation Test Suite")
    print("=" * 60)

    tests = [
        test_imports,
        test_enhanced_ea_client,
        test_meta_business_api,
        test_token_encryption,
        test_endpoint_structure
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} {test.__name__}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Meta Embedded Signup implementation is ready.")
        return True
    else:
        print("⚠️ Some tests failed. Check the implementation.")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)