# Security Setup Guide - AI Agency Platform

**🔒 Critical Security Information for Environment Configuration**

---

## 🚨 **SECURITY ALERT: Never Commit Secrets to Git**

This guide explains how to properly handle environment configuration and secrets in the AI Agency Platform.

### **What We Fixed**

❌ **Previously**: Hardcoded secrets were committed to git  
✅ **Now**: Template files with secure generation process

---

## 🛡️ **Secure Environment Setup Process**

### **Step 1: Use Template Files**

The repository contains template files that are safe to commit:
- ✅ `.env.phase1.template` - Template with placeholders
- ✅ `docker-compose.phase1.template.yml` - Template using environment variables

### **Step 2: Generate Your Environment Files**

Run the Phase 1 initialization script:
```bash
./scripts/phase-1-start.sh
```

This script will:
1. Copy `.env.phase1.template` to `.env.phase1`
2. Generate secure random secrets automatically
3. Replace placeholders with actual values
4. Create `docker-compose.phase1.yml` from template

### **Step 3: Verify Your `.gitignore`**

Ensure these files are **NEVER** committed:
```gitignore
# Environment files - NEVER COMMIT
.env.phase1
docker-compose.phase1.yml

# Data directories - NEVER COMMIT  
data/
```

---

## 🔐 **Security Features Implemented**

### **Automatic Secret Generation**
```bash
# JWT Secret (256-bit random hex)
JWT_SECRET=$(openssl rand -hex 32)

# Database Password (25-character random)  
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
```

### **Environment Variable Usage**
```yaml
# Docker Compose Template
services:
  postgres:
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}  # From .env.phase1
```

### **Cross-Platform Compatibility**
```bash
# macOS and Linux compatible sed commands
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/PLACEHOLDER/$VALUE/" .env.phase1
else
    sed -i "s/PLACEHOLDER/$VALUE/" .env.phase1  
fi
```

---

## 📋 **Security Checklist**

### **Before Starting Development**
- [ ] Run `./scripts/phase-1-start.sh` to generate secure environment files
- [ ] Verify `.env.phase1` contains unique secrets (not template placeholders)
- [ ] Confirm `.env.phase1` is listed in `.gitignore`
- [ ] Check that `data/` directory is excluded from git

### **During Development**
- [ ] Never edit environment files directly - use templates
- [ ] Always use `docker-compose --env-file .env.phase1` commands
- [ ] Regularly verify no secrets are in git history: `git log --grep=password`
- [ ] Use environment variables for all sensitive configuration

### **Production Deployment**
- [ ] Generate new secrets for production (don't reuse development secrets)
- [ ] Use proper secret management (AWS Secrets Manager, Azure Key Vault, etc.)
- [ ] Enable encryption at rest for all databases
- [ ] Set up SSL/TLS certificates for all services

---

## 🔧 **Manual Setup (If Script Fails)**

If the automatic setup script fails, you can manually create the files:

### **1. Create Environment File**
```bash
# Copy template
cp .env.phase1.template .env.phase1

# Generate secure JWT secret
JWT_SECRET=$(openssl rand -hex 32)
echo "Generated JWT Secret: $JWT_SECRET"

# Generate secure database password  
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
echo "Generated DB Password: $DB_PASSWORD"

# Manually edit .env.phase1 and replace:
# YOUR_SECURE_JWT_SECRET_HERE -> your generated JWT secret
# YOUR_DATABASE_PASSWORD -> your generated database password
```

### **2. Create Docker Compose File**
```bash
# Copy template
cp docker-compose.phase1.template.yml docker-compose.phase1.yml

# The template uses environment variables, so no editing needed
```

### **3. Start Services**
```bash
# Start with environment file
docker-compose --env-file .env.phase1 -f docker-compose.phase1.yml up -d
```

---

## 🚨 **What To Do If Secrets Were Committed**

If you accidentally commit secrets to git:

### **1. Immediate Actions**
```bash
# Remove from git index
git rm --cached .env.phase1 docker-compose.phase1.yml

# Add to gitignore if not already there
echo ".env.phase1" >> .gitignore
echo "docker-compose.phase1.yml" >> .gitignore

# Commit the removal
git add .gitignore
git commit -m "Remove sensitive files and update gitignore"
```

### **2. Generate New Secrets**
```bash
# Generate new secrets (old ones are compromised)
openssl rand -hex 32  # New JWT secret
openssl rand -base64 32 | tr -d "=+/" | cut -c1-25  # New DB password

# Update your .env.phase1 with new secrets
```

### **3. Clean Git History (Advanced)**
```bash
# WARNING: This rewrites git history
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env.phase1 docker-compose.phase1.yml' \
  --prune-empty --tag-name-filter cat -- --all

# Force push (if working on personal repo)
git push origin --force --all
```

---

## 🔍 **Security Validation Commands**

### **Check for Secrets in Git**
```bash
# Search for potential secrets in git history
git log --grep=password --grep=secret --grep=key -i

# Search for patterns in current files
grep -r "password\|secret\|key" . --exclude-dir=.git --exclude-dir=node_modules
```

### **Validate Environment Setup**
```bash
# Check that environment file exists and has real secrets
if [ -f ".env.phase1" ]; then
    if grep -q "YOUR_SECURE_JWT_SECRET_HERE" .env.phase1; then
        echo "❌ Environment file still has template placeholders!"
    else
        echo "✅ Environment file has been configured"
    fi
else
    echo "❌ Environment file not found - run ./scripts/phase-1-start.sh"
fi
```

### **Database Connection Test**
```bash
# Test database connection with environment variables
source .env.phase1
docker exec -it postgres psql "$DATABASE_URL" -c "SELECT version();"
```

---

## 📚 **Additional Security Resources**

### **Secret Management Best Practices**
- Use different secrets for development, staging, and production
- Rotate secrets regularly (at least quarterly)
- Monitor for secret exposure in logs and error messages
- Use dedicated secret management services in production

### **Git Security**
- Enable GitHub secret scanning for your repositories
- Use `.gitignore` templates for different project types
- Regular security audits of git history
- Consider using `git-secrets` tool for additional protection

### **Docker Security**
- Don't build images with secrets in environment variables
- Use Docker secrets in swarm mode or Kubernetes secrets
- Scan images for vulnerabilities regularly
- Use minimal base images (alpine) when possible

---

**🎯 Remember: Security is a process, not a destination. Regularly review and update your security practices!**