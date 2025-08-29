-- AI Agency Platform - PostgreSQL Database Initialization
-- Creates multiple databases for different services

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