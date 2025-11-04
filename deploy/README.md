# AI Agency Platform - Deployment Configuration Guide

## Overview

This deployment configuration provides a comprehensive, production-ready infrastructure setup for the AI Agency Platform with multi-tenant customer isolation, enterprise-grade security, and scalable architecture.

## Architecture Components

### 1. Environment Configurations (`deploy/config/`)
- **production.env**: Production environment with Vault integration
- **staging.env**: Staging environment for testing
- **development.env**: Local development configuration

### 2. Docker Compose (`docker-compose.production.yml`)
- Per-customer isolated services
- Production-grade monitoring stack
- Security services integration
- Comprehensive health checks

### 3. Kubernetes Manifests (`deploy/kubernetes/`)
- **shared-infrastructure.yaml**: Shared database and cache clusters
- **production/ai-agency-application.yaml**: Customer-specific application deployments
- **production/monitoring-stack.yaml**: Prometheus, Grafana, Jaeger, Loki, Fluent Bit
- **production/security-vault.yaml**: RBAC, Network Policies, Security Context

### 4. Infrastructure as Code (`deploy/terraform/`)
- **main.tf**: Complete AWS infrastructure provisioning
- **variables.tf**: Configurable deployment parameters

### 5. Security & Secrets (`deploy/config/`)
- **vault-policies.hcl**: Comprehensive Vault access policies
- **security-policies.json**: Enterprise security configuration

## Key Features

### 🔐 Security First
- **Vault Integration**: All secrets managed through HashiCorp Vault
- **Customer Isolation**: Complete data and network isolation per customer
- **RBAC**: Role-based access control with least privilege
- **Encryption**: AES-256-GCM encryption for data at rest and in transit
- **Compliance**: SOC2, GDPR, CCPA compliance frameworks

### 🚀 Production Ready
- **High Availability**: Multi-AZ deployment with automatic failover
- **Auto-scaling**: Horizontal and vertical scaling based on demand
- **Monitoring**: Comprehensive observability with Prometheus/Grafana
- **Backup**: Automated daily backups with cross-region replication
- **Disaster Recovery**: RTO 4 hours, RPO 15 minutes

### 📊 Multi-Tenant Architecture
- **Per-Customer Stacks**: Isolated infrastructure per customer
- **Resource Management**: Tier-based resource allocation
- **Network Isolation**: Separate VPCs and subnets per customer
- **Data Separation**: Individual databases and storage per customer

## Quick Start

### 1. Prerequisites
```bash
# Install required tools
terraform >= 1.5.0
kubectl >= 1.28
helm >= 3.11
vault >= 1.13

# AWS CLI configured with appropriate permissions
aws configure

# Docker and Docker Compose
docker >= 24.0
docker-compose >= 2.0
```

### 2. Infrastructure Deployment
```bash
# Navigate to terraform directory
cd deploy/terraform

# Initialize Terraform
terraform init

# Plan deployment
terraform plan -var-file="production.tfvars"

# Deploy infrastructure
terraform apply -var-file="production.tfvars"
```

### 3. Kubernetes Setup
```bash
# Configure kubectl
aws eks update-kubeconfig --name ai-agency-production

# Deploy shared infrastructure
kubectl apply -f deploy/kubernetes/shared-infrastructure.yaml

# Deploy monitoring stack
kubectl apply -f deploy/kubernetes/production/monitoring-stack.yaml

# Deploy security policies
kubectl apply -f deploy/kubernetes/production/security-vault.yaml
```

### 4. Vault Configuration
```bash
# Initialize and unseal Vault (if not already done)
vault operator init
vault operator unseal

# Enable required secrets engines
vault secrets enable -path=ai-agency/production/database kv-v2
vault secrets enable -path=ai-agency/production/redis kv-v2
vault secrets enable -path=ai-agency/production/qdrant kv-v2
vault secrets enable -path=ai-agency/production/neo4j kv-v2
vault secrets enable -path=ai-agency/production/ai-providers kv-v2
vault secrets enable -path=ai-agency/production/whatsapp kv-v2
vault secrets enable -path=ai-agency/production/security kv-v2

# Configure Kubernetes authentication
vault auth enable kubernetes

# Create policies
vault policy write ai-agency-production deploy/config/vault-policies.hcl

# Create roles for service accounts
vault write auth/kubernetes/role/ai-agency-production-role \
    bound_service_account_names=ai-agency-production-sa \
    bound_service_account_namespaces=ai-agency-production \
    policies=ai-agency-production \
    ttl=24h
```

### 5. Customer Provisioning
```bash
# Use the customer provisioning orchestrator
python infrastructure/provisioning/customer-provisioning.py \
    --customer-id customer_12345 \
    --tier professional \
    --environment production
```

## Configuration Details

### Environment Variables
All sensitive configuration is managed through Vault. Key variables include:

- **Database**: PostgreSQL connection strings and credentials
- **Redis**: Cache and session storage configuration
- **AI Providers**: API keys for OpenAI, Anthropic, Google AI
- **WhatsApp**: Meta Business API tokens and secrets
- **Security**: JWT secrets, encryption keys, SSL certificates

### Service Ports
Each customer gets dedicated port ranges:
- **MCP Server**: 30000-30999
- **PostgreSQL**: 31000-31999
- **Redis**: 32000-32999
- **Qdrant**: 33000-33999
- **Neo4j**: 34000-34999
- **Monitoring**: 35000-35999

### Resource Limits
Tier-based resource allocation:
- **Starter**: 1GB RAM, 0.5 CPU, 100 RPM
- **Professional**: 2GB RAM, 1.0 CPU, 1000 RPM
- **Enterprise**: 4GB RAM, 2.0 CPU, 10000 RPM

## Monitoring & Observability

### Metrics Collection
- **Prometheus**: Application and infrastructure metrics
- **Grafana**: Visualization and alerting dashboards
- **Jaeger**: Distributed tracing for request tracking
- **Loki**: Centralized log aggregation

### Key Dashboards
1. **Customer Performance**: Per-customer resource usage and performance
2. **System Health**: Overall platform health and availability
3. **Security Events**: Authentication and authorization metrics
4. **Cost Analytics**: Resource consumption and cost tracking

### Alerting
- **SLA Monitoring**: Response time and availability alerts
- **Resource Thresholds**: CPU, memory, and storage alerts
- **Security Events**: Failed logins and suspicious activity
- **Business Metrics**: Customer engagement and usage patterns

## Security Considerations

### Data Protection
- All data encrypted at rest using AES-256-GCM
- TLS 1.3 for all network communications
- Customer data isolation at network, compute, and data layers
- Regular security audits and penetration testing

### Access Control
- Multi-factor authentication required for all access
- Role-based access control with principle of least privilege
- Automated credential rotation and management
- Comprehensive audit logging for compliance

### Compliance
- **SOC2**: Security, availability, and confidentiality controls
- **GDPR**: Data protection and privacy compliance
- **CCPA**: California consumer privacy rights
- **ISO27001**: Information security management standards

## Troubleshooting

### Common Issues

1. **Vault Token Expiry**
   ```bash
   # Renew token
   vault token renew

   # Check token status
   vault token lookup
   ```

2. **Service Health Checks Failing**
   ```bash
   # Check pod status
   kubectl get pods -n ai-agency-production

   # Check service logs
   kubectl logs -f deployment/ai-agency-mcp-server
   ```

3. **Resource Constraints**
   ```bash
   # Check resource usage
   kubectl top nodes
   kubectl top pods -n ai-agency-production

   # Scale resources if needed
   kubectl scale deployment ai-agency-mcp-server --replicas=5
   ```

### Debug Commands
```bash
# Check all resources in namespace
kubectl get all -n ai-agency-production

# Check persistent volumes
kubectl get pv,pvc -n ai-agency-production

# Check network policies
kubectl get networkpolicies -n ai-agency-production

# Check RBAC
kubectl get roles,rolebindings,serviceaccounts -n ai-agency-production
```

## Maintenance

### Regular Tasks

1. **Daily**
   - Monitor system health and performance
   - Check backup completion status
   - Review security events and alerts

2. **Weekly**
   - Review resource utilization trends
   - Update SSL certificates if needed
   - Test disaster recovery procedures

3. **Monthly**
   - Perform full backup restoration test
   - Review and update security policies
   - Analyze cost optimization opportunities

4. **Quarterly**
   - Conduct security assessment and penetration testing
   - Review compliance requirements
   - Plan capacity scaling based on growth

### Update Procedures

1. **Application Updates**
   ```bash
   # Update Docker image
   kubectl set image deployment/ai-agency-mcp-server mcp-server=ai-agency-mcp-server:v2.0.0

   # Rolling restart for configuration changes
   kubectl rollout restart deployment/ai-agency-mcp-server
   ```

2. **Infrastructure Updates**
   ```bash
   # Plan infrastructure changes
   terraform plan -var-file="production.tfvars"

   # Apply changes with approval
   terraform apply -var-file="production.tfvars"
   ```

## Support

For technical support and questions:
- **Email**: devops@ai-agency.com
- **Slack**: #platform-engineering
- **Documentation**: https://docs.ai-agency.com
- **Runbooks**: https://runbooks.ai-agency.com

## Contributing

1. All changes must be tested in staging environment first
2. Security review required for all changes
3. Update documentation for configuration changes
4. Follow semantic versioning for releases

---

**Last Updated**: October 2024
**Version**: 1.0.0
**Environment**: Production