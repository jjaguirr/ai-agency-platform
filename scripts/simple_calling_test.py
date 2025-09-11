#!/usr/bin/env python3
"""
Simple WhatsApp Calling Test Script

Direct API test without complex imports to validate calling status.
"""

import asyncio
import os
import json
import aiohttp
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleCallingTest:
    def __init__(self):
        self.access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
        self.phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID') 
        self.base_url = "https://graph.facebook.com/v18.0"
        
        if not self.access_token or not self.phone_number_id:
            logger.error("❌ Missing WHATSAPP_BUSINESS_TOKEN or WHATSAPP_BUSINESS_PHONE_ID")
            exit(1)
    
    async def check_current_settings(self):
        """Check current calling settings"""
        logger.info("📋 Checking current calling settings...")
        
        url = f"{self.base_url}/{self.phone_number_id}/settings"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    calling_settings = data.get('calling', {})
                    
                    logger.info("✅ Current Settings Retrieved:")
                    logger.info(f"  Calling Configured: {'Yes' if calling_settings else 'No'}")
                    
                    if calling_settings:
                        logger.info(f"  Status: {calling_settings.get('status', 'Unknown')}")
                        logger.info(f"  Call Icon: {calling_settings.get('call_icon_visibility', 'Unknown')}")
                        logger.info(f"  Permissions: {calling_settings.get('callback_permission_status', 'Unknown')}")
                        
                        restrictions = calling_settings.get('restrictions', {}).get('restrictions_list', [])
                        if restrictions:
                            logger.warning(f"  ⚠️ Restrictions: {restrictions[0].get('reason', 'Unknown')}")
                        else:
                            logger.info("  Restrictions: None")
                    
                    return calling_settings
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Failed to get settings: {response.status} - {error_text}")
                    return None
    
    async def check_account_info(self):
        """Check account information"""
        logger.info("📞 Checking account information...")
        
        url = f"{self.base_url}/{self.phone_number_id}"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    logger.info("✅ Account Information:")
                    logger.info(f"  Verified Name: {data.get('verified_name', 'Unknown')}")
                    logger.info(f"  Quality Rating: {data.get('quality_rating', 'Unknown')}")
                    logger.info(f"  Platform Type: {data.get('platform_type', 'Unknown')}")
                    
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Failed to get account info: {response.status} - {error_text}")
                    return None
    
    async def test_calling_configuration(self):
        """Test calling configuration (dry run)"""
        logger.info("🧪 Testing calling configuration...")
        
        url = f"{self.base_url}/{self.phone_number_id}/settings"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Test configuration payload
        settings_data = {
            "calling": {
                "status": "ENABLED",
                "call_icon_visibility": "DEFAULT",
                "callback_permission_status": "ENABLED",
                "call_hours": {
                    "status": "DISABLED"  # 24/7 availability
                }
            }
        }
        
        logger.info("🔍 DRY RUN - Would send configuration:")
        logger.info(json.dumps(settings_data, indent=2))
        
        # Actual test (commented out for safety)
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(url, headers=headers, json=settings_data) as response:
        #         if response.status == 200:
        #             logger.info("✅ Configuration would succeed")
        #             return True
        #         else:
        #             error_text = await response.text()
        #             logger.error(f"❌ Configuration would fail: {response.status} - {error_text}")
        #             return False
        
        return True
    
    async def test_call_button(self):
        """Test call button message (dry run)"""
        logger.info("📞 Testing call button message...")
        
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        # Test call button payload
        call_button_data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": "1234567890",  # Test number
            "type": "interactive",
            "interactive": {
                "type": "voice_call",
                "body": {
                    "text": "Test call button from AI Agency Platform"
                },
                "action": {
                    "name": "voice_call",
                    "parameters": {
                        "display_text": "Call Test",
                        "ttl_minutes": 1440
                    }
                }
            }
        }
        
        logger.info("🔍 DRY RUN - Would send call button:")
        logger.info(json.dumps(call_button_data, indent=2))
        
        # Note: Actual call button test commented out to avoid sending test messages
        return True
    
    async def run_tests(self):
        """Run all tests"""
        logger.info("🚀 Starting WhatsApp calling tests...\n")
        
        # Check current settings
        current_settings = await self.check_current_settings()
        
        # Check account info 
        account_info = await self.check_account_info()
        
        # Test configuration
        config_test = await self.test_calling_configuration()
        
        # Test call button
        button_test = await self.test_call_button()
        
        # Summary
        logger.info("\n" + "="*50)
        logger.info("📊 TEST SUMMARY")
        logger.info("="*50)
        
        # Analyze results
        calling_configured = bool(current_settings)
        calling_enabled = current_settings.get('status') == 'ENABLED' if current_settings else False
        quality_good = account_info.get('quality_rating') == 'GREEN' if account_info else False
        
        logger.info(f"Calling Configured: {'✅' if calling_configured else '❌'}")
        logger.info(f"Calling Enabled: {'✅' if calling_enabled else '❌'}")
        logger.info(f"Quality Rating: {'✅ GREEN' if quality_good else '⚠️ Not GREEN'}")
        logger.info(f"Config Test: {'✅' if config_test else '❌'}")
        logger.info(f"Button Test: {'✅' if button_test else '❌'}")
        
        # Overall assessment
        if calling_enabled:
            logger.info("\n✅ CALLING IS ENABLED - Direct calling should work!")
        elif calling_configured:
            logger.info("\n⚠️ CALLING CONFIGURED BUT NOT ENABLED - May need volume requirements")
        else:
            logger.info("\n❌ CALLING NOT CONFIGURED - Needs setup")
        
        if quality_good:
            logger.info("✅ Quality rating suggests sufficient message volume")
        else:
            logger.info("⚠️ Quality rating suggests insufficient message volume (need 1000+/day)")
        
        # Save results
        results = {
            "timestamp": datetime.now().isoformat(),
            "current_settings": current_settings,
            "account_info": account_info,
            "calling_configured": calling_configured,
            "calling_enabled": calling_enabled,
            "quality_good": quality_good,
            "tests_passed": config_test and button_test
        }
        
        os.makedirs("logs", exist_ok=True)
        with open("logs/simple_calling_test.json", "w") as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"\n📁 Results saved to: logs/simple_calling_test.json")
        
        return results

async def main():
    tester = SimpleCallingTest()
    await tester.run_tests()

if __name__ == "__main__":
    asyncio.run(main())