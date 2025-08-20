/**
 * Langfuse + MCPhub Integration Bridge
 * Connects Infrastructure Agents with Langfuse for prompt management and observability
 * 
 * This bridge enables:
 * - Dynamic prompt loading from Langfuse
 * - Multi-model AI execution with tracing
 * - Cost optimization and performance tracking
 * - Customer-specific analytics and insights
 */

const { Langfuse } = require('langfuse');
const Redis = require('redis');

class LangfuseMCPhubBridge {
  constructor(config = {}) {
    // Langfuse configuration
    this.langfuse = new Langfuse({
      publicKey: process.env.LANGFUSE_PUBLIC_KEY,
      secretKey: process.env.LANGFUSE_SECRET_KEY,
      baseUrl: process.env.LANGFUSE_BASE_URL || 'http://localhost:3001'
    });
    
    // Redis for cross-system communication
    this.redis = Redis.createClient({
      url: process.env.REDIS_URL || 'redis://localhost:6379'
    });
    
    // MCPhub API configuration
    this.mcphubBaseUrl = process.env.MCPHUB_BASE_URL || 'http://localhost:3000';
    this.mcphubApiKey = process.env.MCPHUB_API_KEY;
    
    // AI Model configurations
    this.aiModels = {
      'openai-gpt-4o': {
        provider: 'openai',
        model: 'gpt-4o',
        costPerToken: 0.00006, // $0.06 per 1K tokens
        maxTokens: 8192,
        supportedFeatures: ['text', 'vision', 'function-calling']
      },
      'claude-3.5-sonnet': {
        provider: 'anthropic',
        model: 'claude-3-5-sonnet-20241022',
        costPerToken: 0.000015, // $0.015 per 1K tokens
        maxTokens: 8192,
        supportedFeatures: ['text', 'vision', 'function-calling']
      },
      'meta-llama-3': {
        provider: 'meta',
        model: 'llama-3-70b',
        costPerToken: 0.000001, // $0.001 per 1K tokens (local/cheaper)
        maxTokens: 4096,
        supportedFeatures: ['text']
      },
      'deepseek-v2': {
        provider: 'deepseek',
        model: 'deepseek-chat',
        costPerToken: 0.000001, // $0.001 per 1K tokens
        maxTokens: 4096,
        supportedFeatures: ['text', 'function-calling']
      }
    };
    
    this.initialize();
  }
  
  async initialize() {
    try {
      await this.redis.connect();
      console.log('✅ Langfuse-MCPhub Bridge initialized successfully');
    } catch (error) {
      console.error('❌ Bridge initialization error:', error.message);
      throw error;
    }
  }
  
  /**
   * Get versioned prompt from Langfuse for Infrastructure agents
   */
  async getInfrastructureAgentPrompt(agentType, version = 'latest') {
    try {
      const promptName = `infrastructure-agent-${agentType}`;
      const prompt = await this.langfuse.getPrompt(promptName, version);
      
      return {
        name: promptName,
        version: prompt.version,
        content: prompt.prompt,
        config: prompt.config || {},
        labels: prompt.labels || []
      };
    } catch (error) {
      console.error(`Error loading prompt for ${agentType}:`, error.message);
      throw new Error(`Failed to load prompt for Infrastructure agent: ${agentType}`);
    }
  }
  
  /**
   * Execute Infrastructure Agent with Langfuse tracing and multi-model support
   */
  async executeInfrastructureAgent(params) {
    const {
      agentType,
      input,
      customerId = null,
      aiModel = 'auto-select',
      context = {},
      sessionId = null
    } = params;
    
    // Create Langfuse trace for this execution
    const trace = this.langfuse.trace({
      name: `infrastructure-agent-${agentType}`,
      userId: customerId,
      sessionId: sessionId,
      metadata: {
        agentType,
        requestedAiModel: aiModel,
        mcphubGroup: customerId ? `customer-${customerId}` : 'business-operations',
        context
      }
    });
    
    try {
      // Get versioned prompt from Langfuse
      const promptData = await this.getInfrastructureAgentPrompt(agentType);
      
      // Select optimal AI model
      const selectedModel = await this.selectOptimalAIModel(agentType, aiModel, customerId);
      
      // Prepare prompt with context
      const compiledPrompt = this.compilePrompt(promptData.content, {
        customerId,
        customerName: context.customerName,
        customerIndustry: context.customerIndustry,
        ...context
      });
      
      // Create generation tracking
      const generation = trace.generation({
        name: `${agentType}-generation`,
        model: selectedModel,
        modelParameters: {
          temperature: promptData.config.temperature || 0.5,
          maxTokens: promptData.config.maxTokens || 3000,
          topP: promptData.config.topP || 0.9
        },
        input: input,
        prompt: compiledPrompt
      });
      
      // Execute through MCPhub with selected model
      const startTime = Date.now();
      const response = await this.executeThroughMCPhub({
        agentType,
        systemPrompt: compiledPrompt,
        userInput: input,
        aiModel: selectedModel,
        customerId,
        traceId: trace.id
      });
      const executionTime = Date.now() - startTime;
      
      // Calculate cost
      const totalTokens = response.usage?.totalTokens || 0;
      const modelConfig = this.aiModels[selectedModel];
      const cost = totalTokens * modelConfig.costPerToken;
      
      // Complete generation tracking
      generation.end({
        output: response.content,
        usage: {
          promptTokens: response.usage?.promptTokens || 0,
          completionTokens: response.usage?.completionTokens || 0,
          totalTokens: totalTokens
        },
        level: response.success ? 'DEFAULT' : 'ERROR'
      });
      
      // Track performance metrics
      await this.trackPerformanceMetrics({
        agentType,
        aiModel: selectedModel,
        customerId,
        executionTime,
        tokenUsage: response.usage,
        cost,
        success: response.success
      });
      
      // Track customer-specific metrics for LAUNCH bots
      if (customerId && agentType === 'launch-bot') {
        await this.trackLAUNCHBotMetrics(customerId, response, executionTime);
      }
      
      // Send cross-system status update
      await this.sendCrossSystemUpdate({
        type: 'infrastructure-agent-execution',
        agentType,
        customerId,
        success: response.success,
        executionTime,
        traceId: trace.id
      });
      
      return {
        ...response,
        metadata: {
          traceId: trace.id,
          generationId: generation.id,
          aiModel: selectedModel,
          executionTime,
          cost,
          promptVersion: promptData.version
        }
      };
      
    } catch (error) {
      // Log error event
      trace.event({
        name: 'infrastructure-agent-error',
        level: 'ERROR',
        metadata: {
          error: error.message,
          agentType,
          aiModel,
          customerId
        }
      });
      
      throw error;
    } finally {
      await trace.finalize();
    }
  }
  
  /**
   * Intelligent AI model selection based on agent type, cost, and performance
   */
  async selectOptimalAIModel(agentType, preference, customerId = null) {
    if (preference !== 'auto-select') {
      return preference;
    }
    
    // Customer-specific model preferences
    if (customerId) {
      const customerPrefs = await this.getCustomerAIPreferences(customerId);
      if (customerPrefs?.preferredModel) {
        return customerPrefs.preferredModel;
      }
    }
    
    // Get historical performance data from Langfuse
    try {
      const performanceData = await this.getModelPerformanceData(agentType);
      
      // Select based on cost/performance optimization
      const modelSelection = this.optimizeModelSelection(agentType, performanceData);
      return modelSelection;
    } catch (error) {
      console.warn('Using fallback model selection due to performance data error:', error.message);
    }
    
    // Fallback: Agent type-specific optimal models
    const agentModelMap = {
      'research': 'openai-gpt-4o', // Best for research and analysis
      'business': 'claude-3.5-sonnet', // Best for data analysis and reasoning
      'creative': 'openai-gpt-4o', // Best for content generation and creativity
      'development': 'claude-3.5-sonnet', // Best for code and infrastructure
      'launch-bot': 'claude-3.5-sonnet', // Best for conversation and configuration
      'n8n-workflow': 'openai-gpt-4o' // Best for workflow design and automation
    };
    
    return agentModelMap[agentType] || 'claude-3.5-sonnet';
  }
  
  /**
   * Compile prompt template with dynamic context
   */
  compilePrompt(promptTemplate, context) {
    let compiled = promptTemplate;
    
    // Simple template compilation (can be enhanced with proper templating engine)
    for (const [key, value] of Object.entries(context)) {
      if (value !== undefined && value !== null) {
        compiled = compiled.replace(new RegExp(`{{${key}}}`, 'g'), value);
      }
    }
    
    // Handle conditional sections
    compiled = compiled.replace(/{{#if\s+(\w+)}}([\s\S]*?){{\/if}}/g, (match, conditionKey, content) => {
      return context[conditionKey] ? content : '';
    });
    
    return compiled;
  }
  
  /**
   * Execute agent through MCPhub with proper group routing
   */
  async executeThroughMCPhub(params) {
    const {
      agentType,
      systemPrompt,
      userInput,
      aiModel,
      customerId,
      traceId
    } = params;
    
    try {
      const mcphubEndpoint = `${this.mcphubBaseUrl}/api/v1/agents/execute`;
      
      const requestBody = {
        agentType,
        systemPrompt,
        userInput,
        aiModel,
        customerId,
        traceId,
        group: customerId ? `customer-${customerId}` : 'business-operations'
      };
      
      const response = await fetch(mcphubEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.mcphubApiKey}`,
          'X-Langfuse-Trace-Id': traceId
        },
        body: JSON.stringify(requestBody)
      });
      
      if (!response.ok) {
        throw new Error(`MCPhub execution failed: ${response.status} ${response.statusText}`);
      }
      
      return await response.json();
      
    } catch (error) {
      console.error('MCPhub execution error:', error.message);
      throw new Error(`Infrastructure agent execution failed: ${error.message}`);
    }
  }
  
  /**
   * Track performance metrics in Langfuse and local database
   */
  async trackPerformanceMetrics(metrics) {
    try {
      // Send to Langfuse for analytics
      await this.langfuse.event({
        name: 'infrastructure-agent-performance',
        metadata: metrics
      });
      
      // Store in local performance tracking (if database available)
      await this.storeLocalMetrics(metrics);
      
    } catch (error) {
      console.error('Performance tracking error:', error.message);
    }
  }
  
  /**
   * Track LAUNCH bot specific metrics for customer success
   */
  async trackLAUNCHBotMetrics(customerId, response, executionTime) {
    try {
      const metrics = {
        customerId,
        success: response.success,
        executionTime,
        configurationProgress: response.configurationProgress || 0,
        toolsConfigured: response.toolsConfigured || [],
        customerSatisfaction: response.customerSatisfaction
      };
      
      await this.langfuse.event({
        name: 'launch-bot-interaction',
        userId: customerId,
        metadata: metrics
      });
      
      // Check if customer onboarding completed in under 60 seconds
      if (metrics.configurationProgress === 100 && executionTime <= 60000) {
        await this.langfuse.event({
          name: 'launch-bot-success',
          userId: customerId,
          metadata: {
            ...metrics,
            successTarget: 60000,
            actualTime: executionTime,
            achieved: true
          }
        });
      }
      
    } catch (error) {
      console.error('LAUNCH bot metrics tracking error:', error.message);
    }
  }
  
  /**
   * Send cross-system status updates via Redis
   */
  async sendCrossSystemUpdate(update) {
    try {
      const message = {
        id: `update-${Date.now()}`,
        timestamp: new Date().toISOString(),
        source: 'infrastructure-agent',
        ...update
      };
      
      await this.redis.publish('infrastructure:status', JSON.stringify(message));
    } catch (error) {
      console.error('Cross-system update error:', error.message);
    }
  }
  
  /**
   * Get customer AI model preferences
   */
  async getCustomerAIPreferences(customerId) {
    try {
      const response = await fetch(`${this.mcphubBaseUrl}/api/v1/customers/${customerId}/preferences`, {
        headers: {
          'Authorization': `Bearer ${this.mcphubApiKey}`
        }
      });
      
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Customer preferences retrieval error:', error.message);
    }
    
    return null;
  }
  
  /**
   * Get model performance data from Langfuse analytics
   */
  async getModelPerformanceData(agentType) {
    try {
      // This would use Langfuse analytics API when available
      // For now, return mock data structure
      return {
        models: {
          'openai-gpt-4o': { avgLatency: 1200, successRate: 0.98, avgCost: 0.045 },
          'claude-3.5-sonnet': { avgLatency: 800, successRate: 0.99, avgCost: 0.012 },
          'meta-llama-3': { avgLatency: 2000, successRate: 0.95, avgCost: 0.001 }
        }
      };
    } catch (error) {
      console.warn('Performance data retrieval error:', error.message);
      return null;
    }
  }
  
  /**
   * Optimize model selection based on performance data
   */
  optimizeModelSelection(agentType, performanceData) {
    if (!performanceData) {
      return 'claude-3.5-sonnet'; // Safe default
    }
    
    // Score models based on success rate, latency, and cost
    const scores = {};
    for (const [model, data] of Object.entries(performanceData.models)) {
      scores[model] = (
        data.successRate * 0.5 + // 50% weight on success rate
        (1 / data.avgLatency * 1000) * 0.3 + // 30% weight on speed (inverted)
        (1 / data.avgCost) * 0.2 // 20% weight on cost efficiency (inverted)
      );
    }
    
    // Return model with highest score
    return Object.keys(scores).reduce((a, b) => scores[a] > scores[b] ? a : b);
  }
  
  /**
   * Store metrics locally for fast access
   */
  async storeLocalMetrics(metrics) {
    // Implementation would depend on local database choice
    // Could be PostgreSQL, SQLite, or in-memory store
    console.log('Storing metrics locally:', metrics);
  }
  
  /**
   * Get analytics dashboard data
   */
  async getAnalyticsDashboard(dateRange = '7d') {
    try {
      // Get aggregated data from Langfuse
      const analytics = await this.langfuse.analytics({
        projectId: 'ai-agency-platform',
        dateRange,
        groupBy: ['model', 'agentType', 'userId']
      });
      
      return {
        totalExecutions: analytics.totalExecutions || 0,
        totalCost: analytics.totalCost || 0,
        averageLatency: analytics.averageLatency || 0,
        successRate: analytics.successRate || 0,
        modelBreakdown: this.formatModelBreakdown(analytics),
        agentPerformance: this.formatAgentPerformance(analytics),
        customerMetrics: this.formatCustomerMetrics(analytics)
      };
      
    } catch (error) {
      console.error('Analytics dashboard error:', error.message);
      return null;
    }
  }
  
  formatModelBreakdown(analytics) {
    // Format model usage and performance data
    return analytics.models || {};
  }
  
  formatAgentPerformance(analytics) {
    // Format agent-specific performance metrics
    return analytics.agents || {};
  }
  
  formatCustomerMetrics(analytics) {
    // Format customer-specific usage and satisfaction metrics
    return analytics.customers || {};
  }
  
  /**
   * Cleanup resources
   */
  async cleanup() {
    try {
      await this.redis.disconnect();
      await this.langfuse.shutdown();
      console.log('✅ Langfuse-MCPhub Bridge cleanup completed');
    } catch (error) {
      console.error('Cleanup error:', error.message);
    }
  }
}

module.exports = { LangfuseMCPhubBridge };