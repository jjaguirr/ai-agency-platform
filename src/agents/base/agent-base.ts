/**
 * Agent Base Class - Foundation for all AI Agency Platform agents
 * Provides unified access to both MCP servers and direct SDK services
 */
import { EventEmitter } from 'events';
import { emailService, EmailService } from '../services/email-service';
import { instagramService, InstagramService } from '../services/instagram-service';
import { temporalService, TemporalService } from '../services/temporal-service';
import { dockerService, DockerService } from '../services/docker-service';
import { slackService, SlackService } from '../services/slack-service';

export interface AgentConfig {
  agentId: string;
  agentType: 'social-media-manager' | 'finance-agent' | 'marketing-agent' | 'business-agent';
  customerId: string;
  settings: Record<string, any>;
  mcpTools?: string[];
  enabledServices?: string[];
}

export interface AgentMemory {
  shortTerm: Record<string, any>;
  longTerm: Record<string, any>;
  learnings: Array<{
    timestamp: string;
    category: string;
    observation: string;
    impact: 'positive' | 'negative' | 'neutral';
  }>;
}

export interface AgentMetrics {
  tasksCompleted: number;
  successRate: number;
  averageResponseTime: number;
  customerSatisfaction: number;
  lastActive: string;
  errors: Array<{
    timestamp: string;
    error: string;
    context: string;
  }>;
}

export abstract class AgentBase extends EventEmitter {
  protected config: AgentConfig;
  protected memory: AgentMemory;
  protected metrics: AgentMetrics;
  protected isActive: boolean = false;
  
  // Direct SDK Services (Hybrid approach for missing MCP servers)
  protected emailService: EmailService;
  protected instagramService: InstagramService;
  protected temporalService: TemporalService;
  protected dockerService: DockerService;
  protected slackService: SlackService;

  constructor(config: AgentConfig) {
    super();
    
    this.config = config;
    this.memory = {
      shortTerm: {},
      longTerm: {},
      learnings: []
    };
    
    this.metrics = {
      tasksCompleted: 0,
      successRate: 0,
      averageResponseTime: 0,
      customerSatisfaction: 0,
      lastActive: new Date().toISOString(),
      errors: []
    };

    // Initialize direct SDK services
    this.emailService = emailService;
    this.instagramService = instagramService;
    this.temporalService = temporalService;
    this.dockerService = dockerService;
    this.slackService = slackService;

    this.setupEventListeners();
    this.initializeAgent();
  }

  /**
   * Abstract methods that must be implemented by specific agent types
   */
  abstract initialize(): Promise<void>;
  abstract processTask(task: any): Promise<any>;
  abstract getCapabilities(): string[];
  abstract getStatus(): Record<string, any>;

  /**
   * Initialize the agent
   */
  private async initializeAgent() {
    try {
      console.log(`Initializing ${this.config.agentType} agent for customer ${this.config.customerId}`);
      
      // Start Temporal workflow for 24/7 operations
      if (this.config.enabledServices?.includes('temporal')) {
        await this.startAgentWorkflow();
      }
      
      // Create Slack coordination channel if enabled
      if (this.config.enabledServices?.includes('slack')) {
        await this.setupSlackCoordination();
      }
      
      // Call agent-specific initialization
      await this.initialize();
      
      this.isActive = true;
      this.emit('agent:initialized', { agentId: this.config.agentId });
      
    } catch (error: any) {
      console.error(`Agent initialization failed:`, error);
      this.recordError('initialization', error.message);
      throw new Error(`Agent initialization failed: ${error.message}`);
    }
  }

  /**
   * Start Temporal workflow for durable agent operations
   */
  private async startAgentWorkflow() {
    try {
      const workflowHandle = await this.temporalService.startAgentWorkflow({
        agentType: this.config.agentType,
        customerId: this.config.customerId,
        config: this.config.settings
      });
      
      this.memory.longTerm.temporalWorkflowId = workflowHandle.workflowId;
      this.emit('workflow:started', { workflowId: workflowHandle.workflowId });
      
    } catch (error: any) {
      console.error('Failed to start agent workflow:', error);
      this.recordError('temporal', error.message);
    }
  }

  /**
   * Setup Slack coordination channel
   */
  private async setupSlackCoordination() {
    try {
      const channel = await this.slackService.createAgentCoordinationChannel(
        this.config.customerId,
        [this.config.agentType]
      );
      
      this.memory.longTerm.slackChannelId = channel.id;
      
      // Send agent online notification
      await this.slackService.sendNotification(
        channel.id,
        'Agent Online',
        `${this.config.agentType} agent is now active and ready to serve customer ${this.config.customerId}`,
        'success'
      );
      
    } catch (error: any) {
      console.error('Failed to setup Slack coordination:', error);
      this.recordError('slack', error.message);
    }
  }

  /**
   * Setup event listeners for service integration
   */
  private setupEventListeners() {
    // Docker service events
    this.dockerService.on('container:deployed', (data) => {
      this.emit('service:docker:deployed', data);
    });

    // Slack service events
    this.slackService.on('message:sent', (data) => {
      this.emit('service:slack:message', data);
    });

    // Agent-specific events
    this.on('task:completed', (data) => {
      this.updateMetrics('task_completed', data);
    });

    this.on('task:failed', (data) => {
      this.updateMetrics('task_failed', data);
    });
  }

  /**
   * Execute a task with error handling and metrics tracking
   */
  async executeTask(task: any): Promise<any> {
    const startTime = Date.now();
    
    try {
      this.emit('task:started', { task, agentId: this.config.agentId });
      
      const result = await this.processTask(task);
      
      const duration = Date.now() - startTime;
      this.emit('task:completed', { task, result, duration });
      
      // Record learning from successful task
      this.recordLearning('task_execution', `Successfully completed ${task.type}`, 'positive');
      
      return result;
      
    } catch (error: any) {
      const duration = Date.now() - startTime;
      this.emit('task:failed', { task, error: error.message, duration });
      
      this.recordError('task_execution', error.message, task);
      this.recordLearning('task_execution', `Failed to complete ${task.type}: ${error.message}`, 'negative');
      
      throw error;
    }
  }

  /**
   * Send email using integrated email service
   */
  async sendEmail(params: {
    to: string;
    subject: string;
    html: string;
    templateId?: string;
    dynamicTemplateData?: Record<string, any>;
  }) {
    try {
      return await this.emailService.sendEmail(params);
    } catch (error: any) {
      this.recordError('email', error.message, params);
      throw error;
    }
  }

  /**
   * Post to Instagram using integrated service
   */
  async postToInstagram(params: {
    userId: string;
    imageUrl: string;
    caption: string;
    locationId?: string;
  }) {
    try {
      return await this.instagramService.publishPhoto(params);
    } catch (error: any) {
      this.recordError('instagram', error.message, params);
      throw error;
    }
  }

  /**
   * Send Slack notification
   */
  async sendSlackNotification(message: string, priority: 'info' | 'warning' | 'error' | 'success' = 'info') {
    try {
      if (!this.memory.longTerm.slackChannelId) {
        throw new Error('Slack channel not initialized');
      }
      
      return await this.slackService.sendNotification(
        this.memory.longTerm.slackChannelId,
        `${this.config.agentType} Update`,
        message,
        priority
      );
    } catch (error: any) {
      this.recordError('slack', error.message, { message });
      throw error;
    }
  }

  /**
   * Update agent memory
   */
  updateMemory(key: string, value: any, isLongTerm: boolean = false) {
    if (isLongTerm) {
      this.memory.longTerm[key] = value;
    } else {
      this.memory.shortTerm[key] = value;
    }
    
    this.emit('memory:updated', { key, value, isLongTerm });
  }

  /**
   * Record learning from agent experience
   */
  recordLearning(category: string, observation: string, impact: 'positive' | 'negative' | 'neutral') {
    const learning = {
      timestamp: new Date().toISOString(),
      category,
      observation,
      impact
    };
    
    this.memory.learnings.push(learning);
    
    // Keep only last 1000 learnings
    if (this.memory.learnings.length > 1000) {
      this.memory.learnings = this.memory.learnings.slice(-1000);
    }
    
    this.emit('learning:recorded', learning);
  }

  /**
   * Record error for debugging and improvement
   */
  recordError(context: string, error: string, data?: any) {
    const errorRecord = {
      timestamp: new Date().toISOString(),
      error,
      context: `${context}: ${JSON.stringify(data || {})}`
    };
    
    this.metrics.errors.push(errorRecord);
    
    // Keep only last 100 errors
    if (this.metrics.errors.length > 100) {
      this.metrics.errors = this.metrics.errors.slice(-100);
    }
    
    this.emit('error:recorded', errorRecord);
  }

  /**
   * Update agent metrics
   */
  updateMetrics(eventType: string, data: any) {
    this.metrics.lastActive = new Date().toISOString();
    
    switch (eventType) {
      case 'task_completed':
        this.metrics.tasksCompleted++;
        this.updateSuccessRate(true);
        this.updateResponseTime(data.duration);
        break;
        
      case 'task_failed':
        this.updateSuccessRate(false);
        break;
    }
    
    this.emit('metrics:updated', this.metrics);
  }

  /**
   * Update success rate metric
   */
  private updateSuccessRate(success: boolean) {
    const totalTasks = this.metrics.tasksCompleted + this.metrics.errors.length;
    const successfulTasks = success ? this.metrics.tasksCompleted : this.metrics.tasksCompleted;
    this.metrics.successRate = totalTasks > 0 ? (successfulTasks / totalTasks) * 100 : 0;
  }

  /**
   * Update average response time
   */
  private updateResponseTime(duration: number) {
    const currentAvg = this.metrics.averageResponseTime;
    const taskCount = this.metrics.tasksCompleted;
    
    this.metrics.averageResponseTime = taskCount > 1 
      ? ((currentAvg * (taskCount - 1)) + duration) / taskCount
      : duration;
  }

  /**
   * Get comprehensive agent status
   */
  getAgentStatus(): Record<string, any> {
    return {
      agentId: this.config.agentId,
      agentType: this.config.agentType,
      customerId: this.config.customerId,
      isActive: this.isActive,
      capabilities: this.getCapabilities(),
      metrics: this.metrics,
      memory: {
        shortTermKeys: Object.keys(this.memory.shortTerm),
        longTermKeys: Object.keys(this.memory.longTerm),
        learningCount: this.memory.learnings.length
      },
      services: {
        email: !!this.config.enabledServices?.includes('email'),
        instagram: !!this.config.enabledServices?.includes('instagram'),
        temporal: !!this.config.enabledServices?.includes('temporal'),
        docker: !!this.config.enabledServices?.includes('docker'),
        slack: !!this.config.enabledServices?.includes('slack')
      },
      status: this.getStatus()
    };
  }

  /**
   * Graceful agent shutdown
   */
  async shutdown() {
    try {
      console.log(`Shutting down ${this.config.agentType} agent...`);
      
      this.isActive = false;
      
      // Cancel Temporal workflow if running
      if (this.memory.longTerm.temporalWorkflowId) {
        await this.temporalService.cancelWorkflow(
          this.memory.longTerm.temporalWorkflowId,
          'Agent shutdown'
        );
      }
      
      // Send offline notification to Slack
      if (this.memory.longTerm.slackChannelId) {
        await this.slackService.sendNotification(
          this.memory.longTerm.slackChannelId,
          'Agent Offline',
          `${this.config.agentType} agent is shutting down`,
          'warning'
        );
      }
      
      this.emit('agent:shutdown', { agentId: this.config.agentId });
      
    } catch (error: any) {
      console.error('Agent shutdown error:', error);
      this.recordError('shutdown', error.message);
    }
  }
}

export default AgentBase;