"""
WhatsApp Business Token Health Monitoring System
Monitors token validity and provides alerts for expiration
"""

import os
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class TokenHealthMonitor:
    """Monitor WhatsApp Business token health and expiration"""
    
    def __init__(self):
        self.access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
        self.phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID')
        self.last_check = None
        self.token_status = "unknown"
        self.alert_thresholds = {
            "critical": timedelta(hours=1),    # Alert if expires in 1 hour
            "warning": timedelta(days=1),      # Alert if expires in 1 day
            "info": timedelta(days=7)          # Alert if expires in 7 days
        }
    
    async def check_token_health(self) -> Dict[str, Any]:
        """Check current token health status"""
        if not self.access_token or not self.phone_number_id:
            return {
                "healthy": False,
                "status": "missing_credentials",
                "message": "Missing WhatsApp Business token or phone ID"
            }
        
        try:
            # Test token with WhatsApp API
            url = f'https://graph.facebook.com/v18.0/{self.phone_number_id}'
            headers = {'Authorization': f'Bearer {self.access_token}'}
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    self.last_check = datetime.now()
                    
                    if response.status == 200:
                        data = await response.json()
                        self.token_status = "valid"
                        return {
                            "healthy": True,
                            "status": "valid",
                            "message": "Token is working correctly",
                            "account_info": data,
                            "last_check": self.last_check.isoformat()
                        }
                    elif response.status == 401:
                        error_data = await response.json()
                        self.token_status = "expired"
                        
                        # Parse expiration info if available
                        error_msg = error_data.get('error', {}).get('message', '')
                        
                        return {
                            "healthy": False,
                            "status": "expired",
                            "message": f"Token has expired: {error_msg}",
                            "error_details": error_data,
                            "action_required": "Generate new access token from Meta Business Suite",
                            "last_check": self.last_check.isoformat()
                        }
                    else:
                        error_text = await response.text()
                        self.token_status = "error"
                        return {
                            "healthy": False,
                            "status": "api_error",
                            "message": f"API error: {response.status}",
                            "error_details": error_text,
                            "last_check": self.last_check.isoformat()
                        }
                        
        except Exception as e:
            logger.error(f"Token health check failed: {e}")
            self.token_status = "check_failed"
            return {
                "healthy": False,
                "status": "check_failed",
                "message": f"Health check failed: {str(e)}",
                "last_check": datetime.now().isoformat()
            }
    
    async def get_token_info_from_facebook(self) -> Dict[str, Any]:
        """Get detailed token information from Facebook's token debugger API"""
        if not self.access_token:
            return {"error": "No access token available"}
        
        try:
            # Use Facebook's access token debugger API
            url = f'https://graph.facebook.com/debug_token'
            params = {
                'input_token': self.access_token,
                'access_token': self.access_token  # Can use same token for debugging
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        token_data = data.get('data', {})
                        
                        # Parse expiration info
                        expires_at = token_data.get('expires_at')
                        if expires_at:
                            expires_datetime = datetime.fromtimestamp(expires_at)
                            time_until_expiry = expires_datetime - datetime.now()
                            
                            return {
                                "valid": token_data.get('is_valid', False),
                                "expires_at": expires_datetime.isoformat(),
                                "time_until_expiry": str(time_until_expiry),
                                "expires_in_seconds": time_until_expiry.total_seconds(),
                                "scopes": token_data.get('scopes', []),
                                "app_id": token_data.get('app_id'),
                                "user_id": token_data.get('user_id'),
                                "urgency_level": self._get_urgency_level(time_until_expiry)
                            }
                        else:
                            return {
                                "valid": token_data.get('is_valid', False),
                                "expires_at": None,
                                "message": "Token may be permanent or expiration not available",
                                "scopes": token_data.get('scopes', []),
                                "app_id": token_data.get('app_id'),
                                "user_id": token_data.get('user_id')
                            }
                    else:
                        error_text = await response.text()
                        return {"error": f"Token info request failed: {error_text}"}
                        
        except Exception as e:
            logger.error(f"Failed to get token info: {e}")
            return {"error": f"Exception getting token info: {str(e)}"}
    
    def _get_urgency_level(self, time_until_expiry: timedelta) -> str:
        """Determine urgency level based on time until expiration"""
        if time_until_expiry <= self.alert_thresholds["critical"]:
            return "critical"
        elif time_until_expiry <= self.alert_thresholds["warning"]:
            return "warning"
        elif time_until_expiry <= self.alert_thresholds["info"]:
            return "info"
        else:
            return "good"
    
    async def monitor_loop(self, check_interval_minutes: int = 60):
        """Continuous monitoring loop with alerts"""
        logger.info(f"Starting token health monitoring (check every {check_interval_minutes} minutes)")
        
        while True:
            try:
                health_status = await self.check_token_health()
                
                if not health_status["healthy"]:
                    logger.error(f"Token health issue: {health_status['message']}")
                    await self._send_alert(health_status)
                    
                    # Get detailed token info for expired tokens
                    if health_status["status"] == "expired":
                        token_info = await self.get_token_info_from_facebook()
                        logger.error(f"Token details: {token_info}")
                else:
                    logger.info("Token health check passed")
                    # Check for upcoming expiration warnings
                    token_info = await self.get_token_info_from_facebook()
                    if token_info.get("urgency_level") in ["critical", "warning", "info"]:
                        await self._send_expiration_warning(token_info)
                
                # Wait for next check
                await asyncio.sleep(check_interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def health_check_endpoint(self) -> Dict[str, Any]:
        """Health check endpoint for web services"""
        basic_health = await self.check_token_health()
        
        if basic_health["healthy"]:
            # Get additional token info if healthy
            token_info = await self.get_token_info_from_facebook()
            basic_health.update({"token_details": token_info})
        
        return basic_health
    
    async def _send_alert(self, health_status: Dict[str, Any]):
        """Send alert for token health issues"""
        alert_level = "CRITICAL" if health_status["status"] == "expired" else "WARNING"
        message = f"[{alert_level}] WhatsApp Token Issue: {health_status['message']}"
        
        # Log alert
        logger.error(f"ALERT: {message}")
        
        # In production, send to monitoring service
        # await self._send_to_monitoring_service(alert_level, message)
        
        # For now, write to a local alert file
        try:
            alert_data = {
                "timestamp": datetime.now().isoformat(),
                "level": alert_level,
                "status": health_status["status"],
                "message": health_status["message"],
                "action_required": health_status.get("action_required", "Check token configuration")
            }
            
            # Append to alert log
            import json
            with open("logs/token_alerts.log", "a") as f:
                f.write(json.dumps(alert_data) + "\n")
                
        except Exception as e:
            logger.error(f"Failed to write alert log: {e}")
    
    async def _send_expiration_warning(self, token_info: Dict[str, Any]):
        """Send warning for upcoming token expiration"""
        urgency = token_info.get("urgency_level", "unknown")
        expires_at = token_info.get("expires_at", "unknown")
        time_left = token_info.get("time_until_expiry", "unknown")
        
        message = f"WhatsApp token expires in {time_left} (at {expires_at})"
        
        if urgency == "critical":
            logger.error(f"CRITICAL EXPIRATION WARNING: {message}")
        elif urgency == "warning":
            logger.warning(f"EXPIRATION WARNING: {message}")
        elif urgency == "info":
            logger.info(f"EXPIRATION NOTICE: {message}")
        
        # Write to alert log for tracking
        try:
            alert_data = {
                "timestamp": datetime.now().isoformat(),
                "level": f"EXPIRATION_{urgency.upper()}",
                "expires_at": expires_at,
                "time_until_expiry": time_left,
                "message": message,
                "action_required": "Plan token renewal" if urgency in ["critical", "warning"] else "Monitor expiration"
            }
            
            import json
            with open("logs/token_alerts.log", "a") as f:
                f.write(json.dumps(alert_data) + "\n")
                
        except Exception as e:
            logger.error(f"Failed to write expiration warning: {e}")

# Global monitor instance
token_monitor = TokenHealthMonitor()

# Convenience functions
async def check_token_health() -> Dict[str, Any]:
    """Quick token health check"""
    return await token_monitor.check_token_health()

async def get_detailed_token_info() -> Dict[str, Any]:
    """Get detailed token information"""
    return await token_monitor.get_token_info_from_facebook()

def start_monitoring(check_interval_minutes: int = 60):
    """Start background token monitoring"""
    return asyncio.create_task(token_monitor.monitor_loop(check_interval_minutes))

if __name__ == "__main__":
    # Test the monitor
    asyncio.run(token_monitor.health_check_endpoint())