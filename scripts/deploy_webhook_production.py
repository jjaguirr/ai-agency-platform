#!/usr/bin/env python3
"""
Deploy Personal EA Webhook to DigitalOcean App Platform
Automates the deployment process and webhook URL configuration
"""

import os
import sys
import json
import subprocess
import requests
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class WebhookDeployment:
    """Manages DigitalOcean webhook deployment"""
    
    def __init__(self):
        self.app_name = "ai-agency-platform-webhook"
        self.domain = "webhook.aiagency.platform"
        self.github_repo = "jjaguirr/ai-agency-platform"
        self.branch = "phase-2-development"
        
    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met"""
        print("🔍 Checking deployment prerequisites...")
        
        # Check DigitalOcean CLI
        try:
            result = subprocess.run(['doctl', 'version'], capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ DigitalOcean CLI (doctl) not installed")
                print("   Install with: brew install doctl")
                return False
            print("✅ DigitalOcean CLI available")
        except FileNotFoundError:
            print("❌ DigitalOcean CLI (doctl) not found")
            return False
        
        # Check authentication
        try:
            result = subprocess.run(['doctl', 'auth', 'list'], capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ Not authenticated with DigitalOcean")
                print("   Run: doctl auth init")
                return False
            print("✅ DigitalOcean authentication configured")
        except:
            print("❌ DigitalOcean authentication check failed")
            return False
            
        # Check environment variables
        required_env = [
            'WHATSAPP_BUSINESS_TOKEN',
            'WHATSAPP_BUSINESS_PHONE_ID',
            'ELEVENLABS_API_KEY'
        ]
        
        missing_env = [env for env in required_env if not os.getenv(env)]
        if missing_env:
            print(f"❌ Missing environment variables: {', '.join(missing_env)}")
            return False
        print("✅ Required environment variables configured")
        
        return True
    
    def deploy_app(self) -> Dict[str, Any]:
        """Deploy the app to DigitalOcean App Platform"""
        print("🚀 Deploying webhook service to DigitalOcean...")
        
        try:
            # Deploy using the app.yaml spec
            cmd = [
                'doctl', 'apps', 'create',
                '--spec', '.do/app.yaml',
                '--format', 'json'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(__file__)))
            
            if result.returncode != 0:
                print(f"❌ Deployment failed: {result.stderr}")
                # Try to get more details
                print("Full error output:")
                print(result.stdout)
                return {"success": False, "error": result.stderr}
            
            deployment_info = json.loads(result.stdout)
            app_id = deployment_info.get('id')
            
            print(f"✅ Deployment initiated. App ID: {app_id}")
            print("🔄 Monitoring deployment status...")
            
            # Monitor deployment
            return self.monitor_deployment(app_id)
            
        except Exception as e:
            print(f"❌ Deployment error: {e}")
            return {"success": False, "error": str(e)}
    
    def monitor_deployment(self, app_id: str) -> Dict[str, Any]:
        """Monitor deployment progress"""
        import time
        
        max_attempts = 30
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Get app status
                cmd = ['doctl', 'apps', 'get', app_id, '--format', 'json']
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    app_info = json.loads(result.stdout)
                    phase = app_info.get('phase', 'unknown')
                    
                    print(f"📊 Deployment status: {phase} (attempt {attempt + 1}/{max_attempts})")
                    
                    if phase == 'ACTIVE':
                        # Get the live URL
                        live_url = app_info.get('live_url', f"https://{self.domain}")
                        print(f"✅ Deployment successful! Live URL: {live_url}")
                        
                        # Test the health endpoint
                        health_result = self.test_deployment(live_url)
                        
                        return {
                            "success": True,
                            "app_id": app_id,
                            "live_url": live_url,
                            "health_check": health_result
                        }
                    
                    elif phase in ['ERROR', 'SUPERSEDED']:
                        print(f"❌ Deployment failed with phase: {phase}")
                        return {"success": False, "error": f"Deployment phase: {phase}"}
                
                time.sleep(10)
                attempt += 1
                
            except Exception as e:
                print(f"⚠️ Error checking deployment status: {e}")
                time.sleep(10)
                attempt += 1
        
        print("❌ Deployment monitoring timed out")
        return {"success": False, "error": "Deployment monitoring timeout"}
    
    def test_deployment(self, live_url: str) -> Dict[str, Any]:
        """Test the deployed webhook service"""
        print("🧪 Testing deployed webhook service...")
        
        try:
            # Test health endpoint
            health_url = f"{live_url}/health"
            response = requests.get(health_url, timeout=30)
            
            if response.status_code == 200:
                health_data = response.json()
                print("✅ Health check passed")
                print(f"   Status: {health_data.get('status', 'unknown')}")
                print(f"   Environment: {health_data.get('environment', 'unknown')}")
                
                return {
                    "health_check": "passed",
                    "status": health_data.get('status'),
                    "details": health_data
                }
            else:
                print(f"❌ Health check failed: HTTP {response.status_code}")
                return {
                    "health_check": "failed",
                    "status_code": response.status_code,
                    "error": response.text
                }
                
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return {
                "health_check": "error",
                "error": str(e)
            }
    
    def configure_whatsapp_webhook(self, webhook_url: str) -> bool:
        """Configure WhatsApp Business API webhook URL"""
        print(f"🔧 Configuring WhatsApp webhook URL: {webhook_url}")
        
        try:
            # WhatsApp Business API configuration
            phone_number_id = os.getenv('WHATSAPP_BUSINESS_PHONE_ID')
            access_token = os.getenv('WHATSAPP_BUSINESS_TOKEN')
            verify_token = os.getenv('WHATSAPP_VERIFY_TOKEN', 'ai_agency_platform_verify')
            
            if not phone_number_id or not access_token:
                print("❌ Missing WhatsApp Business API credentials")
                return False
            
            # Update webhook configuration
            api_url = f'https://graph.facebook.com/v18.0/{phone_number_id}'
            
            webhook_config = {
                'messaging_product': 'whatsapp',
                'webhooks': {
                    'url': f"{webhook_url}/webhook/whatsapp",
                    'verify_token': verify_token,
                    'fields': ['messages', 'message_deliveries', 'message_reads', 'message_reactions']
                }
            }
            
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(api_url, json=webhook_config, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print("✅ WhatsApp webhook configured successfully")
                return True
            else:
                print(f"❌ WhatsApp webhook configuration failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ WhatsApp webhook configuration error: {e}")
            return False
    
    def generate_deployment_report(self, deployment_result: Dict[str, Any]) -> None:
        """Generate deployment report"""
        print("\\n" + "="*60)
        print("📋 WEBHOOK DEPLOYMENT REPORT")
        print("="*60)
        
        if deployment_result.get('success'):
            print("✅ DEPLOYMENT SUCCESSFUL")
            print(f"🔗 Live URL: {deployment_result.get('live_url')}")
            print(f"🆔 App ID: {deployment_result.get('app_id')}")
            
            health_result = deployment_result.get('health_check', {})
            print(f"🏥 Health Check: {health_result.get('health_check', 'unknown')}")
            
            if health_result.get('health_check') == 'passed':
                print("\\n📱 WhatsApp Integration Status:")
                print(f"   Webhook URL: {deployment_result.get('live_url')}/webhook/whatsapp")
                print(f"   Health Endpoint: {deployment_result.get('live_url')}/health")
                print(f"   Test Endpoint: {deployment_result.get('live_url')}/test")
                
                print("\\n🔄 Next Steps:")
                print("1. Update WhatsApp Business API webhook URL in Meta Developer Console")
                print("2. Test message flow with your WhatsApp Business number")
                print("3. Monitor logs in DigitalOcean dashboard")
                print("4. Set up alerts and monitoring")
            
        else:
            print("❌ DEPLOYMENT FAILED")
            print(f"Error: {deployment_result.get('error', 'Unknown error')}")
            
        print("="*60)

def main():
    """Main deployment function"""
    print("🚀 AI Agency Platform - Webhook Production Deployment")
    print("="*60)
    
    deployment = WebhookDeployment()
    
    # Check prerequisites
    if not deployment.check_prerequisites():
        print("❌ Prerequisites not met. Please resolve and try again.")
        return 1
    
    # Deploy the application
    deployment_result = deployment.deploy_app()
    
    # Generate report
    deployment.generate_deployment_report(deployment_result)
    
    if deployment_result.get('success'):
        # Optionally configure WhatsApp webhook
        live_url = deployment_result.get('live_url')
        if live_url:
            configure_webhook = input("\\n🔧 Configure WhatsApp webhook URL automatically? (y/n): ").lower().strip()
            if configure_webhook in ['y', 'yes']:
                deployment.configure_whatsapp_webhook(live_url)
        
        print("\\n✅ Deployment completed successfully!")
        return 0
    else:
        print("\\n❌ Deployment failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())