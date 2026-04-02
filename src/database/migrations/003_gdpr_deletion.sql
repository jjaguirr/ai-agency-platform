-- Migration 003: GDPR Article 17 deletion audit + state tables
--
-- Moved from the now-removed src/memory/schema.sql. The Mem0/Qdrant/Neo4j
-- layer those tables originally accompanied is gone, but the customer
-- deletion pipeline (src/security/customer_deletion_pipeline.py) still
-- writes to these two tables and they must survive a customer cascade —
-- hence VARCHAR customer_id with no FK to customers(id).

CREATE TABLE IF NOT EXISTS gdpr_compliance_audit (
    id BIGSERIAL PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    action_data JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_gdpr_audit_customer ON gdpr_compliance_audit(customer_id);
CREATE INDEX IF NOT EXISTS idx_gdpr_audit_timestamp ON gdpr_compliance_audit(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_gdpr_audit_action ON gdpr_compliance_audit(action_type);

-- Customer deletion operation state tracker
-- Enables resumable/idempotent deletion across storage layers that don't share a transaction
CREATE TABLE IF NOT EXISTS customer_deletion_operations (
    deletion_id VARCHAR(64) PRIMARY KEY,
    customer_id VARCHAR(255) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requested_by VARCHAR(255),
    reason VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'verified')),
    -- Step completion state: { "redis": {"status": "completed", "result": {...}, "at": "..."}, ... }
    step_state JSONB NOT NULL DEFAULT '{}'::JSONB,
    dry_run_report JSONB,
    verification_result JSONB,
    error TEXT,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deletion_ops_customer ON customer_deletion_operations(customer_id);
CREATE INDEX IF NOT EXISTS idx_deletion_ops_status ON customer_deletion_operations(status) WHERE status != 'verified';
