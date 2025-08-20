#!/usr/bin/env node

import { WebSocketServer } from 'ws';
import { Redis } from 'ioredis';
import jwt from 'jsonwebtoken';
import { EventEmitter } from 'events';

/**
 * Real-Time WebSocket Proof of Concept
 * 
 * Demonstrates real-time communication patterns for the dual-agent architecture:
 * - Agent status updates broadcasting
 * - Customer interaction real-time updates  
 * - System health notification streams
 * - Cross-agent coordination events
 * 
 * API Developer Implementation for Phase 1 Foundation
 */
export class WebSocketProofOfConcept extends EventEmitter {
  constructor(config = {}) {
    super();
    
    this.config = {
      port: config.port || 8080,
      redisUrl: config.redisUrl || 'redis://localhost:6379',
      jwtSecret: config.jwtSecret || process.env.JWT_SECRET || 'phase1-dev-secret',
      maxConnections: config.maxConnections || 1000,
      heartbeatInterval: config.heartbeatInterval || 30000,
      ...config
    };

    this.redis = new Redis(this.config.redisUrl);
    this.redisSubscriber = new Redis(this.config.redisUrl);
    
    this.wsServer = null;
    this.connections = new Map();
    this.rooms = new Map(); // Room-based message broadcasting
    
    // Real-time metrics
    this.metrics = {
      totalConnections: 0,
      activeConnections: 0,
      messagesSent: 0,
      messagesReceived: 0,
      bytesTransferred: 0,
      uptime: Date.now(),
      lastActivity: Date.now()
    };
    
    this.heartbeatInterval = null;
  }

  /**
   * Initialize WebSocket server and Redis subscriptions
   */
  async initialize() {
    console.log('🔌 Initializing Real-Time WebSocket Proof of Concept...');
    
    try {
      // Setup WebSocket server
      await this.setupWebSocketServer();
      
      // Setup Redis message subscriptions
      await this.setupRedisSubscriptions();
      
      // Start heartbeat monitoring
      this.startHeartbeat();
      
      console.log(`✅ WebSocket POC initialized on port ${this.config.port}`);
      console.log(`📊 Max connections: ${this.config.maxConnections}`);
      
      this.emit('server:ready');
      
    } catch (error) {
      console.error('❌ Failed to initialize WebSocket POC:', error);
      throw error;
    }
  }

  /**
   * Setup WebSocket server with authentication and room management
   */
  async setupWebSocketServer() {
    this.wsServer = new WebSocketServer({ 
      port: this.config.port,
      verifyClient: this.authenticateClient.bind(this),
      perMessageDeflate: false,
      maxPayload: 1024 * 1024 // 1MB max message size
    });

    this.wsServer.on('connection', (ws, request) => {
      this.handleNewConnection(ws, request);
    });

    this.wsServer.on('error', (error) => {
      console.error('❌ WebSocket server error:', error);
    });
  }

  /**
   * Setup Redis subscriptions for real-time event broadcasting
   */
  async setupRedisSubscriptions() {
    const channels = [
      'agent:status-updates',
      'customer:interactions', 
      'system:health',
      'coordination:events',
      'infrastructure:notifications',
      'claude-code:updates'
    ];

    for (const channel of channels) {
      await this.redisSubscriber.subscribe(channel);
    }

    this.redisSubscriber.on('message', (channel, message) => {
      this.handleRedisMessage(channel, message);
    });

    console.log(`📡 Subscribed to ${channels.length} Redis channels`);
  }

  /**
   * Handle new WebSocket connection
   */
  handleNewConnection(ws, request) {
    const connectionId = this.generateConnectionId();
    const user = this.extractUserFromRequest(request);
    
    const connection = {
      id: connectionId,
      ws,
      user,
      connectedAt: Date.now(),
      lastPing: Date.now(),
      subscriptions: new Set(),
      rooms: new Set(),
      messagesSent: 0,
      messagesReceived: 0,
      isAlive: true
    };

    this.connections.set(connectionId, connection);
    this.metrics.totalConnections++;
    this.metrics.activeConnections++;

    console.log(`🔗 New connection: ${connectionId} (user: ${user?.email || 'anonymous'})`);

    // Setup connection event handlers
    ws.on('message', (data) => {
      this.handleWebSocketMessage(connectionId, data);
    });

    ws.on('pong', () => {
      connection.lastPing = Date.now();
      connection.isAlive = true;
    });

    ws.on('close', (code, reason) => {
      this.handleConnectionClose(connectionId, code, reason);
    });

    ws.on('error', (error) => {
      console.error(`❌ WebSocket error for ${connectionId}:`, error);
    });

    // Send welcome message
    this.sendToConnection(connectionId, {
      type: 'connection:established',
      connectionId,
      serverTime: Date.now(),
      capabilities: [
        'real-time-updates',
        'room-subscriptions', 
        'agent-status-streaming',
        'system-health-monitoring'
      ]
    });

    // Auto-subscribe to system updates based on user role
    this.autoSubscribeConnection(connection);
  }

  /**
   * Handle incoming WebSocket messages
   */
  async handleWebSocketMessage(connectionId, data) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    try {
      const message = JSON.parse(data);
      connection.messagesReceived++;
      this.metrics.messagesReceived++;
      this.metrics.lastActivity = Date.now();

      console.log(`📨 Message from ${connectionId}:`, message.type);

      switch (message.type) {
        case 'subscribe':
          await this.handleSubscription(connectionId, message);
          break;
          
        case 'unsubscribe':
          await this.handleUnsubscription(connectionId, message);
          break;
          
        case 'join-room':
          await this.handleRoomJoin(connectionId, message);
          break;
          
        case 'leave-room':
          await this.handleRoomLeave(connectionId, message);
          break;
          
        case 'ping':
          this.sendToConnection(connectionId, { type: 'pong', timestamp: Date.now() });
          break;
          
        case 'agent:status-request':
          await this.handleAgentStatusRequest(connectionId, message);
          break;
          
        case 'system:metrics-request':
          await this.handleMetricsRequest(connectionId);
          break;
          
        default:
          console.warn(`⚠️ Unknown message type: ${message.type}`);
          this.sendToConnection(connectionId, {
            type: 'error',
            message: `Unknown message type: ${message.type}`
          });
      }

    } catch (error) {
      console.error(`❌ Error handling message from ${connectionId}:`, error);
      this.sendToConnection(connectionId, {
        type: 'error',
        message: 'Invalid message format'
      });
    }
  }

  /**
   * Handle Redis messages and broadcast to appropriate clients
   */
  handleRedisMessage(channel, message) {
    try {
      const data = JSON.parse(message);
      
      console.log(`📡 Redis message on ${channel}:`, data.type);
      
      // Route messages based on channel and content
      switch (channel) {
        case 'agent:status-updates':
          this.broadcastToSubscribers('agent-status', {
            type: 'agent:status-update',
            data,
            timestamp: Date.now()
          });
          break;
          
        case 'customer:interactions':
          this.broadcastToRoom(`customer-${data.customerId}`, {
            type: 'customer:interaction',
            data,
            timestamp: Date.now()
          });
          break;
          
        case 'system:health':
          this.broadcastToSubscribers('system-health', {
            type: 'system:health-update',
            data,
            timestamp: Date.now()
          });
          break;
          
        case 'coordination:events':
          this.broadcastToSubscribers('coordination', {
            type: 'coordination:event',
            data,
            timestamp: Date.now()
          });
          break;
          
        case 'infrastructure:notifications':
          this.broadcastToSubscribers('infrastructure-updates', {
            type: 'infrastructure:notification',
            data,
            timestamp: Date.now()
          });
          break;
          
        case 'claude-code:updates':
          this.broadcastToSubscribers('claude-code-updates', {
            type: 'claude-code:update',
            data,
            timestamp: Date.now()
          });
          break;
      }
      
    } catch (error) {
      console.error(`❌ Error handling Redis message from ${channel}:`, error);
    }
  }

  /**
   * Handle subscription requests
   */
  async handleSubscription(connectionId, message) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    const { subscription } = message;
    
    // Validate subscription permissions
    if (!this.validateSubscriptionPermission(connection.user, subscription)) {
      this.sendToConnection(connectionId, {
        type: 'subscription:denied',
        subscription,
        reason: 'Insufficient permissions'
      });
      return;
    }

    connection.subscriptions.add(subscription);
    
    this.sendToConnection(connectionId, {
      type: 'subscription:confirmed',
      subscription,
      timestamp: Date.now()
    });

    console.log(`📋 Connection ${connectionId} subscribed to: ${subscription}`);
  }

  /**
   * Handle room join requests
   */
  async handleRoomJoin(connectionId, message) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    const { room } = message;
    
    // Validate room access permissions
    if (!this.validateRoomAccess(connection.user, room)) {
      this.sendToConnection(connectionId, {
        type: 'room:access-denied',
        room,
        reason: 'Access not permitted'
      });
      return;
    }

    // Add connection to room
    if (!this.rooms.has(room)) {
      this.rooms.set(room, new Set());
    }
    
    this.rooms.get(room).add(connectionId);
    connection.rooms.add(room);

    this.sendToConnection(connectionId, {
      type: 'room:joined',
      room,
      members: this.rooms.get(room).size,
      timestamp: Date.now()
    });

    console.log(`🏠 Connection ${connectionId} joined room: ${room}`);
  }

  /**
   * Handle agent status requests
   */
  async handleAgentStatusRequest(connectionId, message) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    // Simulate agent status retrieval
    const agentStatuses = [
      {
        agentId: 'claude-dev-agent-1',
        type: 'claude-code',
        status: 'active',
        currentTask: 'Code review for API endpoints',
        progress: 75,
        lastActivity: Date.now() - 30000
      },
      {
        agentId: 'infra-business-agent-1', 
        type: 'infrastructure',
        status: 'idle',
        currentTask: null,
        progress: 0,
        lastActivity: Date.now() - 300000
      },
      {
        agentId: 'customer-bot-acme-1',
        type: 'launch-bot',
        status: 'learning',
        currentTask: 'Analyzing customer requirements',
        progress: 60,
        lastActivity: Date.now() - 5000
      }
    ];

    this.sendToConnection(connectionId, {
      type: 'agent:status-response',
      agents: agentStatuses,
      timestamp: Date.now()
    });
  }

  /**
   * Handle system metrics requests
   */
  async handleMetricsRequest(connectionId) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    const systemMetrics = {
      websocket: {
        ...this.metrics,
        connections: Array.from(this.connections.values()).map(conn => ({
          id: conn.id,
          user: conn.user?.email,
          connectedAt: conn.connectedAt,
          messagesSent: conn.messagesSent,
          messagesReceived: conn.messagesReceived
        }))
      },
      redis: await this.getRedisMetrics(),
      rooms: Array.from(this.rooms.entries()).map(([room, members]) => ({
        room,
        members: members.size
      }))
    };

    this.sendToConnection(connectionId, {
      type: 'system:metrics-response',
      metrics: systemMetrics,
      timestamp: Date.now()
    });
  }

  /**
   * Broadcasting methods
   */
  broadcastToSubscribers(subscription, message) {
    let sent = 0;
    
    for (const [connectionId, connection] of this.connections.entries()) {
      if (connection.subscriptions.has(subscription)) {
        this.sendToConnection(connectionId, message);
        sent++;
      }
    }
    
    console.log(`📢 Broadcast to ${sent} subscribers of ${subscription}`);
  }

  broadcastToRoom(room, message) {
    const roomMembers = this.rooms.get(room);
    if (!roomMembers) return;

    let sent = 0;
    
    for (const connectionId of roomMembers) {
      if (this.sendToConnection(connectionId, message)) {
        sent++;
      }
    }
    
    console.log(`🏠 Broadcast to ${sent} members of room ${room}`);
  }

  broadcastToAll(message) {
    let sent = 0;
    
    for (const connectionId of this.connections.keys()) {
      if (this.sendToConnection(connectionId, message)) {
        sent++;
      }
    }
    
    console.log(`📡 Broadcast to ${sent} connections`);
  }

  /**
   * Send message to specific connection
   */
  sendToConnection(connectionId, message) {
    const connection = this.connections.get(connectionId);
    if (!connection || connection.ws.readyState !== 1) return false; // Not OPEN

    try {
      const messageStr = JSON.stringify(message);
      connection.ws.send(messageStr);
      connection.messagesSent++;
      this.metrics.messagesSent++;
      this.metrics.bytesTransferred += messageStr.length;
      return true;
    } catch (error) {
      console.error(`❌ Failed to send message to ${connectionId}:`, error);
      return false;
    }
  }

  /**
   * Connection lifecycle methods
   */
  handleConnectionClose(connectionId, code, reason) {
    const connection = this.connections.get(connectionId);
    if (!connection) return;

    // Remove from rooms
    for (const room of connection.rooms) {
      const roomMembers = this.rooms.get(room);
      if (roomMembers) {
        roomMembers.delete(connectionId);
        if (roomMembers.size === 0) {
          this.rooms.delete(room);
        }
      }
    }

    this.connections.delete(connectionId);
    this.metrics.activeConnections--;

    console.log(`🔌 Connection closed: ${connectionId} (code: ${code})`);
  }

  /**
   * Auto-subscribe connections based on user role
   */
  autoSubscribeConnection(connection) {
    const subscriptions = [];
    
    if (connection.user?.role === 'admin') {
      subscriptions.push('system-health', 'agent-status', 'coordination');
    } else if (connection.user?.role === 'customer') {
      subscriptions.push('system-health');
    }
    
    // All authenticated users get basic updates
    subscriptions.push('infrastructure-updates');
    
    for (const subscription of subscriptions) {
      connection.subscriptions.add(subscription);
    }

    if (subscriptions.length > 0) {
      this.sendToConnection(connection.id, {
        type: 'auto-subscriptions',
        subscriptions,
        timestamp: Date.now()
      });
    }
  }

  /**
   * Authentication and authorization
   */
  authenticateClient(info) {
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

  extractUserFromRequest(request) {
    try {
      const token = this.extractTokenFromRequest(request);
      if (!token) return null;

      return jwt.verify(token, this.config.jwtSecret);
    } catch (error) {
      return null;
    }
  }

  extractTokenFromRequest(req) {
    const auth = req.headers.authorization;
    if (auth && auth.startsWith('Bearer ')) {
      return auth.substring(7);
    }
    
    const url = new URL(`http://localhost${req.url}`);
    return url.searchParams.get('token');
  }

  validateSubscriptionPermission(user, subscription) {
    if (!user) return false;
    
    const permissions = {
      'system-health': ['admin', 'customer'],
      'agent-status': ['admin'],
      'coordination': ['admin'],
      'infrastructure-updates': ['admin', 'customer'],
      'claude-code-updates': ['admin']
    };
    
    return permissions[subscription]?.includes(user.role) || false;
  }

  validateRoomAccess(user, room) {
    if (!user) return false;
    
    // Admins can access all rooms
    if (user.role === 'admin') return true;
    
    // Customers can only access their own rooms
    if (user.role === 'customer') {
      return room.startsWith('customer-') && room.includes(user.customerId);
    }
    
    return false;
  }

  /**
   * Heartbeat and health monitoring
   */
  startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      this.performHeartbeat();
    }, this.config.heartbeatInterval);
  }

  performHeartbeat() {
    const now = Date.now();
    const timeoutThreshold = this.config.heartbeatInterval * 2;
    
    for (const [connectionId, connection] of this.connections.entries()) {
      // Check if connection is stale
      if (now - connection.lastPing > timeoutThreshold) {
        console.log(`💔 Connection ${connectionId} timed out`);
        connection.ws.terminate();
        this.connections.delete(connectionId);
        this.metrics.activeConnections--;
        continue;
      }
      
      // Send ping
      if (connection.ws.readyState === 1) {
        connection.isAlive = false;
        connection.ws.ping();
      }
    }
  }

  /**
   * Utility methods
   */
  generateConnectionId() {
    return `ws_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  async getRedisMetrics() {
    try {
      const info = await this.redis.info();
      return {
        connected: true,
        info: info.split('\r\n').reduce((acc, line) => {
          if (line.includes(':')) {
            const [key, value] = line.split(':');
            acc[key] = value;
          }
          return acc;
        }, {})
      };
    } catch (error) {
      return { connected: false, error: error.message };
    }
  }

  /**
   * Server management
   */
  async start() {
    await this.initialize();
    return this;
  }

  async stop() {
    console.log('🔄 Stopping WebSocket POC...');
    
    // Clear heartbeat
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }
    
    // Close all connections
    for (const connection of this.connections.values()) {
      connection.ws.close();
    }
    
    // Close server
    if (this.wsServer) {
      this.wsServer.close();
    }
    
    // Close Redis connections
    await this.redis.quit();
    await this.redisSubscriber.quit();
    
    console.log('✅ WebSocket POC stopped');
  }

  /**
   * Demo mode for testing
   */
  async startDemoMode() {
    console.log('🎭 Starting WebSocket POC in demo mode...');
    
    // Simulate agent status updates
    setInterval(() => {
      this.redis.publish('agent:status-updates', JSON.stringify({
        agentId: `demo-agent-${Date.now()}`,
        status: Math.random() > 0.5 ? 'active' : 'idle',
        progress: Math.floor(Math.random() * 100),
        timestamp: Date.now()
      }));
    }, 5000);
    
    // Simulate system health updates
    setInterval(() => {
      this.redis.publish('system:health', JSON.stringify({
        status: 'healthy',
        cpu: Math.random() * 100,
        memory: Math.random() * 100,
        connections: this.metrics.activeConnections,
        timestamp: Date.now()
      }));
    }, 10000);
    
    console.log('🎭 Demo mode active - simulating real-time events');
  }
}

export default WebSocketProofOfConcept;

// CLI execution
if (import.meta.url === `file://${process.argv[1]}`) {
  const poc = new WebSocketProofOfConcept();
  
  process.on('SIGINT', async () => {
    await poc.stop();
    process.exit(0);
  });
  
  poc.start()
    .then(async () => {
      // Start demo mode if requested
      if (process.argv.includes('--demo')) {
        await poc.startDemoMode();
      }
    })
    .catch(console.error);
}