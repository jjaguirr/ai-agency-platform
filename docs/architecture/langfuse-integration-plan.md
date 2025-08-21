# Langfuse Integration Plan - AI Agency Platform

**Integration Type:** Prompt Engineering & LLM Observability  
**Target Systems:** Infrastructure Agents (Vendor-Agnostic)  
**Version:** 1.0  
**Date:** 2025-01-17

---

## Executive Summary

Integrate Langfuse as the central prompt engineering and LLM observability platform for the **AI Agency Platform**. This enables vendor-agnostic prompt management, performance tracking across multiple AI models (OpenAI, Claude, Meta, DeepSeek, local), and comprehensive observability for customer-facing agent interactions.

### Key Benefits
- **Prompt Versioning**: Centralized management of agent system prompts across AI models
- **Multi-Model Observability**: Track performance across OpenAI, Claude, Meta, DeepSeek, local models
- **Cost Optimization**: Real-time cost tracking and model selection optimization
- **A/B Testing**: Compare prompt effectiveness across different AI providers
- **Customer Insights**: Monitor LAUNCH bot performance and self-configuration success

---

## Architecture Overview

### Langfuse Position in Dual-Agent System

```mermaid
graph TB
    subgraph "Claude Code Agents (Development)"
        CC1[Claude Desktop]
        CC2[Direct MCP Connections]
        CC3[Development Tools]
    end
    
    subgraph "Infrastructure Agents (Business/Customer)"
        IA1[Research Agent]
        IA2[Business Agent] 
        IA3[Creative Agent]
        IA4[LAUNCH Bots]
        IA5[Development Agent]
        IA6[n8n Workflow]
    end
    
    subgraph "MCPhub + Langfuse Integration"
        MH1[MCPhub Server :3000]
        LF1[Langfuse Server :3001]
        LF2[Prompt Management]
        LF3[Tracing & Analytics]
        LF4[Model Performance]
    end
    
    subgraph "AI Model Providers"
        AI1[OpenAI GPT-4]
        AI2[Claude API]
        AI3[Meta Llama]
        AI4[DeepSeek]
        AI5[Local Models]
    end
    
    subgraph "Data Layer"
        DB1[PostgreSQL - MCPhub]
        DB2[PostgreSQL - Langfuse]
        DB3[Redis - Message Bus]
        DB4[Qdrant - Agent Memory]
    end
    
    %% Claude Code agents bypass Langfuse (direct MCP)
    CC1 -.->|No Langfuse| CC2
    
    %% Infrastructure agents route through MCPhub + Langfuse
    IA1 --> MH1
    IA2 --> MH1
    IA3 --> MH1
    IA4 --> MH1
    IA5 --> MH1
    IA6 --> MH1
    
    %% MCPhub integrates with Langfuse
    MH1 --> LF1
    LF1 --> LF2
    LF1 --> LF3
    LF1 --> LF4
    
    %% Langfuse manages AI model interactions
    LF1 --> AI1
    LF1 --> AI2
    LF1 --> AI3
    LF1 --> AI4
    LF1 --> AI5
    
    %% Data connections
    MH1 --> DB1
    LF1 --> DB2
    MH1 --> DB3
    IA1 --> DB4
```

### Integration Scope

**✅ Included in Langfuse Integration:**
- **Infrastructure Agents**: All 6 agent types with vendor-agnostic AI models
- **Customer LAUNCH Bots**: Self-configuration monitoring and optimization
- **Business Process Agents**: Research, Analytics, Creative, Development agents
- **MCPhub Integration**: Prompt management through MCPhub security groups

**❌ Excluded from Langfuse Integration:**
- **Claude Code Agents**: Use direct MCP connections (no Langfuse involvement)
- **Personal Development**: Claude Desktop interactions remain direct
- **Local Development Tools**: Git, filesystem, code analysis tools

---

## Technical Implementation

### 1. Langfuse Deployment Architecture

#### Docker Compose Integration
```yaml
# docker-compose.langfuse.yml
version: '3.8'

services:
  langfuse-server:
    image: langfuse/langfuse:latest
    ports:
      - "3001:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:${LANGFUSE_DB_PASSWORD}@postgres-langfuse:5432/langfuse
      - NEXTAUTH_SECRET=${LANGFUSE_SECRET}
      - SALT=${LANGFUSE_SALT}
      - NEXTAUTH_URL=http://localhost:3001
      - TELEMETRY_ENABLED=true
      - LANGFUSE_ENABLE_EXPERIMENTAL_FEATURES=true
    depends_on:
      - postgres-langfuse
    networks:
      - ai-agency-network

  postgres-langfuse:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=langfuse
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=${LANGFUSE_DB_PASSWORD}
    volumes:
      - langfuse_postgres_data:/var/lib/postgresql/data
    networks:
      - ai-agency-network

  langfuse-worker:
    image: langfuse/langfuse:latest
    command: ["node", "worker.js"]
    environment:
      - DATABASE_URL=postgresql://langfuse:${LANGFUSE_DB_PASSWORD}@postgres-langfuse:5432/langfuse
    depends_on:
      - postgres-langfuse
    networks:
      - ai-agency-network

volumes:
  langfuse_postgres_data:

networks:
  ai-agency-network:
    external: true
```

### 2. MCPhub + Langfuse Integration Layer

#### Prompt Management Integration
```typescript
// src/integrations/langfuse-mcphub-bridge.ts
import { Langfuse } from 'langfuse';
import { MCPhubClient } from './mcphub-client';

export class LangfuseMCPhubBridge {
  private langfuse: Langfuse;
  private mcphub: MCPhubClient;
  
  constructor() {
    this.langfuse = new Langfuse({
      publicKey: process.env.LANGFUSE_PUBLIC_KEY,
      secretKey: process.env.LANGFUSE_SECRET_KEY,
      baseUrl: 'http://localhost:3001'
    });
    this.mcphub = new MCPhubClient();
  }
  
  // Infrastructure agent prompt management
  async getAgentPrompt(agentType: InfrastructureAgentType, version?: string): Promise<string> {
    const prompt = await this.langfuse.getPrompt(
      `infrastructure-agent-${agentType}`,
      version
    );
    return prompt.prompt;
  }
  
  // Multi-model agent execution with tracing
  async executeInfrastructureAgent(
    agentType: InfrastructureAgentType,
    input: string,
    customerId?: string,
    aiModel: AIModel = 'auto-select'
  ): Promise<AgentResponse> {
    const trace = this.langfuse.trace({
      name: `infrastructure-agent-${agentType}`,
      userId: customerId,
      metadata: {
        agentType,
        aiModel,
        mcphubGroup: customerId ? `customer-${customerId}` : 'business-operations'
      }
    });
    
    try {
      // Get versioned prompt from Langfuse
      const systemPrompt = await this.getAgentPrompt(agentType);
      
      // Select optimal AI model
      const selectedModel = await this.selectOptimalModel(agentType, aiModel, customerId);
      
      // Execute through MCPhub with selected model
      const generation = trace.generation({
        name: `${agentType}-generation`,
        model: selectedModel,
        modelParameters: {
          temperature: this.getTemperatureForAgent(agentType),
          maxTokens: this.getMaxTokensForAgent(agentType)
        },
        input: input,
        prompt: systemPrompt
      });
      
      const response = await this.mcphub.executeAgent({
        agentType,
        systemPrompt,
        userInput: input,
        aiModel: selectedModel,
        customerId
      });
      
      // Track response and performance
      generation.end({
        output: response.content,
        usage: {
          promptTokens: response.usage.promptTokens,
          completionTokens: response.usage.completionTokens,
          totalTokens: response.usage.totalTokens
        },
        level: response.success ? 'DEFAULT' : 'ERROR'
      });
      
      // Track customer-specific metrics
      if (customerId) {
        await this.trackCustomerMetrics(customerId, agentType, response);
      }
      
      return response;
      
    } catch (error) {
      trace.event({
        name: 'agent-execution-error',
        level: 'ERROR',
        metadata: { error: error.message, agentType, aiModel }
      });
      throw error;
    } finally {
      await trace.finalize();
    }
  }
  
  // AI model selection with cost optimization
  private async selectOptimalModel(
    agentType: InfrastructureAgentType, 
    preference: AIModel,
    customerId?: string
  ): Promise<string> {
    if (preference !== 'auto-select') return preference;
    
    // Get model performance data from Langfuse
    const modelStats = await this.langfuse.getModelStats(agentType);
    
    // Customer-specific model preferences
    if (customerId) {
      const customerPrefs = await this.mcphub.getCustomerAIPreferences(customerId);
      if (customerPrefs.preferredModel) return customerPrefs.preferredModel;
    }
    
    // Select based on cost/performance for agent type
    const agentModelMap = {
      'research': 'openai-gpt-4o', // Best for research and analysis
      'business': 'claude-3.5-sonnet', // Best for data analysis
      'creative': 'openai-gpt-4o', // Best for content generation
      'development': 'claude-3.5-sonnet', // Best for code and infrastructure
      'launch-bot': 'claude-3.5-sonnet', // Best for conversation and configuration
      'n8n-workflow': 'openai-gpt-4o' // Best for workflow design
    };
    
    return agentModelMap[agentType] || 'claude-3.5-sonnet';
  }
}

// Agent type definitions
type InfrastructureAgentType = 
  | 'research' 
  | 'business' 
  | 'creative' 
  | 'development' 
  | 'launch-bot' 
  | 'n8n-workflow';

type AIModel = 
  | 'openai-gpt-4o' 
  | 'claude-3.5-sonnet' 
  | 'meta-llama-3' 
  | 'deepseek-v2' 
  | 'local-model'
  | 'auto-select';
```

### 3. Infrastructure Agent Prompt Templates

#### Research Agent Prompt Management
```typescript
// Langfuse prompt template: infrastructure-agent-research
const researchAgentPrompt = {
  name: "infrastructure-agent-research",
  version: "1.0",
  prompt: `You are a Business Intelligence Agent specializing in market research and competitive analysis through MCPhub infrastructure tools.

## Core Mission
Provide comprehensive, data-driven business intelligence by leveraging web research, document analysis, and market data to generate actionable insights for business decision-making.

## Available Tools (via MCPhub)
- Web search and data extraction
- Document analysis and synthesis  
- Competitive intelligence gathering
- Market trend analysis
- Report generation and visualization

## Research Methodology
1. **Define Scope**: Clarify research objectives and success criteria
2. **Multi-Source Gathering**: Use diverse, credible sources for comprehensive coverage  
3. **Data Validation**: Cross-reference findings for accuracy and reliability
4. **Trend Analysis**: Identify patterns and predict future developments
5. **Actionable Insights**: Transform data into specific business recommendations

## Customer Context
{{#if customerId}}
Customer ID: {{customerId}}
Industry: {{customerIndustry}}
Specific Requirements: {{customerRequirements}}
{{/if}}

## Output Standards
- Executive summaries with key findings and recommendations
- Detailed analysis with supporting evidence and data sources
- Visual representations of trends and comparative data
- Risk assessment and opportunity identification
- Source citations with credibility assessments

Remember: All research must be objective, well-sourced, and focused on providing maximum business value for decision-making.`,
  
  labels: ["infrastructure-agent", "research", "business-intelligence"],
  
  config: {
    model: "auto-select",
    temperature: 0.3, // Lower temperature for factual research
    maxTokens: 4000,
    topP: 0.9
  }
};
```

#### LAUNCH Bot Prompt Management  
```typescript
// Langfuse prompt template: infrastructure-agent-launch-bot
const launchBotPrompt = {
  name: "infrastructure-agent-launch-bot",
  version: "2.0",
  prompt: `You are a LAUNCH Bot designed to configure customer AI agents through natural conversation in under 60 seconds.

## Mission: Self-Configuration Through Conversation
Guide customers through a friendly conversation to understand their business needs and automatically configure their AI agent with the right tools, AI model, and workflows.

## Configuration States
Current State: {{launchBotState}} (blank → identifying → learning → integrating → active)

### State: Blank
- Introduce yourself and ask about their business
- Focus on understanding their industry and primary goals
- Keep questions open-ended and conversational

### State: Identifying  
- Dig deeper into their specific pain points
- Understand their current processes and challenges
- Identify automation opportunities

### State: Learning
- Map their workflows and daily tasks
- Understand their technical constraints and preferences
- Identify required integrations and tools

### State: Integrating
- Automatically configure tools based on their needs
- Set up AI model preferences (OpenAI, Claude, etc.)
- Test connections and validate setup

### State: Active
- Full operational mode with customer-specific configuration
- Remember customer context and preferences
- Provide ongoing support and optimization

## Customer Information
{{#if customerId}}
Customer: {{customerName}}
Industry: {{customerIndustry}}  
AI Model Preference: {{customerAIModel}}
Current State: {{launchBotState}}
Configuration Progress: {{configurationProgress}}%
{{/if}}

## Available Tools (MCPhub-Routed)
{{#if customerTools}}
Configured Tools: {{customerTools}}
{{else}}
Available for Configuration: [web-search, email-automation, crm-integration, analytics, content-generation, workflow-automation]
{{/if}}

## Conversation Guidelines
- Be friendly, helpful, and conversational
- Ask one question at a time to avoid overwhelming
- Provide clear explanations of what you're configuring
- Confirm important decisions before implementing
- Show progress and celebrate milestones
- Escalate to human support if stuck or customer requests it

## Success Criteria
- Complete configuration in under 60 seconds of conversation
- Customer understands their configured agent capabilities
- All tools are properly connected and tested
- Customer feels confident using their new AI agent

Remember: You're not just configuring software - you're helping customers discover how AI can transform their business!`,

  labels: ["infrastructure-agent", "launch-bot", "customer-onboarding"],
  
  config: {
    model: "claude-3.5-sonnet", // Best for conversation and configuration
    temperature: 0.7, // Balanced for helpful but consistent responses
    maxTokens: 2000,
    topP: 0.95
  }
};
```

### 4. Multi-Model Performance Tracking

#### Cost Optimization Dashboard
```typescript
// Langfuse analytics integration
export class InfrastructureAgentAnalytics {
  
  async getModelPerformanceReport(dateRange: DateRange): Promise<ModelPerformanceReport> {
    const analytics = await this.langfuse.analytics({
      projectId: 'ai-agency-platform',
      dateRange,
      groupBy: ['model', 'agentType', 'customerId']
    });
    
    return {
      totalCost: analytics.totalCost,
      totalTokens: analytics.totalTokens,
      averageLatency: analytics.averageLatency,
      modelBreakdown: {
        'openai-gpt-4o': {
          usage: analytics.models['openai-gpt-4o'],
          costPerToken: 0.00006, // $0.06 per 1K tokens
          avgLatency: analytics.models['openai-gpt-4o'].avgLatency,
          successRate: analytics.models['openai-gpt-4o'].successRate
        },
        'claude-3.5-sonnet': {
          usage: analytics.models['claude-3.5-sonnet'],
          costPerToken: 0.000015, // $0.015 per 1K tokens  
          avgLatency: analytics.models['claude-3.5-sonnet'].avgLatency,
          successRate: analytics.models['claude-3.5-sonnet'].successRate
        },
        'meta-llama-3': {
          usage: analytics.models['meta-llama-3'],
          costPerToken: 0.000001, // $0.001 per 1K tokens (local/cheaper)
          avgLatency: analytics.models['meta-llama-3'].avgLatency,
          successRate: analytics.models['meta-llama-3'].successRate
        }
      },
      recommendations: this.generateOptimizationRecommendations(analytics)
    };
  }
  
  async trackLAUNCHBotSuccess(customerId: string, configurationTime: number): Promise<void> {
    await this.langfuse.event({
      name: 'launch-bot-completion',
      metadata: {
        customerId,
        configurationTime,
        successTarget: 60, // seconds
        success: configurationTime <= 60
      }
    });
  }
}
```

---

## Implementation Roadmap

### Phase 1: Langfuse Foundation (Week 1)
**Objective**: Deploy Langfuse and establish basic integration

#### Tasks:
1. **Deploy Langfuse Infrastructure**
   ```bash
   # Deploy Langfuse with PostgreSQL
   docker-compose -f docker-compose.langfuse.yml up -d
   
   # Initialize Langfuse database and admin user
   ./scripts/initialize-langfuse.sh
   ```

2. **Create Infrastructure Agent Projects**
   - Research Agent project with prompt templates
   - Business Agent project with analytics focus
   - Creative Agent project with multi-model support
   - LAUNCH Bot project with conversation tracking

3. **MCPhub Integration Setup**
   - Install Langfuse SDK in MCPhub server
   - Configure authentication and API keys
   - Set up basic tracing for Infrastructure agents

**Deliverables**:
- ✅ Langfuse operational on port 3001
- ✅ 6 Infrastructure agent projects created
- ✅ Basic MCPhub + Langfuse integration working

### Phase 2: Prompt Management (Week 2)  
**Objective**: Centralize and version all Infrastructure agent prompts

#### Tasks:
1. **Prompt Template Migration**
   - Move Research Agent prompts to Langfuse
   - Create versioned Business Agent prompts
   - Design Creative Agent multi-format prompts
   - Build LAUNCH Bot conversation flows

2. **Dynamic Prompt Loading**
   ```typescript
   // MCPhub integration with Langfuse prompts
   const prompt = await langfuse.getPrompt(
     'infrastructure-agent-research',
     'production'
   );
   ```

3. **A/B Testing Framework**
   - Create prompt variants for each agent type
   - Implement random assignment for testing
   - Track performance metrics per variant

**Deliverables**:
- ✅ All Infrastructure agent prompts in Langfuse
- ✅ Dynamic prompt loading in MCPhub
- ✅ A/B testing framework operational

### Phase 3: Multi-Model Optimization (Week 3)
**Objective**: Optimize AI model selection and cost management

#### Tasks:
1. **Model Performance Tracking**
   - Implement cost tracking per AI model
   - Monitor latency and success rates
   - Track customer satisfaction per model

2. **Intelligent Model Selection**
   ```typescript
   // Auto-select optimal model based on task and cost
   const model = await selectOptimalModel(agentType, customerBudget);
   ```

3. **Cost Optimization Algorithms**
   - Implement cost capping per customer
   - Create model fallback chains
   - Build cost prediction models

**Deliverables**:
- ✅ Multi-model performance dashboard
- ✅ Intelligent model selection algorithm
- ✅ Cost optimization system operational

### Phase 4: Customer Analytics (Week 4)
**Objective**: Customer-specific insights and optimization

#### Tasks:
1. **Customer Journey Tracking**
   - LAUNCH bot configuration success rates
   - Agent usage patterns per customer
   - Feature adoption and engagement metrics

2. **Custom Analytics Dashboards**
   - Customer-specific performance reports
   - Industry benchmark comparisons
   - ROI and value demonstration

3. **Predictive Analytics**
   - Predict customer churn based on usage
   - Recommend optimal configurations
   - Identify upsell opportunities

**Deliverables**:
- ✅ Customer analytics dashboard
- ✅ LAUNCH bot success optimization
- ✅ Predictive customer insights

---

## Success Metrics

### Technical Performance
- **Prompt Loading**: <50ms response time for prompt retrieval
- **Model Selection**: <100ms for intelligent model selection
- **Cost Tracking**: Real-time cost monitoring with <1% variance
- **A/B Testing**: Statistical significance within 48 hours

### Business Impact  
- **LAUNCH Bot Success**: >90% self-configuration in <60 seconds
- **Cost Optimization**: >20% reduction in AI model costs
- **Customer Satisfaction**: >95% positive feedback on agent performance
- **Model Performance**: >15% improvement through prompt optimization

### Operational Excellence
- **Uptime**: 99.9% Langfuse availability
- **Data Accuracy**: 100% prompt version consistency
- **Security**: Zero customer data exposure incidents
- **Scalability**: Support 1000+ concurrent customer agents

---

## Security & Compliance

### Data Protection
- **Customer Isolation**: Complete separation of customer prompts and analytics
- **Encryption**: TLS 1.3 for all Langfuse communications
- **Access Control**: Role-based access to Langfuse projects and data
- **Audit Trails**: Complete logging of all prompt and model interactions

### Compliance Framework
- **GDPR**: Customer right to prompt data deletion and export
- **SOC 2**: Comprehensive audit trails and access controls
- **HIPAA**: Healthcare customer prompt isolation and encryption
- **PCI DSS**: Secure handling of payment-related customer data

### Prompt Security
- **Version Control**: Immutable prompt versioning with audit trails
- **Access Control**: MCPhub group-based access to Langfuse prompts
- **Injection Prevention**: Input sanitization for customer-provided context
- **Backup & Recovery**: Automated prompt backup with disaster recovery

---

## Cost Analysis

### Langfuse Infrastructure Costs
- **Self-Hosted Deployment**: $50/month (2 vCPU, 4GB RAM)
- **PostgreSQL Database**: $30/month (managed database)
- **Storage**: $10/month (prompt templates and analytics data)
- **Total**: ~$90/month for full Langfuse deployment

### Expected ROI
- **Cost Optimization**: 20% reduction in AI model costs (~$500/month savings)
- **Performance Improvement**: 15% faster development through prompt optimization
- **Customer Success**: 25% increase in LAUNCH bot success rate
- **Net Benefit**: ~$400/month positive ROI + development acceleration

---

## Next Steps

1. **Execute Phase 1**: Deploy Langfuse infrastructure and basic integration
2. **Migrate Prompts**: Move Infrastructure agent prompts to Langfuse management
3. **Implement Tracking**: Add comprehensive tracing to all Infrastructure agents
4. **Optimize Models**: Implement intelligent model selection and cost optimization
5. **Launch Analytics**: Deploy customer analytics and success tracking

The Langfuse integration transforms our Infrastructure agents from static prompt-based systems into dynamic, optimized, and continuously improving AI agents with comprehensive observability and cost management.