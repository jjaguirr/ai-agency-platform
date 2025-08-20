-- MCPhub Database Schema for AI Agency Platform Dual-Agent Architecture
-- Enhanced with Langfuse integration for Infrastructure Agents

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Users table for MCPhub authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Security Groups for dual-agent architecture
CREATE TABLE IF NOT EXISTS groups (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    tier INTEGER NOT NULL,
    isolation VARCHAR(50) NOT NULL,
    ai_model VARCHAR(100),
    tools JSONB DEFAULT '[]',
    langfuse_project_id VARCHAR(255), -- Link to Langfuse project
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User group memberships
CREATE TABLE IF NOT EXISTS user_groups (
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    group_id UUID REFERENCES groups(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, group_id)
);

-- Infrastructure Agents (managed by MCPhub + Langfuse)
CREATE TABLE IF NOT EXISTS infrastructure_agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    agent_type VARCHAR(100) NOT NULL,
    group_id UUID REFERENCES groups(id),
    langfuse_prompt_name VARCHAR(255), -- Link to Langfuse prompt
    langfuse_prompt_version VARCHAR(50),
    ai_model_primary VARCHAR(100),
    ai_model_fallback JSONB DEFAULT '[]',
    configuration JSONB DEFAULT '{}',
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Customers with complete isolation
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id VARCHAR(255) UNIQUE NOT NULL, -- External customer identifier
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    industry VARCHAR(100),
    ai_model_preference VARCHAR(100) DEFAULT 'auto-select',
    group_id UUID REFERENCES groups(id), -- customer-{customerId} group
    launch_bot_state VARCHAR(50) DEFAULT 'blank',
    configuration_progress INTEGER DEFAULT 0,
    tools_configured JSONB DEFAULT '[]',
    langfuse_user_id VARCHAR(255), -- Link to Langfuse user tracking
    onboarding_completed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Cross-system messages for Claude Code <-> Infrastructure communication
CREATE TABLE IF NOT EXISTS cross_system_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_system VARCHAR(50) NOT NULL,
    target_system VARCHAR(50) NOT NULL,
    message_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT false,
    response JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- MCP Servers registered with MCPhub
CREATE TABLE IF NOT EXISTS mcp_servers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    type VARCHAR(100) NOT NULL, -- 'infrastructure-tool', 'claude-code-tool'
    endpoint VARCHAR(500),
    command VARCHAR(500),
    args JSONB DEFAULT '[]',
    env JSONB DEFAULT '{}',
    groups JSONB DEFAULT '[]', -- Which groups can access this server
    langfuse_enabled BOOLEAN DEFAULT false, -- Whether to track via Langfuse
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Infrastructure Agent execution logs with Langfuse integration
CREATE TABLE IF NOT EXISTS agent_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES infrastructure_agents(id),
    customer_id VARCHAR(255),
    input_text TEXT,
    output_text TEXT,
    ai_model_used VARCHAR(100),
    langfuse_trace_id VARCHAR(255), -- Link to Langfuse trace
    langfuse_generation_id VARCHAR(255), -- Link to Langfuse generation
    execution_time_ms INTEGER,
    token_usage JSONB, -- {prompt_tokens: X, completion_tokens: Y, total_tokens: Z}
    cost_usd DECIMAL(10,6),
    success BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Customer tool access whitelist
CREATE TABLE IF NOT EXISTS customer_tool_access (
    customer_id VARCHAR(255) REFERENCES customers(customer_id),
    tool_name VARCHAR(255) NOT NULL,
    enabled BOOLEAN DEFAULT true,
    configuration JSONB DEFAULT '{}',
    added_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (customer_id, tool_name)
);

-- Insert default MCPhub groups for dual-agent architecture
INSERT INTO groups (name, tier, isolation, ai_model, tools, langfuse_project_id) VALUES
    ('personal-infrastructure', 0, 'owner-only', 'claude-3.5-sonnet', 
     '["personal-automation", "calendar-sync", "email-automation"]', 
     'personal-infrastructure'),
    ('development-infrastructure', 1, 'team', 'claude-3.5-sonnet', 
     '["docker-deploy", "monitoring-setup", "infrastructure-automation"]', 
     'development-infrastructure'),
    ('business-operations', 2, 'business', 'auto-select', 
     '["brave-search", "context7", "postgres", "everart", "openai"]', 
     'business-operations'),
    ('public-gateway', 4, 'public', 'claude-3.5-sonnet', 
     '["public-conversation", "demo-capabilities"]', 
     'public-gateway')
ON CONFLICT (name) DO UPDATE SET
    langfuse_project_id = EXCLUDED.langfuse_project_id,
    updated_at = NOW();

-- Insert Infrastructure Agents with Langfuse prompt links
INSERT INTO infrastructure_agents (name, agent_type, group_id, langfuse_prompt_name, ai_model_primary, ai_model_fallback) VALUES
    ('Research Agent', 'research', 
     (SELECT id FROM groups WHERE name = 'business-operations'),
     'infrastructure-agent-research', 'openai-gpt-4o', '["claude-3.5-sonnet", "deepseek-v2"]'),
    ('Business Agent', 'business', 
     (SELECT id FROM groups WHERE name = 'business-operations'),
     'infrastructure-agent-business', 'claude-3.5-sonnet', '["openai-gpt-4o", "local-llama-3"]'),
    ('Creative Agent', 'creative', 
     (SELECT id FROM groups WHERE name = 'business-operations'),
     'infrastructure-agent-creative', 'claude-3.5-sonnet', '["openai-gpt-4o", "meta-llama-3"]'),
    ('Development Agent', 'development', 
     (SELECT id FROM groups WHERE name = 'development-infrastructure'),
     'infrastructure-agent-development', 'claude-3.5-sonnet', '["openai-gpt-4o"]'),
    ('n8n Workflow Agent', 'n8n-workflow', 
     (SELECT id FROM groups WHERE name = 'business-operations'),
     'infrastructure-agent-n8n', 'claude-3.5-sonnet', '["openai-gpt-4o"]')
ON CONFLICT DO NOTHING;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_groups_tier ON groups(tier);
CREATE INDEX IF NOT EXISTS idx_groups_name ON groups(name);

CREATE INDEX IF NOT EXISTS idx_customers_customer_id ON customers(customer_id);
CREATE INDEX IF NOT EXISTS idx_customers_group_id ON customers(group_id);
CREATE INDEX IF NOT EXISTS idx_customers_state ON customers(launch_bot_state);

CREATE INDEX IF NOT EXISTS idx_infrastructure_agents_type ON infrastructure_agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_infrastructure_agents_group ON infrastructure_agents(group_id);

CREATE INDEX IF NOT EXISTS idx_cross_system_messages_processed ON cross_system_messages(processed);
CREATE INDEX IF NOT EXISTS idx_cross_system_messages_type ON cross_system_messages(message_type);

CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_id ON agent_executions(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_executions_customer_id ON agent_executions(customer_id);
CREATE INDEX IF NOT EXISTS idx_agent_executions_created_at ON agent_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_executions_langfuse_trace ON agent_executions(langfuse_trace_id);

CREATE INDEX IF NOT EXISTS idx_mcp_servers_type ON mcp_servers(type);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers(enabled);

-- Functions for customer provisioning
CREATE OR REPLACE FUNCTION create_customer_group(customer_id_param VARCHAR(255))
RETURNS UUID AS $$
DECLARE
    group_id UUID;
BEGIN
    INSERT INTO groups (name, tier, isolation, ai_model, tools, langfuse_project_id)
    VALUES (
        'customer-' || customer_id_param,
        3,
        'complete',
        'auto-select',
        '[]',
        'customer-' || customer_id_param
    )
    RETURNING id INTO group_id;
    
    RETURN group_id;
END;
$$ LANGUAGE plpgsql;

-- Function for dynamic LAUNCH bot creation
CREATE OR REPLACE FUNCTION create_launch_bot(customer_id_param VARCHAR(255), customer_name_param VARCHAR(255))
RETURNS UUID AS $$
DECLARE
    group_id UUID;
    customer_uuid UUID;
BEGIN
    -- Create customer-specific group
    group_id := create_customer_group(customer_id_param);
    
    -- Create customer record
    INSERT INTO customers (customer_id, name, group_id, langfuse_user_id)
    VALUES (customer_id_param, customer_name_param, group_id, 'customer-' || customer_id_param)
    RETURNING id INTO customer_uuid;
    
    -- Create customer-specific LAUNCH bot
    INSERT INTO infrastructure_agents (name, agent_type, group_id, langfuse_prompt_name, ai_model_primary)
    VALUES (
        'LAUNCH Bot - ' || customer_name_param,
        'launch-bot',
        group_id,
        'infrastructure-agent-launch-bot',
        'claude-3.5-sonnet'
    );
    
    RETURN customer_uuid;
END;
$$ LANGUAGE plpgsql;

-- Trigger for Langfuse integration tracking
CREATE OR REPLACE FUNCTION log_agent_execution()
RETURNS TRIGGER AS $$
BEGIN
    -- This function can be called by MCPhub to log executions
    -- The actual integration happens in the application layer
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

\echo 'MCPhub database schema with Langfuse integration initialized successfully!';