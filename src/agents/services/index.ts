/**
 * Service Layer Index - Export all direct SDK integrations
 * Centralized access point for hybrid MCP + SDK services
 */

// Direct SDK Services (replacing missing MCP servers)
export { EmailService, emailService } from './email-service';
export { InstagramService, instagramService } from './instagram-service';
export { TemporalService, temporalService } from './temporal-service';
export { DockerService, dockerService } from './docker-service';
export { SlackService, slackService } from './slack-service';

// Re-export agent base class
export { AgentBase } from '../base/agent-base';
export type { AgentConfig, AgentMemory, AgentMetrics } from '../base/agent-base';

/**
 * Service Registry - Track all available services
 */
export const SERVICE_REGISTRY = {
  // Direct SDK Integrations (5 services)
  email: {
    name: 'SendGrid Email Service',
    type: 'direct-sdk',
    package: '@sendgrid/mail',
    status: 'active',
    capabilities: ['transactional_email', 'bulk_email', 'template_email']
  },
  instagram: {
    name: 'Instagram Graph API Service',
    type: 'direct-sdk',
    package: 'axios (Graph API)',
    status: 'active',
    capabilities: ['post_content', 'get_insights', 'manage_account']
  },
  temporal: {
    name: 'Temporal Workflow Service',
    type: 'direct-sdk',
    package: '@temporalio/client',
    status: 'active',
    capabilities: ['durable_workflows', '24_7_operations', 'scheduling']
  },
  docker: {
    name: 'Docker Orchestration Service',
    type: 'direct-sdk',
    package: 'dockerode',
    status: 'active',
    capabilities: ['container_management', 'service_scaling', 'deployment']
  },
  slack: {
    name: 'Slack Team Coordination Service',
    type: 'direct-sdk',
    package: '@slack/web-api',
    status: 'active',
    capabilities: ['team_coordination', 'notifications', 'channel_management']
  },
  
  // Working MCP Servers (5 servers)
  stripe: {
    name: 'Stripe Payments',
    type: 'mcp-server',
    package: '@stripe/mcp',
    status: 'active',
    capabilities: ['payment_processing', 'subscription_management', 'invoicing']
  },
  linear: {
    name: 'Linear Project Management',
    type: 'mcp-server',
    package: '@mseep/linear-mcp-server',
    status: 'active',
    capabilities: ['project_management', 'issue_tracking', 'sprint_planning']
  },
  qdrant: {
    name: 'Qdrant Vector Database',
    type: 'mcp-server',
    package: 'better-qdrant-mcp-server',
    status: 'active',
    capabilities: ['vector_storage', 'semantic_search', 'agent_memory']
  },
  whatsapp: {
    name: 'WhatsApp Business API',
    type: 'mcp-server',
    package: '@jlucaso1/whatsapp-mcp-ts',
    status: 'active',
    capabilities: ['messaging', 'customer_communication', 'media_sharing']
  },
  elevenlabs: {
    name: 'ElevenLabs Voice Synthesis',
    type: 'mcp-server',
    package: '@microagents/mcp-server-elevenlabs',
    status: 'active',
    capabilities: ['voice_synthesis', 'speech_generation', 'audio_processing']
  }
};

/**
 * Check service health status
 */
export async function checkServiceHealth(): Promise<Record<string, boolean>> {
  const health: Record<string, boolean> = {};
  
  try {
    // Test direct SDK services
    health.email = !!process.env.SENDGRID_API_KEY;
    health.instagram = !!process.env.INSTAGRAM_ACCESS_TOKEN;
    health.temporal = !!process.env.TEMPORAL_SERVER_URL;
    health.docker = !!process.env.DOCKER_SOCKET_PATH;
    health.slack = !!process.env.SLACK_BOT_TOKEN;
    
    // Test MCP servers (environment variables)
    health.stripe = !!process.env.STRIPE_SECRET_KEY;
    health.linear = !!process.env.LINEAR_API_KEY;
    health.qdrant = !!process.env.QDRANT_ENDPOINT;
    health.whatsapp = !!process.env.WHATSAPP_SESSION_ID;
    health.elevenlabs = !!process.env.ELEVENLABS_API_KEY;
    
  } catch (error) {
    console.error('Service health check failed:', error);
  }
  
  return health;
}

/**
 * Get service configuration for agent initialization
 */
export function getServiceConfig(agentType: string): string[] {
  const serviceMap: Record<string, string[]> = {
    'social-media-manager': ['instagram', 'slack', 'temporal', 'email'],
    'finance-agent': ['email', 'slack', 'temporal', 'stripe'],
    'marketing-agent': ['email', 'slack', 'temporal', 'instagram'],
    'business-agent': ['email', 'slack', 'temporal', 'docker', 'linear']
  };
  
  return serviceMap[agentType] || ['email', 'slack', 'temporal'];
}

/**
 * Initialize all services for health check
 */
export async function initializeServices() {
  console.log('Initializing AI Agency Platform services...');
  
  const health = await checkServiceHealth();
  const healthyServices = Object.entries(health).filter(([_, status]) => status).map(([name, _]) => name);
  const unhealthyServices = Object.entries(health).filter(([_, status]) => !status).map(([name, _]) => name);
  
  console.log(`✅ Healthy services (${healthyServices.length}):`, healthyServices.join(', '));
  
  if (unhealthyServices.length > 0) {
    console.log(`⚠️  Services needing configuration (${unhealthyServices.length}):`, unhealthyServices.join(', '));
    console.log('Update .env file with required API keys and endpoints');
  }
  
  return {
    totalServices: Object.keys(SERVICE_REGISTRY).length,
    healthyServices: healthyServices.length,
    healthyServicesList: healthyServices,
    unhealthyServices: unhealthyServices.length,
    unhealthyServicesList: unhealthyServices,
    healthStatus: health
  };
}