"""
Personality Database Integration - Customer Personality Preferences Schema
Integrates with existing customer isolation system for personality profile persistence
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

import asyncpg
from asyncpg import Connection, Pool

from .personality_engine import PersonalityProfile, PersonalityTransformationResult, CommunicationChannel

logger = logging.getLogger(__name__)


class PersonalityDatabase:
    """
    Database integration for personality profiles using existing customer isolation infrastructure.
    
    Extends the existing database schema with personality-specific tables while
    maintaining per-customer MCP server isolation patterns.
    """
    
    def __init__(self, database_url: str, pool: Optional[Pool] = None):
        """
        Initialize personality database integration.
        
        Args:
            database_url: PostgreSQL connection string
            pool: Optional existing connection pool
        """
        self.database_url = database_url
        self.pool = pool
        self._initialized = False
        
        logger.info("PersonalityDatabase initialized")
    
    async def initialize(self) -> None:
        """Initialize database connection and create personality tables"""
        
        try:
            if not self.pool:
                self.pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=2,
                    max_size=10,
                    command_timeout=30
                )
            
            # Create personality-specific tables
            await self._create_personality_tables()
            self._initialized = True
            
            logger.info("PersonalityDatabase initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PersonalityDatabase: {e}")
            raise
    
    async def close(self) -> None:
        """Close database connections"""
        
        if self.pool:
            await self.pool.close()
            self.pool = None
            self._initialized = False
    
    async def _create_personality_tables(self) -> None:
        """Create personality-specific database tables with customer isolation"""
        
        personality_schema = """
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

        -- Indexes for personality query performance
        CREATE INDEX IF NOT EXISTS idx_personality_prefs_customer ON customer_personality_preferences(customer_id);
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_customer_channel ON personality_transformations(customer_id, channel, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_personality_transformations_time ON personality_transformations(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_personality_ab_tests_customer_test ON personality_ab_test_results(customer_id, test_name);
        CREATE INDEX IF NOT EXISTS idx_personality_consistency_customer ON personality_consistency_reports(customer_id, created_at DESC);

        -- Enable Row Level Security for personality tables
        ALTER TABLE customer_personality_preferences ENABLE ROW LEVEL SECURITY;
        ALTER TABLE personality_transformations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE personality_ab_test_results ENABLE ROW LEVEL SECURITY;
        ALTER TABLE personality_consistency_reports ENABLE ROW LEVEL SECURITY;

        -- Trigger for updating personality preferences timestamp
        CREATE TRIGGER update_personality_preferences_updated_at 
            BEFORE UPDATE ON customer_personality_preferences 
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(personality_schema)
            logger.info("Personality database schema created successfully")
    
    async def store_personality_profile(self, profile: PersonalityProfile) -> bool:
        """
        Store or update customer personality profile.
        
        Args:
            profile: PersonalityProfile to store
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                # Use UPSERT to handle both inserts and updates
                query = """
                INSERT INTO customer_personality_preferences (
                    customer_id, preferred_tone, communication_style_preferences,
                    successful_patterns, avoided_patterns, personality_consistency_score,
                    updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (customer_id) 
                DO UPDATE SET
                    preferred_tone = EXCLUDED.preferred_tone,
                    communication_style_preferences = EXCLUDED.communication_style_preferences,
                    successful_patterns = EXCLUDED.successful_patterns,
                    avoided_patterns = EXCLUDED.avoided_patterns,
                    personality_consistency_score = EXCLUDED.personality_consistency_score,
                    updated_at = EXCLUDED.updated_at
                """
                
                await conn.execute(
                    query,
                    profile.customer_id,
                    profile.preferred_tone.value,
                    json.dumps(profile.communication_style_preferences),
                    json.dumps(profile.successful_patterns),
                    json.dumps(profile.avoided_patterns),
                    profile.personality_consistency_score,
                    datetime.now()
                )
                
                logger.info(f"Stored personality profile for customer {profile.customer_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to store personality profile: {e}")
            return False
    
    async def load_personality_profile(self, customer_id: str) -> Optional[PersonalityProfile]:
        """
        Load customer personality profile from database.
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            PersonalityProfile if found, None otherwise
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                query = """
                SELECT customer_id, preferred_tone, communication_style_preferences,
                       successful_patterns, avoided_patterns, personality_consistency_score,
                       created_at, updated_at
                FROM customer_personality_preferences
                WHERE customer_id = $1
                """
                
                row = await conn.fetchrow(query, customer_id)
                
                if row:
                    return PersonalityProfile(
                        customer_id=row['customer_id'],
                        preferred_tone=row['preferred_tone'],
                        communication_style_preferences=json.loads(row['communication_style_preferences']),
                        successful_patterns=json.loads(row['successful_patterns']),
                        avoided_patterns=json.loads(row['avoided_patterns']),
                        personality_consistency_score=row['personality_consistency_score'],
                        created_at=row['created_at'].isoformat(),
                        updated_at=row['updated_at'].isoformat()
                    )
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to load personality profile: {e}")
            return None
    
    async def store_transformation_result(self, result: PersonalityTransformationResult, customer_id: str) -> bool:
        """
        Store personality transformation result for analysis.
        
        Args:
            result: PersonalityTransformationResult to store
            customer_id: Customer identifier
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                query = """
                INSERT INTO personality_transformations (
                    customer_id, original_content, transformed_content, channel,
                    personality_tone, transformation_time_ms, consistency_score,
                    premium_casual_indicators, transformation_metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """
                
                await conn.execute(
                    query,
                    customer_id,
                    result.original_content,
                    result.transformed_content,
                    result.channel.value,
                    result.personality_tone.value,
                    result.transformation_time_ms,
                    result.consistency_score,
                    json.dumps(result.premium_casual_indicators),
                    json.dumps(result.transformation_metadata)
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to store transformation result: {e}")
            return False
    
    async def get_transformation_history(
        self,
        customer_id: str,
        channel: Optional[CommunicationChannel] = None,
        limit: int = 50,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get transformation history for consistency analysis.
        
        Args:
            customer_id: Customer identifier
            channel: Optional channel filter
            limit: Maximum number of results
            hours_back: How many hours of history to retrieve
            
        Returns:
            List of transformation records
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                base_query = """
                SELECT id, original_content, transformed_content, channel, personality_tone,
                       transformation_time_ms, consistency_score, premium_casual_indicators,
                       transformation_metadata, created_at
                FROM personality_transformations
                WHERE customer_id = $1 
                AND created_at > NOW() - INTERVAL '%d hours'
                """ % hours_back
                
                params = [customer_id]
                
                if channel:
                    base_query += " AND channel = $2"
                    params.append(channel.value)
                
                base_query += " ORDER BY created_at DESC LIMIT $%d" % (len(params) + 1)
                params.append(limit)
                
                rows = await conn.fetch(base_query, *params)
                
                return [
                    {
                        'id': str(row['id']),
                        'original_content': row['original_content'],
                        'transformed_content': row['transformed_content'],
                        'channel': row['channel'],
                        'personality_tone': row['personality_tone'],
                        'transformation_time_ms': row['transformation_time_ms'],
                        'consistency_score': row['consistency_score'],
                        'premium_casual_indicators': json.loads(row['premium_casual_indicators']),
                        'transformation_metadata': json.loads(row['transformation_metadata']),
                        'created_at': row['created_at'].isoformat()
                    }
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to get transformation history: {e}")
            return []
    
    async def store_ab_test_result(
        self,
        customer_id: str,
        test_name: str,
        variation_name: str,
        result: PersonalityTransformationResult,
        user_preference_score: Optional[float] = None,
        engagement_metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store A/B test result for personality optimization.
        
        Args:
            customer_id: Customer identifier
            test_name: Name of the A/B test
            variation_name: Name of the variation (e.g., "control", "variation_a")
            result: PersonalityTransformationResult from the test
            user_preference_score: Optional user preference score (0-1)
            engagement_metrics: Optional engagement metrics
            
        Returns:
            True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                query = """
                INSERT INTO personality_ab_test_results (
                    customer_id, test_name, variation_name, original_content,
                    transformed_content, channel, personality_tone,
                    user_preference_score, engagement_metrics, test_metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """
                
                test_metadata = {
                    'transformation_time_ms': result.transformation_time_ms,
                    'consistency_score': result.consistency_score,
                    'premium_casual_indicators': result.premium_casual_indicators
                }
                
                await conn.execute(
                    query,
                    customer_id,
                    test_name,
                    variation_name,
                    result.original_content,
                    result.transformed_content,
                    result.channel.value,
                    result.personality_tone.value,
                    user_preference_score,
                    json.dumps(engagement_metrics or {}),
                    json.dumps(test_metadata)
                )
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to store A/B test result: {e}")
            return False
    
    async def get_ab_test_results(
        self,
        customer_id: str,
        test_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get A/B test results for analysis.
        
        Args:
            customer_id: Customer identifier
            test_name: Optional test name filter
            
        Returns:
            List of A/B test results
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                base_query = """
                SELECT test_name, variation_name, original_content, transformed_content,
                       channel, personality_tone, user_preference_score,
                       engagement_metrics, test_metadata, created_at
                FROM personality_ab_test_results
                WHERE customer_id = $1
                """
                
                params = [customer_id]
                
                if test_name:
                    base_query += " AND test_name = $2"
                    params.append(test_name)
                
                base_query += " ORDER BY created_at DESC"
                
                rows = await conn.fetch(base_query, *params)
                
                return [
                    {
                        'test_name': row['test_name'],
                        'variation_name': row['variation_name'],
                        'original_content': row['original_content'],
                        'transformed_content': row['transformed_content'],
                        'channel': row['channel'],
                        'personality_tone': row['personality_tone'],
                        'user_preference_score': row['user_preference_score'],
                        'engagement_metrics': json.loads(row['engagement_metrics']),
                        'test_metadata': json.loads(row['test_metadata']),
                        'created_at': row['created_at'].isoformat()
                    }
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to get A/B test results: {e}")
            return []
    
    async def analyze_customer_consistency(
        self,
        customer_id: str,
        hours_back: int = 24
    ) -> Dict[str, Any]:
        """
        Analyze personality consistency for a customer.
        
        Args:
            customer_id: Customer identifier
            hours_back: Hours of history to analyze
            
        Returns:
            Dictionary with consistency analysis results
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                # Get transformations grouped by channel
                query = """
                SELECT channel, 
                       COUNT(*) as transformation_count,
                       AVG(consistency_score) as avg_consistency_score,
                       AVG(transformation_time_ms) as avg_transformation_time,
                       ARRAY_AGG(DISTINCT personality_tone) as tones_used
                FROM personality_transformations
                WHERE customer_id = $1 
                AND created_at > NOW() - INTERVAL '%d hours'
                AND consistency_score IS NOT NULL
                GROUP BY channel
                """ % hours_back
                
                rows = await conn.fetch(query, customer_id)
                
                channel_analysis = {}
                overall_scores = []
                
                for row in rows:
                    channel_analysis[row['channel']] = {
                        'transformation_count': row['transformation_count'],
                        'avg_consistency_score': float(row['avg_consistency_score']),
                        'avg_transformation_time': int(row['avg_transformation_time']),
                        'tones_used': row['tones_used']
                    }
                    overall_scores.append(float(row['avg_consistency_score']))
                
                # Calculate overall consistency
                overall_consistency = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0
                
                return {
                    'customer_id': customer_id,
                    'analysis_period_hours': hours_back,
                    'overall_consistency_score': overall_consistency,
                    'channel_analysis': channel_analysis,
                    'total_transformations': sum(
                        data['transformation_count'] for data in channel_analysis.values()
                    ),
                    'channels_used': len(channel_analysis),
                    'analysis_timestamp': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to analyze customer consistency: {e}")
            return {
                'customer_id': customer_id,
                'error': str(e),
                'overall_consistency_score': 0.0
            }
    
    async def get_performance_metrics(
        self,
        customer_id: Optional[str] = None,
        hours_back: int = 24
    ) -> Dict[str, Any]:
        """
        Get personality engine performance metrics.
        
        Args:
            customer_id: Optional customer filter
            hours_back: Hours of data to analyze
            
        Returns:
            Dictionary with performance metrics
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            async with self.pool.acquire() as conn:
                base_query = """
                SELECT 
                    COUNT(*) as total_transformations,
                    AVG(transformation_time_ms) as avg_transformation_time,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY transformation_time_ms) as p95_transformation_time,
                    AVG(consistency_score) as avg_consistency_score,
                    COUNT(CASE WHEN transformation_time_ms < 500 THEN 1 END) as under_500ms_count,
                    COUNT(CASE WHEN consistency_score > 0.8 THEN 1 END) as high_consistency_count,
                    COUNT(DISTINCT customer_id) as unique_customers,
                    COUNT(DISTINCT channel) as channels_used
                FROM personality_transformations
                WHERE created_at > NOW() - INTERVAL '%d hours'
                """ % hours_back
                
                params = []
                if customer_id:
                    base_query += " AND customer_id = $1"
                    params.append(customer_id)
                
                row = await conn.fetchrow(base_query, *params)
                
                total_transformations = row['total_transformations'] or 0
                under_500ms_percent = (
                    (row['under_500ms_count'] / total_transformations * 100) 
                    if total_transformations > 0 else 0
                )
                high_consistency_percent = (
                    (row['high_consistency_count'] / total_transformations * 100)
                    if total_transformations > 0 else 0
                )
                
                return {
                    'analysis_period_hours': hours_back,
                    'total_transformations': total_transformations,
                    'avg_transformation_time_ms': int(row['avg_transformation_time'] or 0),
                    'p95_transformation_time_ms': int(row['p95_transformation_time'] or 0),
                    'avg_consistency_score': float(row['avg_consistency_score'] or 0),
                    'performance_sla_compliance': under_500ms_percent,  # Percentage under 500ms
                    'high_consistency_rate': high_consistency_percent,  # Percentage >0.8 consistency
                    'unique_customers_served': row['unique_customers'] or 0,
                    'channels_used': row['channels_used'] or 0,
                    'sla_target_met': under_500ms_percent >= 95,  # 95% should be under 500ms
                    'generated_at': datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {
                'error': str(e),
                'generated_at': datetime.now().isoformat()
            }


# Database utility functions for personality system
async def migrate_personality_schema(database_url: str) -> bool:
    """Run personality database schema migration"""
    
    try:
        db = PersonalityDatabase(database_url)
        await db.initialize()
        await db.close()
        logger.info("Personality schema migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Personality schema migration failed: {e}")
        return False


async def validate_personality_database(database_url: str) -> Dict[str, Any]:
    """Validate personality database setup and performance"""
    
    validation_results = {
        'tables_exist': False,
        'indexes_created': False,
        'rls_enabled': False,
        'triggers_active': False,
        'sample_operations_working': False,
        'performance_acceptable': False
    }
    
    try:
        db = PersonalityDatabase(database_url)
        await db.initialize()
        
        async with db.pool.acquire() as conn:
            # Check if tables exist
            table_check = await conn.fetch("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE '%personality%'
            """)
            validation_results['tables_exist'] = len(table_check) >= 4
            
            # Check indexes
            index_check = await conn.fetch("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename LIKE '%personality%'
            """)
            validation_results['indexes_created'] = len(index_check) >= 5
            
            # Test sample operations
            try:
                test_profile = PersonalityProfile(customer_id='test-validation')
                await db.store_personality_profile(test_profile)
                loaded_profile = await db.load_personality_profile('test-validation')
                validation_results['sample_operations_working'] = loaded_profile is not None
                
                # Clean up test data
                await conn.execute(
                    "DELETE FROM customer_personality_preferences WHERE customer_id = $1",
                    'test-validation'
                )
                
            except Exception as e:
                logger.warning(f"Sample operations test failed: {e}")
            
        await db.close()
        
    except Exception as e:
        logger.error(f"Personality database validation failed: {e}")
        validation_results['error'] = str(e)
    
    return validation_results