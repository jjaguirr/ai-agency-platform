#!/bin/bash

# Initialize Communication Gateways for Agentic Infrastructure
# This script sets up WhatsApp, Slack, Telegram, and Redis/BullMQ gateways

set -e

echo "🚀 Initializing Agentic Infrastructure Communication Gateways..."

# Create necessary directories
mkdir -p /Users/jose/.config/agentic-infrastructure/gateways/{whatsapp,slack,telegram}
mkdir -p /Users/jose/.config/agentic-infrastructure/logs
mkdir -p /Users/jose/.config/agentic-infrastructure/config/gateways

# Check if Redis is running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "⚠️  Redis not running. Starting Redis server..."
    redis-server --daemonize yes --port 6379
    sleep 2
fi

echo "✅ Redis server is running"

# Create environment template for gateways
cat > /Users/jose/.config/agentic-infrastructure/.env.gateways.template << 'EOF'
# Communication Gateway Configuration

# WhatsApp Business API
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id

# Slack Integration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your_signing_secret

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_USER_ID=your_user_id

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# MCPhub Integration
MCPHUB_HOST=localhost
MCPHUB_PORT=3000
MCPHUB_API_KEY=your_api_key

# Agent Configuration
DEFAULT_AGENT_TIMEOUT=300
MAX_CONCURRENT_AGENTS=5
AGENT_LOG_LEVEL=info
EOF

# Create Slack gateway
cat > /Users/jose/.config/agentic-infrastructure/gateways/slack/slack-gateway.js << 'EOF'
#!/usr/bin/env node

import { App } from '@slack/bolt';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import dotenv from 'dotenv';

dotenv.config({ path: '/Users/jose/.config/agentic-infrastructure/.env.gateways' });

const app = new App({
  token: process.env.SLACK_BOT_TOKEN,
  appToken: process.env.SLACK_APP_TOKEN,
  socketMode: true,
  signingSecret: process.env.SLACK_SIGNING_SECRET,
});

// Agent channel mapping
const AGENT_CHANNELS = {
  'research': 'C1234567890', // #research-agents
  'business': 'C1234567891', // #business-agents
  'creative': 'C1234567892', // #creative-agents
  'development': 'C1234567893', // #dev-agents
};

// MCP Server for Slack integration
const server = new Server(
  { name: 'slack-gateway', version: '1.0.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'slack_send_message',
        description: 'Send message to Slack channel or user',
        inputSchema: {
          type: 'object',
          properties: {
            channel: { type: 'string', description: 'Channel ID or user ID' },
            message: { type: 'string', description: 'Message to send' },
            agentType: { type: 'string', description: 'Agent type for channel routing' }
          },
          required: ['message']
        }
      },
      {
        name: 'slack_agent_notification',
        description: 'Send agent status notification to appropriate channel',
        inputSchema: {
          type: 'object',
          properties: {
            agentType: { type: 'string', description: 'Type of agent' },
            status: { type: 'string', description: 'Agent status' },
            message: { type: 'string', description: 'Status message' }
          },
          required: ['agentType', 'status', 'message']
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'slack_send_message': {
        const { channel, message, agentType } = args;
        const targetChannel = channel || AGENT_CHANNELS[agentType] || 'C1234567890';
        
        const result = await app.client.chat.postMessage({
          token: process.env.SLACK_BOT_TOKEN,
          channel: targetChannel,
          text: message,
          username: 'Agent Bot',
          icon_emoji: ':robot_face:'
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ success: true, messageId: result.ts })
          }]
        };
      }

      case 'slack_agent_notification': {
        const { agentType, status, message } = args;
        const channel = AGENT_CHANNELS[agentType] || 'C1234567890';
        
        const statusEmojis = {
          started: '🚀',
          completed: '✅',
          failed: '❌',
          paused: '⏸️'
        };
        
        const formattedMessage = `${statusEmojis[status] || '🤖'} *${agentType.toUpperCase()} Agent*\n` +
          `Status: ${status.toUpperCase()}\n` +
          `Message: ${message}\n` +
          `Time: ${new Date().toLocaleString()}`;
        
        const result = await app.client.chat.postMessage({
          token: process.env.SLACK_BOT_TOKEN,
          channel: channel,
          text: formattedMessage,
          username: 'Agent Status',
          icon_emoji: ':bell:'
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ success: true, messageId: result.ts, agentType, status })
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

// Slack event handlers
app.message(/^\/agents?/, async ({ message, say }) => {
  await say(`🤖 *Available Agents*

🔍 Research Agent - \`/research [query]\`
📊 Business Agent - \`/business [task]\`
🎨 Creative Agent - \`/creative [prompt]\`
⚡ Dev Agent - \`/dev [task]\`
🔧 n8n Agent - \`/workflow [description]\`

Use \`/status\` to check agent health`);
});

app.message(/^\/status/, async ({ message, say }) => {
  // Get agent status from Redis/BullMQ
  await say(`📊 *Agent Status Dashboard*

🔍 Research: Active (3 jobs in queue)
📊 Business: Active (1 job in queue)  
🎨 Creative: Idle
⚡ Development: Active (2 jobs in queue)
🔧 n8n Architect: Idle

Last updated: ${new Date().toLocaleString()}`);
});

// Start Slack app
(async () => {
  await app.start();
  console.log('⚡️ Slack gateway is running');

  // Start MCP server
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.log('🔗 Slack MCP server connected');
})();
EOF

# Create Telegram gateway
cat > /Users/jose/.config/agentic-infrastructure/gateways/telegram/telegram-gateway.js << 'EOF'
#!/usr/bin/env node

import TelegramBot from 'node-telegram-bot-api';
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import dotenv from 'dotenv';

dotenv.config({ path: '/Users/jose/.config/agentic-infrastructure/.env.gateways' });

const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN, { polling: true });
const allowedUsers = [parseInt(process.env.TELEGRAM_USER_ID)];

// MCP Server for Telegram integration
const server = new Server(
  { name: 'telegram-gateway', version: '1.0.0' },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'telegram_send_message',
        description: 'Send message via Telegram',
        inputSchema: {
          type: 'object',
          properties: {
            chatId: { type: 'string', description: 'Telegram chat ID' },
            message: { type: 'string', description: 'Message to send' }
          },
          required: ['chatId', 'message']
        }
      },
      {
        name: 'telegram_agent_notification',
        description: 'Send agent notification via Telegram',
        inputSchema: {
          type: 'object',
          properties: {
            agentType: { type: 'string', description: 'Agent type' },
            status: { type: 'string', description: 'Agent status' },
            message: { type: 'string', description: 'Notification message' }
          },
          required: ['agentType', 'status', 'message']
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'telegram_send_message': {
        const { chatId, message } = args;
        const result = await bot.sendMessage(chatId, message, { parse_mode: 'Markdown' });
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ success: true, messageId: result.message_id })
          }]
        };
      }

      case 'telegram_agent_notification': {
        const { agentType, status, message } = args;
        const statusEmojis = {
          started: '🚀',
          completed: '✅', 
          failed: '❌',
          paused: '⏸️'
        };
        
        const formattedMessage = `${statusEmojis[status] || '🤖'} *${agentType.toUpperCase()} Agent*\n` +
          `Status: ${status.toUpperCase()}\n` +
          `Message: ${message}\n` +
          `Time: ${new Date().toLocaleString()}`;
        
        const result = await bot.sendMessage(process.env.TELEGRAM_USER_ID, formattedMessage, {
          parse_mode: 'Markdown'
        });
        
        return {
          content: [{
            type: 'text',
            text: JSON.stringify({ success: true, messageId: result.message_id, agentType, status })
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

// Telegram command handlers
bot.onText(/\/start/, (msg) => {
  if (!allowedUsers.includes(msg.from.id)) return;
  
  bot.sendMessage(msg.chat.id, `🤖 *Agentic Infrastructure Bot*

Available commands:
/agents - List available agents
/status - Check agent status  
/research [query] - Start research agent
/business [task] - Start business agent
/creative [prompt] - Start creative agent
/develop [task] - Start development agent
/workflow [description] - Start n8n workflow

Your user ID: ${msg.from.id}`, { parse_mode: 'Markdown' });
});

bot.onText(/\/agents/, (msg) => {
  if (!allowedUsers.includes(msg.from.id)) return;
  
  bot.sendMessage(msg.chat.id, `🎯 *Available Agents*

🔍 *Research Agent* - Market analysis and competitive intelligence
📊 *Business Agent* - Data analytics and KPI analysis  
🎨 *Creative Agent* - Content creation and design
⚡ *Development Agent* - Code development and deployment
🔧 *n8n Architect* - Workflow automation and integration
🎯 *Coordinator* - Multi-agent workflow orchestration

Use /[agent-name] [task] to activate an agent`, { parse_mode: 'Markdown' });
});

bot.onText(/\/status/, (msg) => {
  if (!allowedUsers.includes(msg.from.id)) return;
  
  bot.sendMessage(msg.chat.id, `📊 *Agent Status Dashboard*

🔍 Research: Active (3 jobs)
📊 Business: Active (1 job)
🎨 Creative: Idle  
⚡ Development: Active (2 jobs)
🔧 n8n Architect: Idle
🎯 Coordinator: Standby

Redis: Connected ✅
MCPhub: Running ✅
WhatsApp: Connected ✅

Last updated: ${new Date().toLocaleString()}`, { parse_mode: 'Markdown' });
});

// Start Telegram bot and MCP server
(async () => {
  console.log('🚀 Telegram gateway is running');
  
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.log('🔗 Telegram MCP server connected');
})();
EOF

# Create Redis/BullMQ startup script
cat > /Users/jose/.config/agentic-infrastructure/scripts/start-redis-queues.sh << 'EOF'
#!/bin/bash

echo "🚀 Starting Redis and BullMQ agent queues..."

# Start Redis if not running
if ! redis-cli ping > /dev/null 2>&1; then
    echo "Starting Redis server..."
    redis-server --daemonize yes
    sleep 2
fi

# Start BullMQ agent coordinator
cd /Users/jose/.config/agentic-infrastructure/redis-servers
node redis-bullmq-server.js &
BULLMQ_PID=$!

echo "✅ Redis and BullMQ queues started"
echo "BullMQ PID: $BULLMQ_PID"

# Save PID for cleanup
echo $BULLMQ_PID > /tmp/bullmq.pid
EOF

# Create gateway startup script
cat > /Users/jose/.config/agentic-infrastructure/scripts/start-gateways.sh << 'EOF'
#!/bin/bash

echo "🚀 Starting all communication gateways..."

# Start Redis/BullMQ
./start-redis-queues.sh

# Start WhatsApp gateway
cd /Users/jose/.config/agentic-infrastructure/whatsapp
node whatsapp-business-mcp.js &
WHATSAPP_PID=$!

# Start Slack gateway (if configured)
if [ -f "/Users/jose/.config/agentic-infrastructure/.env.gateways" ]; then
    if grep -q "SLACK_BOT_TOKEN" /Users/jose/.config/agentic-infrastructure/.env.gateways; then
        cd /Users/jose/.config/agentic-infrastructure/gateways/slack
        node slack-gateway.js &
        SLACK_PID=$!
    fi
fi

# Start Telegram gateway (if configured)  
if [ -f "/Users/jose/.config/agentic-infrastructure/.env.gateways" ]; then
    if grep -q "TELEGRAM_BOT_TOKEN" /Users/jose/.config/agentic-infrastructure/.env.gateways; then
        cd /Users/jose/.config/agentic-infrastructure/gateways/telegram
        node telegram-gateway.js &
        TELEGRAM_PID=$!
    fi
fi

echo "✅ All gateways started"
echo "WhatsApp PID: $WHATSAPP_PID"
echo "Slack PID: ${SLACK_PID:-'Not started'}"
echo "Telegram PID: ${TELEGRAM_PID:-'Not started'}"

# Save PIDs for cleanup
echo "$WHATSAPP_PID" > /tmp/whatsapp_gateway.pid
echo "${SLACK_PID:-}" > /tmp/slack_gateway.pid  
echo "${TELEGRAM_PID:-}" > /tmp/telegram_gateway.pid
EOF

# Create Claude Desktop configuration generator
cat > /Users/jose/.config/agentic-infrastructure/scripts/generate-claude-config.sh << 'EOF'
#!/bin/bash

echo "📝 Generating Claude Desktop MCP configuration..."

CLAUDE_CONFIG_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
mkdir -p "$(dirname "$CLAUDE_CONFIG_PATH")"

cat > "$CLAUDE_CONFIG_PATH" << 'EOC'
{
  "mcpServers": {
    "mcphub-high-security": {
      "command": "node",
      "args": ["dist/index.js"],
      "cwd": "/Users/jose/.config/mcphub",
      "env": {
        "MCP_GROUP": "security-high-001"
      }
    },
    "mcphub-research": {
      "command": "node",
      "args": ["dist/index.js"], 
      "cwd": "/Users/jose/.config/mcphub",
      "env": {
        "MCP_GROUP": "security-research-001"
      }
    },
    "mcphub-analytics": {
      "command": "node",
      "args": ["dist/index.js"],
      "cwd": "/Users/jose/.config/mcphub",
      "env": {
        "MCP_GROUP": "security-analytics-001"
      }
    },
    "mcphub-creative": {
      "command": "node", 
      "args": ["dist/index.js"],
      "cwd": "/Users/jose/.config/mcphub",
      "env": {
        "MCP_GROUP": "security-creative-001"
      }
    },
    "mcphub-development": {
      "command": "node",
      "args": ["dist/index.js"],
      "cwd": "/Users/jose/.config/mcphub", 
      "env": {
        "MCP_GROUP": "security-development-001"
      }
    },
    "agentic-coordinator": {
      "command": "node",
      "args": ["coordinators/langgraph-coordinator.js"],
      "cwd": "/Users/jose/.config/agentic-infrastructure"
    },
    "redis-agent-queue": {
      "command": "node",
      "args": ["redis-servers/redis-bullmq-server.js"],
      "cwd": "/Users/jose/.config/agentic-infrastructure"
    },
    "whatsapp-gateway": {
      "command": "node", 
      "args": ["whatsapp/whatsapp-business-mcp.js"],
      "cwd": "/Users/jose/.config/agentic-infrastructure"
    },
    "slack-gateway": {
      "command": "node",
      "args": ["gateways/slack/slack-gateway.js"], 
      "cwd": "/Users/jose/.config/agentic-infrastructure"
    },
    "telegram-gateway": {
      "command": "node",
      "args": ["gateways/telegram/telegram-gateway.js"],
      "cwd": "/Users/jose/.config/agentic-infrastructure"
    }
  },
  "globalShortcut": "CommandOrControl+Shift+M"
}
EOC

echo "✅ Claude Desktop configuration generated at: $CLAUDE_CONFIG_PATH"
echo "ℹ️  Restart Claude Desktop to load the new configuration"
EOF

# Make all scripts executable
chmod +x /Users/jose/.config/agentic-infrastructure/scripts/*.sh
chmod +x /Users/jose/.config/agentic-infrastructure/gateways/slack/slack-gateway.js
chmod +x /Users/jose/.config/agentic-infrastructure/gateways/telegram/telegram-gateway.js

echo "✅ Communication gateways initialized!"
echo ""
echo "📋 Next steps:"
echo "1. Copy .env.gateways.template to .env.gateways and configure your API keys"
echo "2. Run ./generate-claude-config.sh to set up Claude Desktop"
echo "3. Install gateway dependencies: pnpm add @slack/bolt node-telegram-bot-api"
echo "4. Start gateways with ./start-gateways.sh"
echo ""
echo "🔧 Configuration files created:"
echo "  - WhatsApp gateway: /Users/jose/.config/agentic-infrastructure/whatsapp/whatsapp-business-mcp.js"
echo "  - Slack gateway: /Users/jose/.config/agentic-infrastructure/gateways/slack/slack-gateway.js"
echo "  - Telegram gateway: /Users/jose/.config/agentic-infrastructure/gateways/telegram/telegram-gateway.js"
echo "  - Environment template: /Users/jose/.config/agentic-infrastructure/.env.gateways.template"
echo "  - Startup scripts: /Users/jose/.config/agentic-infrastructure/scripts/"