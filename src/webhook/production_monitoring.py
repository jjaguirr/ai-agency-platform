#!/usr/bin/env python3
"""
Production Monitoring and Health Checks for Meta-Compliant WhatsApp Webhook Service
Enhanced monitoring with business metrics, performance tracking, and Meta API validation
"""

import asyncio
import logging
import json
import time
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from flask import Blueprint, jsonify, request
import redis
import aiohttp
import requests
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
WEBHOOK_REQUESTS_TOTAL = Counter('webhook_requests_total', 'Total webhook requests', ['endpoint', 'method', 'status'])
WEBHOOK_REQUEST_DURATION = Histogram('webhook_request_duration_seconds', 'Webhook request duration', ['endpoint'])
META_API_CALLS_TOTAL = Counter('meta_api_calls_total', 'Total Meta API calls', ['endpoint', 'status'])
META_API_DURATION = Histogram('meta_api_duration_seconds', 'Meta API call duration', ['endpoint'])
CLIENT_REGISTRATIONS_TOTAL = Counter('client_registrations_total', 'Total client registrations', ['status'])
EA_ROUTING_REQUESTS_TOTAL = Counter('ea_routing_requests_total', 'Total EA routing requests', ['status'])
ACTIVE_CLIENTS_GAUGE = Gauge('active_clients_total', 'Number of active clients')
REDIS_CONNECTIONS_GAUGE = Gauge('redis_connections_total', 'Redis connection pool size')
SYSTEM_HEALTH_GAUGE = Gauge('system_health_score', 'System health score (0-100)')

# Flask blueprint for monitoring endpoints
monitoring_bp = Blueprint('monitoring', __name__)

@dataclass
class HealthCheckResult:
    """Health check result data structure"""
    component: str
    status: str
    response_time_ms: float
    details: Dict[str, Any]
    timestamp: datetime

@dataclass
class BusinessMetrics:
    """Business performance metrics"""
    total_clients: int
    active_clients: int
    messages_sent_24h: int
    messages_received_24h: int
    signup_conversions_24h: int
    avg_response_time_ms: float
    error_rate_percent: float
    uptime_percent: float

class ProductionMonitor:
    """Production monitoring system for webhook service"""

    def __init__(self):
        self.redis_client = self._get_redis_client()
        self.health_checks_enabled = os.getenv('HEALTH_CHECK_ENABLED', 'true').lower() == 'true'
        self.metrics_enabled = os.getenv('METRICS_ENABLED', 'true').lower() == 'true'
        self.deep_health_checks = os.getenv('DEEP_HEALTH_CHECKS', 'false').lower() == 'true'

        # Meta API configuration
        self.meta_app_id = os.getenv('META_APP_ID', '')
        self.meta_app_secret = os.getenv('META_APP_SECRET', '')
        self.meta_api_version = os.getenv('META_API_VERSION', 'v20.0')

        # Health check cache (5 minute TTL)
        self.health_cache = {}
        self.health_cache_ttl = 300  # 5 minutes

        # Background monitoring thread
        self.monitoring_thread = None
        self.monitoring_active = False

    def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client for metrics storage"""
        try:
            redis_url = os.getenv('REDIS_URL')
            if redis_url:
                client = redis.from_url(redis_url)
                client.ping()
                return client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
        return None

    async def check_meta_api_health(self) -> HealthCheckResult:
        """Check Meta Graph API health and token validity"""
        start_time = time.time()

        try:
            # Check if app credentials are configured
            if not self.meta_app_id or not self.meta_app_secret:
                return HealthCheckResult(
                    component="meta_api",
                    status="ERROR",
                    response_time_ms=0,
                    details={"error": "Meta app credentials not configured"},
                    timestamp=datetime.now()
                )

            # Generate app access token for health check
            async with aiohttp.ClientSession() as session:
                token_url = f"https://graph.facebook.com/oauth/access_token"
                params = {
                    'client_id': self.meta_app_id,
                    'client_secret': self.meta_app_secret,
                    'grant_type': 'client_credentials'
                }

                async with session.get(token_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        app_token = token_data.get('access_token')

                        # Test Graph API with app token
                        test_url = f"https://graph.facebook.com/{self.meta_api_version}/{self.meta_app_id}"
                        headers = {'Authorization': f'Bearer {app_token}'}

                        async with session.get(test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as test_response:
                            response_time_ms = (time.time() - start_time) * 1000

                            if test_response.status == 200:
                                app_data = await test_response.json()
                                META_API_CALLS_TOTAL.labels(endpoint='health_check', status='success').inc()
                                META_API_DURATION.labels(endpoint='health_check').observe(response_time_ms / 1000)

                                return HealthCheckResult(
                                    component="meta_api",
                                    status="OK",
                                    response_time_ms=response_time_ms,
                                    details={
                                        "app_name": app_data.get('name', 'Unknown'),
                                        "app_id": self.meta_app_id,
                                        "api_version": self.meta_api_version
                                    },
                                    timestamp=datetime.now()
                                )
                            else:
                                error_data = await test_response.text()
                                META_API_CALLS_TOTAL.labels(endpoint='health_check', status='error').inc()

                                return HealthCheckResult(
                                    component="meta_api",
                                    status="ERROR",
                                    response_time_ms=response_time_ms,
                                    details={"error": f"API test failed: {error_data}"},
                                    timestamp=datetime.now()
                                )
                    else:
                        error_data = await response.text()
                        META_API_CALLS_TOTAL.labels(endpoint='health_check', status='error').inc()

                        return HealthCheckResult(
                            component="meta_api",
                            status="ERROR",
                            response_time_ms=(time.time() - start_time) * 1000,
                            details={"error": f"Token generation failed: {error_data}"},
                            timestamp=datetime.now()
                        )

        except Exception as e:
            META_API_CALLS_TOTAL.labels(endpoint='health_check', status='error').inc()
            return HealthCheckResult(
                component="meta_api",
                status="ERROR",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e)},
                timestamp=datetime.now()
            )

    def check_redis_health(self) -> HealthCheckResult:
        """Check Redis connection and performance"""
        start_time = time.time()

        try:
            if not self.redis_client:
                return HealthCheckResult(
                    component="redis",
                    status="ERROR",
                    response_time_ms=0,
                    details={"error": "Redis client not available"},
                    timestamp=datetime.now()
                )

            # Test basic operations
            test_key = f"health_check:{int(time.time())}"
            self.redis_client.set(test_key, "test_value", ex=60)
            value = self.redis_client.get(test_key)
            self.redis_client.delete(test_key)

            # Get connection pool info
            pool_info = {
                "max_connections": self.redis_client.connection_pool.max_connections,
                "created_connections": len(self.redis_client.connection_pool._created_connections)
            }

            response_time_ms = (time.time() - start_time) * 1000
            REDIS_CONNECTIONS_GAUGE.set(pool_info["created_connections"])

            return HealthCheckResult(
                component="redis",
                status="OK",
                response_time_ms=response_time_ms,
                details={
                    "connection_pool": pool_info,
                    "test_operation": "successful"
                },
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="redis",
                status="ERROR",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e)},
                timestamp=datetime.now()
            )

    def check_system_resources(self) -> HealthCheckResult:
        """Check system resources and performance"""
        start_time = time.time()

        try:
            import psutil

            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Calculate health score (0-100)
            health_score = 100
            if cpu_percent > 80:
                health_score -= 20
            if memory.percent > 85:
                health_score -= 20
            if disk.percent > 90:
                health_score -= 30

            SYSTEM_HEALTH_GAUGE.set(health_score)

            status = "OK" if health_score >= 70 else "WARNING" if health_score >= 50 else "ERROR"

            return HealthCheckResult(
                component="system_resources",
                status=status,
                response_time_ms=(time.time() - start_time) * 1000,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_mb": memory.available / (1024 * 1024),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024 * 1024 * 1024),
                    "health_score": health_score
                },
                timestamp=datetime.now()
            )

        except ImportError:
            # psutil not available
            return HealthCheckResult(
                component="system_resources",
                status="UNKNOWN",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"info": "System monitoring not available (psutil not installed)"},
                timestamp=datetime.now()
            )
        except Exception as e:
            return HealthCheckResult(
                component="system_resources",
                status="ERROR",
                response_time_ms=(time.time() - start_time) * 1000,
                details={"error": str(e)},
                timestamp=datetime.now()
            )

    def get_business_metrics(self) -> BusinessMetrics:
        """Get business performance metrics"""
        try:
            if not self.redis_client:
                return BusinessMetrics(0, 0, 0, 0, 0, 0.0, 0.0, 0.0)

            # Get metrics from Redis
            now = datetime.now()
            yesterday = now - timedelta(days=1)

            # Client metrics
            total_clients = len(self.redis_client.keys("client:*:info")) or 0
            active_clients = len(self.redis_client.keys("client:*:last_activity")) or 0

            # Message metrics (24h)
            messages_sent = int(self.redis_client.get("metrics:messages_sent:24h") or 0)
            messages_received = int(self.redis_client.get("metrics:messages_received:24h") or 0)

            # Signup conversions (24h)
            signup_conversions = int(self.redis_client.get("metrics:signups:24h") or 0)

            # Performance metrics
            avg_response_time = float(self.redis_client.get("metrics:avg_response_time") or 0)
            error_rate = float(self.redis_client.get("metrics:error_rate") or 0)
            uptime_percent = float(self.redis_client.get("metrics:uptime_percent") or 100.0)

            ACTIVE_CLIENTS_GAUGE.set(active_clients)

            return BusinessMetrics(
                total_clients=total_clients,
                active_clients=active_clients,
                messages_sent_24h=messages_sent,
                messages_received_24h=messages_received,
                signup_conversions_24h=signup_conversions,
                avg_response_time_ms=avg_response_time,
                error_rate_percent=error_rate,
                uptime_percent=uptime_percent
            )

        except Exception as e:
            logger.error(f"Failed to get business metrics: {e}")
            return BusinessMetrics(0, 0, 0, 0, 0, 0.0, 0.0, 0.0)

    async def comprehensive_health_check(self, deep_check: bool = False) -> Dict[str, Any]:
        """Perform comprehensive health check"""

        # Check cache first
        cache_key = f"health_check:{'deep' if deep_check else 'basic'}"
        if cache_key in self.health_cache:
            cached_result, cache_time = self.health_cache[cache_key]
            if time.time() - cache_time < self.health_cache_ttl:
                return cached_result

        health_results = []
        overall_status = "OK"
        start_time = time.time()

        # Basic health checks
        redis_health = self.check_redis_health()
        health_results.append(redis_health)

        system_health = self.check_system_resources()
        health_results.append(system_health)

        # Deep health checks (if enabled)
        if deep_check and self.deep_health_checks:
            meta_health = await self.check_meta_api_health()
            health_results.append(meta_health)

        # Determine overall status
        for result in health_results:
            if result.status == "ERROR":
                overall_status = "ERROR"
                break
            elif result.status == "WARNING" and overall_status == "OK":
                overall_status = "WARNING"

        # Get business metrics
        business_metrics = self.get_business_metrics()

        # Compile final result
        total_time = (time.time() - start_time) * 1000

        result = {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "response_time_ms": total_time,
            "version": os.getenv('APP_VERSION', '2.0.0'),
            "environment": os.getenv('ENVIRONMENT', 'production'),
            "health_checks": [asdict(result) for result in health_results],
            "business_metrics": asdict(business_metrics),
            "system_info": {
                "uptime_seconds": int(time.time() - self.get_startup_time()),
                "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
                "deployment_id": os.getenv('DEPLOYMENT_ID', 'unknown')
            }
        }

        # Cache result
        self.health_cache[cache_key] = (result, time.time())

        return result

    def get_startup_time(self) -> float:
        """Get application startup time"""
        return getattr(self, '_startup_time', time.time())

    def record_startup_time(self):
        """Record application startup time"""
        self._startup_time = time.time()

    def start_background_monitoring(self):
        """Start background monitoring thread"""
        if not self.monitoring_active and self.metrics_enabled:
            self.monitoring_active = True
            self.monitoring_thread = threading.Thread(target=self._background_monitoring_loop, daemon=True)
            self.monitoring_thread.start()
            logger.info("Background monitoring started")

    def _background_monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                # Update business metrics every minute
                metrics = self.get_business_metrics()

                # Store metrics in Redis for persistence
                if self.redis_client:
                    self.redis_client.setex(
                        "monitoring:last_update",
                        3600,  # 1 hour TTL
                        json.dumps({
                            "timestamp": datetime.now().isoformat(),
                            "metrics": asdict(metrics)
                        })
                    )

                # Update Prometheus metrics
                ACTIVE_CLIENTS_GAUGE.set(metrics.active_clients)

                # Sleep for 60 seconds
                time.sleep(60)

            except Exception as e:
                logger.error(f"Background monitoring error: {e}")
                time.sleep(60)  # Continue monitoring even on errors

    def stop_background_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
            logger.info("Background monitoring stopped")

# Global monitor instance
production_monitor = ProductionMonitor()

# Flask routes
@monitoring_bp.route('/health')
def health_check():
    """Basic health check endpoint"""
    try:
        deep_check = request.args.get('deep', 'false').lower() == 'true'

        # Run health check
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        health_result = loop.run_until_complete(
            production_monitor.comprehensive_health_check(deep_check=deep_check)
        )

        # Record metrics
        WEBHOOK_REQUESTS_TOTAL.labels(endpoint='/health', method='GET', status=health_result['status']).inc()

        status_code = 200 if health_result['status'] == 'OK' else 503
        return jsonify(health_result), status_code

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        WEBHOOK_REQUESTS_TOTAL.labels(endpoint='/health', method='GET', status='ERROR').inc()

        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@monitoring_bp.route('/embedded-signup/health')
def embedded_signup_health():
    """Health check for embedded signup functionality"""
    try:
        # Check Meta configuration
        meta_configured = bool(os.getenv('META_APP_ID') and os.getenv('META_APP_SECRET'))
        signup_config_id = os.getenv('EMBEDDED_SIGNUP_CONFIG_ID')

        status = "OK" if meta_configured and signup_config_id else "ERROR"

        result = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "meta_app_configured": meta_configured,
            "signup_config_present": bool(signup_config_id),
            "frontend_accessible": True  # If this endpoint responds, frontend is accessible
        }

        WEBHOOK_REQUESTS_TOTAL.labels(endpoint='/embedded-signup/health', method='GET', status=status).inc()

        status_code = 200 if status == 'OK' else 503
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"Embedded signup health check failed: {e}")
        return jsonify({
            "status": "ERROR",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@monitoring_bp.route('/metrics')
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    try:
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
    except Exception as e:
        logger.error(f"Metrics generation failed: {e}")
        return f"# Error generating metrics: {e}\n", 500, {'Content-Type': 'text/plain'}

# Middleware for request monitoring
def monitor_webhook_request(endpoint: str, method: str = 'POST'):
    """Decorator for monitoring webhook requests"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = 'success'

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = 'error'
                raise
            finally:
                duration = time.time() - start_time
                WEBHOOK_REQUESTS_TOTAL.labels(endpoint=endpoint, method=method, status=status).inc()
                WEBHOOK_REQUEST_DURATION.labels(endpoint=endpoint).observe(duration)

        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

# Initialize monitoring
def initialize_production_monitoring():
    """Initialize production monitoring system"""
    production_monitor.record_startup_time()
    production_monitor.start_background_monitoring()
    logger.info("Production monitoring initialized")

# Cleanup function
def cleanup_monitoring():
    """Cleanup monitoring resources"""
    production_monitor.stop_background_monitoring()
    logger.info("Production monitoring cleaned up")