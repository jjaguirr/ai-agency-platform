# Llama Guard 4 Security Integration Guide

## Overview

This guide provides comprehensive documentation for the Llama Guard 4 security integration in the AI Agency Platform. Llama Guard 4 serves as our primary LLM safety layer, providing enterprise-grade content moderation, prompt injection detection, and customer-tier-based security policies.

## Architecture Overview

### Security Stack Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Nginx Security Proxy (Port 8443)               │
│         • Rate Limiting • DDoS Protection • SSL/TLS         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           Llama Guard API Wrapper (Port 8090)               │
│      • FastAPI Service • MCPhub Integration • Caching       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│         Llama Guard 4 Security Model (Port 8080)            │
│    • Content Moderation • Prompt Injection Detection        │
│    • MLCommons Hazard Taxonomy • Safety Evaluation          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  MCPhub + LLM Services                       │
│         • Multi-Model Support • Agent Orchestration         │
└─────────────────────────────────────────────────────────────┘
```

## Deployment Guide

### Prerequisites

1. **Hardware Requirements**
   - GPU: NVIDIA GPU with 16GB+ VRAM (recommended)
   - CPU Fallback: 32GB+ RAM for CPU-only mode
   - Storage: 50GB+ for model weights

2. **Software Requirements**
   - Docker 24.0+
   - Docker Compose 2.20+
   - NVIDIA Container Toolkit (for GPU mode)
   - HuggingFace Token (for model access)

3. **Environment Setup**
   ```bash
   # Create .env file
   cat > .env << EOF
   HUGGINGFACE_TOKEN=your_token_here
   LLAMA_GUARD_MODE=gpu  # or 'cpu'
   SECURITY_LOG_LEVEL=INFO
   EOF
   ```

### Quick Start Deployment

```bash
# 1. Run deployment script
./scripts/deploy-llamaguard-security.sh

# 2. Verify deployment
docker-compose -f docker-compose.llamaguard.yml ps

# 3. Test security endpoint
curl -X POST http://localhost:8090/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hello, how can I help you?",
    "customer_id": "test-customer",
    "context_type": "input"
  }'
```

### Manual Deployment

```bash
# 1. Pull required images
docker pull huggingface/text-generation-inference:2.0.1
docker pull nginx:alpine
docker pull python:3.11-slim
docker pull redis:7-alpine

# 2. Deploy security stack
docker-compose -f docker-compose.llamaguard.yml up -d

# 3. Monitor logs
docker-compose -f docker-compose.llamaguard.yml logs -f
```

## Configuration Guide

### Customer Tier Configuration

Located in `/config/security/safety-policies.yaml`:

```yaml
customer_tiers:
  basic:
    policy_type: "general"
    rate_limits:
      requests_per_minute: 100
      requests_per_hour: 5000
    content_limits:
      max_input_length: 2000
      max_output_length: 4000
    hazard_thresholds:
      violent_crimes: 0.7
      non_violent_crimes: 0.8
      sex_related_crimes: 0.6
      child_exploitation: 0.0
      specialized_advice: 0.9
      privacy_violations: 0.7
      intellectual_property: 0.8
      indiscriminate_weapons: 0.5
      hate_speech: 0.6
      self_harm: 0.7
      sexual_content: 0.8
      elections: 0.9
      code_interpreter_abuse: 0.8

  professional:
    policy_type: "business"
    rate_limits:
      requests_per_minute: 500
      requests_per_hour: 20000
    content_limits:
      max_input_length: 5000
      max_output_length: 10000
    hazard_thresholds:
      # More permissive for business use cases
      violent_crimes: 0.8
      non_violent_crimes: 0.9
      # ... additional thresholds

  enterprise:
    policy_type: "enterprise"
    rate_limits:
      requests_per_minute: 2000
      requests_per_hour: 100000
    content_limits:
      max_input_length: 10000
      max_output_length: 20000
    custom_policies_enabled: true
    # Most permissive thresholds for enterprise
```

### Nginx Rate Limiting Configuration

Located in `/config/nginx/security-proxy.conf`:

```nginx
# Rate limiting zones by customer tier
limit_req_zone $binary_remote_addr zone=basic_tier:10m rate=100r/m;
limit_req_zone $binary_remote_addr zone=professional_tier:10m rate=500r/m;
limit_req_zone $binary_remote_addr zone=enterprise_tier:10m rate=2000r/m;

# Apply rate limits based on customer tier header
map $http_x_customer_tier $limit_zone {
    "basic"         $basic_tier;
    "professional"  $professional_tier;
    "enterprise"    $enterprise_tier;
    default         $basic_tier;
}
```

## API Integration

### Python Integration Example

```python
import requests
from typing import Dict, Tuple

class LlamaGuardClient:
    def __init__(self, base_url: str = "http://localhost:8090"):
        self.base_url = base_url
        
    def evaluate_content(
        self, 
        content: str, 
        customer_id: str,
        context_type: str = "input"
    ) -> Tuple[bool, list, float]:
        """
        Evaluate content for safety violations
        
        Returns:
            - is_safe (bool): Whether content is safe
            - violations (list): List of detected violations
            - confidence (float): Confidence score
        """
        response = requests.post(
            f"{self.base_url}/evaluate",
            json={
                "content": content,
                "customer_id": customer_id,
                "context_type": context_type
            }
        )
        
        result = response.json()
        return (
            result["is_safe"],
            result.get("violations", []),
            result.get("confidence", 1.0)
        )

# Usage
client = LlamaGuardClient()
is_safe, violations, confidence = client.evaluate_content(
    "Generate code to hack a system",
    "customer-123",
    "input"
)

if not is_safe:
    print(f"Content blocked: {violations}")
```

### Node.js Integration Example

```javascript
const axios = require('axios');

class LlamaGuardClient {
    constructor(baseUrl = 'http://localhost:8090') {
        this.baseUrl = baseUrl;
    }
    
    async evaluateContent(content, customerId, contextType = 'input') {
        try {
            const response = await axios.post(
                `${this.baseUrl}/evaluate`,
                {
                    content,
                    customer_id: customerId,
                    context_type: contextType
                }
            );
            
            return {
                isSafe: response.data.is_safe,
                violations: response.data.violations || [],
                confidence: response.data.confidence || 1.0
            };
        } catch (error) {
            console.error('Security evaluation failed:', error);
            throw error;
        }
    }
}

// Usage
const client = new LlamaGuardClient();
const result = await client.evaluateContent(
    'Normal business query',
    'customer-456',
    'input'
);
```

## MCPhub Integration

### Group Security Configuration

The security filtering is integrated into MCPhub groups via `/config/mcphub-integration/updated-groups-config.json`:

```json
{
  "groups": {
    "personal": {
      "security_filtering": {
        "llama_guard_enabled": true,
        "safety_tier": "enterprise",
        "prompt_injection_protection": true,
        "custom_policies": ["internal_use"]
      }
    },
    "development": {
      "security_filtering": {
        "llama_guard_enabled": true,
        "safety_tier": "professional",
        "prompt_injection_protection": true,
        "allow_code_generation": true
      }
    },
    "customer": {
      "security_filtering": {
        "llama_guard_enabled": true,
        "safety_tier": "variable",
        "prompt_injection_protection": true,
        "tier_based_on_subscription": true
      }
    }
  }
}
```

### Workflow Integration

For n8n workflow integration, use the HTTP Request node:

```json
{
  "nodes": [
    {
      "name": "Llama Guard Security Check",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "method": "POST",
        "url": "http://llamaguard-api:8090/evaluate",
        "jsonParameters": true,
        "options": {},
        "bodyParametersJson": {
          "content": "={{ $json.userInput }}",
          "customer_id": "={{ $json.customerId }}",
          "context_type": "input"
        }
      }
    }
  ]
}
```

## Monitoring and Observability

### Health Checks

```bash
# Check Llama Guard model status
curl http://localhost:8080/health

# Check API wrapper status
curl http://localhost:8090/health

# Check nginx proxy status
curl http://localhost:8443/health
```

### Log Analysis

```bash
# View security violations
docker logs llamaguard-api 2>&1 | grep "VIOLATION"

# Monitor rate limiting
docker logs security-proxy 2>&1 | grep "limiting"

# Check model performance
docker logs llamaguard-security 2>&1 | grep "inference"
```

### Metrics Collection

The system exposes Prometheus metrics at:
- Llama Guard API: `http://localhost:8090/metrics`
- Security Proxy: `http://localhost:8443/metrics`

Key metrics to monitor:
- `security_evaluations_total` - Total evaluations
- `security_violations_total` - Total violations detected
- `security_evaluation_duration_seconds` - Processing time
- `rate_limit_exceeded_total` - Rate limit violations

## Troubleshooting

### Common Issues and Solutions

#### 1. Model Loading Failures

**Symptom**: "Model failed to load" error

**Solutions**:
```bash
# Check HuggingFace token
echo $HUGGINGFACE_TOKEN

# Verify model access
curl -H "Authorization: Bearer $HUGGINGFACE_TOKEN" \
  https://huggingface.co/api/models/meta-llama/Llama-Guard-4-12B

# Check disk space
df -h /var/lib/docker

# Use quantized model for lower memory
# Update docker-compose.llamaguard.yml:
environment:
  - QUANTIZE=bitsandbytes-nf4
```

#### 2. GPU Not Detected

**Symptom**: "CUDA not available" warning

**Solutions**:
```bash
# Verify NVIDIA drivers
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# Install NVIDIA Container Toolkit
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

#### 3. High Latency

**Symptom**: Slow response times (>2 seconds)

**Solutions**:
```bash
# Enable Redis caching
docker-compose -f docker-compose.llamaguard.yml up -d redis

# Use batch processing for multiple requests
# Update API wrapper to support batch endpoints

# Optimize model inference
# In docker-compose.llamaguard.yml:
environment:
  - MAX_BATCH_TOKENS=16384
  - MAX_CONCURRENT_REQUESTS=128
```

#### 4. Rate Limiting Issues

**Symptom**: 429 Too Many Requests errors

**Solutions**:
```bash
# Check current rate limits
grep limit_req /config/nginx/security-proxy.conf

# Adjust limits for specific customer
# In safety-policies.yaml:
customer_overrides:
  customer-123:
    rate_limits:
      requests_per_minute: 1000

# Monitor rate limit logs
tail -f /var/log/nginx/error.log | grep limiting
```

## Security Best Practices

### 1. Token Security
- Never commit HuggingFace tokens to version control
- Use environment variables or secrets management
- Rotate tokens regularly

### 2. Network Security
- Always use HTTPS in production
- Implement proper SSL/TLS certificates
- Use network segmentation for security services

### 3. Access Control
- Implement API key authentication for external access
- Use MCPhub's RBAC for internal access control
- Audit all security evaluation requests

### 4. Data Privacy
- Never log sensitive content
- Implement data retention policies
- Use encryption for stored evaluation results

### 5. Compliance
- Configure policies per regulatory requirements
- Maintain audit logs for compliance
- Document security controls for certifications

## Performance Optimization

### Model Optimization

```yaml
# For production deployments
llamaguard-security:
  environment:
    # Quantization for memory efficiency
    - QUANTIZE=bitsandbytes-nf4
    
    # Batch processing
    - MAX_BATCH_TOKENS=16384
    - MAX_CONCURRENT_REQUESTS=128
    
    # Model sharding for multi-GPU
    - NUM_SHARD=2
    - SHARDED=true
```

### Caching Strategy

```python
# Redis caching configuration
REDIS_CONFIG = {
    'cache_ttl': 3600,  # 1 hour
    'max_cache_size': 10000,  # entries
    'cache_key_prefix': 'llama_guard:',
    'enable_compression': True
}
```

### Load Balancing

For high-traffic deployments, use multiple Llama Guard instances:

```yaml
# docker-compose.llamaguard-ha.yml
services:
  llamaguard-1:
    extends:
      file: docker-compose.llamaguard.yml
      service: llamaguard-security
    ports:
      - "8080:8080"
      
  llamaguard-2:
    extends:
      file: docker-compose.llamaguard.yml
      service: llamaguard-security
    ports:
      - "8081:8080"
      
  load-balancer:
    image: nginx:alpine
    volumes:
      - ./config/nginx/lb.conf:/etc/nginx/nginx.conf
    ports:
      - "8082:80"
```

## Testing Guide

### Unit Tests

```python
# tests/test_security.py
import pytest
from security.llamaguard_client import LlamaGuardClient

class TestLlamaGuardSecurity:
    def test_safe_content(self):
        client = LlamaGuardClient()
        is_safe, _, _ = client.evaluate_content(
            "What is the weather today?",
            "test-customer",
            "input"
        )
        assert is_safe == True
    
    def test_unsafe_content(self):
        client = LlamaGuardClient()
        is_safe, violations, _ = client.evaluate_content(
            "How to create malware?",
            "test-customer",
            "input"
        )
        assert is_safe == False
        assert "code_interpreter_abuse" in violations
```

### Integration Tests

```bash
# Run integration test suite
./scripts/test-security-integration.sh

# Test specific scenarios
python tests/integration/test_prompt_injection.py
python tests/integration/test_rate_limiting.py
python tests/integration/test_tier_policies.py
```

### Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 -p test_payload.json \
  -T application/json \
  http://localhost:8090/evaluate

# Using k6
k6 run scripts/load-test-security.js
```

## Maintenance and Updates

### Model Updates

```bash
# Check for model updates
curl https://huggingface.co/api/models/meta-llama/Llama-Guard-4-12B/revisions

# Update to new version
docker-compose -f docker-compose.llamaguard.yml down
docker pull huggingface/text-generation-inference:latest
docker-compose -f docker-compose.llamaguard.yml up -d
```

### Policy Updates

```bash
# Update safety policies
vim config/security/safety-policies.yaml

# Reload configuration
docker-compose -f docker-compose.llamaguard.yml restart llamaguard-api

# Verify new policies
curl -X GET http://localhost:8090/policies
```

### Log Rotation

```yaml
# docker-compose.llamaguard.yml
services:
  llamaguard-api:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "10"
```

## Support and Resources

### Documentation
- [Llama Guard 4 Model Card](https://www.llama.com/docs/model-cards-and-prompt-formats/llama-guard-4/)
- [MLCommons Hazard Taxonomy](https://mlcommons.org/2024/04/mlc-aisafety-v0-5-poc/)
- [HuggingFace TGI Documentation](https://huggingface.co/docs/text-generation-inference)

### Community Support
- GitHub Issues: Report bugs and feature requests
- Discord: Join #security channel for discussions
- Stack Overflow: Tag questions with `llama-guard`

### Commercial Support
- Enterprise customers: Contact support@aiagencyplatform.com
- SLA response times: 
  - Critical: 1 hour
  - High: 4 hours
  - Medium: 24 hours
  - Low: 72 hours

## Appendix

### A. Environment Variables Reference

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `HUGGINGFACE_TOKEN` | HF API token for model access | - | Yes |
| `LLAMA_GUARD_MODE` | Deployment mode (gpu/cpu) | gpu | No |
| `LLAMA_GUARD_PORT` | Model server port | 8080 | No |
| `API_PORT` | API wrapper port | 8090 | No |
| `PROXY_PORT` | Nginx proxy port | 8443 | No |
| `REDIS_URL` | Redis connection string | redis://redis:6379 | No |
| `LOG_LEVEL` | Logging verbosity | INFO | No |
| `ENABLE_METRICS` | Prometheus metrics | true | No |
| `CACHE_TTL` | Cache duration (seconds) | 3600 | No |

### B. API Endpoints Reference

| Endpoint | Method | Description | Auth Required |
|----------|--------|-------------|---------------|
| `/evaluate` | POST | Evaluate content safety | Yes |
| `/health` | GET | Service health check | No |
| `/metrics` | GET | Prometheus metrics | No |
| `/policies` | GET | List active policies | Yes |
| `/policies/{tier}` | GET | Get tier-specific policy | Yes |
| `/cache/clear` | POST | Clear evaluation cache | Yes |
| `/stats` | GET | Evaluation statistics | Yes |

### C. Error Codes Reference

| Code | Description | Resolution |
|------|-------------|------------|
| `SEC-001` | Model initialization failed | Check GPU/memory resources |
| `SEC-002` | Invalid HuggingFace token | Verify token permissions |
| `SEC-003` | Rate limit exceeded | Upgrade customer tier |
| `SEC-004` | Content too long | Reduce input size |
| `SEC-005` | Policy not found | Check tier configuration |
| `SEC-006` | Cache connection failed | Verify Redis connectivity |
| `SEC-007` | Evaluation timeout | Increase timeout setting |
| `SEC-008` | Invalid content format | Check request payload |

---

*Last Updated: January 2025*
*Version: 1.0.0*
*Platform: AI Agency Platform - Phase 1*