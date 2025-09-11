"""
Webhook Performance & Monitoring System
Real-time analytics and monitoring for webhook operations
"""

import time
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from threading import Lock
import os
import redis
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

@dataclass
class WebhookMetric:
    """Individual webhook metric data point"""
    timestamp: float
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    request_size: int
    response_size: int
    ip_address: str
    user_agent: str
    error_message: Optional[str] = None
    customer_id: Optional[str] = None
    message_type: Optional[str] = None

@dataclass
class AggregatedMetrics:
    """Aggregated metrics for time period"""
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    total_data_processed: int
    unique_customers: int
    error_rate: float
    requests_per_minute: float

class WebhookMonitor:
    """Real-time webhook monitoring and analytics"""
    
    def __init__(self, redis_url: Optional[str] = None, retention_hours: int = 24):
        """
        Initialize webhook monitoring
        
        Args:
            redis_url: Redis connection URL (optional, falls back to in-memory)
            retention_hours: How long to keep detailed metrics
        """
        self.retention_hours = retention_hours
        self.lock = Lock()
        
        # Try to connect to Redis for persistence
        self.redis_client = None
        if redis_url or os.getenv('REDIS_URL'):
            try:
                self.redis_client = redis.from_url(redis_url or os.getenv('REDIS_URL'))
                self.redis_client.ping()  # Test connection
                logger.info("✅ Connected to Redis for metrics persistence")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed, using in-memory storage: {e}")
                self.redis_client = None
        
        # In-memory storage (always available as fallback)
        self.metrics_queue = deque(maxlen=10000)  # Keep last 10K requests
        self.aggregated_cache = {}
        self.real_time_stats = {
            'requests_last_minute': deque(maxlen=60),
            'response_times': deque(maxlen=1000),
            'error_count': 0,
            'total_requests': 0,
            'start_time': time.time()
        }
        
        # Start background cleanup task
        asyncio.create_task(self._cleanup_old_metrics())
    
    def record_request(self, 
                      endpoint: str,
                      method: str, 
                      status_code: int,
                      response_time_ms: float,
                      request_size: int = 0,
                      response_size: int = 0,
                      ip_address: str = "unknown",
                      user_agent: str = "unknown",
                      error_message: Optional[str] = None,
                      customer_id: Optional[str] = None,
                      message_type: Optional[str] = None) -> None:
        """Record a webhook request metric"""
        
        timestamp = time.time()
        metric = WebhookMetric(
            timestamp=timestamp,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            response_time_ms=response_time_ms,
            request_size=request_size,
            response_size=response_size,
            ip_address=ip_address,
            user_agent=user_agent,
            error_message=error_message,
            customer_id=customer_id,
            message_type=message_type
        )
        
        with self.lock:
            # Store in memory
            self.metrics_queue.append(metric)
            
            # Update real-time stats
            self.real_time_stats['requests_last_minute'].append(timestamp)
            self.real_time_stats['response_times'].append(response_time_ms)
            self.real_time_stats['total_requests'] += 1
            
            if status_code >= 400:
                self.real_time_stats['error_count'] += 1
        
        # Store in Redis if available
        if self.redis_client:
            try:
                key = f"webhook_metric:{int(timestamp*1000)}"  # Millisecond precision
                self.redis_client.setex(
                    key, 
                    self.retention_hours * 3600,  # TTL in seconds
                    json.dumps(asdict(metric))
                )
                
                # Update aggregated counters
                self._update_redis_counters(metric)
                
            except Exception as e:
                logger.error(f"Failed to store metric in Redis: {e}")
    
    def _update_redis_counters(self, metric: WebhookMetric) -> None:
        """Update Redis-based aggregated counters"""
        try:
            minute_key = f"metrics:minute:{int(metric.timestamp // 60)}"
            hour_key = f"metrics:hour:{int(metric.timestamp // 3600)}"
            
            pipe = self.redis_client.pipeline()
            
            # Increment counters
            pipe.hincrby(minute_key, "total_requests", 1)
            pipe.hincrby(hour_key, "total_requests", 1)
            pipe.hincrby(minute_key, f"status_{metric.status_code}", 1)
            pipe.hincrby(hour_key, f"status_{metric.status_code}", 1)
            
            if metric.status_code >= 400:
                pipe.hincrby(minute_key, "errors", 1)
                pipe.hincrby(hour_key, "errors", 1)
            
            # Set TTL
            pipe.expire(minute_key, 3600)  # 1 hour
            pipe.expire(hour_key, 86400)   # 24 hours
            
            pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to update Redis counters: {e}")
    
    def get_real_time_stats(self) -> Dict[str, Any]:
        """Get real-time statistics"""
        with self.lock:
            current_time = time.time()
            
            # Calculate requests in last minute
            recent_requests = [
                t for t in self.real_time_stats['requests_last_minute'] 
                if current_time - t <= 60
            ]
            
            # Calculate response time stats
            response_times = list(self.real_time_stats['response_times'])
            
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                min_response_time = min(response_times)
                max_response_time = max(response_times)
            else:
                avg_response_time = min_response_time = max_response_time = 0
            
            uptime_seconds = current_time - self.real_time_stats['start_time']
            
            return {
                "timestamp": current_time,
                "requests_per_minute": len(recent_requests),
                "total_requests": self.real_time_stats['total_requests'],
                "error_count": self.real_time_stats['error_count'],
                "error_rate": (
                    self.real_time_stats['error_count'] / max(1, self.real_time_stats['total_requests'])
                ) * 100,
                "avg_response_time_ms": round(avg_response_time, 2),
                "min_response_time_ms": round(min_response_time, 2),
                "max_response_time_ms": round(max_response_time, 2),
                "uptime_seconds": round(uptime_seconds, 2),
                "memory_metrics_count": len(self.metrics_queue),
                "redis_connected": self.redis_client is not None
            }
    
    def get_aggregated_metrics(self, hours_back: int = 1) -> AggregatedMetrics:
        """Get aggregated metrics for specified time period"""
        current_time = time.time()
        cutoff_time = current_time - (hours_back * 3600)
        
        # Get metrics from memory
        recent_metrics = [
            metric for metric in self.metrics_queue 
            if metric.timestamp >= cutoff_time
        ]
        
        if not recent_metrics:
            return AggregatedMetrics(
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_response_time=0,
                min_response_time=0,
                max_response_time=0,
                total_data_processed=0,
                unique_customers=0,
                error_rate=0,
                requests_per_minute=0
            )
        
        # Calculate aggregations
        total_requests = len(recent_metrics)
        successful_requests = sum(1 for m in recent_metrics if m.status_code < 400)
        failed_requests = total_requests - successful_requests
        
        response_times = [m.response_time_ms for m in recent_metrics]
        avg_response_time = sum(response_times) / len(response_times)
        min_response_time = min(response_times)
        max_response_time = max(response_times)
        
        total_data_processed = sum(m.request_size + m.response_size for m in recent_metrics)
        unique_customers = len(set(m.customer_id for m in recent_metrics if m.customer_id))
        
        error_rate = (failed_requests / total_requests) * 100 if total_requests > 0 else 0
        requests_per_minute = total_requests / (hours_back * 60)
        
        return AggregatedMetrics(
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_response_time=round(avg_response_time, 2),
            min_response_time=round(min_response_time, 2),
            max_response_time=round(max_response_time, 2),
            total_data_processed=total_data_processed,
            unique_customers=unique_customers,
            error_rate=round(error_rate, 2),
            requests_per_minute=round(requests_per_minute, 2)
        )
    
    def get_endpoint_breakdown(self, hours_back: int = 1) -> Dict[str, Dict[str, Any]]:
        """Get metrics breakdown by endpoint"""
        current_time = time.time()
        cutoff_time = current_time - (hours_back * 3600)
        
        endpoint_stats = defaultdict(lambda: {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0,
            'response_times': []
        })
        
        for metric in self.metrics_queue:
            if metric.timestamp >= cutoff_time:
                stats = endpoint_stats[metric.endpoint]
                stats['total_requests'] += 1
                stats['response_times'].append(metric.response_time_ms)
                
                if metric.status_code < 400:
                    stats['successful_requests'] += 1
                else:
                    stats['failed_requests'] += 1
        
        # Calculate averages
        for endpoint, stats in endpoint_stats.items():
            if stats['response_times']:
                stats['avg_response_time'] = round(
                    sum(stats['response_times']) / len(stats['response_times']), 2
                )
            del stats['response_times']  # Remove raw data
            
            stats['error_rate'] = round(
                (stats['failed_requests'] / max(1, stats['total_requests'])) * 100, 2
            )
        
        return dict(endpoint_stats)
    
    def get_customer_breakdown(self, hours_back: int = 1) -> Dict[str, Dict[str, Any]]:
        """Get metrics breakdown by customer"""
        current_time = time.time()
        cutoff_time = current_time - (hours_back * 3600)
        
        customer_stats = defaultdict(lambda: {
            'total_requests': 0,
            'message_types': defaultdict(int),
            'avg_response_time': 0,
            'response_times': [],
            'last_activity': 0
        })
        
        for metric in self.metrics_queue:
            if metric.timestamp >= cutoff_time and metric.customer_id:
                stats = customer_stats[metric.customer_id]
                stats['total_requests'] += 1
                stats['response_times'].append(metric.response_time_ms)
                stats['last_activity'] = max(stats['last_activity'], metric.timestamp)
                
                if metric.message_type:
                    stats['message_types'][metric.message_type] += 1
        
        # Calculate averages and format
        result = {}
        for customer_id, stats in customer_stats.items():
            if stats['response_times']:
                avg_response_time = sum(stats['response_times']) / len(stats['response_times'])
            else:
                avg_response_time = 0
            
            result[customer_id] = {
                'total_requests': stats['total_requests'],
                'message_types': dict(stats['message_types']),
                'avg_response_time': round(avg_response_time, 2),
                'last_activity': stats['last_activity'],
                'last_activity_human': datetime.fromtimestamp(stats['last_activity']).strftime(
                    '%Y-%m-%d %H:%M:%S'
                ) if stats['last_activity'] else 'Never'
            }
        
        return result
    
    async def _cleanup_old_metrics(self) -> None:
        """Background task to cleanup old metrics"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                current_time = time.time()
                cutoff_time = current_time - (self.retention_hours * 3600)
                
                with self.lock:
                    # Remove old metrics from memory
                    while self.metrics_queue and self.metrics_queue[0].timestamp < cutoff_time:
                        self.metrics_queue.popleft()
                
                logger.debug(f"Cleaned up old metrics, {len(self.metrics_queue)} remain")
                
            except Exception as e:
                logger.error(f"Error during metrics cleanup: {e}")

# Global monitor instance
webhook_monitor = WebhookMonitor()

# Flask Blueprint for monitoring endpoints
monitoring_bp = Blueprint('monitoring', __name__)

@monitoring_bp.route('/metrics/realtime')
def realtime_metrics():
    """Real-time metrics endpoint"""
    return jsonify(webhook_monitor.get_real_time_stats())

@monitoring_bp.route('/metrics/aggregated')
def aggregated_metrics():
    """Aggregated metrics endpoint"""
    hours_back = request.args.get('hours', 1, type=int)
    hours_back = max(1, min(24, hours_back))  # Limit to 1-24 hours
    
    metrics = webhook_monitor.get_aggregated_metrics(hours_back)
    return jsonify(asdict(metrics))

@monitoring_bp.route('/metrics/endpoints')
def endpoint_metrics():
    """Endpoint breakdown metrics"""
    hours_back = request.args.get('hours', 1, type=int)
    hours_back = max(1, min(24, hours_back))
    
    breakdown = webhook_monitor.get_endpoint_breakdown(hours_back)
    return jsonify(breakdown)

@monitoring_bp.route('/metrics/customers')
def customer_metrics():
    """Customer breakdown metrics"""
    hours_back = request.args.get('hours', 1, type=int)
    hours_back = max(1, min(24, hours_back))
    
    breakdown = webhook_monitor.get_customer_breakdown(hours_back)
    return jsonify(breakdown)

@monitoring_bp.route('/metrics/dashboard')
def metrics_dashboard():
    """Complete metrics dashboard data"""
    hours_back = request.args.get('hours', 1, type=int)
    hours_back = max(1, min(24, hours_back))
    
    return jsonify({
        'realtime': webhook_monitor.get_real_time_stats(),
        'aggregated': asdict(webhook_monitor.get_aggregated_metrics(hours_back)),
        'endpoints': webhook_monitor.get_endpoint_breakdown(hours_back),
        'customers': webhook_monitor.get_customer_breakdown(hours_back),
        'system_info': {
            'retention_hours': webhook_monitor.retention_hours,
            'redis_connected': webhook_monitor.redis_client is not None,
            'memory_metrics': len(webhook_monitor.metrics_queue)
        }
    })

# Decorator for automatic request monitoring
def monitor_webhook_request(func):
    """Decorator to automatically monitor webhook requests"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        error_message = None
        status_code = 200
        
        try:
            result = func(*args, **kwargs)
            if hasattr(result, 'status_code'):
                status_code = result.status_code
            return result
        except Exception as e:
            error_message = str(e)
            status_code = 500
            raise
        finally:
            response_time_ms = (time.time() - start_time) * 1000
            
            # Record the request
            webhook_monitor.record_request(
                endpoint=request.endpoint or 'unknown',
                method=request.method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                request_size=len(request.get_data()) if hasattr(request, 'get_data') else 0,
                ip_address=request.remote_addr or 'unknown',
                user_agent=request.headers.get('User-Agent', 'unknown'),
                error_message=error_message
            )
    
    wrapper.__name__ = func.__name__
    return wrapper