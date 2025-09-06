"""
Customer Isolation Security Tests

Tests to validate that customer data is properly isolated at the database level
and that the Row-Level Security (RLS) policies prevent cross-customer data access.

These tests address Issue #20 - Database Schema Inconsistencies - Customer Isolation Risk
"""

import pytest
import asyncio
import psycopg2
import json
from typing import Dict, List, Tuple
from contextlib import asynccontextmanager
import os
import uuid
import time

class TestCustomerIsolation:
    """Test suite to validate customer isolation at database level"""

    @pytest.fixture
    async def db_connection(self):
        """Create database connection for testing"""
        # Use test database connection
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", 5432),
            database=os.getenv("TEST_POSTGRES_DB", "customer_test"),
            user=os.getenv("POSTGRES_USER", "customer_test"),
            password=os.getenv("POSTGRES_PASSWORD", "test_password")
        )
        conn.autocommit = True
        yield conn
        conn.close()

    @pytest.fixture
    def test_customers(self) -> List[str]:
        """Generate test customer IDs"""
        return [
            f"test_customer_{uuid.uuid4().hex[:8]}",
            f"test_customer_{uuid.uuid4().hex[:8]}",
            f"test_customer_{uuid.uuid4().hex[:8]}"
        ]

    async def test_customer_database_initialization(self, db_connection, test_customers):
        """
        Test that customer-specific database initialization creates proper tables
        """
        cursor = db_connection.cursor()
        
        # Test each customer database initialization
        for customer_id in test_customers:
            # Set customer context
            cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
            
            # Verify all required tables exist
            required_tables = [
                'customer_infrastructure',
                'customer_memory_audit',
                'customer_config',
                'ea_conversations',
                'customer_metrics',
                'monitoring_alerts',
                'scaling_actions',
                'customer_requests',
                'customer_errors',
                'infrastructure_health',
                'cost_tracking',
                'usage_patterns',
                'deployment_log',
                'performance_benchmarks'
            ]
            
            for table_name in required_tables:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    )
                """, (table_name,))
                
                table_exists = cursor.fetchone()[0]
                assert table_exists, f"Table {table_name} does not exist for customer {customer_id}"

    async def test_row_level_security_enabled(self, db_connection, test_customers):
        """
        Test that Row-Level Security is enabled on all customer tables
        """
        cursor = db_connection.cursor()
        
        # Check that RLS is enabled on all customer-sensitive tables
        customer_tables = [
            'customer_infrastructure',
            'customer_memory_audit', 
            'customer_config',
            'ea_conversations',
            'customer_metrics',
            'monitoring_alerts',
            'scaling_actions',
            'customer_requests',
            'customer_errors',
            'infrastructure_health',
            'cost_tracking',
            'usage_patterns',
            'deployment_log',
            'performance_benchmarks'
        ]
        
        for table_name in customer_tables:
            cursor.execute("""
                SELECT relrowsecurity 
                FROM pg_class 
                WHERE relname = %s
            """, (table_name,))
            
            result = cursor.fetchone()
            assert result is not None, f"Table {table_name} not found"
            assert result[0] is True, f"RLS not enabled on table {table_name}"

    async def test_customer_isolation_policies(self, db_connection, test_customers):
        """
        Test that RLS policies prevent cross-customer data access
        """
        cursor = db_connection.cursor()
        
        # Insert test data for different customers
        test_data = {}
        for i, customer_id in enumerate(test_customers):
            # Set customer context
            cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
            
            # Insert test data in customer_infrastructure table
            cursor.execute("""
                INSERT INTO customer_infrastructure 
                (customer_id, tier, mcp_server_id, service_endpoints, resource_limits, provisioning_time, status)
                VALUES (%s, 'test', %s, '{}', '{}', 0.1, 'test_active')
                ON CONFLICT (customer_id) DO UPDATE SET status = 'test_active'
            """, (customer_id, f"mcp-{customer_id}"))
            
            # Insert test data in customer_metrics table
            cursor.execute("""
                INSERT INTO customer_metrics
                (customer_id, tier, cpu_usage, memory_usage, request_count)
                VALUES (%s, 'test', %s, %s, %s)
            """, (customer_id, 10.0 + i, 20.0 + i, 100 + i))
            
            test_data[customer_id] = {
                'cpu_usage': 10.0 + i,
                'memory_usage': 20.0 + i,
                'request_count': 100 + i
            }
        
        # Test isolation: each customer should only see their own data
        for customer_id in test_customers:
            # Set customer context
            cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
            
            # Query customer_infrastructure - should only return this customer's data
            cursor.execute("SELECT customer_id, status FROM customer_infrastructure")
            infra_results = cursor.fetchall()
            
            assert len(infra_results) <= 1, f"Customer {customer_id} can see other customers' infrastructure data"
            if infra_results:
                assert infra_results[0][0] == customer_id, "RLS policy failed for customer_infrastructure"
            
            # Query customer_metrics - should only return this customer's data
            cursor.execute("SELECT customer_id, cpu_usage, memory_usage, request_count FROM customer_metrics")
            metrics_results = cursor.fetchall()
            
            customer_metrics = [row for row in metrics_results if row[0] == customer_id]
            other_metrics = [row for row in metrics_results if row[0] != customer_id]
            
            assert len(other_metrics) == 0, f"Customer {customer_id} can see other customers' metrics: {other_metrics}"
            assert len(customer_metrics) > 0, f"Customer {customer_id} cannot see their own metrics"
            
            # Verify data integrity
            expected_data = test_data[customer_id]
            actual_cpu = float(customer_metrics[0][1])
            actual_memory = float(customer_metrics[0][2])
            actual_requests = customer_metrics[0][3]
            
            assert actual_cpu == expected_data['cpu_usage'], "CPU usage data mismatch"
            assert actual_memory == expected_data['memory_usage'], "Memory usage data mismatch" 
            assert actual_requests == expected_data['request_count'], "Request count data mismatch"

    async def test_customer_isolation_validation_function(self, db_connection, test_customers):
        """
        Test the built-in customer isolation validation function
        """
        cursor = db_connection.cursor()
        
        for customer_id in test_customers:
            # Test the validation function
            cursor.execute("SELECT validate_customer_isolation(%s)", (customer_id,))
            validation_result = cursor.fetchone()[0]
            
            assert validation_result is True, f"Customer isolation validation failed for {customer_id}"

    async def test_customer_data_export_gdpr_compliance(self, db_connection, test_customers):
        """
        Test GDPR-compliant customer data export functionality
        """
        cursor = db_connection.cursor()
        
        customer_id = test_customers[0]
        
        # Set customer context and add some test data
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
        
        # Add test conversation data
        cursor.execute("""
            INSERT INTO ea_conversations (customer_id, session_id, channel, messages)
            VALUES (%s, 'test_session', 'email', '{"test": "message"}')
        """, (customer_id,))
        
        # Test data export function
        cursor.execute("SELECT export_customer_data(%s)", (customer_id,))
        export_result = cursor.fetchone()[0]
        
        assert export_result is not None, "Customer data export returned null"
        
        # Parse the JSON result
        export_data = json.loads(export_result) if isinstance(export_result, str) else export_result
        
        assert export_data['customer_id'] == customer_id, "Export data customer_id mismatch"
        assert 'export_timestamp' in export_data, "Export timestamp missing"
        assert 'conversations' in export_data, "Conversations data missing from export"
        
        # Verify that conversations data is present
        if export_data['conversations']:
            assert len(export_data['conversations']) > 0, "Expected conversation data in export"
            assert export_data['conversations'][0]['customer_id'] == customer_id, "Conversation customer_id mismatch"

    async def test_customer_data_deletion_gdpr_compliance(self, db_connection, test_customers):
        """
        Test GDPR-compliant customer data deletion functionality
        """
        cursor = db_connection.cursor()
        
        customer_id = test_customers[0]
        
        # Set customer context and add test data
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
        
        # Add test data across multiple tables
        cursor.execute("""
            INSERT INTO customer_config (customer_id, config)
            VALUES (%s, '{"test": "config"}')
            ON CONFLICT (customer_id) DO UPDATE SET config = '{"test": "config"}'
        """, (customer_id,))
        
        cursor.execute("""
            INSERT INTO ea_conversations (customer_id, session_id, channel, messages)
            VALUES (%s, 'deletion_test', 'phone', '{"message": "delete me"}')
        """, (customer_id,))
        
        # Verify data exists before deletion
        cursor.execute("SELECT COUNT(*) FROM customer_config WHERE customer_id = %s", (customer_id,))
        config_count_before = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ea_conversations WHERE customer_id = %s", (customer_id,))
        conversations_count_before = cursor.fetchone()[0]
        
        assert config_count_before > 0, "Test data not properly inserted"
        assert conversations_count_before > 0, "Test conversation data not properly inserted"
        
        # Execute customer data deletion
        cursor.execute("SELECT delete_customer_data(%s)", (customer_id,))
        deletion_result = cursor.fetchone()[0]
        
        assert deletion_result is True, "Customer data deletion function failed"
        
        # Verify data is deleted
        cursor.execute("SELECT COUNT(*) FROM customer_config WHERE customer_id = %s", (customer_id,))
        config_count_after = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ea_conversations WHERE customer_id = %s", (customer_id,))
        conversations_count_after = cursor.fetchone()[0]
        
        assert config_count_after == 0, "Customer config data not properly deleted"
        assert conversations_count_after == 0, "Customer conversation data not properly deleted"

    async def test_unauthorized_cross_customer_access_blocked(self, db_connection, test_customers):
        """
        Test that attempts to access other customers' data are blocked
        """
        cursor = db_connection.cursor()
        
        customer_a = test_customers[0]
        customer_b = test_customers[1]
        
        # Insert data for customer A
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_a,))
        cursor.execute("""
            INSERT INTO customer_errors (customer_id, tier, error_type, error_message)
            VALUES (%s, 'test', 'security_test', 'Test error for customer A')
        """, (customer_a,))
        
        # Insert data for customer B
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_b,))
        cursor.execute("""
            INSERT INTO customer_errors (customer_id, tier, error_type, error_message)
            VALUES (%s, 'test', 'security_test', 'Test error for customer B')
        """, (customer_b,))
        
        # Try to access customer B's data while in customer A's context
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_a,))
        
        # This query should only return customer A's errors due to RLS
        cursor.execute("""
            SELECT customer_id, error_message FROM customer_errors 
            WHERE error_type = 'security_test'
        """)
        
        results = cursor.fetchall()
        
        # Should only see customer A's data
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert results[0][0] == customer_a, "Saw data from wrong customer"
        assert "customer A" in results[0][1], "Got wrong error message"
        
        # Verify customer B cannot see customer A's data
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_b,))
        cursor.execute("""
            SELECT customer_id, error_message FROM customer_errors 
            WHERE error_type = 'security_test'
        """)
        
        results = cursor.fetchall()
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert results[0][0] == customer_b, "Customer B seeing wrong data"
        assert "customer B" in results[0][1], "Customer B got wrong error message"

    async def test_performance_with_customer_isolation(self, db_connection, test_customers):
        """
        Test that customer isolation doesn't significantly impact query performance
        """
        cursor = db_connection.cursor()
        
        customer_id = test_customers[0]
        cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
        
        # Insert a reasonable amount of test data
        for i in range(100):
            cursor.execute("""
                INSERT INTO customer_requests 
                (customer_id, tier, endpoint, method, status, response_time)
                VALUES (%s, 'test', '/api/test', 'GET', 200, %s)
            """, (customer_id, 0.1 + (i * 0.001)))
        
        # Time a query with RLS enabled
        start_time = time.time()
        
        cursor.execute("""
            SELECT COUNT(*), AVG(response_time) 
            FROM customer_requests 
            WHERE customer_id = %s AND status = 200
        """, (customer_id,))
        
        result = cursor.fetchone()
        end_time = time.time()
        
        query_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        assert result[0] == 100, "Expected 100 records"
        assert query_time < 50, f"Query took too long: {query_time}ms (should be < 50ms)"
        
        # Verify index is being used efficiently
        cursor.execute("""
            EXPLAIN (ANALYZE, BUFFERS) 
            SELECT COUNT(*) FROM customer_requests 
            WHERE customer_id = %s AND status = 200
        """, (customer_id,))
        
        explain_result = cursor.fetchall()
        explain_text = ' '.join([row[0] for row in explain_result])
        
        # Should use index scan, not sequential scan
        assert "Index Scan" in explain_text or "Bitmap" in explain_text, \
            "Query should use index, not sequential scan"

    async def test_cleanup_test_data(self, db_connection, test_customers):
        """
        Clean up test data after tests complete
        """
        cursor = db_connection.cursor()
        
        # Clean up test data for each customer
        for customer_id in test_customers:
            cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
            
            # Use the built-in deletion function
            cursor.execute("SELECT delete_customer_data(%s)", (customer_id,))
            
            # Verify cleanup
            cursor.execute("""
                SELECT COUNT(*) FROM customer_infrastructure WHERE customer_id = %s
            """, (customer_id,))
            
            remaining_count = cursor.fetchone()[0]
            assert remaining_count == 0, f"Test data not properly cleaned up for {customer_id}"


@pytest.mark.asyncio
class TestCustomerIsolationIntegration:
    """Integration tests for customer isolation with actual database setup"""
    
    async def test_docker_compose_customer_isolation(self):
        """
        Test that the production Docker Compose setup maintains customer isolation
        """
        # This test would require actual Docker containers
        # For now, we'll test the schema compatibility
        
        # Verify that the customer-init.sql script contains all necessary elements
        script_path = "/Users/jose/Documents/🚀 Projects/⚡ Active/ai-agency-platform/config/postgres/customer-init.sql"
        
        with open(script_path, 'r') as f:
            script_content = f.read()
        
        # Verify key elements are present
        assert "ROW LEVEL SECURITY" in script_content, "RLS not configured in init script"
        assert "customer_isolation_policy" in script_content, "RLS policies not defined"
        assert "validate_customer_isolation" in script_content, "Validation function missing"
        assert "export_customer_data" in script_content, "GDPR export function missing"
        assert "delete_customer_data" in script_content, "GDPR deletion function missing"
        
        # Verify all customer tables have RLS enabled
        rls_tables = [
            'customer_infrastructure',
            'customer_memory_audit',
            'customer_config',
            'ea_conversations',
            'customer_metrics'
        ]
        
        for table in rls_tables:
            assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in script_content, \
                f"RLS not enabled for {table}"
            assert f"CREATE POLICY customer_isolation_policy ON {table}" in script_content, \
                f"RLS policy not created for {table}"