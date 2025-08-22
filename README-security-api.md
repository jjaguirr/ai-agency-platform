# Security API (Bypass Mode) - Development Setup

## Overview

This is a simplified security API stack for development that runs in **bypass mode**. The API maintains the same interface as production but returns "safe" for all content evaluations, allowing unblocked development while preserving the security architecture.

## Quick Start

```bash
# Start security API stack
docker-compose -f docker-compose.security-api.yml --env-file .env.security up -d

# Check service status
docker-compose -f docker-compose.security-api.yml --env-file .env.security ps

# View logs
docker-compose -f docker-compose.security-api.yml --env-file .env.security logs -f

# Stop services
docker-compose -f docker-compose.security-api.yml --env-file .env.security down
```

## Services

| Service | Purpose | Port | Status |
|---------|---------|------|--------|
| **security-api** | Security evaluation API (bypass mode) | 8083 | ✅ Returns "safe" for all content |
| **redis-security** | Cache and session storage | 6380 | ✅ Working |
| **security-proxy** | Rate limiting and proxy | 8080 | ⚠️  May need nginx config fix |

## Configuration

- **Environment**: `.env.security`
- **Key Setting**: `LLAMAGUARD_ENABLED=false` (bypass mode)
- **JWT Secret**: Required for API authentication

## API Testing

```bash
# Health check (no auth required)
curl http://localhost:8083/health

# Expected response in bypass mode:
{
  "status": "healthy",
  "llamaguard": "bypass", 
  "redis": "up",
  "mode": "bypass",
  "timestamp": "2025-08-22T00:57:54.931050"
}
```

## Production Deployment

To enable real Llama Guard 4 security for production:

1. **Deploy on x86_64 with GPU**: Requires Linux with NVIDIA GPU
2. **Update environment**: Set `LLAMAGUARD_ENABLED=true` in `.env.security`
3. **Uncomment Llama Guard service**: Restore service in docker-compose
4. **Add HuggingFace token**: Required for model download
5. **Configure GPU resources**: Add GPU allocation to docker-compose

## Development vs Production

| Aspect | Development (Current) | Production (Future) |
|--------|--------------------|-------------------|
| **Security Model** | Bypass (all content safe) | Real Llama Guard 4 AI |
| **Performance** | Instant responses | 200-500ms evaluation |
| **Resources** | Minimal (API + Redis) | GPU + Model (12GB+) |
| **Platform** | ARM64 compatible | Requires x86_64 + GPU |
| **Purpose** | Development/testing | Customer protection |

## Files Created/Modified

- ✅ `docker-compose.security-api.yml` - Simplified security stack
- ✅ `.env.security` - Minimal environment configuration  
- ✅ `src/security/llamaguard-api.py` - Added bypass mode logic
- ✅ `src/security/Dockerfile.llamaguard-api` - Simplified container
- ❌ `scripts/deploy-llamaguard-security.sh` - **DELETED** (was misleading)

## What Was Cleaned Up

- ❌ Complex deployment script with GPU checks
- ❌ Commented-out Llama Guard 4 service definition
- ❌ Unused volumes and config files
- ❌ SSL directories and certificates for development
- ❌ Security logger service (fluent-bit)
- ❌ Model download and caching logic

## Integration with MCPhub

The security API maintains the same interface as production:

- **Endpoint**: `POST /evaluate` with JWT authentication
- **Request**: `{content, customer_id, context_type}`
- **Response**: `{is_safe: true, violations: [], confidence: 1.0}` (bypass mode)
- **MCPhub Integration**: Use security API URL `http://localhost:8083`

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose -f docker-compose.security-api.yml --env-file .env.security logs security-api

# Rebuild if needed
docker-compose -f docker-compose.security-api.yml --env-file .env.security build security-api
```

### Health Check Fails
- Ensure Redis is running: `docker-compose ... ps redis-security`
- Check environment: `cat .env.security`
- Verify bypass mode: Look for "bypass" in health response

### Cannot Connect
- Port conflict: Check if 8083 is available
- Environment loading: Use `--env-file .env.security` flag
- Network issues: Restart Docker Desktop if needed

---

**Development Status**: ✅ **READY FOR MCPHUB INTEGRATION**

This bypass mode setup allows immediate integration testing while maintaining production architecture compatibility.