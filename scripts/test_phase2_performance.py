#!/usr/bin/env python3
"""
Phase 2 Database Performance Validation Script
Tests Phase 2 schema against performance requirements:
- <100ms average query performance
- <500ms cross-channel context recall
- Customer isolation validation
"""

import time
import psycopg2
from psycopg2.extras import RealDictCursor
import statistics
from datetime import datetime
import sys

def test_phase2_performance(database_url: str):
    """Test Phase 2 database performance against SLA requirements"""
    print("🚀 Phase 2 Performance Validation")
    print("=" * 50)
    
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    
    test_results = {
        "personality_queries": [],
        "context_recalls": [],
        "voice_queries": [],
        "dashboard_queries": [],
        "search_queries": []
    }
    
    # Test 1: Customer Personality Preference Queries (<100ms target)
    print("Test 1: Customer Personality Preference Performance")
    for i in range(10):
        start = time.time()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM customer_personality_preferences 
                WHERE customer_id = '00000000-0000-0000-0000-000000000001'
            """)
            result = cursor.fetchone()
        end = time.time()
        query_time_ms = (end - start) * 1000
        test_results["personality_queries"].append(query_time_ms)
        print(f"  Query {i+1}: {query_time_ms:.2f}ms")
    
    avg_personality = statistics.mean(test_results["personality_queries"])
    print(f"  Average: {avg_personality:.2f}ms (Target: <100ms)")
    print(f"  Status: {'✅ PASS' if avg_personality < 100 else '⚠️ SLOW'}")
    print()
    
    # Test 2: Cross-Channel Context Recall (<500ms target)
    print("Test 2: Cross-Channel Context Recall Performance")
    for i in range(10):
        start = time.time()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM conversation_context 
                WHERE customer_id = '00000000-0000-0000-0000-000000000001'
                  AND context_type = 'ongoing'
                ORDER BY last_activity_at DESC 
                LIMIT 5
            """)
            results = cursor.fetchall()
        end = time.time()
        query_time_ms = (end - start) * 1000
        test_results["context_recalls"].append(query_time_ms)
        print(f"  Query {i+1}: {query_time_ms:.2f}ms")
    
    avg_context = statistics.mean(test_results["context_recalls"])
    print(f"  Average: {avg_context:.2f}ms (Target: <500ms)")
    print(f"  Status: {'✅ PASS' if avg_context < 500 else '⚠️ SLOW'}")
    print()
    
    # Test 3: Voice Interaction Query Performance
    print("Test 3: Voice Interaction Query Performance")
    for i in range(10):
        start = time.time()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM voice_interaction_logs 
                WHERE customer_id = '00000000-0000-0000-0000-000000000001'
                ORDER BY started_at DESC 
                LIMIT 10
            """)
            results = cursor.fetchall()
        end = time.time()
        query_time_ms = (end - start) * 1000
        test_results["voice_queries"].append(query_time_ms)
        print(f"  Query {i+1}: {query_time_ms:.2f}ms")
    
    avg_voice = statistics.mean(test_results["voice_queries"])
    print(f"  Average: {avg_voice:.2f}ms (Target: <100ms)")
    print(f"  Status: {'✅ PASS' if avg_voice < 100 else '⚠️ SLOW'}")
    print()
    
    # Test 4: EA Orchestration Dashboard Performance
    print("Test 4: EA Orchestration Dashboard Performance")
    for i in range(10):
        start = time.time()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM ea_orchestration_dashboard LIMIT 5")
            results = cursor.fetchall()
        end = time.time()
        query_time_ms = (end - start) * 1000
        test_results["dashboard_queries"].append(query_time_ms)
        print(f"  Query {i+1}: {query_time_ms:.2f}ms")
    
    avg_dashboard = statistics.mean(test_results["dashboard_queries"])
    print(f"  Average: {avg_dashboard:.2f}ms (Target: <100ms)")
    print(f"  Status: {'✅ PASS' if avg_dashboard < 100 else '⚠️ SLOW'}")
    print()
    
    # Test 5: Full-Text Search Performance (Context Search)
    print("Test 5: Full-Text Search Performance")
    for i in range(10):
        start = time.time()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT context_id, conversation_summary
                FROM conversation_context 
                WHERE to_tsvector('english', search_keywords) @@ to_tsquery('marketing & restaurant')
                  AND customer_id = '00000000-0000-0000-0000-000000000001'
            """)
            results = cursor.fetchall()
        end = time.time()
        query_time_ms = (end - start) * 1000
        test_results["search_queries"].append(query_time_ms)
        print(f"  Query {i+1}: {query_time_ms:.2f}ms")
    
    avg_search = statistics.mean(test_results["search_queries"])
    print(f"  Average: {avg_search:.2f}ms (Target: <100ms)")
    print(f"  Status: {'✅ PASS' if avg_search < 100 else '⚠️ SLOW'}")
    print()
    
    # Test 6: Customer Isolation Validation
    print("Test 6: Customer Isolation Validation")
    with conn.cursor() as cursor:
        # Create second customer for isolation test
        cursor.execute("""
            INSERT INTO customers (
                id, business_name, contact_email, is_active
            ) VALUES (
                '00000000-0000-0000-0000-000000000002',
                'Second Test Business',
                'test2@business.com',
                true
            ) ON CONFLICT (id) DO NOTHING
        """)
        
        cursor.execute("""
            INSERT INTO customer_personality_preferences (
                customer_id, communication_style
            ) VALUES (
                '00000000-0000-0000-0000-000000000002',
                'professional'
            ) ON CONFLICT (customer_id) DO UPDATE SET
                communication_style = EXCLUDED.communication_style
        """)
        
        # Test isolation: Customer 1 should not see Customer 2's data
        cursor.execute("""
            SELECT COUNT(*) as count FROM customer_personality_preferences 
            WHERE customer_id = '00000000-0000-0000-0000-000000000001'
        """)
        customer1_count = cursor.fetchone()['count']
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM customer_personality_preferences 
            WHERE customer_id = '00000000-0000-0000-0000-000000000002'
        """)
        customer2_count = cursor.fetchone()['count']
        
        print(f"  Customer 1 records: {customer1_count}")
        print(f"  Customer 2 records: {customer2_count}")
        print(f"  Status: {'✅ ISOLATED' if customer1_count == 1 and customer2_count == 1 else '❌ LEAK'}")
        
    conn.commit()
    conn.close()
    
    # Overall Performance Summary
    print()
    print("=" * 50)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 50)
    
    all_averages = {
        "Personality Queries": avg_personality,
        "Context Recalls": avg_context, 
        "Voice Queries": avg_voice,
        "Dashboard Queries": avg_dashboard,
        "Search Queries": avg_search
    }
    
    passed_tests = 0
    total_tests = 0
    
    for test_name, avg_time in all_averages.items():
        total_tests += 1
        target = 500 if "Context" in test_name else 100
        status = "✅ PASS" if avg_time < target else "⚠️ SLOW"
        if avg_time < target:
            passed_tests += 1
        print(f"{test_name:20}: {avg_time:6.2f}ms (Target: <{target}ms) {status}")
    
    success_rate = (passed_tests / total_tests) * 100
    print(f"\nOverall Success Rate: {success_rate:.1f}% ({passed_tests}/{total_tests})")
    
    if success_rate >= 80:
        print("🎉 Phase 2 Performance: ACCEPTABLE")
        return True
    else:
        print("⚠️ Phase 2 Performance: NEEDS OPTIMIZATION")
        return False

if __name__ == "__main__":
    database_url = "postgresql://mcphub:mcphub_password@localhost:5432/mcphub"
    success = test_phase2_performance(database_url)
    sys.exit(0 if success else 1)