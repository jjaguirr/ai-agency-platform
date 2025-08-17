#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import axios from 'axios';
import express from 'express';
import dotenv from 'dotenv';

dotenv.config();

// WhatsApp Business API Configuration (2025 Cloud API)
const WHATSAPP_CONFIG = {
  baseURL: 'https://graph.facebook.com/v21.0',
  phoneNumberId: process.env.WHATSAPP_PHONE_NUMBER_ID,
  accessToken: process.env.WHATSAPP_ACCESS_TOKEN,
  webhookVerifyToken: process.env.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
  businessAccountId: process.env.WHATSAPP_BUSINESS_ACCOUNT_ID,
};

// Message templates for agent coordination
const MESSAGE_TEMPLATES = {
  agentStarted: (agentType, taskDescription) => 
    `🤖 *Agent Started*\n\n` +
    `Agent: ${agentType.toUpperCase()}\n` +
    `Task: ${taskDescription}\n` +
    `Time: ${new Date().toLocaleString()}\n\n` +
    `Status: IN_PROGRESS ⚡`,

  agentCompleted: (agentType, result, duration) =>
    `✅ *Agent Completed*\n\n` +
    `Agent: ${agentType.toUpperCase()}\n` +
    `Duration: ${Math.round(duration/1000)}s\n` +
    `Result: ${result.substring(0, 200)}${result.length > 200 ? '...' : ''}\n` +
    `Time: ${new Date().toLocaleString()}`,

  workflowUpdate: (workflowId, currentStep, totalSteps, status) =>
    `🔄 *Workflow Update*\n\n` +
    `ID: ${workflowId}\n` +
    `Progress: ${currentStep}/${totalSteps}\n` +
    `Status: ${status}\n` +
    `Time: ${new Date().toLocaleString()}`,

  coordination: (fromAgent, toAgent, message) =>
    `🔗 *Agent Coordination*\n\n` +
    `From: ${fromAgent} → ${toAgent}\n` +
    `Message: ${message}\n` +
    `Time: ${new Date().toLocaleString()}`,

  error: (agentType, error) =>
    `❌ *Agent Error*\n\n` +
    `Agent: ${agentType.toUpperCase()}\n` +
    `Error: ${error}\n` +
    `Time: ${new Date().toLocaleString()}`
};

class WhatsAppBusinessAPI {
  constructor(config) {
    this.config = config;
    this.axiosInstance = axios.create({
      baseURL: config.baseURL,
      headers: {
        'Authorization': `Bearer ${config.accessToken}`,
        'Content-Type': 'application/json',
      },
    });
  }

  async sendMessage(to, message, type = 'text') {
    try {
      const payload = {
        messaging_product: 'whatsapp',
        recipient_type: 'individual',
        to: to,
        type: type,
      };

      if (type === 'text') {
        payload.text = { body: message };
      } else if (type === 'template') {
        payload.template = message;
      }

      const response = await this.axiosInstance.post(
        `/${this.config.phoneNumberId}/messages`,
        payload
      );

      return response.data;
    } catch (error) {
      console.error('WhatsApp send error:', error.response?.data || error.message);
      throw error;
    }
  }

  async sendInteractiveMessage(to, header, body, footer, buttons) {
    try {
      const payload = {
        messaging_product: 'whatsapp',
        recipient_type: 'individual',
        to: to,
        type: 'interactive',
        interactive: {
          type: 'button',
          header: { type: 'text', text: header },
          body: { text: body },
          footer: { text: footer },
          action: {
            buttons: buttons.map((btn, idx) => ({
              type: 'reply',
              reply: { id: `btn_${idx}`, title: btn }
            }))
          }
        }
      };

      const response = await this.axiosInstance.post(
        `/${this.config.phoneNumberId}/messages`,
        payload
      );

      return response.data;
    } catch (error) {
      console.error('WhatsApp interactive message error:', error.response?.data || error.message);
      throw error;
    }
  }

  async markAsRead(messageId) {
    try {
      const payload = {
        messaging_product: 'whatsapp',
        status: 'read',
        message_id: messageId,
      };

      const response = await this.axiosInstance.post(
        `/${this.config.phoneNumberId}/messages`,
        payload
      );

      return response.data;
    } catch (error) {
      console.error('WhatsApp mark as read error:', error);
      throw error;
    }
  }

  async getMediaUrl(mediaId) {
    try {
      const response = await this.axiosInstance.get(`/${mediaId}`);
      return response.data.url;
    } catch (error) {
      console.error('WhatsApp media URL error:', error);
      throw error;
    }
  }
}

// Initialize WhatsApp API client
const whatsappAPI = new WhatsAppBusinessAPI(WHATSAPP_CONFIG);

// Store active conversations and agent states
const activeConversations = new Map();
const agentStates = new Map();

const server = new Server(
  { name: 'whatsapp-business-mcp', version: '2.0.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'whatsapp_send_message',
        description: 'Send WhatsApp message for agent coordination (2025 Business API)',
        inputSchema: {
          type: 'object',
          properties: {
            to: { 
              type: 'string', 
              description: 'Recipient phone number (with country code)' 
            },
            message: { 
              type: 'string', 
              description: 'Message to send' 
            },
            messageType: {
              type: 'string',
              enum: ['text', 'template'],
              default: 'text',
              description: 'Type of message'
            }
          },
          required: ['to', 'message']
        }
      },
      {
        name: 'whatsapp_agent_notification',
        description: 'Send formatted agent status notification via WhatsApp',
        inputSchema: {
          type: 'object',
          properties: {
            to: { type: 'string', description: 'Recipient phone number' },
            notificationType: {
              type: 'string',
              enum: ['agentStarted', 'agentCompleted', 'workflowUpdate', 'coordination', 'error'],
              description: 'Type of agent notification'
            },
            agentType: { type: 'string', description: 'Type of agent' },
            data: { 
              type: 'object', 
              description: 'Notification data (varies by type)' 
            }
          },
          required: ['to', 'notificationType', 'agentType']
        }
      },
      {
        name: 'whatsapp_interactive_menu',
        description: 'Send interactive menu for agent control',
        inputSchema: {
          type: 'object',
          properties: {
            to: { type: 'string', description: 'Recipient phone number' },
            title: { type: 'string', description: 'Menu title' },
            subtitle: { type: 'string', description: 'Menu subtitle' },
            options: { 
              type: 'array',
              items: { type: 'string' },
              description: 'Menu options' 
            }
          },
          required: ['to', 'title', 'subtitle', 'options']
        }
      },
      {
        name: 'whatsapp_workflow_status',
        description: 'Send comprehensive workflow status update',
        inputSchema: {
          type: 'object',
          properties: {
            to: { type: 'string', description: 'Recipient phone number' },
            workflowId: { type: 'string', description: 'Workflow identifier' },
            agents: { 
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  name: { type: 'string' },
                  status: { type: 'string' },
                  result: { type: 'string' }
                }
              },
              description: 'Agent status list'
            },
            overallStatus: {
              type: 'string',
              enum: ['running', 'completed', 'failed', 'paused'],
              description: 'Overall workflow status'
            }
          },
          required: ['to', 'workflowId', 'agents', 'overallStatus']
        }
      },
      {
        name: 'whatsapp_setup_webhook',
        description: 'Set up webhook server for receiving WhatsApp messages',
        inputSchema: {
          type: 'object',
          properties: {
            port: { 
              type: 'number', 
              default: 3001,
              description: 'Webhook server port' 
            },
            ngrokUrl: { 
              type: 'string', 
              description: 'ngrok URL for webhook (optional)' 
            }
          }
        }
      },
      {
        name: 'whatsapp_command_handler',
        description: 'Handle incoming WhatsApp commands for agent control',
        inputSchema: {
          type: 'object',
          properties: {
            command: { type: 'string', description: 'Command received via WhatsApp' },
            from: { type: 'string', description: 'Sender phone number' },
            messageId: { type: 'string', description: 'WhatsApp message ID' }
          },
          required: ['command', 'from']
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'whatsapp_send_message': {
        const { to, message, messageType = 'text' } = args;
        
        const result = await whatsappAPI.sendMessage(to, message, messageType);
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              messageId: result.messages?.[0]?.id,
              status: result.messages?.[0]?.message_status,
              timestamp: Date.now()
            })
          }]
        };
      }

      case 'whatsapp_agent_notification': {
        const { to, notificationType, agentType, data = {} } = args;
        
        let message;
        switch (notificationType) {
          case 'agentStarted':
            message = MESSAGE_TEMPLATES.agentStarted(agentType, data.taskDescription || 'Processing task');
            break;
          case 'agentCompleted':
            message = MESSAGE_TEMPLATES.agentCompleted(agentType, data.result || 'Task completed', data.duration || 0);
            break;
          case 'workflowUpdate':
            message = MESSAGE_TEMPLATES.workflowUpdate(data.workflowId, data.currentStep || 1, data.totalSteps || 1, data.status || 'running');
            break;
          case 'coordination':
            message = MESSAGE_TEMPLATES.coordination(agentType, data.toAgent || 'system', data.message || 'Coordination message');
            break;
          case 'error':
            message = MESSAGE_TEMPLATES.error(agentType, data.error || 'Unknown error');
            break;
          default:
            throw new Error(`Unknown notification type: ${notificationType}`);
        }
        
        const result = await whatsappAPI.sendMessage(to, message);
        
        // Store agent state for tracking
        agentStates.set(`${to}-${agentType}`, {
          type: notificationType,
          timestamp: Date.now(),
          data
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              messageId: result.messages?.[0]?.id,
              notificationType,
              agentType
            })
          }]
        };
      }

      case 'whatsapp_interactive_menu': {
        const { to, title, subtitle, options } = args;
        
        const result = await whatsappAPI.sendInteractiveMessage(
          to, 
          title,
          subtitle,
          'Select an option:',
          options.slice(0, 3) // WhatsApp limits to 3 buttons
        );
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              messageId: result.messages?.[0]?.id,
              interactiveType: 'button_menu'
            })
          }]
        };
      }

      case 'whatsapp_workflow_status': {
        const { to, workflowId, agents, overallStatus } = args;
        
        const statusEmojis = {
          running: '⚡',
          completed: '✅',
          failed: '❌',
          paused: '⏸️'
        };
        
        let statusMessage = `${statusEmojis[overallStatus]} *Workflow Status*\n\n`;
        statusMessage += `ID: ${workflowId}\n`;
        statusMessage += `Status: ${overallStatus.toUpperCase()}\n\n`;
        statusMessage += `*Agents:*\n`;
        
        agents.forEach((agent, idx) => {
          const agentEmoji = agent.status === 'completed' ? '✅' : 
                            agent.status === 'failed' ? '❌' : 
                            agent.status === 'running' ? '⚡' : '⏳';
          statusMessage += `${idx + 1}. ${agentEmoji} ${agent.name}: ${agent.status}\n`;
          if (agent.result && agent.result.length > 0) {
            statusMessage += `   Result: ${agent.result.substring(0, 50)}...\n`;
          }
        });
        
        statusMessage += `\nUpdated: ${new Date().toLocaleString()}`;
        
        const result = await whatsappAPI.sendMessage(to, statusMessage);
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              messageId: result.messages?.[0]?.id,
              workflowId,
              overallStatus
            })
          }]
        };
      }

      case 'whatsapp_setup_webhook': {
        const { port = 3001, ngrokUrl } = args;
        
        // Set up Express webhook server
        const webhookApp = express();
        webhookApp.use(express.json());
        
        // Webhook verification
        webhookApp.get('/webhook', (req, res) => {
          const mode = req.query['hub.mode'];
          const token = req.query['hub.verify_token'];
          const challenge = req.query['hub.challenge'];
          
          if (mode === 'subscribe' && token === WHATSAPP_CONFIG.webhookVerifyToken) {
            console.log('Webhook verified');
            res.status(200).send(challenge);
          } else {
            res.status(403).send('Verification failed');
          }
        });
        
        // Webhook message receiver
        webhookApp.post('/webhook', async (req, res) => {
          const { entry } = req.body;
          
          if (entry && entry[0]?.changes) {
            for (const change of entry[0].changes) {
              if (change.field === 'messages') {
                const { messages, contacts } = change.value;
                
                if (messages) {
                  for (const message of messages) {
                    await processIncomingMessage(message, contacts[0]);
                  }
                }
              }
            }
          }
          
          res.status(200).send('OK');
        });
        
        const server = webhookApp.listen(port, () => {
          console.log(`WhatsApp webhook server running on port ${port}`);
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              port,
              webhookUrl: ngrokUrl ? `${ngrokUrl}/webhook` : `http://localhost:${port}/webhook`,
              message: 'Webhook server started'
            })
          }]
        };
      }

      case 'whatsapp_command_handler': {
        const { command, from, messageId } = args;
        
        const response = await handleCommand(command, from);
        
        if (messageId) {
          await whatsappAPI.markAsRead(messageId);
        }
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({
              success: true,
              command,
              response: response.message,
              actionTaken: response.action
            })
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

// Helper function to process incoming WhatsApp messages
async function processIncomingMessage(message, contact) {
  const from = message.from;
  const messageType = message.type;
  
  console.log(`Received ${messageType} message from ${contact.profile.name} (${from})`);
  
  let messageText = '';
  
  switch (messageType) {
    case 'text':
      messageText = message.text.body;
      break;
    case 'interactive':
      messageText = message.interactive.button_reply?.title || 
                   message.interactive.list_reply?.title || '';
      break;
    default:
      messageText = `[${messageType} message]`;
  }
  
  // Store conversation context
  activeConversations.set(from, {
    lastMessage: messageText,
    timestamp: Date.now(),
    contact: contact.profile
  });
  
  // Process commands
  if (messageText.startsWith('/')) {
    await handleCommand(messageText, from);
  }
}

// Command handler for WhatsApp agent control
async function handleCommand(command, from) {
  const cmd = command.toLowerCase().trim();
  
  try {
    switch (true) {
      case cmd.startsWith('/status'):
        const statusSummary = `🤖 *MCPhub Agent Status*\n\n` +
          `Active Agents: ${agentStates.size}\n` +
          `Last Update: ${new Date().toLocaleString()}\n\n` +
          `Commands:\n` +
          `/agents - List all agents\n` +
          `/start [agent] - Start agent\n` +
          `/stop [agent] - Stop agent\n` +
          `/workflow - Show workflow status`;
        
        await whatsappAPI.sendMessage(from, statusSummary);
        return { action: 'status_sent', message: 'Status summary sent' };

      case cmd.startsWith('/agents'):
        const agentList = `🎯 *Available Agents*\n\n` +
          `🔍 Research Agent - Market analysis\n` +
          `📊 Business Agent - Data analytics\n` +
          `🎨 Creative Agent - Content generation\n` +
          `⚡ Dev Agent - Code deployment\n` +
          `🔧 n8n Agent - Workflow automation\n\n` +
          `Use /start [agent-name] to activate`;
        
        await whatsappAPI.sendMessage(from, agentList);
        return { action: 'agent_list_sent', message: 'Agent list sent' };

      case cmd.startsWith('/start'):
        const agentToStart = cmd.split(' ')[1] || 'research';
        await whatsappAPI.sendMessage(from, `🚀 Starting ${agentToStart} agent...`);
        return { action: 'agent_started', message: `Started ${agentToStart} agent` };

      case cmd.startsWith('/workflow'):
        await whatsappAPI.sendInteractiveMessage(
          from,
          '🔄 Workflow Control',
          'Choose a workflow action:',
          'Select an option',
          ['Start New Workflow', 'Check Status', 'Pause Current']
        );
        return { action: 'workflow_menu_sent', message: 'Workflow menu sent' };

      default:
        const helpMessage = `❓ *Unknown Command*\n\n` +
          `Available commands:\n` +
          `/status - Agent status\n` +
          `/agents - List agents\n` +
          `/start [agent] - Start agent\n` +
          `/workflow - Workflow control\n\n` +
          `Send any message to start a conversation.`;
        
        await whatsappAPI.sendMessage(from, helpMessage);
        return { action: 'help_sent', message: 'Help message sent' };
    }
  } catch (error) {
    await whatsappAPI.sendMessage(from, `❌ Error: ${error.message}`);
    return { action: 'error', message: error.message };
  }
}

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('WhatsApp Business MCP Server running (2025 Cloud API)');
}

main().catch(console.error);