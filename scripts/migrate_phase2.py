#!/usr/bin/env python3
"""
AI Agency Platform - Phase 2 Database Migration Script
EA Orchestration System Database Schema Updates

This script handles the safe migration from Phase 1 to Phase 2 database schema
with comprehensive validation, performance testing, and rollback capabilities.
"""

import os
import sys
import time
import logging
import argparse
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Add the src directory to the path for imports
sys.path.append(str(Path(__file__).parent.parent / "src"))

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_phase2_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class Phase2Migration:
    """Handles Phase 2 database migration with safety checks and performance validation"""
    
    def __init__(self, database_url: str, dry_run: bool = False):
        self.database_url = database_url
        self.dry_run = dry_run
        self.migration_dir = Path(__file__).parent.parent / "src" / "database" / "migrations"
        self.migration_file = self.migration_dir / "002_phase2_ea_orchestration.sql"
        self.rollback_file = self.migration_dir / "002_phase2_ea_orchestration_rollback.sql"
        
        # Performance benchmarks (Phase 2 requirements)
        self.performance_targets = {
            "max_query_time_ms": 100,
            "max_context_recall_ms": 500,
            "max_voice_processing_ms": 2000
        }
        
        logger.info(f"Phase 2 Migration initialized - Dry Run: {dry_run}")
        
    def get_connection(self) -> psycopg2.extensions.connection:
        """Get database connection with proper configuration"""
        try:
            conn = psycopg2.connect(
                self.database_url,
                cursor_factory=RealDictCursor,
                connect_timeout=10
            )
            conn.autocommit = False  # Use transactions for safety
            return conn
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def check_prerequisites(self) -> bool:
        """Verify system is ready for Phase 2 migration"""
        logger.info("Checking Phase 2 migration prerequisites...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check Phase 1 schema exists
                    cursor.execute("""
                        SELECT version FROM schema_migrations 
                        WHERE version = '1.0.0'
                    """)
                    if not cursor.fetchone():
                        logger.error("Phase 1 migration (1.0.0) not found. Run Phase 1 migration first.")
                        return False
                    
                    # Check for existing Phase 2 migration
                    cursor.execute("""
                        SELECT version FROM schema_migrations 
                        WHERE version = '2.0.0'
                    """)
                    if cursor.fetchone():
                        logger.warning("Phase 2 migration (2.0.0) already applied!")
                        return False
                    
                    # Check required extensions
                    cursor.execute("""
                        SELECT extname FROM pg_extension 
                        WHERE extname IN ('vector', 'uuid-ossp')
                    """)
                    extensions = [row['extname'] for row in cursor.fetchall()]
                    
                    if 'vector' not in extensions:
                        logger.error("pgvector extension required for Phase 2. Install with: CREATE EXTENSION vector;")
                        return False
                        
                    if 'uuid-ossp' not in extensions:
                        logger.warning("uuid-ossp extension recommended for Phase 2")
                    
                    # Check database has sufficient resources
                    cursor.execute("SELECT current_setting('shared_buffers')")
                    shared_buffers = cursor.fetchone()['current_setting']
                    logger.info(f"Database shared_buffers: {shared_buffers}")
                    
                    # Verify active customers for personality preference creation
                    cursor.execute("SELECT COUNT(*) as count FROM customers WHERE is_active = true")
                    active_customers = cursor.fetchone()['count']
                    logger.info(f"Active customers for Phase 2 upgrade: {active_customers}")
                    
                    logger.info("Phase 2 prerequisites check passed ✅")
                    return True
                    
        except psycopg2.Error as e:
            logger.error(f"Prerequisites check failed: {e}")
            return False
    
    def backup_critical_data(self) -> bool:
        """Create backup of critical Phase 1 data before migration"""
        logger.info("Creating backup of critical data...")
        
        if self.dry_run:
            logger.info("DRY RUN: Would create backup of critical tables")
            return True
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Create backup schema
                    cursor.execute("""
                        CREATE SCHEMA IF NOT EXISTS phase1_backup_""" + datetime.now().strftime("%Y%m%d_%H%M%S") + """;
                    """)
                    
                    # Backup critical tables
                    critical_tables = [
                        'customers',
                        'users', 
                        'agents',
                        'agent_conversations',
                        'workflows',
                        'customer_business_context'
                    ]
                    
                    backup_schema = f"phase1_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    for table in critical_tables:
                        cursor.execute(f"""
                            CREATE TABLE {backup_schema}.{table}_backup AS 
                            SELECT * FROM {table};
                        """)
                        
                        cursor.execute(f"SELECT COUNT(*) as count FROM {backup_schema}.{table}_backup")
                        count = cursor.fetchone()['count']
                        logger.info(f"Backed up {count} rows from {table}")
                    
                    conn.commit()
                    logger.info(f"Critical data backed up to schema: {backup_schema} ✅")
                    return True
                    
        except psycopg2.Error as e:
            logger.error(f"Backup failed: {e}")
            return False
    
    def execute_migration(self) -> bool:
        """Execute the Phase 2 migration script"""
        logger.info("Executing Phase 2 database migration...")
        
        if not self.migration_file.exists():
            logger.error(f"Migration file not found: {self.migration_file}")
            return False
        
        if self.dry_run:
            logger.info("DRY RUN: Would execute Phase 2 migration")
            logger.info(f"Migration file: {self.migration_file}")
            return True
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Read and execute migration
                    migration_sql = self.migration_file.read_text()
                    
                    start_time = time.time()
                    cursor.execute(migration_sql)
                    execution_time = time.time() - start_time
                    
                    conn.commit()
                    logger.info(f"Phase 2 migration executed successfully in {execution_time:.2f} seconds ✅")
                    return True
                    
        except psycopg2.Error as e:
            logger.error(f"Migration execution failed: {e}")
            return False
    
    def validate_migration(self) -> bool:
        """Validate Phase 2 migration completed successfully"""
        logger.info("Validating Phase 2 migration...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Check migration record
                    cursor.execute("""
                        SELECT version, applied_at FROM schema_migrations 
                        WHERE version = '2.0.0'
                    """)
                    migration_record = cursor.fetchone()
                    if not migration_record:
                        logger.error("Migration record not found in schema_migrations")
                        return False
                    
                    logger.info(f"Migration 2.0.0 applied at: {migration_record['applied_at']}")
                    
                    # Validate Phase 2 tables exist
                    phase2_tables = [
                        'customer_personality_preferences',
                        'conversation_context',
                        'conversation_context_transitions', 
                        'personal_brand_metrics',
                        'personal_brand_goals',
                        'voice_interaction_logs',
                        'voice_performance_summary'
                    ]
                    
                    for table in phase2_tables:
                        cursor.execute(f"""
                            SELECT COUNT(*) as count 
                            FROM information_schema.tables 
                            WHERE table_name = '{table}'
                        """)
                        if cursor.fetchone()['count'] == 0:
                            logger.error(f"Phase 2 table missing: {table}")
                            return False
                    
                    # Validate Phase 2 views exist
                    phase2_views = [
                        'ea_orchestration_dashboard',
                        'cross_channel_context_health',
                        'brand_performance_trends',
                        'voice_quality_monitor'
                    ]
                    
                    for view in phase2_views:
                        cursor.execute(f"""
                            SELECT COUNT(*) as count 
                            FROM information_schema.views 
                            WHERE table_name = '{view}'
                        """)
                        if cursor.fetchone()['count'] == 0:
                            logger.error(f"Phase 2 view missing: {view}")
                            return False
                    
                    # Validate default personality preferences created
                    cursor.execute("""
                        SELECT COUNT(*) as count 
                        FROM customer_personality_preferences
                    """)
                    personality_count = cursor.fetchone()['count']
                    
                    cursor.execute("SELECT COUNT(*) as count FROM customers WHERE is_active = true")
                    active_customers = cursor.fetchone()['count']
                    
                    if personality_count != active_customers:
                        logger.warning(f"Personality preferences: {personality_count}, Active customers: {active_customers}")
                    else:
                        logger.info(f"Default personality preferences created for {personality_count} customers ✅")
                    
                    logger.info("Phase 2 migration validation passed ✅")
                    return True
                    
        except psycopg2.Error as e:
            logger.error(f"Migration validation failed: {e}")
            return False
    
    def test_performance(self) -> bool:
        """Test Phase 2 performance against targets"""
        logger.info("Testing Phase 2 performance benchmarks...")
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    performance_results = {}
                    
                    # Test 1: Customer personality preference query (<100ms)
                    start_time = time.time()
                    cursor.execute("""
                        SELECT * FROM customer_personality_preferences 
                        WHERE customer_id = (SELECT id FROM customers WHERE is_active = true LIMIT 1)
                    """)
                    query_time_ms = (time.time() - start_time) * 1000
                    performance_results['personality_query_ms'] = query_time_ms
                    
                    # Test 2: Cross-channel context recall (<500ms)
                    start_time = time.time()
                    cursor.execute("""
                        SELECT * FROM conversation_context 
                        WHERE customer_id = (SELECT id FROM customers WHERE is_active = true LIMIT 1)
                        ORDER BY last_activity_at DESC 
                        LIMIT 10
                    """)
                    context_time_ms = (time.time() - start_time) * 1000
                    performance_results['context_recall_ms'] = context_time_ms
                    
                    # Test 3: Dashboard view performance
                    start_time = time.time()
                    cursor.execute("SELECT * FROM ea_orchestration_dashboard LIMIT 5")
                    dashboard_time_ms = (time.time() - start_time) * 1000
                    performance_results['dashboard_query_ms'] = dashboard_time_ms
                    
                    # Evaluate performance
                    passed_tests = 0
                    total_tests = 0
                    
                    for test, result_ms in performance_results.items():
                        total_tests += 1
                        target_ms = self.performance_targets.get('max_query_time_ms', 100)
                        
                        if test == 'context_recall_ms':
                            target_ms = self.performance_targets.get('max_context_recall_ms', 500)
                        
                        if result_ms <= target_ms:
                            logger.info(f"✅ {test}: {result_ms:.2f}ms (target: {target_ms}ms)")
                            passed_tests += 1
                        else:
                            logger.warning(f"⚠️  {test}: {result_ms:.2f}ms (target: {target_ms}ms)")
                    
                    success_rate = (passed_tests / total_tests) * 100
                    logger.info(f"Performance test success rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
                    
                    if success_rate >= 80:  # 80% minimum pass rate
                        logger.info("Phase 2 performance tests passed ✅")
                        return True
                    else:
                        logger.warning("Phase 2 performance below targets ⚠️")
                        return False
                        
        except psycopg2.Error as e:
            logger.error(f"Performance testing failed: {e}")
            return False
    
    def rollback_migration(self) -> bool:
        """Rollback Phase 2 migration if needed"""
        logger.warning("Rolling back Phase 2 migration...")
        
        if not self.rollback_file.exists():
            logger.error(f"Rollback file not found: {self.rollback_file}")
            return False
        
        if self.dry_run:
            logger.info("DRY RUN: Would execute Phase 2 rollback")
            return True
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Read and execute rollback
                    rollback_sql = self.rollback_file.read_text()
                    
                    start_time = time.time()
                    cursor.execute(rollback_sql)
                    execution_time = time.time() - start_time
                    
                    conn.commit()
                    logger.info(f"Phase 2 rollback executed in {execution_time:.2f} seconds ✅")
                    return True
                    
        except psycopg2.Error as e:
            logger.error(f"Rollback execution failed: {e}")
            return False
    
    def run_migration(self, skip_backup: bool = False, skip_performance: bool = False) -> bool:
        """Execute complete Phase 2 migration workflow"""
        logger.info("🚀 Starting Phase 2 Database Migration - EA Orchestration System")
        logger.info("=" * 80)
        
        # Step 1: Prerequisites check
        if not self.check_prerequisites():
            logger.error("Prerequisites check failed. Aborting migration.")
            return False
        
        # Step 2: Backup critical data
        if not skip_backup and not self.backup_critical_data():
            logger.error("Data backup failed. Aborting migration.")
            return False
        
        # Step 3: Execute migration
        if not self.execute_migration():
            logger.error("Migration execution failed. Consider rollback.")
            return False
        
        # Step 4: Validate migration
        if not self.validate_migration():
            logger.error("Migration validation failed. Rolling back...")
            self.rollback_migration()
            return False
        
        # Step 5: Performance testing
        if not skip_performance and not self.test_performance():
            logger.warning("Performance tests failed but migration is functional")
            # Don't rollback on performance failures, just warn
        
        logger.info("=" * 80)
        logger.info("🎉 Phase 2 Migration Completed Successfully!")
        logger.info("EA Orchestration System with Premium-Casual Personality is now active")
        logger.info("Features enabled:")
        logger.info("  ✅ Customer personality preferences")
        logger.info("  ✅ Cross-channel conversation context")  
        logger.info("  ✅ Personal brand metrics tracking")
        logger.info("  ✅ Voice interaction analytics")
        logger.info("  ✅ EA orchestration dashboard")
        logger.info("=" * 80)
        
        return True

def main():
    """Main migration script entry point"""
    parser = argparse.ArgumentParser(description="Phase 2 Database Migration - EA Orchestration System")
    parser.add_argument("--database-url", required=True, help="PostgreSQL database URL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without executing")
    parser.add_argument("--skip-backup", action="store_true", help="Skip data backup (not recommended)")
    parser.add_argument("--skip-performance", action="store_true", help="Skip performance testing")
    parser.add_argument("--rollback", action="store_true", help="Rollback Phase 2 migration")
    
    args = parser.parse_args()
    
    migration = Phase2Migration(args.database_url, args.dry_run)
    
    if args.rollback:
        logger.info("Phase 2 Migration Rollback requested")
        success = migration.rollback_migration()
    else:
        success = migration.run_migration(args.skip_backup, args.skip_performance)
    
    if success:
        logger.info("Operation completed successfully ✅")
        sys.exit(0)
    else:
        logger.error("Operation failed ❌")
        sys.exit(1)

if __name__ == "__main__":
    main()