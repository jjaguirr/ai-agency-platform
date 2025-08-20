#!/usr/bin/env node

import express from 'express';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcrypt';
import { v4 as uuidv4 } from 'uuid';
import { Redis } from 'ioredis';
import pg from 'pg';

/**
 * Customer Provisioning API Framework
 * 
 * Handles customer onboarding, LAUNCH bot lifecycle management, 
 * and AI model configuration for the dual-agent architecture.
 * 
 * API Developer Implementation for Phase 1 Foundation
 */
export class CustomerProvisioningAPI {
  constructor(config = {}) {
    this.config = {
      port: config.port || 3001,
      jwtSecret: config.jwtSecret || process.env.JWT_SECRET || 'phase1-dev-secret',
      dbUrl: config.dbUrl || 'postgresql://mcphub:mcphub_password@localhost:5433/mcphub',
      redisUrl: config.redisUrl || 'redis://localhost:6379',
      corsOrigins: config.corsOrigins || ['http://localhost:3000', 'http://localhost:5678'],
      ...config
    };

    this.app = express();
    this.db = new pg.Pool({ connectionString: this.config.dbUrl });
    this.redis = new Redis(this.config.redisUrl);
    
    // API metrics tracking
    this.apiMetrics = {
      customersCreated: 0,
      botsDeployed: 0,
      apiRequestsProcessed: 0,
      averageResponseTime: 0,
      lastActivity: null
    };
    
    this.setupMiddleware();
    this.setupRoutes();
    this.initializeDatabase();
  }

  /**
   * Setup Express middleware for API security and functionality
   */
  setupMiddleware() {
    // Basic middleware
    this.app.use(express.json({ limit: '10mb' }));
    this.app.use(express.urlencoded({ extended: true }));
    
    // CORS configuration
    this.app.use((req, res, next) => {
      const origin = req.headers.origin;
      if (this.config.corsOrigins.includes(origin)) {
        res.setHeader('Access-Control-Allow-Origin', origin);
      }
      res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
      res.setHeader('Access-Control-Allow-Credentials', 'true');
      
      if (req.method === 'OPTIONS') {
        res.status(200).end();
        return;
      }
      next();
    });

    // Request metrics middleware
    this.app.use((req, res, next) => {
      req.startTime = Date.now();
      res.on('finish', () => {
        const responseTime = Date.now() - req.startTime;
        this.updateAPIMetrics(responseTime);
      });
      next();
    });

    // Authentication middleware
    this.authenticateJWT = (req, res, next) => {
      const authHeader = req.headers.authorization;
      const token = authHeader && authHeader.split(' ')[1];

      if (!token) {
        return res.status(401).json({ 
          error: 'Access token required',
          code: 'AUTH_TOKEN_MISSING'
        });
      }

      jwt.verify(token, this.config.jwtSecret, (err, user) => {
        if (err) {
          return res.status(403).json({ 
            error: 'Invalid or expired token',
            code: 'AUTH_TOKEN_INVALID'
          });
        }
        req.user = user;
        next();
      });
    };

    // Admin authorization middleware
    this.requireAdmin = (req, res, next) => {
      if (!req.user || req.user.role !== 'admin') {
        return res.status(403).json({
          error: 'Admin privileges required',
          code: 'AUTH_INSUFFICIENT_PRIVILEGES'
        });
      }
      next();
    };
  }

  /**
   * Setup API routes for customer provisioning
   */
  setupRoutes() {
    // Health check endpoint
    this.app.get('/health', (req, res) => {
      res.json({
        status: 'healthy',
        service: 'customer-provisioning-api',
        timestamp: Date.now(),
        metrics: this.getAPIMetrics()
      });
    });

    // Authentication endpoints
    this.app.post('/api/v1/auth/login', this.handleLogin.bind(this));
    this.app.post('/api/v1/auth/refresh', this.handleTokenRefresh.bind(this));

    // Customer management endpoints
    this.app.post('/api/v1/customers', this.authenticateJWT, this.requireAdmin, this.createCustomer.bind(this));
    this.app.get('/api/v1/customers', this.authenticateJWT, this.requireAdmin, this.listCustomers.bind(this));
    this.app.get('/api/v1/customers/:customerId', this.authenticateJWT, this.getCustomer.bind(this));
    this.app.put('/api/v1/customers/:customerId', this.authenticateJWT, this.updateCustomer.bind(this));
    this.app.delete('/api/v1/customers/:customerId', this.authenticateJWT, this.requireAdmin, this.deleteCustomer.bind(this));

    // LAUNCH Bot lifecycle endpoints
    this.app.post('/api/v1/customers/:customerId/launch-bot', this.authenticateJWT, this.initializeLaunchBot.bind(this));
    this.app.get('/api/v1/customers/:customerId/launch-bot', this.authenticateJWT, this.getLaunchBotStatus.bind(this));
    this.app.put('/api/v1/customers/:customerId/launch-bot/stage', this.authenticateJWT, this.updateBotStage.bind(this));
    this.app.post('/api/v1/customers/:customerId/launch-bot/configure', this.authenticateJWT, this.configureLaunchBot.bind(this));

    // AI Model configuration endpoints  
    this.app.get('/api/v1/ai-models', this.authenticateJWT, this.listAvailableAIModels.bind(this));
    this.app.put('/api/v1/customers/:customerId/ai-model', this.authenticateJWT, this.setCustomerAIModel.bind(this));
    this.app.get('/api/v1/customers/:customerId/ai-model/usage', this.authenticateJWT, this.getAIModelUsage.bind(this));

    // Customer group and tool management
    this.app.post('/api/v1/customers/:customerId/tools', this.authenticateJWT, this.addCustomerTool.bind(this));
    this.app.get('/api/v1/customers/:customerId/tools', this.authenticateJWT, this.listCustomerTools.bind(this));
    this.app.delete('/api/v1/customers/:customerId/tools/:toolId', this.authenticateJWT, this.removeCustomerTool.bind(this));

    // Monitoring and metrics endpoints
    this.app.get('/api/v1/metrics', this.authenticateJWT, this.requireAdmin, this.getSystemMetrics.bind(this));
    this.app.get('/api/v1/customers/:customerId/metrics', this.authenticateJWT, this.getCustomerMetrics.bind(this));

    // Error handling middleware
    this.app.use((error, req, res, next) => {
      console.error('API Error:', error);
      res.status(error.status || 500).json({
        error: error.message || 'Internal server error',
        code: error.code || 'INTERNAL_ERROR',
        timestamp: Date.now()
      });
    });
  }

  /**
   * Initialize database schema for customer provisioning
   */
  async initializeDatabase() {
    try {
      // Create customers table
      await this.db.query(`
        CREATE TABLE IF NOT EXISTS customers (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name VARCHAR(255) NOT NULL,
          email VARCHAR(255) UNIQUE NOT NULL,
          ai_model VARCHAR(100) DEFAULT 'openai-gpt-4o',
          industry VARCHAR(100),
          compliance_requirements JSONB DEFAULT '[]',
          custom_tools JSONB DEFAULT '[]',
          config JSONB DEFAULT '{}',
          created_at TIMESTAMP DEFAULT NOW(),
          updated_at TIMESTAMP DEFAULT NOW()
        )
      `);

      // Create launch_bots table
      await this.db.query(`
        CREATE TABLE IF NOT EXISTS launch_bots (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
          stage VARCHAR(50) DEFAULT 'blank',
          configuration JSONB DEFAULT '{}',
          setup_progress INTEGER DEFAULT 0,
          last_interaction TIMESTAMP DEFAULT NOW(),
          performance_metrics JSONB DEFAULT '{}',
          created_at TIMESTAMP DEFAULT NOW(),
          updated_at TIMESTAMP DEFAULT NOW()
        )
      `);

      // Create customer_tools table
      await this.db.query(`
        CREATE TABLE IF NOT EXISTS customer_tools (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
          tool_name VARCHAR(100) NOT NULL,
          permissions JSONB DEFAULT '["read", "execute"]',
          config JSONB DEFAULT '{}',
          enabled BOOLEAN DEFAULT true,
          created_at TIMESTAMP DEFAULT NOW()
        )
      `);

      // Create ai_model_usage table
      await this.db.query(`
        CREATE TABLE IF NOT EXISTS ai_model_usage (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
          ai_model VARCHAR(100) NOT NULL,
          tokens_used INTEGER DEFAULT 0,
          requests_count INTEGER DEFAULT 0,
          cost_usd DECIMAL(10,4) DEFAULT 0,
          period_start TIMESTAMP DEFAULT NOW(),
          period_end TIMESTAMP DEFAULT NOW() + INTERVAL '1 month'
        )
      `);

      console.log('✅ Database schema initialized successfully');
    } catch (error) {
      console.error('❌ Database initialization failed:', error);
      throw error;
    }
  }

  /**
   * Authentication handlers
   */
  async handleLogin(req, res) {
    try {
      const { email, password } = req.body;
      
      // Simplified authentication for Phase 1
      // In production, this would query a proper users table
      const validCredentials = {
        'admin@agency.ai': { password: 'admin123', role: 'admin' },
        'customer@test.com': { password: 'customer123', role: 'customer' }
      };

      const user = validCredentials[email];
      if (!user || password !== user.password) {
        return res.status(401).json({ 
          error: 'Invalid credentials',
          code: 'AUTH_INVALID_CREDENTIALS'
        });
      }

      const token = jwt.sign(
        { email, role: user.role },
        this.config.jwtSecret,
        { expiresIn: '24h' }
      );

      res.json({
        access_token: token,
        token_type: 'Bearer',
        expires_in: 86400,
        user: { email, role: user.role }
      });
    } catch (error) {
      next(error);
    }
  }

  async handleTokenRefresh(req, res) {
    // Simplified token refresh for Phase 1
    res.status(501).json({
      error: 'Token refresh not implemented in Phase 1',
      code: 'NOT_IMPLEMENTED'
    });
  }

  /**
   * Customer management handlers
   */
  async createCustomer(req, res, next) {
    try {
      const {
        name,
        email,
        ai_model = 'openai-gpt-4o',
        industry,
        compliance_requirements = [],
        custom_tools = []
      } = req.body;

      // Validate required fields
      if (!name || !email) {
        return res.status(400).json({
          error: 'Name and email are required',
          code: 'VALIDATION_ERROR'
        });
      }

      // Create customer record
      const customerResult = await this.db.query(`
        INSERT INTO customers (name, email, ai_model, industry, compliance_requirements, custom_tools)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
      `, [name, email, ai_model, industry, JSON.stringify(compliance_requirements), JSON.stringify(custom_tools)]);

      const customer = customerResult.rows[0];

      // Create corresponding MCPhub group via Redis message
      await this.createCustomerMCPhubGroup(customer.id, {
        ai_model,
        tools: custom_tools,
        compliance: compliance_requirements
      });

      // Initialize LAUNCH bot
      await this.db.query(`
        INSERT INTO launch_bots (customer_id, stage, setup_progress)
        VALUES ($1, 'blank', 0)
      `, [customer.id]);

      // Track metrics
      this.apiMetrics.customersCreated++;

      res.status(201).json({
        success: true,
        customer: this.formatCustomerResponse(customer),
        message: 'Customer created successfully'
      });
    } catch (error) {
      if (error.code === '23505') { // Unique violation
        return res.status(409).json({
          error: 'Customer with this email already exists',
          code: 'CUSTOMER_EXISTS'
        });
      }
      next(error);
    }
  }

  async listCustomers(req, res, next) {
    try {
      const { limit = 50, offset = 0, search } = req.query;
      
      let query = 'SELECT * FROM customers';
      let params = [];
      
      if (search) {
        query += ' WHERE name ILIKE $1 OR email ILIKE $1';
        params.push(`%${search}%`);
      }
      
      query += ' ORDER BY created_at DESC LIMIT $' + (params.length + 1) + ' OFFSET $' + (params.length + 2);
      params.push(parseInt(limit), parseInt(offset));
      
      const result = await this.db.query(query, params);
      
      res.json({
        customers: result.rows.map(this.formatCustomerResponse),
        total: result.rowCount,
        limit: parseInt(limit),
        offset: parseInt(offset)
      });
    } catch (error) {
      next(error);
    }
  }

  async getCustomer(req, res, next) {
    try {
      const { customerId } = req.params;
      
      // Authorization check
      if (req.user.role !== 'admin') {
        // Customers can only access their own data
        // In production, you'd have proper customer-user mapping
        return res.status(403).json({
          error: 'Access denied',
          code: 'ACCESS_DENIED'
        });
      }

      const result = await this.db.query(`
        SELECT c.*, lb.stage as bot_stage, lb.setup_progress, lb.last_interaction
        FROM customers c
        LEFT JOIN launch_bots lb ON c.id = lb.customer_id
        WHERE c.id = $1
      `, [customerId]);

      if (result.rows.length === 0) {
        return res.status(404).json({
          error: 'Customer not found',
          code: 'CUSTOMER_NOT_FOUND'
        });
      }

      res.json({
        customer: this.formatCustomerResponse(result.rows[0])
      });
    } catch (error) {
      next(error);
    }
  }

  /**
   * LAUNCH Bot lifecycle handlers
   */
  async initializeLaunchBot(req, res, next) {
    try {
      const { customerId } = req.params;
      const { initial_message, conversation_history = [] } = req.body;

      // Update bot stage and configuration
      const result = await this.db.query(`
        UPDATE launch_bots 
        SET stage = 'identifying',
            configuration = jsonb_set(configuration, '{initial_message}', $2),
            setup_progress = 10,
            last_interaction = NOW(),
            updated_at = NOW()
        WHERE customer_id = $1
        RETURNING *
      `, [customerId, JSON.stringify(initial_message)]);

      if (result.rows.length === 0) {
        return res.status(404).json({
          error: 'LAUNCH bot not found for customer',
          code: 'LAUNCH_BOT_NOT_FOUND'
        });
      }

      // Send initialization message to Infrastructure agents
      await this.redis.publish('infrastructure:inbound', JSON.stringify({
        id: uuidv4(),
        type: 'launch-bot-initialize',
        timestamp: Date.now(),
        payload: {
          customerId,
          initial_message,
          conversation_history
        }
      }));

      this.apiMetrics.botsDeployed++;

      res.json({
        success: true,
        bot_status: this.formatLaunchBotResponse(result.rows[0]),
        message: 'LAUNCH bot initialized successfully'
      });
    } catch (error) {
      next(error);
    }
  }

  async getLaunchBotStatus(req, res, next) {
    try {
      const { customerId } = req.params;

      const result = await this.db.query(`
        SELECT * FROM launch_bots WHERE customer_id = $1
      `, [customerId]);

      if (result.rows.length === 0) {
        return res.status(404).json({
          error: 'LAUNCH bot not found',
          code: 'LAUNCH_BOT_NOT_FOUND'
        });
      }

      res.json({
        bot_status: this.formatLaunchBotResponse(result.rows[0])
      });
    } catch (error) {
      next(error);
    }
  }

  async updateBotStage(req, res, next) {
    try {
      const { customerId } = req.params;
      const { stage, progress, configuration = {} } = req.body;

      const validStages = ['blank', 'identifying', 'learning', 'integrating', 'active'];
      if (!validStages.includes(stage)) {
        return res.status(400).json({
          error: 'Invalid bot stage',
          code: 'INVALID_BOT_STAGE',
          valid_stages: validStages
        });
      }

      const result = await this.db.query(`
        UPDATE launch_bots 
        SET stage = $2,
            setup_progress = $3,
            configuration = configuration || $4,
            last_interaction = NOW(),
            updated_at = NOW()
        WHERE customer_id = $1
        RETURNING *
      `, [customerId, stage, progress, JSON.stringify(configuration)]);

      if (result.rows.length === 0) {
        return res.status(404).json({
          error: 'LAUNCH bot not found',
          code: 'LAUNCH_BOT_NOT_FOUND'
        });
      }

      res.json({
        success: true,
        bot_status: this.formatLaunchBotResponse(result.rows[0]),
        message: 'Bot stage updated successfully'
      });
    } catch (error) {
      next(error);
    }
  }

  /**
   * AI Model configuration handlers
   */
  async listAvailableAIModels(req, res, next) {
    try {
      const aiModels = [
        {
          id: 'openai-gpt-4o',
          name: 'OpenAI GPT-4o',
          provider: 'OpenAI',
          capabilities: ['text', 'code', 'analysis'],
          cost_per_1k_tokens: 0.03,
          max_tokens: 128000
        },
        {
          id: 'claude-3.5-sonnet',
          name: 'Claude 3.5 Sonnet',
          provider: 'Anthropic',
          capabilities: ['text', 'analysis', 'reasoning'],
          cost_per_1k_tokens: 0.025,
          max_tokens: 200000
        },
        {
          id: 'meta-llama-3',
          name: 'Meta Llama 3',
          provider: 'Meta',
          capabilities: ['text', 'code'],
          cost_per_1k_tokens: 0.02,
          max_tokens: 8192
        },
        {
          id: 'deepseek-v2',
          name: 'DeepSeek V2',
          provider: 'DeepSeek',
          capabilities: ['code', 'reasoning'],
          cost_per_1k_tokens: 0.015,
          max_tokens: 32768
        }
      ];

      res.json({
        ai_models: aiModels,
        default_model: 'openai-gpt-4o'
      });
    } catch (error) {
      next(error);
    }
  }

  async setCustomerAIModel(req, res, next) {
    try {
      const { customerId } = req.params;
      const { ai_model, reason } = req.body;

      // Update customer AI model
      const result = await this.db.query(`
        UPDATE customers 
        SET ai_model = $2, updated_at = NOW()
        WHERE id = $1
        RETURNING *
      `, [customerId, ai_model]);

      if (result.rows.length === 0) {
        return res.status(404).json({
          error: 'Customer not found',
          code: 'CUSTOMER_NOT_FOUND'
        });
      }

      // Notify MCPhub of model change
      await this.redis.publish('infrastructure:inbound', JSON.stringify({
        id: uuidv4(),
        type: 'customer-ai-model-change',
        timestamp: Date.now(),
        payload: {
          customerId,
          ai_model,
          reason
        }
      }));

      res.json({
        success: true,
        customer: this.formatCustomerResponse(result.rows[0]),
        message: 'AI model updated successfully'
      });
    } catch (error) {
      next(error);
    }
  }

  /**
   * Utility methods
   */
  async createCustomerMCPhubGroup(customerId, config) {
    const groupConfig = {
      groupId: `customer-${customerId}`,
      name: `Customer ${customerId}`,
      isolation: 'complete',
      tools: config.tools,
      ai_model: config.ai_model,
      compliance: config.compliance
    };

    await this.redis.publish('infrastructure:inbound', JSON.stringify({
      id: uuidv4(),
      type: 'create-customer-group',
      timestamp: Date.now(),
      payload: groupConfig
    }));
  }

  formatCustomerResponse(customer) {
    return {
      id: customer.id,
      name: customer.name,
      email: customer.email,
      ai_model: customer.ai_model,
      industry: customer.industry,
      compliance_requirements: customer.compliance_requirements,
      custom_tools: customer.custom_tools,
      bot_stage: customer.bot_stage,
      setup_progress: customer.setup_progress,
      last_interaction: customer.last_interaction,
      created_at: customer.created_at,
      updated_at: customer.updated_at
    };
  }

  formatLaunchBotResponse(bot) {
    return {
      id: bot.id,
      customer_id: bot.customer_id,
      stage: bot.stage,
      configuration: bot.configuration,
      setup_progress: bot.setup_progress,
      last_interaction: bot.last_interaction,
      performance_metrics: bot.performance_metrics,
      created_at: bot.created_at,
      updated_at: bot.updated_at
    };
  }

  updateAPIMetrics(responseTime) {
    this.apiMetrics.apiRequestsProcessed++;
    this.apiMetrics.lastActivity = Date.now();
    
    if (this.apiMetrics.averageResponseTime === 0) {
      this.apiMetrics.averageResponseTime = responseTime;
    } else {
      this.apiMetrics.averageResponseTime = 
        (this.apiMetrics.averageResponseTime * 0.9) + (responseTime * 0.1);
    }
  }

  getAPIMetrics() {
    return {
      ...this.apiMetrics,
      timestamp: Date.now()
    };
  }

  /**
   * Start the API server
   */
  async start() {
    try {
      await new Promise((resolve) => {
        this.server = this.app.listen(this.config.port, () => {
          console.log(`🚀 Customer Provisioning API listening on port ${this.config.port}`);
          resolve();
        });
      });

      // Test database connection
      await this.db.query('SELECT NOW()');
      console.log('✅ Database connection established');

      // Test Redis connection
      await this.redis.ping();
      console.log('✅ Redis connection established');

      return this.server;
    } catch (error) {
      console.error('❌ Failed to start Customer Provisioning API:', error);
      throw error;
    }
  }

  /**
   * Stop the API server
   */
  async stop() {
    if (this.server) {
      await new Promise((resolve) => this.server.close(resolve));
    }
    await this.db.end();
    await this.redis.quit();
    console.log('✅ Customer Provisioning API stopped');
  }
}

export default CustomerProvisioningAPI;

// CLI execution
if (import.meta.url === `file://${process.argv[1]}`) {
  const api = new CustomerProvisioningAPI();
  
  process.on('SIGINT', async () => {
    await api.stop();
    process.exit(0);
  });
  
  api.start().catch(console.error);
}