# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI Agency Platform that serves as both a personal AI operating system and a commercial AI agency. The platform uses self-configuring agents and sophisticated multi-agent orchestration through a security-first architecture with MCPhub as the central hub.

## Development Commands

### Infrastructure Setup
```bash
# Initialize communication gateways
./scripts/init-communication-gateways.sh

# Start Redis and BullMQ queues
/Users/jose/.config/agentic-infrastructure/scripts/start-redis-queues.sh

# Start all communication gateways
/Users/jose/.config/agentic-infrastructure/scripts/start-gateways.sh

# Generate Claude Desktop configuration
/Users/jose/.config/agentic-infrastructure/scripts/generate-claude-config.sh
```

### MCPhub & Services
Since this project relies on MCPhub (enterprise MCP server hub), ensure the following are running:
- MCPhub server on port 3000
- PostgreSQL database for user/group management
- Redis for sessions and queues
- Qdrant vector database for agent memory
- n8n on port 5678 for workflow automation

### Testing & Development
The project doesn't have traditional package.json build scripts yet. Development workflow:
1. Configure environment variables using `.env.gateways.template`
2. Set up MCPhub with the required security groups
3. Test individual MCP servers and agents
4. Use the LangGraph coordinator for multi-agent workflows

## Architecture Overview

### Security-First Design
- **MCPhub Hub**: Central MCP server with JWT+bcrypt authentication and RBAC
- **Group-Based Isolation**: 
  - Personal Tier (Tier 0): Owner-only access for personal data
  - Development Tier (Tier 1): Team development tools
  - Business Tier (Tier 2): Research and analytics tools  
  - Customer Tier (Tier 3): Isolated customer bot environments

### Multi-Agent Coordination
- **LangGraph State Management**: `src/coordinators/langgraph-coordinator.js` handles complex multi-agent workflows
- **Agent Types**:
  - Research Agent: Market analysis via MCPhub research tools
  - Business Agent: Data analytics via PostgreSQL/Redis
  - Creative Agent: Content generation via OpenAI/AI tools
  - Development Agent: Code deployment via Git/filesystem tools
  - n8n Workflow Architect: Visual workflow automation

### Communication Integration
- **WhatsApp Business API**: `src/integrations/whatsapp-business-mcp.js` for business messaging
- **Multi-Channel Support**: Slack, Telegram gateways for team coordination
- **Agent Notifications**: Real-time status updates across all channels

## Key Implementation Patterns

### Agent State Management
Agents use LangGraph with persistent state stored in Qdrant vector database. Each agent has security-tier access controls through MCPhub groups.

### MCP Server Architecture
All tools and integrations go through MCPhub using Model Context Protocol (MCP). This provides:
- Centralized authentication and authorization
- Smart semantic routing for tool discovery
- Complete audit trails for security compliance
- Group-based tool access isolation

### Workflow Orchestration
- **n8n Integration**: Visual workflow design and execution
- **LangGraph Coordination**: Multi-agent state management and delegation
- **Redis/BullMQ**: Job queuing and background processing

## File Structure Importance

- `docs/architecture/Technical Design Document.md`: Complete system architecture and specifications
- `src/coordinators/langgraph-coordinator.js`: Main multi-agent coordination logic
- `src/integrations/`: Communication channel integrations (WhatsApp, etc.)
- `scripts/init-communication-gateways.sh`: Infrastructure initialization
- `config/`: MCPhub and service configurations

## Development Guidelines

### Security Requirements
- All agent interactions must go through MCPhub security groups
- Customer data requires complete isolation (Tier 3)
- Personal data requires owner-only access (Tier 0)
- Development tools restricted to team members (Tier 1)

### Agent Development
- Use the AgentCoordinator class in `langgraph-coordinator.js` as the base pattern
- Implement security tier validation for all agent operations
- Store agent memory and context in Qdrant vector database
- Use MCPhub semantic routing for tool discovery

### Integration Patterns
- All external APIs integrate as MCP servers through MCPhub
- Communication channels use the notification template system
- Workflow coordination happens through LangGraph state management

## LAUNCH Bot System
The platform includes self-configuring customer bots that set up themselves through conversation in <60 seconds. These bots:
- Start in "blank" state and learn business purpose through dialogue
- Configure integrations automatically based on customer needs
- Escalate to human support when appropriate
- Operate in complete isolation per customer (Tier 3 security)

## Production Deployment
The system is designed for Docker deployment with:
- MCPhub as the central security and routing hub
- Multi-service Docker Compose setup
- Nginx reverse proxy with security headers
- Comprehensive monitoring and logging
- Automated backup and disaster recovery

When working with this codebase, prioritize security isolation, use MCPhub for all tool access, and follow the multi-agent coordination patterns established in the LangGraph coordinator.