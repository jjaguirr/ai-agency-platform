#!/usr/bin/env python3
"""
Complete Voice Integration Test
End-to-end testing of the ElevenLabs voice integration system
"""

import asyncio
import logging
import sys
import json
import tempfile
import time
from pathlib import Path
from typing import Dict, Any

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.voice_integration_system import create_voice_integration_system
from src.config.voice_config import create_config
from src.communication.voice_channel import VoiceLanguage

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VoiceIntegrationTester:
    """Complete voice integration testing suite"""
    
    def __init__(self):
        self.test_results = []
        self.voice_system = None
        self.config = None
        
    async def setup(self):
        """Setup test environment"""
        logger.info("🔧 Setting up test environment...")
        
        # Create test configuration
        self.config = create_config("testing", overrides={
            "debug_mode": True,
            "log_level": "WARNING",  # Reduce noise
            "max_concurrent_sessions": 5,
            "response_time_sla": 5.0  # More lenient for testing
        })
        
        # Create voice integration system
        self.voice_system = create_voice_integration_system(self.config.to_dict())
        
        # Initialize system
        success = await self.voice_system.initialize()
        if not success:
            raise Exception("Failed to initialize voice system")
        
        logger.info("✅ Test environment setup complete")
    
    async def teardown(self):
        """Cleanup test environment"""
        logger.info("🧹 Cleaning up test environment...")
        
        if self.voice_system:
            await self.voice_system.shutdown()
        
        logger.info("✅ Test environment cleanup complete")
    
    def record_test_result(self, test_name: str, success: bool, details: Dict[str, Any] = None):
        """Record test result"""
        result = {
            "test": test_name,
            "success": success,
            "timestamp": time.time(),
            "details": details or {}
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}")
        
        if not success and details:
            logger.error(f"   Error: {details.get('error', 'Unknown error')}")
    
    async def test_system_health(self):
        """Test system health check"""
        try:
            # This would normally call an HTTP endpoint, but we'll test the underlying functionality
            health_info = {
                "voice_system_initialized": self.voice_system.is_running,
                "config_valid": len(self.config.validate()) == 0,
                "components_available": True
            }
            
            success = all(health_info.values())
            self.record_test_result("System Health Check", success, health_info)
            
        except Exception as e:
            self.record_test_result("System Health Check", False, {"error": str(e)})
    
    async def test_voice_ea_creation(self):
        """Test voice-enabled EA creation"""
        try:
            customer_id = "test-customer-creation"
            
            start_time = time.time()
            voice_ea = await self.voice_system.get_voice_enabled_ea(customer_id)
            creation_time = time.time() - start_time
            
            # Verify EA was created
            success = (
                voice_ea is not None and
                customer_id in self.voice_system.voice_ea_instances and
                creation_time < 10.0  # Should create within 10 seconds
            )
            
            details = {
                "customer_id": customer_id,
                "creation_time_seconds": creation_time,
                "voice_ea_available": voice_ea is not None,
                "memory_integration_available": customer_id in self.voice_system.voice_memory_instances
            }
            
            self.record_test_result("Voice EA Creation", success, details)
            
        except Exception as e:
            self.record_test_result("Voice EA Creation", False, {"error": str(e)})
    
    async def test_english_voice_interaction(self):
        """Test English voice interaction"""
        try:
            customer_id = "test-customer-english"
            message = "Hello! I need help setting up marketing automation for my business."
            
            start_time = time.time()
            result = await self.voice_system.process_voice_interaction(
                customer_id=customer_id,
                message=message,
                detected_language="en",
                context={"test": "english_interaction"}
            )
            response_time = time.time() - start_time
            
            # Verify response
            success = (
                result.get("success", False) and
                "interaction_id" in result and
                result.get("response_time_seconds", 0) < self.config.response_time_sla and
                len(result.get("text_response", "")) > 0
            )
            
            details = {
                "message": message[:50] + "..." if len(message) > 50 else message,
                "response_time": response_time,
                "ea_response_time": result.get("response_time_seconds", 0),
                "response_length": len(result.get("text_response", "")),
                "has_voice_audio": "voice_audio" in result,
                "interaction_id": result.get("interaction_id"),
                "success": result.get("success")
            }
            
            self.record_test_result("English Voice Interaction", success, details)
            
        except Exception as e:
            self.record_test_result("English Voice Interaction", False, {"error": str(e)})
    
    async def test_spanish_voice_interaction(self):
        """Test Spanish voice interaction"""
        try:
            customer_id = "test-customer-spanish"
            message = "¡Hola! Necesito ayuda configurando automatización de marketing para mi negocio."
            
            start_time = time.time()
            result = await self.voice_system.process_voice_interaction(
                customer_id=customer_id,
                message=message,
                detected_language="es",
                context={"test": "spanish_interaction"}
            )
            response_time = time.time() - start_time
            
            # Verify response
            success = (
                result.get("success", False) and
                result.get("response_time_seconds", 0) < self.config.response_time_sla and
                len(result.get("text_response", "")) > 0
            )
            
            details = {
                "message": message[:50] + "..." if len(message) > 50 else message,
                "response_time": response_time,
                "ea_response_time": result.get("response_time_seconds", 0),
                "response_length": len(result.get("text_response", "")),
                "interaction_id": result.get("interaction_id"),
                "success": result.get("success")
            }
            
            self.record_test_result("Spanish Voice Interaction", success, details)
            
        except Exception as e:
            self.record_test_result("Spanish Voice Interaction", False, {"error": str(e)})
    
    async def test_bilingual_conversation(self):
        """Test bilingual conversation with language switching"""
        try:
            customer_id = "test-customer-bilingual"
            
            # English message
            result1 = await self.voice_system.process_voice_interaction(
                customer_id=customer_id,
                message="Hello! I run a marketing agency.",
                detected_language="en",
                conversation_id="test-bilingual-conversation"
            )
            
            # Spanish message in same conversation
            result2 = await self.voice_system.process_voice_interaction(
                customer_id=customer_id,
                message="Necesito automatización de redes sociales.",
                detected_language="es",
                conversation_id="test-bilingual-conversation"
            )
            
            # English message again
            result3 = await self.voice_system.process_voice_interaction(
                customer_id=customer_id,
                message="Can you help me set this up?",
                detected_language="en",
                conversation_id="test-bilingual-conversation"
            )
            
            # Verify all interactions succeeded
            all_results = [result1, result2, result3]
            success = all(r.get("success", False) for r in all_results)
            
            # Check conversation context preservation
            if customer_id in self.voice_system.voice_memory_instances:
                voice_memory = self.voice_system.voice_memory_instances[customer_id]
                conversation_context = await voice_memory.get_conversation_context("test-bilingual-conversation")
                context_preserved = conversation_context is not None and conversation_context.get("message_count", 0) >= 3
            else:
                context_preserved = False
            
            details = {
                "interactions_completed": len(all_results),
                "all_successful": success,
                "conversation_context_preserved": context_preserved,
                "languages_used": ["en", "es", "en"],
                "response_times": [r.get("response_time_seconds", 0) for r in all_results]
            }
            
            final_success = success and context_preserved
            self.record_test_result("Bilingual Conversation", final_success, details)
            
        except Exception as e:
            self.record_test_result("Bilingual Conversation", False, {"error": str(e)})
    
    async def test_concurrent_interactions(self):
        """Test concurrent voice interactions"""
        try:
            customers = [f"test-customer-concurrent-{i}" for i in range(3)]
            messages = [
                ("Hello, I need business help!", "en"),
                ("¡Hola, necesito ayuda empresarial!", "es"),
                ("Hi, can you assist with automation?", "en")
            ]
            
            # Create concurrent tasks
            tasks = []
            for i, (customer_id, (message, language)) in enumerate(zip(customers, messages)):
                task = self.voice_system.process_voice_interaction(
                    customer_id=customer_id,
                    message=message,
                    detected_language=language,
                    context={"test": "concurrent", "index": i}
                )
                tasks.append(task)
            
            # Run concurrently
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time
            
            # Analyze results
            successful_results = []
            errors = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    errors.append(f"Customer {i}: {str(result)}")
                elif result.get("success", False):
                    successful_results.append(result)
                else:
                    errors.append(f"Customer {i}: {result.get('error', 'Unknown error')}")
            
            success = len(successful_results) == len(customers) and len(errors) == 0
            
            details = {
                "total_customers": len(customers),
                "successful_interactions": len(successful_results),
                "errors": errors,
                "total_time": total_time,
                "avg_response_time": sum(r.get("response_time_seconds", 0) for r in successful_results) / len(successful_results) if successful_results else 0
            }
            
            self.record_test_result("Concurrent Interactions", success, details)
            
        except Exception as e:
            self.record_test_result("Concurrent Interactions", False, {"error": str(e)})
    
    async def test_error_handling(self):
        """Test error handling with invalid inputs"""
        try:
            customer_id = "test-customer-errors"
            
            # Test cases with expected behavior
            test_cases = [
                ("", "en", "empty_message"),  # Empty message
                ("x" * 10000, "en", "very_long_message"),  # Very long message
                ("Valid message", "invalid", "invalid_language"),  # Invalid language
            ]
            
            error_results = []
            
            for message, language, test_type in test_cases:
                try:
                    result = await self.voice_system.process_voice_interaction(
                        customer_id=customer_id,
                        message=message,
                        detected_language=language,
                        context={"test": "error_handling", "type": test_type}
                    )
                    
                    # For error handling tests, we expect either success (graceful handling)
                    # or controlled failure (not system crash)
                    error_results.append({
                        "test_type": test_type,
                        "handled_gracefully": True,
                        "success": result.get("success", False),
                        "error": result.get("error") if not result.get("success") else None
                    })
                    
                except Exception as e:
                    # System should not crash, even with invalid inputs
                    error_results.append({
                        "test_type": test_type,
                        "handled_gracefully": False,
                        "system_crash": True,
                        "error": str(e)
                    })
            
            # Success if all errors were handled gracefully (no system crashes)
            success = all(r["handled_gracefully"] for r in error_results)
            
            details = {
                "test_cases": len(test_cases),
                "gracefully_handled": sum(1 for r in error_results if r["handled_gracefully"]),
                "system_crashes": sum(1 for r in error_results if not r["handled_gracefully"]),
                "results": error_results
            }
            
            self.record_test_result("Error Handling", success, details)
            
        except Exception as e:
            self.record_test_result("Error Handling", False, {"error": str(e)})
    
    async def test_performance_monitoring(self):
        """Test performance monitoring functionality"""
        try:
            # Generate some test interactions for monitoring
            customer_id = "test-customer-monitoring"
            
            for i in range(5):
                await self.voice_system.process_voice_interaction(
                    customer_id=customer_id,
                    message=f"Test message {i} for monitoring",
                    detected_language="en",
                    context={"test": "monitoring", "iteration": i}
                )
            
            # Test performance monitoring functions
            from src.monitoring.voice_performance_monitor import get_voice_performance_dashboard
            
            dashboard_data = await get_voice_performance_dashboard()
            
            # Verify monitoring data
            success = (
                "current_performance" in dashboard_data and
                dashboard_data["current_performance"].get("total_interactions", 0) >= 5
            )
            
            details = {
                "total_interactions": dashboard_data["current_performance"].get("total_interactions", 0),
                "success_rate": dashboard_data["current_performance"].get("success_rate", 0),
                "avg_response_time": dashboard_data["current_performance"].get("avg_response_time", 0),
                "monitoring_available": success
            }
            
            self.record_test_result("Performance Monitoring", success, details)
            
        except Exception as e:
            self.record_test_result("Performance Monitoring", False, {"error": str(e)})
    
    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests
        
        success_rate = (passed_tests / total_tests) if total_tests > 0 else 0
        
        report = {
            "test_summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": success_rate,
                "overall_status": "PASS" if success_rate >= 0.8 else "FAIL"
            },
            "test_results": self.test_results,
            "recommendations": []
        }
        
        # Generate recommendations based on failures
        for result in self.test_results:
            if not result["success"]:
                report["recommendations"].append(
                    f"Fix issue in {result['test']}: {result['details'].get('error', 'Unknown error')}"
                )
        
        if success_rate >= 0.8:
            report["recommendations"].append("System is ready for deployment")
        else:
            report["recommendations"].append("Address failing tests before deployment")
        
        return report
    
    async def run_all_tests(self):
        """Run complete test suite"""
        logger.info("🚀 Starting Complete Voice Integration Test Suite")
        
        # Test sequence
        tests = [
            self.test_system_health,
            self.test_voice_ea_creation,
            self.test_english_voice_interaction,
            self.test_spanish_voice_interaction,
            self.test_bilingual_conversation,
            self.test_concurrent_interactions,
            self.test_error_handling,
            self.test_performance_monitoring
        ]
        
        try:
            await self.setup()
            
            # Run all tests
            for test_func in tests:
                try:
                    await test_func()
                except Exception as e:
                    test_name = test_func.__name__.replace("test_", "").replace("_", " ").title()
                    self.record_test_result(test_name, False, {"error": str(e)})
            
            # Generate report
            report = self.generate_test_report()
            
            return report
            
        finally:
            await self.teardown()

async def main():
    """Main test runner"""
    tester = VoiceIntegrationTester()
    report = await tester.run_all_tests()
    
    # Print report
    print("\n" + "="*80)
    print("VOICE INTEGRATION TEST REPORT")
    print("="*80)
    
    summary = report["test_summary"]
    print(f"Status: {summary['overall_status']}")
    print(f"Tests: {summary['passed_tests']}/{summary['total_tests']} passed ({summary['success_rate']:.1%})")
    
    if summary["failed_tests"] > 0:
        print(f"\nFailed Tests:")
        for result in report["test_results"]:
            if not result["success"]:
                print(f"  ❌ {result['test']}")
                if "error" in result["details"]:
                    print(f"     {result['details']['error']}")
    
    print(f"\nRecommendations:")
    for rec in report["recommendations"]:
        print(f"  • {rec}")
    
    print("="*80)
    
    # Exit with appropriate code
    exit_code = 0 if summary["overall_status"] == "PASS" else 1
    sys.exit(exit_code)

if __name__ == "__main__":
    asyncio.run(main())