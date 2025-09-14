# Production Deployment Guide
## Meta-Compliant WhatsApp Webhook Service

This comprehensive guide covers the complete production deployment process for the Meta-compliant WhatsApp webhook service on DigitalOcean App Platform.

## 📋 Pre-Deployment Checklist

### Meta Developer Console Setup
- [ ] Meta Business Account created and verified
- [ ] Meta app created with appropriate permissions
- [ ] WhatsApp Business API access configured
- [ ] Embedded Signup configuration created
- [ ] App domains configured (webhook.aiagency.platform)
- [ ] Webhook URLs configured in Meta console
- [ ] App review submitted (if required)

### Environment Configuration
- [ ] Production environment file configured (`.env.production.webhook`)
- [ ] All secrets generated and stored securely
- [ ] Encryption keys generated (32+ character AES keys)
- [ ] Meta app credentials obtained and configured
- [ ] WhatsApp Business API tokens configured
- [ ] Redis connection string configured

### Security Requirements
- [ ] SSL certificate configured for webhook domain
- [ ] IP allowlisting configured for Meta server IPs
- [ ] Webhook signature validation enabled
- [ ] Security headers configured
- [ ] Rate limiting enabled
- [ ] Production security mode enabled

### Infrastructure Readiness
- [ ] DigitalOcean account with App Platform access
- [ ] doctl CLI installed and authenticated
- [ ] Custom domain configured (optional)
- [ ] Managed Redis cluster provisioned
- [ ] Monitoring and alerting configured

## 🚀 Deployment Process

### Step 1: Environment Preparation

1. **Configure Production Environment**
   ```bash
   # Copy template and customize
   cp .env.production.template .env.production.webhook

   # Edit with production values
   # ALL VALUES MARKED "your-*-here" MUST BE REPLACED
   vim .env.production.webhook
   ```

2. **Generate Secure Secrets**
   ```bash
   # Generate encryption key (32 characters)
   openssl rand -hex 16

   # Generate JWT secret (64 characters)
   openssl rand -hex 32

   # Generate webhook secrets (32 characters)
   openssl rand -hex 16
   ```

3. **Validate Configuration**
   ```bash
   # Test configuration parsing
   python -c "
   from dotenv import load_dotenv
   load_dotenv('.env.production.webhook')
   import os
   print('✅ Configuration loaded successfully')
   print(f'Meta App ID: {os.getenv('META_APP_ID')[:8]}...')
   print(f'Environment: {os.getenv('ENVIRONMENT')}')
   "
   ```

### Step 2: Pre-Deployment Testing

1. **Run Local Tests**
   ```bash
   # Create test environment
   python -m venv test_env
   source test_env/bin/activate
   pip install -r requirements-webhook.txt pytest

   # Run webhook-specific tests
   python -m pytest tests/test_webhook/ -v

   # Run security tests
   python -m pytest tests/test_security/ -v
   ```

2. **Docker Build Test** (Optional but Recommended)
   ```bash
   # Build production image
   docker build -f src/webhook/Dockerfile.production -t webhook-test:latest .

   # Test container startup
   docker run -d -p 8001:8000 \
     --env-file .env.production.webhook \
     webhook-test:latest

   # Test health endpoint
   curl -f http://localhost:8001/health

   # Cleanup
   docker stop $(docker ps -q --filter ancestor=webhook-test:latest)
   ```

### Step 3: Production Deployment

1. **Execute Deployment Script**
   ```bash
   # Make script executable
   chmod +x scripts/deploy_production_webhook.sh

   # Run deployment (from main branch)
   ./scripts/deploy_production_webhook.sh
   ```

2. **Monitor Deployment Progress**
   - Script will automatically monitor deployment
   - Check DigitalOcean dashboard for visual progress
   - Monitor logs in real-time

3. **Post-Deployment Validation**
   ```bash
   # The deployment script automatically runs these validations:
   # - Health endpoint test
   # - Webhook verification test
   # - Embedded signup page test
   # - Meta API connectivity test
   ```

### Step 4: Meta Developer Console Configuration

1. **Update Webhook URLs**
   - Go to Meta Developer Console
   - WhatsApp → Configuration → Webhook
   - Update URL to: `https://webhook.aiagency.platform/webhook/whatsapp`
   - Update Verify Token to match your configuration

2. **Configure Embedded Signup**
   - WhatsApp → Configuration → Embedded Signup
   - Update callback URL: `https://webhook.aiagency.platform/embedded-signup/callback`
   - Verify configuration ID matches your environment

3. **Test Integration**
   ```bash
   # Test webhook verification
   curl "https://webhook.aiagency.platform/webhook/whatsapp?hub.mode=subscribe&hub.challenge=test123&hub.verify_token=YOUR_VERIFY_TOKEN"

   # Should return: test123
   ```

## 🔧 Post-Deployment Configuration

### DNS Configuration (If Using Custom Domain)

1. **Configure DNS Records**
   ```bash
   # Add CNAME records in your DNS provider
   webhook.aiagency.platform → your-app.ondigitalocean.app
   whatsapp.aiagency.platform → your-app.ondigitalocean.app  # alias
   ```

2. **SSL Certificate Validation**
   ```bash
   # Verify SSL certificate
   curl -I https://webhook.aiagency.platform/health
   # Should show HTTP/2 200 with valid SSL
   ```

### Monitoring Setup

1. **Configure Health Check Monitoring**
   ```bash
   # Set up monitoring service (e.g., Uptime Robot, Pingdom)
   # Monitor these endpoints:
   # - https://webhook.aiagency.platform/health
   # - https://webhook.aiagency.platform/embedded-signup/health
   ```

2. **Set Up Alerting**
   ```bash
   # Configure alerts for:
   # - Downtime (>5 minutes)
   # - High response time (>2 seconds)
   # - High error rate (>5%)
   # - Failed webhook deliveries
   ```

### Business Metrics Tracking

1. **Configure Analytics**
   ```bash
   # Business metrics to track:
   # - Client signups per day
   # - Webhook message volume
   # - EA conversation success rate
   # - Average response times
   ```

2. **Dashboard Setup**
   ```bash
   # Access metrics at:
   # - https://webhook.aiagency.platform/metrics (Prometheus)
   # - DigitalOcean App Platform monitoring
   # - Custom business dashboard (if implemented)
   ```

## 🔍 Validation & Testing

### Comprehensive Testing Checklist

#### Health Check Validation
- [ ] Basic health check: `/health`
- [ ] Deep health check: `/health?deep=true`
- [ ] Embedded signup health: `/embedded-signup/health`
- [ ] Metrics endpoint: `/metrics`

#### Webhook Functionality
- [ ] Webhook verification endpoint working
- [ ] Signature validation working
- [ ] Message reception and processing
- [ ] EA routing functionality
- [ ] Error handling and logging

#### Embedded Signup Flow
- [ ] Signup page loads correctly
- [ ] Facebook SDK integration working
- [ ] Token exchange completes within 30 seconds
- [ ] Client registration successful
- [ ] EA provisioning triggers correctly

#### Security Validation
- [ ] IP allowlisting working (test from non-Meta IP)
- [ ] Signature validation enforced
- [ ] Rate limiting functional
- [ ] Security headers present
- [ ] HTTPS enforcement working

#### Performance Testing
```bash
# Load test health endpoint
ab -n 1000 -c 10 https://webhook.aiagency.platform/health

# Test webhook endpoint (need valid signature)
curl -X POST https://webhook.aiagency.platform/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=..." \
  -d '{"object":"whatsapp_business_account","entry":[...]}'
```

## 🚨 Troubleshooting Guide

### Common Issues and Solutions

#### Issue: Webhook Verification Failed
```bash
# Symptoms: Meta webhook configuration fails
# Solution:
1. Check WHATSAPP_VERIFY_TOKEN matches Meta console
2. Verify HTTPS is working
3. Test endpoint manually:
   curl "https://webhook.aiagency.platform/webhook/whatsapp?hub.mode=subscribe&hub.challenge=test&hub.verify_token=YOUR_TOKEN"
```

#### Issue: Embedded Signup Token Exchange Timeout
```bash
# Symptoms: "Token exchange failed" in logs
# Solution:
1. Check Meta app credentials are correct
2. Verify app has proper permissions
3. Check network connectivity to Meta APIs
4. Validate token exchange happens within 30 seconds
```

#### Issue: High Response Times
```bash
# Symptoms: >2 second response times
# Solution:
1. Check Redis connectivity
2. Verify EA routing performance
3. Review database query performance
4. Check DigitalOcean resource usage
```

#### Issue: Security Blocks
```bash
# Symptoms: Legitimate requests being blocked
# Solution:
1. Verify Meta server IP ranges are current
2. Check security logs for patterns
3. Validate webhook signatures
4. Review rate limiting configuration
```

### Emergency Procedures

#### Emergency Rollback
```bash
# If deployment causes critical issues
./scripts/rollback_webhook_deployment.sh --app-id YOUR_APP_ID --target previous --fast --yes
```

#### Emergency Maintenance Mode
```bash
# Temporarily disable webhook processing
# Update app environment variable:
MAINTENANCE_MODE=true

# Or use DigitalOcean console to scale down to 0 instances
```

#### Contact Information
- **Primary On-Call**: [Your emergency contact]
- **DigitalOcean Support**: [Your support plan]
- **Meta Developer Support**: [If Business verified]

## 📊 Monitoring and Maintenance

### Daily Monitoring Tasks
- [ ] Check application health dashboards
- [ ] Review error logs for unusual patterns
- [ ] Monitor webhook delivery success rates
- [ ] Check client signup conversion rates
- [ ] Verify Meta API quota usage

### Weekly Maintenance Tasks
- [ ] Review performance metrics
- [ ] Update security configurations if needed
- [ ] Check for Meta platform updates
- [ ] Validate backup and recovery procedures
- [ ] Review capacity and scaling needs

### Monthly Tasks
- [ ] Security audit and penetration testing
- [ ] Review and rotate secrets if needed
- [ ] Meta app review and compliance check
- [ ] Performance optimization review
- [ ] Disaster recovery testing

## 📈 Scaling and Optimization

### Horizontal Scaling
```yaml
# DigitalOcean App Platform auto-scaling
autoscaling:
  min_instance_count: 2
  max_instance_count: 8
  metrics:
    cpu: 70%
    memory: 80%
```

### Performance Optimization
- **Redis Connection Pooling**: Configure optimal pool sizes
- **HTTP Keep-Alive**: Enable for Meta API calls
- **Caching**: Implement response caching where appropriate
- **Database Optimization**: Optimize client registry queries

### Cost Optimization
- **Resource Right-Sizing**: Monitor usage and adjust instance sizes
- **Auto-Scaling**: Use efficient scaling policies
- **Redis Optimization**: Optimize memory usage and connection pooling
- **Monitoring Costs**: Track DigitalOcean usage and costs

## 🔐 Security Best Practices

### Ongoing Security Tasks
- [ ] Regular security updates for dependencies
- [ ] Monitor security advisories for Flask, Redis, etc.
- [ ] Rotate secrets on a regular schedule (quarterly)
- [ ] Review access logs for suspicious activity
- [ ] Keep Meta security best practices updated

### Compliance Requirements
- **Data Privacy**: Ensure GDPR/CCPA compliance
- **Meta Policies**: Follow WhatsApp Business API policies
- **Customer Data**: Proper encryption and isolation
- **Audit Trail**: Maintain logs for compliance auditing

## 🎯 Success Metrics

### Technical Metrics
- **Uptime**: >99.9% availability
- **Response Time**: <2 seconds (95th percentile)
- **Error Rate**: <1% of requests
- **Security Incidents**: 0 successful breaches

### Business Metrics
- **Client Onboarding**: <60 seconds from signup to EA
- **Message Processing**: >99% successful webhook processing
- **Customer Satisfaction**: Monitor EA conversation quality
- **Conversion Rate**: Track signup-to-active-customer rate

---

## 📞 Support and Resources

### Documentation
- [Meta Developer Documentation](https://developers.facebook.com/docs/whatsapp)
- [DigitalOcean App Platform Docs](https://docs.digitalocean.com/products/app-platform/)
- [Project Architecture Documentation](./Technical-Design-Document.md)

### Emergency Contacts
- **Development Team**: [Your team contact]
- **Platform Support**: [DigitalOcean support]
- **Meta Business Support**: [If applicable]

### Useful Commands
```bash
# Check deployment status
doctl apps list

# View live logs
doctl apps logs YOUR_APP_ID --follow

# Force rebuild deployment
doctl apps create-deployment YOUR_APP_ID --force-rebuild

# Update app configuration
doctl apps update YOUR_APP_ID --spec .do/app-production.yaml
```

---

**✅ Ready for Production!**

Once you've completed this guide, your Meta-compliant WhatsApp webhook service will be ready to support the business model where clients "acquire EA WhatsApp Services" through your centralized infrastructure, with full production-grade reliability, security, and monitoring.