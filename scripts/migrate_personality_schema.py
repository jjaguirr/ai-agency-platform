#!/usr/bin/env python3
"""
Personality Engine Database Migration Script
Extends existing customer isolation schema with personality-specific tables

This script safely adds personality engine tables to the existing Phase 1 infrastructure
while maintaining all customer isolation and security patterns.
"""

import asyncio
import asyncpg
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agents.personality.personality_database import PersonalityDatabase, validate_personality_database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PersonalityMigration:
    """Manages personality database schema migrations"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.migration_version = "1.0.0"
        
    async def run_migration(self) -> Dict[str, Any]:
        """
        Run complete personality schema migration.
        
        Returns:
            Dict with migration results
        """
        migration_results = {
            'started_at': datetime.now().isoformat(),
            'version': self.migration_version,
            'steps_completed': [],
            'errors': [],
            'success': False
        }
        
        try:
            # Step 1: Validate existing schema
            logger.info("Step 1: Validating existing database schema...")
            existing_validation = await self._validate_existing_schema()
            migration_results['existing_schema_valid'] = existing_validation
            migration_results['steps_completed'].append("existing_schema_validation")
            
            if not existing_validation:
                raise Exception("Existing schema validation failed - migration cannot proceed")
            
            # Step 2: Create personality-specific tables
            logger.info("Step 2: Creating personality tables...")
            await self._create_personality_tables()
            migration_results['steps_completed'].append("personality_tables_created")
            
            # Step 3: Set up indexes and constraints
            logger.info("Step 3: Creating indexes and constraints...")
            await self._create_indexes_and_constraints()
            migration_results['steps_completed'].append("indexes_and_constraints_created")
            
            # Step 4: Enable row-level security
            logger.info("Step 4: Enabling row-level security...")
            await self._enable_row_level_security()
            migration_results['steps_completed'].append("row_level_security_enabled")
            
            # Step 5: Create triggers and functions
            logger.info("Step 5: Creating triggers and functions...")
            await self._create_triggers_and_functions()
            migration_results['steps_completed'].append("triggers_and_functions_created")
            
            # Step 6: Insert migration record
            logger.info("Step 6: Recording migration...")
            await self._record_migration()
            migration_results['steps_completed'].append("migration_recorded")
            
            # Step 7: Validate personality schema
            logger.info("Step 7: Validating personality schema...")
            personality_validation = await validate_personality_database(self.database_url)
            migration_results['personality_schema_validation'] = personality_validation
            migration_results['steps_completed'].append("personality_schema_validated")
            
            # Step 8: Run integration tests
            logger.info("Step 8: Running integration tests...")
            integration_results = await self._run_integration_tests()
            migration_results['integration_tests'] = integration_results
            migration_results['steps_completed'].append("integration_tests_completed")
            
            migration_results['success'] = True
            migration_results['completed_at'] = datetime.now().isoformat()
            
            logger.info("✅ Personality schema migration completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            migration_results['errors'].append(str(e))
            migration_results['failed_at'] = datetime.now().isoformat()
        
        return migration_results
    
    async def _validate_existing_schema(self) -> bool:
        """Validate that existing Phase 1 schema is present"""
        
        try:
            conn = await asyncpg.connect(self.database_url)
            
            # Check for core Phase 1 tables
            required_tables = [
                'customers', 'users', 'agents', 'workflows',
                'messaging_channels', 'customer_business_context'
            ]
            
            for table_name in required_tables:
                result = await conn.fetchrow(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = $1)",
                    table_name
                )
                
                if not result['exists']:
                    logger.error(f"Required table missing: {table_name}")
                    await conn.close()
                    return False
            
            # Check for vector extension (optional for personality patterns)
            vector_check = await conn.fetchrow(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
            
            if not vector_check['exists']:
                logger.warning("Vector extension not found - will attempt to install")
                try:
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    logger.info("Vector extension installed successfully")
                except Exception as e:
                    logger.warning(f"Vector extension not available: {e}")
                    logger.info("Continuing without vector extension - semantic search features will be disabled")
            
            await conn.close()
            logger.info("✅ Existing schema validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return False
    
    async def _create_personality_tables(self) -> None:
        """Create personality-specific tables"""
        
        personality_schema_sql = """
        -- Customer Personality Preferences - Extends existing customer isolation
        CREATE TABLE IF NOT EXISTS customer_personality_preferences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            preferred_tone VARCHAR(50) DEFAULT 'professional_warm' CHECK (preferred_tone IN (
                'professional_warm', 'motivational', 'supportive', 'strategic', 'conversational'
            )),
            communication_style_preferences JSONB DEFAULT '{}'::JSONB,
            successful_patterns JSONB DEFAULT '[]'::JSONB,
            avoided_patterns JSONB DEFAULT '[]'::JSONB,
            personality_consistency_score FLOAT DEFAULT 0.0 CHECK (personality_consistency_score BETWEEN 0 AND 1),
            a_b_test_participation JSONB DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id)
        );

        -- Personality Transformation History - Track all transformations for analysis
        CREATE TABLE IF NOT EXISTS personality_transformations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            original_content TEXT NOT NULL,
            transformed_content TEXT NOT NULL,
            channel VARCHAR(50) NOT NULL CHECK (channel IN ('email', 'whatsapp', 'voice', 'web_chat', 'sms')),
            personality_tone VARCHAR(50) NOT NULL,
            conversation_context VARCHAR(50),
            transformation_time_ms INTEGER NOT NULL,
            consistency_score FLOAT CHECK (consistency_score BETWEEN 0 AND 1),
            premium_casual_indicators JSONB DEFAULT '[]'::JSONB,
            transformation_metadata JSONB DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Personality A/B Test Results - Track A/B testing for optimization  
        CREATE TABLE IF NOT EXISTS personality_ab_test_results (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            test_name VARCHAR(255) NOT NULL,
            variation_name VARCHAR(100) NOT NULL,
            original_content TEXT NOT NULL,
            transformed_content TEXT NOT NULL,
            channel VARCHAR(50) NOT NULL,
            personality_tone VARCHAR(50) NOT NULL,
            user_preference_score FLOAT CHECK (user_preference_score BETWEEN 0 AND 1),
            engagement_metrics JSONB DEFAULT '{}'::JSONB,
            test_metadata JSONB DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        -- Personality Consistency Reports - Store consistency analysis results
        CREATE TABLE IF NOT EXISTS personality_consistency_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            report_period_hours INTEGER DEFAULT 24,
            overall_consistency_score FLOAT CHECK (overall_consistency_score BETWEEN 0 AND 1),
            channel_scores JSONB DEFAULT '{}'::JSONB,
            consistency_issues JSONB DEFAULT '[]'::JSONB,
            improvement_suggestions JSONB DEFAULT '[]'::JSONB,
            sample_transformations JSONB DEFAULT '{}'::JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        conn = await asyncpg.connect(self.database_url)
        await conn.execute(personality_schema_sql)
        await conn.close()
        
        logger.info("✅ Personality tables created successfully")
    
    async def _create_indexes_and_constraints(self) -> None:
        """Create performance indexes and constraints"""
        
        indexes_sql = """
        -- Indexes for personality query performance
        CREATE INDEX IF NOT EXISTS idx_personality_prefs_customer ON customer_personality_preferences(customer_id);
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_customer_channel ON personality_transformations(customer_id, channel, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_time ON personality_transformations(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_consistency ON personality_transformations(consistency_score DESC, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_personality_ab_tests_customer_test ON personality_ab_test_results(customer_id, test_name);
        CREATE INDEX IF NOT EXISTS idx_personality_consistency_customer ON personality_consistency_reports(customer_id, created_at DESC);
        
        -- Performance optimization indexes
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_performance ON personality_transformations(transformation_time_ms, created_at);
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_channel_tone ON personality_transformations(channel, personality_tone, created_at);
        """
        
        conn = await asyncpg.connect(self.database_url)
        await conn.execute(indexes_sql)
        await conn.close()
        
        logger.info("✅ Indexes and constraints created successfully")
    
    async def _enable_row_level_security(self) -> None:
        """Enable row-level security for customer isolation"""
        
        rls_sql = """
        -- Enable Row Level Security for personality tables (matches existing pattern)
        ALTER TABLE customer_personality_preferences ENABLE ROW LEVEL SECURITY;
        ALTER TABLE personality_transformations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE personality_ab_test_results ENABLE ROW LEVEL SECURITY;
        ALTER TABLE personality_consistency_reports ENABLE ROW LEVEL SECURITY;
        
        -- Grant permissions to mcphub user (matches existing pattern)
        GRANT SELECT, INSERT, UPDATE, DELETE ON customer_personality_preferences TO mcphub;
        GRANT SELECT, INSERT, UPDATE, DELETE ON personality_transformations TO mcphub;
        GRANT SELECT, INSERT, UPDATE, DELETE ON personality_ab_test_results TO mcphub;
        GRANT SELECT, INSERT, UPDATE, DELETE ON personality_consistency_reports TO mcphub;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mcphub;
        """
        
        conn = await asyncpg.connect(self.database_url)
        await conn.execute(rls_sql)
        await conn.close()
        
        logger.info("✅ Row-level security enabled for personality tables")
    
    async def _create_triggers_and_functions(self) -> None:
        """Create triggers for automatic timestamp updates"""
        
        triggers_sql = """
        -- Trigger for updating personality preferences timestamp (uses existing function)
        CREATE TRIGGER update_personality_preferences_updated_at 
            BEFORE UPDATE ON customer_personality_preferences 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
        
        conn = await asyncpg.connect(self.database_url)
        
        try:
            await conn.execute(triggers_sql)
        except Exception as e:
            # If trigger already exists, that's fine
            if "already exists" not in str(e):
                raise
        
        await conn.close()
        
        logger.info("✅ Triggers and functions created successfully")
    
    async def _record_migration(self) -> None:
        """Record this migration in schema_migrations table"""
        
        conn = await asyncpg.connect(self.database_url)
        
        migration_record_sql = """
        INSERT INTO schema_migrations (version, description) VALUES 
            ($1, $2)
        ON CONFLICT (version) DO NOTHING;
        """
        
        await conn.execute(
            migration_record_sql,
            f"personality_engine_{self.migration_version}",
            f"Personality Engine - Premium-Casual Transformation System v{self.migration_version}"
        )
        
        await conn.close()
        
        logger.info("✅ Migration recorded in schema_migrations table")
    
    async def _run_integration_tests(self) -> Dict[str, Any]:
        """Run basic integration tests to verify migration"""
        
        test_results = {
            'database_operations': False,
            'customer_isolation': False,
            'performance_acceptable': False,
            'errors': []
        }
        
        try:
            # Test basic database operations
            db = PersonalityDatabase(self.database_url)
            await db.initialize()
            
            # Test storing personality profile
            from src.agents.personality import PersonalityProfile
            test_profile = PersonalityProfile(customer_id='migration-test-customer')
            
            store_success = await db.store_personality_profile(test_profile)
            if store_success:
                # Test loading profile
                loaded_profile = await db.load_personality_profile('migration-test-customer')
                if loaded_profile and loaded_profile.customer_id == 'migration-test-customer':
                    test_results['database_operations'] = True
            
            # Test customer isolation (verify foreign key constraints work)
            conn = await asyncpg.connect(self.database_url)
            
            # Should fail to insert personality data for non-existent customer
            try:
                await conn.execute("""
                    INSERT INTO customer_personality_preferences (customer_id) 
                    VALUES ('00000000-1111-2222-3333-444444444444')
                """)
                # If this doesn't fail, isolation is broken
                test_results['errors'].append("Customer isolation test failed - foreign key not enforced")
            except asyncpg.ForeignKeyViolationError:
                # This is expected - foreign key constraint working
                test_results['customer_isolation'] = True
            except Exception as e:
                test_results['errors'].append(f"Unexpected error in isolation test: {e}")
            
            await conn.close()
            
            # Test performance (basic query speed)
            import time
            start_time = time.time()
            
            # Run some performance queries
            perf_metrics = await db.get_performance_metrics(hours_back=1)
            
            query_time = int((time.time() - start_time) * 1000)
            if query_time < 1000:  # Should be under 1 second
                test_results['performance_acceptable'] = True
            else:
                test_results['errors'].append(f"Performance test failed: {query_time}ms")
            
            # Cleanup test data
            await conn.execute(
                "DELETE FROM customer_personality_preferences WHERE customer_id = $1",
                'migration-test-customer'
            )
            
            await db.close()
            
        except Exception as e:
            test_results['errors'].append(f"Integration test error: {e}")
            logger.error(f"Integration test failed: {e}")
        
        return test_results


async def main():
    """Main migration execution"""
    
    # Get database URL from environment or use default
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql://mcphub:dev_password_123@localhost:5432/ai_agency_platform'
    )
    
    logger.info("🚀 Starting Personality Engine Database Migration")
    logger.info(f"Database URL: {database_url.replace('dev_password_123', '***')}")
    
    try:
        migration = PersonalityMigration(database_url)
        results = await migration.run_migration()
        
        if results['success']:
            logger.info("✅ Migration completed successfully!")
            logger.info(f"Steps completed: {', '.join(results['steps_completed'])}")
            
            if results.get('integration_tests', {}).get('errors'):
                logger.warning("⚠️ Some integration tests had issues:")
                for error in results['integration_tests']['errors']:
                    logger.warning(f"  - {error}")
            
        else:
            logger.error("❌ Migration failed!")
            for error in results['errors']:
                logger.error(f"  - {error}")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Migration script failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)