#!/usr/bin/env python3
"""
WhatsApp Calling Configuration and Testing Script

Tests the complete WhatsApp calling implementation including:
- Calling eligibility validation
- Settings configuration 
- Message volume checking
- Direct calling capability
- Call button functionality

Usage:
    python scripts/test_whatsapp_calling.py
"""

import asyncio
import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.communication.whatsapp_cloud_api import WhatsAppCloudAPIChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WhatsAppCallingTester:
    """Comprehensive WhatsApp calling configuration tester"""
    
    def __init__(self):
        self.customer_id = "test_customer_calling"
        self.channel = None
        self.test_results = {}
        
    async def initialize_channel(self) -> bool:
        """Initialize WhatsApp channel for testing"""
        try:
            logger.info("🔧 Initializing WhatsApp Cloud API channel...")
            
            # Check required environment variables
            required_vars = [
                'WHATSAPP_BUSINESS_TOKEN',
                'WHATSAPP_BUSINESS_PHONE_ID'
            ]
            
            missing_vars = [var for var in required_vars if not os.getenv(var)]
            if missing_vars:
                logger.error(f"❌ Missing environment variables: {missing_vars}")
                return False
            
            # Initialize channel
            self.channel = WhatsAppCloudAPIChannel(
                customer_id=self.customer_id,
                config={
                    'calling_enabled': True,
                    'business_hours': None  # 24/7 for testing
                }
            )
            
            success = await self.channel.initialize()
            if success:
                logger.info("✅ WhatsApp channel initialized successfully")
                return True
            else:
                logger.error("❌ Failed to initialize WhatsApp channel")
                return False
                
        except Exception as e:
            logger.error(f"❌ Channel initialization error: {e}")
            return False
    
    async def test_calling_eligibility(self) -> Dict[str, Any]:
        """Test calling eligibility validation"""
        logger.info("\n📋 Testing calling eligibility validation...")
        
        try:
            # Test business-level eligibility
            business_eligibility = await self.channel._check_calling_eligibility()
            logger.info(f"Business eligibility: {business_eligibility}")
            
            # Test messaging volume check
            volume_check = await self.channel._check_messaging_volume()
            logger.info(f"Volume check: {volume_check}")
            
            # Test user-specific eligibility (using test number)
            test_number = "+1234567890"  # Test number
            user_eligibility = await self.channel._validate_calling_eligibility(test_number)
            logger.info(f"User eligibility for {test_number}: {user_eligibility}")
            
            results = {
                "business_eligibility": business_eligibility,
                "volume_check": volume_check,
                "user_eligibility": user_eligibility,
                "overall_eligible": (
                    business_eligibility.get("eligible", False) and
                    volume_check.get("sufficient", False)
                )
            }
            
            if results["overall_eligible"]:
                logger.info("✅ Calling eligibility tests PASSED")
            else:
                logger.warning("⚠️ Calling eligibility tests show restrictions")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Eligibility test error: {e}")
            return {"error": str(e)}
    
    async def test_calling_configuration(self) -> Dict[str, Any]:
        """Test calling settings configuration"""
        logger.info("\n⚙️ Testing calling settings configuration...")
        
        try:
            # Test configure calling settings
            config_result = await self.channel._configure_calling_settings()
            logger.info(f"Configuration result: {config_result}")
            
            # Verify settings by reading them back
            verification_result = await self.verify_calling_settings()
            logger.info(f"Settings verification: {verification_result}")
            
            results = {
                "configuration_success": config_result,
                "settings_verification": verification_result,
                "configuration_complete": config_result and verification_result.get("settings_found", False)
            }
            
            if results["configuration_complete"]:
                logger.info("✅ Calling configuration tests PASSED")
            else:
                logger.warning("⚠️ Calling configuration tests show issues")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Configuration test error: {e}")
            return {"error": str(e)}
    
    async def verify_calling_settings(self) -> Dict[str, Any]:
        """Verify current calling settings"""
        try:
            url = f"{self.channel.base_url}/{self.channel.phone_number_id}/settings"
            headers = {
                'Authorization': f'Bearer {self.channel.access_token}',
                'Content-Type': 'application/json'
            }
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        calling_settings = data.get('calling', {})
                        
                        return {
                            "settings_found": bool(calling_settings),
                            "calling_status": calling_settings.get('status', 'UNKNOWN'),
                            "call_icon_visibility": calling_settings.get('call_icon_visibility', 'UNKNOWN'),
                            "callback_permission_status": calling_settings.get('callback_permission_status', 'UNKNOWN'),
                            "call_hours_status": calling_settings.get('call_hours', {}).get('status', 'UNKNOWN'),
                            "restrictions": calling_settings.get('restrictions', {}),
                            "full_settings": calling_settings
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "settings_found": False,
                            "error": f"HTTP {response.status}: {error_text}"
                        }
                        
        except Exception as e:
            return {
                "settings_found": False,
                "error": str(e)
            }
    
    async def test_call_button_functionality(self) -> Dict[str, Any]:
        """Test call button message functionality"""
        logger.info("\n📞 Testing call button functionality...")
        
        try:
            test_number = "+1234567890"  # Test number
            
            # Test call button message
            button_result = await self.channel.send_call_button_message(
                to_number=test_number,
                message_text="Test call button from AI Agency Platform",
                button_text="Call Test",
                ttl_minutes=1440  # 24 hours
            )
            
            logger.info(f"Call button result: {button_result}")
            
            results = {
                "button_test_success": button_result.get("success", False),
                "message_id": button_result.get("message_id"),
                "button_details": button_result,
                "test_number": test_number
            }
            
            if results["button_test_success"]:
                logger.info("✅ Call button functionality tests PASSED")
            else:
                logger.warning("⚠️ Call button functionality tests show issues")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Call button test error: {e}")
            return {"error": str(e)}
    
    async def test_direct_calling(self) -> Dict[str, Any]:
        """Test direct calling capability"""
        logger.info("\n🎯 Testing direct calling capability...")
        
        try:
            test_number = "+1234567890"  # Test number
            
            # Test direct call initiation
            call_result = await self.channel.initiate_call(test_number)
            
            logger.info(f"Direct call result: {call_result}")
            
            results = {
                "direct_call_supported": call_result.get("success", False),
                "call_id": call_result.get("call_id"),
                "call_details": call_result,
                "test_number": test_number
            }
            
            if results["direct_call_supported"]:
                logger.info("✅ Direct calling capability tests PASSED")
            else:
                logger.warning("⚠️ Direct calling capability tests show restrictions")
                logger.warning(f"Reason: {call_result.get('error', 'Unknown')}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Direct calling test error: {e}")
            return {"error": str(e)}
    
    async def test_health_check(self) -> Dict[str, Any]:
        """Test channel health check"""
        logger.info("\n🏥 Testing channel health check...")
        
        try:
            health_result = await self.channel.health_check()
            logger.info(f"Health check result: {health_result}")
            
            results = {
                "health_check_success": health_result.get("healthy", False),
                "api_healthy": health_result.get("api_healthy", False),
                "calling_enabled": health_result.get("calling_enabled", False),
                "health_details": health_result
            }
            
            if results["health_check_success"]:
                logger.info("✅ Health check tests PASSED")
            else:
                logger.warning("⚠️ Health check tests show issues")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Health check test error: {e}")
            return {"error": str(e)}
    
    async def run_comprehensive_test(self) -> Dict[str, Any]:
        """Run all calling tests"""
        logger.info("🚀 Starting comprehensive WhatsApp calling tests...\n")
        
        # Initialize channel
        if not await self.initialize_channel():
            return {"error": "Failed to initialize channel"}
        
        # Run all tests
        tests = [
            ("eligibility", self.test_calling_eligibility),
            ("configuration", self.test_calling_configuration),
            ("call_button", self.test_call_button_functionality),
            ("direct_calling", self.test_direct_calling),
            ("health_check", self.test_health_check)
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                logger.info(f"\n--- Running {test_name} test ---")
                results[test_name] = await test_func()
            except Exception as e:
                logger.error(f"❌ Test {test_name} failed with error: {e}")
                results[test_name] = {"error": str(e)}
        
        # Generate summary
        results["summary"] = self.generate_test_summary(results)
        
        logger.info("\n" + "="*60)
        logger.info("📊 TEST SUMMARY")
        logger.info("="*60)
        
        for test_name, result in results["summary"].items():
            if test_name == "overall":
                continue
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            logger.info(f"{test_name:20} {status:10} {result['reason']}")
        
        overall_status = "✅ OVERALL PASS" if results["summary"]["overall"]["passed"] else "❌ OVERALL FAIL"
        logger.info(f"\n{overall_status}")
        logger.info(f"Tests passed: {results['summary']['overall']['passed_count']}/{results['summary']['overall']['total_count']}")
        
        return results
    
    def generate_test_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate test summary"""
        summary = {}
        passed_count = 0
        total_count = 0
        
        # Eligibility test
        eligibility = results.get("eligibility", {})
        eligible = eligibility.get("overall_eligible", False)
        summary["eligibility"] = {
            "passed": eligible,
            "reason": "Business meets calling requirements" if eligible else "Business doesn't meet calling requirements"
        }
        if not eligibility.get("error"):
            total_count += 1
            if eligible:
                passed_count += 1
        
        # Configuration test
        configuration = results.get("configuration", {})
        config_ok = configuration.get("configuration_complete", False)
        summary["configuration"] = {
            "passed": config_ok,
            "reason": "Settings configured successfully" if config_ok else "Settings configuration failed"
        }
        if not configuration.get("error"):
            total_count += 1
            if config_ok:
                passed_count += 1
        
        # Call button test
        call_button = results.get("call_button", {})
        button_ok = call_button.get("button_test_success", False)
        summary["call_button"] = {
            "passed": button_ok,
            "reason": "Call button works correctly" if button_ok else "Call button functionality failed"
        }
        if not call_button.get("error"):
            total_count += 1
            if button_ok:
                passed_count += 1
        
        # Direct calling test
        direct_calling = results.get("direct_calling", {})
        direct_ok = direct_calling.get("direct_call_supported", False)
        summary["direct_calling"] = {
            "passed": direct_ok,
            "reason": "Direct calling works" if direct_ok else "Direct calling not available (likely needs 1000+ messages)"
        }
        if not direct_calling.get("error"):
            total_count += 1
            if direct_ok:
                passed_count += 1
        
        # Health check test
        health = results.get("health_check", {})
        health_ok = health.get("health_check_success", False)
        summary["health_check"] = {
            "passed": health_ok,
            "reason": "System healthy" if health_ok else "System health issues detected"
        }
        if not health.get("error"):
            total_count += 1
            if health_ok:
                passed_count += 1
        
        # Overall summary
        summary["overall"] = {
            "passed": passed_count >= 3,  # Need at least 3/5 tests passing
            "passed_count": passed_count,
            "total_count": total_count,
            "success_rate": passed_count / max(total_count, 1) * 100
        }
        
        return summary

async def main():
    """Main test runner"""
    tester = WhatsAppCallingTester()
    
    try:
        results = await tester.run_comprehensive_test()
        
        # Save results to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"logs/whatsapp_calling_test_{timestamp}.json"
        
        os.makedirs("logs", exist_ok=True)
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"\n📁 Test results saved to: {results_file}")
        
        # Exit with appropriate code
        exit_code = 0 if results.get("summary", {}).get("overall", {}).get("passed", False) else 1
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"❌ Test runner failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())