/**
 * Temporal Workflow Service - Direct SDK Integration
 * Replaces missing @temporal-io/mcp-server package
 */
import { Client, Connection, WorkflowHandle } from '@temporalio/client';
import { Worker, NativeConnection } from '@temporalio/worker';

export interface AgentWorkflowParams {
  agentType: string;
  customerId: string;
  config: Record<string, any>;
  scheduleInterval?: string; // e.g., '1 hour', '30 minutes'
}

export interface WorkflowStatus {
  workflowId: string;
  runId: string;
  status: 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'TERMINATED';
  result?: any;
  error?: string;
}

export class TemporalService {
  private client?: Client;
  private worker?: Worker;
  private connection?: Connection;

  constructor() {
    this.initializeConnection();
  }

  /**
   * Initialize Temporal client connection
   */
  private async initializeConnection() {
    try {
      const serverUrl = process.env.TEMPORAL_SERVER_URL || 'localhost:7233';
      this.connection = await Connection.connect({ address: serverUrl });
      this.client = new Client({ connection: this.connection });
      console.log('Temporal client initialized successfully');
    } catch (error) {
      console.error('Failed to initialize Temporal client:', error);
      throw new Error(`Temporal connection failed: ${error}`);
    }
  }

  /**
   * Ensure client is connected
   */
  private async ensureClient(): Promise<Client> {
    if (!this.client) {
      await this.initializeConnection();
    }
    return this.client!;
  }

  /**
   * Start an agent workflow for 24/7 operations
   */
  async startAgentWorkflow(params: AgentWorkflowParams): Promise<WorkflowHandle> {
    const client = await this.ensureClient();
    const { agentType, customerId, config, scheduleInterval } = params;
    
    const workflowId = `agent-${agentType}-${customerId}-${Date.now()}`;
    
    try {
      const handle = await client.workflow.start('AgentWorkflow', {
        args: [{ agentType, customerId, config }],
        taskQueue: 'agent-task-queue',
        workflowId,
        memo: {
          agentType,
          customerId,
          createdAt: new Date().toISOString()
        },
        searchAttributes: {
          AgentType: [agentType],
          CustomerId: [customerId]
        }
      });

      console.log(`Started agent workflow: ${workflowId}`);
      return handle;
    } catch (error: any) {
      console.error('Failed to start agent workflow:', error);
      throw new Error(`Workflow start failed: ${error.message}`);
    }
  }

  /**
   * Schedule recurring agent tasks
   */
  async scheduleRecurringAgent(params: AgentWorkflowParams & { cronExpression: string }) {
    const client = await this.ensureClient();
    const { agentType, customerId, config, cronExpression } = params;
    
    const scheduleId = `schedule-${agentType}-${customerId}`;
    
    try {
      const scheduleHandle = await client.schedule.create({
        scheduleId,
        spec: {
          cronExpressions: [cronExpression]
        },
        action: {
          type: 'startWorkflow',
          workflowType: 'AgentWorkflow',
          args: [{ agentType, customerId, config }],
          taskQueue: 'agent-task-queue'
        }
      });

      console.log(`Created schedule: ${scheduleId} with cron: ${cronExpression}`);
      return scheduleHandle;
    } catch (error: any) {
      console.error('Failed to create schedule:', error);
      throw new Error(`Schedule creation failed: ${error.message}`);
    }
  }

  /**
   * Get workflow status
   */
  async getWorkflowStatus(workflowId: string): Promise<WorkflowStatus> {
    const client = await this.ensureClient();
    
    try {
      const handle = client.workflow.getHandle(workflowId);
      const description = await handle.describe();
      
      return {
        workflowId: description.workflowId,
        runId: description.runId,
        status: description.status.name as WorkflowStatus['status'],
        result: description.status.name === 'COMPLETED' ? await handle.result() : undefined,
        error: description.status.name === 'FAILED' ? description.closeTime : undefined
      };
    } catch (error: any) {
      console.error('Failed to get workflow status:', error);
      throw new Error(`Status check failed: ${error.message}`);
    }
  }

  /**
   * Cancel a running workflow
   */
  async cancelWorkflow(workflowId: string, reason?: string): Promise<void> {
    const client = await this.ensureClient();
    
    try {
      const handle = client.workflow.getHandle(workflowId);
      await handle.cancel(reason);
      console.log(`Cancelled workflow: ${workflowId}`);
    } catch (error: any) {
      console.error('Failed to cancel workflow:', error);
      throw new Error(`Workflow cancellation failed: ${error.message}`);
    }
  }

  /**
   * Terminate a workflow (more forceful than cancel)
   */
  async terminateWorkflow(workflowId: string, reason?: string): Promise<void> {
    const client = await this.ensureClient();
    
    try {
      const handle = client.workflow.getHandle(workflowId);
      await handle.terminate(reason);
      console.log(`Terminated workflow: ${workflowId}`);
    } catch (error: any) {
      console.error('Failed to terminate workflow:', error);
      throw new Error(`Workflow termination failed: ${error.message}`);
    }
  }

  /**
   * List all workflows for a customer
   */
  async listCustomerWorkflows(customerId: string, status?: 'RUNNING' | 'COMPLETED' | 'FAILED') {
    const client = await this.ensureClient();
    
    try {
      let query = `CustomerId = "${customerId}"`;
      if (status) {
        query += ` AND WorkflowStatus = "${status}"`;
      }

      const workflows = await client.workflow.list({ query });
      return workflows.workflows.map(wf => ({
        workflowId: wf.workflowId,
        runId: wf.runId,
        status: wf.status,
        startTime: wf.startTime,
        closeTime: wf.closeTime,
        agentType: wf.memo?.agentType
      }));
    } catch (error: any) {
      console.error('Failed to list workflows:', error);
      throw new Error(`Workflow listing failed: ${error.message}`);
    }
  }

  /**
   * Send signal to a running workflow
   */
  async signalWorkflow(workflowId: string, signalName: string, args: any[]) {
    const client = await this.ensureClient();
    
    try {
      const handle = client.workflow.getHandle(workflowId);
      await handle.signal(signalName, ...args);
      console.log(`Sent signal ${signalName} to workflow: ${workflowId}`);
    } catch (error: any) {
      console.error('Failed to send signal:', error);
      throw new Error(`Signal failed: ${error.message}`);
    }
  }

  /**
   * Query workflow state
   */
  async queryWorkflow(workflowId: string, queryName: string, args?: any[]): Promise<any> {
    const client = await this.ensureClient();
    
    try {
      const handle = client.workflow.getHandle(workflowId);
      return await handle.query(queryName, ...(args || []));
    } catch (error: any) {
      console.error('Failed to query workflow:', error);
      throw new Error(`Query failed: ${error.message}`);
    }
  }

  /**
   * Initialize worker for processing workflows
   */
  async createWorker(taskQueue: string = 'agent-task-queue', workflowsPath?: string) {
    try {
      const connection = await NativeConnection.connect({
        address: process.env.TEMPORAL_SERVER_URL || 'localhost:7233'
      });

      this.worker = await Worker.create({
        connection,
        taskQueue,
        workflowsPath: workflowsPath || './src/workflows', // Path to workflow definitions
        activities: {
          // Add your activities here
        }
      });

      console.log(`Worker created for task queue: ${taskQueue}`);
      return this.worker;
    } catch (error: any) {
      console.error('Failed to create worker:', error);
      throw new Error(`Worker creation failed: ${error.message}`);
    }
  }

  /**
   * Start the worker (for production deployment)
   */
  async startWorker() {
    if (!this.worker) {
      throw new Error('Worker not initialized. Call createWorker() first.');
    }
    
    console.log('Starting Temporal worker...');
    await this.worker.run();
  }

  /**
   * Graceful shutdown
   */
  async shutdown() {
    if (this.worker) {
      console.log('Shutting down Temporal worker...');
      this.worker.shutdown();
    }
    
    if (this.connection) {
      await this.connection.close();
    }
  }
}

// Singleton instance
export const temporalService = new TemporalService();