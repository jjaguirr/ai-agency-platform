-- AI Agency Platform - Phase 2 Database Schema Updates (Vector Extension Free)
-- EA Orchestration System with Premium-Casual Personality and Cross-Channel Context
-- Version: 2.0 - Phase 2 EA Evolution (Development Version - No Vector Extensions)
-- Migration: 002_phase2_ea_orchestration_no_vector
-- Performance Target: <100ms average query performance

-- ====================================================================
-- MIGRATION METADATA & VALIDATION
-- ====================================================================

-- Check if this migration has already been applied
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM schema_migrations WHERE version = '2.0.0') THEN
        RAISE EXCEPTION 'Migration 2.0.0 has already been applied. Aborting to prevent duplicate execution.';
    END IF;
END $$;

-- ====================================================================
-- PHASE 2: CUSTOMER PERSONALITY & COMMUNICATION PREFERENCES
-- ====================================================================

-- Customer personality preferences for premium-casual EA evolution
CREATE TABLE IF NOT EXISTS customer_personality_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    
    -- Premium-casual personality settings
    communication_style VARCHAR(100) DEFAULT 'premium_casual' CHECK (communication_style IN ('professional', 'casual', 'premium_casual', 'formal', 'friendly')),
    tone_preferences JSONB DEFAULT '{
        "formality_level": "premium_casual",
        "humor_style": "light_professional", 
        "response_length": "concise_detailed",
        "technical_complexity": "business_appropriate"
    }'::JSONB,
    
    -- Channel-specific preferences
    channel_preferences JSONB DEFAULT '{
        "email": {"preferred": true, "response_time": "within_1_hour"},
        "whatsapp": {"preferred": true, "response_time": "within_5_minutes"},
        "voice": {"preferred": true, "language": "en", "accent": "neutral"}
    }'::JSONB,
    
    -- EA delegation preferences
    delegation_preferences JSONB DEFAULT '{
        "auto_delegate_social_media": true,
        "auto_delegate_finance": true,
        "auto_delegate_marketing": false,
        "requires_approval_threshold": "high_impact"
    }'::JSONB,
    
    -- Personalization settings
    preferred_language VARCHAR(10) DEFAULT 'en' CHECK (preferred_language IN ('en', 'es', 'en-es')),
    timezone VARCHAR(50) DEFAULT 'UTC',
    business_hours JSONB DEFAULT '{
        "start": "09:00",
        "end": "17:00", 
        "days": ["monday", "tuesday", "wednesday", "thursday", "friday"]
    }'::JSONB,
    
    -- Version tracking for personality evolution
    version_number INTEGER DEFAULT 1,
    learning_enabled BOOLEAN DEFAULT true,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure one personality profile per customer
    UNIQUE(customer_id)
);

-- ====================================================================
-- PHASE 2: CROSS-CHANNEL CONVERSATION CONTEXT MANAGEMENT  
-- ====================================================================

-- Cross-channel conversation context with <500ms recall SLA
CREATE TABLE IF NOT EXISTS conversation_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    context_id VARCHAR(255) NOT NULL, -- Unified context ID across channels
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    
    -- Channel information
    channel_type VARCHAR(50) NOT NULL CHECK (channel_type IN ('email', 'whatsapp', 'voice', 'web', 'sms', 'telegram')),
    channel_thread_id VARCHAR(255), -- Platform-specific thread/conversation ID
    
    -- Context content (no vector embeddings for dev version)
    conversation_summary TEXT NOT NULL,
    key_topics JSONB DEFAULT '[]'::JSONB, -- Array of key discussion topics
    action_items JSONB DEFAULT '[]'::JSONB, -- Outstanding action items
    decisions_made JSONB DEFAULT '[]'::JSONB, -- Decisions from conversation
    
    -- Context metadata
    context_type VARCHAR(50) DEFAULT 'ongoing' CHECK (context_type IN ('ongoing', 'completed', 'archived', 'escalated')),
    importance_score FLOAT DEFAULT 0.5 CHECK (importance_score BETWEEN 0 AND 1),
    sentiment_analysis JSONB DEFAULT '{}'::JSONB,
    
    -- EA orchestration context
    assigned_agents JSONB DEFAULT '[]'::JSONB, -- Which specialist agents are involved
    delegation_history JSONB DEFAULT '[]'::JSONB, -- Track EA delegation decisions
    escalation_level VARCHAR(50) DEFAULT 'none' CHECK (escalation_level IN ('none', 'low', 'medium', 'high', 'urgent')),
    
    -- Performance tracking
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0,
    context_freshness_score FLOAT DEFAULT 1.0, -- Degrades over time
    
    -- Text-based search optimization (instead of vector)
    search_keywords TEXT, -- Extracted keywords for full-text search
    
    -- Temporal tracking
    conversation_started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '30 days'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Conversation context transitions (for channel handoffs)
CREATE TABLE IF NOT EXISTS conversation_context_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    context_id VARCHAR(255) NOT NULL,
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    
    -- Transition details
    from_channel VARCHAR(50) NOT NULL,
    to_channel VARCHAR(50) NOT NULL,
    transition_reason VARCHAR(100) NOT NULL,
    
    -- Context preservation
    preserved_context JSONB NOT NULL, -- What context was carried over
    lost_context JSONB DEFAULT '[]'::JSONB, -- What couldn't be preserved
    
    -- Performance metrics
    transition_latency_ms INTEGER, -- Time taken for context handoff
    context_preservation_score FLOAT, -- How much context was preserved (0-1)
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign key reference (no formal FK due to compound key complexity)
    CHECK (context_id IS NOT NULL AND customer_id IS NOT NULL)
);

-- ====================================================================
-- PHASE 2: PERSONAL BRAND METRICS & ADVANCEMENT TRACKING
-- ====================================================================

-- Personal brand metrics tracking for customer success measurement
CREATE TABLE IF NOT EXISTS personal_brand_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    
    -- Metric classification
    metric_type VARCHAR(100) NOT NULL CHECK (metric_type IN (
        'social_media_engagement', 'thought_leadership', 'network_growth', 
        'content_performance', 'brand_mentions', 'industry_recognition',
        'speaking_opportunities', 'media_coverage', 'influence_score',
        'reputation_sentiment', 'competitor_comparison', 'market_share'
    )),
    
    -- Metric values and context
    metric_value DECIMAL(12,4) NOT NULL,
    metric_unit VARCHAR(50) NOT NULL, -- followers, mentions, percentage, score, etc.
    baseline_value DECIMAL(12,4), -- Starting point for comparison
    target_value DECIMAL(12,4), -- Goal target
    
    -- Performance categorization
    performance_category VARCHAR(50) DEFAULT 'baseline' CHECK (performance_category IN (
        'declining', 'stagnant', 'baseline', 'improving', 'exceeding', 'exceptional'
    )),
    
    -- Temporal and contextual data
    measurement_period VARCHAR(50) NOT NULL, -- daily, weekly, monthly, quarterly
    data_source VARCHAR(100) NOT NULL, -- social_media_agent, marketing_agent, manual, api_import
    confidence_score FLOAT DEFAULT 1.0 CHECK (confidence_score BETWEEN 0 AND 1),
    
    -- Attribution to EA and specialist agents
    contributing_agents JSONB DEFAULT '[]'::JSONB, -- Which agents contributed to this metric
    improvement_attribution JSONB DEFAULT '{}'::JSONB, -- What actions led to improvement
    
    -- Business impact correlation
    revenue_correlation DECIMAL(8,4), -- Correlation with revenue changes
    customer_acquisition_impact INTEGER, -- New customers attributed to brand improvement
    
    -- Metadata
    external_reference_id VARCHAR(255), -- Reference to external system measurement
    measurement_metadata JSONB DEFAULT '{}'::JSONB,
    
    measured_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Personal brand goal tracking and milestones
CREATE TABLE IF NOT EXISTS personal_brand_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    
    -- Goal definition
    goal_name VARCHAR(255) NOT NULL,
    goal_description TEXT,
    goal_category VARCHAR(100) NOT NULL,
    
    -- Target metrics
    target_metrics JSONB NOT NULL, -- Array of target metric achievements
    current_progress JSONB DEFAULT '{}'::JSONB, -- Current progress toward goals
    completion_percentage DECIMAL(5,2) DEFAULT 0.00,
    
    -- Timeline
    target_completion_date TIMESTAMP WITH TIME ZONE,
    estimated_completion_date TIMESTAMP WITH TIME ZONE,
    actual_completion_date TIMESTAMP WITH TIME ZONE,
    
    -- EA orchestration
    assigned_agents JSONB DEFAULT '[]'::JSONB, -- Which agents are working on this goal
    recommended_actions JSONB DEFAULT '[]'::JSONB, -- EA recommended actions
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('draft', 'active', 'on_hold', 'completed', 'cancelled')),
    priority_level VARCHAR(50) DEFAULT 'medium' CHECK (priority_level IN ('low', 'medium', 'high', 'urgent')),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ====================================================================
-- PHASE 2: VOICE INTERACTION TRACKING (ElevenLabs Integration)
-- ====================================================================

-- Voice interaction logs for bilingual EA and performance analytics
CREATE TABLE IF NOT EXISTS voice_interaction_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id VARCHAR(255) NOT NULL UNIQUE, -- ElevenLabs session ID
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    
    -- Voice session details  
    session_type VARCHAR(50) NOT NULL CHECK (session_type IN ('ea_conversation', 'agent_briefing', 'status_update', 'emergency_alert')),
    language_detected VARCHAR(10) NOT NULL CHECK (language_detected IN ('en', 'es', 'en-es')),
    language_responded VARCHAR(10) NOT NULL CHECK (language_responded IN ('en', 'es', 'en-es')),
    
    -- Audio processing metrics
    audio_duration_seconds DECIMAL(8,3) NOT NULL,
    speech_to_text_latency_ms INTEGER NOT NULL,
    text_to_speech_latency_ms INTEGER NOT NULL,
    synthesis_time_ms INTEGER NOT NULL,
    total_processing_time_ms INTEGER NOT NULL,
    
    -- Quality metrics
    transcription_confidence DECIMAL(5,4), -- STT confidence score
    voice_quality_score DECIMAL(5,4), -- TTS quality assessment
    conversation_quality_rating INTEGER CHECK (conversation_quality_rating BETWEEN 1 AND 5),
    
    -- Content analysis
    conversation_summary TEXT,
    key_intents_detected JSONB DEFAULT '[]'::JSONB,
    emotions_detected JSONB DEFAULT '{}'::JSONB,
    action_items_generated JSONB DEFAULT '[]'::JSONB,
    
    -- Technical performance
    connection_quality VARCHAR(50) CHECK (connection_quality IN ('excellent', 'good', 'fair', 'poor')),
    audio_interruptions INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_details JSONB DEFAULT '[]'::JSONB,
    
    -- Billing and cost tracking
    elevenlabs_character_count INTEGER,
    estimated_cost_usd DECIMAL(8,6),
    billing_tier VARCHAR(50), -- ElevenLabs pricing tier used
    
    -- EA orchestration context
    delegated_to_agents JSONB DEFAULT '[]'::JSONB, -- Which agents were mentioned/assigned
    follow_up_required BOOLEAN DEFAULT false,
    escalation_triggered BOOLEAN DEFAULT false,
    
    -- Performance benchmarking
    sla_compliance BOOLEAN DEFAULT true, -- Met <2s response SLA
    benchmark_comparison JSONB DEFAULT '{}'::JSONB, -- Comparison to performance targets
    
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Voice interaction performance aggregations (for monitoring dashboard)
CREATE TABLE IF NOT EXISTS voice_performance_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    summary_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Volume metrics
    total_interactions INTEGER DEFAULT 0,
    total_audio_minutes DECIMAL(10,2) DEFAULT 0,
    peak_concurrent_sessions INTEGER DEFAULT 0,
    
    -- Performance metrics
    avg_response_time_ms DECIMAL(8,2),
    p95_response_time_ms DECIMAL(8,2),
    p99_response_time_ms DECIMAL(8,2),
    sla_compliance_percentage DECIMAL(5,2),
    
    -- Quality metrics
    avg_transcription_confidence DECIMAL(5,4),
    avg_voice_quality_score DECIMAL(5,4),
    avg_conversation_rating DECIMAL(3,2),
    error_rate_percentage DECIMAL(5,2),
    
    -- Language distribution
    english_interactions INTEGER DEFAULT 0,
    spanish_interactions INTEGER DEFAULT 0,
    bilingual_interactions INTEGER DEFAULT 0,
    
    -- Cost tracking
    total_cost_usd DECIMAL(10,6) DEFAULT 0,
    cost_per_interaction DECIMAL(8,6),
    cost_per_minute DECIMAL(8,6),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique constraint for daily summaries
    UNIQUE(customer_id, summary_date)
);

-- ====================================================================
-- PHASE 2: PERFORMANCE INDEXES (Optimized for <100ms queries)
-- ====================================================================

-- Customer personality preferences indexes
CREATE INDEX IF NOT EXISTS idx_personality_customer_id ON customer_personality_preferences(customer_id);
CREATE INDEX IF NOT EXISTS idx_personality_communication_style ON customer_personality_preferences(communication_style);
CREATE INDEX IF NOT EXISTS idx_personality_language ON customer_personality_preferences(preferred_language);

-- Conversation context performance indexes (Critical for <500ms SLA)
CREATE INDEX IF NOT EXISTS idx_conversation_context_customer_id ON conversation_context(customer_id, last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_context_id ON conversation_context(context_id, customer_id);
CREATE INDEX IF NOT EXISTS idx_conversation_channel_type ON conversation_context(channel_type, customer_id);
CREATE INDEX IF NOT EXISTS idx_conversation_importance ON conversation_context(importance_score DESC, customer_id);
CREATE INDEX IF NOT EXISTS idx_conversation_active ON conversation_context(customer_id, context_type, expires_at);

-- Full-text search index for conversation context (instead of vector)
CREATE INDEX IF NOT EXISTS idx_conversation_search_keywords ON conversation_context USING gin(to_tsvector('english', search_keywords));
CREATE INDEX IF NOT EXISTS idx_conversation_summary_search ON conversation_context USING gin(to_tsvector('english', conversation_summary));

-- Context transitions performance
CREATE INDEX IF NOT EXISTS idx_context_transitions_customer_time ON conversation_context_transitions(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_context_transitions_context_id ON conversation_context_transitions(context_id);

-- Personal brand metrics indexes
CREATE INDEX IF NOT EXISTS idx_brand_metrics_customer_type ON personal_brand_metrics(customer_id, metric_type, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_brand_metrics_performance ON personal_brand_metrics(performance_category, customer_id);
CREATE INDEX IF NOT EXISTS idx_brand_metrics_period ON personal_brand_metrics(measurement_period, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_brand_metrics_source ON personal_brand_metrics(data_source, customer_id);

-- Personal brand goals indexes
CREATE INDEX IF NOT EXISTS idx_brand_goals_customer_status ON personal_brand_goals(customer_id, status, priority_level);
CREATE INDEX IF NOT EXISTS idx_brand_goals_completion ON personal_brand_goals(target_completion_date, status);

-- Voice interaction performance indexes (Critical for real-time analytics)
CREATE INDEX IF NOT EXISTS idx_voice_logs_customer_time ON voice_interaction_logs(customer_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_voice_logs_interaction_id ON voice_interaction_logs(interaction_id);
CREATE INDEX IF NOT EXISTS idx_voice_logs_language ON voice_interaction_logs(language_detected, customer_id);
CREATE INDEX IF NOT EXISTS idx_voice_logs_performance ON voice_interaction_logs(total_processing_time_ms, sla_compliance);
CREATE INDEX IF NOT EXISTS idx_voice_logs_session_type ON voice_interaction_logs(session_type, customer_id, started_at DESC);

-- Voice performance summary indexes
CREATE INDEX IF NOT EXISTS idx_voice_summary_customer_date ON voice_performance_summary(customer_id, summary_date DESC);
CREATE INDEX IF NOT EXISTS idx_voice_summary_performance ON voice_performance_summary(sla_compliance_percentage, summary_date DESC);

-- ====================================================================
-- ROW LEVEL SECURITY FOR PHASE 2 TABLES
-- ====================================================================

-- Enable RLS on all new Phase 2 tables for customer isolation
ALTER TABLE customer_personality_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_context_transitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE personal_brand_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE personal_brand_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE voice_interaction_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE voice_performance_summary ENABLE ROW LEVEL SECURITY;

-- ====================================================================
-- TRIGGERS FOR AUTOMATION AND PERFORMANCE
-- ====================================================================

-- Update triggers for timestamp management
CREATE TRIGGER update_personality_preferences_updated_at 
    BEFORE UPDATE ON customer_personality_preferences 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_context_updated_at 
    BEFORE UPDATE ON conversation_context 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_brand_metrics_updated_at 
    BEFORE UPDATE ON personal_brand_metrics 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_brand_goals_updated_at 
    BEFORE UPDATE ON personal_brand_goals 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_voice_summary_updated_at 
    BEFORE UPDATE ON voice_performance_summary 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Context freshness decay function
CREATE OR REPLACE FUNCTION update_context_freshness()
RETURNS TRIGGER AS $$
BEGIN
    -- Update context freshness based on time since last access
    NEW.context_freshness_score = GREATEST(
        0.1, -- Minimum freshness
        1.0 - (EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - NEW.last_accessed)) / 2592000.0) -- 30 day decay
    );
    
    -- Update access tracking
    NEW.access_count = OLD.access_count + 1;
    NEW.last_accessed = CURRENT_TIMESTAMP;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_context_freshness_update
    BEFORE UPDATE ON conversation_context
    FOR EACH ROW 
    WHEN (NEW.last_accessed > OLD.last_accessed)
    EXECUTE FUNCTION update_context_freshness();

-- Voice performance aggregation trigger
CREATE OR REPLACE FUNCTION update_voice_performance_summary()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO voice_performance_summary (
        customer_id,
        summary_date,
        total_interactions,
        total_audio_minutes,
        avg_response_time_ms,
        sla_compliance_percentage,
        avg_transcription_confidence,
        avg_voice_quality_score,
        english_interactions,
        spanish_interactions,
        bilingual_interactions,
        total_cost_usd
    )
    VALUES (
        NEW.customer_id,
        CURRENT_DATE,
        1,
        NEW.audio_duration_seconds / 60.0,
        NEW.total_processing_time_ms,
        CASE WHEN NEW.sla_compliance THEN 100.0 ELSE 0.0 END,
        NEW.transcription_confidence,
        NEW.voice_quality_score,
        CASE WHEN NEW.language_detected = 'en' THEN 1 ELSE 0 END,
        CASE WHEN NEW.language_detected = 'es' THEN 1 ELSE 0 END,
        CASE WHEN NEW.language_detected = 'en-es' THEN 1 ELSE 0 END,
        NEW.estimated_cost_usd
    )
    ON CONFLICT (customer_id, summary_date)
    DO UPDATE SET
        total_interactions = voice_performance_summary.total_interactions + 1,
        total_audio_minutes = voice_performance_summary.total_audio_minutes + (NEW.audio_duration_seconds / 60.0),
        avg_response_time_ms = (
            (voice_performance_summary.avg_response_time_ms * voice_performance_summary.total_interactions + NEW.total_processing_time_ms) /
            (voice_performance_summary.total_interactions + 1)
        ),
        sla_compliance_percentage = (
            ((voice_performance_summary.sla_compliance_percentage * voice_performance_summary.total_interactions / 100.0) + 
             CASE WHEN NEW.sla_compliance THEN 1 ELSE 0 END) * 100.0
        ) / (voice_performance_summary.total_interactions + 1),
        avg_transcription_confidence = (
            (voice_performance_summary.avg_transcription_confidence * voice_performance_summary.total_interactions + NEW.transcription_confidence) /
            (voice_performance_summary.total_interactions + 1)
        ),
        avg_voice_quality_score = (
            (voice_performance_summary.avg_voice_quality_score * voice_performance_summary.total_interactions + NEW.voice_quality_score) /
            (voice_performance_summary.total_interactions + 1)
        ),
        english_interactions = voice_performance_summary.english_interactions + 
            CASE WHEN NEW.language_detected = 'en' THEN 1 ELSE 0 END,
        spanish_interactions = voice_performance_summary.spanish_interactions + 
            CASE WHEN NEW.language_detected = 'es' THEN 1 ELSE 0 END,
        bilingual_interactions = voice_performance_summary.bilingual_interactions + 
            CASE WHEN NEW.language_detected = 'en-es' THEN 1 ELSE 0 END,
        total_cost_usd = voice_performance_summary.total_cost_usd + NEW.estimated_cost_usd,
        updated_at = CURRENT_TIMESTAMP;
        
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_voice_performance_summary
    AFTER INSERT ON voice_interaction_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_voice_performance_summary();

-- ====================================================================
-- PHASE 2 VIEWS FOR PERFORMANCE AND MONITORING
-- ====================================================================

-- EA Orchestration Performance Dashboard View
CREATE OR REPLACE VIEW ea_orchestration_dashboard AS
SELECT 
    c.id as customer_id,
    c.business_name,
    p.communication_style,
    p.preferred_language,
    
    -- Context metrics
    COUNT(DISTINCT ctx.context_id) as active_conversations,
    AVG(ctx.context_freshness_score) as avg_context_freshness,
    MAX(ctx.last_activity_at) as last_conversation_activity,
    
    -- Voice metrics (today)
    COALESCE(vs.total_interactions, 0) as voice_interactions_today,
    COALESCE(vs.sla_compliance_percentage, 100) as voice_sla_compliance,
    
    -- Brand metrics (latest)
    (SELECT COUNT(*) FROM personal_brand_goals WHERE customer_id = c.id AND status = 'active') as active_brand_goals,
    (SELECT AVG(completion_percentage) FROM personal_brand_goals WHERE customer_id = c.id AND status = 'active') as avg_goal_completion,
    
    CURRENT_TIMESTAMP as dashboard_updated_at
FROM customers c
LEFT JOIN customer_personality_preferences p ON c.id = p.customer_id
LEFT JOIN conversation_context ctx ON c.id = ctx.customer_id AND ctx.context_type = 'ongoing'
LEFT JOIN voice_performance_summary vs ON c.id = vs.customer_id AND vs.summary_date = CURRENT_DATE
WHERE c.is_active = true
GROUP BY c.id, c.business_name, p.communication_style, p.preferred_language, 
         vs.total_interactions, vs.sla_compliance_percentage
ORDER BY last_conversation_activity DESC NULLS LAST;

-- Cross-Channel Context Health View
CREATE OR REPLACE VIEW cross_channel_context_health AS
SELECT 
    customer_id,
    channel_type,
    COUNT(*) as active_contexts,
    AVG(context_freshness_score) as avg_freshness,
    AVG(importance_score) as avg_importance,
    COUNT(CASE WHEN last_activity_at > (CURRENT_TIMESTAMP - INTERVAL '1 hour') THEN 1 END) as recent_activity,
    COUNT(CASE WHEN expires_at < CURRENT_TIMESTAMP THEN 1 END) as expired_contexts,
    MAX(last_activity_at) as last_activity
FROM conversation_context 
WHERE context_type = 'ongoing'
GROUP BY customer_id, channel_type
ORDER BY customer_id, last_activity DESC;

-- Personal Brand Performance Trends View  
CREATE OR REPLACE VIEW brand_performance_trends AS
SELECT 
    customer_id,
    metric_type,
    DATE_TRUNC('week', measured_at) as week_period,
    AVG(metric_value) as avg_value,
    MIN(metric_value) as min_value,
    MAX(metric_value) as max_value,
    COUNT(*) as measurement_count,
    AVG(CASE WHEN performance_category IN ('improving', 'exceeding', 'exceptional') THEN 1 ELSE 0 END) * 100 as positive_trend_percentage
FROM personal_brand_metrics 
WHERE measured_at >= (CURRENT_DATE - INTERVAL '12 weeks')
GROUP BY customer_id, metric_type, DATE_TRUNC('week', measured_at)
ORDER BY customer_id, metric_type, week_period DESC;

-- Voice Quality and Performance Monitoring View
CREATE OR REPLACE VIEW voice_quality_monitor AS
SELECT 
    customer_id,
    DATE(started_at) as interaction_date,
    language_detected,
    COUNT(*) as total_interactions,
    AVG(total_processing_time_ms) as avg_response_time_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_processing_time_ms) as p95_response_time_ms,
    AVG(transcription_confidence) as avg_transcription_confidence,
    AVG(voice_quality_score) as avg_voice_quality,
    COUNT(CASE WHEN sla_compliance THEN 1 END) * 100.0 / COUNT(*) as sla_compliance_rate,
    SUM(estimated_cost_usd) as daily_voice_cost,
    COUNT(CASE WHEN error_count > 0 THEN 1 END) * 100.0 / COUNT(*) as error_rate
FROM voice_interaction_logs 
WHERE started_at >= (CURRENT_DATE - INTERVAL '30 days')
GROUP BY customer_id, DATE(started_at), language_detected
ORDER BY customer_id, interaction_date DESC, language_detected;

-- ====================================================================
-- PHASE 2 INITIAL DATA & DEFAULTS
-- ====================================================================

-- Create default personality preferences for existing customers
INSERT INTO customer_personality_preferences (customer_id, communication_style, preferred_language)
SELECT 
    id,
    'premium_casual',
    'en'
FROM customers 
WHERE is_active = true
ON CONFLICT (customer_id) DO NOTHING;

-- ====================================================================
-- GRANT PERMISSIONS FOR PHASE 2 TABLES
-- ====================================================================

-- Grant necessary permissions for MCP servers and applications
GRANT SELECT, INSERT, UPDATE, DELETE ON customer_personality_preferences TO mcphub;
GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_context TO mcphub;
GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_context_transitions TO mcphub;
GRANT SELECT, INSERT, UPDATE, DELETE ON personal_brand_metrics TO mcphub;
GRANT SELECT, INSERT, UPDATE, DELETE ON personal_brand_goals TO mcphub;
GRANT SELECT, INSERT, UPDATE, DELETE ON voice_interaction_logs TO mcphub;
GRANT SELECT, INSERT, UPDATE, DELETE ON voice_performance_summary TO mcphub;

-- Grant access to views
GRANT SELECT ON ea_orchestration_dashboard TO mcphub;
GRANT SELECT ON cross_channel_context_health TO mcphub;
GRANT SELECT ON brand_performance_trends TO mcphub;
GRANT SELECT ON voice_quality_monitor TO mcphub;

-- ====================================================================
-- MIGRATION COMPLETION AND VALIDATION
-- ====================================================================

-- Record migration completion
INSERT INTO schema_migrations (version, description) VALUES 
    ('2.0.0', 'Phase 2 EA Orchestration System - Premium-Casual Personality, Cross-Channel Context, Personal Brand Metrics, Voice Integration (Development Version)')
ON CONFLICT (version) DO NOTHING;

-- Validate Phase 2 schema deployment
DO $$
DECLARE
    table_count INTEGER;
    index_count INTEGER;
    view_count INTEGER;
BEGIN
    -- Count Phase 2 tables
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
    
    IF table_count < 7 THEN
        RAISE EXCEPTION 'Phase 2 migration incomplete: Expected 7 tables, found %', table_count;
    END IF;
    
    -- Count Phase 2 indexes
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes 
    WHERE indexname LIKE 'idx_%personality%' 
       OR indexname LIKE 'idx_%conversation%' 
       OR indexname LIKE 'idx_%brand%'
       OR indexname LIKE 'idx_%voice%';
    
    IF index_count < 15 THEN
        RAISE NOTICE 'Phase 2 migration warning: Expected 15+ indexes, found %. Performance may be impacted.', index_count;
    END IF;
    
    -- Count Phase 2 views
    SELECT COUNT(*) INTO view_count
    FROM information_schema.views 
    WHERE table_name IN (
        'ea_orchestration_dashboard',
        'cross_channel_context_health', 
        'brand_performance_trends',
        'voice_quality_monitor'
    );
    
    IF view_count < 4 THEN
        RAISE EXCEPTION 'Phase 2 migration incomplete: Expected 4 views, found %', view_count;
    END IF;
    
    RAISE NOTICE 'Phase 2 database schema migration completed successfully!';
    RAISE NOTICE 'Tables: %, Indexes: %, Views: %', table_count, index_count, view_count;
    RAISE NOTICE 'EA Orchestration System ready for Premium-Casual personality and cross-channel context preservation.';
    RAISE NOTICE 'NOTE: This development version uses text search instead of vector embeddings.';
END $$;