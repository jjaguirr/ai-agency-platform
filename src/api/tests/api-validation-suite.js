#!/usr/bin/env node

import { Redis } from 'ioredis';
import fetch from 'node-fetch';
import WebSocket from 'ws';
import { v4 as uuidv4 } from 'uuid';

/**
 * API Validation Test Suite for Phase 1 Foundation
 * 
 * Tests all API patterns for dual-agent coordination:
 * - Cross-system message bus validation
 * - Customer provisioning API testing
 * - Real-time WebSocket communication
 * - Database API patterns validation
 * 
 * API Developer Implementation for Phase 1 Completion
 */
export class APIValidationSuite {
  constructor(config = {}) {
    this.config = {
      redisUrl: config.redisUrl || 'redis://localhost:6379',
      apiBaseUrl: config.apiBaseUrl || 'http://localhost:3001',
      wsUrl: config.wsUrl || 'ws://localhost:8080',
      testTimeout: config.testTimeout || 30000,
      ...config
    };

    this.redis = new Redis(this.config.redisUrl);
    this.testResults = [];
    this.apiMetrics = {
      testsRun: 0,
      testsPassed: 0,
      testsFailed: 0,
      averageResponseTime: 0,
      startTime: Date.now()
    };
  }

  /**
   * Run complete API validation suite
   */
  async runValidationSuite() {
    console.log('🧪 Starting API Validation Suite for Phase 1...\n');

    const testSuites = [
      { name: 'Redis Message Bus API', test: this.testRedisMessageBusAPI.bind(this) },
      { name: 'Cross-System Communication', test: this.testCrossSystemCommunication.bind(this) },
      { name: 'Customer Provisioning API', test: this.testCustomerProvisioningAPI.bind(this) },
      { name: 'LAUNCH Bot Lifecycle API', test: this.testLaunchBotLifecycleAPI.bind(this) },
      { name: 'AI Model Configuration API', test: this.testAIModelConfigurationAPI.bind(this) },
      { name: 'Real-time WebSocket API', test: this.testWebSocketAPI.bind(this) },
      { name: 'Database API Patterns', test: this.testDatabaseAPIPatterns.bind(this) },
      { name: 'API Performance & Security', test: this.testAPIPerformanceAndSecurity.bind(this) }
    ];

    for (const suite of testSuites) {
      console.log(`\n📋 Running ${suite.name} Tests...`);
      try {
        const suiteResults = await suite.test();
        this.logTestResults(suite.name, suiteResults);
      } catch (error) {
        console.error(`❌ Test suite ${suite.name} failed:`, error.message);
        this.testResults.push({
          suite: suite.name,
          status: 'failed',
          error: error.message,
          timestamp: Date.now()
        });
      }
    }

    return this.generateValidationReport();
  }

  /**
   * Test Redis Message Bus API patterns
   */
  async testRedisMessageBusAPI() {
    const tests = [];
    
    // Test 1: Basic Redis connectivity
    tests.push(await this.runTest('Redis Connectivity', async () => {
      const ping = await this.redis.ping();
      if (ping !== 'PONG') throw new Error('Redis ping failed');
      return { status: 'connected', ping };
    }));

    // Test 2: Cross-system message publishing
    tests.push(await this.runTest('Cross-System Message Publishing', async () => {
      const testMessage = {
        id: uuidv4(),
        type: 'status-update',
        timestamp: Date.now(),
        payload: { agentId: 'test-agent', status: 'testing', progress: 50 }
      };

      const subscribers = await this.redis.publish('claude-code:outbound', JSON.stringify(testMessage));
      return { message: testMessage, subscribers };
    }));

    // Test 3: Message subscription and handling
    tests.push(await this.runTest('Message Subscription Pattern', async () => {
      const testSubscriber = new Redis(this.config.redisUrl);
      let receivedMessage = null;

      testSubscriber.subscribe('test-channel');
      testSubscriber.on('message', (channel, message) => {
        if (channel === 'test-channel') {
          receivedMessage = JSON.parse(message);
        }
      });

      // Publish test message
      const testMessage = {
        id: uuidv4(),
        type: 'test-message',
        timestamp: Date.now(),
        payload: { test: 'subscription-validation' }
      };

      await this.redis.publish('test-channel', JSON.stringify(testMessage));
      
      // Wait for message reception
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      await testSubscriber.quit();
      
      if (!receivedMessage) throw new Error('Message not received');
      return { sent: testMessage, received: receivedMessage };
    }));

    // Test 4: Message queue patterns (BullMQ integration)
    tests.push(await this.runTest('BullMQ Queue Integration', async () => {
      const queueMessage = {
        id: uuidv4(),
        type: 'agent_queue_job',
        timestamp: Date.now(),
        payload: {
          agentType: 'research-agents',
          task: { query: 'API validation test' },
          priority: 5
        }
      };

      await this.redis.publish('queue:research-agents', JSON.stringify(queueMessage));
      return { queued: queueMessage };
    }));

    return tests;
  }

  /**
   * Test cross-system communication patterns
   */
  async testCrossSystemCommunication() {
    const tests = [];

    // Test 1: Claude Code to Infrastructure messaging
    tests.push(await this.runTest('Claude Code → Infrastructure Message', async () => {
      const message = {
        id: uuidv4(),
        type: 'tool-request',
        timestamp: Date.now(),
        agentId: 'claude-dev-agent-1',
        payload: {
          toolName: 'business-intelligence',
          params: { query: 'test data analysis' },
          callbackId: uuidv4()
        }
      };

      await this.redis.publish('claude-code:outbound', JSON.stringify(message));
      return { message, direction: 'claude-code → infrastructure' };
    }));

    // Test 2: Infrastructure to Claude Code response
    tests.push(await this.runTest('Infrastructure → Claude Code Response', async () => {
      const message = {
        id: uuidv4(),
        type: 'task-completion',
        timestamp: Date.now(),
        agentId: 'infra-business-agent-1',
        payload: {
          originalRequest: uuidv4(),
          result: { status: 'completed', data: 'test analysis result' },
          executionTime: 2500
        }
      };

      await this.redis.publish('infrastructure:outbound', JSON.stringify(message));
      return { message, direction: 'infrastructure → claude-code' };
    }));

    // Test 3: System coordination message
    tests.push(await this.runTest('System Coordination Message', async () => {
      const message = {
        id: uuidv4(),
        type: 'workflow-coordination',
        timestamp: Date.now(),
        payload: {
          workflowId: uuidv4(),
          stage: 'cross-system-handoff',
          from: 'claude-code-system',
          to: 'infrastructure-system',
          handoffData: { artifacts: ['code.js', 'tests.js'], deployment: 'ready' }
        }
      };

      await this.redis.publish('system:coordination', JSON.stringify(message));
      return { message, type: 'coordination' };
    }));

    return tests;
  }

  /**
   * Test Customer Provisioning API endpoints
   */
  async testCustomerProvisioningAPI() {
    const tests = [];
    let authToken = null;

    // Test 1: API health check
    tests.push(await this.runTest('API Health Check', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/health`);
      const data = await response.json();
      if (response.status !== 200) throw new Error(`Health check failed: ${response.status}`);
      return data;
    }));

    // Test 2: Authentication
    tests.push(await this.runTest('Authentication', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'admin@agency.ai',
          password: 'admin123'
        })
      });

      const data = await response.json();
      if (response.status !== 200) throw new Error(`Authentication failed: ${data.error}`);
      
      authToken = data.access_token;
      return { authenticated: true, token_type: data.token_type };
    }));

    // Test 3: Create customer
    tests.push(await this.runTest('Create Customer', async () => {
      const customer = {
        name: 'Test Customer API Validation',
        email: `test-${Date.now()}@validation.test`,
        ai_model: 'openai-gpt-4o',
        industry: 'Technology',
        compliance_requirements: ['GDPR'],
        custom_tools: ['web-search', 'content-generation']
      };

      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify(customer)
      });

      const data = await response.json();
      if (response.status !== 201) throw new Error(`Customer creation failed: ${data.error}`);
      
      return { customer: data.customer, created: true };
    }));

    return tests;
  }

  /**
   * Test LAUNCH Bot lifecycle API
   */
  async testLaunchBotLifecycleAPI() {
    const tests = [];
    let customerId = null;

    // First create a customer for testing
    const customer = await this.createTestCustomer();
    customerId = customer.id;

    // Test 1: Initialize LAUNCH Bot
    tests.push(await this.runTest('Initialize LAUNCH Bot', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers/${customerId}/launch-bot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await this.getAuthToken()}`
        },
        body: JSON.stringify({
          initial_message: 'I want to automate my customer support',
          conversation_history: []
        })
      });

      const data = await response.json();
      if (response.status !== 200) throw new Error(`Bot initialization failed: ${data.error}`);
      
      return { bot_initialized: true, stage: data.bot_status.stage };
    }));

    // Test 2: Get LAUNCH Bot status
    tests.push(await this.runTest('Get LAUNCH Bot Status', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers/${customerId}/launch-bot`, {
        headers: {
          'Authorization': `Bearer ${await this.getAuthToken()}`
        }
      });

      const data = await response.json();
      if (response.status !== 200) throw new Error(`Failed to get bot status: ${data.error}`);
      
      return { bot_status: data.bot_status };
    }));

    // Test 3: Update bot stage
    tests.push(await this.runTest('Update Bot Stage', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers/${customerId}/launch-bot/stage`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await this.getAuthToken()}`
        },
        body: JSON.stringify({
          stage: 'learning',
          progress: 60,
          configuration: { business_type: 'support', priority_high: true }
        })
      });

      const data = await response.json();
      if (response.status !== 200) throw new Error(`Stage update failed: ${data.error}`);
      
      return { stage_updated: true, new_stage: data.bot_status.stage };
    }));

    return tests;
  }

  /**
   * Test AI Model configuration API
   */
  async testAIModelConfigurationAPI() {
    const tests = [];
    
    // Test 1: List available AI models
    tests.push(await this.runTest('List Available AI Models', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/ai-models`, {
        headers: {
          'Authorization': `Bearer ${await this.getAuthToken()}`
        }
      });

      const data = await response.json();
      if (response.status !== 200) throw new Error(`Failed to list AI models: ${data.error}`);
      
      return { 
        models_count: data.ai_models.length,
        default_model: data.default_model,
        models: data.ai_models.map(m => m.id)
      };
    }));

    // Test 2: Set customer AI model
    const customer = await this.createTestCustomer();
    tests.push(await this.runTest('Set Customer AI Model', async () => {
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers/${customer.id}/ai-model`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${await this.getAuthToken()}`
        },
        body: JSON.stringify({
          ai_model: 'claude-3.5-sonnet',
          reason: 'Customer prefers Anthropic models'
        })
      });

      const data = await response.json();
      if (response.status !== 200) throw new Error(`AI model update failed: ${data.error}`);
      
      return { model_updated: true, new_model: data.customer.ai_model };
    }));

    return tests;
  }

  /**
   * Test WebSocket real-time communication
   */
  async testWebSocketAPI() {
    const tests = [];
    
    // Test 1: WebSocket connection
    tests.push(await this.runTest('WebSocket Connection', async () => {
      const token = await this.getAuthToken();
      const wsUrl = `${this.config.wsUrl}?token=${token}`;
      
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl, {
          headers: { 'X-Client-Type': 'api-test' }
        });

        const timeout = setTimeout(() => {
          ws.close();
          reject(new Error('WebSocket connection timeout'));
        }, 5000);

        ws.on('open', () => {
          clearTimeout(timeout);
          ws.close();
          resolve({ connected: true, url: wsUrl });
        });

        ws.on('error', (error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    }));

    // Test 2: WebSocket message handling
    tests.push(await this.runTest('WebSocket Message Handling', async () => {
      const token = await this.getAuthToken();
      const wsUrl = `${this.config.wsUrl}?token=${token}`;
      
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(wsUrl);
        let receivedMessages = [];

        const timeout = setTimeout(() => {
          ws.close();
          reject(new Error('WebSocket message test timeout'));
        }, 10000);

        ws.on('open', () => {
          // Send test message
          ws.send(JSON.stringify({
            type: 'api:metrics-request',
            id: uuidv4()
          }));
        });

        ws.on('message', (data) => {
          const message = JSON.parse(data);
          receivedMessages.push(message);
          
          if (message.type === 'api:metrics-response') {
            clearTimeout(timeout);
            ws.close();
            resolve({ 
              messages_received: receivedMessages.length,
              metrics_response: message.data ? true : false
            });
          }
        });

        ws.on('error', (error) => {
          clearTimeout(timeout);
          reject(error);
        });
      });
    }));

    return tests;
  }

  /**
   * Test database API patterns
   */
  async testDatabaseAPIPatterns() {
    const tests = [];
    
    // Test 1: Customer CRUD operations
    tests.push(await this.runTest('Customer CRUD Operations', async () => {
      const token = await this.getAuthToken();
      
      // Create
      const createResponse = await fetch(`${this.config.apiBaseUrl}/api/v1/customers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: 'CRUD Test Customer',
          email: `crud-${Date.now()}@test.com`,
          ai_model: 'openai-gpt-4o'
        })
      });

      const customer = (await createResponse.json()).customer;
      if (createResponse.status !== 201) throw new Error('Customer creation failed');

      // Read
      const readResponse = await fetch(`${this.config.apiBaseUrl}/api/v1/customers/${customer.id}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (readResponse.status !== 200) throw new Error('Customer read failed');

      // Update would go here in full implementation
      // Delete would go here in full implementation

      return { 
        create: 'success', 
        read: 'success',
        customer_id: customer.id
      };
    }));

    // Test 2: Database query performance
    tests.push(await this.runTest('Database Query Performance', async () => {
      const token = await this.getAuthToken();
      const startTime = Date.now();
      
      const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers?limit=50`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      const queryTime = Date.now() - startTime;
      const data = await response.json();
      
      if (response.status !== 200) throw new Error('Query failed');
      
      return {
        query_time_ms: queryTime,
        records_returned: data.customers?.length || 0,
        performance: queryTime < 1000 ? 'good' : 'slow'
      };
    }));

    return tests;
  }

  /**
   * Test API performance and security
   */
  async testAPIPerformanceAndSecurity() {
    const tests = [];
    
    // Test 1: API response time
    tests.push(await this.runTest('API Response Time', async () => {
      const iterations = 10;
      const responseTimes = [];
      
      for (let i = 0; i < iterations; i++) {
        const startTime = Date.now();
        const response = await fetch(`${this.config.apiBaseUrl}/health`);
        const responseTime = Date.now() - startTime;
        responseTimes.push(responseTime);
        
        if (response.status !== 200) throw new Error(`Health check failed on iteration ${i + 1}`);
      }
      
      const averageTime = responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length;
      
      return {
        iterations,
        average_response_time_ms: Math.round(averageTime),
        min_time_ms: Math.min(...responseTimes),
        max_time_ms: Math.max(...responseTimes),
        performance: averageTime < 200 ? 'excellent' : averageTime < 500 ? 'good' : 'slow'
      };
    }));

    // Test 2: Authentication security
    tests.push(await this.runTest('Authentication Security', async () => {
      // Test without token
      const noTokenResponse = await fetch(`${this.config.apiBaseUrl}/api/v1/customers`);
      if (noTokenResponse.status !== 401) throw new Error('Should reject requests without token');
      
      // Test with invalid token
      const invalidTokenResponse = await fetch(`${this.config.apiBaseUrl}/api/v1/customers`, {
        headers: { 'Authorization': 'Bearer invalid-token' }
      });
      if (invalidTokenResponse.status !== 403) throw new Error('Should reject requests with invalid token');
      
      return {
        no_token_rejection: true,
        invalid_token_rejection: true,
        security_level: 'good'
      };
    }));

    // Test 3: Rate limiting (if implemented)
    tests.push(await this.runTest('Rate Limiting Behavior', async () => {
      // This is a simplified test - in production you'd test actual rate limits
      const rapidRequests = [];
      for (let i = 0; i < 5; i++) {
        rapidRequests.push(fetch(`${this.config.apiBaseUrl}/health`));
      }
      
      const responses = await Promise.all(rapidRequests);
      const successCount = responses.filter(r => r.status === 200).length;
      
      return {
        rapid_requests_sent: 5,
        successful_responses: successCount,
        rate_limiting: successCount < 5 ? 'active' : 'not_detected'
      };
    }));

    return tests;
  }

  /**
   * Utility methods
   */
  async getAuthToken() {
    const response = await fetch(`${this.config.apiBaseUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: 'admin@agency.ai',
        password: 'admin123'
      })
    });
    
    const data = await response.json();
    return data.access_token;
  }

  async createTestCustomer() {
    const token = await this.getAuthToken();
    const response = await fetch(`${this.config.apiBaseUrl}/api/v1/customers`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        name: `Test Customer ${Date.now()}`,
        email: `test-${Date.now()}@validation.test`,
        ai_model: 'openai-gpt-4o'
      })
    });

    const data = await response.json();
    return data.customer;
  }

  async runTest(testName, testFunction) {
    this.apiMetrics.testsRun++;
    const startTime = Date.now();
    
    try {
      const result = await Promise.race([
        testFunction(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Test timeout')), this.config.testTimeout)
        )
      ]);
      
      const responseTime = Date.now() - startTime;
      this.updateAverageResponseTime(responseTime);
      this.apiMetrics.testsPassed++;
      
      return {
        name: testName,
        status: 'passed',
        result,
        responseTime,
        timestamp: Date.now()
      };
    } catch (error) {
      const responseTime = Date.now() - startTime;
      this.apiMetrics.testsFailed++;
      
      return {
        name: testName,
        status: 'failed',
        error: error.message,
        responseTime,
        timestamp: Date.now()
      };
    }
  }

  updateAverageResponseTime(responseTime) {
    if (this.apiMetrics.averageResponseTime === 0) {
      this.apiMetrics.averageResponseTime = responseTime;
    } else {
      this.apiMetrics.averageResponseTime = 
        (this.apiMetrics.averageResponseTime * 0.9) + (responseTime * 0.1);
    }
  }

  logTestResults(suiteName, tests) {
    const passed = tests.filter(t => t.status === 'passed').length;
    const failed = tests.filter(t => t.status === 'failed').length;
    
    console.log(`  ✅ Passed: ${passed}`);
    console.log(`  ❌ Failed: ${failed}`);
    
    tests.forEach(test => {
      const icon = test.status === 'passed' ? '✅' : '❌';
      const time = `${test.responseTime}ms`;
      console.log(`    ${icon} ${test.name} (${time})`);
      
      if (test.status === 'failed') {
        console.log(`      Error: ${test.error}`);
      }
    });
    
    this.testResults.push({
      suite: suiteName,
      tests,
      passed,
      failed,
      timestamp: Date.now()
    });
  }

  generateValidationReport() {
    const totalDuration = Date.now() - this.apiMetrics.startTime;
    const overallPassRate = (this.apiMetrics.testsPassed / this.apiMetrics.testsRun * 100).toFixed(1);
    
    const report = {
      summary: {
        title: 'Phase 1 API Validation Report',
        timestamp: new Date().toISOString(),
        duration_ms: totalDuration,
        tests_run: this.apiMetrics.testsRun,
        tests_passed: this.apiMetrics.testsPassed,
        tests_failed: this.apiMetrics.testsFailed,
        pass_rate_percent: parseFloat(overallPassRate),
        average_response_time_ms: Math.round(this.apiMetrics.averageResponseTime),
        overall_status: this.apiMetrics.testsFailed === 0 ? 'PASSED' : 'FAILED'
      },
      test_suites: this.testResults,
      recommendations: this.generateRecommendations()
    };

    console.log('\n' + '='.repeat(80));
    console.log('📊 PHASE 1 API VALIDATION REPORT');
    console.log('='.repeat(80));
    console.log(`Status: ${report.summary.overall_status}`);
    console.log(`Tests Run: ${report.summary.tests_run}`);
    console.log(`Pass Rate: ${report.summary.pass_rate_percent}%`);
    console.log(`Average Response Time: ${report.summary.average_response_time_ms}ms`);
    console.log(`Duration: ${(report.summary.duration_ms / 1000).toFixed(1)}s`);
    
    if (report.recommendations.length > 0) {
      console.log('\n🔧 Recommendations:');
      report.recommendations.forEach((rec, i) => {
        console.log(`  ${i + 1}. ${rec}`);
      });
    }
    
    console.log('\n✅ API Validation Suite Complete');
    
    return report;
  }

  generateRecommendations() {
    const recommendations = [];
    
    if (this.apiMetrics.averageResponseTime > 1000) {
      recommendations.push('API response times are high - consider performance optimization');
    }
    
    if (this.apiMetrics.testsFailed > 0) {
      recommendations.push('Some tests failed - review error logs and fix failing components');
    }
    
    if (this.apiMetrics.testsPassed / this.apiMetrics.testsRun < 0.95) {
      recommendations.push('Pass rate is below 95% - additional testing and fixes needed');
    }
    
    return recommendations;
  }

  async cleanup() {
    await this.redis.quit();
  }
}

export default APIValidationSuite;

// CLI execution
if (import.meta.url === `file://${process.argv[1]}`) {
  const suite = new APIValidationSuite();
  
  suite.runValidationSuite()
    .then(report => {
      console.log('\n📄 Full report available in test results');
      process.exit(report.summary.overall_status === 'PASSED' ? 0 : 1);
    })
    .catch(error => {
      console.error('❌ Validation suite failed:', error);
      process.exit(1);
    })
    .finally(() => {
      suite.cleanup();
    });
}