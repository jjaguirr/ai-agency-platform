# CLAUDE.md - AI Agency Platform Configuration

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a vendor-agnostic AI Agency Platform built through a phased development approach, enabling businesses to deploy sophisticated AI automation through self-configuring LAUNCH bots and enterprise-grade multi-agent orchestration.

## Phased Development Strategy

**Phase 1** (8 weeks): Foundation Infrastructure + Essential Agents  
**Phase 2** (4 weeks): Enhanced Agent Portfolio + Advanced Orchestration  
**Phase 3** (4 weeks): Scale & Operations + Enterprise Features

This phased approach reduces complexity, enables faster time-to-market, and provides early revenue generation while building toward the complete platform vision.

## Business Context

**Product**: Commercial AI Agency Platform ($500K → $5M → $25M ARR)  
**Market**: $50B+ AI services market with vendor-agnostic positioning  
**Breakthrough Feature**: LAUNCH bots that self-configure in <60 seconds  
**Competitive Advantage**: Only platform supporting OpenAI, Claude, Meta, DeepSeek, and local models

## Enhanced Agent Portfolio (Progressive Rollout)

The platform delivers specialized agents through progressive rollout aligned with development phases:

### Phase 1: Essential Foundation (Weeks 1-8)
**Focus**: Rapid customer onboarding and immediate value delivery

### 1. Customer Success Agent (Phase 1 Priority)
**Purpose**: Customer health monitoring, churn prediction, retention strategies  
**Capabilities**: Health scoring, usage analytics, escalation triggers  
**Business Impact**: 85% reduction in customer churn through predictive analytics  
**Phase 1 Scope**: Basic health monitoring, automated alerts, simple onboarding

### 2. Marketing Automation Agent (Phase 1 Priority)
**Purpose**: Lead generation, email campaign automation  
**Capabilities**: Campaign creation, lead scoring, social media posting  
**Business Impact**: 300% improvement in lead conversion rates  
**Phase 1 Scope**: Email automation, basic lead scoring, social media posting

### Phase 2: Revenue Acceleration (Weeks 9-12)
**Focus**: Advanced business automation and measurable ROI

### 3. Sales Automation Agent (Phase 2)
**Purpose**: Pipeline management, lead scoring, deal closing automation  
**Capabilities**: CRM automation, proposal generation, sales forecasting  
**Business Impact**: 250% increase in sales velocity through pipeline optimization

### 4. Financial Management Agent (Phase 2)
**Purpose**: Cash flow analysis, budget planning, expense optimization  
**Capabilities**: Invoice automation, financial reporting, cost reduction strategies  
**Business Impact**: 40% improvement in cash flow through automation

### 5. Operations Intelligence Agent (Phase 2)
**Purpose**: Process optimization, inventory management, supply chain automation  
**Capabilities**: Quality assurance, resource allocation, efficiency analytics  
**Business Impact**: 60% operational cost reduction through process optimization

### 6. Compliance Security Agent (Phase 2)
**Purpose**: Regulatory compliance automation, data protection, audit trails  
**Capabilities**: Security monitoring, policy enforcement, risk assessment  
**Business Impact**: 100% regulatory compliance achievement

### Phase 3: Enterprise Scale (Weeks 13-16)
**Focus**: Advanced features, enterprise compliance, and market leadership

### 7. Industry Specialist Agents (Phase 3)
**Purpose**: Vertical-specific automation (Healthcare, Real Estate, E-commerce, Professional Services)  
**Capabilities**: Industry compliance (HIPAA, PCI-DSS), specialized workflows  
**Business Impact**: 90% faster time-to-market for new industry verticals

### 8. Innovation Strategy Agent (Phase 3)
**Purpose**: Market opportunity identification, competitive analysis, strategic planning  
**Capabilities**: Trend analysis, business model optimization  
**Business Impact**: 90% faster time-to-market for new initiatives

## Revenue-Focused Architecture

### Multi-Agent Coordination Patterns
- **Revenue Optimization Workflow**: Sales → Customer Success → Marketing → Financial Management
- **Customer Lifecycle Management**: Marketing → Sales → Operations → Customer Success → Compliance  
- **Business Intelligence Pipeline**: Operations → Financial → Innovation Strategy → Marketing
- **Parallel Execution**: Multiple agents working simultaneously for maximum efficiency

### Simplified LAUNCH Bot (2-Stage Process)

#### Stage 1: Quick Setup (30 seconds)
- **Industry Detection**: Automatic business type identification
- **Essential Agents**: Customer Success + Marketing Automation agents
- **AI Model Selection**: Customer choice of OpenAI or Claude
- **Basic Integration**: Essential business tool connections
- **Success Rate**: >85% completion without intervention

#### Stage 2: Advanced Configuration (Optional)
- **Custom Workflows**: Tailored business process automation
- **Advanced Integrations**: CRM, ERP, specialized tools
- **Performance Optimization**: Agent fine-tuning based on usage
- **Enterprise Features**: Advanced security and compliance
- **Progression Rate**: >60% customers advance to Stage 2

### Customer Success Metrics by Phase
**Phase 1**: >85% Stage 1 success, >4.0/5.0 satisfaction, 50+ customers  
**Phase 2**: >90% Stage 2 progression, <3% churn, $100K+ MRR  
**Phase 3**: Enterprise ready, 500+ customers, market leadership

## Technical Architecture

### Infrastructure Components
- **MCPhub Hub**: Central MCP server with JWT+bcrypt authentication and RBAC
- **Multi-Database**: PostgreSQL (business data), Redis (sessions/queues), Qdrant (agent memory)
- **n8n Integration**: Visual workflow automation and process orchestration
- **Langfuse Platform**: Dynamic prompt management and multi-model optimization

### Security Model
- **5-Tier Security Groups**: Personal → Development → Business → Customer → Public
- **Llama Guard 4 AI Safety**: Enterprise-grade LLM security with MLCommons standards
- **Dual-Layer Protection**: Nginx security proxy + AI-powered content moderation
- **Prompt Injection Defense**: Real-time detection and blocking of manipulation attempts
- **Customer Isolation**: Complete data separation per customer with configurable AI models
- **Vendor-Agnostic AI**: Support for OpenAI, Claude, Meta, DeepSeek, local models
- **Compliance Ready**: GDPR, HIPAA, PCI-DSS, SOC2 support with automated audit trails

### Key Implementation Files by Phase
**Phase 1 Documents**:
- `docs/architecture/Phase-1-PRD.md` - Foundation infrastructure requirements
- `docs/architecture/Technical Design Document.md` - Complete system architecture  
- `docker-compose.langfuse.yml` - Langfuse + MCPhub deployment
- `docker-compose.llamaguard.yml` - Llama Guard 4 security deployment
- `scripts/initialize-langfuse.sh` - Automated Langfuse setup
- `scripts/deploy-llamaguard-security.sh` - Automated security stack deployment

**Security Implementation Files**:
- `config/security/safety-policies.yaml` - Tier-based safety policies and compliance rules
- `config/nginx/security-proxy.conf` - Rate limiting and DDoS protection configuration
- `src/security/llamaguard-api.py` - LLM safety evaluation API wrapper

**Phase 2 Documents**:
- `docs/architecture/Phase-2-PRD.md` - Agent system & orchestration
- `config/infrastructure-agents-config.json` - Agent configuration
- `src/prompts/agent-system-prompts.json` - Enhanced agent prompts

**Phase 3 Documents**:
- `docs/architecture/Phase-3-PRD.md` - Scale & operations requirements
- `PROJECT-SUMMARY.md` - Overall project status and roadmap

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
### Phase 1 Infrastructure Requirements
Since this project relies on MCPhub (enterprise MCP server hub), ensure the following are running:
- MCPhub server on port 3000 (5-tier security architecture)
- PostgreSQL database for user/group management and business data
- Redis for sessions, queues, and real-time coordination
- Qdrant vector database for agent memory and customer isolation
- n8n on port 5678 for basic workflow automation

### Phase 2 Additional Requirements
- Advanced LangGraph integration for multi-agent orchestration
- Enhanced n8n workflows for complex business processes
- Additional AI model integrations (Meta, DeepSeek, local models)

### Phase 3 Enterprise Requirements
- Advanced monitoring and analytics dashboards
- Enterprise compliance and audit systems
- White-label deployment capabilities

## Business Success Framework

### Revenue Targets by Phase
**Phase 1** (8 weeks): Foundation for customer acquisition  
- 50+ customers successfully onboarded
- $10K+ MRR (proof of concept)
- >80% customer retention validation

**Phase 2** (4 weeks): Professional tier enablement  
- $499-$2,999/month Professional tier pricing
- 200+ customers on Professional tier
- $100K+ MRR milestone

**Phase 3** (4 weeks): Enterprise readiness  
- Enterprise tier preparation ($5K+/month)
- Market validation for $5M+ ARR trajectory
- Competitive advantage establishment

**Long-term**: $500K → $5M → $25M ARR progression

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

### Development Priorities by Phase

**Phase 1 Priorities**:
1. **Foundation First**: Core infrastructure (auth, database, API, MCPhub)
2. **Essential Agents**: Customer Success + Marketing Automation only
3. **LAUNCH Bot Stage 1**: 30-second quick setup process
4. **Customer Validation**: Prove product-market fit with minimal features

**Phase 2 Priorities**:
1. **Revenue Agents**: Sales, Financial, Operations, Compliance agents
2. **Advanced Orchestration**: Multi-agent coordination and workflows
3. **LAUNCH Bot Stage 2**: Advanced configuration and customization
4. **Professional Tier**: Enable higher-value customer segments

**Phase 3 Priorities**:
1. **Enterprise Features**: Advanced analytics, compliance, white-label
2. **Industry Specialization**: Vertical-specific agents and workflows
3. **Scale Operations**: Support 1000+ customers with optimal performance
4. **Market Leadership**: Competitive differentiation and thought leadership

### Security Requirements
- All agent interactions must maintain complete customer isolation
- Multi-model AI support with customer-configurable preferences
- Compliance-ready architecture for enterprise sales
- Complete audit trails for regulatory requirements

### Performance Standards by Phase
**Phase 1 Standards**:
- **API Response**: <200ms p95 response time
- **Agent Processing**: <2 seconds for simple tasks
- **LAUNCH Bot Stage 1**: <30 seconds completion
- **System Uptime**: 99.9% target with 50+ concurrent customers

**Phase 2 Standards**:
- **Multi-Agent Coordination**: <500ms inter-agent communication
- **Workflow Execution**: 95% completion rate without intervention
- **LAUNCH Bot Stage 2**: <5 minutes advanced configuration
- **Customer Load**: 500+ concurrent customers

**Phase 3 Standards**:
- **Enterprise Scale**: 1000+ customers with optimal performance
- **Advanced Analytics**: Real-time business intelligence across all agents
- **Compliance Automation**: 100% regulatory compliance achievement
- **Market Leadership**: Industry-leading performance and customer satisfaction

When working with this codebase, follow the phased development approach: start with Phase 1 foundation, validate with customers, then progressively enhance toward the complete platform vision.

## Phased Implementation Benefits

### Phase 1 Benefits (Foundation)
- **Faster Time-to-Market**: 8 weeks vs 16 weeks for full platform
- **Early Revenue**: Customer acquisition starts 6 weeks earlier
- **Risk Mitigation**: Validate core value proposition before advanced features
- **Customer Feedback**: Real user insights guide Phase 2 development

### Phase 2 Benefits (Revenue Acceleration)
- **Professional Tier**: Enable $499-$2,999/month pricing
- **Measurable ROI**: Deliver 250%+ improvements in customer metrics
- **Competitive Advantage**: Advanced agent coordination vs basic automation
- **Market Positioning**: Establish vendor-agnostic leadership

### Phase 3 Benefits (Enterprise Scale)
- **Enterprise Ready**: Support large organizations with advanced compliance
- **Market Leadership**: First-mover advantage in vendor-agnostic AI platforms
- **Scalable Operations**: Foundation for $5M+ ARR trajectory
- **Industry Expansion**: Vertical-specific solutions for rapid growth

### Overall Platform Vision
This phased approach creates a new paradigm in AI agency services: a vendor-agnostic platform that combines cutting-edge technology with proven business models, delivering measurable customer value while building toward market leadership in the $50B+ AI services market.

**Success Enablers**: Simplified LAUNCH bot workflow, progressive agent rollout, customer choice of AI models, complete data isolation, and enterprise-grade security from day one.