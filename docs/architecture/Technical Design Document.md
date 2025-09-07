# AI Agency Platform - Technical Design Document (TDD)

**Document Type:** Technical Design Document  
**Version:** 6.0 - EA-First Architecture  
**Date:** August 29, 2025

## Executive Summary

### Vision Statement
Vendor-agnostic AI Agency Platform enabling ambitious professionals to deploy a premium-casual Executive Assistant that learns entire businesses through natural conversation and creates automations in real-time with complete per-customer isolation.

### Technical Innovation
- **Premium-Casual EA Core:** Sophisticated EA with approachable personality that handles everything through natural dialogue
- **Multi-Channel Casual Communication:** Natural voice conversations, WhatsApp messaging, and conversational email
- **Per-Customer MCP Servers:** Complete isolation via dedicated MCP server instances
- **Conversational Learning:** EA learns business through phone calls, WhatsApp, and email with personality consistency
- **Real-Time Workflow Creation:** EA creates n8n workflows during conversations
- **Personal Brand Intelligence:** Focus on career advancement, personal branding, and business growth
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
  ttsService: ElevenLabsTTS; // Premium-casual voice synthesis
  sttService: WhisperSTT;
  personalityEngine: CasualPersonalityEngine; // Maintains approachable tone across channels
  
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

### 5. Premium-Casual Communication Architecture

```typescript
// ElevenLabs Voice Synthesis for Natural Conversations
class PremiumCasualVoiceService {
  elevenLabsClient: ElevenLabsClient;
  voiceProfiles: Map<string, VoiceProfile>; // Customer-specific voice preferences
  personalityEngine: CasualPersonalityEngine;
  
  constructor() {
    this.elevenLabsClient = new ElevenLabsClient({
      apiKey: process.env.ELEVENLABS_API_KEY,
      timeout: 5000 // Quick response for natural conversation flow
    });
  }
  
  async synthesizeCasualResponse(
    text: string, 
    customerId: string, 
    conversationContext: ConversationContext
  ): Promise<AudioBuffer> {
    // Apply premium-casual personality transformation
    const casualText = await this.personalityEngine.transformToCasual(text, conversationContext);
    
    // Get customer's preferred voice profile (approachable, not corporate)
    const voiceProfile = this.voiceProfiles.get(customerId) || this.getDefaultCasualVoice();
    
    // Synthesize with ElevenLabs
    const audioResponse = await this.elevenLabsClient.textToSpeech({
      text: casualText,
      voice_id: voiceProfile.voiceId,
      model_id: "eleven_multilingual_v2", // Natural conversation model
      voice_settings: {
        stability: 0.75, // Consistent but not robotic
        similarity_boost: 0.8, // Natural voice characteristics
        style: 0.6, // Conversational style
        use_speaker_boost: true // Clear audio for phone calls
      }
    });
    
    return audioResponse.audio;
  }
  
  private getDefaultCasualVoice(): VoiceProfile {
    return {
      voiceId: "pNInz6obpgDQGcFmaJgB", // Adam - friendly male voice
      name: "Casual Assistant",
      personality: "approachable_professional",
      tone: "premium_casual"
    };
  }
}

// WhatsApp Business API Integration
class WhatsAppBusinessService {
  whatsappClient: WhatsAppBusinessClient;
  personalityEngine: CasualPersonalityEngine;
  businessMemory: BusinessMemorySystem;
  
  async handleIncomingMessage(message: WhatsAppMessage, customerId: string): Promise<void> {
    // Retrieve business context for personalized response
    const businessContext = await this.businessMemory.recallBusinessContext(
      message.text, 
      customerId
    );
    
    // Process with premium-casual EA personality
    const response = await this.generateCasualResponse(message, businessContext);
    
    // Send response maintaining conversational flow
    await this.sendCasualResponse(message.from, response, customerId);
    
    // Store interaction for business learning
    await this.businessMemory.learnBusiness({
      customerId,
      channel: 'whatsapp',
      input: message.text,
      output: response.text,
      businessInsights: response.insights,
      timestamp: Date.now()
    });
  }
  
  async sendCasualResponse(
    phoneNumber: string, 
    response: CasualResponse, 
    customerId: string
  ): Promise<void> {
    const message = {
      messaging_product: "whatsapp",
      to: phoneNumber,
      type: "text",
      text: {
        body: response.text
      }
    };
    
    // Add rich media if response includes suggestions or documents
    if (response.attachments?.length > 0) {
      message.type = "interactive";
      message.interactive = {
        type: "button",
        body: { text: response.text },
        action: {
          buttons: response.attachments.map(attachment => ({
            type: "reply",
            reply: {
              id: attachment.id,
              title: attachment.title
            }
          }))
        }
      };
    }
    
    await this.whatsappClient.sendMessage(message);
  }
}

// Premium-Casual Personality Engine
class CasualPersonalityEngine {
  conversationPatterns: ConversationPatternStore;
  toneAnalyzer: ToneAnalyzer;
  
  async transformToCasual(
    formalText: string, 
    context: ConversationContext
  ): Promise<string> {
    // Apply conversation patterns for premium-casual tone
    const patterns = await this.conversationPatterns.getPatternsFor(context.businessType);
    
    // Transform formal language to approachable while maintaining sophistication
    let casualText = formalText
      .replace(/I have identified/g, "I noticed")
      .replace(/I recommend that you/g, "You might want to")
      .replace(/Please find attached/g, "Here's what I've got for you")
      .replace(/I would suggest/g, "How about we")
      .replace(/At your earliest convenience/g, "when you get a chance");
    
    // Add motivational elements for ambitious professionals
    if (context.taskType === 'career_advancement') {
      casualText = this.addMotivationalTone(casualText, context);
    }
    
    // Ensure business context relevance
    if (context.businessInsights) {
      casualText = this.addBusinessContext(casualText, context.businessInsights);
    }
    
    return casualText;
  }
  
  private addMotivationalTone(text: string, context: ConversationContext): string {
    const motivationalPhrases = [
      "This is going to be great for your growth",
      "You're building something awesome here",
      "Let's get you ahead of the competition",
      "This will definitely boost your profile"
    ];
    
    // Add contextually appropriate motivation
    return `${text} ${motivationalPhrases[Math.floor(Math.random() * motivationalPhrases.length)]}.`;
  }
}

// Personal Brand Intelligence System
class PersonalBrandIntelligence {
  socialMediaAnalyzer: SocialMediaAnalyzer;
  careerAdvancementEngine: CareerAdvancementEngine;
  businessGrowthAnalyzer: BusinessGrowthAnalyzer;
  
  async generatePersonalBrandInsights(customerId: string): Promise<PersonalBrandInsights> {
    const [socialMetrics, careerOpportunities, businessGrowth] = await Promise.all([
      this.socialMediaAnalyzer.analyzePersonalBrand(customerId),
      this.careerAdvancementEngine.identifyOpportunities(customerId),
      this.businessGrowthAnalyzer.assessGrowthPotential(customerId)
    ]);
    
    return {
      socialMetrics: {
        engagement_rate: socialMetrics.engagement,
        brand_consistency: socialMetrics.consistency,
        growth_trajectory: socialMetrics.growth,
        recommendations: this.generateSocialRecommendations(socialMetrics)
      },
      careerOpportunities: {
        networking_opportunities: careerOpportunities.networking,
        skill_gaps: careerOpportunities.skills,
        market_positioning: careerOpportunities.positioning,
        action_items: this.generateCareerActions(careerOpportunities)
      },
      businessGrowth: {
        revenue_optimization: businessGrowth.revenue,
        process_automation: businessGrowth.automation,
        competitive_advantages: businessGrowth.advantages,
        growth_strategies: this.generateGrowthStrategies(businessGrowth)
      }
    };
  }
}
```

### 6. Per-Customer MCP Server Architecture

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
  voice_synthesis_time: <2 seconds for ElevenLabs TTS generation
  whatsapp_message_delivery: <1 second for casual messaging
  personality_consistency: <500ms for tone transformation
  provisioning_time: <30 seconds from purchase to working EA
  memory_recall: <500ms for business context retrieval
  workflow_creation: <2 minutes for template-based workflows
  concurrent_eas: 100+ active Executive Assistants with premium-casual personalities
  personal_brand_analysis: <5 seconds for social media insights
  
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
  whatsapp_business: Meta WhatsApp Business API with casual messaging
  elevenlabs_voice: ElevenLabs TTS with premium-casual voice profiles
  email_service: SMTP/IMAP providers (Gmail, Outlook) with conversational tone
  phone_service: Twilio Voice API + ElevenLabs TTS + Whisper STT
  personality_engine: Premium-casual personality consistency across channels
  
Personal_Brand_Intelligence:
  social_media_analyzer: LinkedIn, Instagram, Twitter brand analysis
  career_advancement: Networking and opportunity identification
  business_growth_analyzer: Revenue and process optimization insights
  content_creation_assistant: Brand-consistent content generation
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