-- AI Agency Platform - Customer-Specific Database Initialization
-- Creates customer-isolated infrastructure tables within the customer database
-- This script ensures complete customer isolation by creating all infrastructure
-- tables within each customer's dedicated database rather than shared tables.
--
-- Variables replaced by provisioning orchestrator:
-- CUSTOMER_ID environment variable should be set before running this script

-- ========================================
-- CUSTOMER-ISOLATED INFRASTRUCTURE TABLES
-- ========================================

-- Customer Infrastructure Management (per-customer isolation)
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

-- Customer Memory Audit (per-customer isolated memory operations)
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

-- Customer Configuration Storage (per-customer isolated)
CREATE TABLE IF NOT EXISTS customer_config (
    customer_id TEXT PRIMARY KEY,
    config JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- EA Conversation History (per-customer isolated cross-channel continuity)
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

-- Customer Metrics (per-customer isolated monitoring)
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

-- Customer-Specific Monitoring Alerts
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

-- Customer-Specific Auto-Scaling Actions Log
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

-- Customer Requests Tracking (per-customer isolated performance analysis)
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

-- Customer-Specific Errors Tracking
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

-- Customer-Specific Infrastructure Health Tracking
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

-- Customer-Specific Cost Tracking and Optimization
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

-- Customer-Specific Usage Patterns (for predictive scaling)
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

-- Customer-Specific Deployment Log
CREATE TABLE IF NOT EXISTS deployment_log (
    id SERIAL PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    environment TEXT NOT NULL,
    version TEXT NOT NULL,
    customer_id TEXT NOT NULL, -- Always populated for customer-specific deployments
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

-- Customer-Specific Performance Benchmarks
CREATE TABLE IF NOT EXISTS performance_benchmarks (
    id SERIAL PRIMARY KEY,
    benchmark_type TEXT NOT NULL,
    customer_id TEXT NOT NULL, -- Always populated for customer isolation
    tier TEXT NOT NULL,
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

-- ========================================
-- ROW-LEVEL SECURITY (RLS) POLICIES
-- ========================================
-- Additional security layer to ensure data isolation even with application bugs

-- Enable RLS on all customer-sensitive tables
ALTER TABLE customer_infrastructure ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_memory_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE ea_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoring_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE scaling_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_errors ENABLE ROW LEVEL SECURITY;
ALTER TABLE infrastructure_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployment_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE performance_benchmarks ENABLE ROW LEVEL SECURITY;

-- Create RLS policies to enforce customer isolation
-- These policies ensure that even if application code has bugs, 
-- customers can only access their own data

CREATE POLICY customer_isolation_policy ON customer_infrastructure
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON customer_memory_audit
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON customer_config
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON ea_conversations
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON customer_metrics
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON monitoring_alerts
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON scaling_actions
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON customer_requests
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON customer_errors
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON infrastructure_health
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON cost_tracking
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON usage_patterns
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON deployment_log
    USING (customer_id = current_setting('app.customer_id', true));

CREATE POLICY customer_isolation_policy ON performance_benchmarks
    USING (customer_id = current_setting('app.customer_id', true));

-- ========================================
-- CUSTOMER ISOLATION VALIDATION
-- ========================================

-- Create a function to validate customer isolation
CREATE OR REPLACE FUNCTION validate_customer_isolation(test_customer_id TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    table_record RECORD;
    accessible_count INTEGER;
    total_count INTEGER;
BEGIN
    -- Set customer context for testing
    PERFORM set_config('app.customer_id', test_customer_id, false);
    
    -- Test each table to ensure RLS is working
    FOR table_record IN 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name LIKE '%customer%'
    LOOP
        EXECUTE format('SELECT COUNT(*) FROM %I', table_record.table_name) INTO accessible_count;
        EXECUTE format('SELECT COUNT(*) FROM %I', table_record.table_name) INTO total_count;
        
        -- If we can see records for other customers, isolation is broken
        IF accessible_count > 0 THEN
            EXECUTE format('
                SELECT COUNT(*) FROM %I WHERE customer_id != %L', 
                table_record.table_name, test_customer_id
            ) INTO total_count;
            
            IF total_count > 0 THEN
                RAISE NOTICE 'Customer isolation FAILED for table: %', table_record.table_name;
                RETURN FALSE;
            END IF;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Customer isolation VALIDATED for customer: %', test_customer_id;
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- COMPLIANCE & AUDIT FUNCTIONS
-- ========================================

-- Function to generate customer data export (GDPR compliance)
CREATE OR REPLACE FUNCTION export_customer_data(target_customer_id TEXT)
RETURNS JSON AS $$
DECLARE
    customer_data JSON;
BEGIN
    -- Set customer context
    PERFORM set_config('app.customer_id', target_customer_id, false);
    
    -- Export all customer data as JSON
    SELECT json_build_object(
        'customer_id', target_customer_id,
        'export_timestamp', NOW(),
        'infrastructure', (SELECT json_agg(row_to_json(t)) FROM customer_infrastructure t),
        'memory_audit', (SELECT json_agg(row_to_json(t)) FROM customer_memory_audit t),
        'config', (SELECT json_agg(row_to_json(t)) FROM customer_config t),
        'conversations', (SELECT json_agg(row_to_json(t)) FROM ea_conversations t),
        'metrics', (SELECT json_agg(row_to_json(t)) FROM customer_metrics t),
        'alerts', (SELECT json_agg(row_to_json(t)) FROM monitoring_alerts t),
        'scaling_actions', (SELECT json_agg(row_to_json(t)) FROM scaling_actions t),
        'requests', (SELECT json_agg(row_to_json(t)) FROM customer_requests t),
        'errors', (SELECT json_agg(row_to_json(t)) FROM customer_errors t),
        'infrastructure_health', (SELECT json_agg(row_to_json(t)) FROM infrastructure_health t),
        'cost_tracking', (SELECT json_agg(row_to_json(t)) FROM cost_tracking t),
        'usage_patterns', (SELECT json_agg(row_to_json(t)) FROM usage_patterns t),
        'deployment_log', (SELECT json_agg(row_to_json(t)) FROM deployment_log t),
        'performance_benchmarks', (SELECT json_agg(row_to_json(t)) FROM performance_benchmarks t)
    ) INTO customer_data;
    
    RETURN customer_data;
END;
$$ LANGUAGE plpgsql;

-- Function to securely delete all customer data (GDPR right to be forgotten)
CREATE OR REPLACE FUNCTION delete_customer_data(target_customer_id TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    table_record RECORD;
    deleted_count INTEGER := 0;
BEGIN
    -- Set customer context
    PERFORM set_config('app.customer_id', target_customer_id, false);
    
    -- Delete from all customer tables
    FOR table_record IN 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name LIKE '%customer%'
    LOOP
        EXECUTE format('DELETE FROM %I WHERE customer_id = %L', 
                      table_record.table_name, target_customer_id);
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE 'Deleted % rows from %', deleted_count, table_record.table_name;
    END LOOP;
    
    RAISE NOTICE 'Customer data deletion completed for customer: %', target_customer_id;
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ========================================
-- INITIAL CUSTOMER DATA SETUP
-- ========================================

-- Insert initial customer infrastructure record if CUSTOMER_ID is provided
-- This will be populated by the provisioning orchestrator
DO $$
DECLARE
    current_customer_id TEXT;
BEGIN
    current_customer_id := current_setting('app.customer_id', true);
    
    IF current_customer_id IS NOT NULL AND current_customer_id != '' THEN
        -- Set RLS context
        PERFORM set_config('app.customer_id', current_customer_id, false);
        
        -- Insert initial customer infrastructure record
        INSERT INTO customer_infrastructure (
            customer_id, 
            tier, 
            mcp_server_id, 
            service_endpoints, 
            resource_limits,
            provisioning_time,
            status
        ) VALUES (
            current_customer_id,
            'starter', -- Will be updated by provisioning orchestrator
            'mcp-server-' || current_customer_id,
            '{}',
            '{"memory": "2GB", "cpu": "1", "storage": "10GB"}',
            0.0,
            'initializing'
        ) ON CONFLICT (customer_id) DO NOTHING;
        
        RAISE NOTICE 'Customer database initialized for customer: %', current_customer_id;
    END IF;
END $$;

-- Create indices for optimal performance with customer isolation
-- These indices ensure that queries filtered by customer_id are fast
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_global_customer_lookup 
    ON customer_infrastructure(customer_id, status, tier);