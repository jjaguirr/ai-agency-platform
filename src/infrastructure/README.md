# AI Agency Platform - Phase 3: Port Allocation & Infrastructure Orchestration

This module implements intelligent port allocation and infrastructure orchestration for customer isolation and rapid provisioning.

## 🎯 Key Features

### Intelligent Port Allocation
- **Dynamic Port Management**: Automatic port allocation with conflict resolution
- **Service-Specific Ranges**: Dedicated port ranges for different service types
- **Customer Isolation**: Complete port isolation between customers
- **Performance Optimized**: Sub-100ms allocation with intelligent distribution
- **Persistence**: Database-backed allocation tracking with Redis caching

### Infrastructure Orchestration  
- **Rapid Provisioning**: <30 second customer environment setup
- **Complete Isolation**: Per-customer Docker networks and resources
- **Tier-Based Scaling**: Basic, Professional, Enterprise service tiers
- **Health Monitoring**: Automated service health checks and recovery
- **Lifecycle Management**: Full deployment, scaling, and termination workflows

### Docker Compose Integration
- **Dynamic Configuration**: Auto-generated customer-specific configurations
- **Security-First**: Automated credential generation and secure defaults
- **Deployment Automation**: One-command deployment scripts
- **Environment Management**: Isolated customer configurations and volumes

## 🏗️ Architecture

### Port Allocation System
```
Port Ranges:
├── MCP Server:        30000-30999
├── PostgreSQL:        31000-31999  
├── Redis:             32000-32999
├── Qdrant HTTP:       33000-33999
├── Qdrant gRPC:       34000-34999
├── Neo4j HTTP:        35000-35999
├── Neo4j Bolt:        36000-36999
├── Memory Monitor:    37000-37999
├── Security API:      38000-38999
└── Custom Services:   39000-49999
```

### Service Tiers
```yaml
Basic Tier:
  Memory: 2G
  CPU: 1.0
  Services: [PostgreSQL, Redis, MCP Server]
  Max Customers: 100

Professional Tier:  
  Memory: 4G
  CPU: 2.0
  Services: [PostgreSQL, Redis, Qdrant, MCP Server, Memory Monitor]
  Max Customers: 500

Enterprise Tier:
  Memory: 8G
  CPU: 4.0  
  Services: [PostgreSQL, Redis, Qdrant, Neo4j, MCP Server, Memory Monitor, Security API]
  Max Customers: 1000
```

## 🚀 Quick Start

### 1. Initialize System
```bash
# Install dependencies
pip install -r requirements.txt

# Start core services
docker-compose up -d postgres redis qdrant

# Initialize port allocation system
python -m infrastructure.cli metrics
```

### 2. Provision Customer Environment
```bash
# Allocate ports for customer services
python -m infrastructure.cli allocate \\
  --customer-id customer_001 \\
  --services postgres,redis,qdrant,mcp_server,memory_monitor

# Provision complete environment
python -m infrastructure.cli provision \\
  --customer-id customer_001 \\
  --tier professional \\
  --ai-model claude-3.5-sonnet
```

### 3. Generate Deployment Configuration
```bash
# Generate Docker Compose configuration
python -m infrastructure.cli compose \\
  --customer-id customer_001 \\
  --tier professional \\
  --output-dir ./deploy/customers

# Deploy customer environment
./deploy/customers/deploy-customer_001.sh
```

### 4. Monitor and Manage
```bash
# Check environment status
python -m infrastructure.cli status --customer-id customer_001

# Get system metrics
python -m infrastructure.cli metrics

# Cleanup expired resources
python -m infrastructure.cli cleanup
```

## 📚 API Reference

### Port Allocator

```python
from infrastructure.port_allocator import create_port_allocator, ServiceType

# Initialize allocator
allocator = await create_port_allocator(
    redis_url="redis://localhost:6379",
    postgres_url="postgresql://user:pass@localhost:5432/db"
)

# Allocate port
allocation = await allocator.allocate_port(
    customer_id="customer_001",
    service_type=ServiceType.POSTGRES,
    preferred_port=31001  # Optional
)

# Get customer ports
ports = await allocator.get_customer_ports("customer_001")

# Monitor utilization
utilization = await allocator.get_port_utilization()
```

### Infrastructure Orchestrator

```python
from infrastructure.infrastructure_orchestrator import create_infrastructure_orchestrator

# Initialize orchestrator  
orchestrator = await create_infrastructure_orchestrator()

# Provision environment
environment = await orchestrator.provision_customer_environment(
    customer_id="customer_001",
    tier="professional",
    ai_model="claude-3.5-sonnet"
)

# Health check
health = await orchestrator.perform_health_check("customer_001")

# Terminate environment
success = await orchestrator.terminate_customer_environment("customer_001")
```

### Docker Compose Generator

```python
from infrastructure.docker_compose_generator import DockerComposeGenerator

# Create generator
generator = DockerComposeGenerator(port_allocator)

# Generate configuration
compose_file = await generator.generate_customer_compose(
    customer_id="customer_001",
    tier="professional", 
    ai_model="claude-3.5-sonnet",
    credentials=secure_credentials,
    allocated_ports=port_allocations
)
```

## 🔧 Configuration

### Environment Variables
```bash
# Database connections
REDIS_URL=redis://localhost:6379
POSTGRES_URL=postgresql://user:pass@localhost:5432/db

# Port allocation settings  
PORT_ALLOCATION_TIMEOUT=30
PORT_RANGE_START_POSTGRES=31000
PORT_RANGE_END_POSTGRES=31999

# Infrastructure settings
DEPLOYMENT_TIMEOUT=300
HEALTH_CHECK_INTERVAL=60
MAX_CONCURRENT_DEPLOYMENTS=10

# Security settings
JWT_SECRET_LENGTH=32
POSTGRES_PASSWORD_LENGTH=24
ENCRYPTION_KEY_LENGTH=32
```

### Service Configuration Files
```
config/
├── postgres/
│   ├── customer-init.sql
│   └── production.conf
├── redis/
│   └── redis.conf  
├── qdrant/
│   └── production.yaml
├── neo4j/
│   └── neo4j.conf
└── mcp/
    └── {customer_id}/
        └── config.yaml
```

## 🧪 Testing

### Unit Tests
```bash
# Run port allocation tests
python -m pytest tests/unit/test_port_allocator.py -v

# Run orchestration tests  
python -m pytest tests/unit/test_infrastructure_orchestrator.py -v

# Run Docker Compose tests
python -m pytest tests/unit/test_docker_compose_generator.py -v
```

### Integration Tests
```bash
# Run complete integration test suite
python -m pytest tests/integration/test_port_allocation_integration.py -v

# Run performance benchmarks
python -m pytest tests/integration/test_port_allocation_integration.py::TestPortAllocationIntegration::test_performance_benchmarks -v
```

### Load Testing
```bash
# Test rapid customer provisioning
python scripts/load_test_provisioning.py --customers 100 --concurrent 10

# Test port allocation performance
python scripts/benchmark_port_allocation.py --allocations 1000
```

## 📊 Monitoring & Metrics

### Key Performance Indicators
- **Port Allocation Time**: Target <100ms (95th percentile)
- **Environment Provisioning**: Target <30 seconds end-to-end
- **System Uptime**: Target >99.9% availability
- **Customer Isolation**: 100% verified separation
- **Resource Utilization**: Optimized per-customer limits

### Monitoring Endpoints
```bash
# Health check
GET /health

# Metrics
GET /metrics

# Port utilization
GET /metrics/ports

# Environment status
GET /metrics/environments
```

### Alerting
- Port range utilization >85%
- Failed environment provisioning
- Service health check failures
- Resource limit breaches
- Customer isolation violations

## 🔒 Security

### Customer Isolation
- **Network Isolation**: Dedicated Docker networks per customer
- **Port Isolation**: Non-overlapping port allocations  
- **Data Isolation**: Separate databases and volumes
- **Process Isolation**: Individual containers per customer
- **Access Control**: Customer-specific credentials and tokens

### Security Best Practices
- Automated credential generation with high entropy
- Regular credential rotation (configurable intervals)
- Encrypted communication between services
- Audit logging for all infrastructure operations
- Compliance with data protection regulations

## 🚀 Production Deployment

### Infrastructure Requirements
- **CPU**: Minimum 8 cores, recommended 16+ cores
- **Memory**: Minimum 32GB RAM, recommended 64+ GB
- **Storage**: SSD storage, 1TB+ for customer data
- **Network**: Gigabit networking for service communication
- **Docker**: Docker Engine 20.10+ with Compose v3.8+

### Scaling Considerations
- **Horizontal Scaling**: Multiple orchestrator instances
- **Database Scaling**: Read replicas for port allocation
- **Load Balancing**: Customer traffic distribution  
- **Backup Strategy**: Automated backups for customer data
- **Disaster Recovery**: Multi-region deployment capability

### Deployment Checklist
- [ ] Core infrastructure services running
- [ ] Database migrations completed
- [ ] Port ranges configured and validated
- [ ] Security policies applied
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery tested
- [ ] Load testing completed
- [ ] Customer onboarding workflow validated

## 🐛 Troubleshooting

### Common Issues

**Port Allocation Failures**
```bash
# Check port range utilization
python -m infrastructure.cli metrics

# Cleanup expired allocations
python -m infrastructure.cli cleanup

# Manually deallocate stuck ports
python -m infrastructure.cli deallocate --customer-id <customer_id>
```

**Environment Provisioning Failures**
```bash
# Check Docker status
docker system info

# Review orchestrator logs
docker logs ai-agency-orchestrator

# Force cleanup failed deployment
python -m infrastructure.cli terminate --customer-id <customer_id> --force
```

**Service Health Issues**
```bash
# Check individual service health
docker-compose -f deploy/customers/docker-compose.<customer_id>.yml ps

# View service logs
docker-compose -f deploy/customers/docker-compose.<customer_id>.yml logs <service_name>

# Restart unhealthy services
docker-compose -f deploy/customers/docker-compose.<customer_id>.yml restart <service_name>
```

### Support Resources
- **Documentation**: [Technical Design Document](../../docs/architecture/Technical-Design-Document.md)
- **Issue Tracking**: GitHub Issues with `infrastructure` label
- **Performance Monitoring**: Built-in metrics and monitoring
- **Community Support**: Platform development team

## 🔄 Continuous Improvement

### Roadmap
- [ ] **Auto-scaling**: Dynamic resource scaling based on usage
- [ ] **Multi-region**: Cross-region deployment capabilities  
- [ ] **Advanced Monitoring**: Predictive alerting and anomaly detection
- [ ] **Cost Optimization**: Resource usage optimization algorithms
- [ ] **Service Mesh**: Advanced service-to-service communication
- [ ] **GitOps Integration**: Infrastructure as Code deployment

### Contributing
1. Review architecture and design patterns
2. Follow TDD practices for all infrastructure changes
3. Ensure complete test coverage for new features
4. Validate performance impacts with benchmarks
5. Document all configuration and operational procedures

---

**Phase 3 Infrastructure Module**  
Part of the AI Agency Platform  
Built with ❤️ for scalable customer isolation