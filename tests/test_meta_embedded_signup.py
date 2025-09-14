#!/usr/bin/env python3
"""
Integration tests for Meta Embedded Signup functionality
"""

import pytest
import json
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from webhook.whatsapp_webhook_service import app, ea_registry, EAClient
from webhook.meta_business_api import MetaBusinessAPI, MetaTokenExchangeResult, MetaWABAInfo


@pytest.fixture
def client():
    """Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    with patch('webhook.whatsapp_webhook_service.redis_client') as mock:
        mock.set.return_value = True
        mock.get.return_value = None
        mock.delete.return_value = True
        yield mock


@pytest.fixture
def mock_meta_api():
    """Mock Meta Business API"""
    with patch('webhook.whatsapp_webhook_service.meta_business_api') as mock:
        yield mock


class TestMetaTokenExchange:
    """Test Meta authorization code token exchange"""

    def test_token_exchange_success(self, client, mock_redis, mock_meta_api):
        """Test successful authorization code exchange"""
        # Mock successful token exchange
        mock_token_result = MetaTokenExchangeResult(
            success=True,
            access_token="test_business_token",
            token_type="bearer",
            expires_in=5184000,
            granted_scopes=["whatsapp_business_messaging", "whatsapp_business_management"]
        )
        mock_meta_api.exchange_authorization_code = AsyncMock(return_value=mock_token_result)

        # Mock business validation
        mock_meta_api.validate_business_token = AsyncMock(return_value={
            "id": "test_business_id",
            "name": "Test Business",
            "type": "business"
        })

        # Mock business accounts
        mock_meta_api.get_business_accounts = AsyncMock(return_value=[{
            "id": "test_business_123",
            "name": "Test Business Account"
        }])

        # Mock WABA accounts
        mock_waba = MetaWABAInfo(
            waba_id="test_waba_123",
            name="Test WABA",
            currency="USD",
            timezone_id="America/New_York",
            message_template_namespace="test_namespace",
            account_review_status="APPROVED",
            business_verification_status="VERIFIED",
            phone_numbers=[{
                "id": "test_phone_123",
                "display_phone_number": "+1234567890",
                "verified_name": "Test Business",
                "quality_rating": "GREEN"
            }]
        )
        mock_meta_api.get_whatsapp_business_accounts = AsyncMock(return_value=[mock_waba])

        # Test token exchange request
        response = client.post('/embedded-signup/token-exchange',
                              json={
                                  "authorization_code": "test_auth_code",
                                  "client_id": "test_client_123",
                                  "customer_id": "customer_456",
                                  "mcp_endpoint": "https://test.com/mcp",
                                  "auth_token": "test_auth_token"
                              })

        assert response.status_code == 200
        data = json.loads(response.data)

        assert data["status"] == "success"
        assert data["message"] == "Authorization code exchanged successfully"
        assert "integration_data" in data
        assert data["integration_data"]["waba_id"] == "test_waba_123"
        assert data["integration_data"]["display_phone_number"] == "+1234567890"

        # Verify Redis storage
        mock_redis.set.assert_called_once()

    def test_token_exchange_missing_fields(self, client):
        """Test token exchange with missing required fields"""
        response = client.post('/embedded-signup/token-exchange',
                              json={"authorization_code": "test_code"})

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Missing required field" in data["error"]

    def test_token_exchange_meta_api_failure(self, client, mock_meta_api):
        """Test token exchange when Meta API fails"""
        mock_token_result = MetaTokenExchangeResult(
            success=False,
            error_message="Invalid authorization code"
        )
        mock_meta_api.exchange_authorization_code = AsyncMock(return_value=mock_token_result)

        response = client.post('/embedded-signup/token-exchange',
                              json={
                                  "authorization_code": "invalid_code",
                                  "client_id": "test_client_123",
                                  "customer_id": "customer_456",
                                  "mcp_endpoint": "https://test.com/mcp",
                                  "auth_token": "test_auth_token"
                              })

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["error"] == "Token exchange failed"
        assert data["message"] == "Invalid authorization code"

    def test_token_exchange_no_business_accounts(self, client, mock_meta_api):
        """Test token exchange when no business accounts found"""
        mock_token_result = MetaTokenExchangeResult(
            success=True,
            access_token="test_token"
        )
        mock_meta_api.exchange_authorization_code = AsyncMock(return_value=mock_token_result)
        mock_meta_api.validate_business_token = AsyncMock(return_value={"id": "test", "type": "business"})
        mock_meta_api.get_business_accounts = AsyncMock(return_value=[])

        response = client.post('/embedded-signup/token-exchange',
                              json={
                                  "authorization_code": "test_code",
                                  "client_id": "test_client",
                                  "customer_id": "customer_456",
                                  "mcp_endpoint": "https://test.com/mcp",
                                  "auth_token": "test_auth_token"
                              })

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data["error"] == "No business accounts found"


class TestMetaClientRegistration:
    """Test Meta client registration completion"""

    def test_register_client_success(self, client, mock_redis, mock_meta_api):
        """Test successful client registration"""
        # Mock stored integration data
        integration_data = {
            "client_id": "test_client_123",
            "customer_id": "customer_456",
            "mcp_endpoint": "https://test.com/mcp",
            "auth_token": "test_auth_token",
            "waba_id": "test_waba_123",
            "business_phone_number_id": "test_phone_123",
            "business_id": "test_business_123",
            "meta_business_token": "test_business_token",
            "meta_token_expires": (datetime.now() + timedelta(days=60)).isoformat(),
            "meta_app_id": "test_app_id",
            "display_phone_number": "+1234567890",
            "waba_name": "Test WABA",
            "business_name": "Test Business"
        }

        mock_redis.get.return_value = json.dumps(integration_data).encode()
        mock_meta_api.subscribe_to_webhooks = AsyncMock(return_value=True)

        # Mock registry registration
        with patch.object(ea_registry, 'register_client') as mock_register:
            mock_register.return_value = True

            response = client.post('/embedded-signup/register-client',
                                  json={
                                      "client_id": "test_client_123",
                                      "phone_number": "+1234567890"
                                  })

            assert response.status_code == 201
            data = json.loads(response.data)

            assert data["status"] == "success"
            assert data["message"] == "Meta WhatsApp integration completed successfully"
            assert data["client_id"] == "test_client_123"
            assert data["integration_details"]["waba_id"] == "test_waba_123"

            # Verify client registration was called
            mock_register.assert_called_once()

    def test_register_client_no_integration_data(self, client, mock_redis):
        """Test client registration with no pending integration data"""
        mock_redis.get.return_value = None

        response = client.post('/embedded-signup/register-client',
                              json={
                                  "client_id": "test_client_123",
                                  "phone_number": "+1234567890"
                              })

        assert response.status_code == 404
        data = json.loads(response.data)
        assert data["error"] == "Integration data not found"

    def test_register_client_webhook_subscription_failure(self, client, mock_redis, mock_meta_api):
        """Test client registration when webhook subscription fails"""
        integration_data = {
            "client_id": "test_client_123",
            "customer_id": "customer_456",
            "mcp_endpoint": "https://test.com/mcp",
            "auth_token": "test_auth_token",
            "waba_id": "test_waba_123",
            "business_phone_number_id": "test_phone_123",
            "business_id": "test_business_123",
            "meta_business_token": "test_business_token",
            "meta_app_id": "test_app_id"
        }

        mock_redis.get.return_value = json.dumps(integration_data).encode()
        mock_meta_api.subscribe_to_webhooks = AsyncMock(return_value=False)

        with patch.object(ea_registry, 'register_client') as mock_register:
            mock_register.return_value = True

            response = client.post('/embedded-signup/register-client',
                                  json={
                                      "client_id": "test_client_123",
                                      "phone_number": "+1234567890"
                                  })

            # Should still succeed even if webhook subscription fails
            assert response.status_code == 201
            data = json.loads(response.data)
            assert data["integration_details"]["webhook_subscribed"] is False


class TestMetaClientStatus:
    """Test Meta client status endpoints"""

    def test_get_client_status_with_meta_integration(self, client):
        """Test getting status for client with Meta integration"""
        # Create test client with Meta integration
        test_client = EAClient(
            client_id="test_client_123",
            customer_id="customer_456",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_auth_token",
            waba_id="test_waba_123",
            business_phone_number_id="test_phone_123",
            business_id="test_business_123",
            meta_business_token="test_business_token",
            meta_token_expires=datetime.now() + timedelta(days=30),
            embedded_signup_completed=True
        )

        with patch.object(ea_registry, 'get_client') as mock_get_client:
            mock_get_client.return_value = test_client

            response = client.get('/embedded-signup/client-status/test_client_123')

            assert response.status_code == 200
            data = json.loads(response.data)

            assert data["status"] == "success"
            status = data["meta_integration_status"]
            assert status["embedded_signup_completed"] is True
            assert status["has_meta_integration"] is True
            assert status["waba_id"] == "test_waba_123"
            assert status["token_valid"] is True

    def test_get_client_status_not_found(self, client):
        """Test getting status for non-existent client"""
        with patch.object(ea_registry, 'get_client') as mock_get_client:
            mock_get_client.return_value = None

            response = client.get('/embedded-signup/client-status/nonexistent')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert data["error"] == "Client not found"

    def test_get_client_status_with_pending_integration(self, client, mock_redis):
        """Test getting status for client with pending integration"""
        # Create test client without Meta integration
        test_client = EAClient(
            client_id="test_client_123",
            customer_id="customer_456",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_auth_token",
            embedded_signup_completed=False
        )

        # Mock pending integration data
        pending_data = {
            "waba_id": "test_waba_123",
            "display_phone_number": "+1234567890",
            "meta_token_expires": (datetime.now() + timedelta(minutes=15)).isoformat()
        }
        mock_redis.get.return_value = json.dumps(pending_data).encode()

        with patch.object(ea_registry, 'get_client') as mock_get_client:
            mock_get_client.return_value = test_client

            response = client.get('/embedded-signup/client-status/test_client_123')

            assert response.status_code == 200
            data = json.loads(response.data)

            assert data["pending_integration"] is not None
            assert data["pending_integration"]["token_exchange_completed"] is True
            assert data["pending_integration"]["awaiting_registration"] is True


class TestMetaClientRevocation:
    """Test Meta client integration revocation"""

    def test_revoke_client_integration_success(self, client):
        """Test successful integration revocation"""
        # Create test client with Meta integration
        test_client = EAClient(
            client_id="test_client_123",
            customer_id="customer_456",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_auth_token",
            waba_id="test_waba_123",
            business_phone_number_id="test_phone_123",
            meta_business_token="test_business_token",
            embedded_signup_completed=True
        )

        with patch.object(ea_registry, 'get_client') as mock_get_client, \
             patch.object(ea_registry, 'register_client') as mock_register:

            mock_get_client.return_value = test_client
            mock_register.return_value = True

            response = client.delete('/embedded-signup/revoke-client/test_client_123')

            assert response.status_code == 200
            data = json.loads(response.data)

            assert data["status"] == "success"
            assert data["message"] == "Meta WhatsApp integration revoked successfully"

            # Verify client was re-registered without Meta integration
            mock_register.assert_called_once()
            updated_client = mock_register.call_args[0][0]
            assert updated_client.embedded_signup_completed is False
            assert updated_client.waba_id is None

    def test_revoke_client_not_found(self, client):
        """Test revoking integration for non-existent client"""
        with patch.object(ea_registry, 'get_client') as mock_get_client:
            mock_get_client.return_value = None

            response = client.delete('/embedded-signup/revoke-client/nonexistent')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert data["error"] == "Client not found"

    def test_revoke_client_no_integration(self, client):
        """Test revoking integration for client without Meta integration"""
        test_client = EAClient(
            client_id="test_client_123",
            customer_id="customer_456",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_auth_token",
            embedded_signup_completed=False
        )

        with patch.object(ea_registry, 'get_client') as mock_get_client:
            mock_get_client.return_value = test_client

            response = client.delete('/embedded-signup/revoke-client/test_client_123')

            assert response.status_code == 400
            data = json.loads(response.data)
            assert data["error"] == "No Meta integration to revoke"


class TestMetaMessageRouting:
    """Test message routing with Meta integration"""

    def test_message_routing_via_business_phone_id(self, client):
        """Test message routing using business phone number ID"""
        # Create test client with Meta integration
        test_client = EAClient(
            client_id="test_client_123",
            customer_id="customer_456",
            phone_number="+1234567890",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_auth_token",
            waba_id="test_waba_123",
            business_phone_number_id="test_phone_123",
            meta_business_token="test_business_token",
            embedded_signup_completed=True
        )

        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "metadata": {
                            "phone_number_id": "test_phone_123",
                            "display_phone_number": "+1234567890"
                        },
                        "messages": [{
                            "from": "+1987654321",
                            "id": "test_message_123",
                            "type": "text",
                            "text": {"body": "Hello EA"},
                            "timestamp": str(int(datetime.now().timestamp()))
                        }]
                    }
                }]
            }]
        }

        with patch.object(ea_registry, 'get_client_by_business_phone_id') as mock_get_client, \
             patch('webhook.whatsapp_webhook_service.route_to_ea_client') as mock_route, \
             patch('webhook.whatsapp_webhook_service.send_via_meta_api') as mock_send:

            mock_get_client.return_value = test_client
            mock_route.return_value = "Hello! How can I help?"
            mock_send.return_value = True

            response = client.post('/webhook/whatsapp',
                                  json=webhook_data,
                                  headers={'X-Hub-Signature-256': 'test_signature'})

            assert response.status_code == 200

            # Verify client lookup by business phone ID was called
            mock_get_client.assert_called_once_with("test_phone_123")

            # Verify message routing was called
            mock_route.assert_called_once()

            # Verify Meta API send was used
            mock_send.assert_called_once()

    def test_fallback_to_phone_number_lookup(self, client):
        """Test fallback to traditional phone number lookup"""
        test_client = EAClient(
            client_id="test_client_123",
            customer_id="customer_456",
            phone_number="+1987654321",
            mcp_endpoint="https://test.com/mcp",
            auth_token="test_auth_token"
        )

        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "+1987654321",
                            "id": "test_message_123",
                            "type": "text",
                            "text": {"body": "Hello EA"},
                            "timestamp": str(int(datetime.now().timestamp()))
                        }]
                    }
                }]
            }]
        }

        with patch.object(ea_registry, 'get_client_by_business_phone_id') as mock_get_by_business, \
             patch.object(ea_registry, 'get_client_by_phone') as mock_get_by_phone, \
             patch('webhook.whatsapp_webhook_service.route_to_ea_client') as mock_route, \
             patch('webhook.whatsapp_webhook_service.send_whatsapp_response') as mock_send:

            mock_get_by_business.return_value = None  # No business phone lookup
            mock_get_by_phone.return_value = test_client  # Found via phone number
            mock_route.return_value = "Hello! How can I help?"

            response = client.post('/webhook/whatsapp',
                                  json=webhook_data,
                                  headers={'X-Hub-Signature-256': 'test_signature'})

            assert response.status_code == 200

            # Verify fallback to phone number lookup
            mock_get_by_phone.assert_called_once_with("+1987654321")

            # Verify legacy send method was used (not Meta API)
            mock_send.assert_called_once()


class TestMetaBusinessAPI:
    """Test Meta Business API integration"""

    @pytest.fixture
    def meta_api(self):
        """Meta Business API instance for testing"""
        return MetaBusinessAPI()

    @pytest.mark.asyncio
    async def test_token_exchange(self, meta_api):
        """Test Meta authorization code exchange"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'access_token': 'test_business_token',
                'token_type': 'bearer',
                'expires_in': 5184000
            })

            mock_post.return_value.__aenter__.return_value = mock_response

            result = await meta_api.exchange_authorization_code('test_auth_code')

            assert result.success is True
            assert result.access_token == 'test_business_token'
            assert result.expires_in == 5184000

    @pytest.mark.asyncio
    async def test_send_message(self, meta_api):
        """Test sending message via Meta API"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = Mock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'messages': [{'id': 'test_message_123'}]
            })

            mock_post.return_value.__aenter__.return_value = mock_response

            message_id = await meta_api.send_message(
                'test_token',
                'test_phone_123',
                '+1234567890',
                'text',
                {'text': {'body': 'Hello!'}}
            )

            assert message_id == 'test_message_123'

    def test_webhook_signature_validation(self, meta_api):
        """Test Meta webhook signature validation"""
        # Mock app secret
        with patch.dict(os.environ, {'META_APP_SECRET': 'test_secret'}):
            meta_api.app_secret = 'test_secret'

            payload = b'{"test": "data"}'
            # Calculate expected signature
            import hmac
            import hashlib
            expected_sig = hmac.new(b'test_secret', payload, hashlib.sha256).hexdigest()

            # Test with correct signature
            assert meta_api.validate_webhook_signature(payload, f'sha256={expected_sig}') is True

            # Test with incorrect signature
            assert meta_api.validate_webhook_signature(payload, 'sha256=wrong_signature') is False


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])