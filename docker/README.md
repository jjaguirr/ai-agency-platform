# Docker Configuration

**Note**: Active Docker Compose files are located in the **project root directory**.

## Docker Compose Files (Root Directory)

### Development (`../docker-compose.yml`)
**Location**: `./docker-compose.yml`
Main development environment with all services needed for local development:
- PostgreSQL (customer data)
- Redis (session/cache)  
- Qdrant (vector storage)
- All AI Agency Platform services

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
**Location**: `./docker-compose.ci.yml`
Ultra-optimized CI configuration with <60s startup:
- Lightweight test database (tmpfs)
- In-memory cache
- Aggressive performance optimizations
- GitHub Actions optimized

**Usage**:
```bash
docker-compose -f docker-compose.ci.yml up --build
```

### Production (`../docker-compose.production.yml`)
**Location**: `./docker-compose.production.yml`
Per-customer production infrastructure template:
- Customer isolation with dedicated ports
- Resource limits and health checks
- Security hardening
- Scalable deployment (1000+ customers)

**Usage**:
```bash
# Set customer environment variables
export CUSTOMER_ID=customer_12345
export CUSTOMER_TIER=professional
docker-compose -f docker-compose.production.yml up -d
```

## Quick Commands

```bash
# Development (most common)
docker-compose up

# CI testing  
docker-compose -f docker-compose.ci.yml up --build

# Production deployment
docker-compose -f docker-compose.production.yml up -d
```

## Environment Files
- `.env` - Main environment variables (not committed)
- `.env.production` - Production environment template
- `.env.production.template` - Template for required variables
- Production environments use separate secure configs per customer

## Archive
Previous docker compose configurations have been moved to:
`docs/archive/2025-09-10/docker/`

These were replaced by the optimized root directory configurations that support:
- Ultra-fast CI startup (<60s)
- Per-customer production isolation
- Enhanced development experience