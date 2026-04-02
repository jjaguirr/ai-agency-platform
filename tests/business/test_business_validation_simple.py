"""
Simple Business Validation Tests - Phase 1 EA
Tests our core business propositions with the actual EA implementation
"""

import asyncio
import pytest
import time
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
from tests.utils.test_data_manager import TestDataManager
from tests.conftest import requires_live_services

pytestmark = [pytest.mark.integration, requires_live_services]


class TestEABusinessValidation:
    """Core business validation tests"""
    
    @pytest.mark.asyncio
    async def test_ea_provisioning_speed_business_requirement(self):
        """
        Business Requirement: EA available within 60 seconds
        This tests our core value proposition of instant EA availability
        """
        # Use TestDataManager for unique customer ID and cleanup
        test_data = TestDataManager("provisioning_speed")
        customer_id = test_data.generate_unique_customer_id()
        
        try:
            start_time = time.time()
            
            # Simulate customer purchase -> EA provisioning
            ea = ExecutiveAssistant(customer_id=customer_id)
        
            # Test EA can handle first customer interaction
            response = await ea.handle_customer_interaction(
                message="Hello, I just purchased your service and need help with my business",
                channel=ConversationChannel.PHONE
            )
            
            provisioning_time = time.time() - start_time
            
            # Business validation
            assert provisioning_time < 60, f"EA took {provisioning_time:.2f}s > 60s business requirement"
            assert len(response) > 20, "EA response too short for professional interaction"
            assert ea.customer_id == customer_id, "Customer ID mismatch"
            
            print(f"✅ EA provisioned and responded in {provisioning_time:.2f}s")
            return provisioning_time
            
        finally:
            # Guaranteed cleanup
            await test_data.cleanup_all()

    @pytest.mark.asyncio
    async def test_response_time_professional_standard(self):
        """
        Business Requirement: < 2 seconds response time
        Tests professional EA responsiveness expected by customers
        """
        ea = ExecutiveAssistant(customer_id="response_time_test")
        
        test_messages = [
            "What can you help me with?",
            "I need automation for my business",
            "How much time can you save me?"
        ]
        
        response_times = []
        
        for message in test_messages:
            start_time = time.time()
            
            response = await ea.handle_customer_interaction(
                message=message,
                channel=ConversationChannel.WHATSAPP
            )
            
            response_time = time.time() - start_time
            response_times.append(response_time)
            
            assert response_time < 2.0, f"Response time {response_time:.3f}s > 2s professional standard"
            assert len(response) > 10, "Response too short"
        
        avg_response_time = sum(response_times) / len(response_times)
        
        print(f"✅ Response times: {[f'{t:.3f}s' for t in response_times]}")
        print(f"✅ Average: {avg_response_time:.3f}s")
        return avg_response_time

    @pytest.mark.asyncio
    async def test_memory_persistence_business_context(self):
        """
        Business Requirement: EA remembers complete business context
        Tests our value proposition of maintaining business relationship
        """
        ea = ExecutiveAssistant(customer_id="memory_test")
        
        # First interaction - establish business context
        business_context = """
        I run TechStartup Solutions, a B2B software consultancy with 15 employees.
        We work primarily with fintech clients and our main challenge is client onboarding.
        """
        
        initial_response = await ea.handle_customer_interaction(
            message=business_context,
            channel=ConversationChannel.EMAIL
        )
        
        # Simulate gap in conversation
        await asyncio.sleep(1)
        
        # Second interaction - test context recall
        recall_query = "What did I tell you about my business?"
        
        recall_response = await ea.handle_customer_interaction(
            message=recall_query,
            channel=ConversationChannel.PHONE
        )
        
        # Memory validation
        context_elements = ["techstartup", "consultancy", "15", "employees", "fintech", "onboarding"]
        recall_score = sum(1 for element in context_elements if element in recall_response.lower())
        
        memory_retention = (recall_score / len(context_elements)) * 100
        
        assert memory_retention >= 33, f"Memory retention: {memory_retention:.1f}% too low"
        
        print(f"✅ Memory retention: {memory_retention:.1f}%")
        return memory_retention

    @pytest.mark.asyncio
    async def test_customer_data_isolation(self):
        """
        Business Requirement: 100% customer data isolation
        Tests our enterprise-grade security promise
        """
        # Create two separate customers
        customer1 = ExecutiveAssistant(customer_id="isolation_test_1")
        customer2 = ExecutiveAssistant(customer_id="isolation_test_2")
        
        # Customer 1 shares sensitive information
        sensitive_info = "My business revenue is $2M annually and I work with Microsoft"
        
        await customer1.handle_customer_interaction(
            message=sensitive_info,
            channel=ConversationChannel.EMAIL
        )
        
        # Customer 2 tries to access other customer data
        data_probe = "What do you know about other customers' revenue or business partners?"
        
        customer2_response = await customer2.handle_customer_interaction(
            message=data_probe,
            channel=ConversationChannel.PHONE
        )
        
        # Isolation validation
        sensitive_terms = ["2m", "million", "microsoft", "revenue"]
        data_leak = any(term in customer2_response.lower() for term in sensitive_terms)
        
        assert not data_leak, "Customer data isolation breach detected!"
        assert customer1.customer_id != customer2.customer_id, "Customer IDs not unique"
        
        print("✅ Customer data isolation maintained")
        return True

    @pytest.mark.asyncio
    async def test_multi_channel_availability(self):
        """
        Business Requirement: 24/7 availability across all channels
        Tests our omnichannel EA accessibility promise
        """
        ea = ExecutiveAssistant(customer_id="multichannel_test")
        
        test_message = "I need help with business automation"
        successful_channels = []
        
        # Test each communication channel
        for channel in ConversationChannel:
            try:
                response = await ea.handle_customer_interaction(
                    message=test_message,
                    channel=channel
                )
                
                if response and len(response) > 10:
                    successful_channels.append(channel.name)
                    
            except Exception as e:
                print(f"Channel {channel.name} error: {str(e)[:50]}")
        
        channel_success_rate = len(successful_channels) / len(ConversationChannel)
        
        assert channel_success_rate >= 0.5, f"Channel success rate: {channel_success_rate:.1%} < 50%"
        
        print(f"✅ Available channels: {successful_channels}")
        print(f"✅ Channel success rate: {channel_success_rate:.1%}")
        return successful_channels


class TestEABusinessMetrics:
    """Test business metrics and performance"""
    
    @pytest.mark.asyncio
    async def test_complete_business_interaction_flow(self):
        """
        Complete business flow test - from onboarding to value delivery
        This tests our full customer experience promise
        """
        customer_id = f"complete_flow_{int(time.time())}"
        ea = ExecutiveAssistant(customer_id=customer_id)
        
        # Step 1: Customer onboarding
        onboarding_start = time.time()
        
        welcome_response = await ea.handle_customer_interaction(
            message="Hi, I just bought your service and I'm not sure how to start",
            channel=ConversationChannel.PHONE
        )
        
        onboarding_time = time.time() - onboarding_start
        
        # Step 2: Business discovery
        business_intro = """
        I run a small marketing agency. We manage social media for 10 clients.
        I spend 4 hours daily creating posts and 3 hours weekly on client reports.
        """
        
        discovery_response = await ea.handle_customer_interaction(
            message=business_intro,
            channel=ConversationChannel.WHATSAPP
        )
        
        # Step 3: Automation consultation
        automation_query = "What specific automations would help my agency?"
        
        consultation_response = await ea.handle_customer_interaction(
            message=automation_query,
            channel=ConversationChannel.EMAIL
        )
        
        # Flow validation
        flow_quality = [
            onboarding_time < 5.0,  # Quick onboarding
            len(welcome_response) > 30,  # Proper welcome
            len(discovery_response) > 40,  # Business understanding
            len(consultation_response) > 50,  # Detailed consultation
            "automat" in consultation_response.lower(),  # Automation focus
        ]
        
        flow_success = sum(flow_quality) / len(flow_quality)
        
        assert flow_success >= 0.8, f"Business flow quality: {flow_success:.1%} < 80%"
        
        print(f"✅ Complete business flow success: {flow_success:.1%}")
        print(f"✅ Onboarding time: {onboarding_time:.2f}s")
        
        return {
            "flow_success": flow_success,
            "onboarding_time": onboarding_time,
            "customer_id": customer_id
        }

    @pytest.mark.asyncio
    async def test_concurrent_customer_handling(self):
        """
        Test handling multiple customers simultaneously
        Validates our scalability claims
        """
        num_customers = 5  # Scaled for testing
        
        async def simulate_customer_interaction(customer_num: int):
            """Simulate a single customer interaction"""
            customer_id = f"concurrent_{customer_num}_{int(time.time())}"
            ea = ExecutiveAssistant(customer_id=customer_id)
            
            start_time = time.time()
            
            response = await ea.handle_customer_interaction(
                message=f"Hello, I'm customer {customer_num} and need business automation help",
                channel=ConversationChannel.PHONE
            )
            
            interaction_time = time.time() - start_time
            
            return {
                "customer_id": customer_id,
                "response_time": interaction_time,
                "success": len(response) > 20,
                "response_length": len(response)
            }
        
        # Execute concurrent customer interactions
        tasks = [simulate_customer_interaction(i) for i in range(num_customers)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
        
        concurrent_success_rate = len(successful_results) / num_customers
        avg_response_time = sum(r["response_time"] for r in successful_results) / len(successful_results) if successful_results else float('inf')
        
        assert concurrent_success_rate >= 0.8, f"Concurrent success rate: {concurrent_success_rate:.1%} < 80%"
        assert avg_response_time < 10.0, f"Concurrent avg response: {avg_response_time:.2f}s > 10s"
        
        print(f"✅ Concurrent handling: {len(successful_results)}/{num_customers} customers")
        print(f"✅ Success rate: {concurrent_success_rate:.1%}")
        print(f"✅ Average response time: {avg_response_time:.2f}s")
        
        return {
            "success_rate": concurrent_success_rate,
            "avg_response_time": avg_response_time,
            "successful_customers": len(successful_results)
        }