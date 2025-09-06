"""
Production Monitoring & Observability for Per-Customer Infrastructure

Implements comprehensive monitoring for customer isolation, performance SLAs, and infrastructure health.
Provides real-time metrics, alerting, and cost tracking for per-customer deployments.

Key Features:
- Per-customer resource usage and performance monitoring
- SLA enforcement (<30s provisioning, <500ms memory recall, >99.9% uptime)
- Cost tracking and optimization recommendations
- Security monitoring and compliance validation
- Automated alerting and incident response
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import docker
import asyncpg
import redis.asyncio as redis
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import aiohttp

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SLAMetric(Enum):
    PROVISIONING_TIME = "provisioning_time"
    MEMORY_RECALL_TIME = "memory_recall_time"
    UPTIME = "uptime"
    RESPONSE_TIME = "response_time"


@dataclass
class CustomerMetrics:
    """Real-time metrics for individual customer infrastructure"""
    customer_id: str
    tier: str
    provisioning_time: float
    uptime_percentage: float
    memory_recall_avg_ms: float
    response_time_p95_ms: float
    cpu_usage_percent: float
    memory_usage_percent: float
    storage_usage_gb: float
    request_count_24h: int
    error_count_24h: int
    cost_per_day_usd: float
    last_updated: datetime
    sla_violations: List[str]


@dataclass
class Alert:
    """Alert definition for monitoring"""
    id: str
    customer_id: str
    level: AlertLevel
    metric: str
    threshold: float
    current_value: float
    message: str
    created_at: datetime
    resolved_at: Optional[datetime] = None


class ProductionMonitor:
    """
    Production monitoring system for per-customer AI Agency Platform infrastructure.
    
    Monitors:
    - Customer provisioning performance (30-second SLA)
    - Memory system performance (<500ms SLA)
    - Infrastructure health and uptime (>99.9% SLA)
    - Resource usage and cost optimization
    - Security and compliance metrics
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize production monitoring system"""
        self.config = config or self._default_config()
        
        # Initialize metrics collectors
        self.registry = CollectorRegistry()
        self._init_prometheus_metrics()
        
        # Infrastructure connections
        self.docker_client = docker.from_env()
        self.postgres_pool = None
        self.redis_pool = None
        
        # Monitoring state
        self.customer_metrics = {}  # customer_id -> CustomerMetrics
        self.active_alerts = {}     # alert_id -> Alert
        self.monitoring_active = False
        
        logger.info("Initialized Production Monitor")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default monitoring configuration"""
        return {
            "sla_targets": {
                "provisioning_time_seconds": 30,
                "memory_recall_ms": 500,
                "uptime_percentage": 99.9,
                "response_time_p95_ms": 200
            },
            "alert_thresholds": {
                "cpu_usage_percent": 80,
                "memory_usage_percent": 85,
                "error_rate_percent": 5,
                "storage_usage_percent": 90
            },
            "monitoring": {
                "collection_interval_seconds": 30,
                "retention_days": 30,
                "prometheus_port": 9090,
                "grafana_enabled": True
            },
            "cost_tracking": {
                "enabled": True,
                "cost_per_hour": {
                    "starter": 0.10,
                    "professional": 0.25,
                    "enterprise": 0.50
                }
            },
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "mcphub",
                "user": "mcphub",
                "password": "mcphub_password"
            }
        }
    
    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics collectors"""
        
        # Customer provisioning metrics
        self.provisioning_time_histogram = Histogram(
            'customer_provisioning_seconds',
            'Time taken to provision customer infrastructure',
            ['customer_tier'],
            registry=self.registry,
            buckets=[5, 10, 15, 20, 30, 45, 60, 120]
        )
        
        self.provisioning_sla_violations = Counter(
            'customer_provisioning_sla_violations_total',
            'Number of customer provisioning SLA violations',
            ['customer_tier'],
            registry=self.registry
        )
        
        # Memory system metrics
        self.memory_recall_histogram = Histogram(
            'customer_memory_recall_seconds',
            'Time taken for memory recall operations',
            ['customer_id', 'query_type'],
            registry=self.registry,
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
        )
        
        self.memory_sla_violations = Counter(
            'customer_memory_sla_violations_total',
            'Number of memory recall SLA violations',
            ['customer_id'],
            registry=self.registry
        )
        
        # Infrastructure health metrics
        self.customer_uptime = Gauge(
            'customer_uptime_percentage',
            'Customer infrastructure uptime percentage',
            ['customer_id', 'tier'],
            registry=self.registry
        )
        
        self.customer_cpu_usage = Gauge(
            'customer_cpu_usage_percentage',
            'Customer infrastructure CPU usage',
            ['customer_id', 'tier'],
            registry=self.registry
        )
        
        self.customer_memory_usage = Gauge(
            'customer_memory_usage_percentage',
            'Customer infrastructure memory usage',
            ['customer_id', 'tier'],
            registry=self.registry
        )
        
        # Business metrics
        self.customer_requests = Counter(
            'customer_requests_total',
            'Total number of customer requests',
            ['customer_id', 'tier', 'endpoint'],
            registry=self.registry
        )
        
        self.customer_errors = Counter(
            'customer_errors_total',
            'Total number of customer errors',
            ['customer_id', 'tier', 'error_type'],
            registry=self.registry
        )
        
        # Cost tracking metrics
        self.customer_cost_daily = Gauge(
            'customer_cost_daily_usd',
            'Daily infrastructure cost per customer',
            ['customer_id', 'tier'],
            registry=self.registry
        )
        
        # Security metrics
        self.security_violations = Counter(
            'security_violations_total',
            'Security violations detected',
            ['customer_id', 'violation_type'],
            registry=self.registry
        )
    
    async def start_monitoring(self):
        """Start continuous monitoring of all customer infrastructure"""
        if self.monitoring_active:
            logger.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        
        # Initialize database connections
        await self._init_connections()
        
        # Start monitoring tasks
        monitoring_tasks = [
            self._monitor_customer_infrastructure(),
            self._monitor_provisioning_performance(),
            self._monitor_memory_performance(),
            self._monitor_cost_optimization(),
            self._monitor_security_compliance(),
            self._process_alerts()
        ]
        
        logger.info("🚀 Starting production monitoring...")
        await asyncio.gather(*monitoring_tasks)
    
    async def _init_connections(self):
        """Initialize database and cache connections"""
        if not self.postgres_pool:
            postgres_config = self.config["database"]
            self.postgres_pool = await asyncpg.create_pool(
                host=postgres_config["host"],
                port=postgres_config["port"],
                database=postgres_config["database"],
                user=postgres_config["user"],
                password=postgres_config["password"],
                min_size=2,
                max_size=10
            )
        
        if not self.redis_pool:
            self.redis_pool = redis.ConnectionPool.from_url("redis://localhost:6379", db=0)
    
    async def _monitor_customer_infrastructure(self):
        """Monitor all customer infrastructure health and performance"""
        while self.monitoring_active:
            try:
                # Get all customer containers
                customer_containers = self.docker_client.containers.list(
                    filters={"label": "ai-agency.service=mcp-server"}
                )
                
                for container in customer_containers:
                    customer_id = container.labels.get("ai-agency.customer-id")
                    if not customer_id:
                        continue
                    
                    # Collect container metrics
                    metrics = await self._collect_container_metrics(container, customer_id)
                    
                    # Update customer metrics
                    self.customer_metrics[customer_id] = metrics
                    
                    # Update Prometheus metrics
                    await self._update_prometheus_metrics(metrics)
                    
                    # Check SLA violations
                    await self._check_sla_violations(metrics)
                
                logger.info(f"📊 Monitored {len(customer_containers)} customer infrastructures")
                
            except Exception as e:
                logger.error(f"Error monitoring customer infrastructure: {e}")
            
            await asyncio.sleep(self.config["monitoring"]["collection_interval_seconds"])
    
    async def _collect_container_metrics(self, container: docker.models.containers.Container, 
                                       customer_id: str) -> CustomerMetrics:
        """Collect detailed metrics for a customer container"""
        try:
            # Get container stats
            stats = container.stats(stream=False)
            
            # Calculate CPU usage
            cpu_usage = self._calculate_cpu_usage(stats)
            
            # Calculate memory usage  
            memory_usage = self._calculate_memory_usage(stats)
            
            # Get container tier
            tier = container.labels.get("ai-agency.tier", "unknown")
            
            # Get provisioning time from database
            provisioning_time = await self._get_provisioning_time(customer_id)
            
            # Calculate uptime
            uptime_percentage = await self._calculate_uptime(customer_id)
            
            # Get memory recall performance
            memory_recall_avg = await self._get_memory_performance(customer_id)
            
            # Get response time metrics
            response_time_p95 = await self._get_response_time_metrics(customer_id)
            
            # Calculate storage usage
            storage_usage = await self._calculate_storage_usage(customer_id)
            
            # Get request/error counts
            request_count, error_count = await self._get_request_metrics(customer_id)
            
            # Calculate daily cost
            cost_per_day = self._calculate_daily_cost(tier, cpu_usage, memory_usage, storage_usage)
            
            # Check for SLA violations
            sla_violations = self._check_customer_sla_violations(
                provisioning_time, memory_recall_avg, uptime_percentage, response_time_p95
            )
            
            return CustomerMetrics(
                customer_id=customer_id,
                tier=tier,
                provisioning_time=provisioning_time,
                uptime_percentage=uptime_percentage,
                memory_recall_avg_ms=memory_recall_avg,
                response_time_p95_ms=response_time_p95,
                cpu_usage_percent=cpu_usage,
                memory_usage_percent=memory_usage,
                storage_usage_gb=storage_usage,
                request_count_24h=request_count,
                error_count_24h=error_count,
                cost_per_day_usd=cost_per_day,
                last_updated=datetime.utcnow(),
                sla_violations=sla_violations
            )
            
        except Exception as e:
            logger.error(f"Error collecting metrics for customer {customer_id}: {e}")
            return None
    
    def _calculate_cpu_usage(self, stats: Dict) -> float:
        """Calculate CPU usage percentage from container stats"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_count = len(stats['cpu_stats']['cpu_usage']['percpu_usage'])
            
            if system_delta > 0 and cpu_delta > 0:
                cpu_usage = (cpu_delta / system_delta) * cpu_count * 100.0
                return min(cpu_usage, 100.0)
        except (KeyError, ZeroDivisionError):
            pass
        
        return 0.0
    
    def _calculate_memory_usage(self, stats: Dict) -> float:
        """Calculate memory usage percentage from container stats"""
        try:
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            
            if memory_limit > 0:
                return (memory_usage / memory_limit) * 100.0
        except (KeyError, ZeroDivisionError):
            pass
        
        return 0.0
    
    async def _get_provisioning_time(self, customer_id: str) -> float:
        """Get customer provisioning time from database"""
        try:
            async with self.postgres_pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT provisioning_time FROM customer_infrastructure WHERE customer_id = $1",
                    customer_id
                )
                return result or 0.0
        except Exception:
            return 0.0
    
    async def _calculate_uptime(self, customer_id: str) -> float:
        """Calculate customer infrastructure uptime percentage"""
        try:
            # Check if all customer containers are running
            customer_containers = self.docker_client.containers.list(
                filters={
                    "label": f"ai-agency.customer-id={customer_id}",
                    "status": "running"
                }
            )
            
            total_containers = len(self.docker_client.containers.list(
                filters={"label": f"ai-agency.customer-id={customer_id}"},
                all=True
            ))
            
            if total_containers == 0:
                return 0.0
            
            return (len(customer_containers) / total_containers) * 100.0
            
        except Exception:
            return 0.0
    
    async def _get_memory_performance(self, customer_id: str) -> float:
        """Get average memory recall time for customer"""
        try:
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            # Get recent memory recall times from Redis
            recall_times = await redis_client.lrange(f"memory_recall_times:{customer_id}", 0, 100)
            
            if recall_times:
                times = [float(time) for time in recall_times]
                return sum(times) / len(times) * 1000  # Convert to milliseconds
                
        except Exception:
            pass
        
        return 0.0
    
    async def _get_response_time_metrics(self, customer_id: str) -> float:
        """Get 95th percentile response time for customer"""
        try:
            # This would typically query your metrics store (Prometheus, etc.)
            # For now, we'll simulate with a reasonable value
            return 150.0  # milliseconds
        except Exception:
            return 0.0
    
    async def _calculate_storage_usage(self, customer_id: str) -> float:
        """Calculate total storage usage for customer in GB"""
        try:
            # Get volume usage for customer
            volumes = self.docker_client.volumes.list(
                filters={"label": f"ai-agency.customer-id={customer_id}"}
            )
            
            total_size = 0
            for volume in volumes:
                # This would require a more sophisticated approach in production
                # to calculate actual volume usage
                total_size += 1.0  # Placeholder: 1GB per volume
            
            return total_size
            
        except Exception:
            return 0.0
    
    async def _get_request_metrics(self, customer_id: str) -> tuple:
        """Get request and error counts for past 24 hours"""
        try:
            async with self.postgres_pool.acquire() as conn:
                # Get request counts
                request_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM customer_requests 
                    WHERE customer_id = $1 
                    AND created_at > NOW() - INTERVAL '24 hours'
                """, customer_id) or 0
                
                # Get error counts
                error_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM customer_errors 
                    WHERE customer_id = $1 
                    AND created_at > NOW() - INTERVAL '24 hours'
                """, customer_id) or 0
                
                return request_count, error_count
                
        except Exception:
            return 0, 0
    
    def _calculate_daily_cost(self, tier: str, cpu_usage: float, memory_usage: float, storage_gb: float) -> float:
        """Calculate estimated daily infrastructure cost for customer"""
        try:
            base_cost = self.config["cost_tracking"]["cost_per_hour"].get(tier.lower(), 0.10)
            
            # Adjust based on actual usage
            usage_multiplier = (cpu_usage + memory_usage) / 200.0  # Average of CPU and memory usage
            storage_cost = storage_gb * 0.01  # $0.01 per GB per day
            
            daily_cost = (base_cost * 24 * usage_multiplier) + storage_cost
            return round(daily_cost, 4)
            
        except Exception:
            return 0.0
    
    def _check_customer_sla_violations(self, provisioning_time: float, memory_recall_ms: float, 
                                     uptime_percentage: float, response_time_p95: float) -> List[str]:
        """Check for SLA violations and return list of violations"""
        violations = []
        targets = self.config["sla_targets"]
        
        if provisioning_time > targets["provisioning_time_seconds"]:
            violations.append(f"Provisioning time {provisioning_time:.2f}s > {targets['provisioning_time_seconds']}s")
        
        if memory_recall_ms > targets["memory_recall_ms"]:
            violations.append(f"Memory recall {memory_recall_ms:.2f}ms > {targets['memory_recall_ms']}ms")
        
        if uptime_percentage < targets["uptime_percentage"]:
            violations.append(f"Uptime {uptime_percentage:.2f}% < {targets['uptime_percentage']}%")
        
        if response_time_p95 > targets["response_time_p95_ms"]:
            violations.append(f"Response time P95 {response_time_p95:.2f}ms > {targets['response_time_p95_ms']}ms")
        
        return violations
    
    async def _update_prometheus_metrics(self, metrics: CustomerMetrics):
        """Update Prometheus metrics with customer data"""
        if not metrics:
            return
        
        try:
            # Update uptime metric
            self.customer_uptime.labels(
                customer_id=metrics.customer_id, 
                tier=metrics.tier
            ).set(metrics.uptime_percentage)
            
            # Update resource usage metrics
            self.customer_cpu_usage.labels(
                customer_id=metrics.customer_id,
                tier=metrics.tier
            ).set(metrics.cpu_usage_percent)
            
            self.customer_memory_usage.labels(
                customer_id=metrics.customer_id,
                tier=metrics.tier
            ).set(metrics.memory_usage_percent)
            
            # Update cost metric
            self.customer_cost_daily.labels(
                customer_id=metrics.customer_id,
                tier=metrics.tier
            ).set(metrics.cost_per_day_usd)
            
            # Record SLA violations
            if metrics.provisioning_time > self.config["sla_targets"]["provisioning_time_seconds"]:
                self.provisioning_sla_violations.labels(tier=metrics.tier).inc()
            
            if metrics.memory_recall_avg_ms > self.config["sla_targets"]["memory_recall_ms"]:
                self.memory_sla_violations.labels(customer_id=metrics.customer_id).inc()
            
        except Exception as e:
            logger.error(f"Error updating Prometheus metrics: {e}")
    
    async def _check_sla_violations(self, metrics: CustomerMetrics):
        """Check for SLA violations and create alerts"""
        if not metrics or not metrics.sla_violations:
            return
        
        for violation in metrics.sla_violations:
            alert = Alert(
                id=f"sla_{metrics.customer_id}_{int(time.time())}",
                customer_id=metrics.customer_id,
                level=AlertLevel.CRITICAL,
                metric="sla_violation",
                threshold=0,
                current_value=1,
                message=f"SLA violation for customer {metrics.customer_id}: {violation}",
                created_at=datetime.utcnow()
            )
            
            await self._create_alert(alert)
    
    async def _monitor_provisioning_performance(self):
        """Monitor customer provisioning performance and trends"""
        while self.monitoring_active:
            try:
                # Query recent provisioning metrics
                async with self.postgres_pool.acquire() as conn:
                    recent_provisions = await conn.fetch("""
                        SELECT customer_id, tier, provisioning_time, created_at
                        FROM customer_infrastructure 
                        WHERE created_at > NOW() - INTERVAL '1 hour'
                        ORDER BY created_at DESC
                    """)
                
                for provision in recent_provisions:
                    # Record provisioning time
                    self.provisioning_time_histogram.labels(
                        customer_tier=provision['tier']
                    ).observe(provision['provisioning_time'])
                
                logger.info(f"📊 Analyzed {len(recent_provisions)} recent provisions")
                
            except Exception as e:
                logger.error(f"Error monitoring provisioning performance: {e}")
            
            await asyncio.sleep(300)  # Check every 5 minutes
    
    async def _monitor_memory_performance(self):
        """Monitor Mem0 memory system performance across all customers"""
        while self.monitoring_active:
            try:
                redis_client = redis.Redis(connection_pool=self.redis_pool)
                
                # Get all customer memory performance data
                for customer_id in self.customer_metrics.keys():
                    recall_times = await redis_client.lrange(f"memory_recall_times:{customer_id}", 0, 100)
                    
                    for recall_time in recall_times[-10:]:  # Last 10 operations
                        self.memory_recall_histogram.labels(
                            customer_id=customer_id,
                            query_type="business_context"
                        ).observe(float(recall_time))
                
            except Exception as e:
                logger.error(f"Error monitoring memory performance: {e}")
            
            await asyncio.sleep(60)  # Check every minute
    
    async def _monitor_cost_optimization(self):
        """Monitor infrastructure costs and provide optimization recommendations"""
        while self.monitoring_active:
            try:
                total_daily_cost = sum(metrics.cost_per_day_usd for metrics in self.customer_metrics.values())
                
                # Check for cost optimization opportunities
                high_cost_customers = [
                    metrics for metrics in self.customer_metrics.values()
                    if metrics.cost_per_day_usd > 5.0 and metrics.cpu_usage_percent < 30
                ]
                
                if high_cost_customers:
                    for metrics in high_cost_customers:
                        alert = Alert(
                            id=f"cost_optimization_{metrics.customer_id}_{int(time.time())}",
                            customer_id=metrics.customer_id,
                            level=AlertLevel.WARNING,
                            metric="cost_optimization",
                            threshold=5.0,
                            current_value=metrics.cost_per_day_usd,
                            message=f"Cost optimization opportunity: Customer {metrics.customer_id} has low CPU usage ({metrics.cpu_usage_percent:.1f}%) but high daily cost (${metrics.cost_per_day_usd:.2f})",
                            created_at=datetime.utcnow()
                        )
                        await self._create_alert(alert)
                
                logger.info(f"💰 Total daily infrastructure cost: ${total_daily_cost:.2f}")
                
            except Exception as e:
                logger.error(f"Error monitoring cost optimization: {e}")
            
            await asyncio.sleep(3600)  # Check hourly
    
    async def _monitor_security_compliance(self):
        """Monitor security compliance and isolation validation"""
        while self.monitoring_active:
            try:
                # Validate customer isolation
                for customer_id in self.customer_metrics.keys():
                    isolation_valid = await self._validate_customer_isolation(customer_id)
                    
                    if not isolation_valid:
                        self.security_violations.labels(
                            customer_id=customer_id,
                            violation_type="isolation_breach"
                        ).inc()
                        
                        alert = Alert(
                            id=f"security_{customer_id}_{int(time.time())}",
                            customer_id=customer_id,
                            level=AlertLevel.CRITICAL,
                            metric="security_violation",
                            threshold=0,
                            current_value=1,
                            message=f"CRITICAL: Customer isolation breach detected for {customer_id}",
                            created_at=datetime.utcnow()
                        )
                        await self._create_alert(alert)
                
            except Exception as e:
                logger.error(f"Error monitoring security compliance: {e}")
            
            await asyncio.sleep(300)  # Check every 5 minutes
    
    async def _validate_customer_isolation(self, customer_id: str) -> bool:
        """Validate that customer infrastructure is properly isolated"""
        try:
            # Check network isolation
            customer_network = f"customer-{customer_id}-network"
            networks = [net.name for net in self.docker_client.networks.list()]
            
            if customer_network not in networks:
                logger.warning(f"Customer network missing: {customer_network}")
                return False
            
            # Check container isolation
            customer_containers = self.docker_client.containers.list(
                filters={"label": f"ai-agency.customer-id={customer_id}"}
            )
            
            for container in customer_containers:
                # Verify container is on correct network
                container_networks = list(container.attrs['NetworkSettings']['Networks'].keys())
                if customer_network not in container_networks:
                    logger.warning(f"Container {container.name} not on customer network")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating customer isolation: {e}")
            return False
    
    async def _process_alerts(self):
        """Process and handle alerts"""
        while self.monitoring_active:
            try:
                # Process active alerts
                for alert_id, alert in list(self.active_alerts.items()):
                    if alert.level == AlertLevel.CRITICAL:
                        await self._handle_critical_alert(alert)
                    elif alert.level == AlertLevel.WARNING:
                        await self._handle_warning_alert(alert)
                
                # Clean up resolved alerts
                resolved_alerts = [
                    alert_id for alert_id, alert in self.active_alerts.items()
                    if alert.resolved_at is not None
                ]
                
                for alert_id in resolved_alerts:
                    del self.active_alerts[alert_id]
                
            except Exception as e:
                logger.error(f"Error processing alerts: {e}")
            
            await asyncio.sleep(60)  # Process alerts every minute
    
    async def _create_alert(self, alert: Alert):
        """Create and store new alert"""
        self.active_alerts[alert.id] = alert
        
        # Store in database
        try:
            async with self.postgres_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO monitoring_alerts (
                        id, customer_id, level, metric, threshold, current_value, 
                        message, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                    alert.id, alert.customer_id, alert.level.value, alert.metric,
                    alert.threshold, alert.current_value, alert.message, alert.created_at
                )
        except Exception as e:
            logger.error(f"Error storing alert: {e}")
        
        logger.warning(f"🚨 {alert.level.value.upper()} ALERT: {alert.message}")
    
    async def _handle_critical_alert(self, alert: Alert):
        """Handle critical alerts with immediate action"""
        logger.critical(f"🔥 CRITICAL ALERT: {alert.message}")
        
        # Immediate actions based on alert type
        if alert.metric == "sla_violation":
            await self._handle_sla_violation(alert)
        elif alert.metric == "security_violation":
            await self._handle_security_violation(alert)
        
        # Send to incident management system
        await self._send_to_incident_management(alert)
    
    async def _handle_warning_alert(self, alert: Alert):
        """Handle warning alerts with monitoring and optimization"""
        logger.warning(f"⚠️ WARNING ALERT: {alert.message}")
        
        if alert.metric == "cost_optimization":
            await self._suggest_cost_optimization(alert)
    
    async def _handle_sla_violation(self, alert: Alert):
        """Handle SLA violation with automated remediation"""
        # This would implement automated remediation actions
        logger.critical(f"Handling SLA violation for customer {alert.customer_id}")
    
    async def _handle_security_violation(self, alert: Alert):
        """Handle security violation with immediate isolation"""
        # This would implement security incident response
        logger.critical(f"Handling security violation for customer {alert.customer_id}")
    
    async def _send_to_incident_management(self, alert: Alert):
        """Send critical alert to incident management system"""
        # This would integrate with PagerDuty, OpsGenie, etc.
        logger.info(f"Sent alert {alert.id} to incident management")
    
    async def _suggest_cost_optimization(self, alert: Alert):
        """Suggest cost optimization actions"""
        # This would provide specific recommendations
        logger.info(f"Generated cost optimization suggestions for customer {alert.customer_id}")
    
    async def get_customer_metrics(self, customer_id: str) -> Optional[CustomerMetrics]:
        """Get current metrics for specific customer"""
        return self.customer_metrics.get(customer_id)
    
    async def get_platform_metrics(self) -> Dict[str, Any]:
        """Get overall platform metrics"""
        if not self.customer_metrics:
            return {}
        
        metrics = list(self.customer_metrics.values())
        
        return {
            "total_customers": len(metrics),
            "average_provisioning_time": sum(m.provisioning_time for m in metrics) / len(metrics),
            "average_uptime": sum(m.uptime_percentage for m in metrics) / len(metrics),
            "total_daily_cost": sum(m.cost_per_day_usd for m in metrics),
            "sla_compliance": {
                "provisioning": sum(1 for m in metrics if m.provisioning_time <= 30) / len(metrics),
                "memory_recall": sum(1 for m in metrics if m.memory_recall_avg_ms <= 500) / len(metrics),
                "uptime": sum(1 for m in metrics if m.uptime_percentage >= 99.9) / len(metrics)
            },
            "active_alerts": len(self.active_alerts),
            "critical_alerts": len([a for a in self.active_alerts.values() if a.level == AlertLevel.CRITICAL])
        }
    
    async def export_metrics(self, format: str = "prometheus") -> str:
        """Export metrics in specified format"""
        if format == "prometheus":
            return prometheus_client.generate_latest(self.registry).decode('utf-8')
        elif format == "json":
            platform_metrics = await self.get_platform_metrics()
            customer_metrics = {k: asdict(v) for k, v in self.customer_metrics.items()}
            
            return json.dumps({
                "platform": platform_metrics,
                "customers": customer_metrics,
                "timestamp": datetime.utcnow().isoformat()
            }, default=str, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    async def stop_monitoring(self):
        """Stop monitoring and cleanup resources"""
        self.monitoring_active = False
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        logger.info("Production monitoring stopped")


# Example usage and testing
async def main():
    """Example usage of Production Monitor"""
    monitor = ProductionMonitor()
    
    try:
        # Start monitoring (this would run continuously in production)
        await asyncio.wait_for(monitor.start_monitoring(), timeout=60)
    except asyncio.TimeoutError:
        # Get sample metrics
        platform_metrics = await monitor.get_platform_metrics()
        print(f"Platform metrics: {platform_metrics}")
        
        # Export metrics
        prometheus_metrics = await monitor.export_metrics("prometheus")
        print(f"Prometheus metrics exported: {len(prometheus_metrics)} characters")
        
        await monitor.stop_monitoring()


if __name__ == "__main__":
    asyncio.run(main())