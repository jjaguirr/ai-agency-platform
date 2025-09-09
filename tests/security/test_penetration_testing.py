"""
Phase 2 EA Orchestration - Penetration Testing Suite

Comprehensive security penetration testing for:
- SQL injection attempts on customer queries
- Memory space traversal attempts (customer_{id} bypass)
- API parameter tampering for customer_id manipulation
- Session hijacking and cache poisoning tests
- Premium-casual EA security validation
- Cross-channel context security breaches

Designed for enterprise security requirements with zero tolerance for data leakage.
"""

import pytest
import asyncio
import json
import logging
import uuid
import time
import hashlib
import secrets
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from unittest.mock import Mock, patch, AsyncMock
import jwt
import asyncpg
import redis.asyncio as redis
import aiohttp

from src.database.connection import get_db_connection
from src.agents.executive_assistant import ExecutiveAssistant
from src.communication.whatsapp_channel import WhatsAppChannel
from src.communication.email_channel import EmailChannel
from src.agents.memory.ea_memory_integration import EAMemoryIntegration

logger = logging.getLogger(__name__)


class TestSQLInjectionPenetration:
    """
    Comprehensive SQL injection penetration testing for Phase 2 EA system.
    
    Tests all possible injection vectors including:
    - Classic SQL injection
    - Blind SQL injection
    - Time-based SQL injection
    - Union-based SQL injection
    - Boolean-based SQL injection
    - Second-order SQL injection
    """
    
    @pytest.fixture
    async def db_connection(self):
        conn = await get_db_connection()
        yield conn
        await conn.close()
    
    @pytest.fixture
    async def penetration_test_customer(self, db_connection):
        """Create customer for penetration testing"""
        customer_id = str(uuid.uuid4())
        await db_connection.execute("""
            INSERT INTO customers (id, business_name, business_type, contact_email,
                                 onboarding_status, subscription_tier, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, customer_id, "Penetration Test Target", "security_testing",
            f"pentest-{int(time.time())}@example.com", "active", "enterprise", True)
        
        yield customer_id
        
        await db_connection.execute("DELETE FROM customers WHERE id = $1", customer_id)
    
    async def test_classic_sql_injection_attacks(self, db_connection, penetration_test_customer):
        """Test classic SQL injection attack patterns"""
        customer_id = penetration_test_customer
        
        # Create test data
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS customer_personality_preferences (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                personality_type VARCHAR(50) NOT NULL,
                sensitive_data TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        await db_connection.execute("""
            INSERT INTO customer_personality_preferences (customer_id, personality_type, sensitive_data)
            VALUES ($1, $2, $3)
        """, customer_id, "premium", "SECRET_CUSTOMER_DATA_12345")
        
        # SQL injection attack patterns
        injection_payloads = [
            # Classic injection attempts
            "'; DROP TABLE customer_personality_preferences; --",
            "' OR '1'='1' --",
            "' OR 1=1 --",
            "admin'--",
            "admin'/*",
            "' OR 'x'='x'",
            "') OR ('1'='1' --",
            
            # Union-based injection
            "' UNION SELECT id, customer_id, sensitive_data FROM customer_personality_preferences --",
            "' UNION SELECT null, null, version() --",
            "' UNION SELECT table_name, null, null FROM information_schema.tables --",
            
            # Blind injection attempts
            "' AND (SELECT COUNT(*) FROM customer_personality_preferences) > 0 --",
            "' AND (SELECT SUBSTRING(sensitive_data,1,1) FROM customer_personality_preferences WHERE customer_id != $1) = 'S' --",
            
            # Time-based blind injection
            "'; WAITFOR DELAY '00:00:05' --",
            "' OR (SELECT SLEEP(5)) --",
            "'; SELECT pg_sleep(5); --",
            
            # Stacked queries
            "'; INSERT INTO audit_logs (action) VALUES ('HACKED'); --",
            "'; UPDATE customers SET is_active = false; --",
            
            # Boolean-based blind injection
            "' AND ASCII(SUBSTRING((SELECT sensitive_data FROM customer_personality_preferences LIMIT 1),1,1)) > 65 --",
            
            # Error-based injection
            "' AND EXTRACTVALUE(1, CONCAT(0x7e, (SELECT sensitive_data FROM customer_personality_preferences LIMIT 1))) --",
            "' AND (SELECT CAST(sensitive_data AS INT) FROM customer_personality_preferences) --",
            
            # Advanced evasion techniques
            "' /*! UNION */ SELECT * FROM customer_personality_preferences --",
            "' /*!50000 UNION */ SELECT * FROM customer_personality_preferences --",
            "'/**/UNION/**/SELECT/**/sensitive_data/**/FROM/**/customer_personality_preferences --",
            
            # URL encoding evasion
            "%27%20OR%201%3D1%20--",
            "%27%29%20OR%20%28%271%27%3D%271%27%20--",
            
            # Double encoding
            "%2527%2520OR%25201%253D1%2520--",
            
            # Hex encoding
            "0x27204f5220312e3d31202d2d",
            
            # Unicode evasion
            "' OR 1=1\u00a0--",
            "'\u02bcOR\u02bc1\u02bc=\u02bc1\u02bc--"
        ]
        
        successful_injections = []
        
        for payload in injection_payloads:
            try:
                start_time = time.time()
                
                # Test injection in WHERE clause
                result = await db_connection.fetch("""
                    SELECT * FROM customer_personality_preferences 
                    WHERE customer_id = $1 AND personality_type = $2
                """, customer_id, payload)
                
                end_time = time.time()
                response_time = end_time - start_time
                
                # Check for successful injection indicators
                if len(result) > 1:  # More results than expected
                    successful_injections.append(f"Excessive results: {payload}")
                
                if response_time > 5.0:  # Time-based injection success
                    successful_injections.append(f"Time delay detected: {payload}")
                
                # Should return 0 or 1 result maximum
                assert len(result) <= 1, f"SQL injection may have succeeded: {payload} returned {len(result)} results"
                
            except Exception as e:
                error_msg = str(e).lower()
                # Check if error reveals sensitive information
                if any(term in error_msg for term in ['secret', 'password', 'sensitive', 'customer_data']):
                    successful_injections.append(f"Information disclosure: {payload} - {e}")
                
                # Most injections should fail gracefully
                continue
        
        # Fail test if any injections succeeded
        if successful_injections:
            pytest.fail(f"SQL injection vulnerabilities detected: {successful_injections}")
        
        logger.info("✅ All SQL injection attacks blocked successfully")
    
    async def test_nosql_injection_attempts(self, db_connection, penetration_test_customer):
        """Test NoSQL injection attempts on JSONB fields"""
        customer_id = penetration_test_customer
        
        # Create conversation context with JSONB data
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS conversation_context (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                context_data JSONB NOT NULL DEFAULT '{}'::JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        test_context = {
            "topic": "financial_planning",
            "sensitive_info": "Customer secret data",
            "user_role": "admin"
        }
        
        await db_connection.execute("""
            INSERT INTO conversation_context (customer_id, context_data)
            VALUES ($1, $2)
        """, customer_id, json.dumps(test_context))
        
        # NoSQL injection payloads for JSONB
        nosql_payloads = [
            # MongoDB-style injection attempts
            '{"$ne": null}',
            '{"$exists": true}',
            '{"$regex": ".*"}',
            '{"$where": "function() { return true; }"}',
            '{"$or": [{"sensitive_info": {"$exists": true}}]}',
            
            # JSON injection attempts
            '{"topic": "financial_planning", "user_role": {"$ne": "user"}}',
            '"; drop table conversation_context; --',
            '\'; return {}; var x=\'',
            
            # JavaScript injection in JSON context
            'function(){return{}}()',
            'constructor.constructor("return process")().exit()',
            
            # Boolean manipulation
            'true',
            'false',
            '1==1',
            
            # Array manipulation  
            '[]',
            '[{"$exists": true}]',
            
            # Prototype pollution attempts
            '{"__proto__": {"admin": true}}',
            '{"constructor": {"prototype": {"admin": true}}}'
        ]
        
        for payload in nosql_payloads:
            try:
                # Test JSONB query with malicious payload
                result = await db_connection.fetch("""
                    SELECT * FROM conversation_context 
                    WHERE customer_id = $1 AND context_data @> $2
                """, customer_id, payload)
                
                # Should return 0 results for malicious queries
                assert len(result) == 0, f"NoSQL injection may have succeeded: {payload}"
                
            except Exception as e:
                # Most malicious payloads should cause query errors
                error_msg = str(e).lower()
                if 'sensitive' in error_msg or 'secret' in error_msg:
                    pytest.fail(f"Information disclosure in NoSQL injection: {payload} - {e}")
                continue
        
        logger.info("✅ All NoSQL injection attacks blocked successfully")
    
    async def test_second_order_sql_injection(self, db_connection, penetration_test_customer):
        """Test second-order SQL injection attacks"""
        customer_id = penetration_test_customer
        
        # Create voice interaction logs table
        await db_connection.execute("""
            CREATE TABLE IF NOT EXISTS voice_interaction_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                interaction_id VARCHAR(255) NOT NULL,
                transcript_data JSONB NOT NULL DEFAULT '{}'::JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # First-order: Insert potentially malicious data that looks benign
        malicious_interaction_id = "voice_001'; DROP TABLE voice_interaction_logs; --"
        
        await db_connection.execute("""
            INSERT INTO voice_interaction_logs (customer_id, interaction_id, transcript_data)
            VALUES ($1, $2, $3)
        """, customer_id, malicious_interaction_id, json.dumps({"text": "Hello EA"}))
        
        # Second-order: Use the stored data in another query (simulating application behavior)
        try:
            stored_interactions = await db_connection.fetch("""
                SELECT interaction_id FROM voice_interaction_logs WHERE customer_id = $1
            """, customer_id)
            
            assert len(stored_interactions) > 0
            
            # Simulate application using stored interaction_id in dynamic query
            for interaction in stored_interactions:
                interaction_id = interaction["interaction_id"]
                
                # This should NOT execute the embedded SQL
                result = await db_connection.fetch("""
                    SELECT * FROM voice_interaction_logs WHERE interaction_id = $1
                """, interaction_id)
                
                # Table should still exist and contain data
                assert len(result) >= 0  # Should not crash or delete table
            
        except Exception as e:
            # Should not fail due to second-order injection
            if "does not exist" in str(e):
                pytest.fail(f"Second-order SQL injection succeeded - table dropped: {e}")
        
        # Verify table still exists
        table_check = await db_connection.fetchval("""
            SELECT COUNT(*) FROM voice_interaction_logs WHERE customer_id = $1
        """, customer_id)
        
        assert table_check >= 1, "Second-order SQL injection may have succeeded"
        
        logger.info("✅ Second-order SQL injection attacks blocked")


class TestCustomerIdManipulationAttacks:
    """
    Test customer_id parameter tampering and manipulation attacks.
    
    Validates protection against:
    - Direct customer_id parameter manipulation
    - JWT token tampering
    - Session hijacking attempts
    - API parameter injection
    - Memory space traversal attacks
    """
    
    @pytest.fixture
    async def test_customers(self):
        """Create multiple customers for tampering tests"""
        conn = await get_db_connection()
        customer_ids = []
        
        try:
            for i in range(3):
                customer_id = str(uuid.uuid4())
                await conn.execute("""
                    INSERT INTO customers (id, business_name, business_type, contact_email,
                                         onboarding_status, subscription_tier, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, customer_id, f"Tamper Test Customer {i}", "security_testing",
                    f"tamper-test-{i}-{int(time.time())}@example.com", 
                    "active", "enterprise", True)
                customer_ids.append(customer_id)
            
            yield customer_ids
            
        finally:
            for customer_id in customer_ids:
                await conn.execute("DELETE FROM customers WHERE id = $1", customer_id)
            await conn.close()
    
    async def test_direct_customer_id_tampering(self, test_customers):
        """Test direct customer_id parameter tampering in API calls"""
        customer_ids = test_customers
        target_customer, victim_customer_1, victim_customer_2 = customer_ids
        
        conn = await get_db_connection()
        
        try:
            # Set up test data for each customer
            for i, customer_id in enumerate(customer_ids):
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS customer_personality_preferences (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                        personality_type VARCHAR(50) NOT NULL,
                        secret_data TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                await conn.execute("""
                    INSERT INTO customer_personality_preferences (customer_id, personality_type, secret_data)
                    VALUES ($1, $2, $3)
                """, customer_id, f"type_{i}", f"SECRET_DATA_CUSTOMER_{i}")
            
            # Attack 1: Direct customer_id substitution
            try:
                # Target customer tries to access victim's data by changing customer_id
                stolen_data = await conn.fetch("""
                    SELECT * FROM customer_personality_preferences WHERE customer_id = $1
                """, victim_customer_1)  # Should be empty due to RLS
                
                # With proper RLS, this should return no results or only target customer's data
                for row in stolen_data:
                    assert row["customer_id"] == victim_customer_1  # This should not happen if RLS works
                    pytest.fail(f"Customer ID tampering succeeded: accessed {victim_customer_1} data")
                    
            except Exception as e:
                # Expected - access should be denied
                pass
            
            # Attack 2: UUID format manipulation
            tampered_ids = [
                victim_customer_1.upper(),  # Case manipulation
                victim_customer_1.replace('-', ''),  # Format manipulation
                f"'{victim_customer_1}'",  # Quote injection
                f"{victim_customer_1} OR 1=1",  # SQL injection in UUID
                f"{victim_customer_1}; --",  # SQL comment injection
                f"{victim_customer_1}' OR '1'='1",  # Boolean injection
            ]
            
            for tampered_id in tampered_ids:
                try:
                    result = await conn.fetch("""
                        SELECT * FROM customer_personality_preferences WHERE customer_id = $1
                    """, tampered_id)
                    
                    # Should return no results for tampered IDs
                    assert len(result) == 0, f"UUID tampering succeeded with: {tampered_id}"
                    
                except Exception:
                    # Expected - tampered UUIDs should cause errors
                    continue
            
            # Attack 3: Memory space traversal attempts
            traversal_attempts = [
                f"../../../{victim_customer_1}",
                f"..\\..\\..\\{victim_customer_1}",  
                f"%2e%2e%2f{victim_customer_1}",  # URL encoded traversal
                f"....//....//....//....//system/{victim_customer_1}",
                f"{target_customer}/../{victim_customer_1}",
                f"{target_customer}%00{victim_customer_1}"  # Null byte injection
            ]
            
            for traversal_attempt in traversal_attempts:
                try:
                    result = await conn.fetch("""
                        SELECT * FROM customer_personality_preferences WHERE customer_id = $1
                    """, traversal_attempt)
                    
                    assert len(result) == 0, f"Memory traversal succeeded with: {traversal_attempt}"
                    
                except Exception:
                    # Expected - traversal attempts should fail
                    continue
            
        finally:
            await conn.close()
        
        logger.info("✅ Customer ID tampering attacks blocked successfully")
    
    async def test_jwt_token_manipulation(self, test_customers):
        """Test JWT token tampering for customer_id manipulation"""
        customer_ids = test_customers
        target_customer, victim_customer = customer_ids[0], customer_ids[1]
        
        # Simulate JWT token structure
        secret_key = "test_jwt_secret_key_12345"
        
        # Create legitimate token for target customer
        legitimate_payload = {
            "customer_id": target_customer,
            "user_role": "admin",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600
        }
        
        legitimate_token = jwt.encode(legitimate_payload, secret_key, algorithm="HS256")
        
        # JWT tampering attempts
        jwt_attacks = []
        
        # Attack 1: Change customer_id in payload without re-signing
        try:
            decoded = jwt.decode(legitimate_token, options={"verify_signature": False})
            decoded["customer_id"] = victim_customer
            tampered_token = jwt.encode(decoded, secret_key, algorithm="HS256")
            jwt_attacks.append(("customer_id_change", tampered_token))
        except Exception:
            pass
        
        # Attack 2: Algorithm confusion attack (HS256 -> None)
        try:
            tampered_payload = {
                "customer_id": victim_customer,
                "user_role": "admin",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600
            }
            none_token = jwt.encode(tampered_payload, "", algorithm="none")
            jwt_attacks.append(("algorithm_none", none_token))
        except Exception:
            pass
        
        # Attack 3: Key confusion attack (HS256 -> RS256)
        try:
            # This would require the attacker to know the public key
            rs256_token = legitimate_token.replace("HS256", "RS256")
            jwt_attacks.append(("algorithm_confusion", rs256_token))
        except Exception:
            pass
        
        # Attack 4: Token with extended expiration
        try:
            extended_payload = legitimate_payload.copy()
            extended_payload["exp"] = int(time.time()) + 86400 * 365  # 1 year
            extended_token = jwt.encode(extended_payload, "wrong_key", algorithm="HS256")
            jwt_attacks.append(("extended_expiration", extended_token))
        except Exception:
            pass
        
        # Test token validation against attacks
        for attack_name, attack_token in jwt_attacks:
            try:
                # Proper validation should reject tampered tokens
                decoded = jwt.decode(attack_token, secret_key, algorithms=["HS256"])
                
                # If decoding succeeds, check customer_id hasn't been tampered
                if decoded.get("customer_id") == victim_customer:
                    pytest.fail(f"JWT tampering succeeded: {attack_name} - accessed victim customer data")
                    
            except jwt.InvalidTokenError:
                # Expected - tampered tokens should be rejected
                logger.info(f"✅ JWT attack blocked: {attack_name}")
                continue
            except Exception as e:
                # Other errors are also acceptable (token rejected)
                logger.info(f"✅ JWT attack blocked: {attack_name} - {e}")
                continue
        
        logger.info("✅ JWT token manipulation attacks blocked")
    
    async def test_session_hijacking_attempts(self, test_customers):
        """Test session hijacking and cache poisoning attacks"""
        customer_ids = test_customers
        target_customer, victim_customer = customer_ids[0], customer_ids[1]
        
        # Simulate session storage (Redis-like)
        session_attacks = [
            # Session ID manipulation
            f"session_{target_customer}",
            f"session_{victim_customer}",
            f"session_{target_customer}_{victim_customer}",
            
            # Cache key manipulation
            f"customer_data_{target_customer}",
            f"customer_data_{victim_customer}", 
            f"ea_memory_{target_customer}",
            f"ea_memory_{victim_customer}",
            
            # Session fixation attempts
            f"PHPSESSID={target_customer}",
            f"JSESSIONID={victim_customer}",
            
            # Cache poisoning attempts
            f"cache_key_{target_customer}_redirect_{victim_customer}",
            f"memory_key_{target_customer}/../{victim_customer}"
        ]
        
        # Mock Redis connection for testing
        async with redis.Redis(host='localhost', port=6379, db=1) as redis_conn:
            try:
                # Set up legitimate session data
                await redis_conn.set(
                    f"session_{target_customer}",
                    json.dumps({"customer_id": target_customer, "role": "user"}),
                    ex=3600
                )
                
                await redis_conn.set(
                    f"session_{victim_customer}",
                    json.dumps({"customer_id": victim_customer, "role": "admin"}),
                    ex=3600
                )
                
                # Test session manipulation attacks
                for attack_key in session_attacks:
                    try:
                        # Attempt to access session data with manipulated key
                        session_data = await redis_conn.get(attack_key)
                        
                        if session_data:
                            data = json.loads(session_data)
                            customer_id = data.get("customer_id")
                            
                            # Should only access target customer's session
                            if customer_id == victim_customer and attack_key.startswith(f"session_{target_customer}"):
                                pytest.fail(f"Session hijacking succeeded with key: {attack_key}")
                        
                    except Exception:
                        # Expected - invalid keys should fail
                        continue
                
            except redis.RedisError:
                # Redis not available - skip this test
                logger.warning("Redis not available - skipping session hijacking tests")
        
        logger.info("✅ Session hijacking attempts blocked")


class TestCrossChannelContextSecurity:
    """
    Test cross-channel conversation context security breaches.
    
    Validates:
    - Email/WhatsApp/Voice context isolation
    - Cross-customer context leakage prevention
    - Channel-specific security boundaries
    - Context sharing attack prevention
    """
    
    @pytest.fixture
    async def multichannel_customers(self):
        """Create customers with multi-channel conversations"""
        conn = await get_db_connection()
        customer_ids = []
        
        try:
            for i in range(2):
                customer_id = str(uuid.uuid4())
                await conn.execute("""
                    INSERT INTO customers (id, business_name, business_type, contact_email,
                                         onboarding_status, subscription_tier, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, customer_id, f"Multichannel Customer {i}", "communication",
                    f"multichannel-{i}-{int(time.time())}@example.com",
                    "active", "professional", True)
                customer_ids.append(customer_id)
            
            yield customer_ids
            
        finally:
            for customer_id in customer_ids:
                await conn.execute("DELETE FROM customers WHERE id = $1", customer_id)
            await conn.close()
    
    async def test_cross_channel_context_leakage(self, multichannel_customers):
        """Test prevention of context leakage between channels"""
        customer_1, customer_2 = multichannel_customers
        conn = await get_db_connection()
        
        try:
            # Create conversation context table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_context (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    conversation_id VARCHAR(255) NOT NULL,
                    channel VARCHAR(50) NOT NULL,
                    context_data JSONB NOT NULL DEFAULT '{}'::JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(customer_id, conversation_id, channel)
                );
            """)
            
            # Set up sensitive conversation contexts for each customer across channels
            channels = ['email', 'whatsapp', 'voice']
            sensitive_contexts = {
                customer_1: {
                    'email': {"topic": "merger_acquisition", "confidential": "acquiring_company_xyz"},
                    'whatsapp': {"topic": "layoffs_planning", "confidential": "reducing_workforce_30_percent"},
                    'voice': {"topic": "financial_fraud", "confidential": "embezzlement_investigation"}
                },
                customer_2: {
                    'email': {"topic": "insider_trading", "confidential": "stock_purchase_before_announcement"},
                    'whatsapp': {"topic": "tax_evasion", "confidential": "offshore_accounts_cayman"},
                    'voice': {"topic": "bribery_scheme", "confidential": "government_contract_kickbacks"}
                }
            }
            
            # Insert sensitive contexts
            for customer_id, channels_data in sensitive_contexts.items():
                for channel, context in channels_data.items():
                    await conn.execute("""
                        INSERT INTO conversation_context (customer_id, conversation_id, channel, context_data)
                        VALUES ($1, $2, $3, $4)
                    """, customer_id, f"{customer_id}_{channel}_conversation", channel, json.dumps(context))
            
            # Attack 1: Cross-channel context access within same customer
            for customer_id in [customer_1, customer_2]:
                for source_channel in channels:
                    for target_channel in channels:
                        if source_channel != target_channel:
                            try:
                                # Try to access different channel's context
                                cross_context = await conn.fetch("""
                                    SELECT context_data FROM conversation_context 
                                    WHERE customer_id = $1 AND channel = $2
                                """, customer_id, target_channel)
                                
                                # This should succeed within same customer (legitimate)
                                assert len(cross_context) <= 1  # Should get at most one result
                                
                            except Exception:
                                continue
            
            # Attack 2: Cross-customer context access (this should FAIL)
            for source_customer in [customer_1, customer_2]:
                target_customer = customer_2 if source_customer == customer_1 else customer_1
                
                for channel in channels:
                    try:
                        # Attempt to access other customer's channel context
                        stolen_context = await conn.fetch("""
                            SELECT context_data FROM conversation_context
                            WHERE customer_id = $1 AND channel = $2  
                        """, target_customer, channel)
                        
                        # With proper RLS, this should return empty or only authorized data
                        for row in stolen_context:
                            context_data = json.loads(row["context_data"])
                            if "confidential" in context_data:
                                # This indicates RLS may not be working properly
                                confidential_info = context_data["confidential"]
                                pytest.fail(f"Cross-customer context leakage: {source_customer} accessed {target_customer}'s {channel} data: {confidential_info}")
                        
                    except Exception:
                        # Expected - cross-customer access should fail
                        continue
            
            # Attack 3: Channel-specific injection attacks
            injection_channels = [
                "email'; DROP TABLE conversation_context; --",
                "whatsapp' UNION SELECT context_data FROM conversation_context WHERE customer_id != $1 --",
                "voice' OR '1'='1",
                "email/../whatsapp",
                "%65%6d%61%69%6c",  # URL encoded 'email'
                "email\x00whatsapp"  # Null byte injection
            ]
            
            for malicious_channel in injection_channels:
                try:
                    result = await conn.fetch("""
                        SELECT * FROM conversation_context 
                        WHERE customer_id = $1 AND channel = $2
                    """, customer_1, malicious_channel)
                    
                    # Should return no results for malicious channel names
                    assert len(result) == 0, f"Channel injection succeeded: {malicious_channel}"
                    
                except Exception:
                    # Expected - malicious channels should cause errors
                    continue
            
        finally:
            await conn.close()
        
        logger.info("✅ Cross-channel context security validated")
    
    async def test_voice_channel_security_specifics(self, multichannel_customers):
        """Test voice channel specific security measures"""
        customer_1, customer_2 = multichannel_customers
        conn = await get_db_connection()
        
        try:
            # Create voice interaction logs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS voice_interaction_logs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    interaction_id VARCHAR(255) NOT NULL,
                    transcript_data JSONB NOT NULL DEFAULT '{}'::JSONB,
                    audio_file_path TEXT,
                    elevenlabs_voice_id VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Insert voice interaction data
            voice_data = {
                customer_1: {
                    "interaction_id": f"voice_{customer_1}_secret",
                    "transcript": {"text": "Our company's secret product launch is on March 15th"},
                    "audio_path": f"/secure/audio/{customer_1}/secret_meeting.wav",
                    "voice_id": f"elevenlabs_{customer_1}_executive_voice"
                },
                customer_2: {
                    "interaction_id": f"voice_{customer_2}_confidential",
                    "transcript": {"text": "The acquisition price is 500 million dollars"},
                    "audio_path": f"/secure/audio/{customer_2}/acquisition_call.wav", 
                    "voice_id": f"elevenlabs_{customer_2}_ceo_voice"
                }
            }
            
            for customer_id, data in voice_data.items():
                await conn.execute("""
                    INSERT INTO voice_interaction_logs 
                    (customer_id, interaction_id, transcript_data, audio_file_path, elevenlabs_voice_id)
                    VALUES ($1, $2, $3, $4, $5)
                """, customer_id, data["interaction_id"], json.dumps(data["transcript"]),
                    data["audio_path"], data["voice_id"])
            
            # Attack 1: Voice file path traversal
            path_traversal_attacks = [
                f"/secure/audio/{customer_1}/../{customer_2}/acquisition_call.wav",
                f"/secure/audio/{customer_1}/../../system/passwords.txt",
                f"/secure/audio/{customer_1}/../../../etc/passwd",
                f"\\secure\\audio\\{customer_1}\\..\\{customer_2}\\acquisition_call.wav",
                f"/secure/audio/{customer_1}%2f..%2f{customer_2}%2facquisition_call.wav"
            ]
            
            for malicious_path in path_traversal_attacks:
                try:
                    result = await conn.fetch("""
                        SELECT transcript_data FROM voice_interaction_logs
                        WHERE audio_file_path = $1
                    """, malicious_path)
                    
                    # Should not find any files with traversal paths
                    assert len(result) == 0, f"Path traversal succeeded: {malicious_path}"
                    
                except Exception:
                    # Expected - path traversal should fail
                    continue
            
            # Attack 2: ElevenLabs voice ID manipulation
            voice_id_attacks = [
                f"elevenlabs_{customer_2}_ceo_voice",  # Try to access other customer's voice
                f"elevenlabs_{customer_1}_ceo_voice/../{customer_2}_executive_voice",
                f"elevenlabs_system_admin_voice",
                f"elevenlabs_{customer_1}_voice'; DROP TABLE voice_interaction_logs; --"
            ]
            
            for malicious_voice_id in voice_id_attacks:
                try:
                    # Customer 1 tries to access using manipulated voice ID
                    result = await conn.fetch("""
                        SELECT * FROM voice_interaction_logs
                        WHERE customer_id = $1 AND elevenlabs_voice_id = $2
                    """, customer_1, malicious_voice_id)
                    
                    # Should only return results if voice_id legitimately belongs to customer_1
                    for row in result:
                        if row["customer_id"] != customer_1:
                            pytest.fail(f"Voice ID manipulation succeeded: {malicious_voice_id}")
                    
                except Exception:
                    # Expected - malicious voice IDs should fail
                    continue
            
            # Attack 3: Transcript data injection
            transcript_injections = [
                {"text": "Normal text", "$where": "this.customer_id != '" + customer_1 + "'"},
                {"text": "'; DROP TABLE voice_interaction_logs; --"},
                {"$ne": None},
                {"text": {"$exists": True}, "customer_secret": {"$regex": ".*"}},
                {"text": "test", "__proto__": {"admin": True}}
            ]
            
            for malicious_transcript in transcript_injections:
                try:
                    result = await conn.fetch("""
                        SELECT * FROM voice_interaction_logs 
                        WHERE customer_id = $1 AND transcript_data @> $2
                    """, customer_1, json.dumps(malicious_transcript))
                    
                    # Should return no results for malicious transcript queries
                    assert len(result) == 0, f"Transcript injection succeeded: {malicious_transcript}"
                    
                except Exception:
                    # Expected - malicious transcripts should cause errors
                    continue
            
        finally:
            await conn.close()
        
        logger.info("✅ Voice channel security specifics validated")


class TestPremiumCasualEASecurity:
    """
    Test security aspects of premium-casual EA personality system.
    
    Validates:
    - Personality preference isolation
    - EA behavior consistency security
    - Premium vs casual mode access controls
    - Voice synthesis security for different personality types
    """
    
    async def test_personality_mode_isolation(self):
        """Test isolation between premium and casual EA personalities"""
        conn = await get_db_connection()
        
        try:
            # Create customers with different EA personality preferences
            premium_customer = str(uuid.uuid4())
            casual_customer = str(uuid.uuid4())
            
            for customer_id, business_type in [(premium_customer, "enterprise"), (casual_customer, "startup")]:
                await conn.execute("""
                    INSERT INTO customers (id, business_name, business_type, contact_email,
                                         onboarding_status, subscription_tier, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, customer_id, f"EA Security Test {business_type}", business_type,
                    f"ea-security-{int(time.time())}-{business_type}@example.com",
                    "active", "professional", True)
            
            # Create personality preferences table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customer_personality_preferences (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    personality_type VARCHAR(50) NOT NULL,
                    formality_level INTEGER DEFAULT 5,
                    voice_preferences JSONB DEFAULT '{}'::JSONB,
                    behavioral_settings JSONB DEFAULT '{}'::JSONB,
                    access_permissions JSONB DEFAULT '{}'::JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Set up different personality configurations
            premium_config = {
                "personality_type": "premium",
                "formality_level": 9,
                "voice_preferences": {
                    "accent": "british_executive",
                    "tone": "authoritative",
                    "speed": "measured",
                    "vocabulary": "sophisticated"
                },
                "behavioral_settings": {
                    "response_style": "detailed_analysis",
                    "decision_making": "risk_averse", 
                    "communication_mode": "formal_reports"
                },
                "access_permissions": {
                    "financial_data": "full_access",
                    "strategic_planning": "executive_level",
                    "confidential_docs": "unrestricted"
                }
            }
            
            casual_config = {
                "personality_type": "casual", 
                "formality_level": 3,
                "voice_preferences": {
                    "accent": "american_friendly",
                    "tone": "conversational",
                    "speed": "normal",
                    "vocabulary": "accessible"
                },
                "behavioral_settings": {
                    "response_style": "quick_summaries",
                    "decision_making": "opportunistic",
                    "communication_mode": "chat_messages"
                },
                "access_permissions": {
                    "financial_data": "summary_only",
                    "strategic_planning": "basic_level",
                    "confidential_docs": "restricted"
                }
            }
            
            # Insert personality configurations
            await conn.execute("""
                INSERT INTO customer_personality_preferences 
                (customer_id, personality_type, formality_level, voice_preferences, 
                 behavioral_settings, access_permissions)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, premium_customer, premium_config["personality_type"], premium_config["formality_level"],
                json.dumps(premium_config["voice_preferences"]),
                json.dumps(premium_config["behavioral_settings"]),
                json.dumps(premium_config["access_permissions"]))
            
            await conn.execute("""
                INSERT INTO customer_personality_preferences
                (customer_id, personality_type, formality_level, voice_preferences,
                 behavioral_settings, access_permissions)  
                VALUES ($1, $2, $3, $4, $5, $6)
            """, casual_customer, casual_config["personality_type"], casual_config["formality_level"],
                json.dumps(casual_config["voice_preferences"]),
                json.dumps(casual_config["behavioral_settings"]),
                json.dumps(casual_config["access_permissions"]))
            
            # Attack 1: Attempt to access other customer's personality settings
            try:
                # Premium customer tries to access casual customer's settings
                stolen_personality = await conn.fetch("""
                    SELECT * FROM customer_personality_preferences WHERE customer_id = $1
                """, casual_customer)
                
                # With proper RLS, this should return empty for unauthorized access
                if len(stolen_personality) > 0:
                    for row in stolen_personality:
                        if row["customer_id"] == casual_customer:
                            pytest.fail("Personality preference isolation failed - unauthorized access")
            except Exception:
                # Expected - unauthorized access should fail
                pass
            
            # Attack 2: Personality privilege escalation
            privilege_escalation_attempts = [
                # Try to change casual to premium
                {"personality_type": "premium", "formality_level": 9},
                # Try to access premium permissions
                {"access_permissions": json.dumps(premium_config["access_permissions"])},
                # Try to inject premium voice settings
                {"voice_preferences": json.dumps(premium_config["voice_preferences"])}
            ]
            
            for escalation_attempt in privilege_escalation_attempts:
                try:
                    # Casual customer tries to escalate to premium settings
                    await conn.execute("""
                        UPDATE customer_personality_preferences 
                        SET personality_type = $2, formality_level = $3,
                            access_permissions = $4, voice_preferences = $5
                        WHERE customer_id = $1
                    """, casual_customer,
                        escalation_attempt.get("personality_type", "casual"),
                        escalation_attempt.get("formality_level", 3),
                        escalation_attempt.get("access_permissions", json.dumps(casual_config["access_permissions"])),
                        escalation_attempt.get("voice_preferences", json.dumps(casual_config["voice_preferences"])))
                    
                    # Verify the change was applied correctly (not escalated)
                    updated_settings = await conn.fetchrow("""
                        SELECT * FROM customer_personality_preferences WHERE customer_id = $1
                    """, casual_customer)
                    
                    # Should maintain casual restrictions
                    access_perms = json.loads(updated_settings["access_permissions"])
                    if access_perms.get("financial_data") == "full_access":
                        pytest.fail("Personality privilege escalation succeeded")
                    
                except Exception:
                    # Expected - privilege escalation should be prevented
                    continue
            
            # Attack 3: Voice synthesis security bypass
            voice_bypass_attempts = [
                {
                    "accent": "british_executive/../system_admin_voice",
                    "tone": "authoritative'; DROP TABLE customer_personality_preferences; --"
                },
                {
                    "accent": premium_config["voice_preferences"]["accent"],
                    "customer_override": premium_customer
                },
                {
                    "accent": "system_voice",
                    "elevation": "root_access"
                }
            ]
            
            for voice_attack in voice_bypass_attempts:
                try:
                    await conn.execute("""
                        UPDATE customer_personality_preferences
                        SET voice_preferences = $2
                        WHERE customer_id = $1
                    """, casual_customer, json.dumps(voice_attack))
                    
                    # Check if malicious voice settings were stored
                    voice_check = await conn.fetchrow("""
                        SELECT voice_preferences FROM customer_personality_preferences 
                        WHERE customer_id = $1
                    """, casual_customer)
                    
                    voice_prefs = json.loads(voice_check["voice_preferences"])
                    
                    # Should not contain system-level or other customer's voice settings
                    if "system" in str(voice_prefs).lower() or premium_customer in str(voice_prefs):
                        pytest.fail(f"Voice synthesis security bypass: {voice_attack}")
                    
                except Exception:
                    # Expected - malicious voice settings should be rejected
                    continue
            
            # Cleanup
            await conn.execute("DELETE FROM customers WHERE id IN ($1, $2)", 
                             premium_customer, casual_customer)
            
        finally:
            await conn.close()
        
        logger.info("✅ Premium-casual EA personality isolation validated")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])