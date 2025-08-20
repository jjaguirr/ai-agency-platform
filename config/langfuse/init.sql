-- Langfuse Database Initialization for AI Agency Platform
-- This script sets up the Langfuse database with AI Agency Platform specific configurations

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create AI Agency Platform specific tables for enhanced functionality

-- Infrastructure Agent Projects table
CREATE TABLE IF NOT EXISTS ai_agency_projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    agent_type VARCHAR(100) NOT NULL,
    mcphub_group VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Insert Infrastructure Agent projects
INSERT INTO ai_agency_projects (name, description, agent_type, mcphub_group) VALUES
    ('research-agent', 'Business Intelligence and Market Research Agent', 'research', 'business-operations'),
    ('business-agent', 'Business Analytics and KPI Tracking Agent', 'business', 'business-operations'),
    ('creative-agent', 'Marketing Creative and Content Generation Agent', 'creative', 'business-operations'),
    ('development-agent', 'Infrastructure Development and Automation Agent', 'development', 'development-infrastructure'),
    ('launch-bot', 'Self-Configuring Customer Onboarding Bot', 'launch-bot', 'customer-{customerId}'),
    ('n8n-workflow', 'Visual Workflow Architect and Automation Agent', 'n8n-workflow', 'business-operations')
ON CONFLICT (name) DO NOTHING;

-- Infrastructure Agent Performance Metrics table
CREATE TABLE IF NOT EXISTS ai_agency_agent_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_type VARCHAR(100) NOT NULL,
    ai_model VARCHAR(100) NOT NULL,
    customer_id VARCHAR(255),
    execution_time_ms INTEGER,
    token_usage JSONB,
    cost_usd DECIMAL(10,6),
    success BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Customer Configuration table for LAUNCH bot tracking
CREATE TABLE IF NOT EXISTS ai_agency_customer_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id VARCHAR(255) NOT NULL UNIQUE,
    customer_name VARCHAR(255),
    industry VARCHAR(100),
    ai_model_preference VARCHAR(100),
    launch_bot_state VARCHAR(50) DEFAULT 'blank',
    configuration_time_seconds INTEGER,
    tools_configured JSONB DEFAULT '[]',
    configuration_success BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- AI Model Performance tracking
CREATE TABLE IF NOT EXISTS ai_agency_model_performance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ai_model VARCHAR(100) NOT NULL,
    agent_type VARCHAR(100) NOT NULL,
    date DATE DEFAULT CURRENT_DATE,
    total_requests INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(10,6) DEFAULT 0,
    avg_latency_ms DECIMAL(8,2) DEFAULT 0,
    success_rate DECIMAL(5,4) DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ai_model, agent_type, date)
);

-- Prompt A/B Testing Results
CREATE TABLE IF NOT EXISTS ai_agency_prompt_experiments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_name VARCHAR(255) NOT NULL,
    version_a VARCHAR(50) NOT NULL,
    version_b VARCHAR(50) NOT NULL,
    agent_type VARCHAR(100) NOT NULL,
    metric_name VARCHAR(100) NOT NULL, -- 'success_rate', 'customer_satisfaction', 'latency', etc.
    version_a_value DECIMAL(10,6),
    version_b_value DECIMAL(10,6),
    sample_size_a INTEGER,
    sample_size_b INTEGER,
    statistical_significance DECIMAL(5,4),
    winner VARCHAR(10), -- 'A', 'B', or 'NONE'
    experiment_start TIMESTAMP,
    experiment_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_agent_metrics_agent_type ON ai_agency_agent_metrics(agent_type);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_ai_model ON ai_agency_agent_metrics(ai_model);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_customer_id ON ai_agency_agent_metrics(customer_id);
CREATE INDEX IF NOT EXISTS idx_agent_metrics_created_at ON ai_agency_agent_metrics(created_at);

CREATE INDEX IF NOT EXISTS idx_customer_configs_customer_id ON ai_agency_customer_configs(customer_id);
CREATE INDEX IF NOT EXISTS idx_customer_configs_state ON ai_agency_customer_configs(launch_bot_state);

CREATE INDEX IF NOT EXISTS idx_model_performance_model ON ai_agency_model_performance(ai_model);
CREATE INDEX IF NOT EXISTS idx_model_performance_agent ON ai_agency_model_performance(agent_type);
CREATE INDEX IF NOT EXISTS idx_model_performance_date ON ai_agency_model_performance(date);

CREATE INDEX IF NOT EXISTS idx_prompt_experiments_name ON ai_agency_prompt_experiments(prompt_name);
CREATE INDEX IF NOT EXISTS idx_prompt_experiments_agent ON ai_agency_prompt_experiments(agent_type);

-- Functions for automated metrics aggregation
CREATE OR REPLACE FUNCTION update_model_performance_daily()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO ai_agency_model_performance (
        ai_model, 
        agent_type, 
        date,
        total_requests,
        total_tokens,
        total_cost_usd,
        avg_latency_ms,
        success_rate
    )
    SELECT 
        NEW.ai_model,
        NEW.agent_type,
        CURRENT_DATE,
        1,
        COALESCE((NEW.token_usage->>'total')::INTEGER, 0),
        NEW.cost_usd,
        NEW.execution_time_ms,
        CASE WHEN NEW.success THEN 1.0 ELSE 0.0 END
    ON CONFLICT (ai_model, agent_type, date) 
    DO UPDATE SET
        total_requests = ai_agency_model_performance.total_requests + 1,
        total_tokens = ai_agency_model_performance.total_tokens + COALESCE((NEW.token_usage->>'total')::INTEGER, 0),
        total_cost_usd = ai_agency_model_performance.total_cost_usd + NEW.cost_usd,
        avg_latency_ms = (ai_agency_model_performance.avg_latency_ms * ai_agency_model_performance.total_requests + NEW.execution_time_ms) / (ai_agency_model_performance.total_requests + 1),
        success_rate = (ai_agency_model_performance.success_rate * ai_agency_model_performance.total_requests + CASE WHEN NEW.success THEN 1.0 ELSE 0.0 END) / (ai_agency_model_performance.total_requests + 1),
        updated_at = NOW();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for automated performance tracking
CREATE TRIGGER trigger_update_model_performance
    AFTER INSERT ON ai_agency_agent_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_model_performance_daily();

-- Initial admin user setup (will be created by Langfuse on first run)
-- This is handled by Langfuse's internal initialization

\echo 'AI Agency Platform Langfuse database initialized successfully!';