# AI Agency Platform - Vault Policies for Secret Management
# Comprehensive Vault policies for production secret management

# ==============================================
# AI Agency Platform Production Policy
# ==============================================

# Production Database Policy
path "ai-agency/production/database/*" {
  capabilities = ["read", "list"]
}

# Production Redis Policy
path "ai-agency/production/redis/*" {
  capabilities = ["read", "list"]
}

# Production Qdrant Policy
path "ai-agency/production/qdrant/*" {
  capabilities = ["read", "list"]
}

# Production Neo4j Policy
path "ai-agency/production/neo4j/*" {
  capabilities = ["read", "list"]
}

# Production AI Providers Policy
path "ai-agency/production/ai-providers/*" {
  capabilities = ["read", "list"]
}

# Production WhatsApp Policy
path "ai-agency/production/whatsapp/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Production Security Policy
path "ai-agency/production/security/*" {
  capabilities = ["read", "list"]
}

# Production Configuration Policy
path "ai-agency/production/config" {
  capabilities = ["read", "list"]
}

# Customer-specific secrets policy (read-only for application)
path "customer/production/data/*" {
  capabilities = ["read", "list"]
}

# ==============================================
# AI Agency Platform Staging Policy
# ==============================================

# Staging Database Policy
path "ai-agency/staging/database/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging Redis Policy
path "ai-agency/staging/redis/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging Qdrant Policy
path "ai-agency/staging/qdrant/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging Neo4j Policy
path "ai-agency/staging/neo4j/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging AI Providers Policy
path "ai-agency/staging/ai-providers/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging WhatsApp Policy
path "ai-agency/staging/whatsapp/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging Security Policy
path "ai-agency/staging/security/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging Configuration Policy
path "ai-agency/staging/config" {
  capabilities = ["read", "list", "create", "update"]
}

# Staging Customer-specific secrets policy
path "customer/staging/data/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# AI Agency Platform Development Policy
# ==============================================

# Development Database Policy
path "ai-agency/development/database/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development Redis Policy
path "ai-agency/development/redis/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development Qdrant Policy
path "ai-agency/development/qdrant/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development Neo4j Policy
path "ai-agency/development/neo4j/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development AI Providers Policy
path "ai-agency/development/ai-providers/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development WhatsApp Policy
path "ai-agency/development/whatsapp/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development Security Policy
path "ai-agency/development/security/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development Configuration Policy
path "ai-agency/development/config" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Development Customer-specific secrets policy
path "customer/development/data/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# Admin Policy for Infrastructure Management
# ==============================================

# Admin Database Policy
path "ai-agency/+/database/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin Redis Policy
path "ai-agency/+/redis/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin Qdrant Policy
path "ai-agency/+/qdrant/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin Neo4j Policy
path "ai-agency/+/neo4j/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin AI Providers Policy
path "ai-agency/+/ai-providers/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin WhatsApp Policy
path "ai-agency/+/whatsapp/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin Security Policy
path "ai-agency/+/security/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin Configuration Policy
path "ai-agency/+/config" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Admin Customer Management Policy
path "customer/+/data/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# Kubernetes Authentication Policy
# ==============================================

# Kubernetes authentication mount
path "auth/kubernetes/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Token management
path "auth/token/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# Transit Engine Policy for Encryption
# ==============================================

# Transit engine for encryption operations
path "transit/encrypt/ai-agency-production" {
  capabilities = ["update"]
}

path "transit/decrypt/ai-agency-production" {
  capabilities = ["update"]
}

path "transit/encrypt/ai-agency-staging" {
  capabilities = ["update"]
}

path "transit/decrypt/ai-agency-staging" {
  capabilities = ["update"]
}

path "transit/encrypt/ai-agency-development" {
  capabilities = ["update"]
}

path "transit/decrypt/ai-agency-development" {
  capabilities = ["update"]
}

# ==============================================
# PKI Engine Policy for TLS Certificates
# ==============================================

# Certificate issuance and management
path "pki/issue/ai-agency-production" {
  capabilities = ["create", "update"]
}

path "pki/cert/ca" {
  capabilities = ["read"]
}

path "pki/revoke" {
  capabilities = ["create", "update"]
}

# ==============================================
# Audit and Monitoring Policies
# ==============================================

# Syslog for audit logging
path "syslog/*" {
  capabilities = ["create", "update"]
}

# Metrics collection
path "metrics/*" {
  capabilities = ["read"]
}

# ==============================================
# Backup and Recovery Policies
# ==============================================

# AWS integration for backups
path "aws/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Database backup policies
path "database/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# Emergency Access Policy
# ==============================================

# Emergency root access (highly restricted)
path "*" {
  capabilities = ["deny"]
}

# Emergency token creation (break glass procedure)
path "auth/token/create-orphan" {
  capabilities = ["update"]
}

# ==============================================
# Compliance and Audit Policies
# ==============================================

# Audit device for compliance logging
path "audit/*" {
  capabilities = ["read", "list"]
}

# SSH secrets for bastion access
path "ssh/*" {
  capabilities = ["read", "list", "create", "delete"]
}

# ==============================================
# Customer Provisioning Policy
# ==============================================

# Customer-specific secret creation
path "customer/+/data/+/" {
  capabilities = ["create", "read", "update", "delete"]
}

# Customer provisioning workflow
path "provisioning/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# Monitoring and Alerting Policies
# ==============================================

# Prometheus metrics collection
path "prometheus/*" {
  capabilities = ["read"]
}

# AlertManager configuration
path "alertmanager/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# Vault Agent Policy for Kubernetes
# ==============================================

# Agent token renewal
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Agent lookup
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# ==============================================
# Database Migration Policy
# ==============================================

# Migration secret management
path "migration/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Schema management
path "schema/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# Feature Flag Management Policy
# ==============================================

# Feature flag configuration
path "feature-flags/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# A/B testing configuration
path "ab-testing/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# API Rate Limiting Policy
# ==============================================

# Rate limiting configuration
path "rate-limiting/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Customer tier management
path "customer-tiers/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# ==============================================
# Logging and Analytics Policy
# ==============================================

# Log aggregation configuration
path "logging/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Analytics data collection
path "analytics/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# Security Scanning Policy
# ==============================================

# Vulnerability scanning
path "security-scan/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Compliance scanning
path "compliance-scan/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# Disaster Recovery Policy
# ==============================================

# DR configuration management
path "disaster-recovery/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Backup verification
path "backup-verification/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# Cost Optimization Policy
# ==============================================

# Resource optimization
path "cost-optimization/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}

# Budget management
path "budget/*" {
  capabilities = ["read", "list", "create", "update"]
}

# ==============================================
# Documentation Policy
# ==============================================

# API documentation secrets
path "documentation/*" {
  capabilities = ["read", "list", "create", "update"]
}

# Client credential management
path "client-credentials/*" {
  capabilities = ["read", "list", "create", "update", "delete"]
}