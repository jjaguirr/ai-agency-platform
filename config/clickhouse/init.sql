-- AI Agency Platform - ClickHouse Initialization
-- Analytics database setup for LangFuse integration

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS langfuse_analytics;

-- Use the analytics database
USE langfuse_analytics;

-- Create tables for AI Agency Platform specific analytics
-- This will be populated by LangFuse automatically, but we can add custom tables

CREATE TABLE IF NOT EXISTS agent_performance (
    timestamp DateTime64(3),
    agent_type String,
    customer_id String,
    model_used String,
    prompt_tokens UInt32,
    completion_tokens UInt32,
    total_tokens UInt32,
    cost_usd Float64,
    latency_ms UInt32,
    success_rate Float64,
    INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 8192,
    INDEX idx_agent_type agent_type TYPE set(100) GRANULARITY 8192,
    INDEX idx_customer_id customer_id TYPE bloom_filter(0.01) GRANULARITY 8192
) ENGINE = MergeTree()
ORDER BY (agent_type, timestamp)
TTL timestamp + INTERVAL 1 YEAR;

CREATE TABLE IF NOT EXISTS launch_bot_analytics (
    timestamp DateTime64(3),
    customer_id String,
    configuration_time_seconds UInt32,
    success Bool,
    failure_reason String,
    configured_tools Array(String),
    selected_ai_model String,
    customer_industry String,
    INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 8192,
    INDEX idx_customer_id customer_id TYPE bloom_filter(0.01) GRANULARITY 8192
) ENGINE = MergeTree()
ORDER BY (success, timestamp)
TTL timestamp + INTERVAL 2 YEARS;

CREATE TABLE IF NOT EXISTS cost_optimization (
    date Date,
    agent_type String,
    model_name String,
    total_requests UInt64,
    total_cost_usd Float64,
    avg_latency_ms Float64,
    success_rate Float64,
    cost_per_request Float64,
    INDEX idx_date date TYPE minmax GRANULARITY 8192,
    INDEX idx_agent_type agent_type TYPE set(10) GRANULARITY 8192
) ENGINE = SummingMergeTree()
ORDER BY (date, agent_type, model_name);

-- Create materialized view for real-time cost tracking
CREATE MATERIALIZED VIEW IF NOT EXISTS cost_tracking_mv TO cost_optimization AS
SELECT
    toDate(timestamp) as date,
    agent_type,
    model_used as model_name,
    count() as total_requests,
    sum(cost_usd) as total_cost_usd,
    avg(latency_ms) as avg_latency_ms,
    avg(success_rate) as success_rate,
    avg(cost_usd) as cost_per_request
FROM agent_performance
GROUP BY date, agent_type, model_name;

-- Grant necessary permissions (if using authentication)
-- GRANT ALL ON langfuse_analytics.* TO default;