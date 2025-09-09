#!/usr/bin/env python3
"""
Phase 2 Database Schema Validation Tests
Validates all acceptance criteria for EA Orchestration premium-casual personality system
"""

import psycopg2
import time
import json
import pytest
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

class Phase2DatabaseValidator:
    """Validates Phase 2 database schema implementation"""
    
    def __init__(self):
        self.conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='mcphub',
            user='mcphub',
            password='mcphub123'
        )
        self.cur = self.conn.cursor()
    
    def cleanup(self):
        """Clean up database connection"""
        self.cur.close()
        self.conn.close()

    def test_schema_exists(self) -> Dict[str, bool]:
        """Test that all required Phase 2 tables exist"""
        required_tables = [
            'customer_personality_preferences',
            'conversation_context',
            'personal_brand_metrics',
            'voice_interaction_logs'
        ]
        
        results = {}
        for table in required_tables:
            self.cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s AND table_schema = 'public'
                )
            """, (table,))
            results[table] = self.cur.fetchone()[0]
            
        return results

    def test_customer_isolation(self) -> Dict[str, any]:
        """Test customer isolation via Row Level Security"""
        # Check RLS is enabled on critical tables
        self.cur.execute("""
            SELECT tablename, rowsecurity 
            FROM pg_tables 
            WHERE tablename IN (
                'customer_personality_preferences',
                'conversation_context', 
                'personal_brand_metrics',
                'voice_interaction_logs'
            )
        """)
        
        rls_status = {row[0]: row[1] for row in self.cur.fetchall()}
        
        # Test data isolation by customer_id
        self.cur.execute("""
            SELECT COUNT(DISTINCT customer_id) 
            FROM customer_personality_preferences
        """)
        isolated_customers = self.cur.fetchone()[0]
        
        return {
            'rls_enabled': all(rls_status.values()),
            'tables_with_rls': rls_status,
            'isolated_customers': isolated_customers
        }

    def test_personality_preferences_functionality(self) -> Dict[str, any]:
        """Test premium-casual personality preference storage"""
        test_customer_id = '00000000-0000-0000-0000-000000000001'
        
        # Test personality preference insertion
        start_time = time.time()
        self.cur.execute("""
            INSERT INTO customer_personality_preferences (
                customer_id,
                communication_style,
                tone_preferences,
                channel_preferences,
                delegation_preferences
            ) VALUES (
                %s,
                'premium_casual',
                '{"formality_level": "premium_casual", "humor_style": "light_professional"}',
                '{"email": {"preferred": true, "response_time": "within_1_hour"}}',
                '{"auto_delegate_social_media": true}'
            ) ON CONFLICT (customer_id) DO UPDATE SET
                communication_style = EXCLUDED.communication_style,
                updated_at = CURRENT_TIMESTAMP
        """, (test_customer_id,))
        
        insert_time = (time.time() - start_time) * 1000
        
        # Test preference retrieval
        start_time = time.time()
        self.cur.execute("""
            SELECT communication_style, tone_preferences, channel_preferences 
            FROM customer_personality_preferences 
            WHERE customer_id = %s
        """, (test_customer_id,))
        
        result = self.cur.fetchone()
        query_time = (time.time() - start_time) * 1000
        
        self.conn.commit()
        
        return {
            'insert_performance_ms': insert_time,
            'query_performance_ms': query_time,
            'preferences_stored': result is not None,
            'communication_style': result[0] if result else None,
            'jsonb_functionality': isinstance(result[1], dict) if result else False
        }

    def test_cross_channel_context_preservation(self) -> Dict[str, any]:
        """Test cross-channel conversation context functionality"""
        test_customer_id = '00000000-0000-0000-0000-000000000001'
        context_id = f'test-context-{int(time.time())}'
        
        # Test context creation
        start_time = time.time()
        self.cur.execute("""
            INSERT INTO conversation_context (
                context_id,
                customer_id,
                channel_type,
                conversation_summary,
                key_topics,
                action_items,
                assigned_agents,
                importance_score
            ) VALUES (
                %s, %s, 'whatsapp',
                'Customer discussed premium casual communication preferences for EA interactions',
                '["communication", "preferences", "ea_interaction"]',
                '[{"task": "Update EA personality", "priority": "high"}]',
                '["social_media_manager", "business_agent"]',
                0.8
            )
        """, (context_id, test_customer_id))
        
        creation_time = (time.time() - start_time) * 1000
        
        # Test context retrieval with <500ms SLA requirement
        start_time = time.time()
        self.cur.execute("""
            SELECT context_id, conversation_summary, key_topics, 
                   action_items, assigned_agents, importance_score,
                   context_freshness_score
            FROM conversation_context 
            WHERE customer_id = %s AND context_id = %s
        """, (test_customer_id, context_id))
        
        result = self.cur.fetchone()
        retrieval_time = (time.time() - start_time) * 1000
        
        # Test channel transition
        self.cur.execute("""
            INSERT INTO conversation_context_transitions (
                context_id, customer_id, from_channel, to_channel,
                transition_reason, preserved_context, 
                transition_latency_ms, context_preservation_score
            ) VALUES (
                %s, %s, 'whatsapp', 'email',
                'detailed_response_required',
                '{"summary": "Premium casual preferences discussion"}',
                150, 0.95
            )
        """, (context_id, test_customer_id))
        
        self.conn.commit()
        
        return {
            'creation_performance_ms': creation_time,
            'retrieval_performance_ms': retrieval_time,
            'meets_sla_requirement': retrieval_time < 500,  # <500ms SLA
            'context_preserved': result is not None,
            'jsonb_arrays_working': len(result[2]) > 0 if result else False,
            'importance_scoring': result[5] == 0.8 if result else False,
            'channel_transition_logged': True  # If we got here without error
        }

    def test_personal_brand_metrics_tracking(self) -> Dict[str, any]:
        """Test personal brand metrics and career advancement tracking"""
        test_customer_id = '00000000-0000-0000-0000-000000000001'
        
        # Test metrics insertion
        start_time = time.time()
        self.cur.execute("""
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
                revenue_correlation,
                measured_at
            ) VALUES (
                %s, 'social_media_engagement', 1250.0, 'followers',
                1000.0, 2000.0, 'improving', 'weekly',
                'social_media_agent', 
                '["social_media_manager", "marketing_agent"]',
                0.65, CURRENT_TIMESTAMP
            )
        """, (test_customer_id,))
        
        insert_time = (time.time() - start_time) * 1000
        
        # Test metrics retrieval and analysis
        start_time = time.time()
        self.cur.execute("""
            SELECT metric_type, metric_value, performance_category,
                   contributing_agents, revenue_correlation
            FROM personal_brand_metrics 
            WHERE customer_id = %s AND metric_type = 'social_media_engagement'
            ORDER BY measured_at DESC LIMIT 1
        """, (test_customer_id,))
        
        result = self.cur.fetchone()
        query_time = (time.time() - start_time) * 1000
        
        self.conn.commit()
        
        return {
            'insert_performance_ms': insert_time,
            'query_performance_ms': query_time,
            'metrics_stored': result is not None,
            'performance_categorization': result[2] == 'improving' if result else False,
            'agent_attribution_tracked': len(result[3]) > 0 if result else False,
            'revenue_correlation_tracked': result[4] == 0.65 if result else False
        }

    def test_voice_interaction_logging(self) -> Dict[str, any]:
        """Test voice interaction logging for ElevenLabs integration"""
        test_customer_id = '00000000-0000-0000-0000-000000000001'
        interaction_id = f'test-voice-{int(time.time())}'
        
        # Test voice log insertion
        start_time = time.time()
        self.cur.execute("""
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
                conversation_summary,
                key_intents_detected,
                delegated_to_agents,
                sla_compliance,
                started_at,
                completed_at
            ) VALUES (
                %s, %s, 'ea_conversation', 'en', 'en',
                45.5, 120, 180, 250, 1800,
                0.95, 0.92,
                'Customer requested social media campaign update in premium casual tone',
                '["campaign_update", "social_media", "premium_casual"]',
                '["social_media_manager"]',
                true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '46 seconds'
            )
        """, (interaction_id, test_customer_id))
        
        insert_time = (time.time() - start_time) * 1000
        
        # Test voice log retrieval
        start_time = time.time()
        self.cur.execute("""
            SELECT interaction_id, session_type, language_detected,
                   total_processing_time_ms, sla_compliance,
                   transcription_confidence, key_intents_detected
            FROM voice_interaction_logs 
            WHERE customer_id = %s AND interaction_id = %s
        """, (test_customer_id, interaction_id))
        
        result = self.cur.fetchone()
        query_time = (time.time() - start_time) * 1000
        
        self.conn.commit()
        
        return {
            'insert_performance_ms': insert_time,
            'query_performance_ms': query_time,
            'voice_logs_stored': result is not None,
            'sla_tracking': result[4] if result else False,
            'quality_metrics_tracked': result[5] > 0.9 if result else False,
            'intent_detection_logged': len(result[6]) > 0 if result else False,
            'response_time_logged': result[3] == 1800 if result else False
        }

    def test_performance_indexes(self) -> Dict[str, any]:
        """Test that performance indexes are in place"""
        # Check for critical performance indexes
        self.cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE (indexname LIKE 'idx_%personality%' 
               OR indexname LIKE 'idx_%conversation%' 
               OR indexname LIKE 'idx_%brand%'
               OR indexname LIKE 'idx_%voice%')
            AND schemaname = 'public'
        """)
        
        indexes = [row[0] for row in self.cur.fetchall()]
        
        # Test query performance with indexes
        test_customer_id = '00000000-0000-0000-0000-000000000001'
        
        performance_tests = []
        
        # Test personality preferences index
        start_time = time.time()
        self.cur.execute("""
            SELECT * FROM customer_personality_preferences 
            WHERE customer_id = %s
        """, (test_customer_id,))
        performance_tests.append(('personality_lookup', (time.time() - start_time) * 1000))
        
        # Test conversation context index
        start_time = time.time()
        self.cur.execute("""
            SELECT * FROM conversation_context 
            WHERE customer_id = %s 
            ORDER BY last_activity_at DESC LIMIT 10
        """, (test_customer_id,))
        performance_tests.append(('context_lookup', (time.time() - start_time) * 1000))
        
        return {
            'total_indexes_found': len(indexes),
            'index_names': indexes,
            'performance_tests': performance_tests,
            'all_queries_under_100ms': all(time_ms < 100 for _, time_ms in performance_tests)
        }

    def run_all_tests(self) -> Dict[str, any]:
        """Run comprehensive Phase 2 database validation"""
        print("🔍 Running Phase 2 Database Schema Validation Tests...")
        
        results = {
            'test_timestamp': datetime.now().isoformat(),
            'schema_exists': self.test_schema_exists(),
            'customer_isolation': self.test_customer_isolation(),
            'personality_preferences': self.test_personality_preferences_functionality(),
            'cross_channel_context': self.test_cross_channel_context_preservation(),
            'brand_metrics': self.test_personal_brand_metrics_tracking(),
            'voice_interaction': self.test_voice_interaction_logging(),
            'performance_indexes': self.test_performance_indexes()
        }
        
        # Calculate overall success metrics
        all_tables_exist = all(results['schema_exists'].values())
        performance_met = (
            results['personality_preferences']['query_performance_ms'] < 100 and
            results['cross_channel_context']['retrieval_performance_ms'] < 500 and
            results['brand_metrics']['query_performance_ms'] < 100 and
            results['voice_interaction']['query_performance_ms'] < 100 and
            results['performance_indexes']['all_queries_under_100ms']
        )
        
        results['validation_summary'] = {
            'all_tables_exist': all_tables_exist,
            'customer_isolation_verified': results['customer_isolation']['rls_enabled'],
            'performance_targets_met': performance_met,
            'cross_channel_sla_met': results['cross_channel_context']['meets_sla_requirement'],
            'total_indexes': results['performance_indexes']['total_indexes_found'],
            'overall_success': all_tables_exist and performance_met
        }
        
        return results

def main():
    """Main test execution"""
    validator = Phase2DatabaseValidator()
    
    try:
        results = validator.run_all_tests()
        
        print("\n" + "="*60)
        print("PHASE 2 DATABASE SCHEMA VALIDATION RESULTS")
        print("="*60)
        
        summary = results['validation_summary']
        
        print(f"✅ All Required Tables Exist: {summary['all_tables_exist']}")
        print(f"✅ Customer Isolation Verified: {summary['customer_isolation_verified']}")
        print(f"✅ Performance Targets Met: {summary['performance_targets_met']}")
        print(f"✅ Cross-Channel SLA (<500ms): {summary['cross_channel_sla_met']}")
        print(f"✅ Performance Indexes: {summary['total_indexes']}")
        
        print(f"\n🎯 OVERALL SUCCESS: {summary['overall_success']}")
        
        if summary['overall_success']:
            print("\n🚀 Phase 2 database schema is ready for EA Orchestration!")
            print("   • Premium-casual personality system: READY")
            print("   • Cross-channel context preservation: READY") 
            print("   • Personal brand metrics tracking: READY")
            print("   • Voice interaction logging: READY")
            print("   • Performance optimization: READY")
        else:
            print("\n⚠️  Some requirements not fully met. Check detailed results.")
            
        # Print detailed performance metrics
        print(f"\nPerformance Metrics:")
        print(f"  • Personality preferences query: {results['personality_preferences']['query_performance_ms']:.2f}ms")
        print(f"  • Context retrieval: {results['cross_channel_context']['retrieval_performance_ms']:.2f}ms")
        print(f"  • Brand metrics query: {results['brand_metrics']['query_performance_ms']:.2f}ms") 
        print(f"  • Voice interaction query: {results['voice_interaction']['query_performance_ms']:.2f}ms")
        
        return 0 if summary['overall_success'] else 1
        
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        return 1
    finally:
        validator.cleanup()

if __name__ == '__main__':
    exit(main())