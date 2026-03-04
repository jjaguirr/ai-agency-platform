# Docker Configuration

## Docker Compose Files

All docker-compose files live at the **project root**:

### Development (`docker-compose.yml`)
Main development environment with all services for local development.

```bash
docker compose up -d
```

### CI/CD (`docker-compose.ci.yml`)
Minimal services for continuous integration testing.

```bash
docker compose -f docker-compose.ci.yml up -d
```

### Production (`docker-compose.production.yml`)
Production-ready configuration with resource limits, health checks, and security.

```bash
docker compose -f docker-compose.production.yml up -d
```

### Monitoring (`docker/docker-compose.monitoring.yml`)
Observability stack (Prometheus, Grafana, Jaeger). Overlay on top of dev:

```bash
docker compose -f docker-compose.yml -f docker/docker-compose.monitoring.yml up -d
```

## Environment Files
- `.env` - Main environment variables (not committed)
- `.env.production.template` - Template for production variables
