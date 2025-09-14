#!/usr/bin/env python3
"""
Production Security Configuration for Meta-Compliant WhatsApp Webhook Service
Security hardening, IP allowlisting, signature validation, and threat protection
"""

import os
import hmac
import hashlib
import logging
import ipaddress
import time
import json
from typing import Dict, List, Optional, Tuple, Any
from functools import wraps
from flask import request, abort, g
from werkzeug.exceptions import Forbidden, TooManyRequests
import redis
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Meta WhatsApp Business API IP ranges (official Meta server IPs)
WHATSAPP_IP_RANGES = [
    # Facebook/Meta primary IP ranges
    "31.13.24.0/21",
    "31.13.64.0/18",
    "45.64.40.0/22",
    "66.220.144.0/20",
    "69.63.176.0/20",
    "69.171.224.0/19",
    "74.119.76.0/22",
    "103.4.96.0/22",
    "129.134.0.0/17",
    "157.240.0.0/17",
    "173.252.64.0/18",
    "179.60.192.0/22",
    "185.60.216.0/22",
    "204.15.20.0/22",

    # Additional Meta infrastructure ranges
    "129.134.0.0/16",
    "157.240.0.0/16",
    "173.252.0.0/16",
    "31.13.0.0/16",
    "69.171.0.0/16",
    "69.63.0.0/16",
    "66.220.0.0/16",
    "74.119.0.0/16"
]

# Additional development/testing IPs (disable in production)
DEVELOPMENT_IP_RANGES = [
    "127.0.0.1/32",      # localhost
    "10.0.0.0/8",        # Private networks
    "172.16.0.0/12",     # Private networks
    "192.168.0.0/16",    # Private networks
]

class SecurityConfig:
    """Production security configuration and validation"""

    def __init__(self):
        self.production_mode = os.getenv('PRODUCTION_MODE', 'false').lower() == 'true'
        self.enable_ip_allowlist = os.getenv('ENABLE_IP_ALLOWLIST', 'true').lower() == 'true'
        self.enforce_webhook_secret = os.getenv('ENFORCE_WEBHOOK_SECRET', 'true').lower() == 'true'
        self.rate_limit_enabled = os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true'

        # Security tokens and secrets
        self.webhook_secret = os.getenv('WHATSAPP_WEBHOOK_SECRET', '')
        self.meta_webhook_secret = os.getenv('META_WEBHOOK_SECRET', '')
        self.verify_token = os.getenv('WHATSAPP_VERIFY_TOKEN', '')
        self.meta_verify_token = os.getenv('META_WEBHOOK_VERIFY_TOKEN', '')

        # Rate limiting configuration
        self.redis_client = self._get_redis_client()
        self.rate_limits = {
            'webhook': int(os.getenv('RATE_LIMIT_WEBHOOK', '10000')),  # per hour
            'signup': int(os.getenv('RATE_LIMIT_EMBEDDED_SIGNUP', '100')),  # per hour
            'health': int(os.getenv('RATE_LIMIT_HEALTH', '1000')),  # per hour
            'default': int(os.getenv('RATE_LIMIT_DEFAULT', '1000'))  # per hour
        }

        # IP allowlist (Meta + development if not production)
        self.allowed_ip_ranges = WHATSAPP_IP_RANGES.copy()
        if not self.production_mode:
            self.allowed_ip_ranges.extend(DEVELOPMENT_IP_RANGES)

        self.allowed_networks = [ipaddress.ip_network(ip_range) for ip_range in self.allowed_ip_ranges]

        # Security headers
        self.security_headers = {
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' connect.facebook.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' graph.facebook.com",
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
        }

        # Validate security configuration
        self._validate_security_config()

    def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client for rate limiting"""
        try:
            redis_url = os.getenv('REDIS_URL')
            if redis_url:
                client = redis.from_url(redis_url)
                client.ping()
                return client
        except Exception as e:
            logger.warning(f"Redis connection failed for rate limiting: {e}")
        return None

    def _validate_security_config(self):
        """Validate security configuration for production"""
        if self.production_mode:
            issues = []

            # Check webhook secret
            if not self.webhook_secret or len(self.webhook_secret) < 32:
                issues.append("WHATSAPP_WEBHOOK_SECRET must be at least 32 characters")

            # Check verify tokens
            if not self.verify_token or len(self.verify_token) < 20:
                issues.append("WHATSAPP_VERIFY_TOKEN must be at least 20 characters")

            if not self.meta_verify_token or len(self.meta_verify_token) < 20:
                issues.append("META_WEBHOOK_VERIFY_TOKEN must be at least 20 characters")

            # Check encryption keys
            encryption_key = os.getenv('ENCRYPTION_KEY', '')
            if not encryption_key or len(encryption_key) < 32:
                issues.append("ENCRYPTION_KEY must be at least 32 characters")

            if issues:
                logger.error("❌ Security configuration issues:")
                for issue in issues:
                    logger.error(f"  - {issue}")
                raise ValueError("Production security requirements not met")

            logger.info("✅ Security configuration validated for production")

    def is_ip_allowed(self, client_ip: str) -> bool:
        """Check if client IP is in allowed ranges"""
        if not self.enable_ip_allowlist:
            return True

        try:
            client_addr = ipaddress.ip_address(client_ip)

            for network in self.allowed_networks:
                if client_addr in network:
                    return True

            return False

        except ValueError:
            logger.warning(f"Invalid IP address format: {client_ip}")
            return False

    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str = None) -> bool:
        """Validate Meta webhook signature"""
        if not self.enforce_webhook_secret:
            return True

        if not secret:
            secret = self.webhook_secret

        if not secret:
            logger.error("Webhook secret not configured")
            return False

        try:
            # Meta uses SHA256 HMAC with 'sha256=' prefix
            if signature.startswith('sha256='):
                expected_signature = 'sha256=' + hmac.new(
                    secret.encode('utf-8'),
                    payload,
                    hashlib.sha256
                ).hexdigest()

                return hmac.compare_digest(signature, expected_signature)
            else:
                logger.warning(f"Invalid signature format: {signature[:20]}...")
                return False

        except Exception as e:
            logger.error(f"Signature validation error: {e}")
            return False

    def check_rate_limit(self, identifier: str, limit_type: str = 'default') -> Tuple[bool, Dict[str, Any]]:
        """Check rate limit for identifier"""
        if not self.rate_limit_enabled or not self.redis_client:
            return True, {}

        try:
            limit = self.rate_limits.get(limit_type, self.rate_limits['default'])
            window = 3600  # 1 hour window

            # Use sliding window rate limiting
            now = time.time()
            pipeline = self.redis_client.pipeline()

            # Remove old entries
            pipeline.zremrangebyscore(f"rate_limit:{identifier}", 0, now - window)

            # Count current requests
            pipeline.zcard(f"rate_limit:{identifier}")

            # Add current request
            pipeline.zadd(f"rate_limit:{identifier}", {str(now): now})

            # Set expiry
            pipeline.expire(f"rate_limit:{identifier}", window)

            results = pipeline.execute()
            current_count = results[1]

            allowed = current_count < limit

            return allowed, {
                'limit': limit,
                'current': current_count,
                'window_seconds': window,
                'reset_time': int(now + window)
            }

        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # Fail open - allow request if rate limiting fails
            return True, {}

    def get_client_identifier(self, request) -> str:
        """Get client identifier for rate limiting"""
        # Try to get real client IP (considering proxy headers)
        client_ip = request.headers.get('X-Real-IP') or \
                   request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or \
                   request.remote_addr

        # For webhook requests, use IP + User-Agent for better identification
        user_agent = request.headers.get('User-Agent', 'unknown')[:50]  # Limit length

        return f"{client_ip}:{user_agent}"

    def apply_security_headers(self, response):
        """Apply security headers to response"""
        for header, value in self.security_headers.items():
            response.headers[header] = value
        return response

# Global security configuration
security_config = SecurityConfig()

def require_meta_webhook_signature(secret_env_var: str = 'WHATSAPP_WEBHOOK_SECRET'):
    """Decorator to require and validate Meta webhook signature"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not security_config.enforce_webhook_secret:
                return func(*args, **kwargs)

            signature = request.headers.get('X-Hub-Signature-256')
            if not signature:
                logger.warning(f"Missing webhook signature from {request.remote_addr}")
                abort(401, "Missing webhook signature")

            payload = request.get_data()
            secret = os.getenv(secret_env_var, security_config.webhook_secret)

            if not security_config.validate_webhook_signature(payload, signature, secret):
                logger.warning(f"Invalid webhook signature from {request.remote_addr}")
                abort(401, "Invalid webhook signature")

            return func(*args, **kwargs)
        return wrapper
    return decorator

def require_ip_allowlist(func):
    """Decorator to require IP allowlisting"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not security_config.enable_ip_allowlist:
            return func(*args, **kwargs)

        client_ip = request.headers.get('X-Real-IP') or \
                   request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or \
                   request.remote_addr

        if not security_config.is_ip_allowed(client_ip):
            logger.warning(f"IP not allowed: {client_ip}")
            abort(403, "Access denied")

        return func(*args, **kwargs)
    return wrapper

def require_rate_limit(limit_type: str = 'default'):
    """Decorator to enforce rate limiting"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not security_config.rate_limit_enabled:
                return func(*args, **kwargs)

            identifier = security_config.get_client_identifier(request)
            allowed, info = security_config.check_rate_limit(identifier, limit_type)

            if not allowed:
                logger.warning(f"Rate limit exceeded for {identifier}: {info}")

                # Add rate limit headers
                from flask import jsonify
                response = jsonify({
                    "error": "Rate limit exceeded",
                    "limit": info.get('limit'),
                    "reset_time": info.get('reset_time')
                })
                response.status_code = 429
                response.headers['X-RateLimit-Limit'] = str(info.get('limit', 0))
                response.headers['X-RateLimit-Remaining'] = str(max(0, info.get('limit', 0) - info.get('current', 0)))
                response.headers['X-RateLimit-Reset'] = str(info.get('reset_time', 0))
                response.headers['Retry-After'] = str(3600)  # 1 hour

                return response

            # Add rate limit headers to successful responses
            g.rate_limit_info = info

            return func(*args, **kwargs)
        return wrapper
    return decorator

def add_security_headers(func):
    """Decorator to add security headers to response"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        response = func(*args, **kwargs)

        # Apply security headers
        if hasattr(response, 'headers'):
            response = security_config.apply_security_headers(response)

            # Add rate limit headers if available
            if hasattr(g, 'rate_limit_info') and g.rate_limit_info:
                info = g.rate_limit_info
                response.headers['X-RateLimit-Limit'] = str(info.get('limit', 0))
                response.headers['X-RateLimit-Remaining'] = str(max(0, info.get('limit', 0) - info.get('current', 0)))
                response.headers['X-RateLimit-Reset'] = str(info.get('reset_time', 0))

        return response
    return wrapper

def log_security_event(event_type: str, details: Dict[str, Any]):
    """Log security events for monitoring and auditing"""
    security_log = {
        'timestamp': datetime.now().isoformat(),
        'event_type': event_type,
        'client_ip': request.headers.get('X-Real-IP') or
                    request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
                    request.remote_addr,
        'user_agent': request.headers.get('User-Agent', 'unknown')[:100],
        'endpoint': request.path,
        'method': request.method,
        'details': details
    }

    # Log to application logger
    logger.warning(f"SECURITY_EVENT: {json.dumps(security_log)}")

    # Store in Redis for security monitoring (if available)
    if security_config.redis_client:
        try:
            security_config.redis_client.lpush(
                'security_events',
                json.dumps(security_log)
            )
            # Keep only last 1000 events
            security_config.redis_client.ltrim('security_events', 0, 999)
            # Set expiry for 7 days
            security_config.redis_client.expire('security_events', 604800)
        except Exception as e:
            logger.error(f"Failed to store security event: {e}")

# Security middleware for Flask app
def init_security_middleware(app):
    """Initialize security middleware for Flask app"""

    @app.before_request
    def security_before_request():
        """Security checks before processing request"""

        # Skip security checks for health endpoints in development
        if not security_config.production_mode and request.path in ['/health', '/embedded-signup/health']:
            return

        # IP allowlist check for webhook endpoints
        if request.path.startswith('/webhook/'):
            if not security_config.is_ip_allowed(
                request.headers.get('X-Real-IP') or
                request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
                request.remote_addr
            ):
                log_security_event('ip_blocked', {
                    'blocked_ip': request.remote_addr,
                    'endpoint': request.path
                })
                abort(403, "Access denied")

    @app.after_request
    def security_after_request(response):
        """Apply security headers after request processing"""
        return security_config.apply_security_headers(response)

    # Register error handlers
    @app.errorhandler(403)
    def handle_forbidden(error):
        log_security_event('access_denied', {
            'error': str(error),
            'endpoint': request.path
        })
        return {
            "error": "Access denied",
            "timestamp": datetime.now().isoformat()
        }, 403

    @app.errorhandler(429)
    def handle_rate_limit(error):
        log_security_event('rate_limit_exceeded', {
            'error': str(error),
            'endpoint': request.path
        })
        return {
            "error": "Rate limit exceeded",
            "timestamp": datetime.now().isoformat()
        }, 429

    logger.info("✅ Security middleware initialized")

# Export decorators and utilities
__all__ = [
    'security_config',
    'require_meta_webhook_signature',
    'require_ip_allowlist',
    'require_rate_limit',
    'add_security_headers',
    'log_security_event',
    'init_security_middleware'
]