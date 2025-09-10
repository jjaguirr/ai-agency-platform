"""
Enhanced Webhook Security Module
Critical security implementation for WhatsApp webhook endpoints

This module provides comprehensive webhook security validation including:
- Twilio signature verification
- Advanced rate limiting per phone number and endpoint
- Request payload validation and sanitization
- Anti-spam and abuse protection
- Real-time security monitoring and alerting
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from urllib.parse import urlencode, parse_qs
import redis
from fastapi import Request, HTTPException
import ipaddress

logger = logging.getLogger(__name__)

@dataclass
class RateLimitResult:
    """Result of rate limiting check"""
    allowed: bool
    requests_remaining: int
    reset_time: int
    current_requests: int
    limit: int

@dataclass
class SecurityValidationResult:
    """Result of webhook security validation"""
    valid: bool
    customer_id: Optional[str]
    validation_errors: List[str]
    security_warnings: List[str]
    timestamp: datetime

@dataclass
class WebhookSecurityConfig:
    """Configuration for webhook security"""
    rate_limit_per_phone: int = 60  # requests per minute
    rate_limit_per_ip: int = 300    # requests per minute
    max_payload_size: int = 1024 * 1024  # 1MB
    allowed_content_types: List[str] = None
    suspicious_patterns: List[str] = None
    
    def __post_init__(self):
        if self.allowed_content_types is None:
            self.allowed_content_types = [
                'application/x-www-form-urlencoded',
                'application/json',
                'multipart/form-data'
            ]
        
        if self.suspicious_patterns is None:
            self.suspicious_patterns = [
                r'<script.*?>.*?</script>',
                r'javascript:',
                r'onclick=',
                r'onerror=',
                r'onload=',
                r'eval\(',
                r'exec\(',
                r'system\(',
                r'../../../',
                r'../../../../',
                r'\.\./',
                r'%2e%2e%2f',
                r'%252e%252e%252f'
            ]

class AdvancedRateLimiter:
    """Advanced rate limiting with Redis backend and multiple algorithms"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        
    async def check_rate_limit(
        self, 
        key: str, 
        limit: int, 
        window: int = 60,
        algorithm: str = "sliding_window"
    ) -> RateLimitResult:
        """
        Check rate limit using specified algorithm
        
        Args:
            key: Unique identifier for rate limiting
            limit: Maximum requests allowed in window
            window: Time window in seconds
            algorithm: "sliding_window" or "token_bucket"
        """
        try:
            if algorithm == "sliding_window":
                return await self._sliding_window_check(key, limit, window)
            elif algorithm == "token_bucket":
                return await self._token_bucket_check(key, limit, window)
            else:
                raise ValueError(f"Unknown rate limiting algorithm: {algorithm}")
        except Exception as e:
            logger.error(f"Rate limiting error for key {key}: {e}")
            # Fail open for availability
            return RateLimitResult(
                allowed=True,
                requests_remaining=limit,
                reset_time=int(time.time() + window),
                current_requests=0,
                limit=limit
            )
    
    async def _sliding_window_check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """Sliding window rate limiting"""
        current_time = time.time()
        window_start = current_time - window
        
        # Redis pipeline for atomic operations
        pipeline = self.redis.pipeline()
        
        # Remove expired entries
        pipeline.zremrangebyscore(f"rate_limit:{key}", 0, window_start)
        
        # Count current requests in window
        pipeline.zcard(f"rate_limit:{key}")
        
        # Add current request
        pipeline.zadd(f"rate_limit:{key}", {str(current_time): current_time})
        
        # Set TTL for cleanup
        pipeline.expire(f"rate_limit:{key}", window * 2)
        
        results = pipeline.execute()
        current_requests = results[1]
        
        # Check if over limit
        allowed = current_requests < limit
        
        if not allowed:
            # Remove the request we just added since it's not allowed
            self.redis.zrem(f"rate_limit:{key}", str(current_time))
        
        return RateLimitResult(
            allowed=allowed,
            requests_remaining=max(0, limit - current_requests - (1 if allowed else 0)),
            reset_time=int(current_time + window),
            current_requests=current_requests + (1 if allowed else 0),
            limit=limit
        )
    
    async def _token_bucket_check(self, key: str, limit: int, window: int) -> RateLimitResult:
        """Token bucket rate limiting"""
        bucket_key = f"token_bucket:{key}"
        current_time = time.time()
        
        # Get current bucket state
        bucket_data = self.redis.hmget(bucket_key, 'tokens', 'last_refill')
        
        tokens = float(bucket_data[0] or limit)
        last_refill = float(bucket_data[1] or current_time)
        
        # Calculate tokens to add based on time elapsed
        time_elapsed = current_time - last_refill
        tokens_to_add = (time_elapsed / window) * limit
        tokens = min(limit, tokens + tokens_to_add)
        
        # Check if request is allowed
        allowed = tokens >= 1.0
        
        if allowed:
            tokens -= 1.0
        
        # Update bucket state
        self.redis.hmset(bucket_key, {
            'tokens': tokens,
            'last_refill': current_time
        })
        self.redis.expire(bucket_key, window * 2)
        
        return RateLimitResult(
            allowed=allowed,
            requests_remaining=int(tokens),
            reset_time=int(current_time + (window * (1 - tokens / limit))),
            current_requests=limit - int(tokens),
            limit=limit
        )

class WebhookSecurityValidator:
    """Comprehensive webhook security validation"""
    
    def __init__(self, config: WebhookSecurityConfig = None):
        self.config = config or WebhookSecurityConfig()
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=14,  # Use DB 14 for webhook security
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True
        )
        self.rate_limiter = AdvancedRateLimiter(self.redis_client)
        
        # IP whitelist and blacklist
        self.ip_whitelist = self._load_ip_whitelist()
        self.ip_blacklist = self._load_ip_blacklist()
        
        # Twilio webhook configuration
        self.twilio_webhook_secret = os.getenv('TWILIO_WEBHOOK_AUTH_TOKEN')
        if not self.twilio_webhook_secret:
            logger.warning("TWILIO_WEBHOOK_AUTH_TOKEN not configured - webhook signature validation disabled")
    
    def _load_ip_whitelist(self) -> List[ipaddress.IPv4Network]:
        """Load IP whitelist from environment or default Twilio IPs"""
        whitelist_env = os.getenv('WEBHOOK_IP_WHITELIST', '')
        
        # Default Twilio webhook IP ranges
        default_twilio_ips = [
            '34.196.124.0/24',
            '34.228.4.0/24', 
            '52.44.250.0/24',
            '54.92.8.0/24',
            '54.94.77.0/24',
            '107.20.250.0/24',
            '107.21.228.0/24',
            '174.129.245.0/24'
        ]
        
        if whitelist_env:
            ip_ranges = whitelist_env.split(',')
        else:
            ip_ranges = default_twilio_ips
        
        whitelist = []
        for ip_range in ip_ranges:
            try:
                whitelist.append(ipaddress.IPv4Network(ip_range.strip()))
            except ValueError as e:
                logger.warning(f"Invalid IP range in whitelist: {ip_range} - {e}")
        
        return whitelist
    
    def _load_ip_blacklist(self) -> List[ipaddress.IPv4Network]:
        """Load IP blacklist from environment"""
        blacklist_env = os.getenv('WEBHOOK_IP_BLACKLIST', '')
        if not blacklist_env:
            return []
        
        blacklist = []
        for ip_range in blacklist_env.split(','):
            try:
                blacklist.append(ipaddress.IPv4Network(ip_range.strip()))
            except ValueError as e:
                logger.warning(f"Invalid IP range in blacklist: {ip_range} - {e}")
        
        return blacklist
    
    async def validate_webhook_request(
        self, 
        request: Request, 
        payload: str,
        customer_id: str = None
    ) -> SecurityValidationResult:
        """
        Comprehensive webhook request validation
        
        Args:
            request: FastAPI request object
            payload: Raw request payload
            customer_id: Customer ID if known
            
        Returns:
            SecurityValidationResult with validation outcome
        """
        validation_errors = []
        security_warnings = []
        
        try:
            # 1. IP Address validation
            client_ip = self._get_client_ip(request)
            ip_validation = await self._validate_ip_address(client_ip)
            if not ip_validation[0]:
                validation_errors.append(f"IP address {client_ip} not allowed: {ip_validation[1]}")
            
            # 2. Rate limiting validation
            rate_limit_checks = await self._validate_rate_limits(request, customer_id)
            if not rate_limit_checks[0]:
                validation_errors.append(f"Rate limit exceeded: {rate_limit_checks[1]}")
            
            # 3. Payload size validation
            if len(payload) > self.config.max_payload_size:
                validation_errors.append(f"Payload size {len(payload)} exceeds maximum {self.config.max_payload_size}")
            
            # 4. Content type validation
            content_type = request.headers.get('content-type', '').split(';')[0]
            if content_type not in self.config.allowed_content_types:
                validation_errors.append(f"Content type {content_type} not allowed")
            
            # 5. Twilio signature validation
            if self.twilio_webhook_secret:
                signature_valid = await self._validate_twilio_signature(request, payload)
                if not signature_valid:
                    validation_errors.append("Invalid Twilio webhook signature")
            else:
                security_warnings.append("Webhook signature validation disabled")
            
            # 6. Payload content validation
            content_validation = await self._validate_payload_content(payload)
            if content_validation[1]:  # security warnings
                security_warnings.extend(content_validation[1])
            if not content_validation[0]:  # validation errors
                validation_errors.extend(content_validation[2])
            
            # 7. Suspicious pattern detection
            suspicious_patterns = await self._detect_suspicious_patterns(payload)
            if suspicious_patterns:
                security_warnings.extend([f"Suspicious pattern detected: {pattern}" for pattern in suspicious_patterns])
            
            # 8. Customer validation if provided
            if customer_id:
                customer_validation = await self._validate_customer_context(customer_id)
                if not customer_validation:
                    validation_errors.append(f"Invalid customer context: {customer_id}")
            
            valid = len(validation_errors) == 0
            
            # Log security events
            await self._log_security_event(request, payload, customer_id, valid, validation_errors, security_warnings)
            
            return SecurityValidationResult(
                valid=valid,
                customer_id=customer_id,
                validation_errors=validation_errors,
                security_warnings=security_warnings,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Webhook security validation error: {e}")
            return SecurityValidationResult(
                valid=False,
                customer_id=customer_id,
                validation_errors=[f"Security validation failed: {e}"],
                security_warnings=[],
                timestamp=datetime.now()
            )
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request headers"""
        # Check for IP in various headers (proxy-aware)
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host
    
    async def _validate_ip_address(self, ip_address: str) -> Tuple[bool, str]:
        """Validate IP address against whitelist/blacklist"""
        try:
            ip = ipaddress.IPv4Address(ip_address)
            
            # Check blacklist first
            for blacklisted_range in self.ip_blacklist:
                if ip in blacklisted_range:
                    return False, f"IP {ip_address} is blacklisted"
            
            # Check whitelist if configured
            if self.ip_whitelist:
                for allowed_range in self.ip_whitelist:
                    if ip in allowed_range:
                        return True, "IP allowed"
                return False, f"IP {ip_address} not in whitelist"
            
            return True, "IP validation passed"
            
        except ValueError:
            return False, f"Invalid IP address format: {ip_address}"
    
    async def _validate_rate_limits(self, request: Request, customer_id: str = None) -> Tuple[bool, str]:
        """Validate multiple rate limiting rules"""
        client_ip = self._get_client_ip(request)
        
        # 1. IP-based rate limiting
        ip_rate_limit = await self.rate_limiter.check_rate_limit(
            f"ip:{client_ip}",
            self.config.rate_limit_per_ip,
            60  # 1 minute window
        )
        
        if not ip_rate_limit.allowed:
            return False, f"IP rate limit exceeded: {ip_rate_limit.current_requests}/{ip_rate_limit.limit}"
        
        # 2. Phone number rate limiting (if available in payload)
        phone_number = self._extract_phone_number(request)
        if phone_number:
            phone_rate_limit = await self.rate_limiter.check_rate_limit(
                f"phone:{phone_number}",
                self.config.rate_limit_per_phone,
                60  # 1 minute window
            )
            
            if not phone_rate_limit.allowed:
                return False, f"Phone rate limit exceeded: {phone_rate_limit.current_requests}/{phone_rate_limit.limit}"
        
        # 3. Customer-based rate limiting
        if customer_id:
            customer_rate_limit = await self.rate_limiter.check_rate_limit(
                f"customer:{customer_id}",
                100,  # 100 requests per minute per customer
                60
            )
            
            if not customer_rate_limit.allowed:
                return False, f"Customer rate limit exceeded: {customer_rate_limit.current_requests}/{customer_rate_limit.limit}"
        
        return True, "Rate limits passed"
    
    def _extract_phone_number(self, request: Request) -> Optional[str]:
        """Extract phone number from request for rate limiting"""
        # This depends on webhook payload structure
        # For Twilio, phone number is usually in 'From' field
        try:
            if hasattr(request, '_body'):
                body = request._body.decode('utf-8')
                parsed = parse_qs(body)
                from_number = parsed.get('From', [None])[0]
                if from_number:
                    # Clean phone number
                    return from_number.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
        except:
            pass
        
        return None
    
    async def _validate_twilio_signature(self, request: Request, payload: str) -> bool:
        """Validate Twilio webhook signature"""
        if not self.twilio_webhook_secret:
            return False
        
        signature = request.headers.get('X-Twilio-Signature')
        if not signature:
            return False
        
        # Build URL for signature validation
        url = str(request.url)
        
        # Sort and encode parameters for signature calculation
        if request.method == 'POST' and payload:
            try:
                # Parse form data
                parsed_data = parse_qs(payload)
                sorted_params = sorted(parsed_data.items())
                
                # Build parameter string
                param_string = urlencode(sorted_params, doseq=True)
                validation_string = url + param_string
                
            except:
                # If parsing fails, use raw payload
                validation_string = url + payload
        else:
            validation_string = url
        
        # Calculate expected signature
        expected_signature = base64.b64encode(
            hmac.new(
                self.twilio_webhook_secret.encode('utf-8'),
                validation_string.encode('utf-8'),
                hashlib.sha1
            ).digest()
        ).decode('utf-8')
        
        # Compare signatures using constant-time comparison
        return hmac.compare_digest(signature, expected_signature)
    
    async def _validate_payload_content(self, payload: str) -> Tuple[bool, List[str], List[str]]:
        """Validate payload content for security issues"""
        warnings = []
        errors = []
        
        try:
            # Basic JSON validation if applicable
            if payload.startswith('{'):
                try:
                    json.loads(payload)
                except json.JSONDecodeError:
                    errors.append("Invalid JSON payload")
            
            # Check for null bytes
            if '\x00' in payload:
                errors.append("Null bytes detected in payload")
            
            # Check for extremely long lines (potential DoS)
            lines = payload.split('\n')
            for i, line in enumerate(lines):
                if len(line) > 10000:  # 10KB per line max
                    warnings.append(f"Extremely long line detected at line {i+1}")
            
            # Check for nested depth (potential parser bomb)
            if payload.count('{') > 100 or payload.count('[') > 100:
                warnings.append("Deep nesting detected in payload")
            
            return len(errors) == 0, warnings, errors
            
        except Exception as e:
            errors.append(f"Payload validation error: {e}")
            return False, warnings, errors
    
    async def _detect_suspicious_patterns(self, payload: str) -> List[str]:
        """Detect suspicious patterns in payload"""
        import re
        
        detected_patterns = []
        
        for pattern in self.config.suspicious_patterns:
            try:
                if re.search(pattern, payload, re.IGNORECASE):
                    detected_patterns.append(pattern)
            except re.error:
                logger.warning(f"Invalid regex pattern: {pattern}")
        
        return detected_patterns
    
    async def _validate_customer_context(self, customer_id: str) -> bool:
        """Validate customer context and existence"""
        # This should validate against your customer database
        # For now, basic validation
        if not customer_id or len(customer_id) < 3:
            return False
        
        # Check if customer exists in cache/database
        # TODO: Implement customer validation
        return True
    
    async def _log_security_event(
        self,
        request: Request,
        payload: str,
        customer_id: str,
        valid: bool,
        errors: List[str],
        warnings: List[str]
    ):
        """Log security events for monitoring and audit"""
        event = {
            'timestamp': datetime.now().isoformat(),
            'client_ip': self._get_client_ip(request),
            'user_agent': request.headers.get('user-agent', ''),
            'url': str(request.url),
            'method': request.method,
            'payload_size': len(payload),
            'customer_id': customer_id,
            'validation_result': 'PASS' if valid else 'FAIL',
            'errors': errors,
            'warnings': warnings,
            'headers': dict(request.headers)
        }
        
        # Log to security audit system
        if valid:
            logger.info(f"Webhook security validation PASSED: {json.dumps(event)}")
        else:
            logger.warning(f"Webhook security validation FAILED: {json.dumps(event)}")
        
        # Store in Redis for real-time monitoring
        try:
            self.redis_client.lpush('webhook_security_events', json.dumps(event))
            self.redis_client.ltrim('webhook_security_events', 0, 1000)  # Keep last 1000 events
            self.redis_client.expire('webhook_security_events', 86400)  # 24 hours
        except Exception as e:
            logger.error(f"Failed to store security event: {e}")

# Security monitoring and alerting
class WebhookSecurityMonitor:
    """Real-time webhook security monitoring"""
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=14,
            password=os.getenv('REDIS_PASSWORD'),
            decode_responses=True
        )
        
        self.alert_thresholds = {
            'failed_validations_per_minute': 10,
            'suspicious_patterns_per_hour': 5,
            'rate_limit_violations_per_hour': 50
        }
    
    async def check_security_alerts(self):
        """Check for security alert conditions"""
        try:
            # Get recent security events
            events = self.redis_client.lrange('webhook_security_events', 0, -1)
            
            current_time = datetime.now()
            one_minute_ago = current_time - timedelta(minutes=1)
            one_hour_ago = current_time - timedelta(hours=1)
            
            failed_validations = 0
            suspicious_patterns = 0
            rate_limit_violations = 0
            
            for event_json in events:
                try:
                    event = json.loads(event_json)
                    event_time = datetime.fromisoformat(event['timestamp'])
                    
                    if event_time >= one_minute_ago and event['validation_result'] == 'FAIL':
                        failed_validations += 1
                    
                    if event_time >= one_hour_ago:
                        if any('Suspicious pattern' in warning for warning in event.get('warnings', [])):
                            suspicious_patterns += 1
                        
                        if any('rate limit' in error.lower() for error in event.get('errors', [])):
                            rate_limit_violations += 1
                
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
            
            # Check thresholds and generate alerts
            alerts = []
            
            if failed_validations >= self.alert_thresholds['failed_validations_per_minute']:
                alerts.append({
                    'type': 'HIGH_FAILED_VALIDATIONS',
                    'severity': 'HIGH',
                    'count': failed_validations,
                    'threshold': self.alert_thresholds['failed_validations_per_minute'],
                    'message': f'{failed_validations} webhook validation failures in the last minute'
                })
            
            if suspicious_patterns >= self.alert_thresholds['suspicious_patterns_per_hour']:
                alerts.append({
                    'type': 'SUSPICIOUS_PATTERNS',
                    'severity': 'MEDIUM',
                    'count': suspicious_patterns,
                    'threshold': self.alert_thresholds['suspicious_patterns_per_hour'],
                    'message': f'{suspicious_patterns} suspicious patterns detected in the last hour'
                })
            
            if rate_limit_violations >= self.alert_thresholds['rate_limit_violations_per_hour']:
                alerts.append({
                    'type': 'HIGH_RATE_LIMIT_VIOLATIONS',
                    'severity': 'MEDIUM',
                    'count': rate_limit_violations,
                    'threshold': self.alert_thresholds['rate_limit_violations_per_hour'],
                    'message': f'{rate_limit_violations} rate limit violations in the last hour'
                })
            
            # Send alerts
            for alert in alerts:
                await self._send_security_alert(alert)
            
            return alerts
            
        except Exception as e:
            logger.error(f"Security monitoring error: {e}")
            return []
    
    async def _send_security_alert(self, alert: Dict[str, Any]):
        """Send security alert notification"""
        logger.critical(f"WEBHOOK SECURITY ALERT: {json.dumps(alert)}")
        
        # TODO: Implement alert delivery (Slack, email, PagerDuty, etc.)
        # Example implementation:
        # await send_slack_alert(alert)
        # await send_email_alert(alert)
        
        # Store alert in Redis for dashboard
        try:
            alert_with_timestamp = {
                **alert,
                'timestamp': datetime.now().isoformat(),
                'alert_id': f"alert_{int(time.time())}"
            }
            
            self.redis_client.lpush('webhook_security_alerts', json.dumps(alert_with_timestamp))
            self.redis_client.ltrim('webhook_security_alerts', 0, 100)  # Keep last 100 alerts
            self.redis_client.expire('webhook_security_alerts', 86400 * 7)  # 7 days
            
        except Exception as e:
            logger.error(f"Failed to store security alert: {e}")

# Global instances
webhook_security_config = WebhookSecurityConfig()
webhook_security_validator = WebhookSecurityValidator(webhook_security_config)
webhook_security_monitor = WebhookSecurityMonitor()