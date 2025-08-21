# CLAUDE.md - AI Agency Platform Configuration

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI Agency Platform that serves as a vendor-agnostic AI Agency Platform with enhanced agent portfolio, enabling businesses to deploy sophisticated AI automation through self-configuring LAUNCH bots and enterprise-grade multi-agent orchestration.

## Business Context

**Product**: Commercial AI Agency Platform ($500K → $5M → $25M ARR)  
**Market**: $50B+ AI services market with vendor-agnostic positioning  
**Breakthrough Feature**: LAUNCH bots that self-configure in <60 seconds  
**Competitive Advantage**: Only platform supporting OpenAI, Claude, Meta, DeepSeek, and local models

## Enhanced Agent Portfolio

The platform delivers six specialized agent types designed for comprehensive business automation:

### 1. Marketing Automation Agent
**Purpose**: Multi-channel campaigns, lead generation, conversion optimization  
**Capabilities**: SEO/SEM, social media automation, email marketing, marketing analytics  
**Business Impact**: 300% improvement in lead conversion rates

### 2. Customer Success Agent  
**Purpose**: Customer health monitoring, churn prediction, retention strategies  
**Capabilities**: Upsell identification, onboarding automation, satisfaction tracking  
**Business Impact**: 85% reduction in customer churn through predictive analytics

### 3. Sales Automation Agent
**Purpose**: Pipeline management, lead scoring, deal closing automation  
**Capabilities**: CRM automation, proposal generation, sales forecasting, territory management  
**Business Impact**: 250% increase in sales velocity through pipeline optimization

### 4. Operations Intelligence Agent
**Purpose**: Process optimization, inventory management, supply chain automation  
**Capabilities**: Quality assurance, resource allocation, efficiency analytics  
**Business Impact**: 60% operational cost reduction through process optimization

### 5. Financial Management Agent
**Purpose**: Cash flow analysis, budget planning, expense optimization  
**Capabilities**: Invoice automation, financial reporting, cost reduction strategies  
**Business Impact**: 40% improvement in cash flow through automation

### 6. Compliance Security Agent
**Purpose**: Regulatory compliance automation, data protection, audit trails  
**Capabilities**: Security monitoring, policy enforcement, risk assessment  
**Business Impact**: 100% regulatory compliance achievement

### 7. Industry Specialist Agents
**Purpose**: Vertical-specific automation (Healthcare, Real Estate, E-commerce, Professional Services)  
**Capabilities**: Industry compliance (HIPAA, PCI-DSS), specialized workflows  
**Business Impact**: 90% faster time-to-market for new industry verticals

### 8. Innovation Strategy Agent
**Purpose**: Market opportunity identification, competitive analysis, strategic planning  
**Capabilities**: Trend analysis, business model optimization  
**Business Impact**: 90% faster time-to-market for new initiatives

## Revenue-Focused Architecture

### Multi-Agent Coordination Patterns
- **Revenue Optimization Workflow**: Sales → Customer Success → Marketing → Financial Management
- **Customer Lifecycle Management**: Marketing → Sales → Operations → Customer Success → Compliance  
- **Business Intelligence Pipeline**: Operations → Financial → Innovation Strategy → Marketing
- **Parallel Execution**: Multiple agents working simultaneously for maximum efficiency

### Customer Success Metrics
- **LAUNCH Bot Performance**: >90% self-configuration success in <60 seconds
- **Revenue Growth**: >25% month-over-month ARR growth  
- **Customer Retention**: <3% monthly churn across all tiers
- **Operational Efficiency**: <$50/month operational cost per customer

## Technical Architecture

### Infrastructure Components
- **MCPhub Hub**: Central MCP server with JWT+bcrypt authentication and RBAC
- **Multi-Database**: PostgreSQL (business data), Redis (sessions/queues), Qdrant (agent memory)
- **n8n Integration**: Visual workflow automation and process orchestration
- **Langfuse Platform**: Dynamic prompt management and multi-model optimization

### Security Model
- **5-Tier Security Groups**: Personal → Development → Business → Customer → Public
- **Customer Isolation**: Complete data separation per customer with configurable AI models
- **Vendor-Agnostic AI**: Support for OpenAI, Claude, Meta, DeepSeek, local models
- **Compliance Ready**: GDPR, HIPAA, PCI-DSS, SOC2 support

### Key Implementation Files
- `docs/architecture/Product Requirements Document.md` - Business requirements and market strategy
- `docs/architecture/Technical Design Document.md` - Complete system architecture  
- `PROJECT-SUMMARY.md` - Project overview and current status
- `docker-compose.langfuse.yml` - Langfuse + MCPhub deployment
- `scripts/initialize-langfuse.sh` - Automated Langfuse setup

## Development Commands

### Infrastructure Setup
```bash
# Initialize Langfuse for prompt engineering
./scripts/initialize-langfuse.sh

# Access platforms
open http://localhost:3001  # Langfuse UI  
open http://localhost:3000  # MCPhub API
```

### MCPhub & Services
Since this project relies on MCPhub (enterprise MCP server hub), ensure the following are running:
- MCPhub server on port 3000
- PostgreSQL database for user/group management
- Redis for sessions and queues
- Qdrant vector database for agent memory
- n8n on port 5678 for workflow automation

## Business Success Framework

### Revenue Targets
- **Year 1**: $500K ARR with >80% customer satisfaction
- **Year 2**: $5M ARR with enterprise market penetration  
- **Year 3**: $25M ARR with market leadership position

### Customer Success Indicators
- **LAUNCH Bot Performance**: >90% successful self-configuration without human intervention
- **Customer Satisfaction**: >4.5/5.0 average rating with onboarding experience
- **Escalation Rate**: 15-20% escalation to human support (optimal balance)
- **Revenue Growth**: >20% month-over-month growth through enhanced agent capabilities

### Market Positioning
- **Unique Value Proposition**: "The only AI agency platform that gets you operational in 60 seconds with your choice of AI models, complete data control, and enterprise-grade security"
- **Competitive Differentiation**: Vendor-agnostic approach vs. vendor lock-in competitors
- **Target Segments**: SMB (focus), AI Agencies, Enterprise, Industry Verticals

## Development Guidelines

### Agent Development Priorities
1. **Revenue Impact**: Prioritize agents with highest customer ROI
2. **Market Differentiation**: Focus on vendor-agnostic capabilities  
3. **Customer Success**: Optimize for >90% LAUNCH bot success rates
4. **Scalability**: Design for 10,000+ concurrent customer environments

### Security Requirements
- All agent interactions must maintain complete customer isolation
- Multi-model AI support with customer-configurable preferences
- Compliance-ready architecture for enterprise sales
- Complete audit trails for regulatory requirements

### Performance Standards
- **API Response**: <200ms p95 response time
- **Agent Processing**: <2 seconds for simple tasks, <30 seconds for complex
- **LAUNCH Bot Setup**: <60 seconds for complete customer configuration
- **System Uptime**: 99.99% availability target

When working with this codebase, prioritize business value delivery, customer success metrics, and the enhanced agent portfolio that drives revenue growth from $500K to $25M ARR.

## Expected Business Impact

### Personal Development Acceleration
- **Enhanced Productivity**: Advanced AI agent assistance for development tasks
- **Market Insights**: Real-time competitive intelligence and opportunity identification  
- **Strategic Guidance**: AI-powered business development and growth strategies

### Commercial AI Agency Platform
- **Vendor-Agnostic Infrastructure**: Customer choice of AI models increases market appeal
- **Enhanced Agent Portfolio**: Comprehensive business automation across all departments
- **Customer Success Automation**: LAUNCH bots reduce onboarding costs and improve satisfaction
- **Scalable Operations**: Support unlimited customers with optimized resource usage

Remember: This platform represents a new paradigm in AI agency services, combining cutting-edge technology with proven business models to create a scalable, profitable, and market-leading AI automation platform.