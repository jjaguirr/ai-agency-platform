"""
Integration Tests for Webhook → EA Flow
End-to-end testing of WhatsApp webhook to Executive Assistant response flow

CRITICAL TDD RULE: These tests MUST FAIL until full integration is complete
Tests both monolithic (current) and separated services (future) architectures
"""

import asyncio
import pytest
import requests
import json
import time
import hmac
import hashlib
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Dict, Any, List

# Import webhook and EA modules
import sys
import os

# Add project root and webhook-service to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
webhook_service_path = os.path.join(project_root, 'webhook-service')
sys.path.append(project_root)
sys.path.append(webhook_service_path)

try:
    from customer_ea_manager import handle_whatsapp_customer_message, health_check
except ImportError:
    # Fallback for when webhook service is not available
    def handle_whatsapp_customer_message(*args, **kwargs):
        raise ImportError("Webhook service not available")

    def health_check():
        return {"status": "unavailable"}

@pytest.fixture
def webhook_base_url():
    """Webhook service base URL"""
    return "http://localhost:8000"  # Current webhook service

@pytest.fixture
def mock_whatsapp_webhook_payload():
    """Mock WhatsApp webhook payload from Meta"""
    return {
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "782822591574136"
                            },
                            "contacts": [
                                {
                                    "profile": {
                                        "name": "Test Customer"
                                    },
                                    "wa_id": "1234567890"
                                }
                            ],
                            "messages": [
                                {
                                    "from": "1234567890",
                                    "id": "wamid.test123",
                                    "timestamp": "1699123456",
                                    "text": {
                                        "body": "Hi Sarah, I need help automating my business processes"
                                    },
                                    "type": "text"
                                }
                            ]
                        },
                        "field": "messages"
                    }
                ]
            }
        ]
    }

@pytest.fixture
def valid_webhook_headers():
    """Valid headers for webhook verification"""
    return {
        "X-Hub-Signature-256": "sha256=test_signature",
        "Content-Type": "application/json",
        "User-Agent": "Meta-WhatsApp-Webhook"
    }

def generate_webhook_signature(payload: str, secret: str) -> str:
    """Generate valid webhook signature for testing"""
    return 'sha256=' + hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

class TestWebhookToEAFlow:
    """Test complete webhook to EA response flow"""

    @pytest.mark.integration
    async def test_webhook_receives_whatsapp_message(self, webhook_base_url, mock_whatsapp_webhook_payload, valid_webhook_headers):
        """
        FAILING TEST: Webhook should receive and process WhatsApp messages

        This tests the current monolithic webhook service
        """
        url = f"{webhook_base_url}/webhook/whatsapp"
        payload_json = json.dumps(mock_whatsapp_webhook_payload)

        # Generate valid signature for testing
        webhook_secret = "test_webhook_secret"
        signature = generate_webhook_signature(payload_json, webhook_secret)
        headers = {
            **valid_webhook_headers,
            "X-Hub-Signature-256": signature
        }

        try:
            with patch.dict(os.environ, {"APP_TOKEN": webhook_secret}):
                response = requests.post(
                    url,
                    headers=headers,
                    data=payload_json,
                    timeout=10.0
                )

            assert response.status_code == 200
            response_data = response.json()
            assert response_data["status"] == "success"

        except requests.exceptions.ConnectionError:
            pytest.fail("Webhook service not running - start with 'python webhook-service/app.py'")

    @pytest.mark.integration
    async def test_webhook_ea_bridge_message_processing(self):
        """
        FAILING TEST: EA bridge should process WhatsApp messages correctly

        Tests the customer_ea_manager bridge functionality
        """
        # Test message data
        whatsapp_number = "+1234567890"
        message = "Hi Sarah, I run a jewelry e-commerce business and need help with social media automation"
        conversation_id = "test_conv_webhook_001"
        metadata = {
            "platform": "whatsapp",
            "timestamp": datetime.now().isoformat()
        }

        # Process through EA bridge
        start_time = time.time()

        try:
            response = await handle_whatsapp_customer_message(
                whatsapp_number=whatsapp_number,
                message=message,
                conversation_id=conversation_id,
                metadata=metadata
            )

            processing_time = time.time() - start_time

            # Validate response
            assert isinstance(response, str)
            assert len(response) > 0
            assert "Sarah" in response or "Executive Assistant" in response

            # Performance validation (3s SLA from business requirements)
            assert processing_time <= 3.0, f"Processing took {processing_time:.2f}s, exceeds 3s SLA"

        except ImportError as e:
            pytest.fail(f"EA system not available: {e}")

    @pytest.mark.integration
    async def test_ea_response_sent_via_whatsapp_api(self, webhook_base_url, mock_whatsapp_webhook_payload):
        """
        FAILING TEST: EA response should be sent back via WhatsApp API

        This test validates the complete round-trip flow
        """
        # Mock WhatsApp API response
        mock_whatsapp_response = MagicMock()
        mock_whatsapp_response.status_code = 200
        mock_whatsapp_response.json.return_value = {"messages": [{"id": "sent_message_id"}]}

        with patch('requests.post', return_value=mock_whatsapp_response) as mock_post:
            url = f"{webhook_base_url}/webhook/whatsapp"
            payload_json = json.dumps(mock_whatsapp_webhook_payload)

            # Set required environment variables
            with patch.dict(os.environ, {
                "WHATSAPP_ACCESS_TOKEN": "test_token",
                "WHATSAPP_PHONE_NUMBER_ID": "782822591574136",
                "APP_TOKEN": ""  # Disable signature verification for test
            }):
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    data=payload_json,
                    timeout=15.0
                )

            # Verify webhook processing
            assert response.status_code == 200

            # Verify WhatsApp API was called to send response
            mock_post.assert_called()

            # Check the call was to WhatsApp Graph API
            call_args = mock_post.call_args
            assert "graph.facebook.com" in call_args[1]['url']
            assert call_args[1]['headers']['Authorization'].startswith('Bearer')

            # Verify message structure
            sent_data = call_args[1]['json']
            assert sent_data['messaging_product'] == 'whatsapp'
            assert sent_data['type'] == 'text'
            assert 'body' in sent_data['text']

    @pytest.mark.integration
    async def test_customer_isolation_in_webhook_flow(self):
        """
        FAILING TEST: Different customers should have isolated EA instances

        Critical security requirement for multi-tenant system
        """
        # Customer A conversation
        customer_a_number = "+1111111111"
        customer_a_message = "I run a jewelry store and need automation help"
        customer_a_response = await handle_whatsapp_customer_message(
            whatsapp_number=customer_a_number,
            message=customer_a_message,
            conversation_id="conv_a_001"
        )

        # Customer B conversation
        customer_b_number = "+2222222222"
        customer_b_message = "I run a consulting business and need automation help"
        customer_b_response = await handle_whatsapp_customer_message(
            whatsapp_number=customer_b_number,
            message=customer_b_message,
            conversation_id="conv_b_001"
        )

        # Responses should be different and context-appropriate
        assert customer_a_response != customer_b_response

        # Follow-up messages should maintain separate contexts
        customer_a_followup = await handle_whatsapp_customer_message(
            whatsapp_number=customer_a_number,
            message="What do you remember about my business?",
            conversation_id="conv_a_002"
        )

        # Customer A's EA should remember jewelry store context
        assert "jewelry" in customer_a_followup.lower() or "store" in customer_a_followup.lower()

class TestWebhookEAPerformance:
    """Performance tests for webhook → EA flow"""

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_webhook_ea_response_under_3_seconds(self):
        """
        FAILING TEST: Complete webhook → EA → response should be under 3 seconds

        Business requirement from Phase-1 PRD
        """
        whatsapp_number = "+1234567890"
        message = "Hi, I need help with my business automation"
        conversation_id = "perf_test_001"

        start_time = time.time()

        response = await handle_whatsapp_customer_message(
            whatsapp_number=whatsapp_number,
            message=message,
            conversation_id=conversation_id
        )

        total_time = time.time() - start_time

        # Validate response quality
        assert isinstance(response, str)
        assert len(response) > 50  # Substantial response

        # Performance requirement
        assert total_time <= 3.0, f"Total processing time {total_time:.2f}s exceeds 3s business requirement"

    @pytest.mark.integration
    @pytest.mark.performance
    async def test_concurrent_webhook_processing(self):
        """
        FAILING TEST: Should handle multiple concurrent webhook messages

        Requirement: 100 concurrent customers
        """
        concurrent_customers = 50  # Start with 50 for testing
        tasks = []

        for i in range(concurrent_customers):
            customer_number = f"+555000{i:04d}"
            message = f"Hi Sarah, I'm customer {i} and need automation help"
            conversation_id = f"concurrent_test_{i}"

            task = handle_whatsapp_customer_message(
                whatsapp_number=customer_number,
                message=message,
                conversation_id=conversation_id
            )
            tasks.append(task)

        # Execute all tasks concurrently
        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Validate all responses
        successful_responses = 0
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                print(f"Customer {i} failed: {response}")
            else:
                assert isinstance(response, str)
                assert len(response) > 0
                successful_responses += 1

        # At least 95% success rate under load
        success_rate = successful_responses / concurrent_customers
        assert success_rate >= 0.95, f"Success rate {success_rate:.2%} below 95% threshold"

        # Average response time should still be reasonable
        avg_time = total_time / concurrent_customers
        assert avg_time <= 5.0, f"Average response time {avg_time:.2f}s too high under load"

class TestWebhookEAFailover:
    """Test failover scenarios for webhook → EA flow"""

    @pytest.mark.integration
    async def test_ea_fallback_when_imports_fail(self):
        """
        FAILING TEST: Should provide fallback response when EA imports fail

        Critical resilience requirement
        """
        # Simulate import failure
        with patch('webhook_service.customer_ea_manager.EA_IMPORTS_AVAILABLE', False):
            response = await handle_whatsapp_customer_message(
                whatsapp_number="+1234567890",
                message="Test message during EA failure",
                conversation_id="failover_test_001"
            )

            # Should still get a professional response
            assert isinstance(response, str)
            assert len(response) > 20
            assert ("Sarah" in response or "Executive Assistant" in response)
            assert ("setting up" in response or "operational soon" in response)

    @pytest.mark.integration
    async def test_webhook_graceful_degradation_openai_failure(self):
        """
        FAILING TEST: Should gracefully degrade when OpenAI API fails

        Webhook should still respond even if AI processing fails
        """
        # Mock OpenAI failure
        with patch('openai.OpenAI') as mock_openai:
            mock_openai.side_effect = Exception("OpenAI API unavailable")

            response = await handle_whatsapp_customer_message(
                whatsapp_number="+1234567890",
                message="Help me with automation",
                conversation_id="openai_failure_test"
            )

            # Should get fallback response
            assert isinstance(response, str)
            assert len(response) > 10
            # Should indicate technical issue professionally
            assert any(word in response.lower() for word in ["technical", "moment", "resolve", "back"])

    @pytest.mark.integration
    async def test_webhook_memory_failure_recovery(self):
        """
        FAILING TEST: Should handle memory system failures gracefully
        """
        # Simulate memory system failure
        with patch('webhook_service.customer_ea_manager.UnifiedContextStore') as mock_context:
            mock_context.side_effect = Exception("Memory store unavailable")

            response = await handle_whatsapp_customer_message(
                whatsapp_number="+1234567890",
                message="Remember our previous conversation?",
                conversation_id="memory_failure_test"
            )

            # Should still respond (without memory context)
            assert isinstance(response, str)
            assert len(response) > 20

class TestWebhookEABusinessLogic:
    """Test business logic in webhook → EA flow"""

    @pytest.mark.integration
    async def test_ea_identifies_automation_opportunities(self):
        """
        FAILING TEST: EA should identify automation opportunities from messages

        Core business value proposition
        """
        business_message = """Hi Sarah, I run a jewelry e-commerce store. Every day I spend 2 hours
        manually posting to Instagram and Facebook, and I often forget to post consistently.
        I also spend hours every week creating invoices and sending follow-up emails to customers."""

        response = await handle_whatsapp_customer_message(
            whatsapp_number="+1234567890",
            message=business_message,
            conversation_id="automation_test_001"
        )

        # Should identify and mention automation opportunities
        response_lower = response.lower()
        automation_indicators = [
            "automat", "workflow", "schedule", "social media",
            "instagram", "facebook", "invoic", "follow-up", "save time"
        ]

        found_indicators = [indicator for indicator in automation_indicators if indicator in response_lower]
        assert len(found_indicators) >= 2, f"EA should identify automation opportunities. Found: {found_indicators}"

    @pytest.mark.integration
    async def test_ea_maintains_professional_business_tone(self):
        """
        FAILING TEST: EA should maintain professional business tone

        Brand requirement for Executive Assistant persona
        """
        test_messages = [
            "yo whats up",
            "help me pls",
            "URGENT!!!! NEED HELP NOW!!!",
            "Can you help me with my business automation needs?"
        ]

        for message in test_messages:
            response = await handle_whatsapp_customer_message(
                whatsapp_number="+1234567890",
                message=message,
                conversation_id=f"tone_test_{hash(message)}"
            )

            # Should maintain professional tone regardless of customer input
            assert not any(unprofessional in response.lower() for unprofessional in [
                "yo", "sup", "lol", "omg", "wtf", "gonna", "wanna"
            ])

            # Should include professional business language
            professional_indicators = [
                "sarah", "executive assistant", "business", "help", "automation",
                "workflow", "process", "solution"
            ]

            found_professional = [indicator for indicator in professional_indicators
                                if indicator in response.lower()]
            assert len(found_professional) >= 2, f"Response lacks professional tone: {response[:100]}..."

    @pytest.mark.integration
    async def test_ea_handles_competitive_inquiries(self):
        """
        FAILING TEST: EA should handle competitive inquiries professionally

        Business requirement for market positioning
        """
        competitive_message = "How are you different from Zapier and Make.com? Why should I choose you?"

        response = await handle_whatsapp_customer_message(
            whatsapp_number="+1234567890",
            message=competitive_message,
            conversation_id="competitive_test_001"
        )

        # Should position as business partner, not just software
        positioning_keywords = [
            "business partner", "conversation", "learn", "adapt",
            "executive assistant", "not software", "not tool"
        ]

        response_lower = response.lower()
        found_positioning = [keyword for keyword in positioning_keywords if keyword in response_lower]

        assert len(found_positioning) >= 2, f"Should position against automation tools. Found: {found_positioning}"

        # Should not bash competitors directly
        assert not any(negative in response_lower for negative in [
            "bad", "worse", "terrible", "sucks", "awful"
        ])

class TestWebhookEAIntegration:
    """Test integration points in webhook → EA flow"""

    @pytest.mark.integration
    async def test_webhook_ea_health_check_integration(self):
        """
        FAILING TEST: Health check should validate EA system availability
        """
        health_status = await health_check()

        assert health_status["status"] in ["healthy", "degraded", "error"]
        assert "components" in health_status
        assert "timestamp" in health_status

        # Should test EA system availability
        if health_status["status"] == "healthy":
            assert health_status["imports_available"] is True
        elif health_status["status"] == "degraded":
            # Should indicate what components are unavailable
            assert any(status != "available" for status in health_status["components"].values())

    @pytest.mark.integration
    async def test_webhook_validates_whatsapp_signature(self, webhook_base_url, mock_whatsapp_webhook_payload):
        """
        FAILING TEST: Webhook should validate WhatsApp signatures for security
        """
        url = f"{webhook_base_url}/webhook/whatsapp"
        payload_json = json.dumps(mock_whatsapp_webhook_payload)

        # Invalid signature should be rejected
        invalid_headers = {
            "X-Hub-Signature-256": "sha256=invalid_signature",
            "Content-Type": "application/json"
        }

        with patch.dict(os.environ, {"APP_TOKEN": "test_secret"}):
            response = requests.post(
                url,
                headers=invalid_headers,
                data=payload_json,
                timeout=5.0
            )

        # Should reject invalid signatures
        assert response.status_code == 403

# Quality Gates for Webhook → EA Integration
class TestWebhookEAQualityGates:
    """Quality gates that must pass before production deployment"""

    @pytest.mark.integration
    async def test_end_to_end_flow_quality_gate(self):
        """
        FAILING TEST: Complete quality gate for webhook → EA flow

        Must pass all critical requirements
        """
        test_customer = "+1555123TEST"
        business_inquiry = """Hi, I'm Sarah from Premium Jewelry Co. I need help automating
        my Instagram posting and customer follow-up emails. I'm currently spending 10 hours
        per week on these tasks."""

        start_time = time.time()

        # Process business inquiry
        response = await handle_whatsapp_customer_message(
            whatsapp_number=test_customer,
            message=business_inquiry,
            conversation_id="quality_gate_test"
        )

        processing_time = time.time() - start_time

        # Quality Gate 1: Performance (< 3 seconds)
        assert processing_time <= 3.0, f"Failed performance gate: {processing_time:.2f}s"

        # Quality Gate 2: Response Quality (substantial and relevant)
        assert len(response) >= 100, "Response too short for business inquiry"
        response_lower = response.lower()

        # Quality Gate 3: Business Understanding
        business_understanding = any(term in response_lower for term in [
            "jewelry", "instagram", "follow-up", "email", "automat", "workflow"
        ])
        assert business_understanding, "EA did not demonstrate business understanding"

        # Quality Gate 4: Professional Tone
        professional_tone = any(term in response_lower for term in [
            "sarah", "executive assistant", "help", "solution", "business"
        ])
        assert professional_tone, "Response lacks professional EA tone"

        # Quality Gate 5: Automation Opportunity Identification
        automation_mention = any(term in response_lower for term in [
            "automat", "save time", "workflow", "process", "hour"
        ])
        assert automation_mention, "EA did not identify automation opportunities"

        print(f"✅ All quality gates passed in {processing_time:.2f}s")
        print(f"📝 Response length: {len(response)} characters")
        print(f"🎯 Business understanding: {business_understanding}")
        print(f"💼 Professional tone: {professional_tone}")
        print(f"🤖 Automation identification: {automation_mention}")

    @pytest.mark.integration
    async def test_webhook_ea_sla_compliance(self):
        """
        FAILING TEST: Validate SLA compliance for webhook → EA flow

        Business SLA requirements from Phase-1 PRD
        """
        # Test multiple scenarios for SLA validation
        test_scenarios = [
            ("simple_greeting", "Hi Sarah"),
            ("business_inquiry", "I need help with my business automation"),
            ("complex_business", "I run multiple e-commerce stores and need complex automation"),
            ("urgent_request", "URGENT: My current automation is broken, need immediate help")
        ]

        sla_results = []

        for scenario_name, message in test_scenarios:
            start_time = time.time()

            response = await handle_whatsapp_customer_message(
                whatsapp_number=f"+1555{hash(scenario_name) % 10000:04d}",
                message=message,
                conversation_id=f"sla_test_{scenario_name}"
            )

            processing_time = time.time() - start_time

            sla_results.append({
                "scenario": scenario_name,
                "processing_time": processing_time,
                "sla_met": processing_time <= 3.0,
                "response_length": len(response)
            })

        # All scenarios must meet SLA
        failed_scenarios = [r for r in sla_results if not r["sla_met"]]
        assert len(failed_scenarios) == 0, f"SLA failures: {failed_scenarios}"

        # Average response time should be well under SLA
        avg_time = sum(r["processing_time"] for r in sla_results) / len(sla_results)
        assert avg_time <= 2.0, f"Average response time {avg_time:.2f}s too close to 3s SLA limit"

        print(f"📊 SLA Test Results:")
        for result in sla_results:
            status = "✅" if result["sla_met"] else "❌"
            print(f"  {status} {result['scenario']}: {result['processing_time']:.2f}s")
        print(f"📈 Average response time: {avg_time:.2f}s")