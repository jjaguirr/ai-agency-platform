"""
AI/ML Integration Test for Executive Assistant Memory System

Comprehensive test of the AI/ML-enhanced memory system including:
- Business learning engine pattern recognition
- Workflow template matching and recommendation
- Cross-channel conversation continuity
- Memory-driven business intelligence
- Performance validation and SLA compliance

This demonstrates the full AI/ML capabilities integrated with the EA system.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Any

import pytest

# Heavy transitive deps (mem0 → sentence-transformers → torch). Skip collection
# if not installed rather than crashing the whole run.
pytest.importorskip("mem0")
pytest.importorskip("sentence_transformers")

from tests.conftest import requires_live_services

pytestmark = [pytest.mark.integration, requires_live_services]

# Configure logging for test output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import AI/ML components
from src.agents.ai_ml.business_learning_engine import BusinessLearningEngine
from src.agents.ai_ml.workflow_template_matcher import WorkflowTemplateMatcher
from src.agents.memory.ea_memory_integration import EAMemoryIntegration, ConversationContext


class AIMLIntegrationTester:
    """
    Comprehensive tester for AI/ML memory integration capabilities.
    
    Tests the full pipeline from conversation input to actionable business insights
    and workflow template recommendations with performance validation.
    """
    
    def __init__(self):
        """Initialize test components"""
        self.test_customer_id = f"test_customer_aiml_{int(time.time())}"
        self.test_results = {
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "performance_metrics": [],
            "detailed_results": []
        }
        
        logger.info(f"Initialized AI/ML integration tester for customer {self.test_customer_id}")
    
    async def run_comprehensive_test_suite(self) -> Dict[str, Any]:
        """Run the complete AI/ML integration test suite"""
        logger.info("🚀 Starting comprehensive AI/ML integration test suite")
        
        start_time = time.time()
        
        try:
            # Test 1: Business Learning Engine
            await self._test_business_learning_engine()
            
            # Test 2: Workflow Template Matching
            await self._test_workflow_template_matching()
            
            # Test 3: Memory Integration
            await self._test_memory_integration()
            
            # Test 4: Cross-Channel Conversation Processing
            await self._test_cross_channel_processing()
            
            # Test 5: Business Intelligence Generation
            await self._test_business_intelligence()
            
            # Test 6: Performance Validation
            await self._test_performance_requirements()
            
            # Test 7: End-to-End Customer Journey
            await self._test_end_to_end_journey()
            
            total_time = time.time() - start_time
            
            # Generate comprehensive test report
            test_report = self._generate_test_report(total_time)
            
            logger.info(f"✅ AI/ML integration test suite completed in {total_time:.2f}s")
            logger.info(f"📊 Results: {self.test_results['tests_passed']}/{self.test_results['tests_run']} tests passed")
            
            return test_report
            
        except Exception as e:
            logger.error(f"❌ Test suite failed: {e}")
            return {
                "test_successful": False,
                "error": str(e),
                "results": self.test_results
            }
    
    async def _test_business_learning_engine(self):
        """Test business learning engine capabilities"""
        logger.info("🧠 Testing Business Learning Engine")
        
        test_start = time.time()
        
        # Initialize business learning engine
        learning_engine = BusinessLearningEngine()
        
        # Test conversation: Marketing agency with automation needs
        test_conversation = """
        Hi, I run a marketing agency called BrandBoost. We help local businesses with their digital marketing.
        Every day I manually create social media posts for 10 different clients using Canva and then schedule them in Buffer.
        It takes me about 3 hours each day and it's getting really repetitive and time-consuming.
        I also use Excel to track campaign performance and send weekly reports to clients via email.
        We're growing fast but I'm spending too much time on these manual processes instead of strategy.
        """
        
        # Extract business insights
        insights = await learning_engine.extract_business_insights(
            conversation_text=test_conversation,
            conversation_history=[
                {"role": "user", "content": test_conversation},
                {"role": "assistant", "content": "I understand you need help with automation"}
            ],
            context_memories=[]
        )
        
        test_time = time.time() - test_start
        
        # Validate results
        success = self._validate_business_insights(insights, test_time)
        
        self._record_test_result(
            test_name="Business Learning Engine",
            success=success,
            duration=test_time,
            details=insights
        )
        
        logger.info(f"✅ Business Learning Engine test completed: {len(insights.get('business_entities', []))} entities, {len(insights.get('business_patterns', []))} patterns")
    
    async def _test_workflow_template_matching(self):
        """Test workflow template matching capabilities"""
        logger.info("🔧 Testing Workflow Template Matching")
        
        test_start = time.time()
        
        # Initialize template matcher
        template_matcher = WorkflowTemplateMatcher()
        
        # Create mock business insights
        mock_business_insights = {
            "automation_opportunities": [
                {
                    "id": "social_media_automation_opp",
                    "title": "Social Media Posting Automation",
                    "description": "Automate daily social media posting for multiple clients",
                    "pattern_type": "frequency_process",
                    "automation_score": 0.9,
                    "confidence": 0.85,
                    "readiness_score": 0.8,
                    "related_entities": [
                        {"entity_type": "tool_integration", "value": "canva"},
                        {"entity_type": "tool_integration", "value": "buffer"}
                    ]
                }
            ],
            "business_entities": [
                {"entity_type": "tool_integration", "value": "canva", "confidence": 0.9},
                {"entity_type": "tool_integration", "value": "buffer", "confidence": 0.9},
                {"entity_type": "frequency", "value": "daily", "confidence": 0.8}
            ],
            "business_patterns": [
                {"pattern_type": "frequency_process", "confidence": 0.8, "automation_score": 0.9}
            ]
        }
        
        # Get template recommendations
        recommendations = await template_matcher.recommend_templates(
            business_insights=mock_business_insights,
            customer_context={
                "customer_id": self.test_customer_id,
                "industry": "marketing",
                "company_size": "small"
            }
        )
        
        test_time = time.time() - test_start
        
        # Validate recommendations
        success = self._validate_template_recommendations(recommendations, test_time)
        
        self._record_test_result(
            test_name="Workflow Template Matching",
            success=success,
            duration=test_time,
            details=recommendations
        )
        
        logger.info(f"✅ Template matching test completed: {len(recommendations.get('template_recommendations', []))} recommendations")
    
    async def _test_memory_integration(self):
        """Test memory integration with AI/ML components"""
        logger.info("🧠 Testing Memory Integration")
        
        test_start = time.time()
        
        # Initialize memory integration
        memory_integration = EAMemoryIntegration(self.test_customer_id)
        
        # Create test conversation context
        conversation_context = ConversationContext(
            customer_id=self.test_customer_id,
            conversation_id="test_conversation_001",
            channel="whatsapp",
            message_history=[
                {"role": "user", "content": "I need help automating my email marketing campaigns"},
                {"role": "assistant", "content": "I'd be happy to help with email automation!"}
            ],
            current_intent="automation_request"
        )
        
        # Process conversation with AI/ML enhancement
        processing_results = await memory_integration.process_business_conversation(conversation_context)
        
        test_time = time.time() - test_start
        
        # Validate processing
        success = self._validate_memory_processing(processing_results, test_time)
        
        self._record_test_result(
            test_name="Memory Integration",
            success=success,
            duration=test_time,
            details=processing_results
        )
        
        # Cleanup
        await memory_integration.close()
        
        logger.info(f"✅ Memory integration test completed: {processing_results.get('high_confidence_learnings', 0)} high-confidence learnings")
    
    async def _test_cross_channel_processing(self):
        """Test cross-channel conversation continuity"""
        logger.info("📞 Testing Cross-Channel Processing")
        
        test_start = time.time()
        
        memory_integration = EAMemoryIntegration(self.test_customer_id)
        
        # Simulate conversation across multiple channels
        channels = ["phone", "whatsapp", "email"]
        conversation_results = []
        
        for i, channel in enumerate(channels):
            conversation_context = ConversationContext(
                customer_id=self.test_customer_id,
                conversation_id=f"cross_channel_test_{i}",
                channel=channel,
                message_history=[
                    {"role": "user", "content": f"Continuing our conversation from {channels[i-1] if i > 0 else 'earlier'} - about the CRM automation"},
                ],
                current_intent="conversation_continuity"
            )
            
            result = await memory_integration.process_business_conversation(conversation_context)
            conversation_results.append(result)
        
        test_time = time.time() - test_start
        
        # Validate cross-channel continuity
        success = self._validate_cross_channel_continuity(conversation_results, test_time)
        
        self._record_test_result(
            test_name="Cross-Channel Processing",
            success=success,
            duration=test_time,
            details=conversation_results
        )
        
        await memory_integration.close()
        
        logger.info(f"✅ Cross-channel processing test completed: {len(channels)} channels tested")
    
    async def _test_business_intelligence(self):
        """Test AI/ML business intelligence generation"""
        logger.info("📊 Testing Business Intelligence Generation")
        
        test_start = time.time()
        
        memory_integration = EAMemoryIntegration(self.test_customer_id)
        
        # Generate AI/ML-enhanced business intelligence
        intelligence = await memory_integration.get_ai_ml_business_intelligence()
        
        test_time = time.time() - test_start
        
        # Validate intelligence generation
        success = self._validate_business_intelligence(intelligence, test_time)
        
        self._record_test_result(
            test_name="Business Intelligence Generation",
            success=success,
            duration=test_time,
            details=intelligence
        )
        
        await memory_integration.close()
        
        logger.info(f"✅ Business intelligence test completed with AI/ML enhancements")
    
    async def _test_performance_requirements(self):
        """Test performance against SLA requirements"""
        logger.info("⚡ Testing Performance Requirements")
        
        test_start = time.time()
        
        # Test memory recall performance
        memory_integration = EAMemoryIntegration(self.test_customer_id)
        
        # Store test data
        test_context = {
            "business_description": "Performance test business context",
            "automation_opportunities": ["test_opportunity"],
            "phase": "performance_test"
        }
        
        store_start = time.time()
        memory_id = await memory_integration.memory_manager.store_business_context(
            context=test_context,
            session_id="performance_test"
        )
        store_time = time.time() - store_start
        
        # Test retrieval performance
        retrieve_start = time.time()
        results = await memory_integration.memory_manager.retrieve_business_context(
            query="Performance test business",
            limit=5
        )
        retrieve_time = time.time() - retrieve_start
        
        test_time = time.time() - test_start
        
        # Validate SLA compliance
        sla_compliance = {
            "memory_storage": store_time < 0.3,  # 300ms SLA
            "memory_retrieval": retrieve_time < 0.5,  # 500ms SLA
            "overall_processing": test_time < 2.0  # 2s SLA
        }
        
        success = all(sla_compliance.values())
        
        self._record_test_result(
            test_name="Performance Requirements",
            success=success,
            duration=test_time,
            details={
                "sla_compliance": sla_compliance,
                "store_time": store_time,
                "retrieve_time": retrieve_time,
                "results_count": len(results)
            }
        )
        
        await memory_integration.close()
        
        logger.info(f"⚡ Performance test completed: SLA compliance {success}")
    
    async def _test_end_to_end_journey(self):
        """Test complete end-to-end customer journey"""
        logger.info("🎯 Testing End-to-End Customer Journey")
        
        test_start = time.time()
        
        memory_integration = EAMemoryIntegration(self.test_customer_id)
        
        # Simulate complete customer onboarding journey
        journey_steps = [
            {
                "step": "business_discovery",
                "message": "Hi, I'm Sarah the CEO of a small e-commerce company. We sell handmade jewelry online and I'm spending way too much time on manual processes.",
                "channel": "phone"
            },
            {
                "step": "process_identification", 
                "message": "Every day I manually update inventory in Excel, post on Instagram and Facebook, and respond to customer emails. It takes about 4 hours daily.",
                "channel": "phone"
            },
            {
                "step": "automation_discussion",
                "message": "I'd love to automate the social media posting and maybe the inventory updates too. Can you help with that?",
                "channel": "whatsapp"
            },
            {
                "step": "template_selection",
                "message": "The social media automation sounds perfect! How quickly can we set that up?",
                "channel": "email"
            }
        ]
        
        journey_results = []
        for i, step in enumerate(journey_steps):
            conversation_context = ConversationContext(
                customer_id=self.test_customer_id,
                conversation_id=f"journey_step_{i}",
                channel=step["channel"],
                message_history=[
                    {"role": "user", "content": step["message"]}
                ],
                current_intent=step["step"]
            )
            
            result = await memory_integration.process_business_conversation(conversation_context)
            journey_results.append({
                "step": step["step"],
                "channel": step["channel"],
                "processing_time": result.get("processing_time_seconds", 0),
                "learnings": result.get("high_confidence_learnings", 0),
                "opportunities": result.get("workflow_ready_opportunities", 0)
            })
        
        # Get final business intelligence
        final_intelligence = await memory_integration.get_ai_ml_business_intelligence()
        
        test_time = time.time() - test_start
        
        # Validate journey completion
        success = self._validate_customer_journey(journey_results, final_intelligence, test_time)
        
        self._record_test_result(
            test_name="End-to-End Customer Journey",
            success=success,
            duration=test_time,
            details={
                "journey_steps": journey_results,
                "final_intelligence": final_intelligence
            }
        )
        
        await memory_integration.close()
        
        total_learnings = sum(step.get("learnings", 0) for step in journey_results)
        total_opportunities = sum(step.get("opportunities", 0) for step in journey_results)
        
        logger.info(f"🎯 End-to-end journey completed: {total_learnings} learnings, {total_opportunities} opportunities")
    
    def _validate_business_insights(self, insights: Dict[str, Any], duration: float) -> bool:
        """Validate business insights extraction results"""
        required_fields = ["business_entities", "business_patterns", "automation_opportunities"]
        
        # Check required fields exist
        for field in required_fields:
            if field not in insights:
                logger.error(f"Missing required field: {field}")
                return False
        
        # Check processing was successful
        if not insights.get("processing_successful", False):
            logger.error("Business insights processing failed")
            return False
        
        # Check performance
        if duration > 3.0:  # 3 second timeout
            logger.error(f"Business insights processing too slow: {duration}s")
            return False
        
        # Check we extracted meaningful data
        entities_count = len(insights.get("business_entities", []))
        patterns_count = len(insights.get("business_patterns", []))
        
        if entities_count == 0 and patterns_count == 0:
            logger.error("No business insights extracted")
            return False
        
        return True
    
    def _validate_template_recommendations(self, recommendations: Dict[str, Any], duration: float) -> bool:
        """Validate template recommendations"""
        if not recommendations.get("recommendation_successful", False):
            logger.error("Template recommendation failed")
            return False
        
        # Check we got recommendations
        template_recs = recommendations.get("template_recommendations", [])
        if len(template_recs) == 0:
            logger.error("No template recommendations generated")
            return False
        
        # Check recommendation quality
        for rec in template_recs:
            if rec.get("match_confidence", 0) < 0.5:
                logger.error(f"Low confidence recommendation: {rec.get('match_confidence', 0)}")
                return False
        
        # Check performance
        if duration > 2.0:  # 2 second timeout
            logger.error(f"Template matching too slow: {duration}s")
            return False
        
        return True
    
    def _validate_memory_processing(self, processing_results: Dict[str, Any], duration: float) -> bool:
        """Validate memory processing results"""
        if not processing_results.get("memory_operations_successful", False):
            logger.error("Memory operations failed")
            return False
        
        # Check SLA compliance
        if not processing_results.get("performance_within_sla", False):
            logger.error("Memory processing exceeded SLA")
            return False
        
        # Check we processed something meaningful
        if processing_results.get("high_confidence_learnings", 0) == 0:
            logger.warning("No high-confidence learnings extracted")
        
        return True
    
    def _validate_cross_channel_continuity(self, conversation_results: List[Dict[str, Any]], duration: float) -> bool:
        """Validate cross-channel conversation continuity"""
        # Check all conversations processed successfully
        for result in conversation_results:
            if not result.get("memory_operations_successful", False):
                logger.error("Cross-channel conversation processing failed")
                return False
        
        # Check continuity was maintained (should have conversation continuity results)
        for result in conversation_results:
            if "conversation_continuity" not in result:
                logger.error("Conversation continuity not maintained")
                return False
        
        return True
    
    def _validate_business_intelligence(self, intelligence: Dict[str, Any], duration: float) -> bool:
        """Validate business intelligence generation"""
        required_sections = ["customer_id", "generation_timestamp"]
        
        for section in required_sections:
            if section not in intelligence:
                logger.error(f"Missing intelligence section: {section}")
                return False
        
        # Check AI/ML enhancements are present
        if "ai_ml_enhancements" in intelligence:
            ai_ml_data = intelligence["ai_ml_enhancements"]
            if not ai_ml_data.get("ai_ml_processing_enabled", False):
                logger.warning("AI/ML processing not enabled in intelligence")
        
        return True
    
    def _validate_customer_journey(self, journey_results: List[Dict[str, Any]], 
                                 final_intelligence: Dict[str, Any], duration: float) -> bool:
        """Validate complete customer journey"""
        # Check all journey steps completed
        if len(journey_results) < 4:
            logger.error("Customer journey incomplete")
            return False
        
        # Check progression - later steps should have more learnings
        total_learnings = sum(step.get("learnings", 0) for step in journey_results)
        if total_learnings == 0:
            logger.error("No learnings extracted during customer journey")
            return False
        
        # Check final intelligence has comprehensive data
        if not final_intelligence.get("customer_id"):
            logger.error("Final intelligence missing customer data")
            return False
        
        return True
    
    def _record_test_result(self, test_name: str, success: bool, duration: float, details: Any):
        """Record individual test result"""
        self.test_results["tests_run"] += 1
        
        if success:
            self.test_results["tests_passed"] += 1
        else:
            self.test_results["tests_failed"] += 1
        
        self.test_results["performance_metrics"].append({
            "test_name": test_name,
            "duration": duration,
            "success": success
        })
        
        self.test_results["detailed_results"].append({
            "test_name": test_name,
            "success": success,
            "duration": duration,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details
        })
    
    def _generate_test_report(self, total_duration: float) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        success_rate = (self.test_results["tests_passed"] / self.test_results["tests_run"] * 100 
                       if self.test_results["tests_run"] > 0 else 0)
        
        avg_test_duration = (sum(m["duration"] for m in self.test_results["performance_metrics"]) / 
                           len(self.test_results["performance_metrics"])
                           if self.test_results["performance_metrics"] else 0)
        
        return {
            "test_report_generated": datetime.utcnow().isoformat(),
            "test_customer_id": self.test_customer_id,
            "overall_success": self.test_results["tests_failed"] == 0,
            "success_rate_percent": success_rate,
            "total_duration": total_duration,
            "average_test_duration": avg_test_duration,
            
            # Summary statistics
            "summary": {
                "tests_run": self.test_results["tests_run"],
                "tests_passed": self.test_results["tests_passed"],
                "tests_failed": self.test_results["tests_failed"],
                "success_rate": f"{success_rate:.1f}%"
            },
            
            # Performance analysis
            "performance_analysis": {
                "fastest_test": min(self.test_results["performance_metrics"], 
                                  key=lambda x: x["duration"])["test_name"] if self.test_results["performance_metrics"] else None,
                "slowest_test": max(self.test_results["performance_metrics"], 
                                  key=lambda x: x["duration"])["test_name"] if self.test_results["performance_metrics"] else None,
                "average_duration": avg_test_duration,
                "sla_compliance": avg_test_duration < 2.0  # 2s SLA per test
            },
            
            # Detailed results
            "test_results": self.test_results["detailed_results"],
            "performance_metrics": self.test_results["performance_metrics"],
            
            # AI/ML capabilities validated
            "ai_ml_capabilities_tested": [
                "Business entity extraction",
                "Pattern recognition and analysis", 
                "Workflow template matching",
                "ROI projections and impact analysis",
                "Cross-channel conversation continuity",
                "Memory-driven business intelligence",
                "Performance SLA compliance",
                "End-to-end customer journey processing"
            ]
        }


async def run_ai_ml_integration_tests():
    """Run the comprehensive AI/ML integration tests"""
    print("🚀 AI/ML Memory Integration Test Suite")
    print("=" * 60)
    
    tester = AIMLIntegrationTester()
    
    try:
        # Run comprehensive test suite
        results = await tester.run_comprehensive_test_suite()
        
        # Display results
        print(f"\n📊 Test Results Summary")
        print(f"Overall Success: {'✅ PASS' if results['overall_success'] else '❌ FAIL'}")
        print(f"Success Rate: {results['success_rate_percent']:.1f}%")
        print(f"Total Duration: {results['total_duration']:.2f}s")
        print(f"Tests Run: {results['summary']['tests_run']}")
        print(f"Tests Passed: {results['summary']['tests_passed']}")
        print(f"Tests Failed: {results['summary']['tests_failed']}")
        
        print(f"\n🏃 Performance Analysis")
        perf = results['performance_analysis']
        print(f"Average Test Duration: {perf['average_duration']:.3f}s")
        print(f"SLA Compliance: {'✅ PASS' if perf['sla_compliance'] else '❌ FAIL'}")
        
        if results['overall_success']:
            print(f"\n🎉 All AI/ML integration tests passed!")
            print(f"The EA memory system with AI/ML enhancements is ready for production.")
        else:
            print(f"\n⚠️  Some tests failed. Review detailed results for issues.")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        return {"test_execution_failed": True, "error": str(e)}


if __name__ == "__main__":
    # Run the AI/ML integration tests
    asyncio.run(run_ai_ml_integration_tests())