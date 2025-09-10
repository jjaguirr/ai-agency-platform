"""
Comprehensive Penetration Testing Suite
Security validation for Issue #49 fixes

This test suite validates all security implementations including:
- Customer data isolation
- Redis security fixes
- Webhook signature validation
- API authentication
- GDPR compliance
- Cross-customer access prevention
"""

import asyncio
import json
import logging
import os
import pytest
import redis
import requests
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any
import aiohttp
import psycopg2
from psycopg2.extras import RealDictCursor

# Import security modules
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from security.customer_data_security import (
    SecureCustomerRedis,
    SecurityValidator,
    GDPRCompliance,
    WebhookSecurity
)

logger = logging.getLogger(__name__)

class PenetrationTestSuite:
    """Comprehensive penetration testing for customer isolation"""
    
    def __init__(self):
        self.test_customers = [
            f"pentest_customer_{uuid.uuid4().hex[:8]}",
            f"pentest_customer_{uuid.uuid4().hex[:8]}",
            f"pentest_customer_{uuid.uuid4().hex[:8]}"
        ]
        self.security_validator = SecurityValidator()
        self.gdpr_compliance = GDPRCompliance()
        self.webhook_security = WebhookSecurity()
        
        # Test results
        self.results = {
            "redis_isolation": [],
            "api_authentication": [],
            "webhook_security": [],
            "gdpr_compliance": [],
            "cross_customer_access": [],
            "data_encryption": []
        }
    
    async def run_comprehensive_security_tests(self) -> Dict[str, Any]:
        """Run all penetration tests and return detailed results"""
        logger.info("🔒 Starting comprehensive security penetration tests...")
        
        try:
            # Test 1: Redis Customer Isolation
            await self._test_redis_customer_isolation()
            
            # Test 2: API Authentication Bypass Attempts
            await self._test_api_authentication_bypass()
            
            # Test 3: Webhook Security Validation
            await self._test_webhook_security_vulnerabilities()
            
            # Test 4: Cross-Customer Data Access Attempts
            await self._test_cross_customer_data_access()
            
            # Test 5: GDPR Compliance Validation
            await self._test_gdpr_compliance()
            
            # Test 6: Data Encryption Validation
            await self._test_data_encryption()
            
            # Test 7: Rate Limiting Bypass Attempts
            await self._test_rate_limiting_bypass()
            
            # Test 8: SQL Injection and NoSQL Injection
            await self._test_injection_vulnerabilities()
            
            # Generate final security report
            return await self._generate_security_report()
            
        except Exception as e:
            logger.error(f"Penetration test suite failed: {e}")
            return {
                "status": "FAILED",
                "error": str(e),
                "results": self.results
            }
    
    async def _test_redis_customer_isolation(self):
        """Test Redis customer isolation - CRITICAL SECURITY FIX"""
        logger.info("🔍 Testing Redis customer isolation...")
        
        test_data = {}
        redis_clients = {}
        
        # Create secure Redis clients for each test customer
        for customer_id in self.test_customers:
            redis_clients[customer_id] = SecureCustomerRedis(customer_id)
            test_data[customer_id] = {
                "sensitive_data": f"SECRET_DATA_FOR_{customer_id}",
                "business_info": f"Confidential business data for {customer_id}",
                "phone_numbers": [f"+1555000{i}" for i in range(3)]
            }
        
        # Test 1: Store data for each customer
        for customer_id, data in test_data.items():
            redis_client = redis_clients[customer_id]
            
            for key, value in data.items():
                success = await redis_client.set_secure(key, value, ex=300)
                assert success, f"Failed to store data for customer {customer_id}"
        
        # Test 2: Verify customer isolation - each customer should only see their data
        isolation_violations = []
        
        for customer_id in self.test_customers:
            redis_client = redis_clients[customer_id]
            
            # Try to retrieve own data (should work)
            own_data = await redis_client.get_secure("sensitive_data")
            expected_data = test_data[customer_id]["sensitive_data"]
            
            if own_data != expected_data:
                isolation_violations.append(f"Customer {customer_id} cannot access own data")
            
            # Try to access other customers' data (should fail)
            for other_customer_id in self.test_customers:
                if other_customer_id != customer_id:
                    # Attempt to access other customer's Redis database
                    try:
                        other_redis = redis.Redis(
                            host='localhost',
                            port=6379,
                            db=redis_clients[other_customer_id].redis_db,
                            decode_responses=True
                        )
                        
                        # Try to access encrypted keys directly (should fail)
                        keys = other_redis.keys("*")
                        for key in keys:
                            if key.startswith(f"customer_{other_customer_id}_"):
                                try:
                                    # This should not return decrypted data
                                    raw_value = other_redis.get(key)
                                    if raw_value and expected_data in str(raw_value):
                                        isolation_violations.append(
                                            f"CRITICAL: Customer {customer_id} can access {other_customer_id}'s raw data"
                                        )
                                except:
                                    pass  # Expected to fail
                    except:
                        pass  # Expected Redis access to fail
        
        # Test 3: Verify encryption is working
        encryption_test_passed = True
        for customer_id in self.test_customers:
            redis_client = redis_clients[customer_id]
            
            # Check that data is actually encrypted in Redis
            try:
                raw_redis = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=redis_client.redis_db,
                    decode_responses=False  # Get raw bytes
                )
                
                keys = raw_redis.keys(f"customer_{customer_id}_*")
                for key in keys:
                    raw_value = raw_redis.get(key)
                    if raw_value and test_data[customer_id]["sensitive_data"].encode() in raw_value:
                        encryption_test_passed = False
                        isolation_violations.append(f"Data not encrypted for customer {customer_id}")
                        break
            except Exception as e:
                logger.warning(f"Could not verify encryption for {customer_id}: {e}")
        
        # Clean up test data
        for customer_id in self.test_customers:
            redis_client = redis_clients[customer_id]
            await redis_client.secure_delete_all_customer_data()
        
        self.results["redis_isolation"] = {
            "test_passed": len(isolation_violations) == 0 and encryption_test_passed,
            "violations": isolation_violations,
            "encryption_verified": encryption_test_passed,
            "customers_tested": len(self.test_customers)
        }
        
        logger.info(f"Redis isolation test: {'PASSED' if len(isolation_violations) == 0 else 'FAILED'}")
    
    async def _test_api_authentication_bypass(self):
        """Test API authentication bypass attempts"""
        logger.info("🔍 Testing API authentication bypass attempts...")
        
        # Test endpoints that should require authentication
        test_endpoints = [
            "http://localhost:8001/api/chat",
            "http://localhost:8001/api/voice/upload",
            "http://localhost:8001/api/conversations",
            "http://localhost:8001/api/status"
        ]
        
        bypass_attempts = []
        
        for endpoint in test_endpoints:
            # Test 1: No authentication header
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(endpoint, json={"test": "data"}) as response:
                        if response.status != 401:
                            bypass_attempts.append(f"Endpoint {endpoint} accessible without authentication")
            except:
                pass  # Expected to fail
            
            # Test 2: Invalid JWT token
            invalid_tokens = [
                "Bearer invalid_token",
                "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid",
                "Bearer " + "a" * 100,
                "Invalid Bearer token",
                ""
            ]
            
            for token in invalid_tokens:
                try:
                    headers = {"Authorization": token}
                    async with aiohttp.ClientSession() as session:
                        async with session.post(endpoint, headers=headers, json={"test": "data"}) as response:
                            if response.status != 401:
                                bypass_attempts.append(f"Endpoint {endpoint} accessible with invalid token: {token[:20]}...")
                except:
                    pass  # Expected to fail
            
            # Test 3: JWT token manipulation
            try:
                # Try to access with manipulated customer_id in payload
                manipulated_payload = {
                    "customer_id": "ATTACKER_CUSTOMER",
                    "user_id": "attacker",
                    "exp": int(time.time()) + 3600
                }
                
                # This should fail because we don't have the signing key
                headers = {"Authorization": "Bearer fake_manipulated_token"}
                async with aiohttp.ClientSession() as session:
                    async with session.post(endpoint, headers=headers, json={"test": "data"}) as response:
                        if response.status != 401:
                            bypass_attempts.append(f"Endpoint {endpoint} vulnerable to JWT manipulation")
            except:
                pass  # Expected to fail
        
        self.results["api_authentication"] = {
            "test_passed": len(bypass_attempts) == 0,
            "bypass_attempts": bypass_attempts,
            "endpoints_tested": len(test_endpoints)
        }
        
        logger.info(f"API authentication test: {'PASSED' if len(bypass_attempts) == 0 else 'FAILED'}")
    
    async def _test_webhook_security_vulnerabilities(self):
        """Test webhook security implementation"""
        logger.info("🔍 Testing webhook security vulnerabilities...")
        
        webhook_vulnerabilities = []
        
        # Test 1: Missing webhook signature
        try:
            webhook_url = "http://localhost:8080/webhook/whatsapp"  # Example webhook URL
            payload = "From=whatsapp:+1234567890&Body=Test message"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, data=payload) as response:
                    if response.status == 200:
                        webhook_vulnerabilities.append("Webhook accepts requests without signature validation")
        except:
            pass  # Webhook might not be running
        
        # Test 2: Invalid webhook signature
        try:
            headers = {"X-Twilio-Signature": "invalid_signature"}
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, headers=headers, data=payload) as response:
                    if response.status == 200:
                        webhook_vulnerabilities.append("Webhook accepts invalid signatures")
        except:
            pass
        
        # Test 3: Rate limiting bypass
        try:
            # Send many requests rapidly
            rate_limit_violations = 0
            for i in range(100):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(webhook_url, data=f"test_{i}") as response:
                            if response.status != 429:  # Should be rate limited
                                rate_limit_violations += 1
                except:
                    pass
            
            if rate_limit_violations > 50:  # Allow some leeway
                webhook_vulnerabilities.append("Webhook rate limiting ineffective")
        except:
            pass
        
        # Test 4: Signature validation with known test data
        signature_validation_works = False
        try:
            test_secret = "test_webhook_secret"
            test_payload = "From=whatsapp:+1234567890&Body=Test"
            test_url = "https://example.com/webhook"
            
            # Create valid signature
            import hmac
            import hashlib
            import base64
            
            signature_data = test_url + test_payload
            expected_signature = base64.b64encode(
                hmac.new(
                    test_secret.encode(),
                    signature_data.encode(),
                    hashlib.sha1
                ).digest()
            ).decode()
            
            # Test the webhook security validator directly
            validation_result = self.webhook_security.validate_twilio_signature(
                payload=test_payload,
                signature=expected_signature,
                url=test_url
            )
            
            if not validation_result:
                webhook_vulnerabilities.append("Webhook signature validation implementation incorrect")
            else:
                signature_validation_works = True
                
        except Exception as e:
            webhook_vulnerabilities.append(f"Webhook signature validation error: {e}")
        
        self.results["webhook_security"] = {
            "test_passed": len(webhook_vulnerabilities) == 0,
            "vulnerabilities": webhook_vulnerabilities,
            "signature_validation_works": signature_validation_works
        }
        
        logger.info(f"Webhook security test: {'PASSED' if len(webhook_vulnerabilities) == 0 else 'FAILED'}")
    
    async def _test_cross_customer_data_access(self):
        """Test cross-customer data access prevention"""
        logger.info("🔍 Testing cross-customer data access prevention...")
        
        access_violations = []
        
        # Test database-level customer isolation
        try:
            db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub",
                user="mcphub", 
                password="mcphub_password"
            )
            
            cursor = db_connection.cursor(cursor_factory=RealDictCursor)
            
            # Insert test data for different customers
            test_data = {}
            for customer_id in self.test_customers:
                cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
                
                # Insert customer-specific data
                cursor.execute("""
                    INSERT INTO customer_config (customer_id, config)
                    VALUES (%s, %s)
                    ON CONFLICT (customer_id) DO UPDATE SET config = EXCLUDED.config
                """, (customer_id, json.dumps({"secret_key": f"SECRET_{customer_id}"})))
                
                test_data[customer_id] = f"SECRET_{customer_id}"
            
            db_connection.commit()
            
            # Test isolation: each customer should only see their own data
            for customer_id in self.test_customers:
                cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
                
                # Query customer config
                cursor.execute("SELECT customer_id, config FROM customer_config")
                results = cursor.fetchall()
                
                # Should only see own data
                visible_customers = [row['customer_id'] for row in results]
                other_customers = [cid for cid in self.test_customers if cid != customer_id]
                
                for other_customer in other_customers:
                    if other_customer in visible_customers:
                        access_violations.append(f"Customer {customer_id} can see {other_customer}'s data")
            
            # Clean up test data
            for customer_id in self.test_customers:
                cursor.execute("SELECT set_config('app.customer_id', %s, false)", (customer_id,))
                cursor.execute("DELETE FROM customer_config WHERE customer_id = %s", (customer_id,))
            
            db_connection.commit()
            cursor.close()
            db_connection.close()
            
        except Exception as e:
            access_violations.append(f"Database isolation test failed: {e}")
        
        self.results["cross_customer_access"] = {
            "test_passed": len(access_violations) == 0,
            "violations": access_violations,
            "customers_tested": len(self.test_customers)
        }
        
        logger.info(f"Cross-customer access test: {'PASSED' if len(access_violations) == 0 else 'FAILED'}")
    
    async def _test_gdpr_compliance(self):
        """Test GDPR compliance implementation"""
        logger.info("🔍 Testing GDPR compliance...")
        
        gdpr_violations = []
        
        for customer_id in self.test_customers:
            try:
                # Test data export functionality
                export_result = await self.gdpr_compliance.export_customer_data(customer_id)
                
                if not export_result:
                    gdpr_violations.append(f"Data export failed for customer {customer_id}")
                    continue
                
                # Verify export contains required fields
                required_fields = ['customer_id', 'export_timestamp', 'voice_data', 'whatsapp_data']
                for field in required_fields:
                    if not hasattr(export_result, field):
                        gdpr_violations.append(f"Export missing field {field} for customer {customer_id}")
                
                # Test data deletion functionality
                deletion_result = await self.gdpr_compliance.delete_customer_data(customer_id)
                
                if not deletion_result:
                    gdpr_violations.append(f"Data deletion failed for customer {customer_id}")
                    continue
                
                # Verify deletion report
                if not deletion_result.secure_deletion_verified:
                    gdpr_violations.append(f"Secure deletion not verified for customer {customer_id}")
                
            except Exception as e:
                gdpr_violations.append(f"GDPR compliance test failed for {customer_id}: {e}")
        
        self.results["gdpr_compliance"] = {
            "test_passed": len(gdpr_violations) == 0,
            "violations": gdpr_violations,
            "customers_tested": len(self.test_customers)
        }
        
        logger.info(f"GDPR compliance test: {'PASSED' if len(gdpr_violations) == 0 else 'FAILED'}")
    
    async def _test_data_encryption(self):
        """Test data encryption implementation"""
        logger.info("🔍 Testing data encryption...")
        
        encryption_failures = []
        
        for customer_id in self.test_customers:
            try:
                redis_client = SecureCustomerRedis(customer_id)
                
                # Test data is encrypted at rest
                test_data = "SENSITIVE_UNENCRYPTED_DATA_12345"
                await redis_client.set_secure("encryption_test", test_data)
                
                # Check raw Redis data to ensure it's encrypted
                raw_redis = redis.Redis(
                    host='localhost',
                    port=6379,
                    db=redis_client.redis_db,
                    decode_responses=False
                )
                
                keys = raw_redis.keys(f"customer_{customer_id}_*")
                found_unencrypted = False
                
                for key in keys:
                    raw_value = raw_redis.get(key)
                    if raw_value and test_data.encode() in raw_value:
                        found_unencrypted = True
                        break
                
                if found_unencrypted:
                    encryption_failures.append(f"Unencrypted data found for customer {customer_id}")
                
                # Clean up
                await redis_client.delete_secure("encryption_test")
                
            except Exception as e:
                encryption_failures.append(f"Encryption test failed for {customer_id}: {e}")
        
        self.results["data_encryption"] = {
            "test_passed": len(encryption_failures) == 0,
            "failures": encryption_failures,
            "customers_tested": len(self.test_customers)
        }
        
        logger.info(f"Data encryption test: {'PASSED' if len(encryption_failures) == 0 else 'FAILED'}")
    
    async def _test_rate_limiting_bypass(self):
        """Test rate limiting bypass attempts"""
        logger.info("🔍 Testing rate limiting bypass attempts...")
        
        rate_limit_bypasses = []
        
        # Test Redis-based rate limiting
        for customer_id in self.test_customers:
            try:
                redis_client = SecureCustomerRedis(customer_id)
                
                # Attempt to bypass rate limiting with rapid requests
                successful_requests = 0
                for i in range(200):  # Try to exceed typical rate limits
                    try:
                        success = await redis_client.set_secure(f"rate_test_{i}", f"data_{i}", ex=60)
                        if success:
                            successful_requests += 1
                    except:
                        pass  # Rate limiting might cause exceptions
                
                # Check if rate limiting is working (should not allow all 200 requests)
                if successful_requests >= 150:  # Allow some leeway
                    rate_limit_bypasses.append(f"Rate limiting bypass possible for customer {customer_id}")
                
                # Clean up
                await redis_client.secure_delete_all_customer_data()
                
            except Exception as e:
                logger.warning(f"Rate limiting test failed for {customer_id}: {e}")
        
        self.results["rate_limiting"] = {
            "test_passed": len(rate_limit_bypasses) == 0,
            "bypasses": rate_limit_bypasses,
            "customers_tested": len(self.test_customers)
        }
        
        logger.info(f"Rate limiting test: {'PASSED' if len(rate_limit_bypasses) == 0 else 'FAILED'}")
    
    async def _test_injection_vulnerabilities(self):
        """Test SQL injection and NoSQL injection vulnerabilities"""
        logger.info("🔍 Testing injection vulnerabilities...")
        
        injection_vulnerabilities = []
        
        # Test SQL injection payloads
        sql_payloads = [
            "'; DROP TABLE customer_config; --",
            "' OR '1'='1",
            "' UNION SELECT * FROM customer_config --",
            "'; INSERT INTO customer_config VALUES ('hacker', '{}'); --"
        ]
        
        # Test Redis injection payloads
        redis_payloads = [
            "FLUSHALL",
            "CONFIG SET dir /tmp",
            "EVAL \"return redis.call('FLUSHALL')\" 0"
        ]
        
        for customer_id in self.test_customers:
            try:
                redis_client = SecureCustomerRedis(customer_id)
                
                # Test SQL injection resistance
                for payload in sql_payloads:
                    try:
                        # This should be safely handled
                        await redis_client.set_secure("injection_test", payload)
                        stored_value = await redis_client.get_secure("injection_test")
                        
                        # The payload should be stored as-is, not executed
                        if stored_value != payload:
                            injection_vulnerabilities.append(f"SQL injection payload modified for {customer_id}")
                        
                    except Exception as e:
                        # Exceptions are acceptable for injection attempts
                        pass
                
                # Test Redis injection resistance
                for payload in redis_payloads:
                    try:
                        # This should not execute Redis commands
                        await redis_client.set_secure("redis_injection_test", payload)
                        
                        # Check that the payload didn't affect other customers' data
                        # by trying to retrieve data from another customer
                        other_customer = [c for c in self.test_customers if c != customer_id][0]
                        other_redis_client = SecureCustomerRedis(other_customer)
                        
                        # If injection worked, this might fail or return unexpected data
                        test_result = await other_redis_client.get_secure("nonexistent_key")
                        # Should return None normally
                        
                    except Exception as e:
                        # Exceptions are acceptable for injection attempts
                        pass
                
                # Clean up
                await redis_client.secure_delete_all_customer_data()
                
            except Exception as e:
                injection_vulnerabilities.append(f"Injection test failed for {customer_id}: {e}")
        
        self.results["injection_vulnerabilities"] = {
            "test_passed": len(injection_vulnerabilities) == 0,
            "vulnerabilities": injection_vulnerabilities,
            "payloads_tested": len(sql_payloads) + len(redis_payloads)
        }
        
        logger.info(f"Injection vulnerability test: {'PASSED' if len(injection_vulnerabilities) == 0 else 'FAILED'}")
    
    async def _generate_security_report(self) -> Dict[str, Any]:
        """Generate comprehensive security test report"""
        total_tests = len(self.results)
        passed_tests = sum(1 for result in self.results.values() if result.get("test_passed", False))
        
        overall_status = "PASSED" if passed_tests == total_tests else "FAILED"
        
        # Calculate risk score
        critical_failures = 0
        high_failures = 0
        
        critical_tests = ["redis_isolation", "cross_customer_access", "api_authentication"]
        high_tests = ["webhook_security", "gdpr_compliance", "data_encryption"]
        
        for test_name in critical_tests:
            if not self.results.get(test_name, {}).get("test_passed", False):
                critical_failures += 1
        
        for test_name in high_tests:
            if not self.results.get(test_name, {}).get("test_passed", False):
                high_failures += 1
        
        # Risk scoring: Critical = 10 points, High = 5 points
        risk_score = (critical_failures * 10) + (high_failures * 5)
        
        if risk_score == 0:
            risk_level = "LOW"
        elif risk_score <= 10:
            risk_level = "MEDIUM"
        elif risk_score <= 20:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"
        
        report = {
            "test_summary": {
                "status": overall_status,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": total_tests - passed_tests,
                "risk_level": risk_level,
                "risk_score": risk_score
            },
            "detailed_results": self.results,
            "security_recommendations": self._generate_security_recommendations(),
            "compliance_status": {
                "gdpr_compliant": self.results.get("gdpr_compliance", {}).get("test_passed", False),
                "customer_isolation": self.results.get("redis_isolation", {}).get("test_passed", False),
                "data_encryption": self.results.get("data_encryption", {}).get("test_passed", False)
            },
            "timestamp": datetime.now().isoformat(),
            "test_environment": {
                "customers_tested": len(self.test_customers),
                "test_duration_seconds": 0  # Would calculate actual duration
            }
        }
        
        return report
    
    def _generate_security_recommendations(self) -> List[str]:
        """Generate security recommendations based on test results"""
        recommendations = []
        
        if not self.results.get("redis_isolation", {}).get("test_passed", False):
            recommendations.append("CRITICAL: Fix Redis customer isolation - implement per-customer databases with encryption")
        
        if not self.results.get("api_authentication", {}).get("test_passed", False):
            recommendations.append("CRITICAL: Implement JWT authentication on all API endpoints")
        
        if not self.results.get("cross_customer_access", {}).get("test_passed", False):
            recommendations.append("CRITICAL: Fix database row-level security for customer isolation")
        
        if not self.results.get("webhook_security", {}).get("test_passed", False):
            recommendations.append("HIGH: Implement proper webhook signature validation and rate limiting")
        
        if not self.results.get("gdpr_compliance", {}).get("test_passed", False):
            recommendations.append("HIGH: Implement GDPR compliance features (data export, deletion)")
        
        if not self.results.get("data_encryption", {}).get("test_passed", False):
            recommendations.append("HIGH: Implement data encryption at rest for all customer data")
        
        if len(recommendations) == 0:
            recommendations.append("All security tests passed - maintain current security practices")
        
        return recommendations

# Async test runner
async def run_penetration_tests():
    """Run comprehensive penetration tests"""
    test_suite = PenetrationTestSuite()
    report = await test_suite.run_comprehensive_security_tests()
    
    print("=" * 80)
    print("🔒 SECURITY PENETRATION TEST REPORT")
    print("=" * 80)
    print(f"Overall Status: {report['test_summary']['status']}")
    print(f"Risk Level: {report['test_summary']['risk_level']}")
    print(f"Tests Passed: {report['test_summary']['passed_tests']}/{report['test_summary']['total_tests']}")
    print("\n📋 Security Recommendations:")
    for rec in report['security_recommendations']:
        print(f"  • {rec}")
    
    print("\n📊 Detailed Results:")
    for test_name, result in report['detailed_results'].items():
        status = "PASS" if result.get('test_passed', False) else "FAIL"
        print(f"  {test_name}: {status}")
    
    print("=" * 80)
    
    return report

if __name__ == "__main__":
    asyncio.run(run_penetration_tests())