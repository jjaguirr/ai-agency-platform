-- AI Agency Platform - PostgreSQL Database Initialization
-- Creates multiple databases for different services and infrastructure management

-- Create LangFuse database
CREATE DATABASE langfuse;

-- Create Grafana database  
CREATE DATABASE grafana;

-- Create n8n database
CREATE DATABASE n8n;

-- Grant permissions to main user
GRANT ALL PRIVILEGES ON DATABASE langfuse TO mcphub;
GRANT ALL PRIVILEGES ON DATABASE grafana TO mcphub;
GRANT ALL PRIVILEGES ON DATABASE n8n TO mcphub;

-- Create additional users for specific services (optional)
CREATE USER langfuse_user WITH PASSWORD 'langfuse_password';
CREATE USER grafana_user WITH PASSWORD 'grafana_password';
CREATE USER n8n_user WITH PASSWORD 'n8n_password';

-- Grant database-specific permissions
GRANT CONNECT ON DATABASE langfuse TO langfuse_user;
GRANT CONNECT ON DATABASE grafana TO grafana_user;  
GRANT CONNECT ON DATABASE n8n TO n8n_user;

-- ========================================
-- PRODUCTION INFRASTRUCTURE TABLES
-- ========================================

-- Switch to main database for infrastructure tables
\c mcphub;

-- Customer Infrastructure Management
CREATE TABLE IF NOT EXISTS customer_infrastructure (
    id SERIAL PRIMARY KEY,
    customer_id TEXT UNIQUE NOT NULL,
    tier TEXT NOT NULL DEFAULT 'starter',
    mcp_server_id TEXT NOT NULL,
    service_endpoints JSONB NOT NULL,
    resource_limits JSONB NOT NULL,
    provisioning_time DECIMAL(10,3) NOT NULL,
    status TEXT NOT NULL DEFAULT 'provisioning',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_customer_infrastructure_customer_id ON customer_infrastructure(customer_id);
CREATE INDEX idx_customer_infrastructure_status ON customer_infrastructure(status);
CREATE INDEX idx_customer_infrastructure_tier ON customer_infrastructure(tier);

-- Customer Memory Audit (per-customer memory operations)
CREATE TABLE IF NOT EXISTS customer_memory_audit (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_memory_audit_customer ON customer_memory_audit(customer_id);
CREATE INDEX idx_memory_audit_timestamp ON customer_memory_audit(timestamp);
CREATE INDEX idx_memory_audit_action ON customer_memory_audit(action);

-- Customer Configuration Storage
CREATE TABLE IF NOT EXISTS customer_config (
    customer_id TEXT PRIMARY KEY,
    config JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- EA Conversation History (cross-channel continuity)
CREATE TABLE IF NOT EXISTS ea_conversations (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    messages JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conversations_customer ON ea_conversations(customer_id);
CREATE INDEX idx_conversations_session ON ea_conversations(session_id);
CREATE INDEX idx_conversations_channel ON ea_conversations(channel);

-- Production Monitoring & Metrics
CREATE TABLE IF NOT EXISTS customer_metrics (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    cpu_usage DECIMAL(5,2),
    memory_usage DECIMAL(5,2),
    storage_usage DECIMAL(10,2),
    request_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    response_time DECIMAL(10,3),
    memory_recall_time DECIMAL(10,3),
    uptime_percentage DECIMAL(5,2),
    cost_daily DECIMAL(10,4),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_customer_metrics_customer_id ON customer_metrics(customer_id);
CREATE INDEX idx_customer_metrics_created_at ON customer_metrics(created_at);
CREATE INDEX idx_customer_metrics_tier ON customer_metrics(tier);

-- Monitoring Alerts
CREATE TABLE IF NOT EXISTS monitoring_alerts (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    level TEXT NOT NULL,
    metric TEXT NOT NULL,
    threshold DECIMAL(15,6),
    current_value DECIMAL(15,6),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP NULL
);

CREATE INDEX idx_monitoring_alerts_customer_id ON monitoring_alerts(customer_id);
CREATE INDEX idx_monitoring_alerts_level ON monitoring_alerts(level);
CREATE INDEX idx_monitoring_alerts_resolved ON monitoring_alerts(resolved_at);

-- Auto-Scaling Actions Log
CREATE TABLE IF NOT EXISTS scaling_actions (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    justification TEXT NOT NULL,
    cost_impact DECIMAL(10,4),
    confidence_score DECIMAL(3,2),
    executed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_scaling_actions_customer_id ON scaling_actions(customer_id);
CREATE INDEX idx_scaling_actions_executed_at ON scaling_actions(executed_at);
CREATE INDEX idx_scaling_actions_action ON scaling_actions(action);

-- Customer Requests Tracking (for performance analysis)
CREATE TABLE IF NOT EXISTS customer_requests (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    method TEXT NOT NULL,
    status INTEGER NOT NULL,
    response_time DECIMAL(10,3),
    request_size INTEGER,
    response_size INTEGER,
    user_agent TEXT,
    ip_address INET,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_customer_requests_customer_id ON customer_requests(customer_id);
CREATE INDEX idx_customer_requests_created_at ON customer_requests(created_at);
CREATE INDEX idx_customer_requests_status ON customer_requests(status);
CREATE INDEX idx_customer_requests_endpoint ON customer_requests(endpoint);

-- Customer Errors Tracking
CREATE TABLE IF NOT EXISTS customer_errors (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT,
    stack_trace TEXT,
    endpoint TEXT,
    request_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_customer_errors_customer_id ON customer_errors(customer_id);
CREATE INDEX idx_customer_errors_created_at ON customer_errors(created_at);
CREATE INDEX idx_customer_errors_type ON customer_errors(error_type);

-- Infrastructure Health Tracking
CREATE TABLE IF NOT EXISTS infrastructure_health (
    id SERIAL PRIMARY KEY,
    customer_id TEXT,
    service_name TEXT NOT NULL,
    service_type TEXT NOT NULL,
    container_id TEXT,
    status TEXT NOT NULL,
    health_check_result JSONB,
    response_time DECIMAL(10,3),
    cpu_usage DECIMAL(5,2),
    memory_usage DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_infrastructure_health_customer_id ON infrastructure_health(customer_id);
CREATE INDEX idx_infrastructure_health_service ON infrastructure_health(service_name);
CREATE INDEX idx_infrastructure_health_status ON infrastructure_health(status);
CREATE INDEX idx_infrastructure_health_created_at ON infrastructure_health(created_at);

-- Cost Tracking and Optimization
CREATE TABLE IF NOT EXISTS cost_tracking (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_usage DECIMAL(15,6),
    unit_cost DECIMAL(10,6),
    total_cost DECIMAL(10,4),
    billing_period_start TIMESTAMP NOT NULL,
    billing_period_end TIMESTAMP NOT NULL,
    optimization_suggestions JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_cost_tracking_customer_id ON cost_tracking(customer_id);
CREATE INDEX idx_cost_tracking_billing_period ON cost_tracking(billing_period_start, billing_period_end);
CREATE INDEX idx_cost_tracking_resource_type ON cost_tracking(resource_type);

-- Customer Usage Patterns (for predictive scaling)
CREATE TABLE IF NOT EXISTS usage_patterns (
    id SERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL,
    pattern_type TEXT NOT NULL, -- 'hourly', 'daily', 'weekly', 'seasonal'
    pattern_data JSONB NOT NULL,
    confidence_score DECIMAL(3,2),
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_usage_patterns_customer_id ON usage_patterns(customer_id);
CREATE INDEX idx_usage_patterns_type ON usage_patterns(pattern_type);
CREATE INDEX idx_usage_patterns_updated ON usage_patterns(last_updated);

-- Infrastructure Deployments Log
CREATE TABLE IF NOT EXISTS deployment_log (
    id SERIAL PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    version TEXT NOT NULL,
    customer_id TEXT, -- NULL for platform-wide deployments
    deployment_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    rollback_at TIMESTAMP,
    deployment_config JSONB,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_deployment_log_deployment_id ON deployment_log(deployment_id);
CREATE INDEX idx_deployment_log_environment ON deployment_log(environment);
CREATE INDEX idx_deployment_log_customer_id ON deployment_log(customer_id);
CREATE INDEX idx_deployment_log_status ON deployment_log(status);

-- Performance Benchmarks
CREATE TABLE IF NOT EXISTS performance_benchmarks (
    id SERIAL PRIMARY KEY,
    benchmark_type TEXT NOT NULL,
    customer_id TEXT,
    tier TEXT,
    metric_name TEXT NOT NULL,
    target_value DECIMAL(15,6),
    actual_value DECIMAL(15,6),
    sla_met BOOLEAN DEFAULT FALSE,
    test_duration DECIMAL(10,3),
    test_conditions JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_performance_benchmarks_type ON performance_benchmarks(benchmark_type);
CREATE INDEX idx_performance_benchmarks_customer ON performance_benchmarks(customer_id);
CREATE INDEX idx_performance_benchmarks_sla ON performance_benchmarks(sla_met);
CREATE INDEX idx_performance_benchmarks_created ON performance_benchmarks(created_at);

-- Connect to each database and grant schema permissions
\c langfuse;
GRANT ALL ON SCHEMA public TO langfuse_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO langfuse_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO langfuse_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO langfuse_user;

\c grafana;
GRANT ALL ON SCHEMA public TO grafana_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO grafana_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO grafana_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO grafana_user;

\c n8n;
GRANT ALL ON SCHEMA public TO n8n_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO n8n_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO n8n_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO n8n_user;