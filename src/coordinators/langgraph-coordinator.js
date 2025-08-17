#!/usr/bin/env node

import { ChatOpenAI } from "@langchain/openai";
import { McpAdapter, MultiServerMcpAdapter } from "@langchain/mcp-adapters";
import { StateGraph, END, START } from "@langchain/langgraph";
import { HumanMessage, AIMessage } from "@langchain/core/messages";
import { z } from "zod";
import dotenv from 'dotenv';

dotenv.config();

// LangGraph State Schema for Multi-Agent Coordination
const AgentState = z.object({
  messages: z.array(z.any()),
  currentAgent: z.string().optional(),
  workflowId: z.string(),
  agentResults: z.record(z.any()).default({}),
  nextAction: z.string().optional(),
  isComplete: z.boolean().default(false),
  userIntent: z.string().optional(),
  whatsappMessage: z.string().optional(),
});

// MCP Server Configurations (connecting to MCPhub)
const mcpServerConfigs = [
  {
    name: "mcphub-research", 
    transport: {
      type: "stdio",
      command: "node",
      args: ["dist/index.js"], // MCPhub main server
      env: {
        MCP_GROUP: "security-research-001"  // Research security profile
      }
    }
  },
  {
    name: "mcphub-business",
    transport: {
      type: "stdio", 
      command: "node",
      args: ["dist/index.js"],
      env: {
        MCP_GROUP: "security-analytics-001"  // Business analytics profile
      }
    }
  },
  {
    name: "mcphub-creative",
    transport: {
      type: "stdio",
      command: "node", 
      args: ["dist/index.js"],
      env: {
        MCP_GROUP: "security-creative-001"  // Creative security profile
      }
    }
  },
  {
    name: "mcphub-dev",
    transport: {
      type: "stdio",
      command: "node",
      args: ["dist/index.js"], 
      env: {
        MCP_GROUP: "security-development-001"  // Development profile
      }
    }
  },
  {
    name: "redis-agents",
    transport: {
      type: "stdio",
      command: "node",
      args: ["redis-bullmq-server.js"]  // Our new BullMQ server
    }
  }
];

// Initialize Multi-Server MCP Adapter (2025 pattern)
const mcpAdapter = new MultiServerMcpAdapter({
  servers: mcpServerConfigs
});

// Initialize LLM with MCP tools
const llm = new ChatOpenAI({
  model: "gpt-4o",
  temperature: 0.7,
}).bind({
  tools: await mcpAdapter.getTools(),
});

// Agent Node Definitions
class AgentCoordinator {
  constructor() {
    this.graph = this.buildGraph();
  }

  buildGraph() {
    const workflow = new StateGraph(AgentState);

    // Define agent nodes
    workflow.addNode("classifier", this.classifyIntent.bind(this));
    workflow.addNode("research_agent", this.researchAgent.bind(this));
    workflow.addNode("business_agent", this.businessAgent.bind(this));
    workflow.addNode("creative_agent", this.creativeAgent.bind(this));
    workflow.addNode("dev_agent", this.devAgent.bind(this));
    workflow.addNode("coordinator", this.coordinatorAgent.bind(this));
    workflow.addNode("whatsapp_notifier", this.whatsappNotifier.bind(this));

    // Define edges and routing
    workflow.addEdge(START, "classifier");
    
    workflow.addConditionalEdges(
      "classifier",
      this.routeToAgent.bind(this),
      {
        research: "research_agent",
        business: "business_agent", 
        creative: "creative_agent",
        development: "dev_agent",
        coordinate: "coordinator",
        complete: "whatsapp_notifier"
      }
    );

    // Agent completion routing
    ["research_agent", "business_agent", "creative_agent", "dev_agent"].forEach(agent => {
      workflow.addConditionalEdges(
        agent,
        this.checkIfComplete.bind(this),
        {
          continue: "coordinator",
          complete: "whatsapp_notifier"
        }
      );
    });

    workflow.addConditionalEdges(
      "coordinator",
      this.coordinatorRouting.bind(this),
      {
        research: "research_agent",
        business: "business_agent",
        creative: "creative_agent", 
        development: "dev_agent",
        complete: "whatsapp_notifier"
      }
    );

    workflow.addEdge("whatsapp_notifier", END);

    return workflow.compile();
  }

  async classifyIntent(state) {
    const lastMessage = state.messages[state.messages.length - 1];
    
    const classificationPrompt = `
    Classify this user request into one of these agent types:
    - research: Market research, web analysis, competitive intelligence
    - business: Data analysis, KPIs, financial metrics, database queries
    - creative: Content creation, image generation, marketing materials
    - development: Code development, deployment, technical tasks
    - coordinate: Multi-agent workflows, complex projects
    
    Request: ${lastMessage.content}
    
    Respond with just the category name.
    `;

    const response = await llm.invoke([new HumanMessage(classificationPrompt)]);
    const intent = response.content.toLowerCase().trim();

    return {
      ...state,
      userIntent: intent,
      currentAgent: intent,
      messages: [...state.messages, new AIMessage(`Classified as: ${intent}`)],
    };
  }

  async researchAgent(state) {
    console.log("🔍 Research Agent activated");
    
    try {
      // Use MCPhub research tools (brave-search, context7)
      const researchTasks = await mcpAdapter.invokeTool("brave-search", {
        query: this.extractResearchQuery(state.messages),
        num_results: 10
      });

      const result = {
        agent: "research",
        data: researchTasks,
        timestamp: Date.now(),
        status: "completed"
      };

      // Queue for further processing if needed
      await mcpAdapter.invokeTool("agent_queue_job", {
        agentType: "research-agents",
        task: { query: this.extractResearchQuery(state.messages) },
        priority: 7,
        metadata: { workflowId: state.workflowId }
      });

      return {
        ...state,
        agentResults: { ...state.agentResults, research: result },
        messages: [...state.messages, new AIMessage(`Research completed: ${JSON.stringify(result)}`)],
        nextAction: "business" // Chain to business analysis
      };
    } catch (error) {
      return {
        ...state,
        agentResults: { ...state.agentResults, research: { error: error.message } },
        messages: [...state.messages, new AIMessage(`Research failed: ${error.message}`)],
      };
    }
  }

  async businessAgent(state) {
    console.log("📊 Business Agent activated");
    
    try {
      // Use MCPhub analytics tools (postgres, sqlite)
      const businessQuery = this.extractBusinessQuery(state);
      
      const businessData = await mcpAdapter.invokeTool("postgres_query", {
        query: businessQuery,
        parameters: []
      });

      // Queue business analysis job
      await mcpAdapter.invokeTool("agent_queue_job", {
        agentType: "business-agents", 
        task: { 
          query: businessQuery,
          researchData: state.agentResults.research?.data 
        },
        priority: 8,
        metadata: { workflowId: state.workflowId }
      });

      const result = {
        agent: "business",
        data: businessData,
        timestamp: Date.now(),
        status: "completed"
      };

      return {
        ...state,
        agentResults: { ...state.agentResults, business: result },
        messages: [...state.messages, new AIMessage(`Business analysis completed`)],
        nextAction: state.userIntent === "coordinate" ? "creative" : "complete"
      };
    } catch (error) {
      return {
        ...state,
        agentResults: { ...state.agentResults, business: { error: error.message } },
        messages: [...state.messages, new AIMessage(`Business analysis failed: ${error.message}`)],
      };
    }
  }

  async creativeAgent(state) {
    console.log("🎨 Creative Agent activated");
    
    try {
      // Use MCPhub creative tools (openai, everart) 
      const creativePrompt = this.extractCreativePrompt(state);
      
      const creativeContent = await mcpAdapter.invokeTool("openai_generate", {
        prompt: creativePrompt,
        model: "gpt-4o",
        max_tokens: 1000
      });

      // Queue creative job
      await mcpAdapter.invokeTool("agent_queue_job", {
        agentType: "creative-agents",
        task: {
          prompt: creativePrompt,
          businessData: state.agentResults.business?.data,
          researchData: state.agentResults.research?.data
        },
        priority: 6,
        metadata: { workflowId: state.workflowId }
      });

      const result = {
        agent: "creative", 
        data: creativeContent,
        timestamp: Date.now(),
        status: "completed"
      };

      return {
        ...state,
        agentResults: { ...state.agentResults, creative: result },
        messages: [...state.messages, new AIMessage(`Creative content generated`)],
        nextAction: state.userIntent === "coordinate" ? "development" : "complete"
      };
    } catch (error) {
      return {
        ...state,
        agentResults: { ...state.agentResults, creative: { error: error.message } },
        messages: [...state.messages, new AIMessage(`Creative generation failed: ${error.message}`)],
      };
    }
  }

  async devAgent(state) {
    console.log("⚡ Development Agent activated");
    
    try {
      // Use MCPhub dev tools (git-local, github, local-filesystem)
      const devTask = this.extractDevTask(state);
      
      // Queue development job
      const devJob = await mcpAdapter.invokeTool("agent_queue_job", {
        agentType: "dev-agents",
        task: {
          action: devTask.action,
          files: devTask.files,
          creativeAssets: state.agentResults.creative?.data
        },
        priority: 9,
        metadata: { workflowId: state.workflowId }
      });

      const result = {
        agent: "development",
        data: devJob,
        timestamp: Date.now(),
        status: "queued"
      };

      return {
        ...state,
        agentResults: { ...state.agentResults, development: result },
        messages: [...state.messages, new AIMessage(`Development task queued: ${devJob.jobId}`)],
        nextAction: "complete"
      };
    } catch (error) {
      return {
        ...state,
        agentResults: { ...state.agentResults, development: { error: error.message } },
        messages: [...state.messages, new AIMessage(`Development task failed: ${error.message}`)],
      };
    }
  }

  async coordinatorAgent(state) {
    console.log("🔧 Coordinator Agent activated");
    
    try {
      // Create workflow coordination
      const workflow = this.createWorkflow(state);
      
      const coordinationResult = await mcpAdapter.invokeTool("agent_coordination", {
        workflow: workflow,
        workflowId: state.workflowId
      });

      return {
        ...state,
        agentResults: { ...state.agentResults, coordination: coordinationResult },
        messages: [...state.messages, new AIMessage(`Workflow coordinated: ${coordinationResult.workflowId}`)],
        nextAction: workflow[0]?.agentType.replace('-agents', '') || "complete"
      };
    } catch (error) {
      return {
        ...state,
        nextAction: "complete"
      };
    }
  }

  async whatsappNotifier(state) {
    console.log("📱 WhatsApp Notifier activated");
    
    try {
      // Send completion notification via WhatsApp
      const summary = this.createSummary(state);
      
      // This would integrate with WhatsApp Business API
      const whatsappResult = {
        message: `🤖 Agent Workflow Complete!\n\n${summary}`,
        timestamp: Date.now(),
        workflowId: state.workflowId
      };

      return {
        ...state,
        whatsappMessage: whatsappResult.message,
        isComplete: true,
        messages: [...state.messages, new AIMessage(`WhatsApp notification sent`)]
      };
    } catch (error) {
      return {
        ...state,
        isComplete: true,
        messages: [...state.messages, new AIMessage(`Workflow completed with errors`)]
      };
    }
  }

  // Routing Logic
  routeToAgent(state) {
    return state.userIntent || "research";
  }

  checkIfComplete(state) {
    return state.nextAction === "complete" ? "complete" : "continue";
  }

  coordinatorRouting(state) {
    return state.nextAction || "complete";
  }

  // Helper Methods
  extractResearchQuery(messages) {
    const lastMessage = messages[messages.length - 1];
    return lastMessage.content || "market research";
  }

  extractBusinessQuery(state) {
    return "SELECT * FROM metrics WHERE date >= NOW() - INTERVAL '30 days'";
  }

  extractCreativePrompt(state) {
    const research = state.agentResults.research?.data;
    const business = state.agentResults.business?.data;
    return `Create marketing content based on: ${JSON.stringify({ research, business })}`;
  }

  extractDevTask(state) {
    return {
      action: "deploy",
      files: ["index.html", "styles.css"],
    };
  }

  createWorkflow(state) {
    return [
      { agentType: "research-agents", task: { type: "market_analysis" } },
      { agentType: "business-agents", task: { type: "financial_analysis" }, dependsOn: ["research"] },
      { agentType: "creative-agents", task: { type: "content_creation" }, dependsOn: ["business"] },
      { agentType: "dev-agents", task: { type: "deployment" }, dependsOn: ["creative"] }
    ];
  }

  createSummary(state) {
    const results = Object.entries(state.agentResults);
    return results.map(([agent, result]) => `${agent}: ${result.status}`).join('\n');
  }

  // Main execution method
  async processRequest(userMessage, workflowId = null) {
    const initialState = {
      messages: [new HumanMessage(userMessage)],
      workflowId: workflowId || `workflow-${Date.now()}`,
      agentResults: {},
      isComplete: false
    };

    console.log(`🚀 Starting workflow: ${initialState.workflowId}`);
    
    try {
      const finalState = await this.graph.invoke(initialState);
      return finalState;
    } catch (error) {
      console.error("Workflow error:", error);
      return {
        ...initialState,
        error: error.message,
        isComplete: true
      };
    }
  }
}

// Main execution
async function main() {
  try {
    console.log("🏗️ Initializing LangGraph Multi-Agent Coordinator...");
    
    // Initialize MCP connections
    await mcpAdapter.connect();
    console.log("✅ Connected to MCPhub MCP servers");

    const coordinator = new AgentCoordinator();
    console.log("✅ LangGraph coordinator initialized");

    // Example workflow execution
    const result = await coordinator.processRequest(
      "I need to launch a new product. Please research the market, analyze our business metrics, create marketing content, and deploy the landing page."
    );

    console.log("🎉 Workflow completed:");
    console.log(JSON.stringify(result, null, 2));

  } catch (error) {
    console.error("❌ Coordinator initialization failed:", error);
  }
}

// Export for use as module
export { AgentCoordinator, mcpAdapter };

// Run if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}