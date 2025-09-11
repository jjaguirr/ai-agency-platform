#!/usr/bin/env python3
"""
Multi-Environment Webhook Management System
Manages development, staging, and production webhook deployments
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

class WebhookEnvironmentManager:
    """Manages webhook deployments across multiple environments"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.environments = {
            'development': {
                'config': '.do/environments/development.yaml',
                'domain': 'webhook-dev.aiagency.platform',
                'branch': 'phase-2-development',
                'description': 'Development environment for testing new features'
            },
            'staging': {
                'config': '.do/environments/staging.yaml',
                'domain': 'webhook-staging.aiagency.platform',
                'branch': 'main',
                'description': 'Staging environment for pre-production testing'
            },
            'production': {
                'config': '.do/environments/production.yaml',
                'domain': 'webhook.aiagency.platform',
                'branch': 'main',
                'description': 'Production environment for live customer traffic'
            }
        }
    
    def list_environments(self) -> None:
        """List all available environments"""
        print("🌍 Available Webhook Environments:")
        print("=" * 60)
        
        for env_name, config in self.environments.items():
            print(f"📍 {env_name.upper()}")
            print(f"   Domain: {config['domain']}")
            print(f"   Branch: {config['branch']}")
            print(f"   Config: {config['config']}")
            print(f"   Description: {config['description']}")
            print()
    
    def validate_environment(self, environment: str) -> bool:
        """Validate environment exists and configuration is ready"""
        if environment not in self.environments:
            print(f"❌ Environment '{environment}' not found")
            print(f"Available environments: {', '.join(self.environments.keys())}")
            return False
        
        config_path = self.project_root / self.environments[environment]['config']
        if not config_path.exists():
            print(f"❌ Configuration file not found: {config_path}")
            return False
        
        print(f"✅ Environment '{environment}' configuration validated")
        return True
    
    def check_prerequisites(self) -> bool:
        """Check deployment prerequisites"""
        print("🔍 Checking deployment prerequisites...")
        
        # Check DigitalOcean CLI
        try:
            result = subprocess.run(['doctl', 'version'], capture_output=True, text=True)
            if result.returncode != 0:
                print("❌ DigitalOcean CLI (doctl) not installed or not working")
                return False
            print("✅ DigitalOcean CLI available")
        except FileNotFoundError:
            print("❌ DigitalOcean CLI (doctl) not found. Install with: brew install doctl")
            return False
        
        # Check authentication
        try:
            result = subprocess.run(['doctl', 'auth', 'list'], capture_output=True, text=True)
            if result.returncode != 0 or not result.stdout.strip():
                print("❌ Not authenticated with DigitalOcean")
                print("   Run: doctl auth init")
                return False
            print("✅ DigitalOcean authentication configured")
        except Exception as e:
            print(f"❌ DigitalOcean authentication check failed: {e}")
            return False
        
        return True
    
    def deploy_environment(self, environment: str, update: bool = False) -> Dict[str, Any]:
        """Deploy or update a specific environment"""
        if not self.validate_environment(environment):
            return {"success": False, "error": "Invalid environment"}
        
        if not self.check_prerequisites():
            return {"success": False, "error": "Prerequisites not met"}
        
        config_path = self.project_root / self.environments[environment]['config']
        action = "update" if update else "create"
        
        print(f"🚀 {'Updating' if update else 'Deploying'} {environment} environment...")
        print(f"📁 Using config: {config_path}")
        
        try:
            if update:
                # Update existing app
                cmd = ['doctl', 'apps', 'update', '--spec', str(config_path)]
                # Note: We'd need the app ID for updates, this is simplified
            else:
                # Create new app
                cmd = ['doctl', 'apps', 'create', '--spec', str(config_path), '--format', 'json']
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            
            if result.returncode != 0:
                print(f"❌ Deployment failed: {result.stderr}")
                return {"success": False, "error": result.stderr}
            
            # Parse deployment result
            if not update:
                deployment_info = json.loads(result.stdout)
                app_id = deployment_info.get('id')
                
                print(f"✅ Deployment initiated for {environment}")
                print(f"🆔 App ID: {app_id}")
                
                # Monitor deployment
                return self.monitor_deployment(app_id, environment)
            else:
                print(f"✅ Update initiated for {environment}")
                return {"success": True, "action": "update", "environment": environment}
                
        except Exception as e:
            print(f"❌ Deployment error: {e}")
            return {"success": False, "error": str(e)}
    
    def monitor_deployment(self, app_id: str, environment: str) -> Dict[str, Any]:
        """Monitor deployment progress"""
        import time
        
        max_attempts = 20
        attempt = 0
        
        print(f"🔄 Monitoring {environment} deployment...")
        
        while attempt < max_attempts:
            try:
                cmd = ['doctl', 'apps', 'get', app_id, '--format', 'json']
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    app_info = json.loads(result.stdout)
                    phase = app_info.get('phase', 'unknown')
                    
                    print(f"📊 {environment.title()} status: {phase} (attempt {attempt + 1}/{max_attempts})")
                    
                    if phase == 'ACTIVE':
                        live_url = app_info.get('live_url')
                        domain = self.environments[environment]['domain']
                        
                        print(f"✅ {environment.title()} deployment successful!")
                        print(f"🔗 Live URL: {live_url or f'https://{domain}'}")
                        
                        # Test health endpoint
                        health_result = self.test_environment_health(domain)
                        
                        return {
                            "success": True,
                            "app_id": app_id,
                            "environment": environment,
                            "live_url": live_url or f"https://{domain}",
                            "health_check": health_result
                        }
                    
                    elif phase in ['ERROR', 'SUPERSEDED']:
                        print(f"❌ {environment.title()} deployment failed: {phase}")
                        return {"success": False, "error": f"Deployment phase: {phase}"}
                
                time.sleep(15)
                attempt += 1
                
            except Exception as e:
                print(f"⚠️ Error monitoring deployment: {e}")
                time.sleep(15)
                attempt += 1
        
        print(f"❌ {environment.title()} deployment monitoring timed out")
        return {"success": False, "error": "Deployment monitoring timeout"}
    
    def test_environment_health(self, domain: str) -> Dict[str, Any]:
        """Test environment health endpoint"""
        import requests
        
        try:
            health_url = f"https://{domain}/health"
            print(f"🧪 Testing health endpoint: {health_url}")
            
            response = requests.get(health_url, timeout=30)
            
            if response.status_code == 200:
                health_data = response.json()
                print("✅ Health check passed")
                return {
                    "status": "healthy",
                    "details": health_data,
                    "response_time": response.elapsed.total_seconds()
                }
            else:
                print(f"❌ Health check failed: HTTP {response.status_code}")
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "error": response.text
                }
                
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return {"status": "error", "error": str(e)}
    
    def list_deployments(self) -> None:
        """List all current deployments"""
        print("🚀 Current Webhook Deployments:")
        print("=" * 60)
        
        try:
            result = subprocess.run(['doctl', 'apps', 'list', '--format', 'json'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                print("❌ Failed to list deployments")
                return
            
            apps = json.loads(result.stdout)
            webhook_apps = [app for app in apps if 'webhook' in app.get('spec', {}).get('name', '').lower()]
            
            if not webhook_apps:
                print("📭 No webhook deployments found")
                return
            
            for app in webhook_apps:
                name = app.get('spec', {}).get('name', 'Unknown')
                app_id = app.get('id', 'Unknown')
                phase = app.get('phase', 'Unknown')
                live_url = app.get('live_url', 'N/A')
                
                print(f"📍 {name}")
                print(f"   ID: {app_id}")
                print(f"   Status: {phase}")
                print(f"   URL: {live_url}")
                print()
                
        except Exception as e:
            print(f"❌ Error listing deployments: {e}")
    
    def generate_environment_report(self, results: List[Dict[str, Any]]) -> None:
        """Generate deployment report for multiple environments"""
        print("\\n" + "=" * 80)
        print("📋 MULTI-ENVIRONMENT DEPLOYMENT REPORT")
        print("=" * 80)
        
        successful = [r for r in results if r.get('success')]
        failed = [r for r in results if not r.get('success')]
        
        print(f"✅ Successful deployments: {len(successful)}")
        print(f"❌ Failed deployments: {len(failed)}")
        
        for result in successful:
            env = result.get('environment', 'Unknown')
            url = result.get('live_url', 'N/A')
            print(f"   🌍 {env.title()}: {url}")
        
        if failed:
            print("\\n❌ Failed Deployments:")
            for result in failed:
                env = result.get('environment', 'Unknown')
                error = result.get('error', 'Unknown error')
                print(f"   🚨 {env.title()}: {error}")
        
        print("\\n🔄 Next Steps:")
        print("1. Test webhook endpoints with WhatsApp Business API")
        print("2. Configure environment-specific webhook URLs in Meta Developer Console")
        print("3. Set up monitoring and alerting for production")
        print("4. Update DNS records for custom domains")
        print("=" * 80)

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description="Multi-Environment Webhook Management")
    parser.add_argument('action', choices=['list', 'deploy', 'update', 'status', 'test'],
                       help='Action to perform')
    parser.add_argument('--environment', '-e', choices=['development', 'staging', 'production'],
                       help='Target environment')
    parser.add_argument('--all', action='store_true',
                       help='Apply to all environments')
    
    args = parser.parse_args()
    
    manager = WebhookEnvironmentManager()
    
    if args.action == 'list':
        manager.list_environments()
        
    elif args.action == 'deploy':
        if args.all:
            results = []
            for env in ['development', 'staging', 'production']:
                print(f"\\n🚀 Deploying {env} environment...")
                result = manager.deploy_environment(env)
                result['environment'] = env
                results.append(result)
            manager.generate_environment_report(results)
        elif args.environment:
            result = manager.deploy_environment(args.environment)
        else:
            print("❌ Specify --environment or --all")
            
    elif args.action == 'update':
        if args.environment:
            result = manager.deploy_environment(args.environment, update=True)
        else:
            print("❌ Specify --environment for updates")
            
    elif args.action == 'status':
        manager.list_deployments()
        
    elif args.action == 'test':
        if args.environment:
            env_config = manager.environments.get(args.environment)
            if env_config:
                manager.test_environment_health(env_config['domain'])
        else:
            print("❌ Specify --environment for testing")

if __name__ == "__main__":
    main()