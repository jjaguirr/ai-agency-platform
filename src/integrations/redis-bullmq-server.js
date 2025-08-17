#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { Queue, Worker, QueueEvents, Job } from 'bullmq';
import { Redis } from 'ioredis';

// Redis connection (2025 best practices)
const redis = new Redis({
  host: process.env.REDIS_HOST || 'localhost',
  port: parseInt(process.env.REDIS_PORT || '6379'),
  retryDelayOnFailover: 100,
  enableReadyCheck: false,
  maxRetriesPerRequest: null,
  lazyConnect: true,
});

// BullMQ Queues for specialized agents (2025 architecture)
const agentQueues = {
  'research-agents': new Queue('research-agents', { 
    connection: redis,
    defaultJobOptions: {
      removeOnComplete: 50,
      removeOnFail: 100,
      attempts: 3,
      backoff: {
        type: 'exponential',
        delay: 2000,
      },
    }
  }),
  'business-agents': new Queue('business-agents', { 
    connection: redis,
    defaultJobOptions: {
      removeOnComplete: 50,
      removeOnFail: 100,
      attempts: 2,
      backoff: 'fixed',
    }
  }),
  'creative-agents': new Queue('creative-agents', { 
    connection: redis,
    defaultJobOptions: {
      removeOnComplete: 30,
      removeOnFail: 50,
      attempts: 3,
      delay: 1000,
    }
  }),
  'dev-agents': new Queue('dev-agents', { 
    connection: redis,
    defaultJobOptions: {
      removeOnComplete: 100,
      removeOnFail: 200,
      attempts: 5,
      backoff: {
        type: 'exponential',
        delay: 3000,
      },
    }
  }),
  'n8n-architects': new Queue('n8n-architects', { 
    connection: redis,
    defaultJobOptions: {
      removeOnComplete: 25,
      removeOnFail: 75,
      attempts: 2,
    }
  }),
  'coordination': new Queue('coordination', { 
    connection: redis,
    defaultJobOptions: {
      removeOnComplete: 200,
      removeOnFail: 100,
      attempts: 1, // Coordination messages should not retry
    }
  }),
};

// Queue Events for monitoring
const queueEvents = {};
Object.keys(agentQueues).forEach(queueName => {
  queueEvents[queueName] = new QueueEvents(queueName, { connection: redis });
});

// Workers for processing jobs (2025 patterns)
const workers = {};
Object.entries(agentQueues).forEach(([queueName, queue]) => {
  workers[queueName] = new Worker(queueName, async (job) => {
    console.log(`Processing ${queueName} job:`, job.id, job.data);
    
    // Update job progress
    await job.updateProgress(25);
    
    // Simulate agent processing based on type
    const processingTime = getProcessingTime(queueName);
    await new Promise(resolve => setTimeout(resolve, processingTime));
    
    await job.updateProgress(75);
    
    // Return results with metadata
    const result = {
      status: 'completed',
      timestamp: Date.now(),
      agent: queueName,
      jobId: job.id,
      data: job.data,
      processingTime,
      result: `Processed by ${queueName}`,
    };
    
    await job.updateProgress(100);
    return result;
  }, { 
    connection: redis,
    concurrency: getConcurrency(queueName),
    removeOnComplete: { count: 50 },
    removeOnFail: { count: 100 },
  });
});

// Helper functions for agent-specific processing
function getProcessingTime(queueName) {
  const times = {
    'research-agents': 3000,
    'business-agents': 2000, 
    'creative-agents': 5000,
    'dev-agents': 4000,
    'n8n-architects': 6000,
    'coordination': 500,
  };
  return times[queueName] || 2000;
}

function getConcurrency(queueName) {
  const concurrency = {
    'research-agents': 3,
    'business-agents': 2,
    'creative-agents': 1, // Creative work is sequential
    'dev-agents': 4,
    'n8n-architects': 2,
    'coordination': 10, // High concurrency for coordination
  };
  return concurrency[queueName] || 1;
}

const server = new Server(
  { name: 'redis-bullmq-server', version: '2.0.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'agent_queue_job',
        description: 'Queue a job for a specialized agent (2025 multi-agent architecture)',
        inputSchema: {
          type: 'object',
          properties: {
            agentType: {
              type: 'string',
              enum: ['research-agents', 'business-agents', 'creative-agents', 'dev-agents', 'n8n-architects', 'coordination'],
              description: 'Type of specialized agent to use'
            },
            task: {
              type: 'object',
              description: 'Task data for the agent'
            },
            priority: {
              type: 'number',
              minimum: 1,
              maximum: 10,
              default: 5,
              description: 'Job priority (1=low, 10=urgent)'
            },
            delay: {
              type: 'number',
              minimum: 0,
              description: 'Delay in milliseconds before processing'
            },
            metadata: {
              type: 'object',
              description: 'Additional metadata for tracking'
            }
          },
          required: ['agentType', 'task']
        }
      },
      {
        name: 'get_agent_status',
        description: 'Get status of all agent queues or specific agent type',
        inputSchema: {
          type: 'object',
          properties: {
            agentType: {
              type: 'string',
              enum: ['research-agents', 'business-agents', 'creative-agents', 'dev-agents', 'n8n-architects', 'coordination'],
              description: 'Specific agent type to check (optional)'
            }
          }
        }
      },
      {
        name: 'get_job_result',
        description: 'Get result of a completed job',
        inputSchema: {
          type: 'object',
          properties: {
            jobId: { type: 'string', description: 'Job ID to check' },
            agentType: { type: 'string', description: 'Agent type that processed the job' }
          },
          required: ['jobId', 'agentType']
        }
      },
      {
        name: 'agent_coordination',
        description: 'Coordinate between multiple agents (workflow orchestration)',
        inputSchema: {
          type: 'object',
          properties: {
            workflow: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  agentType: { type: 'string' },
                  task: { type: 'object' },
                  dependsOn: { type: 'array', items: { type: 'string' } }
                }
              }
            },
            workflowId: { type: 'string', description: 'Unique workflow identifier' }
          },
          required: ['workflow', 'workflowId']
        }
      },
      {
        name: 'redis_pub_sub',
        description: 'Real-time agent communication via Redis pub/sub',
        inputSchema: {
          type: 'object',
          properties: {
            action: {
              type: 'string',
              enum: ['publish', 'subscribe', 'unsubscribe'],
              description: 'Pub/sub action'
            },
            channel: { type: 'string', description: 'Channel name' },
            message: { type: 'object', description: 'Message to publish' }
          },
          required: ['action', 'channel']
        }
      },
      {
        name: 'get_metrics',
        description: 'Get comprehensive metrics for agent performance monitoring',
        inputSchema: {
          type: 'object',
          properties: {
            timeRange: {
              type: 'string',
              enum: ['1h', '24h', '7d', '30d'],
              default: '1h',
              description: 'Time range for metrics'
            }
          }
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'agent_queue_job': {
        const { agentType, task, priority = 5, delay = 0, metadata = {} } = args;
        const queue = agentQueues[agentType];
        
        if (!queue) {
          throw new Error(`Unknown agent type: ${agentType}`);
        }
        
        const jobData = {
          task,
          metadata: {
            ...metadata,
            queuedAt: Date.now(),
            priority,
          }
        };
        
        const job = await queue.add(`${agentType}-task`, jobData, {
          priority: 10 - priority, // BullMQ uses lower numbers for higher priority
          delay,
          removeOnComplete: 50,
          removeOnFail: 100,
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              jobId: job.id,
              agentType,
              status: 'queued',
              estimatedProcessingTime: getProcessingTime(agentType),
              position: await job.getPosition()
            })
          }]
        };
      }

      case 'get_agent_status': {
        const { agentType } = args;
        const result = {};
        
        const queueNames = agentType ? [agentType] : Object.keys(agentQueues);
        
        for (const name of queueNames) {
          const queue = agentQueues[name];
          const [waiting, active, completed, failed, delayed] = await Promise.all([
            queue.getWaiting(),
            queue.getActive(), 
            queue.getCompleted(),
            queue.getFailed(),
            queue.getDelayed(),
          ]);
          
          result[name] = {
            waiting: waiting.length,
            active: active.length,
            completed: completed.length,
            failed: failed.length,
            delayed: delayed.length,
            isPaused: await queue.isPaused(),
            concurrency: getConcurrency(name),
          };
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(result, null, 2)
          }]
        };
      }

      case 'get_job_result': {
        const { jobId, agentType } = args;
        const queue = agentQueues[agentType];
        
        if (!queue) {
          throw new Error(`Unknown agent type: ${agentType}`);
        }
        
        const job = await queue.getJob(jobId);
        if (!job) {
          return {
            content: [{
              type: 'text',
              text: JSON.stringify({ error: 'Job not found', jobId })
            }]
          };
        }
        
        const state = await job.getState();
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              jobId,
              state,
              data: job.data,
              result: job.returnvalue,
              progress: job.progress,
              processedOn: job.processedOn,
              finishedOn: job.finishedOn,
              attemptsMade: job.attemptsMade,
            })
          }]
        };
      }

      case 'agent_coordination': {
        const { workflow, workflowId } = args;
        const coordinationQueue = agentQueues['coordination'];
        
        // Create coordination job
        const coordinationJob = await coordinationQueue.add('workflow-coordination', {
          workflowId,
          workflow,
          status: 'started',
          createdAt: Date.now(),
        });
        
        // Process workflow steps (simplified orchestration)
        const results = [];
        for (const step of workflow) {
          const { agentType, task, dependsOn = [] } = step;
          
          // Check dependencies (simplified)
          // In production, you'd implement proper dependency resolution
          
          const stepJob = await agentQueues[agentType].add(`workflow-${workflowId}-step`, {
            ...task,
            workflowId,
            stepId: step.id || Date.now(),
          });
          
          results.push({
            stepId: step.id,
            agentType,
            jobId: stepJob.id,
            status: 'queued'
          });
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              workflowId,
              coordinationJobId: coordinationJob.id,
              steps: results
            })
          }]
        };
      }

      case 'redis_pub_sub': {
        const { action, channel, message } = args;
        
        switch (action) {
          case 'publish': {
            const subscribers = await redis.publish(channel, JSON.stringify(message));
            return {
              content: [{
                type: 'text',
                text: JSON.stringify({ 
                  success: true, 
                  channel, 
                  subscribers,
                  message: 'Published successfully'
                })
              }]
            };
          }
          // Note: Subscribe/unsubscribe would need a different Redis connection
          // as it blocks the connection
          default:
            throw new Error(`Pub/sub action ${action} not implemented in this context`);
        }
      }

      case 'get_metrics': {
        const { timeRange } = args;
        
        // Get metrics for all queues
        const metrics = {};
        for (const [name, queue] of Object.entries(agentQueues)) {
          const jobCounts = await queue.getJobCounts();
          metrics[name] = {
            ...jobCounts,
            throughput: await calculateThroughput(queue, timeRange),
            avgProcessingTime: await calculateAvgProcessingTime(queue, timeRange),
          };
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              timestamp: Date.now(),
              timeRange,
              agentMetrics: metrics,
              redisInfo: await redis.info('memory')
            }, null, 2)
          }]
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [{
        type: 'text',
        text: JSON.stringify({ error: error.message })
      }],
      isError: true
    };
  }
});

// Helper functions for metrics
async function calculateThroughput(queue, timeRange) {
  // Simplified throughput calculation
  const completed = await queue.getCompleted();
  const timeMs = { '1h': 3600000, '24h': 86400000, '7d': 604800000, '30d': 2592000000 }[timeRange];
  const recent = completed.filter(job => Date.now() - job.finishedOn < timeMs);
  return recent.length / (timeMs / 3600000); // jobs per hour
}

async function calculateAvgProcessingTime(queue, timeRange) {
  // Simplified average processing time calculation
  const completed = await queue.getCompleted(0, 100);
  const processingTimes = completed
    .filter(job => job.finishedOn && job.processedOn)
    .map(job => job.finishedOn - job.processedOn);
  
  return processingTimes.length > 0 
    ? processingTimes.reduce((a, b) => a + b, 0) / processingTimes.length 
    : 0;
}

async function main() {
  try {
    await redis.connect();
    console.error('Connected to Redis');
    
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error('BullMQ Redis MCP Server running with 2025 architecture');
  } catch (error) {
    console.error('Failed to start server:', error);
    process.exit(1);
  }
}

// Graceful shutdown
process.on('SIGINT', async () => {
  console.error('Shutting down...');
  
  // Close all workers
  await Promise.all(Object.values(workers).map(worker => worker.close()));
  
  // Close all queues
  await Promise.all(Object.values(agentQueues).map(queue => queue.close()));
  
  // Close Redis connection
  await redis.disconnect();
  
  process.exit(0);
});

main().catch(console.error);