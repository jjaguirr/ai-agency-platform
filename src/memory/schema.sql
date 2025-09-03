-- Memory Infrastructure Database Schema
-- Per-customer memory audit logs and performance tracking

-- Customer memory audit logs table
CREATE TABLE IF NOT EXISTS customer_memory_audit (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    action VARCHAR(100) NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Indexes for performance
    INDEX idx_customer_memory_audit_customer_id (customer_id),
    INDEX idx_customer_memory_audit_timestamp (timestamp DESC),
    INDEX idx_customer_memory_audit_action (action),
    INDEX idx_customer_memory_audit_data_gin (data) -- GIN index for JSONB queries
);

-- Performance metrics tracking table
CREATE TABLE IF NOT EXISTS memory_performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    operation VARCHAR(100) NOT NULL,
    latency_seconds DECIMAL(8,6) NOT NULL,
    success BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Indexes for performance queries
    INDEX idx_memory_performance_customer_id (customer_id),
    INDEX idx_memory_performance_operation (operation),
    INDEX idx_memory_performance_timestamp (timestamp DESC),
    INDEX idx_memory_performance_latency (latency_seconds)
);

-- Customer isolation validation logs
CREATE TABLE IF NOT EXISTS isolation_validation_logs (
    id BIGSERIAL PRIMARY KEY,
    test_id UUID NOT NULL DEFAULT gen_random_uuid(),
    customers_tested TEXT[] NOT NULL,
    isolation_verified BOOLEAN NOT NULL,
    violation_count INTEGER NOT NULL DEFAULT 0,
    validation_details JSONB NOT NULL,
    test_duration_seconds DECIMAL(8,3),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_isolation_validation_test_id (test_id),
    INDEX idx_isolation_validation_timestamp (timestamp DESC),
    INDEX idx_isolation_validation_verified (isolation_verified)
);

-- SLA violation alerts table
CREATE TABLE IF NOT EXISTS sla_violation_alerts (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    operation VARCHAR(100) NOT NULL,
    alert_type VARCHAR(50) NOT NULL, -- 'warning' or 'critical'
    alert_message TEXT NOT NULL,
    latency_seconds DECIMAL(8,6),
    consecutive_violations INTEGER DEFAULT 0,
    alert_data JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    
    -- Indexes
    INDEX idx_sla_alerts_customer_id (customer_id),
    INDEX idx_sla_alerts_type (alert_type),
    INDEX idx_sla_alerts_timestamp (timestamp DESC),
    INDEX idx_sla_alerts_unresolved (resolved_at) WHERE resolved_at IS NULL
);

-- Memory usage statistics (aggregated per customer)
CREATE TABLE IF NOT EXISTS customer_memory_stats (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    stats_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Operation counts
    total_operations INTEGER NOT NULL DEFAULT 0,
    mem0_operations INTEGER NOT NULL DEFAULT 0,
    redis_operations INTEGER NOT NULL DEFAULT 0,
    postgres_operations INTEGER NOT NULL DEFAULT 0,
    
    -- Performance metrics
    avg_latency_seconds DECIMAL(8,6),
    p95_latency_seconds DECIMAL(8,6),
    p99_latency_seconds DECIMAL(8,6),
    max_latency_seconds DECIMAL(8,6),
    
    -- SLA compliance
    sla_violations INTEGER NOT NULL DEFAULT 0,
    sla_compliance_percent DECIMAL(5,2),
    
    -- Error tracking
    error_count INTEGER NOT NULL DEFAULT 0,
    success_rate_percent DECIMAL(5,2),
    
    -- Memory utilization (estimated)
    estimated_memory_kb BIGINT DEFAULT 0,
    
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Unique constraint on customer and date
    UNIQUE(customer_id, stats_date),
    
    -- Indexes
    INDEX idx_memory_stats_customer_id (customer_id),
    INDEX idx_memory_stats_date (stats_date DESC)
);

-- Create a function to update customer memory stats
CREATE OR REPLACE FUNCTION update_customer_memory_stats()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO customer_memory_stats (
        customer_id,
        stats_date,
        total_operations,
        avg_latency_seconds,
        sla_violations,
        error_count
    )
    VALUES (
        NEW.customer_id,
        CURRENT_DATE,
        1,
        NEW.latency_seconds,
        CASE WHEN NEW.latency_seconds > 0.5 THEN 1 ELSE 0 END, -- 500ms SLA
        CASE WHEN NEW.success THEN 0 ELSE 1 END
    )
    ON CONFLICT (customer_id, stats_date)
    DO UPDATE SET
        total_operations = customer_memory_stats.total_operations + 1,
        avg_latency_seconds = (
            (customer_memory_stats.avg_latency_seconds * customer_memory_stats.total_operations + NEW.latency_seconds) /
            (customer_memory_stats.total_operations + 1)
        ),
        sla_violations = customer_memory_stats.sla_violations + 
            CASE WHEN NEW.latency_seconds > 0.5 THEN 1 ELSE 0 END,
        error_count = customer_memory_stats.error_count + 
            CASE WHEN NEW.success THEN 0 ELSE 1 END,
        success_rate_percent = (
            ((customer_memory_stats.total_operations - customer_memory_stats.error_count) * 100.0) /
            GREATEST(customer_memory_stats.total_operations, 1)
        ),
        sla_compliance_percent = (
            ((customer_memory_stats.total_operations - customer_memory_stats.sla_violations) * 100.0) /
            GREATEST(customer_memory_stats.total_operations, 1)
        ),
        updated_at = NOW();
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update stats
CREATE TRIGGER trigger_update_memory_stats
    AFTER INSERT ON memory_performance_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_customer_memory_stats();

-- Views for easier querying

-- Current SLA compliance view
CREATE OR REPLACE VIEW current_sla_compliance AS
SELECT 
    customer_id,
    total_operations,
    sla_violations,
    ROUND(sla_compliance_percent, 2) as sla_compliance_percent,
    ROUND(avg_latency_seconds * 1000, 2) as avg_latency_ms,
    success_rate_percent,
    updated_at
FROM customer_memory_stats 
WHERE stats_date = CURRENT_DATE
ORDER BY sla_compliance_percent ASC, total_operations DESC;

-- Recent memory operations view
CREATE OR REPLACE VIEW recent_memory_operations AS
SELECT 
    customer_id,
    operation,
    ROUND(latency_seconds * 1000, 2) as latency_ms,
    success,
    metadata,
    timestamp
FROM memory_performance_metrics 
WHERE timestamp >= NOW() - INTERVAL '1 hour'
ORDER BY timestamp DESC;

-- Active SLA violation alerts view
CREATE OR REPLACE VIEW active_sla_alerts AS
SELECT 
    customer_id,
    operation,
    alert_type,
    alert_message,
    ROUND(latency_seconds * 1000, 2) as latency_ms,
    consecutive_violations,
    timestamp,
    NOW() - timestamp as alert_age
FROM sla_violation_alerts 
WHERE resolved_at IS NULL
ORDER BY 
    CASE alert_type 
        WHEN 'critical' THEN 1 
        WHEN 'warning' THEN 2 
        ELSE 3 
    END,
    timestamp DESC;

-- Customer isolation health view  
CREATE OR REPLACE VIEW isolation_health_summary AS
SELECT 
    DATE(timestamp) as test_date,
    COUNT(*) as total_tests,
    SUM(CASE WHEN isolation_verified THEN 1 ELSE 0 END) as passed_tests,
    SUM(violation_count) as total_violations,
    ROUND(
        (SUM(CASE WHEN isolation_verified THEN 1 ELSE 0 END) * 100.0) / COUNT(*), 
        2
    ) as isolation_success_rate
FROM isolation_validation_logs 
WHERE timestamp >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(timestamp)
ORDER BY test_date DESC;

-- Indexes for views performance
CREATE INDEX IF NOT EXISTS idx_memory_stats_current_date 
    ON customer_memory_stats (stats_date) 
    WHERE stats_date = CURRENT_DATE;

CREATE INDEX IF NOT EXISTS idx_memory_perf_recent 
    ON memory_performance_metrics (timestamp) 
    WHERE timestamp >= NOW() - INTERVAL '1 hour';

-- Comments for documentation
COMMENT ON TABLE customer_memory_audit IS 'Audit log for all customer memory operations and access';
COMMENT ON TABLE memory_performance_metrics IS 'Performance metrics for memory operations with SLA tracking';
COMMENT ON TABLE isolation_validation_logs IS 'Results of customer isolation validation tests';
COMMENT ON TABLE sla_violation_alerts IS 'SLA violation alerts and incident tracking';
COMMENT ON TABLE customer_memory_stats IS 'Aggregated daily statistics per customer for monitoring dashboards';

COMMENT ON VIEW current_sla_compliance IS 'Real-time SLA compliance status for all customers';
COMMENT ON VIEW recent_memory_operations IS 'Recent memory operations for debugging and monitoring';
COMMENT ON VIEW active_sla_alerts IS 'Active SLA violation alerts requiring attention';
COMMENT ON VIEW isolation_health_summary IS 'Customer isolation validation health over time';