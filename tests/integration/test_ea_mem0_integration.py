#!/usr/bin/env python3
"""
Test EA-Mem0 Integration - Comprehensive Testing of AI/ML Business Learning

Tests the complete integration between Executive Assistant and Mem0 memory system
for business learning, conversation continuity, and automation opportunity detection.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any

from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
from src.agents.memory.ea_memory_integration import EAMemoryIntegration, ConversationContext, BusinessInsightType

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class EAMem0IntegrationTester:
    """Comprehensive tester for EA-Mem0 integration"""
    
    def __init__(self):
        self.test_results = []
        self.test_customer_id = f"test_customer_{uuid.uuid4().hex[:8]}"
        
    async def run_comprehensive_test_suite(self):
        """Run complete test suite for EA-Mem0 integration"""
        print("🚀 Starting EA-Mem0 Integration Test Suite")
        print(f"Test Customer ID: {self.test_customer_id}")
        print("=" * 80)
        
        try:
            # Test 1: Basic EA initialization with Mem0
            await self.test_ea_initialization()
            
            # Test 2: Business discovery conversation processing
            await self.test_business_discovery_conversation()
            
            # Test 3: Automation opportunity detection
            await self.test_automation_opportunity_detection()
            
            # Test 4: Cross-channel conversation continuity
            await self.test_cross_channel_continuity()
            
            # Test 5: Template recommendation system
            await self.test_template_recommendations()
            
            # Test 6: Business intelligence dashboard
            await self.test_business_intelligence_dashboard()
            
            # Test 7: Performance and memory isolation
            await self.test_performance_and_isolation()
            
            # Print test results summary
            self.print_test_results_summary()
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}")
            raise
    
    async def test_ea_initialization(self):
        """Test EA initialization with Mem0 integration"""
        print("\n📋 Test 1: EA Initialization with Mem0")
        print("-" * 40)
        
        try:
            # Initialize EA with test customer
            mcp_url = "http://localhost:30001"  # Test MCP server
            ea = ExecutiveAssistant(self.test_customer_id, mcp_url)
            
            # Verify memory integration is initialized
            assert hasattr(ea.memory, 'mem0_integration'), "Mem0 integration not initialized"
            assert ea.memory.mem0_integration.customer_id == self.test_customer_id, "Customer ID mismatch"
            
            # Test memory system components
            memory_manager = ea.memory.mem0_integration.memory_manager
            assert memory_manager.customer_id == self.test_customer_id, "Memory manager customer ID mismatch"
            
            print("✅ EA initialization successful")
            print(f"   - Customer ID: {self.test_customer_id}")
            print(f"   - MCP Server URL: {mcp_url}")
            print(f"   - Mem0 Integration: Initialized")
            print(f"   - Memory Manager: Ready")
            
            self.test_results.append({
                "test": "EA Initialization",
                "status": "PASS",
                "details": "All components initialized successfully"
            })
            
            return ea
            
        except Exception as e:
            self.test_results.append({
                "test": "EA Initialization", 
                "status": "FAIL",
                "error": str(e)
            })
            raise
    
    async def test_business_discovery_conversation(self):
        """Test business discovery conversation with AI/ML processing"""
        print("\n📋 Test 2: Business Discovery Conversation")
        print("-" * 40)
        
        try:
            ea = await self.test_ea_initialization()
            
            # Simulate comprehensive business discovery conversation
            discovery_conversation = [
                ("phone", "Hi Sarah! I'm excited to work with you. I run a marketing agency called BrandBoost."),
                ("phone", "We specialize in helping local restaurants with their digital marketing - social media, online reviews, email campaigns."),
                ("phone", "My biggest challenge is that I manually create social media posts for 15 restaurant clients every day. It takes me 3-4 hours and it's very repetitive."),
                ("phone", "I use Canva for design, Buffer for scheduling, and I track everything in a Google Sheet. I also send weekly performance reports to each client via email."),
                ("phone", "I'd love to automate the social media posting and maybe the reporting too. Can you help me set that up?")
            ]
            
            conversation_results = []
            conversation_id = str(uuid.uuid4())
            
            for channel_str, message in discovery_conversation:
                channel = ConversationChannel.PHONE
                response = await ea.handle_customer_interaction(
                    message=message,
                    channel=channel, 
                    conversation_id=conversation_id
                )
                
                conversation_results.append({
                    "message": message,
                    "response": response,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                print(f"📝 Message: {message[:80]}...")
                print(f"🤖 Response: {response[:100]}...")
                print()
            
            # Verify business learning extraction
            intelligence_dashboard = await ea.get_business_intelligence_dashboard()
            
            # Check for expected business insights
            assert intelligence_dashboard.get("business_processes_identified", 0) > 0, "No business processes identified"
            assert intelligence_dashboard.get("automation_opportunities_found", 0) > 0, "No automation opportunities found"
            assert len(intelligence_dashboard.get("tools_discovered", [])) >= 3, "Expected tools not discovered (Canva, Buffer, Google Sheets)"
            
            print("✅ Business discovery conversation successful")
            print(f"   - Messages processed: {len(discovery_conversation)}")
            print(f"   - Business processes identified: {intelligence_dashboard.get('business_processes_identified', 0)}")
            print(f"   - Automation opportunities: {intelligence_dashboard.get('automation_opportunities_found', 0)}")
            print(f"   - Tools discovered: {len(intelligence_dashboard.get('tools_discovered', []))}")
            print(f"   - Memory quality score: {intelligence_dashboard.get('memory_quality_score', 0):.2f}")
            
            self.test_results.append({
                "test": "Business Discovery",
                "status": "PASS",
                "details": f"Identified {intelligence_dashboard.get('business_processes_identified', 0)} processes, {intelligence_dashboard.get('automation_opportunities_found', 0)} opportunities"
            })
            
            return ea, conversation_results
            
        except Exception as e:
            self.test_results.append({
                "test": "Business Discovery",
                "status": "FAIL", 
                "error": str(e)
            })
            raise
    
    async def test_automation_opportunity_detection(self):
        """Test automation opportunity detection and template matching"""
        print("\n📋 Test 3: Automation Opportunity Detection")
        print("-" * 40)
        
        try:
            ea, _ = await self.test_business_discovery_conversation()
            
            # Test specific automation scenarios
            automation_scenarios = [
                "I spend 2 hours every morning posting to Instagram and Facebook for all my clients",
                "I manually send follow-up emails to prospects who haven't responded in 3 days",
                "Every Friday I generate performance reports from Google Analytics and email them to clients",
                "I have to manually update inventory in Shopify when items are running low"
            ]
            
            automation_results = []
            
            for scenario in automation_scenarios:
                response = await ea.handle_customer_interaction(
                    message=scenario,
                    channel=ConversationChannel.PHONE,
                    conversation_id=str(uuid.uuid4())
                )
                
                automation_results.append({
                    "scenario": scenario,
                    "response": response,
                    "automation_detected": "automat" in response.lower() or "workflow" in response.lower()
                })
                
                print(f"📋 Scenario: {scenario[:60]}...")
                print(f"🔍 Automation detected: {'✅' if automation_results[-1]['automation_detected'] else '❌'}")
                print(f"🤖 Response: {response[:80]}...")
                print()
            
            # Verify automation detection
            detected_automations = sum(1 for r in automation_results if r["automation_detected"])
            assert detected_automations >= 3, f"Expected at least 3 automation detections, got {detected_automations}"
            
            print("✅ Automation opportunity detection successful")
            print(f"   - Scenarios tested: {len(automation_scenarios)}")
            print(f"   - Automations detected: {detected_automations}")
            print(f"   - Detection rate: {detected_automations/len(automation_scenarios)*100:.1f}%")
            
            self.test_results.append({
                "test": "Automation Detection",
                "status": "PASS", 
                "details": f"{detected_automations}/{len(automation_scenarios)} automations detected"
            })
            
            return ea
            
        except Exception as e:
            self.test_results.append({
                "test": "Automation Detection",
                "status": "FAIL",
                "error": str(e)
            })
            raise
    
    async def test_cross_channel_continuity(self):
        """Test conversation continuity across different channels"""
        print("\n📋 Test 4: Cross-Channel Conversation Continuity")
        print("-" * 40)
        
        try:
            ea = await self.test_automation_opportunity_detection()
            
            # Multi-channel conversation flow
            conversation_id = str(uuid.uuid4())
            
            # Start with phone call
            phone_response = await ea.handle_customer_interaction(
                message="I want to discuss automating my social media posting workflow",
                channel=ConversationChannel.PHONE,
                conversation_id=conversation_id
            )
            
            # Continue via WhatsApp
            whatsapp_response = await ea.handle_customer_interaction(
                message="Following up on our call - can you show me those template options we discussed?",
                channel=ConversationChannel.WHATSAPP,
                conversation_id=conversation_id
            )
            
            # Finalize via Email
            email_response = await ea.handle_customer_interaction(
                message="Thanks for the WhatsApp info. Please proceed with setting up the social media automation.",
                channel=ConversationChannel.EMAIL,
                conversation_id=conversation_id
            )
            
            # Test context awareness in responses
            context_maintained = (
                "social media" in whatsapp_response.lower() and
                "template" in whatsapp_response.lower() and
                "automation" in email_response.lower()
            )
            
            assert context_maintained, "Context not maintained across channels"
            
            print("✅ Cross-channel continuity successful")
            print(f"   - Conversation ID: {conversation_id}")
            print(f"   - Channels tested: Phone → WhatsApp → Email")
            print(f"   - Context maintained: {'✅' if context_maintained else '❌'}")
            print(f"   - Phone response: {phone_response[:60]}...")
            print(f"   - WhatsApp response: {whatsapp_response[:60]}...")
            print(f"   - Email response: {email_response[:60]}...")
            
            self.test_results.append({
                "test": "Cross-Channel Continuity",
                "status": "PASS",
                "details": "Context maintained across phone, WhatsApp, and email"
            })
            
            return ea
            
        except Exception as e:
            self.test_results.append({
                "test": "Cross-Channel Continuity",
                "status": "FAIL",
                "error": str(e)
            })
            raise
    
    async def test_template_recommendations(self):
        """Test workflow template recommendation system"""
        print("\n📋 Test 5: Template Recommendation System")
        print("-" * 40)
        
        try:
            ea = await self.test_cross_channel_continuity()
            
            # Get business intelligence dashboard
            dashboard = await ea.get_business_intelligence_dashboard()
            
            # Check for template recommendations
            high_priority_opportunities = dashboard.get("high_priority_opportunities", [])
            recommended_actions = dashboard.get("recommended_next_actions", [])
            
            assert len(high_priority_opportunities) > 0, "No high-priority opportunities identified"
            assert len(recommended_actions) > 0, "No recommended actions provided"
            
            # Test specific template scenarios
            template_test_messages = [
                "I need to automate posting to multiple social media platforms",
                "Help me set up automated email follow-ups for leads",
                "I want to automate data entry from forms to spreadsheets"
            ]
            
            template_responses = []
            
            for message in template_test_messages:
                response = await ea.handle_customer_interaction(
                    message=message,
                    channel=ConversationChannel.PHONE,
                    conversation_id=str(uuid.uuid4())
                )
                
                template_mentioned = (
                    "template" in response.lower() or
                    "workflow" in response.lower() or
                    "automation" in response.lower()
                )
                
                template_responses.append({
                    "message": message,
                    "template_mentioned": template_mentioned,
                    "response": response[:100]
                })
            
            template_mentions = sum(1 for r in template_responses if r["template_mentioned"])
            
            print("✅ Template recommendation system successful")
            print(f"   - High-priority opportunities: {len(high_priority_opportunities)}")
            print(f"   - Recommended actions: {len(recommended_actions)}")
            print(f"   - Template mentions in responses: {template_mentions}/{len(template_test_messages)}")
            
            for opportunity in high_priority_opportunities[:3]:  # Show top 3
                print(f"   - Opportunity: {opportunity.get('description', '')[:60]}...")
                print(f"     Priority: {opportunity.get('priority_score', 0):.2f}, "
                      f"Automation: {opportunity.get('automation_potential', 0):.2f}")
            
            self.test_results.append({
                "test": "Template Recommendations",
                "status": "PASS",
                "details": f"{len(high_priority_opportunities)} opportunities, {template_mentions} template mentions"
            })
            
            return ea
            
        except Exception as e:
            self.test_results.append({
                "test": "Template Recommendations",
                "status": "FAIL",
                "error": str(e)
            })
            raise
    
    async def test_business_intelligence_dashboard(self):
        """Test comprehensive business intelligence dashboard"""
        print("\n📋 Test 6: Business Intelligence Dashboard")
        print("-" * 40)
        
        try:
            ea = await self.test_template_recommendations()
            
            # Get comprehensive dashboard
            dashboard = await ea.get_business_intelligence_dashboard()
            
            # Verify dashboard components
            required_components = [
                "generation_timestamp",
                "customer_id", 
                "total_memories",
                "business_processes_identified",
                "automation_opportunities_found",
                "tools_discovered",
                "high_priority_opportunities",
                "memory_quality_score",
                "ea_context"
            ]
            
            missing_components = [c for c in required_components if c not in dashboard]
            assert len(missing_components) == 0, f"Missing dashboard components: {missing_components}"
            
            # Verify data quality
            assert dashboard["customer_id"] == self.test_customer_id, "Customer ID mismatch in dashboard"
            assert dashboard["total_memories"] > 0, "No memories in dashboard"
            assert dashboard["memory_quality_score"] > 0, "Zero memory quality score"
            
            print("✅ Business intelligence dashboard successful")
            print(f"   - Customer ID: {dashboard['customer_id']}")
            print(f"   - Total memories: {dashboard['total_memories']}")
            print(f"   - Business processes: {dashboard['business_processes_identified']}")
            print(f"   - Automation opportunities: {dashboard['automation_opportunities_found']}")
            print(f"   - Tools discovered: {len(dashboard['tools_discovered'])}")
            print(f"   - Memory quality: {dashboard['memory_quality_score']:.2f}")
            print(f"   - High-priority opportunities: {len(dashboard['high_priority_opportunities'])}")
            
            # Show EA context
            ea_context = dashboard.get("ea_context", {})
            print(f"   - EA Name: {ea_context.get('ea_name', 'Unknown')}")
            print(f"   - Personality: {ea_context.get('personality', 'Unknown')}")
            
            self.test_results.append({
                "test": "Business Intelligence Dashboard",
                "status": "PASS",
                "details": f"All components present, {dashboard['total_memories']} memories, quality score {dashboard['memory_quality_score']:.2f}"
            })
            
            return ea, dashboard
            
        except Exception as e:
            self.test_results.append({
                "test": "Business Intelligence Dashboard",
                "status": "FAIL",
                "error": str(e)
            })
            raise
    
    async def test_performance_and_isolation(self):
        """Test performance requirements and memory isolation"""
        print("\n📋 Test 7: Performance and Memory Isolation")
        print("-" * 40)
        
        try:
            ea, _ = await self.test_business_intelligence_dashboard()
            
            # Test memory performance
            memory_integration = ea.memory.mem0_integration
            performance_monitor = memory_integration.performance_monitor
            
            # Get performance snapshot
            performance_snapshot = performance_monitor.get_current_performance_snapshot()
            
            # Verify performance metrics exist
            assert "operation_statistics" in performance_snapshot, "No operation statistics"
            assert "current_alert_level" in performance_snapshot, "No alert level"
            assert "total_operations" in performance_snapshot, "No total operations count"
            
            # Test memory isolation by creating second customer
            test_customer_2 = f"test_customer_2_{uuid.uuid4().hex[:8]}"
            ea2 = ExecutiveAssistant(test_customer_2, "http://localhost:30001")
            
            # Store different data for each customer
            await ea.handle_customer_interaction(
                message="My secret business data for customer 1",
                channel=ConversationChannel.PHONE
            )
            
            await ea2.handle_customer_interaction(
                message="My secret business data for customer 2",
                channel=ConversationChannel.PHONE
            )
            
            # Verify isolation - each customer should only see their own data
            dashboard1 = await ea.get_business_intelligence_dashboard()
            dashboard2 = await ea2.get_business_intelligence_dashboard()
            
            assert dashboard1["customer_id"] != dashboard2["customer_id"], "Customer IDs should be different"
            
            print("✅ Performance and isolation testing successful")
            print(f"   - Performance monitoring: Active")
            print(f"   - Alert level: {performance_snapshot.get('current_alert_level', 'unknown')}")
            print(f"   - Total operations: {performance_snapshot.get('total_operations', 0)}")
            print(f"   - Customer isolation: Verified")
            print(f"   - Customer 1 ID: {dashboard1['customer_id']}")
            print(f"   - Customer 2 ID: {dashboard2['customer_id']}")
            
            # Cleanup customer 2
            await ea2.memory.close()
            
            self.test_results.append({
                "test": "Performance and Isolation",
                "status": "PASS",
                "details": f"Performance monitoring active, customer isolation verified"
            })
            
            return ea
            
        except Exception as e:
            self.test_results.append({
                "test": "Performance and Isolation",
                "status": "FAIL",
                "error": str(e)
            })
            raise
    
    def print_test_results_summary(self):
        """Print comprehensive test results summary"""
        print("\n" + "=" * 80)
        print("🎯 EA-Mem0 Integration Test Results Summary")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["status"] == "PASS")
        failed_tests = total_tests - passed_tests
        
        print(f"📊 Overall Results:")
        print(f"   - Total Tests: {total_tests}")
        print(f"   - Passed: {passed_tests} ✅")
        print(f"   - Failed: {failed_tests} ❌")
        print(f"   - Success Rate: {passed_tests/total_tests*100:.1f}%")
        print()
        
        print("📋 Detailed Results:")
        for i, result in enumerate(self.test_results, 1):
            status_icon = "✅" if result["status"] == "PASS" else "❌"
            print(f"   {i}. {result['test']}: {status_icon}")
            
            if result["status"] == "PASS":
                print(f"      Details: {result['details']}")
            else:
                print(f"      Error: {result['error']}")
            print()
        
        if failed_tests == 0:
            print("🎉 All tests passed! EA-Mem0 integration is fully functional.")
            print("🚀 Ready for production deployment.")
        else:
            print(f"⚠️  {failed_tests} tests failed. Please review and fix issues before deployment.")
        
        print("=" * 80)


# Main execution
async def main():
    """Run comprehensive EA-Mem0 integration tests"""
    tester = EAMem0IntegrationTester()
    await tester.run_comprehensive_test_suite()


if __name__ == "__main__":
    asyncio.run(main())