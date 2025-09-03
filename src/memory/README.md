# Memory Infrastructure for AI Agency Platform

This directory contains the Mem0-based memory infrastructure implementation for the AI Agency Platform's Executive Assistant agents, providing per-customer memory isolation with <500ms recall performance.

## Architecture Overview

### Memory Layer Hierarchy

```
Customer A                    Customer B
┌─────────────────────┐      ┌─────────────────────┐
│ EA Agent A          │      │ EA Agent B          │
│ ┌─────────────────┐ │      │ ┌─────────────────┐ │
│ │ Working Memory  │ │      │ │ Working Memory  │ │
│ │ (Redis DB 0)    │ │      │ │ (Redis DB 1)    │ │
│ │ <2ms access     │ │      │ │ <2ms access     │ │
│ └─────────────────┘ │      │ └─────────────────┘ │
│ ┌─────────────────┐ │      │ ┌─────────────────┐ │
│ │ Semantic Memory │ │      │ │ Semantic Memory │ │
│ │ (Mem0 + Qdrant) │ │      │ │ (Mem0 + Qdrant) │ │
│ │ <500ms SLA      │ │      │ │ <500ms SLA      │ │
│ └─────────────────┘ │      │ └─────────────────┘ │
│ ┌─────────────────┐ │      │ ┌─────────────────┐ │
│ │ Persistent Data │ │      │ │ Persistent Data │ │
│ │ (PostgreSQL)    │ │      │ │ (PostgreSQL)    │ │
│ │ <100ms queries  │ │      │ │ <100ms queries  │ │
│ └─────────────────┘ │      │ └─────────────────┘ │
└─────────────────────┘      └─────────────────────┘
```

## Key Features

- **Per-Customer Isolation**: Complete memory separation via unique `user_id` and `agent_id`
- **Hybrid Memory Architecture**: Optimized for different access patterns
- **Performance SLA**: <500ms semantic memory recall guaranteed
- **Scalability**: Support for 100+ concurrent customers
- **Cross-Channel Continuity**: Seamless conversation flow across phone, WhatsApp, email

## Components

### Core Memory Manager (`mem0_manager.py`)

```python
from src.memory import EAMemoryManager

# Initialize per-customer memory
memory_manager = EAMemoryManager("customer_123")

# Store business context
await memory_manager.store_business_context(
    context={"business_description": "E-commerce jewelry store"},
    session_id="discovery_session_1"
)

# Retrieve with semantic search
results = await memory_manager.retrieve_business_context(
    query="jewelry business automation opportunities",
    limit=5
)
```

### Isolation Validator (`isolation_validator.py`)

```python
from src.memory import MemoryIsolationValidator

# Validate customer isolation
validation_result = await MemoryIsolationValidator.validate_customer_isolation(
    customer_a_id="customer_123",
    customer_b_id="customer_456"
)

assert validation_result["isolation_verified"] == True
```

### Performance Monitor (`performance_monitor.py`)

```python
from src.memory import MemoryPerformanceMonitor

# Track operation performance
monitor = MemoryPerformanceMonitor("customer_123")
await monitor.track_memory_operation(
    operation="mem0_search",
    latency=0.245,  # 245ms
    success=True
)

# Generate performance report
report = await monitor.generate_performance_report(time_window_hours=24)
```

## Infrastructure Services

### 1. Qdrant Vector Database
- **Purpose**: Vector storage for Mem0 embeddings
- **Port**: 6333 (HTTP), 6334 (gRPC)
- **Collections**: Per-customer isolation via `customer_{id}_memories`

### 2. Neo4j Graph Database
- **Purpose**: Graph relationships for Mem0 knowledge graphs
- **Port**: 7474 (Browser), 7687 (Bolt)
- **Databases**: Per-customer isolation via `customer_{id}_graph`

### 3. Memory Monitor Service
- **Purpose**: Real-time monitoring and SLA enforcement
- **Port**: 8084
- **Features**: Performance tracking, alerting, isolation validation

## Performance SLA Targets

| Operation | Target | Layer |
|-----------|--------|--------|
| Semantic Search | <500ms | Mem0 + Qdrant |
| Working Memory | <2ms | Redis |
| Persistent Query | <100ms | PostgreSQL |
| Hybrid Retrieval | <1s | All layers |

## Customer Isolation

### Memory Boundaries
- **Mem0**: Unique `user_id` per customer (`customer_{id}`)
- **Redis**: Separate database per customer (DB 0-15)
- **Qdrant**: Separate collections (`customer_{id}_memories`)
- **Neo4j**: Separate databases (`customer_{id}_graph`)
- **PostgreSQL**: Customer ID filtering on all queries

### Validation
- **Automated Testing**: Continuous isolation validation
- **Zero Cross-Access**: Guaranteed no customer data leakage
- **Enterprise Grade**: Suitable for sensitive business data

## Quick Start

### 1. Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Edit with your configuration
vim .env
```

### 2. Start Infrastructure
```bash
# Start all memory services
docker compose up -d postgres redis qdrant neo4j memory-monitor

# Verify services are healthy
curl http://localhost:8084/health
```

### 3. Run Tests
```bash
# Install dependencies
pip install -r requirements.txt

# Run memory integration tests
python -m pytest tests/memory/ -v
```

### 4. Initialize Customer Memory
```python
from src.memory import EAMemoryManager

# Create memory manager for new customer
memory_manager = EAMemoryManager("customer_new_123")

# Store initial business context
await memory_manager.store_business_context(
    context={
        "business_description": "New customer onboarding",
        "discovery_phase": "initial"
    },
    session_id="onboarding_session"
)
```

## Monitoring & Alerting

### Health Checks
```bash
# Overall system health
curl http://localhost:8084/health

# Detailed component health
curl http://localhost:8084/health/detailed
```

### Performance Metrics
```bash
# Prometheus metrics
curl http://localhost:8084/metrics

# Customer-specific performance
curl http://localhost:8084/customers/customer_123/performance
```

### SLA Monitoring
```bash
# Performance report
curl -X POST http://localhost:8084/performance/report \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "customer_123", "time_window_hours": 24}'
```

### Isolation Testing
```bash
# Test isolation between customers
curl -X POST http://localhost:8084/isolation/test \
  -H "Content-Type: application/json" \
  -d '{"customer_a_id": "customer_123", "customer_b_id": "customer_456"}'
```

## Configuration

### Memory Configuration
```python
config = {
    "mem0": {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "host": "localhost",
                "port": 6333,
                "collection_name": "customer_{customer_id}_memories"
            }
        },
        "graph_store": {
            "provider": "neo4j",
            "config": {
                "url": "neo4j://localhost:7687",
                "database": "customer_{customer_id}_graph"
            }
        },
        "llm": {
            "provider": "openai",
            "config": {"model": "gpt-4o-mini"}
        }
    }
}
```

### Performance Tuning
```python
performance_config = {
    "redis_timeout": 0.002,     # 2ms
    "mem0_timeout": 0.5,        # 500ms SLA
    "postgres_timeout": 0.1,    # 100ms
    "connection_pools": 10
}
```

## Troubleshooting

### Common Issues

1. **Memory SLA Violations**
   - Check Qdrant performance: `curl http://localhost:6333/health`
   - Monitor connection pools
   - Review query complexity

2. **Isolation Failures**
   - Verify customer ID uniqueness
   - Check collection/database naming
   - Run isolation validation tests

3. **Connection Errors**
   - Verify all services are running
   - Check network connectivity
   - Review service dependencies

### Debug Commands
```bash
# Check service logs
docker logs ai-agency-qdrant
docker logs ai-agency-neo4j
docker logs ai-agency-memory-monitor

# Test memory operations
python tests/memory/test_mem0_integration.py

# Performance diagnostics
curl http://localhost:8084/customers/customer_123/memory/test
```

## Development

### Adding New Memory Operations
1. Extend `EAMemoryManager` class
2. Add performance tracking
3. Update TDD tests
4. Document API changes

### Custom Memory Layers
1. Implement memory interface
2. Add to `OptimizedMemoryRouter`
3. Configure SLA targets
4. Add monitoring support

## Production Deployment

### Scaling Guidelines
- **Qdrant**: Scale horizontally with sharding
- **Neo4j**: Use clustering for high availability
- **Redis**: Use Redis Cluster for >16 DBs
- **Monitoring**: Deploy memory-monitor in HA mode

### Security Considerations
- Enable authentication on all services
- Use TLS for inter-service communication
- Regular security audits
- Customer data encryption at rest

## Support

For issues related to memory infrastructure:
1. Check monitoring dashboards
2. Review service logs
3. Run diagnostic tests
4. Consult architecture documentation