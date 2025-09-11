#!/usr/bin/env python3
"""
WhatsApp Calling Configuration Script

This script helps configure and enable WhatsApp calling according to Meta's requirements.
It checks current status, validates requirements, and attempts to enable calling.

Usage:
    python scripts/enable_whatsapp_calling.py [--dry-run] [--force]
    
Options:
    --dry-run    Show what would be done without making changes
    --force      Attempt to enable calling even if requirements not met
"""

import asyncio
import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.communication.whatsapp_cloud_api import WhatsAppCloudAPIChannel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WhatsAppCallingConfigurator:
    """WhatsApp calling configuration and enablement"""
    
    def __init__(self, dry_run: bool = False, force: bool = False):
        self.dry_run = dry_run
        self.force = force
        self.customer_id = "calling_config"
        self.channel = None
        
    async def initialize(self) -> bool:
        """Initialize WhatsApp channel"""
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
                config={'calling_enabled': True}
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
    
    async def check_current_status(self) -> Dict[str, Any]:
        """Check current calling status"""
        logger.info("\n📋 Checking current calling status...")
        
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
                        
                        status = {
                            "calling_configured": bool(calling_settings),
                            "calling_status": calling_settings.get('status', 'NOT_CONFIGURED'),
                            "call_icon_visibility": calling_settings.get('call_icon_visibility', 'NOT_SET'),
                            "callback_permission_status": calling_settings.get('callback_permission_status', 'NOT_SET'),
                            "call_hours": calling_settings.get('call_hours', {}),
                            "restrictions": calling_settings.get('restrictions', {}),
                            "raw_settings": calling_settings
                        }
                        
                        # Check for restrictions
                        restrictions = status["restrictions"].get("restrictions_list", [])
                        if restrictions:
                            status["has_restrictions"] = True
                            status["restriction_details"] = restrictions[0]
                        else:
                            status["has_restrictions"] = False
                        
                        # Overall assessment
                        status["calling_enabled"] = (
                            status["calling_status"] == "ENABLED" and
                            not status["has_restrictions"]
                        )
                        
                        self.log_status_details(status)
                        return status
                        
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to get settings: HTTP {response.status} - {error_text}")
                        return {"error": f"HTTP {response.status}: {error_text}"}
                        
        except Exception as e:
            logger.error(f"❌ Status check error: {e}")
            return {"error": str(e)}
    
    def log_status_details(self, status: Dict[str, Any]):
        """Log detailed status information"""
        logger.info("📊 Current Calling Status:")
        logger.info(f"  Calling Configured: {'✅' if status['calling_configured'] else '❌'}")
        logger.info(f"  Calling Status: {status['calling_status']}")
        logger.info(f"  Call Icon Visibility: {status['call_icon_visibility']}")
        logger.info(f"  Callback Permissions: {status['callback_permission_status']}")
        
        if status["has_restrictions"]:
            restriction = status["restriction_details"]
            logger.warning(f"  ⚠️ RESTRICTION: {restriction.get('type', 'Unknown')}")
            logger.warning(f"     Reason: {restriction.get('reason', 'Not specified')}")
            if restriction.get('expiration'):
                exp_date = datetime.fromtimestamp(restriction['expiration'])
                logger.warning(f"     Expires: {exp_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        call_hours = status.get("call_hours", {})
        if call_hours:
            logger.info(f"  Call Hours Status: {call_hours.get('status', 'NOT_SET')}")
            if call_hours.get('timezone_id'):
                logger.info(f"  Timezone: {call_hours['timezone_id']}")
        
        overall_status = "✅ ENABLED" if status["calling_enabled"] else "❌ DISABLED"
        logger.info(f"  Overall Status: {overall_status}")
    
    async def check_prerequisites(self) -> Dict[str, Any]:
        """Check calling prerequisites"""
        logger.info("\n🔍 Checking calling prerequisites...")
        
        try:
            # Check business eligibility
            business_check = await self.channel._check_calling_eligibility()
            logger.info(f"Business eligibility: {business_check['reason']}")
            
            # Check messaging volume
            volume_check = await self.channel._check_messaging_volume()
            logger.info(f"Volume check: {volume_check}")
            
            # Get account info
            account_info = await self.get_account_info()
            
            prerequisites = {
                "business_eligible": business_check.get("eligible", False),
                "business_reason": business_check.get("reason", "Unknown"),
                "volume_sufficient": volume_check.get("sufficient", False),
                "volume_details": volume_check,
                "account_info": account_info,
                "ready_for_calling": (
                    business_check.get("eligible", False) and
                    volume_check.get("sufficient", False)
                )
            }
            
            self.log_prerequisites(prerequisites)
            return prerequisites
            
        except Exception as e:
            logger.error(f"❌ Prerequisites check error: {e}")
            return {"error": str(e)}
    
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        try:
            url = f"{self.channel.base_url}/{self.channel.phone_number_id}"
            headers = {
                'Authorization': f'Bearer {self.channel.access_token}',
                'Content-Type': 'application/json'
            }
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {"error": f"HTTP {response.status}"}
                        
        except Exception as e:
            return {"error": str(e)}
    
    def log_prerequisites(self, prerequisites: Dict[str, Any]):
        """Log prerequisite details"""
        logger.info("📋 Prerequisites Check:")
        
        business_status = "✅" if prerequisites["business_eligible"] else "❌"
        logger.info(f"  Business Eligible: {business_status} {prerequisites['business_reason']}")
        
        volume_status = "✅" if prerequisites["volume_sufficient"] else "❌"
        volume_details = prerequisites["volume_details"]
        logger.info(f"  Volume Sufficient: {volume_status} {volume_details.get('current', 'Unknown')}")
        
        if not prerequisites["volume_sufficient"]:
            logger.warning(f"    Recommendation: {volume_details.get('recommendation', 'Increase messaging volume')}")
        
        account_info = prerequisites["account_info"]
        if not account_info.get("error"):
            logger.info(f"  Account Name: {account_info.get('verified_name', 'Unknown')}")
            logger.info(f"  Quality Rating: {account_info.get('quality_rating', 'Unknown')}")
        
        overall_status = "✅ READY" if prerequisites["ready_for_calling"] else "❌ NOT READY"
        logger.info(f"  Overall: {overall_status}")
    
    async def enable_calling(self) -> Dict[str, Any]:
        """Enable calling with proper configuration"""
        logger.info("\n🚀 Enabling WhatsApp calling...")
        
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No changes will be made")
            return await self.simulate_enable_calling()
        
        try:
            # Check prerequisites first
            prerequisites = await self.check_prerequisites()
            
            if not prerequisites.get("ready_for_calling") and not self.force:
                logger.error("❌ Prerequisites not met. Use --force to attempt anyway.")
                return {
                    "success": False,
                    "reason": "Prerequisites not met",
                    "prerequisites": prerequisites
                }
            
            if not prerequisites.get("ready_for_calling") and self.force:
                logger.warning("⚠️ Force mode enabled - attempting despite unmet prerequisites")
            
            # Configure calling settings
            url = f"{self.channel.base_url}/{self.channel.phone_number_id}/settings"
            headers = {
                'Authorization': f'Bearer {self.channel.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Official Meta calling configuration
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
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=settings_data) as response:
                    if response.status == 200:
                        logger.info("✅ Calling enabled successfully!")
                        
                        # Verify the configuration
                        verification = await self.check_current_status()
                        
                        return {
                            "success": True,
                            "message": "Calling enabled successfully",
                            "configuration": settings_data,
                            "verification": verification
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Failed to enable calling: HTTP {response.status} - {error_text}")
                        
                        # Parse specific errors
                        error_info = self.parse_calling_error(error_text)
                        
                        return {
                            "success": False,
                            "error": error_text,
                            "http_status": response.status,
                            "error_info": error_info
                        }
                        
        except Exception as e:
            logger.error(f"❌ Enable calling error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def simulate_enable_calling(self) -> Dict[str, Any]:
        """Simulate enabling calling (dry run)"""
        logger.info("🎭 Simulating calling enablement...")
        
        prerequisites = await self.check_prerequisites()
        
        if prerequisites.get("ready_for_calling"):
            logger.info("✅ Would enable calling successfully")
            return {
                "success": True,
                "simulated": True,
                "message": "Would enable calling (dry run)",
                "prerequisites": prerequisites
            }
        else:
            logger.warning("⚠️ Would fail due to unmet prerequisites")
            return {
                "success": False,
                "simulated": True,
                "message": "Would fail to enable calling (dry run)",
                "prerequisites": prerequisites
            }
    
    def parse_calling_error(self, error_text: str) -> Dict[str, Any]:
        """Parse calling configuration errors"""
        error_info = {"parsed": True}
        
        if "messaging limit" in error_text.lower():
            error_info.update({
                "type": "messaging_volume_insufficient",
                "description": "Business needs 1,000+ messages in 24 hours to enable calling",
                "solution": "Increase business-initiated messaging volume"
            })
        elif "permission" in error_text.lower():
            error_info.update({
                "type": "permission_error",
                "description": "Insufficient permissions to configure calling",
                "solution": "Check WhatsApp Business Management permissions"
            })
        elif "quality" in error_text.lower():
            error_info.update({
                "type": "quality_restriction",
                "description": "Account quality rating too low for calling",
                "solution": "Improve messaging quality and user engagement"
            })
        else:
            error_info.update({
                "type": "unknown_error",
                "description": "Unrecognized error type",
                "solution": "Check Meta's WhatsApp Business API documentation"
            })
        
        return error_info
    
    async def run_configuration(self) -> Dict[str, Any]:
        """Run complete configuration process"""
        logger.info("🚀 Starting WhatsApp calling configuration...\n")
        
        # Initialize
        if not await self.initialize():
            return {"error": "Failed to initialize"}
        
        results = {}
        
        # Check current status
        results["current_status"] = await self.check_current_status()
        
        # Check prerequisites
        results["prerequisites"] = await self.check_prerequisites()
        
        # Enable calling
        results["enable_result"] = await self.enable_calling()
        
        # Final status check
        if results["enable_result"].get("success"):
            results["final_status"] = await self.check_current_status()
        
        # Generate summary
        results["summary"] = self.generate_summary(results)
        
        self.log_final_summary(results["summary"])
        
        return results
    
    def generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate configuration summary"""
        current_status = results.get("current_status", {})
        prerequisites = results.get("prerequisites", {})
        enable_result = results.get("enable_result", {})
        final_status = results.get("final_status", {})
        
        summary = {
            "initial_calling_enabled": current_status.get("calling_enabled", False),
            "prerequisites_met": prerequisites.get("ready_for_calling", False),
            "configuration_attempted": not self.dry_run,
            "configuration_successful": enable_result.get("success", False),
            "final_calling_enabled": final_status.get("calling_enabled", current_status.get("calling_enabled", False)),
            "dry_run": self.dry_run,
            "force_used": self.force
        }
        
        # Overall success
        if self.dry_run:
            summary["overall_success"] = enable_result.get("success", False)
            summary["message"] = "Dry run completed"
        else:
            summary["overall_success"] = summary["final_calling_enabled"]
            summary["message"] = "Calling enabled" if summary["overall_success"] else "Calling not enabled"
        
        return summary
    
    def log_final_summary(self, summary: Dict[str, Any]):
        """Log final configuration summary"""
        logger.info("\n" + "="*60)
        logger.info("📊 CONFIGURATION SUMMARY")
        logger.info("="*60)
        
        mode = "DRY RUN" if summary["dry_run"] else "LIVE"
        logger.info(f"Mode: {mode}")
        
        if summary["force_used"]:
            logger.info("Force mode: ENABLED")
        
        logger.info(f"Initial Status: {'✅ Enabled' if summary['initial_calling_enabled'] else '❌ Disabled'}")
        logger.info(f"Prerequisites: {'✅ Met' if summary['prerequisites_met'] else '❌ Not Met'}")
        
        if summary["configuration_attempted"]:
            config_status = "✅ Success" if summary["configuration_successful"] else "❌ Failed"
            logger.info(f"Configuration: {config_status}")
        else:
            logger.info("Configuration: 🔍 Simulated only")
        
        logger.info(f"Final Status: {'✅ Enabled' if summary['final_calling_enabled'] else '❌ Disabled'}")
        
        overall_status = "✅ SUCCESS" if summary["overall_success"] else "❌ FAILED"
        logger.info(f"\n{overall_status}: {summary['message']}")

async def main():
    """Main configuration runner"""
    parser = argparse.ArgumentParser(description="Configure WhatsApp calling")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--force", action="store_true", help="Attempt to enable calling even if requirements not met")
    
    args = parser.parse_args()
    
    configurator = WhatsAppCallingConfigurator(dry_run=args.dry_run, force=args.force)
    
    try:
        results = await configurator.run_configuration()
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "dryrun" if args.dry_run else "live"
        results_file = f"logs/whatsapp_calling_config_{mode}_{timestamp}.json"
        
        os.makedirs("logs", exist_ok=True)
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"\n📁 Configuration results saved to: {results_file}")
        
        # Exit with appropriate code
        exit_code = 0 if results.get("summary", {}).get("overall_success", False) else 1
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"❌ Configuration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())