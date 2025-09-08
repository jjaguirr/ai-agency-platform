-- AI Agency Platform - Phase 2 Database Schema Rollback
-- EA Orchestration System Rollback Script
-- Version: 2.0 - Phase 2 EA Evolution Rollback
-- Migration Rollback: 002_phase2_ea_orchestration_rollback
-- WARNING: This will remove Phase 2 features and data

-- ====================================================================
-- ROLLBACK VALIDATION & SAFETY CHECKS
-- ====================================================================

-- Verify that Phase 2 migration was applied
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '2.0.0') THEN
        RAISE EXCEPTION 'Phase 2 migration (2.0.0) was not found. Cannot rollback migration that was not applied.';
    END IF;
    
    RAISE NOTICE 'Phase 2 migration found. Proceeding with rollback...';
    RAISE WARNING 'THIS WILL PERMANENTLY DELETE ALL PHASE 2 DATA INCLUDING:';
    RAISE WARNING '- Customer personality preferences';
    RAISE WARNING '- Cross-channel conversation contexts'; 
    RAISE WARNING '- Personal brand metrics and goals';
    RAISE WARNING '- Voice interaction logs and performance data';
    RAISE WARNING 'This operation cannot be undone!';
END $$;

-- ====================================================================
-- DATA PRESERVATION (Optional - Enable if needed)
-- ====================================================================

-- Uncomment the following sections if you need to preserve data before rollback

/*
-- Create backup tables for data preservation
CREATE TABLE IF NOT EXISTS backup_customer_personality_preferences AS 
SELECT * FROM customer_personality_preferences;

CREATE TABLE IF NOT EXISTS backup_conversation_context AS 
SELECT * FROM conversation_context;

CREATE TABLE IF NOT EXISTS backup_personal_brand_metrics AS 
SELECT * FROM personal_brand_metrics;

CREATE TABLE IF NOT EXISTS backup_voice_interaction_logs AS 
SELECT * FROM voice_interaction_logs;

RAISE NOTICE 'Phase 2 data backed up to backup_* tables';
*/

-- ====================================================================
-- REMOVE PHASE 2 VIEWS
-- ====================================================================

DROP VIEW IF EXISTS voice_quality_monitor CASCADE;
DROP VIEW IF EXISTS brand_performance_trends CASCADE;
DROP VIEW IF EXISTS cross_channel_context_health CASCADE;
DROP VIEW IF EXISTS ea_orchestration_dashboard CASCADE;

RAISE NOTICE 'Phase 2 views removed';

-- ====================================================================
-- REMOVE PHASE 2 TRIGGERS AND FUNCTIONS
-- ====================================================================

-- Remove voice performance aggregation trigger
DROP TRIGGER IF EXISTS trigger_voice_performance_summary ON voice_interaction_logs;
DROP FUNCTION IF EXISTS update_voice_performance_summary() CASCADE;

-- Remove context freshness trigger
DROP TRIGGER IF EXISTS trigger_context_freshness_update ON conversation_context;
DROP FUNCTION IF EXISTS update_context_freshness() CASCADE;

-- Remove timestamp update triggers for Phase 2 tables
DROP TRIGGER IF EXISTS update_voice_summary_updated_at ON voice_performance_summary;
DROP TRIGGER IF EXISTS update_brand_goals_updated_at ON personal_brand_goals;
DROP TRIGGER IF EXISTS update_brand_metrics_updated_at ON personal_brand_metrics;
DROP TRIGGER IF EXISTS update_conversation_context_updated_at ON conversation_context;
DROP TRIGGER IF EXISTS update_personality_preferences_updated_at ON customer_personality_preferences;

RAISE NOTICE 'Phase 2 triggers and functions removed';

-- ====================================================================
-- REMOVE PHASE 2 TABLES (In dependency order)
-- ====================================================================

-- Remove dependent tables first
DROP TABLE IF EXISTS conversation_context_transitions CASCADE;
DROP TABLE IF EXISTS voice_performance_summary CASCADE;
DROP TABLE IF EXISTS personal_brand_goals CASCADE;
DROP TABLE IF EXISTS personal_brand_metrics CASCADE;
DROP TABLE IF EXISTS voice_interaction_logs CASCADE;
DROP TABLE IF EXISTS conversation_context CASCADE;
DROP TABLE IF EXISTS customer_personality_preferences CASCADE;

RAISE NOTICE 'Phase 2 tables removed';

-- ====================================================================
-- REMOVE PHASE 2 INDEXES
-- ====================================================================

-- Note: Indexes are automatically removed when tables are dropped
-- This section documents what indexes were removed for reference

/*
Phase 2 Indexes Removed:
- idx_personality_customer_id
- idx_personality_communication_style
- idx_personality_language
- idx_conversation_context_customer_id
- idx_conversation_context_id
- idx_conversation_channel_type
- idx_conversation_importance
- idx_conversation_active
- idx_conversation_context_embedding
- idx_context_transitions_customer_time
- idx_context_transitions_context_id
- idx_brand_metrics_customer_type
- idx_brand_metrics_performance
- idx_brand_metrics_period
- idx_brand_metrics_source
- idx_brand_goals_customer_status
- idx_brand_goals_completion
- idx_voice_logs_customer_time
- idx_voice_logs_interaction_id
- idx_voice_logs_language
- idx_voice_logs_performance
- idx_voice_logs_session_type
- idx_voice_summary_customer_date
- idx_voice_summary_performance
*/

RAISE NOTICE 'Phase 2 indexes automatically removed with tables';

-- ====================================================================
-- REVOKE PHASE 2 PERMISSIONS
-- ====================================================================

-- Permissions are automatically revoked when objects are dropped
RAISE NOTICE 'Phase 2 permissions automatically revoked with objects';

-- ====================================================================
-- UPDATE MIGRATION RECORD
-- ====================================================================

-- Remove Phase 2 migration record
DELETE FROM schema_migrations WHERE version = '2.0.0';

RAISE NOTICE 'Phase 2 migration record removed from schema_migrations';

-- ====================================================================
-- ROLLBACK COMPLETION AND VALIDATION
-- ====================================================================

-- Validate rollback completion
DO $$
DECLARE
    table_count INTEGER;
    view_count INTEGER;
    migration_exists BOOLEAN;
BEGIN
    -- Verify Phase 2 tables are gone
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables 
    WHERE table_name IN (
        'customer_personality_preferences',
        'conversation_context', 
        'conversation_context_transitions',
        'personal_brand_metrics',
        'personal_brand_goals', 
        'voice_interaction_logs',
        'voice_performance_summary'
    );
    
    IF table_count > 0 THEN
        RAISE EXCEPTION 'Rollback incomplete: % Phase 2 tables still exist', table_count;
    END IF;
    
    -- Verify Phase 2 views are gone
    SELECT COUNT(*) INTO view_count
    FROM information_schema.views 
    WHERE table_name IN (
        'ea_orchestration_dashboard',
        'cross_channel_context_health', 
        'brand_performance_trends',
        'voice_quality_monitor'
    );
    
    IF view_count > 0 THEN
        RAISE EXCEPTION 'Rollback incomplete: % Phase 2 views still exist', view_count;
    END IF;
    
    -- Verify migration record is gone
    SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '2.0.0') INTO migration_exists;
    
    IF migration_exists THEN
        RAISE EXCEPTION 'Rollback incomplete: Migration record still exists';
    END IF;
    
    RAISE NOTICE '================================================================================';
    RAISE NOTICE 'PHASE 2 ROLLBACK COMPLETED SUCCESSFULLY!';
    RAISE NOTICE '================================================================================';
    RAISE NOTICE 'Database has been rolled back to Phase 1 state';
    RAISE NOTICE 'All Phase 2 features and data have been removed';
    RAISE NOTICE 'System is ready to return to Phase 1 operations';
    RAISE NOTICE '================================================================================';
END $$;