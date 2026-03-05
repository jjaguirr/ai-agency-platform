# Docker Configuration

## Docker Compose Files

### Development (`../docker-compose.yml`)
Main development environment with all services needed for local development:
- PostgreSQL (customer data)
- Redis (session/cache)
- ChromaDB (vector storage)
- Services accessible on standard ports

**Usage**:
```bash
# Start development environment
docker-compose up

# Background mode
docker-compose up -d

# Stop services
docker-compose down
```

### CI/CD (`../docker-compose.ci.yml`)
Minimal services for continuous integration testing:
- Lightweight test database
- In-memory cache
- Optimized for speed

**Usage**:
```bash
docker compose -f docker-compose.ci.yml up --build
```

### Production (`../docker-compose.production.yml`)
Production-ready configuration with:
- Resource limits
- Health checks
- Security hardening
- Persistent volumes
- Load balancing

**Usage**:
```bash
docker compose -f docker-compose.production.yml up -d
```

### Monitoring (`docker-compose.monitoring.yml`)
Observability stack:
- Prometheus (metrics)
- Grafana (dashboards)
- Jaeger (tracing)
- Log aggregation

**Usage**:
```bash
# Add to development stack
docker-compose -f docker-compose.yml -f docker/docker-compose.monitoring.yml up
```

## Quick Commands

```bash
# Development (most common)
docker-compose up

# With monitoring
docker-compose -f docker-compose.yml -f docker/docker-compose.monitoring.yml up

# CI testing
docker compose -f docker-compose.ci.yml up --build

# Production deployment
docker compose -f docker-compose.production.yml up -d
```

## Environment Files
- `.env` - Main environment variables (not committed)
- `.env.example` - Template for required variables
- Production environments use separate secure configs