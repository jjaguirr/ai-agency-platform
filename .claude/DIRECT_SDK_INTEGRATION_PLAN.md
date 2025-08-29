# Direct SDK Integration Plan for Missing MCP Servers

## Overview
While researching MCP servers, several don't exist as npm packages yet. This document outlines the direct SDK integration strategy for maintaining full functionality.

## ✅ **Working MCP Servers (5 total)**
1. **Stripe Payments** - `@stripe/mcp`
2. **Linear Project Management** - `@mseep/linear-mcp-server`
3. **Qdrant Vector Database** - `better-qdrant-mcp-server`
4. **WhatsApp Business** - `@jlucaso1/whatsapp-mcp-ts`
5. **ElevenLabs Voice** - `@microagents/mcp-server-elevenlabs`

## 🔧 **Direct SDK Integration Required (5 components)**

### 1. SendGrid Email Integration
**Why needed**: Customer communication, transactional emails
**SDK**: `@sendgrid/mail`
**Implementation**:
```typescript
// agents/email-service.ts
import sgMail from '@sendgrid/mail';

sgMail.setApiKey(process.env.SENDGRID_API_KEY);

export async function sendEmail(to: string, subject: string, content: string) {
  const msg = {
    to,
    from: 'noreply@aiagencyplatform.com',
    subject,
    html: content,
  };
  return await sgMail.send(msg);
}
```

### 2. Instagram Graph API Integration
**Why needed**: Social Media Manager agent functionality
**SDK**: Direct API calls with axios
**Implementation**:
```typescript
// agents/instagram-service.ts
import axios from 'axios';

export class InstagramService {
  private accessToken = process.env.INSTAGRAM_ACCESS_TOKEN;
  
  async getUserMedia(userId: string) {
    const response = await axios.get(
      `https://graph.instagram.com/v20.0/${userId}/media`,
      { params: { access_token: this.accessToken } }
    );
    return response.data;
  }
  
  async publishPhoto(imageUrl: string, caption: string) {
    // Implementation for posting content
  }
}
```

### 3. Temporal Workflow Orchestration
**Why needed**: 24/7 agent operations, durable workflows
**SDK**: `@temporalio/client` + `@temporalio/worker`
**Implementation**:
```typescript
// agents/temporal-service.ts
import { Client, Connection } from '@temporalio/client';

export async function createTemporalClient() {
  return Client.create({
    connection: await Connection.connect({
      address: process.env.TEMPORAL_SERVER_URL,
    }),
  });
}

export async function startAgentWorkflow(agentType: string, customerId: string) {
  const client = await createTemporalClient();
  return await client.workflow.start('AgentWorkflow', {
    args: [{ agentType, customerId }],
    taskQueue: 'agent-task-queue',
    workflowId: `agent-${agentType}-${customerId}`,
  });
}
```

### 4. Docker Orchestration Integration
**Why needed**: Container deployment and scaling
**SDK**: `dockerode`
**Implementation**:
```typescript
// agents/docker-service.ts
import Docker from 'dockerode';

export class DockerService {
  private docker = new Docker({ socketPath: process.env.DOCKER_SOCKET_PATH });
  
  async deployContainer(image: string, config: any) {
    const container = await this.docker.createContainer({
      Image: image,
      ...config,
    });
    await container.start();
    return container;
  }
  
  async scaleService(serviceName: string, replicas: number) {
    // Implementation for service scaling
  }
}
```

### 5. Slack Team Coordination Integration
**Why needed**: Agent coordination, notifications
**SDK**: `@slack/web-api`
**Implementation**:
```typescript
// agents/slack-service.ts
import { WebClient } from '@slack/web-api';

export class SlackService {
  private client = new WebClient(process.env.SLACK_BOT_TOKEN);
  
  async sendMessage(channel: string, text: string) {
    return await this.client.chat.postMessage({
      channel,
      text,
    });
  }
  
  async createChannel(name: string, purpose: string) {
    return await this.client.conversations.create({
      name,
      purpose: { value: purpose },
    });
  }
}
```

## 📁 **Recommended File Structure**
```
src/
├── agents/
│   ├── services/
│   │   ├── email-service.ts          # SendGrid integration
│   │   ├── instagram-service.ts      # Instagram Graph API
│   │   ├── temporal-service.ts       # Temporal workflows
│   │   ├── docker-service.ts         # Docker orchestration
│   │   └── slack-service.ts          # Slack coordination
│   └── base/
│       └── agent-base.ts             # Base agent with all service access
```

## 🔄 **Agent Enhancement Strategy**

### Phase 1A: Service Layer Implementation (Week 1)
1. Create service classes for each missing MCP server
2. Implement core functionality (send email, post to Instagram, etc.)
3. Add proper error handling and retry logic
4. Write unit tests for each service

### Phase 1B: Agent Integration (Week 2)
1. Update agent base class to include all services
2. Modify existing agents to use service layer
3. Add service access to agent tools configuration
4. Test end-to-end functionality

### Phase 1C: Coordination Layer (Week 3)
1. Implement cross-service coordination (Slack + Temporal)
2. Add monitoring and alerting via Slack
3. Set up workflow orchestration via Temporal
4. Validate complete agent ecosystem

## 🎯 **Benefits of Hybrid Approach**
- **Reliability**: Using official SDKs instead of community MCP servers
- **Flexibility**: Direct control over API integration and error handling
- **Performance**: No additional MCP protocol overhead for simple operations
- **Maintenance**: Easier to maintain and debug than community packages

## 📋 **Environment Variables Summary**
```bash
# MCP Servers (5)
STRIPE_SECRET_KEY=sk_test_...
LINEAR_API_KEY=lin_api_...
QDRANT_URL=http://qdrant:6333
WHATSAPP_SESSION_ID=...
ELEVENLABS_API_KEY=...

# Direct SDK Integration (5)
SENDGRID_API_KEY=SG....
INSTAGRAM_ACCESS_TOKEN=...
TEMPORAL_SERVER_URL=temporal:7233
DOCKER_SOCKET_PATH=/var/run/docker.sock
SLACK_BOT_TOKEN=xoxb-...
```

This hybrid approach provides the best of both worlds: verified MCP servers where available, and reliable direct SDK integration where needed.