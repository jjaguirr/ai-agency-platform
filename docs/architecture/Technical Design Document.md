# AI Agency Platform - Technical Design Document (TDD)

**Document Type:** Technical Design Document  
**Version:** 6.0 - EA-First Architecture  
**Date:** August 29, 2025

## Executive Summary

### Vision Statement
Vendor-agnostic AI Agency Platform enabling businesses to deploy an Executive Assistant that learns entire businesses through conversation and creates automations in real-time with complete per-customer isolation.

### Technical Innovation
- **Executive Assistant Core:** Single sophisticated EA that handles everything through natural dialogue
- **Per-Customer MCP Servers:** Complete isolation via dedicated MCP server instances
- **Conversational Learning:** EA learns business through phone calls, WhatsApp, and email
- **Real-Time Workflow Creation:** EA creates n8n workflows during conversations
- **Vendor-Agnostic AI:** Customer choice of OpenAI, Claude, Meta, DeepSeek, local models

---

## System Architecture

### Phase 1 Architecture - Executive Assistant Foundation

```mermaid
graph TB
    subgraph "Communication Channels"
        MC1[WhatsApp Business API]
        MC2[Email SMTP/IMAP]
        MC3[Phone/Voice (Twilio + ElevenLabs)]
    end
    
    subgraph "Executive Assistant Core"
        EA1[Executive Assistant]
        EA2[Business Learning System]
        EA3[Workflow Creation Engine]
        EA4[Customer Relationship Memory]
    end
    
    subgraph "Per-Customer MCP Servers"
        MCP1[Customer MCP Server Instance]
        MCP2[Dedicated PostgreSQL Schema]
        MCP3[Isolated Memory Layer - Mem0]
        MCP4[Private Redis Namespace]
    end
    
    subgraph "Business Memory System"
        BM1[Mem0 Memory Layer]
        BM2[PostgreSQL Business Context]
        BM3[Redis Conversation Memory]
        BM4[Pattern Recognition Engine]
    end
    
    subgraph "Workflow Orchestration"
        WO1[n8n Workflow Engine]
        WO2[Temporal Orchestrator]
        WO3[Agent Workflow Creator]
    end
    
    subgraph "AI Model Layer"
        AI1[OpenAI GPT-4o]
        AI2[Claude 3.5 Sonnet]
        AI3[Vendor-Agnostic Router]
    end
    
    subgraph "Management Interface (Future)"
        UI1[EA Dashboard]
        UI2[Business Context Viewer]
        UI3[Workflow Monitor]
    end
    
    MC1 --> MCP1
    MC2 --> MCP1
    MC3 --> MCP1
    MCP1 --> EA1
    EA1 --> EA2
    EA2 --> BM1
    EA3 --> WO1
    EA4 --> BM2
    BM3 --> EA1
    WO2 --> WO1
    EA1 --> AI1
    EA1 --> AI2
    UI1 --> MCP1
```

### Database Architecture

```yaml
PostgreSQL_Per_Customer:
  customers:
    - customer_id, email, company, mcp_server_id
    - Complete customer isolation via per-customer MCP servers
  
  business_knowledge:
    - entity_type, relationships, business_context
    - EA's learned business understanding
    
  conversation_history:
    - session_id, channel, messages, business_insights
    - Complete interaction history for EA learning
    
  workflows:
    - workflow_id, ea_created, n8n_data, business_purpose
    - EA-created workflow storage with business context

Mem0_Per_Customer:
  business_memory_collections:
    - Customer-isolated vector collections
    - Semantic search for business context
    - Pattern recognition and learning
    
Redis_Per_Customer:
  conversation_context: Active EA conversation state
  business_memory: Real-time business context access
  workflow_state: EA workflow creation status
```

## Core Components

### 1. Executive Assistant System

```typescript
// Executive Assistant Architecture
interface ExecutiveAssistant {
  id: string;
  customerId: string;
  mcpServerId: string;
  communicationChannels: ['whatsapp', 'email', 'phone'];
  businessMemory: BusinessMemorySystem;
  workflowCreator: N8nIntegration;
  conversationEngine: ConversationEngine;
}

class BusinessMemorySystem {
  memoryLayer: Mem0Client; // TODO: Implement Mem0 client
  businessContext: PostgreSQLGraph;
  conversationMemory: RedisClient;
  
  async learnBusiness(interaction: BusinessInteraction): Promise<void> {
    // Store business insight in vector store for semantic retrieval
    await this.vectorStore.upsert({
      id: interaction.id,
      vector: await this.embedBusinessContext(interaction),
      payload: interaction
    });
    
    // Update business knowledge graph
    await this.businessContext.updateBusinessRelationships(interaction);
    
    // Cache conversation context for immediate access
    await this.conversationMemory.setex(
      `business_context:${interaction.customerId}`, 
      3600, 
      JSON.stringify(interaction)
    );
  }
  
  async recallBusinessContext(query: string): Promise<BusinessInteraction[]> {
    const queryVector = await this.embedBusinessQuery(query);
    return await this.vectorStore.search(queryVector, { limit: 10 });
  }
}
```

### 2. Communication Integration Layer

```typescript
// Executive Assistant Communication System
class CommunicationHub {
  whatsappAPI: WhatsAppBusinessAPI;
  emailService: EmailSMTPService;
  phoneService: TwilioVoiceAPI;
  ttsService: ElevenLabsTTS;
  sttService: WhisperSTT;
  
  async handleCustomerCommunication(message: IncomingMessage, ea: ExecutiveAssistant): Promise<void> {
    // Process message through EA with business context
    const businessContext = await ea.businessMemory.recallBusinessContext(message.content);
    const response = await ea.processWithBusinessContext(message, businessContext);
    
    // Send response through appropriate channel
    switch (message.channel) {
      case 'whatsapp':
        await this.whatsappAPI.sendMessage(message.from, response);
        break;
      case 'email':
        await this.emailService.sendEmail(message.from, response);
        break;
      case 'phone':
        const audioResponse = await this.ttsService.synthesize(response);
        await this.phoneService.playAudio(message.from, audioResponse);
        break;
    }
    
    // Log interaction for business learning
    await ea.businessMemory.learnBusiness({
      input: message.content,
      output: response,
      channel: message.channel,
      businessInsights: await this.extractBusinessInsights(message, response),
      timestamp: Date.now()
    });
  }
}
```

### 3. EA Workflow Creation System

```typescript
// Executive Assistant Workflow Creation
class EAWorkflowCreator {
  n8nClient: N8nAPIClient;
  temporalClient: TemporalClient;
  templateEngine: WorkflowTemplateEngine;
  
  async createWorkflowDuringConversation(ea: ExecutiveAssistant, businessNeed: BusinessNeed): Promise<string> {
    // Match business need to pre-built template
    const template = await this.templateEngine.matchBusinessNeedToTemplate(businessNeed);
    
    // Customize template based on business context
    const customizedWorkflow = await this.customizeTemplate(template, ea.businessMemory);
    
    // Generate n8n workflow JSON
    const n8nWorkflow = {
      name: `${ea.customerId}_${businessNeed.type}_${Date.now()}`,
      nodes: await this.generateNodes(customizedWorkflow),
      connections: await this.generateConnections(customizedWorkflow)
    };
    
    // Deploy to customer's isolated n8n instance
    const workflowId = await this.n8nClient.createWorkflow(n8nWorkflow, ea.mcpServerId);
    
    // Schedule with Temporal for 24/7 execution
    await this.temporalClient.startWorkflow({
      workflowId: `ea_${ea.id}_workflow_${workflowId}`,
      taskQueue: `customer-${ea.customerId}-workflows`,
      workflowType: 'EAWorkflowExecutor'
    });
    
    return workflowId;
  }
}
```

### 4. EA Temporal Orchestration

```typescript
// 24/7 Executive Assistant Operation with Temporal
@Workflow()
export class EAWorkflowExecutor {
  @WorkflowMain()
  async execute(params: EAWorkflowParams): Promise<void> {
    // Continuous EA operation loop
    while (true) {
      // Check for pending customer communications
      const communications = await Activities.checkPendingCommunications(params.eaId);
      
      // Process each communication with business context
      for (const communication of communications) {
        await Activities.processWithBusinessContext(params.eaId, communication);
      }
      
      // Identify workflow creation opportunities during conversations
      const workflowOpportunities = await Activities.identifyWorkflowOpportunities(params.eaId);
      
      for (const opportunity of workflowOpportunities) {
        await Activities.createWorkflowFromTemplate(params.eaId, opportunity);
      }
      
      // Check for proactive business insights
      await Activities.generateProactiveInsights(params.eaId);
      
      // Sleep for optimal polling interval
      await sleep('30s');
    }
  }
}

// Temporal Activities for reliable EA execution
export const Activities = {
  async processWithBusinessContext(eaId: string, communication: Communication): Promise<void> {
    // Process communication with full business context and memory
  },
  
  async createWorkflowFromTemplate(eaId: string, opportunity: WorkflowOpportunity): Promise<void> {
    // Create workflow using pre-built templates with customization
  },
  
  async generateProactiveInsights(eaId: string): Promise<void> {
    // Generate proactive business insights and suggestions
  }
};
```

### 5. Per-Customer MCP Server Architecture

```yaml
Per_Customer_MCP_Configuration:
  isolation_model:
    dedicated_servers: Each customer gets own MCP server instance
    complete_separation: No shared infrastructure between customers
    resource_allocation: Per-customer compute and storage limits
    network_isolation: Customer-specific network namespaces
    
  ea_integration:
    direct_access: EA has complete control over customer MCP server
    tool_orchestration: Full MCP protocol tool access and routing
    ai_model_selection: Customer choice of OpenAI, Claude, local models
    workflow_automation: Direct n8n integration per customer
    
  security_architecture:
    database_isolation: Customer-specific PostgreSQL schemas
    memory_isolation: Private Mem0 memory spaces per customer
    workflow_isolation: Customer-specific n8n workspaces
    credential_management: Isolated API keys and access tokens
```

## Performance & Scalability

### Phase 1 Performance Requirements
```yaml
EA_Performance_Targets:
  ea_response_time: <2 seconds for communication responses
  provisioning_time: <30 seconds from purchase to working EA
  memory_recall: <500ms for business context retrieval
  workflow_creation: <2 minutes for template-based workflows
  concurrent_eas: 100+ active Executive Assistants
  
Per_Customer_Scalability:
  mcp_provisioning: <30 seconds per customer MCP server
  isolation_scaling: Support 1,000+ individual MCP servers
  database_optimization: Per-customer schema with connection pooling
  memory_scaling: Customer-isolated Mem0 memory spaces
  temporal_scaling: Per-customer workflow execution queues
```

## Security Implementation

### Complete Customer Isolation
```yaml
Per_Customer_Isolation:
  dedicated_mcp_servers: Each customer gets own MCP server instance
  database_separation: Customer-specific PostgreSQL schemas
  memory_spaces: Private Mem0 memory spaces per customer
  workflow_storage: Customer-specific n8n workspaces
  credential_isolation: Customer-owned API keys and tokens
  
Communication_Security:
  channel_authentication: Secure API keys per customer
  conversation_encryption: End-to-end encryption for all communications
  business_audit_trails: Complete EA interaction logging
  customer_rate_limits: Per-customer MCP server rate limiting
```

## Deployment Architecture

### Infrastructure Components
```yaml
Per_Customer_MCP_Services:
  mcp_server: Customer-specific MCP server instance
  postgresql: pgvector/pgvector:pg16 with customer schema
  redis: redis:7-alpine with customer namespace
  mem0: mem0ai/mem0 with customer memory spaces
  n8n: n8nio/n8n with customer workspace
  temporal: temporalio/auto-setup with customer queue
  
EA_Services:
  executive_assistant: aiagency/executive-assistant:1.0
  conversation_engine: aiagency/conversation-engine:1.0
  workflow_creator: aiagency/workflow-creator:1.0
  business_memory: aiagency/business-memory:1.0
  
Communication_Integrations:
  whatsapp_business: Meta WhatsApp Business API
  email_service: SMTP/IMAP providers (Gmail, Outlook) 
  phone_service: Twilio Voice API + ElevenLabs TTS + Whisper STT
```

---

## Implementation Mapping to PRD Requirements

### Phase 1 PRD Mapping
| PRD Requirement | Technical Implementation | Location |
|----------------|-------------------------|----------|
| Social Media Manager | AgentWorkflowCreator + MessagingHub | Core Components §1,§2 |
| Finance Agent | AgentMemory + TemporalOrchestrator | Core Components §1,§4 |
| Marketing Agent | N8nIntegration + Mem0MemoryLayer | Core Components §1,§3 |
| Business Agent | PostgreSQLGraph + MCPhubRouting | Core Components §1,§5 |
| WhatsApp Integration | WhatsAppBusinessAPI | Messaging Layer §2 |
| Email Integration | EmailSMTPService | Messaging Layer §2 |
| Instagram Integration | InstagramGraphAPI | Messaging Layer §2 |
| Agent Learning | Mem0Client + PostgreSQLGraph | AgentMemory §1 |
| Workflow Creation | N8nAPIClient + WorkflowCreator | Workflow System §3 |
| 24/7 Operation | TemporalWorkflowExecutor | Temporal Orchestration §4 |
| Customer Isolation | MCPhub Security Groups | Security Implementation |

### Success Metrics Implementation
| Metric | Monitoring Implementation |
|--------|------------------------------|
| EA available within 60 seconds | Provisioning time monitoring |
| Multi-channel communication | Channel-specific delivery confirmations |
| Business learning functional | Vector store business context metrics |
| Workflow creation during calls | Template-based workflow success rates |
| Per-customer isolation validated | MCP server isolation automated tests |
| 4 agents operational | Health checks + status endpoints |
| Multi-channel messaging | Channel-specific delivery confirmations |
| Agent learning functional | Vector store update metrics |
| Workflow creation working | N8n API success rates |
| Customer isolation validated | Security audit automated tests |

---

**Document Classification:** Technical Design Document - EA-First Architecture  
**Version:** 6.0 - Phase-1-PRD Aligned  
**Next Review:** Weekly during Phase 1 EA implementation  
**Success Criteria:** Executive Assistant deployed with per-customer isolation and conversational learning