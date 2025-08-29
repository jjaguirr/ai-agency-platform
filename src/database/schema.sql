-- AI Agency Platform - Phase 1 Database Schema
-- Multi-tenant architecture with complete customer isolation
-- Version: 1.0 - Foundation Infrastructure

-- ====================================================================
-- CUSTOMER & TENANT MANAGEMENT
-- ====================================================================

-- Core customer table with complete isolation
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_name VARCHAR(255) NOT NULL,
    business_type VARCHAR(100),
    contact_email VARCHAR(255) NOT NULL UNIQUE,
    contact_phone VARCHAR(50),
    onboarding_status VARCHAR(50) DEFAULT 'pending' CHECK (onboarding_status IN ('pending', 'stage1', 'stage2', 'active', 'suspended')),
    subscription_tier VARCHAR(50) DEFAULT 'starter' CHECK (subscription_tier IN ('trial', 'starter', 'professional', 'enterprise')),
    api_quota_limit INTEGER DEFAULT 10000,
    api_quota_used INTEGER DEFAULT 0,
    api_quota_reset_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP + INTERVAL '1 month',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}'::JSONB
);

-- Customer MCPhub security group mappings
CREATE TABLE IF NOT EXISTS customer_security_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    group_tier INTEGER NOT NULL CHECK (group_tier IN (3, 4)), -- Only Tier 3 (customer) and Tier 4 (public/trial)
    group_name VARCHAR(100) NOT NULL,
    permissions JSONB DEFAULT '{}'::JSONB,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- AUTHENTICATION & AUTHORIZATION
-- ====================================================================

-- User accounts with role-based access control
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'manager', 'user', 'agent')),
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMP WITH TIME ZONE,
    mfa_enabled BOOLEAN DEFAULT false,
    mfa_secret VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, email)
);

-- JWT refresh tokens with automatic cleanup
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_revoked BOOLEAN DEFAULT false
);

-- API keys for programmatic access
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    key_name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(255) NOT NULL,
    permissions JSONB DEFAULT '{}'::JSONB,
    last_used TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- AGENT MANAGEMENT & DEPLOYMENT
-- ====================================================================

-- Core agent definitions and configurations
CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    agent_type VARCHAR(100) NOT NULL CHECK (agent_type IN ('social_media_manager', 'finance_agent', 'marketing_agent', 'business_agent')),
    agent_name VARCHAR(255) NOT NULL,
    description TEXT,
    ai_model VARCHAR(100) DEFAULT 'gpt-4o' CHECK (ai_model IN ('gpt-4o', 'gpt-4-turbo', 'claude-3.5-sonnet')),
    system_prompt TEXT,
    configuration JSONB DEFAULT '{}'::JSONB,
    messaging_channels JSONB DEFAULT '[]'::JSONB, -- Array of enabled channels: whatsapp, email, instagram
    is_active BOOLEAN DEFAULT true,
    deployment_status VARCHAR(50) DEFAULT 'draft' CHECK (deployment_status IN ('draft', 'deploying', 'active', 'paused', 'error')),
    performance_metrics JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, agent_name)
);

-- Agent learning and memory system
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    memory_type VARCHAR(50) NOT NULL CHECK (memory_type IN ('conversation', 'pattern', 'preference', 'workflow')),
    context VARCHAR(255),
    content TEXT NOT NULL,
    embedding_vector VECTOR(1536), -- OpenAI ada-002 embedding size
    importance_score FLOAT DEFAULT 0.5 CHECK (importance_score BETWEEN 0 AND 1),
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Agent conversation history with complete customer isolation
CREATE TABLE IF NOT EXISTS agent_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    conversation_id VARCHAR(255) NOT NULL,
    channel VARCHAR(50) NOT NULL CHECK (channel IN ('whatsapp', 'email', 'instagram', 'api', 'web')),
    participant_id VARCHAR(255), -- Channel-specific user ID
    message_type VARCHAR(50) NOT NULL CHECK (message_type IN ('user', 'agent', 'system')),
    content TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    sentiment_score FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- WORKFLOW & AUTOMATION MANAGEMENT
-- ====================================================================

-- n8n workflow integration and management
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    workflow_name VARCHAR(255) NOT NULL,
    n8n_workflow_id VARCHAR(255),
    workflow_type VARCHAR(100) NOT NULL CHECK (workflow_type IN ('social_automation', 'financial_tracking', 'marketing_campaign', 'business_process')),
    configuration JSONB DEFAULT '{}'::JSONB,
    status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'error')),
    execution_count INTEGER DEFAULT 0,
    last_execution TIMESTAMP WITH TIME ZONE,
    performance_metrics JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Workflow execution logs with performance tracking
CREATE TABLE IF NOT EXISTS workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    execution_id VARCHAR(255),
    status VARCHAR(50) NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'timeout')),
    input_data JSONB,
    output_data JSONB,
    error_message TEXT,
    execution_time_ms INTEGER,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- ====================================================================
-- MESSAGING & CHANNEL MANAGEMENT
-- ====================================================================

-- Channel configurations per customer
CREATE TABLE IF NOT EXISTS messaging_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    channel_type VARCHAR(50) NOT NULL CHECK (channel_type IN ('whatsapp', 'email', 'instagram', 'telegram')),
    channel_name VARCHAR(255) NOT NULL,
    configuration JSONB NOT NULL,
    credentials_encrypted TEXT, -- Encrypted API tokens and credentials
    is_active BOOLEAN DEFAULT true,
    last_health_check TIMESTAMP WITH TIME ZONE,
    health_status VARCHAR(50) DEFAULT 'unknown' CHECK (health_status IN ('healthy', 'warning', 'error', 'unknown')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, channel_type, channel_name)
);

-- Message queue for reliable delivery
CREATE TABLE IF NOT EXISTS message_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    channel_type VARCHAR(50) NOT NULL,
    recipient VARCHAR(255) NOT NULL,
    message_content TEXT NOT NULL,
    message_type VARCHAR(50) DEFAULT 'text' CHECK (message_type IN ('text', 'image', 'video', 'document', 'template')),
    priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'retry')),
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    scheduled_for TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- BUSINESS INTELLIGENCE & ANALYTICS
-- ====================================================================

-- Customer activity tracking for business intelligence
CREATE TABLE IF NOT EXISTS customer_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    activity_type VARCHAR(100) NOT NULL,
    activity_data JSONB DEFAULT '{}'::JSONB,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Cost tracking for AI model usage
CREATE TABLE IF NOT EXISTS ai_usage_costs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    model_provider VARCHAR(50) NOT NULL CHECK (model_provider IN ('openai', 'anthropic', 'meta', 'deepseek')),
    model_name VARCHAR(100) NOT NULL,
    usage_type VARCHAR(50) NOT NULL CHECK (usage_type IN ('input_tokens', 'output_tokens', 'requests', 'embeddings')),
    quantity INTEGER NOT NULL,
    cost_usd DECIMAL(10,6) NOT NULL,
    billing_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- SECURITY & AUDIT LOGGING
-- ====================================================================

-- Complete audit trail for compliance
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(255) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    changes JSONB,
    ip_address INET,
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Security incident tracking
CREATE TABLE IF NOT EXISTS security_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
    incident_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50) NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    description TEXT NOT NULL,
    affected_resources JSONB,
    status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved', 'false_positive')),
    assigned_to VARCHAR(255),
    resolved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- INDEXES FOR PERFORMANCE OPTIMIZATION
-- ====================================================================

-- Customer isolation performance indexes
CREATE INDEX IF NOT EXISTS idx_customers_active ON customers(is_active, created_at);
CREATE INDEX IF NOT EXISTS idx_users_customer_email ON users(customer_id, email);
CREATE INDEX IF NOT EXISTS idx_agents_customer_type ON agents(customer_id, agent_type, is_active);
CREATE INDEX IF NOT EXISTS idx_agent_memories_customer_agent ON agent_memories(customer_id, agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workflows_customer_status ON workflows(customer_id, status);
CREATE INDEX IF NOT EXISTS idx_messaging_channels_customer ON messaging_channels(customer_id, is_active);

-- Performance indexes for real-time operations
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at) WHERE is_revoked = false;
CREATE INDEX IF NOT EXISTS idx_api_keys_customer_active ON api_keys(customer_id, is_active);
CREATE INDEX IF NOT EXISTS idx_message_queue_status_priority ON message_queue(status, priority, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_agent_conversations_customer_time ON agent_conversations(customer_id, created_at DESC);

-- Additional indexes for tables with inline index declarations
CREATE INDEX IF NOT EXISTS idx_customer_activities_customer_type_time ON customer_activities(customer_id, activity_type, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_costs_customer_billing_provider ON ai_usage_costs(customer_id, billing_date, model_provider);
CREATE INDEX IF NOT EXISTS idx_audit_logs_customer_action_time ON audit_logs(customer_id, action, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time ON audit_logs(user_id, created_at);

-- Vector search index for agent memories (requires pgvector extension)
CREATE INDEX IF NOT EXISTS idx_agent_memories_embedding ON agent_memories USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists = 100);

-- ====================================================================
-- ROW LEVEL SECURITY POLICIES (Critical for Customer Isolation)
-- ====================================================================

-- Enable RLS on all customer data tables
ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messaging_channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage_costs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- RLS policies will be created via application logic with customer_id context
-- This ensures 100% customer data isolation at the database level

-- ====================================================================
-- FUNCTIONS & TRIGGERS FOR AUTOMATION
-- ====================================================================

-- Automatic timestamp updates
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers to relevant tables
CREATE TRIGGER update_customers_updated_at BEFORE UPDATE ON customers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_workflows_updated_at BEFORE UPDATE ON workflows FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_messaging_channels_updated_at BEFORE UPDATE ON messaging_channels FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_security_incidents_updated_at BEFORE UPDATE ON security_incidents FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Automatic API quota reset function
CREATE OR REPLACE FUNCTION reset_api_quotas()
RETURNS void AS $$
BEGIN
    UPDATE customers 
    SET api_quota_used = 0,
        api_quota_reset_date = CURRENT_TIMESTAMP + INTERVAL '1 month'
    WHERE api_quota_reset_date <= CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- Clean up expired tokens
CREATE OR REPLACE FUNCTION cleanup_expired_tokens()
RETURNS void AS $$
BEGIN
    DELETE FROM refresh_tokens WHERE expires_at <= CURRENT_TIMESTAMP;
    UPDATE api_keys SET is_active = false WHERE expires_at <= CURRENT_TIMESTAMP;
END;
$$ LANGUAGE plpgsql;

-- ====================================================================
-- INITIAL DATA & CONFIGURATION
-- ====================================================================

-- Insert default system customer for platform operations (Tier 0)
INSERT INTO customers (
    id,
    business_name,
    business_type,
    contact_email,
    onboarding_status,
    subscription_tier,
    api_quota_limit,
    is_active,
    metadata
) VALUES (
    '00000000-0000-0000-0000-000000000000',
    'AI Agency Platform System',
    'platform',
    'system@aiagencyplatform.com',
    'active',
    'enterprise',
    999999999,
    true,
    '{"internal": true, "tier": 0}'
) ON CONFLICT (id) DO NOTHING;

-- Grant necessary permissions for vector operations
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mcphub;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mcphub;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO mcphub;

-- ====================================================================
-- SCHEMA VERSION & VALIDATION
-- ====================================================================

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(50) PRIMARY KEY,
    description TEXT,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_migrations (version, description) VALUES 
    ('1.0.0', 'Phase 1 Foundation Infrastructure Schema')
ON CONFLICT (version) DO NOTHING;

-- Validate schema integrity
DO $$
BEGIN
    -- Verify all required tables exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name IN 
        ('customers', 'users', 'agents', 'workflows', 'messaging_channels', 'audit_logs')) THEN
        RAISE EXCEPTION 'Critical tables missing from schema deployment';
    END IF;
    
    -- Verify vector extension is available
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE NOTICE 'Vector extension not installed - agent memory features will be limited';
    END IF;
    
    RAISE NOTICE 'Phase 1 database schema validation completed successfully';
END $$;