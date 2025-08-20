#!/usr/bin/env node

import { Redis } from 'ioredis';
import { WebSocketServer } from 'ws';
import { EventEmitter } from 'events';
import jwt from 'jsonwebtoken';

/**
 * Cross-System API Bridge for Dual-Agent Architecture
 * 
 * Handles secure communication between:
 * - Claude Code agents (development system)
 * - Infrastructure agents (business/customer system)
 * 
 * API Developer Implementation for Phase 1 Foundation
 */
export class CrossSystemAPIBridge extends EventEmitter {
  constructor(config = {}) {
    super();
    
    this.config = {
      redisUrl: config.redisUrl || 'redis://localhost:6379',
      jwtSecret: config.jwtSecret || process.env.JWT_SECRET || 'phase1-dev-secret',
      wsPort: config.wsPort || 8080,
      ...config
    };
    
    // Redis clients for different message channels
    this.redisPublisher = new Redis(this.config.redisUrl);
    this.redisSubscriber = new Redis(this.config.redisUrl);
    
    // WebSocket server for real-time communication
    this.wsServer = null;
    this.connectedClients = new Map();
    
    // Message tracking for API validation
    this.messageHistory = [];
    this.apiMetrics = {
      messagesProcessed: 0,
      errorsCount: 0,
      lastActivity: null,
      averageResponseTime: 0,
      systemHealth: 'healthy'
    };
  }

  /**
   * Initialize the cross-system API bridge
   */
  async initialize() {
    try {
      console.log('🌉 Initializing Cross-System API Bridge...');
      
      // Setup Redis message channels
      await this.setupMessageChannels();
      
      // Initialize WebSocket server
      await this.initializeWebSocketServer();
      
      // Setup API validation patterns
      this.setupAPIValidationPatterns();
      
      console.log('✅ Cross-System API Bridge initialized successfully');
      this.emit('bridge:ready');
      
    } catch (error) {
      console.error('❌ Failed to initialize Cross-System API Bridge:', error);
      throw error;
    }
  }

  /**
   * Setup Redis message channels for cross-system communication
   */
  async setupMessageChannels() {
    // Channel definitions for dual-agent architecture
    const channels = {
      'claude-code:outbound': this.handleClaudeCodeMessage.bind(this),
      'infrastructure:outbound': this.handleInfrastructureMessage.bind(this), 
      'system:coordination': this.handleCoordinationMessage.bind(this),
      'system:health': this.handleHealthMessage.bind(this)
    };

    // Subscribe to all channels
    for (const [channel, handler] of Object.entries(channels)) {
      await this.redisSubscriber.subscribe(channel);
      this.redisSubscriber.on('message', (receivedChannel, message) => {
        if (receivedChannel === channel) {
          this.processMessage(channel, message, handler);
        }
      });
    }

    console.log(`📡 Subscribed to ${Object.keys(channels).length} message channels`);
  }

  /**
   * Initialize WebSocket server for real-time API communication
   */
  async initializeWebSocketServer() {
    this.wsServer = new WebSocketServer({ 
      port: this.config.wsPort,
      verifyClient: this.authenticateWebSocketClient.bind(this)
    });

    this.wsServer.on('connection', (ws, request) => {
      const clientId = this.generateClientId();
      const clientInfo = {
        id: clientId,
        type: this.extractClientType(request),
        connected: Date.now(),
        ws
      };

      this.connectedClients.set(clientId, clientInfo);
      
      ws.on('message', (data) => {
        this.handleWebSocketMessage(clientId, data);
      });

      ws.on('close', () => {
        this.connectedClients.delete(clientId);
      });

      // Send welcome message with client info
      ws.send(JSON.stringify({
        type: 'connection:established',
        clientId,
        timestamp: Date.now()
      }));
    });

    console.log(`🔌 WebSocket server listening on port ${this.config.wsPort}`);
  }

  /**
   * Process incoming messages with validation and metrics
   */
  async processMessage(channel, rawMessage, handler) {
    const startTime = Date.now();
    
    try {
      const message = JSON.parse(rawMessage);
      
      // Validate message structure
      const validationResult = this.validateMessageStructure(message);
      if (!validationResult.valid) {
        throw new Error(`Invalid message structure: ${validationResult.error}`);
      }

      // Update metrics
      this.apiMetrics.messagesProcessed++;
      this.apiMetrics.lastActivity = Date.now();
      
      // Process message through handler
      const result = await handler(message, channel);
      
      // Calculate response time
      const responseTime = Date.now() - startTime;
      this.updateAverageResponseTime(responseTime);
      
      // Log successful processing
      this.logAPIActivity({
        channel,
        messageId: message.id,
        responseTime,
        status: 'success'
      });

      return result;
      
    } catch (error) {
      this.apiMetrics.errorsCount++;
      this.logAPIActivity({
        channel,
        error: error.message,
        responseTime: Date.now() - startTime,
        status: 'error'
      });
      
      console.error(`❌ Error processing message on ${channel}:`, error);
      throw error;
    }
  }

  /**
   * Handle messages from Claude Code agents
   */
  async handleClaudeCodeMessage(message, channel) {
    console.log('🔧 Processing Claude Code message:', message.type);
    
    switch (message.type) {
      case 'status-update':
        await this.forwardStatusUpdate(message, 'claude-code');
        break;
        
      case 'tool-request':
        await this.processToolRequest(message, 'claude-code');
        break;
        
      case 'workflow-handoff':
        await this.processWorkflowHandoff(message, 'claude-code');
        break;
        
      default:
        console.warn(`⚠️ Unknown Claude Code message type: ${message.type}`);
    }
    
    return { processed: true, system: 'claude-code' };
  }

  /**
   * Handle messages from Infrastructure agents
   */
  async handleInfrastructureMessage(message, channel) {
    console.log('🏗️ Processing Infrastructure message:', message.type);
    
    switch (message.type) {
      case 'task-completion':
        await this.forwardTaskCompletion(message, 'infrastructure');
        break;
        
      case 'customer-bot-status':
        await this.processCustomerBotStatus(message);
        break;
        
      case 'business-intelligence':
        await this.processBusinessIntelligence(message);
        break;
        
      default:
        console.warn(`⚠️ Unknown Infrastructure message type: ${message.type}`);
    }
    
    return { processed: true, system: 'infrastructure' };
  }

  /**
   * Handle system coordination messages
   */
  async handleCoordinationMessage(message, channel) {
    console.log('🎯 Processing coordination message:', message.type);
    
    // Forward coordination messages to all connected clients
    this.broadcastToClients({
      type: 'system:coordination',
      data: message,
      timestamp: Date.now()
    });
    
    return { processed: true, system: 'coordination' };
  }

  /**
   * Handle system health messages
   */
  async handleHealthMessage(message, channel) {
    // Update system health status
    this.apiMetrics.systemHealth = message.status || 'unknown';
    
    // Broadcast health update to monitoring clients
    this.broadcastToClients({
      type: 'system:health',
      data: {
        status: this.apiMetrics.systemHealth,
        metrics: this.getAPIMetrics(),
        timestamp: Date.now()
      }
    }, 'monitoring');
    
    return { processed: true, system: 'health' };
  }

  /**
   * Process tool requests from Claude Code to Infrastructure
   */
  async processToolRequest(message, sourceSystem) {
    const { toolName, params, callbackId } = message.payload;
    
    // Route tool request to Infrastructure system
    await this.redisPublisher.publish('infrastructure:inbound', JSON.stringify({
      id: this.generateMessageId(),
      type: 'tool-execution',
      source: sourceSystem,
      timestamp: Date.now(),
      payload: {
        toolName,
        params,
        callbackId,
        requestedBy: message.agentId
      }
    }));
    
    console.log(`🔄 Routed tool request: ${toolName} from ${sourceSystem}`);
  }

  /**
   * Forward status updates between systems
   */
  async forwardStatusUpdate(message, sourceSystem) {
    const targetChannel = sourceSystem === 'claude-code' 
      ? 'infrastructure:inbound' 
      : 'claude-code:inbound';
    
    await this.redisPublisher.publish(targetChannel, JSON.stringify({
      id: this.generateMessageId(),
      type: 'status-notification',
      source: sourceSystem,
      timestamp: Date.now(),
      payload: message.payload
    }));
    
    // Also broadcast to WebSocket clients
    this.broadcastToClients({
      type: 'status:update',
      source: sourceSystem,
      data: message.payload,
      timestamp: Date.now()
    });
  }

  /**
   * Validate message structure for API compliance
   */
  validateMessageStructure(message) {
    const requiredFields = ['id', 'type', 'timestamp', 'payload'];
    const missingFields = requiredFields.filter(field => !message[field]);
    
    if (missingFields.length > 0) {
      return {
        valid: false,
        error: `Missing required fields: ${missingFields.join(', ')}`
      };
    }
    
    // Validate timestamp is recent (within 5 minutes)
    const messageAge = Date.now() - message.timestamp;
    if (messageAge > 5 * 60 * 1000) {
      return {
        valid: false,
        error: 'Message timestamp too old'
      };
    }
    
    return { valid: true };
  }

  /**
   * Setup API validation patterns for different message types
   */
  setupAPIValidationPatterns() {
    this.validationPatterns = {
      'status-update': {
        required: ['agentId', 'status', 'progress'],
        optional: ['details', 'metadata']
      },
      'tool-request': {
        required: ['toolName', 'params', 'callbackId'],
        optional: ['priority', 'timeout']
      },
      'workflow-handoff': {
        required: ['workflowId', 'targetSystem', 'handoffData'],
        optional: ['dependencies', 'deadline']
      }
    };
  }

  /**
   * Authenticate WebSocket clients
   */
  authenticateWebSocketClient(info) {
    try {
      const token = this.extractTokenFromRequest(info.req);
      if (!token) return false;
      
      jwt.verify(token, this.config.jwtSecret);
      return true;
    } catch (error) {
      console.warn('🔒 WebSocket authentication failed:', error.message);
      return false;
    }
  }

  /**
   * Handle WebSocket messages from clients
   */
  async handleWebSocketMessage(clientId, data) {
    try {
      const message = JSON.parse(data);
      const client = this.connectedClients.get(clientId);
      
      if (!client) return;
      
      // Process different types of WebSocket messages
      switch (message.type) {
        case 'api:metrics-request':
          client.ws.send(JSON.stringify({
            type: 'api:metrics-response',
            data: this.getAPIMetrics(),
            timestamp: Date.now()
          }));
          break;
          
        case 'system:status-request':
          client.ws.send(JSON.stringify({
            type: 'system:status-response', 
            data: await this.getSystemStatus(),
            timestamp: Date.now()
          }));
          break;
          
        default:
          console.warn(`⚠️ Unknown WebSocket message type: ${message.type}`);
      }
      
    } catch (error) {
      console.error(`❌ Error handling WebSocket message from ${clientId}:`, error);
    }
  }

  /**
   * Broadcast messages to connected WebSocket clients
   */
  broadcastToClients(message, clientType = null) {
    const messageStr = JSON.stringify(message);
    
    for (const [clientId, client] of this.connectedClients.entries()) {
      if (clientType && client.type !== clientType) continue;
      
      try {
        if (client.ws.readyState === 1) { // WebSocket.OPEN
          client.ws.send(messageStr);
        }
      } catch (error) {
        console.error(`❌ Failed to send message to client ${clientId}:`, error);
        this.connectedClients.delete(clientId);
      }
    }
  }

  /**
   * Get comprehensive API metrics
   */
  getAPIMetrics() {
    return {
      ...this.apiMetrics,
      connectedClients: this.connectedClients.size,
      uptime: Date.now() - (this.apiMetrics.startTime || Date.now()),
      errorRate: this.apiMetrics.messagesProcessed > 0 
        ? (this.apiMetrics.errorsCount / this.apiMetrics.messagesProcessed * 100).toFixed(2)
        : 0
    };
  }

  /**
   * Get current system status
   */
  async getSystemStatus() {
    try {
      // Test Redis connectivity
      const redisPing = await this.redisPublisher.ping();
      
      return {
        bridge: 'operational',
        redis: redisPing === 'PONG' ? 'healthy' : 'unhealthy',
        websocket: this.wsServer ? 'active' : 'inactive',
        connectedClients: this.connectedClients.size,
        lastActivity: this.apiMetrics.lastActivity,
        systemHealth: this.apiMetrics.systemHealth
      };
    } catch (error) {
      return {
        bridge: 'error',
        error: error.message,
        timestamp: Date.now()
      };
    }
  }

  /**
   * Log API activity for monitoring
   */
  logAPIActivity(activity) {
    const logEntry = {
      timestamp: Date.now(),
      ...activity
    };
    
    this.messageHistory.push(logEntry);
    
    // Keep only last 1000 entries
    if (this.messageHistory.length > 1000) {
      this.messageHistory = this.messageHistory.slice(-1000);
    }
    
    // Emit for external monitoring
    this.emit('api:activity', logEntry);
  }

  /**
   * Update average response time metric
   */
  updateAverageResponseTime(responseTime) {
    if (this.apiMetrics.averageResponseTime === 0) {
      this.apiMetrics.averageResponseTime = responseTime;
    } else {
      // Simple moving average
      this.apiMetrics.averageResponseTime = 
        (this.apiMetrics.averageResponseTime * 0.9) + (responseTime * 0.1);
    }
  }

  /**
   * Utility methods
   */
  generateMessageId() {
    return `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  generateClientId() {
    return `client_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
  }

  extractTokenFromRequest(req) {
    const auth = req.headers.authorization;
    if (auth && auth.startsWith('Bearer ')) {
      return auth.substring(7);
    }
    return req.url ? new URL(`http://localhost${req.url}`).searchParams.get('token') : null;
  }

  extractClientType(req) {
    return req.headers['x-client-type'] || 'unknown';
  }

  /**
   * Graceful shutdown
   */
  async shutdown() {
    console.log('🔄 Shutting down Cross-System API Bridge...');
    
    // Close WebSocket server
    if (this.wsServer) {
      this.wsServer.close();
    }
    
    // Close Redis connections
    await this.redisPublisher.quit();
    await this.redisSubscriber.quit();
    
    console.log('✅ Cross-System API Bridge shutdown complete');
  }
}

// Export for use in other modules
export default CrossSystemAPIBridge;

// CLI execution
if (import.meta.url === `file://${process.argv[1]}`) {
  const bridge = new CrossSystemAPIBridge();
  
  // Handle graceful shutdown
  process.on('SIGINT', async () => {
    await bridge.shutdown();
    process.exit(0);
  });
  
  // Initialize and start
  bridge.initialize().catch(console.error);
}