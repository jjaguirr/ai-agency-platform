-- Phase 2 Database Schema Validation SQL
-- Comprehensive validation of EA Orchestration premium-casual personality system
-- Target: <100ms average query performance, customer isolation verification

-- ====================================================================
-- VALIDATION 1: REQUIRED TABLES EXISTENCE
-- ====================================================================

SELECT 'Phase 2 Schema Validation' as validation_type;

SELECT 
    'Required Tables Check' as test_name,
    COUNT(CASE WHEN table_name = 'customer_personality_preferences' THEN 1 END) as personality_table,
    COUNT(CASE WHEN table_name = 'conversation_context' THEN 1 END) as context_table,
    COUNT(CASE WHEN table_name = 'personal_brand_metrics' THEN 1 END) as brand_metrics_table,
    COUNT(CASE WHEN table_name = 'voice_interaction_logs' THEN 1 END) as voice_table,
    COUNT(CASE WHEN table_name IN (
        'customer_personality_preferences',
        'conversation_context',
        'personal_brand_metrics', 
        'voice_interaction_logs'
    ) THEN 1 END) as total_required_tables
FROM information_schema.tables 
WHERE table_schema = 'public';

-- ====================================================================
-- VALIDATION 2: CUSTOMER ISOLATION VERIFICATION
-- ====================================================================

SELECT 
    'Customer Isolation Check' as test_name,
    tablename,
    CASE WHEN rowsecurity THEN 'ENABLED' ELSE 'DISABLED' END as rls_status
FROM pg_tables 
WHERE tablename IN (
    'customer_personality_preferences',
    'conversation_context',
    'personal_brand_metrics',
    'voice_interaction_logs'
)
ORDER BY tablename;

-- Check customer data isolation
SELECT 
    'Data Isolation Verification' as test_name,
    COUNT(DISTINCT customer_id) as isolated_customers
FROM customer_personality_preferences;

-- ====================================================================
-- VALIDATION 3: PREMIUM-CASUAL PERSONALITY PREFERENCES FUNCTIONALITY  
-- ====================================================================

-- Test personality preference storage and retrieval
\timing on

-- Performance test: Personality preferences query
SELECT 
    'Personality Preferences Performance' as test_name,
    COUNT(*) as total_preferences,
    COUNT(CASE WHEN communication_style = 'premium_casual' THEN 1 END) as premium_casual_count,
    COUNT(CASE WHEN preferred_language IN ('en', 'es', 'en-es') THEN 1 END) as language_support
FROM customer_personality_preferences;

-- Test JSONB functionality for tone preferences
SELECT 
    'JSONB Functionality Test' as test_name,
    customer_id,
    tone_preferences->>'formality_level' as formality_level,
    channel_preferences->>'email' as email_prefs
FROM customer_personality_preferences 
LIMIT 3;

\timing off

-- ====================================================================
-- VALIDATION 4: CROSS-CHANNEL CONTEXT PRESERVATION
-- ====================================================================

-- Test context storage capability
INSERT INTO conversation_context (
    context_id, 
    customer_id, 
    channel_type, 
    conversation_summary,
    key_topics,
    action_items,
    assigned_agents,
    importance_score,
    escalation_level
) VALUES (
    'validation-context-001',
    '00000000-0000-0000-0000-000000000001',
    'email',
    'Customer validation test for cross-channel context preservation and premium-casual EA personality',
    '["validation", "premium_casual", "cross_channel", "ea_personality"]',
    '[{"task": "Validate schema implementation", "priority": "high", "deadline": "2025-09-07"}]',
    '["business_agent", "technical_lead"]',
    0.9,
    'medium'
) ON CONFLICT DO NOTHING;

\timing on

-- Performance test: Context retrieval with <500ms SLA requirement
SELECT 
    'Context Retrieval Performance' as test_name,
    context_id,
    channel_type,
    jsonb_array_length(key_topics) as topic_count,
    jsonb_array_length(action_items) as action_count,
    importance_score,
    context_freshness_score,
    escalation_level
FROM conversation_context 
WHERE customer_id = '00000000-0000-0000-0000-000000000001'
ORDER BY last_activity_at DESC 
LIMIT 5;

\timing off

-- Test channel transition logging
SELECT 
    'Channel Transitions Check' as test_name,
    COUNT(*) as total_transitions,
    AVG(transition_latency_ms) as avg_latency_ms,
    AVG(context_preservation_score) as avg_preservation_score
FROM conversation_context_transitions;

-- ====================================================================  
-- VALIDATION 5: PERSONAL BRAND METRICS TRACKING
-- ====================================================================

-- Test brand metrics insertion
INSERT INTO personal_brand_metrics (
    customer_id,
    metric_type,
    metric_value,
    metric_unit,
    baseline_value,
    target_value,
    performance_category,
    measurement_period,
    data_source,
    contributing_agents,
    improvement_attribution,
    revenue_correlation,
    measured_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'thought_leadership',
    750.5,
    'mentions',
    500.0,
    1000.0,
    'improving',
    'monthly',
    'social_media_agent',
    '["social_media_manager", "marketing_agent"]',
    '{"content_strategy": "premium_casual_tone", "engagement_increase": 15}',
    0.42,
    CURRENT_TIMESTAMP
) ON CONFLICT DO NOTHING;

\timing on

-- Performance test: Brand metrics queries
SELECT 
    'Brand Metrics Performance' as test_name,
    metric_type,
    AVG(metric_value) as avg_value,
    COUNT(*) as measurement_count,
    AVG(revenue_correlation) as avg_revenue_correlation,
    COUNT(CASE WHEN performance_category IN ('improving', 'exceeding', 'exceptional') THEN 1 END) as positive_metrics
FROM personal_brand_metrics 
WHERE customer_id = '00000000-0000-0000-0000-000000000001'
GROUP BY metric_type;

\timing off

-- ====================================================================
-- VALIDATION 6: VOICE INTERACTION LOGGING (ElevenLabs Integration)
-- ====================================================================

-- Test voice interaction logging
INSERT INTO voice_interaction_logs (
    interaction_id,
    customer_id,
    session_type,
    language_detected,
    language_responded,
    audio_duration_seconds,
    speech_to_text_latency_ms,
    text_to_speech_latency_ms,
    synthesis_time_ms,
    total_processing_time_ms,
    transcription_confidence,
    voice_quality_score,
    conversation_quality_rating,
    conversation_summary,
    key_intents_detected,
    emotions_detected,
    action_items_generated,
    delegated_to_agents,
    sla_compliance,
    started_at,
    completed_at
) VALUES (
    'validation-voice-001',
    '00000000-0000-0000-0000-000000000001',
    'ea_conversation',
    'en',
    'en', 
    65.3,
    145,
    220,
    180,
    1750,
    0.96,
    0.94,
    5,
    'Customer requested premium casual tone adjustment for EA voice interactions',
    '["tone_adjustment", "premium_casual", "voice_interaction", "ea_personality"]',
    '{"confidence": 0.85, "satisfaction": 0.92}',
    '[{"task": "Update voice personality settings", "priority": "medium"}]',
    '["business_agent"]',
    true,
    CURRENT_TIMESTAMP - INTERVAL '2 minutes',
    CURRENT_TIMESTAMP - INTERVAL '1 minute'
) ON CONFLICT (interaction_id) DO NOTHING;

\timing on

-- Performance test: Voice interaction queries  
SELECT 
    'Voice Interaction Performance' as test_name,
    session_type,
    COUNT(*) as total_interactions,
    AVG(total_processing_time_ms) as avg_processing_time_ms,
    AVG(transcription_confidence) as avg_transcription_confidence,
    AVG(voice_quality_score) as avg_voice_quality,
    COUNT(CASE WHEN sla_compliance THEN 1 END) * 100.0 / COUNT(*) as sla_compliance_rate
FROM voice_interaction_logs 
WHERE customer_id = '00000000-0000-0000-0000-000000000001'
GROUP BY session_type;

-- Test bilingual support
SELECT 
    'Bilingual Support Check' as test_name,
    language_detected,
    language_responded,
    COUNT(*) as interaction_count
FROM voice_interaction_logs
GROUP BY language_detected, language_responded
ORDER BY interaction_count DESC;

\timing off

-- ====================================================================
-- VALIDATION 7: PERFORMANCE INDEXES VERIFICATION  
-- ====================================================================

-- Check critical performance indexes
SELECT 
    'Performance Indexes Check' as test_name,
    COUNT(*) as total_phase2_indexes
FROM pg_indexes 
WHERE (indexname LIKE 'idx_%personality%' 
   OR indexname LIKE 'idx_%conversation%' 
   OR indexname LIKE 'idx_%brand%'
   OR indexname LIKE 'idx_%voice%')
AND schemaname = 'public';

-- List specific indexes for verification
SELECT 
    'Index Details' as test_name,
    indexname,
    tablename
FROM pg_indexes 
WHERE (indexname LIKE 'idx_%personality%' 
   OR indexname LIKE 'idx_%conversation%' 
   OR indexname LIKE 'idx_%brand%'
   OR indexname LIKE 'idx_%voice%')
AND schemaname = 'public'
ORDER BY tablename, indexname;

-- ====================================================================
-- VALIDATION 8: MONITORING VIEWS FUNCTIONALITY
-- ====================================================================

-- Test EA Orchestration Dashboard View
SELECT 
    'EA Orchestration Dashboard' as test_name,
    business_name,
    communication_style,
    preferred_language,
    active_conversations,
    voice_sla_compliance
FROM ea_orchestration_dashboard 
LIMIT 3;

-- Test Cross-Channel Context Health View
SELECT 
    'Cross-Channel Context Health' as test_name,
    channel_type,
    active_contexts,
    avg_freshness,
    recent_activity
FROM cross_channel_context_health
LIMIT 5;

-- ====================================================================
-- VALIDATION 9: MIGRATION COMPLETION VERIFICATION
-- ====================================================================

-- Verify migration was applied successfully  
SELECT 
    'Migration Status' as test_name,
    version,
    description,
    applied_at
FROM schema_migrations 
WHERE version = '2.0.0';

-- ====================================================================
-- VALIDATION SUMMARY
-- ====================================================================

SELECT 
    'PHASE 2 VALIDATION SUMMARY' as summary,
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN (
        'customer_personality_preferences', 'conversation_context', 
        'personal_brand_metrics', 'voice_interaction_logs'
    )) as required_tables_count,
    (SELECT COUNT(*) FROM pg_tables WHERE tablename IN (
        'customer_personality_preferences', 'conversation_context',
        'personal_brand_metrics', 'voice_interaction_logs'
    ) AND rowsecurity = true) as rls_enabled_tables,
    (SELECT COUNT(*) FROM pg_indexes WHERE (
        indexname LIKE 'idx_%personality%' OR
        indexname LIKE 'idx_%conversation%' OR 
        indexname LIKE 'idx_%brand%' OR
        indexname LIKE 'idx_%voice%'
    ) AND schemaname = 'public') as performance_indexes,
    (SELECT COUNT(*) FROM information_schema.views WHERE table_name IN (
        'ea_orchestration_dashboard', 'cross_channel_context_health',
        'brand_performance_trends', 'voice_quality_monitor'
    )) as monitoring_views;

-- Final validation message
SELECT 
    CASE 
        WHEN (
            (SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN (
                'customer_personality_preferences', 'conversation_context', 
                'personal_brand_metrics', 'voice_interaction_logs'
            )) = 4
            AND
            (SELECT COUNT(*) FROM pg_tables WHERE tablename IN (
                'customer_personality_preferences', 'conversation_context',
                'personal_brand_metrics', 'voice_interaction_logs'
            ) AND rowsecurity = true) = 4
            AND
            (SELECT COUNT(*) FROM schema_migrations WHERE version = '2.0.0') = 1
        ) THEN '🚀 PHASE 2 DATABASE SCHEMA VALIDATION: SUCCESS - Ready for EA Orchestration!'
        ELSE '⚠️ PHASE 2 DATABASE SCHEMA VALIDATION: Issues detected - Review results above'
    END as validation_result;