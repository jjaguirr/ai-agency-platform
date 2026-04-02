#!/usr/bin/env python3
"""
AI Agency Platform - Infrastructure Management CLI
Phase 3: Port Allocation and Orchestration Management

Command-line interface for managing port allocation, customer environments,
and infrastructure orchestration operations.

Usage:
    python -m infrastructure.cli allocate --customer-id customer_001 --services postgres,redis
    python -m infrastructure.cli provision --customer-id customer_001 --tier professional
    python -m infrastructure.cli status --customer-id customer_001
    python -m infrastructure.cli metrics
    python -m infrastructure.cli cleanup
"""

import asyncio
import argparse
import json
import sys
import logging
from typing import List, Dict, Any
from pathlib import Path

from src.infrastructure.port_allocator import (
    create_port_allocator, ServiceType, allocate_customer_ports
)
from src.infrastructure.infrastructure_orchestrator import (
    create_infrastructure_orchestrator
)
from src.infrastructure.docker_compose_generator import DockerComposeGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InfrastructureCLI:
    """Command-line interface for infrastructure management"""
    
    def __init__(self):
        self.port_allocator = None
        self.orchestrator = None
        
    async def initialize(self, redis_url: str = None, postgres_url: str = None):
        """Initialize CLI with database connections"""
        try:
            self.port_allocator = await create_port_allocator(
                redis_url=redis_url, 
                postgres_url=postgres_url
            )
            self.orchestrator = await create_infrastructure_orchestrator(
                redis_url=redis_url,
                postgres_url=postgres_url
            )
            logger.info("✅ CLI initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize CLI: {e}")
            raise
    
    async def close(self):
        """Close connections and cleanup"""
        if self.port_allocator:
            await self.port_allocator.close()
        if self.orchestrator and hasattr(self.orchestrator, 'port_allocator'):
            # Don't double-close the same allocator
            pass
        logger.info("✅ CLI connections closed")
    
    async def allocate_ports_command(self, customer_id: str, services: List[str], 
                                   preferred_ports: Dict[str, int] = None) -> Dict[str, Any]:
        """Allocate ports for customer services"""
        try:
            # Convert service strings to ServiceType enums
            service_types = []
            for service_str in services:
                try:
                    service_type = ServiceType(service_str.upper())
                    service_types.append(service_type)
                except ValueError:
                    logger.error(f"❌ Unknown service type: {service_str}")
                    return {"success": False, "error": f"Unknown service type: {service_str}"}
            
            logger.info(f"🔄 Allocating ports for customer {customer_id}, services: {services}")
            
            # Allocate ports
            allocated_ports = {}
            for service_type in service_types:
                preferred_port = preferred_ports.get(service_type.value.lower()) if preferred_ports else None
                
                allocation = await self.port_allocator.allocate_port(
                    customer_id=customer_id,
                    service_type=service_type,
                    preferred_port=preferred_port
                )
                allocated_ports[service_type.value] = allocation.port
            
            logger.info(f"✅ Allocated ports: {allocated_ports}")
            
            return {
                "success": True,
                "customer_id": customer_id,
                "allocated_ports": allocated_ports,
                "message": f"Successfully allocated {len(allocated_ports)} ports"
            }
        
        except Exception as e:
            logger.error(f"❌ Port allocation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def deallocate_ports_command(self, customer_id: str, services: List[str] = None) -> Dict[str, Any]:
        """Deallocate ports for customer services"""
        try:
            if services:
                # Deallocate specific services
                service_types = [ServiceType(s.upper()) for s in services]
                deallocated = []
                
                for service_type in service_types:
                    success = await self.port_allocator.deallocate_port(customer_id, service_type)
                    if success:
                        deallocated.append(service_type.value)
                
                logger.info(f"✅ Deallocated ports for services: {deallocated}")
                return {
                    "success": True,
                    "customer_id": customer_id,
                    "deallocated_services": deallocated
                }
            else:
                # Deallocate all customer ports
                customer_ports = await self.port_allocator.get_customer_ports(customer_id)
                deallocated = []
                
                for service_type in customer_ports.keys():
                    success = await self.port_allocator.deallocate_port(customer_id, service_type)
                    if success:
                        deallocated.append(service_type.value)
                
                logger.info(f"✅ Deallocated all ports for customer {customer_id}")
                return {
                    "success": True,
                    "customer_id": customer_id,
                    "deallocated_services": deallocated
                }
        
        except Exception as e:
            logger.error(f"❌ Port deallocation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def provision_environment_command(self, customer_id: str, tier: str, 
                                         ai_model: str = "claude-3.5-sonnet",
                                         custom_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Provision complete customer environment"""
        try:
            logger.info(f"🚀 Provisioning environment for customer {customer_id} (tier: {tier})")
            
            environment = await self.orchestrator.provision_customer_environment(
                customer_id=customer_id,
                tier=tier,
                ai_model=ai_model,
                custom_config=custom_config
            )
            
            logger.info(f"✅ Environment provisioned successfully")
            
            return {
                "success": True,
                "environment": environment.to_dict(),
                "message": f"Environment provisioned for customer {customer_id}"
            }
        
        except Exception as e:
            logger.error(f"❌ Environment provisioning failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def terminate_environment_command(self, customer_id: str, force: bool = False) -> Dict[str, Any]:
        """Terminate customer environment"""
        try:
            logger.info(f"🗑️ Terminating environment for customer {customer_id}")
            
            success = await self.orchestrator.terminate_customer_environment(
                customer_id=customer_id,
                force=force
            )
            
            if success:
                logger.info(f"✅ Environment terminated successfully")
                return {
                    "success": True,
                    "customer_id": customer_id,
                    "message": "Environment terminated successfully"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to terminate environment"
                }
        
        except Exception as e:
            logger.error(f"❌ Environment termination failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_status_command(self, customer_id: str = None) -> Dict[str, Any]:
        """Get status of customer environments"""
        try:
            if customer_id:
                # Get specific customer status
                environment_status = self.orchestrator.get_environment_status(customer_id)
                if environment_status:
                    customer_ports = await self.port_allocator.get_customer_ports(customer_id)
                    health_check = await self.orchestrator.perform_health_check(customer_id)
                    
                    return {
                        "success": True,
                        "customer_id": customer_id,
                        "environment": environment_status,
                        "allocated_ports": {k.value: v for k, v in customer_ports.items()},
                        "health_check": health_check
                    }
                else:
                    return {
                        "success": False,
                        "error": f"No environment found for customer {customer_id}"
                    }
            else:
                # Get status of all environments
                environments = self.orchestrator.list_environments()
                return {
                    "success": True,
                    "environments": environments,
                    "total_environments": len(environments)
                }
        
        except Exception as e:
            logger.error(f"❌ Failed to get status: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_metrics_command(self) -> Dict[str, Any]:
        """Get system metrics"""
        try:
            allocation_metrics = self.port_allocator.get_allocation_metrics()
            utilization = await self.port_allocator.get_port_utilization()
            orchestration_metrics = self.orchestrator.get_orchestration_metrics()
            
            return {
                "success": True,
                "allocation_metrics": allocation_metrics,
                "port_utilization": utilization,
                "orchestration_metrics": orchestration_metrics,
                "timestamp": allocation_metrics.get("timestamp")
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to get metrics: {e}")
            return {"success": False, "error": str(e)}
    
    async def cleanup_command(self) -> Dict[str, Any]:
        """Cleanup expired allocations and orphaned resources"""
        try:
            logger.info("🧹 Starting cleanup process...")
            
            # Cleanup expired allocations
            expired_count = await self.port_allocator.cleanup_expired_allocations()
            
            # Additional cleanup could be added here
            cleanup_results = {
                "expired_allocations_cleaned": expired_count,
                "cleanup_timestamp": self.port_allocator.allocation_metrics.get("last_cleanup")
            }
            
            logger.info(f"✅ Cleanup completed: {cleanup_results}")
            
            return {
                "success": True,
                "cleanup_results": cleanup_results,
                "message": "Cleanup completed successfully"
            }
        
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_compose_command(self, customer_id: str, tier: str, 
                                     ai_model: str = "claude-3.5-sonnet",
                                     output_dir: str = "./deploy/customers") -> Dict[str, Any]:
        """Generate Docker Compose configuration for customer"""
        try:
            logger.info(f"📝 Generating Docker Compose for customer {customer_id}")
            
            # Get allocated ports
            customer_ports = await self.port_allocator.get_customer_ports(customer_id)
            if not customer_ports:
                return {
                    "success": False,
                    "error": f"No ports allocated for customer {customer_id}. Run 'allocate' first."
                }
            
            # Generate credentials (in production, these would be securely generated)
            credentials = {
                "postgres_password": f"secure_pass_{customer_id}",
                "jwt_secret": f"jwt_secret_{customer_id}",
                "encryption_key": f"enc_key_{customer_id}"
            }
            
            # Create generator
            generator = DockerComposeGenerator(
                port_allocator=self.port_allocator,
                output_dir=output_dir
            )
            
            # Generate configuration
            compose_file = await generator.generate_customer_compose(
                customer_id=customer_id,
                tier=tier,
                ai_model=ai_model,
                credentials=credentials,
                allocated_ports=customer_ports
            )
            
            # Generate deployment script
            script_file = generator.generate_deployment_script(customer_id, compose_file)
            
            logger.info(f"✅ Generated Docker Compose configuration")
            
            return {
                "success": True,
                "customer_id": customer_id,
                "compose_file": str(compose_file),
                "deployment_script": str(script_file),
                "allocated_ports": {k.value: v for k, v in customer_ports.items()},
                "message": "Docker Compose configuration generated successfully"
            }
        
        except Exception as e:
            logger.error(f"❌ Docker Compose generation failed: {e}")
            return {"success": False, "error": str(e)}


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser"""
    parser = argparse.ArgumentParser(
        description="AI Agency Platform - Infrastructure Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Allocate ports for customer services
  python -m infrastructure.cli allocate --customer-id customer_001 --services postgres,redis,qdrant
  
  # Provision complete environment
  python -m infrastructure.cli provision --customer-id customer_001 --tier professional --ai-model claude-3.5-sonnet
  
  # Get customer status
  python -m infrastructure.cli status --customer-id customer_001
  
  # Get system metrics
  python -m infrastructure.cli metrics
  
  # Generate Docker Compose configuration
  python -m infrastructure.cli compose --customer-id customer_001 --tier professional
  
  # Cleanup expired resources
  python -m infrastructure.cli cleanup
        """
    )
    
    # Global options
    parser.add_argument('--redis-url', help='Redis connection URL')
    parser.add_argument('--postgres-url', help='PostgreSQL connection URL')
    parser.add_argument('--json', action='store_true', help='Output results as JSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Allocate ports command
    allocate_parser = subparsers.add_parser('allocate', help='Allocate ports for customer services')
    allocate_parser.add_argument('--customer-id', required=True, help='Customer identifier')
    allocate_parser.add_argument('--services', required=True, 
                               help='Comma-separated list of services (postgres,redis,qdrant,etc.)')
    allocate_parser.add_argument('--preferred-ports', 
                               help='JSON object with preferred ports for services')
    
    # Deallocate ports command
    deallocate_parser = subparsers.add_parser('deallocate', help='Deallocate customer ports')
    deallocate_parser.add_argument('--customer-id', required=True, help='Customer identifier')
    deallocate_parser.add_argument('--services', 
                                 help='Comma-separated list of services (omit to deallocate all)')
    
    # Provision environment command
    provision_parser = subparsers.add_parser('provision', help='Provision customer environment')
    provision_parser.add_argument('--customer-id', required=True, help='Customer identifier')
    provision_parser.add_argument('--tier', required=True, choices=['basic', 'professional', 'enterprise'],
                                help='Service tier')
    provision_parser.add_argument('--ai-model', default='claude-3.5-sonnet', help='AI model preference')
    provision_parser.add_argument('--custom-config', help='JSON object with custom configuration')
    
    # Terminate environment command
    terminate_parser = subparsers.add_parser('terminate', help='Terminate customer environment')
    terminate_parser.add_argument('--customer-id', required=True, help='Customer identifier')
    terminate_parser.add_argument('--force', action='store_true', help='Force termination')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Get environment status')
    status_parser.add_argument('--customer-id', help='Customer identifier (omit for all environments)')
    
    # Metrics command
    subparsers.add_parser('metrics', help='Get system metrics')
    
    # Cleanup command
    subparsers.add_parser('cleanup', help='Cleanup expired allocations and resources')
    
    # Docker Compose generation command
    compose_parser = subparsers.add_parser('compose', help='Generate Docker Compose configuration')
    compose_parser.add_argument('--customer-id', required=True, help='Customer identifier')
    compose_parser.add_argument('--tier', required=True, choices=['basic', 'professional', 'enterprise'],
                              help='Service tier')
    compose_parser.add_argument('--ai-model', default='claude-3.5-sonnet', help='AI model preference')
    compose_parser.add_argument('--output-dir', default='./deploy/customers', help='Output directory')
    
    return parser


async def main():
    """Main CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize CLI
    cli = InfrastructureCLI()
    
    try:
        await cli.initialize(redis_url=args.redis_url, postgres_url=args.postgres_url)
        
        # Execute command
        result = None
        
        if args.command == 'allocate':
            services = [s.strip() for s in args.services.split(',')]
            preferred_ports = json.loads(args.preferred_ports) if args.preferred_ports else None
            result = await cli.allocate_ports_command(args.customer_id, services, preferred_ports)
        
        elif args.command == 'deallocate':
            services = [s.strip() for s in args.services.split(',')] if args.services else None
            result = await cli.deallocate_ports_command(args.customer_id, services)
        
        elif args.command == 'provision':
            custom_config = json.loads(args.custom_config) if args.custom_config else None
            result = await cli.provision_environment_command(
                args.customer_id, args.tier, args.ai_model, custom_config
            )
        
        elif args.command == 'terminate':
            result = await cli.terminate_environment_command(args.customer_id, args.force)
        
        elif args.command == 'status':
            result = await cli.get_status_command(args.customer_id)
        
        elif args.command == 'metrics':
            result = await cli.get_metrics_command()
        
        elif args.command == 'cleanup':
            result = await cli.cleanup_command()
        
        elif args.command == 'compose':
            result = await cli.generate_compose_command(
                args.customer_id, args.tier, args.ai_model, args.output_dir
            )
        
        # Output result
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get('success'):
                print(f"✅ {result.get('message', 'Command completed successfully')}")
                if 'allocated_ports' in result:
                    print(f"Allocated ports: {result['allocated_ports']}")
                if 'environment' in result:
                    env = result['environment']
                    print(f"Environment status: {env.get('status')}")
                    print(f"Services: {len(env.get('services', {}))}")
            else:
                print(f"❌ Command failed: {result.get('error', 'Unknown error')}")
                sys.exit(1)
    
    except Exception as e:
        logger.error(f"❌ CLI error: {e}")
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            print(f"❌ Error: {e}")
        sys.exit(1)
    
    finally:
        await cli.close()


if __name__ == "__main__":
    asyncio.run(main())