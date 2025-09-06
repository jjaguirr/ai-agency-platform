"""
Auto-Scaling Manager for Per-Customer Infrastructure

Implements intelligent auto-scaling based on customer usage patterns and performance metrics.
Provides automated resource scaling, cost optimization, and capacity management.

Key Features:
- Tier-based auto-scaling (Starter/Professional/Enterprise)
- Resource optimization based on usage patterns
- Cost-aware scaling decisions
- Predictive scaling for anticipated load
- Automated recovery from resource constraints
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import docker
import asyncpg
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class ScalingAction(Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    MIGRATE_TIER = "migrate_tier"
    NO_ACTION = "no_action"


class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"


@dataclass
class ScalingDecision:
    """Scaling decision with justification and metrics"""
    customer_id: str
    action: ScalingAction
    resource_type: ResourceType
    current_allocation: Dict[str, Any]
    target_allocation: Dict[str, Any]
    justification: str
    cost_impact_daily: float
    confidence_score: float
    created_at: datetime


@dataclass
class CustomerUsagePattern:
    """Customer usage pattern analysis"""
    customer_id: str
    tier: str
    avg_cpu_usage: float
    avg_memory_usage: float
    peak_cpu_usage: float
    peak_memory_usage: float
    request_rate_avg: float
    request_rate_peak: float
    storage_growth_gb_daily: float
    error_rate: float
    response_time_avg: float
    usage_trend: str  # "increasing", "decreasing", "stable"
    seasonal_patterns: List[Dict[str, Any]]
    cost_efficiency_score: float


class AutoScalingManager:
    """
    Intelligent auto-scaling manager for per-customer AI Agency Platform infrastructure.
    
    Capabilities:
    - Real-time resource monitoring and scaling
    - Predictive scaling based on usage patterns
    - Cost-optimized scaling decisions
    - Tier migration recommendations
    - Automated recovery from resource constraints
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize auto-scaling manager"""
        self.config = config or self._default_config()
        
        # Infrastructure connections
        self.docker_client = docker.from_env()
        self.postgres_pool = None
        self.redis_pool = None
        
        # Scaling state
        self.customer_patterns = {}  # customer_id -> CustomerUsagePattern
        self.scaling_decisions = []   # List of recent scaling decisions
        self.scaling_active = False
        
        # Scaling locks to prevent concurrent modifications
        self.scaling_locks = {}  # customer_id -> lock
        
        logger.info("Initialized Auto-Scaling Manager")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default auto-scaling configuration"""
        return {
            "scaling_thresholds": {
                "cpu_scale_up": 80,      # Scale up when CPU > 80%
                "cpu_scale_down": 30,    # Scale down when CPU < 30%
                "memory_scale_up": 85,   # Scale up when memory > 85%
                "memory_scale_down": 40, # Scale down when memory < 40%
                "response_time_ms": 500, # Scale up when response time > 500ms
                "error_rate_percent": 5  # Scale up when error rate > 5%
            },
            "scaling_policies": {
                "scale_up_factor": 1.5,     # Increase resources by 50%
                "scale_down_factor": 0.7,   # Decrease resources by 30%
                "min_observation_minutes": 15,  # Minimum observation before scaling
                "cooldown_minutes": 30,     # Cooldown between scaling actions
                "max_scale_up_per_day": 3,  # Max scale-up events per customer per day
                "max_scale_down_per_day": 2 # Max scale-down events per customer per day
            },
            "tier_migration": {
                "usage_threshold_days": 7,  # Analyze 7 days for tier migration
                "upgrade_threshold": 0.8,   # Upgrade if consistently > 80% usage
                "downgrade_threshold": 0.3, # Downgrade if consistently < 30% usage
                "confidence_required": 0.85 # Minimum confidence for tier migration
            },
            "cost_optimization": {
                "max_cost_increase_percent": 25,  # Max 25% cost increase per scaling
                "cost_efficiency_threshold": 0.6, # Efficiency score for optimization
                "optimize_on_weekends": True,      # Optimize resources on weekends
                "predictive_scaling_days": 3       # Days ahead for predictive scaling
            },
            "resource_limits": {
                "starter": {
                    "cpu_min": 0.5, "cpu_max": 2.0,
                    "memory_min": "1GB", "memory_max": "4GB",
                    "storage_max": "20GB"
                },
                "professional": {
                    "cpu_min": 1.0, "cpu_max": 4.0,
                    "memory_min": "2GB", "memory_max": "8GB",
                    "storage_max": "100GB"
                },
                "enterprise": {
                    "cpu_min": 2.0, "cpu_max": 8.0,
                    "memory_min": "4GB", "memory_max": "16GB",
                    "storage_max": "500GB"
                }
            }
        }
    
    async def start_auto_scaling(self):
        """Start continuous auto-scaling monitoring and execution"""
        if self.scaling_active:
            logger.warning("Auto-scaling already active")
            return
        
        self.scaling_active = True
        
        # Initialize connections
        await self._init_connections()
        
        # Start scaling tasks
        scaling_tasks = [
            self._monitor_usage_patterns(),
            self._execute_scaling_decisions(),
            self._analyze_tier_migrations(),
            self._predictive_scaling(),
            self._cost_optimization_cleanup()
        ]
        
        logger.info("🚀 Starting auto-scaling manager...")
        await asyncio.gather(*scaling_tasks)
    
    async def _init_connections(self):
        """Initialize database connections"""
        if not self.postgres_pool:
            self.postgres_pool = await asyncpg.create_pool(
                host="localhost",
                port=5432,
                database="mcphub",
                user="mcphub",
                password="mcphub_password",
                min_size=2,
                max_size=10
            )
        
        if not self.redis_pool:
            self.redis_pool = redis.ConnectionPool.from_url("redis://localhost:6379", db=1)
    
    async def _monitor_usage_patterns(self):
        """Monitor customer usage patterns and identify scaling opportunities"""
        while self.scaling_active:
            try:
                # Get all customer containers
                customer_containers = self.docker_client.containers.list(
                    filters={"label": "ai-agency.service=mcp-server"}
                )
                
                for container in customer_containers:
                    customer_id = container.labels.get("ai-agency.customer-id")
                    if not customer_id:
                        continue
                    
                    # Analyze usage pattern
                    pattern = await self._analyze_customer_usage(customer_id, container)
                    if pattern:
                        self.customer_patterns[customer_id] = pattern
                        
                        # Check if scaling is needed
                        decision = await self._evaluate_scaling_need(pattern)
                        if decision and decision.action != ScalingAction.NO_ACTION:
                            self.scaling_decisions.append(decision)
                
                logger.info(f"📊 Analyzed usage patterns for {len(customer_containers)} customers")
                
            except Exception as e:
                logger.error(f"Error monitoring usage patterns: {e}")
            
            await asyncio.sleep(300)  # Analyze every 5 minutes
    
    async def _analyze_customer_usage(self, customer_id: str, container: docker.models.containers.Container) -> Optional[CustomerUsagePattern]:
        """Analyze detailed usage pattern for a customer"""
        try:
            # Get container stats
            stats = container.stats(stream=False)
            
            # Calculate current resource usage
            cpu_usage = self._calculate_cpu_usage(stats)
            memory_usage = self._calculate_memory_usage(stats)
            
            # Get tier
            tier = container.labels.get("ai-agency.tier", "starter")
            
            # Get historical metrics from database
            historical_metrics = await self._get_historical_metrics(customer_id, days=7)
            
            # Calculate usage statistics
            cpu_metrics = self._calculate_usage_statistics(historical_metrics, "cpu_usage")
            memory_metrics = self._calculate_usage_statistics(historical_metrics, "memory_usage")
            request_metrics = await self._get_request_rate_metrics(customer_id)
            
            # Analyze usage trends
            usage_trend = self._analyze_usage_trend(historical_metrics)
            
            # Calculate storage growth
            storage_growth = await self._calculate_storage_growth(customer_id)
            
            # Get error rate and response time
            error_rate = await self._get_error_rate(customer_id)
            response_time = await self._get_avg_response_time(customer_id)
            
            # Detect seasonal patterns
            seasonal_patterns = self._detect_seasonal_patterns(historical_metrics)
            
            # Calculate cost efficiency score
            cost_efficiency = self._calculate_cost_efficiency(
                cpu_metrics["avg"], memory_metrics["avg"], request_metrics["avg"]
            )
            
            return CustomerUsagePattern(
                customer_id=customer_id,
                tier=tier,
                avg_cpu_usage=cpu_metrics["avg"],
                avg_memory_usage=memory_metrics["avg"],
                peak_cpu_usage=cpu_metrics["peak"],
                peak_memory_usage=memory_metrics["peak"],
                request_rate_avg=request_metrics["avg"],
                request_rate_peak=request_metrics["peak"],
                storage_growth_gb_daily=storage_growth,
                error_rate=error_rate,
                response_time_avg=response_time,
                usage_trend=usage_trend,
                seasonal_patterns=seasonal_patterns,
                cost_efficiency_score=cost_efficiency
            )
            
        except Exception as e:
            logger.error(f"Error analyzing usage for customer {customer_id}: {e}")
            return None
    
    def _calculate_cpu_usage(self, stats: Dict) -> float:
        """Calculate CPU usage from container stats"""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            cpu_count = len(stats['cpu_stats']['cpu_usage']['percpu_usage'])
            
            if system_delta > 0 and cpu_delta > 0:
                return min((cpu_delta / system_delta) * cpu_count * 100.0, 100.0)
        except (KeyError, ZeroDivisionError):
            pass
        return 0.0
    
    def _calculate_memory_usage(self, stats: Dict) -> float:
        """Calculate memory usage from container stats"""
        try:
            memory_usage = stats['memory_stats']['usage']
            memory_limit = stats['memory_stats']['limit']
            return (memory_usage / memory_limit) * 100.0 if memory_limit > 0 else 0.0
        except (KeyError, ZeroDivisionError):
            return 0.0
    
    async def _get_historical_metrics(self, customer_id: str, days: int) -> List[Dict]:
        """Get historical metrics for usage analysis"""
        try:
            async with self.postgres_pool.acquire() as conn:
                metrics = await conn.fetch("""
                    SELECT cpu_usage, memory_usage, request_count, error_count, 
                           response_time, created_at
                    FROM customer_metrics 
                    WHERE customer_id = $1 
                    AND created_at > NOW() - INTERVAL '%d days'
                    ORDER BY created_at ASC
                """ % days, customer_id)
                
                return [dict(row) for row in metrics]
        except Exception:
            return []
    
    def _calculate_usage_statistics(self, metrics: List[Dict], field: str) -> Dict[str, float]:
        """Calculate usage statistics from historical data"""
        if not metrics:
            return {"avg": 0.0, "peak": 0.0, "min": 0.0}
        
        values = [m.get(field, 0) for m in metrics if m.get(field) is not None]
        
        if not values:
            return {"avg": 0.0, "peak": 0.0, "min": 0.0}
        
        return {
            "avg": sum(values) / len(values),
            "peak": max(values),
            "min": min(values)
        }
    
    async def _get_request_rate_metrics(self, customer_id: str) -> Dict[str, float]:
        """Get request rate metrics"""
        try:
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            
            # Get request counts from last hour
            request_counts = await redis_client.lrange(f"request_counts:{customer_id}", 0, 60)
            
            if request_counts:
                counts = [float(count) for count in request_counts]
                return {
                    "avg": sum(counts) / len(counts),
                    "peak": max(counts)
                }
        except Exception:
            pass
        
        return {"avg": 0.0, "peak": 0.0}
    
    def _analyze_usage_trend(self, metrics: List[Dict]) -> str:
        """Analyze usage trend over time"""
        if len(metrics) < 2:
            return "stable"
        
        # Simple trend analysis using CPU usage
        recent_avg = sum(m.get("cpu_usage", 0) for m in metrics[-24:]) / min(len(metrics), 24)  # Last 24 hours
        older_avg = sum(m.get("cpu_usage", 0) for m in metrics[-48:-24]) / min(len(metrics) - 24, 24) if len(metrics) > 24 else recent_avg
        
        if recent_avg > older_avg * 1.2:
            return "increasing"
        elif recent_avg < older_avg * 0.8:
            return "decreasing"
        else:
            return "stable"
    
    async def _calculate_storage_growth(self, customer_id: str) -> float:
        """Calculate daily storage growth rate"""
        try:
            async with self.postgres_pool.acquire() as conn:
                growth_data = await conn.fetch("""
                    SELECT storage_usage, DATE(created_at) as date
                    FROM customer_metrics
                    WHERE customer_id = $1
                    AND created_at > NOW() - INTERVAL '7 days'
                    ORDER BY created_at ASC
                """, customer_id)
                
                if len(growth_data) >= 2:
                    first_storage = growth_data[0]['storage_usage']
                    last_storage = growth_data[-1]['storage_usage']
                    days = (growth_data[-1]['date'] - growth_data[0]['date']).days or 1
                    
                    return (last_storage - first_storage) / days
        except Exception:
            pass
        
        return 0.0
    
    async def _get_error_rate(self, customer_id: str) -> float:
        """Get customer error rate percentage"""
        try:
            async with self.postgres_pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT 
                        COALESCE(SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END), 0) as errors,
                        COALESCE(COUNT(*), 0) as total
                    FROM customer_requests
                    WHERE customer_id = $1
                    AND created_at > NOW() - INTERVAL '1 hour'
                """, customer_id)
                
                if result and result['total'] > 0:
                    return (result['errors'] / result['total']) * 100.0
        except Exception:
            pass
        
        return 0.0
    
    async def _get_avg_response_time(self, customer_id: str) -> float:
        """Get average response time"""
        try:
            async with self.postgres_pool.acquire() as conn:
                result = await conn.fetchval("""
                    SELECT AVG(response_time)
                    FROM customer_requests
                    WHERE customer_id = $1
                    AND created_at > NOW() - INTERVAL '1 hour'
                """, customer_id)
                
                return result or 0.0
        except Exception:
            return 0.0
    
    def _detect_seasonal_patterns(self, metrics: List[Dict]) -> List[Dict[str, Any]]:
        """Detect seasonal usage patterns"""
        # Simple implementation - could be enhanced with more sophisticated analysis
        if len(metrics) < 168:  # Less than 7 days of hourly data
            return []
        
        # Group by hour of day
        hourly_patterns = {}
        for metric in metrics:
            hour = metric['created_at'].hour
            if hour not in hourly_patterns:
                hourly_patterns[hour] = []
            hourly_patterns[hour].append(metric.get('cpu_usage', 0))
        
        patterns = []
        for hour, usages in hourly_patterns.items():
            avg_usage = sum(usages) / len(usages)
            patterns.append({
                "hour": hour,
                "avg_cpu_usage": avg_usage,
                "pattern_type": "daily"
            })
        
        return patterns
    
    def _calculate_cost_efficiency(self, avg_cpu: float, avg_memory: float, avg_requests: float) -> float:
        """Calculate cost efficiency score (0-1, higher is more efficient)"""
        try:
            # Simple efficiency calculation
            resource_utilization = (avg_cpu + avg_memory) / 200.0  # Average of CPU and memory
            request_efficiency = min(avg_requests / 100.0, 1.0)    # Normalize request rate
            
            # Combine factors
            efficiency = (resource_utilization * 0.6) + (request_efficiency * 0.4)
            return min(max(efficiency, 0.0), 1.0)
        except:
            return 0.5  # Default moderate efficiency
    
    async def _evaluate_scaling_need(self, pattern: CustomerUsagePattern) -> Optional[ScalingDecision]:
        """Evaluate if customer needs scaling based on usage pattern"""
        try:
            thresholds = self.config["scaling_thresholds"]
            
            # Check CPU scaling needs
            if pattern.avg_cpu_usage > thresholds["cpu_scale_up"]:
                return await self._create_scale_up_decision(pattern, ResourceType.CPU)
            elif pattern.avg_cpu_usage < thresholds["cpu_scale_down"]:
                return await self._create_scale_down_decision(pattern, ResourceType.CPU)
            
            # Check memory scaling needs
            if pattern.avg_memory_usage > thresholds["memory_scale_up"]:
                return await self._create_scale_up_decision(pattern, ResourceType.MEMORY)
            elif pattern.avg_memory_usage < thresholds["memory_scale_down"]:
                return await self._create_scale_down_decision(pattern, ResourceType.MEMORY)
            
            # Check performance-based scaling
            if pattern.response_time_avg > thresholds["response_time_ms"]:
                return await self._create_performance_scale_up_decision(pattern)
            
            if pattern.error_rate > thresholds["error_rate_percent"]:
                return await self._create_performance_scale_up_decision(pattern)
            
            # Check tier migration needs
            tier_decision = await self._evaluate_tier_migration(pattern)
            if tier_decision:
                return tier_decision
            
        except Exception as e:
            logger.error(f"Error evaluating scaling need for {pattern.customer_id}: {e}")
        
        return None
    
    async def _create_scale_up_decision(self, pattern: CustomerUsagePattern, resource_type: ResourceType) -> ScalingDecision:
        """Create scale-up decision"""
        current_resources = await self._get_current_resources(pattern.customer_id)
        scale_factor = self.config["scaling_policies"]["scale_up_factor"]
        
        if resource_type == ResourceType.CPU:
            target_cpu = min(current_resources["cpu"] * scale_factor, 
                           self.config["resource_limits"][pattern.tier]["cpu_max"])
            target_resources = {**current_resources, "cpu": target_cpu}
            justification = f"CPU usage {pattern.avg_cpu_usage:.1f}% exceeds threshold"
        else:  # MEMORY
            current_memory_gb = float(current_resources["memory"].rstrip("GB"))
            target_memory_gb = min(current_memory_gb * scale_factor, 
                                 float(self.config["resource_limits"][pattern.tier]["memory_max"].rstrip("GB")))
            target_resources = {**current_resources, "memory": f"{target_memory_gb}GB"}
            justification = f"Memory usage {pattern.avg_memory_usage:.1f}% exceeds threshold"
        
        cost_impact = self._calculate_cost_impact(current_resources, target_resources, pattern.tier)
        confidence = 0.8  # High confidence for threshold-based scaling
        
        return ScalingDecision(
            customer_id=pattern.customer_id,
            action=ScalingAction.SCALE_UP,
            resource_type=resource_type,
            current_allocation=current_resources,
            target_allocation=target_resources,
            justification=justification,
            cost_impact_daily=cost_impact,
            confidence_score=confidence,
            created_at=datetime.utcnow()
        )
    
    async def _create_scale_down_decision(self, pattern: CustomerUsagePattern, resource_type: ResourceType) -> Optional[ScalingDecision]:
        """Create scale-down decision with safety checks"""
        # Only scale down if usage is consistently low
        if pattern.usage_trend == "increasing":
            return None
        
        current_resources = await self._get_current_resources(pattern.customer_id)
        scale_factor = self.config["scaling_policies"]["scale_down_factor"]
        
        if resource_type == ResourceType.CPU:
            target_cpu = max(current_resources["cpu"] * scale_factor,
                           self.config["resource_limits"][pattern.tier]["cpu_min"])
            # Don't scale down if already at minimum
            if target_cpu >= current_resources["cpu"]:
                return None
            target_resources = {**current_resources, "cpu": target_cpu}
            justification = f"CPU usage {pattern.avg_cpu_usage:.1f}% below threshold, trend: {pattern.usage_trend}"
        else:  # MEMORY
            current_memory_gb = float(current_resources["memory"].rstrip("GB"))
            target_memory_gb = max(current_memory_gb * scale_factor,
                                 float(self.config["resource_limits"][pattern.tier]["memory_min"].rstrip("GB")))
            if target_memory_gb >= current_memory_gb:
                return None
            target_resources = {**current_resources, "memory": f"{target_memory_gb}GB"}
            justification = f"Memory usage {pattern.avg_memory_usage:.1f}% below threshold, trend: {pattern.usage_trend}"
        
        cost_impact = self._calculate_cost_impact(current_resources, target_resources, pattern.tier)
        confidence = 0.7  # Lower confidence for scale-down to be conservative
        
        return ScalingDecision(
            customer_id=pattern.customer_id,
            action=ScalingAction.SCALE_DOWN,
            resource_type=resource_type,
            current_allocation=current_resources,
            target_allocation=target_resources,
            justification=justification,
            cost_impact_daily=cost_impact,
            confidence_score=confidence,
            created_at=datetime.utcnow()
        )
    
    async def _create_performance_scale_up_decision(self, pattern: CustomerUsagePattern) -> ScalingDecision:
        """Create performance-based scale-up decision"""
        current_resources = await self._get_current_resources(pattern.customer_id)
        
        # Scale up both CPU and memory for performance issues
        scale_factor = 1.3  # More conservative for performance scaling
        target_cpu = min(current_resources["cpu"] * scale_factor,
                        self.config["resource_limits"][pattern.tier]["cpu_max"])
        current_memory_gb = float(current_resources["memory"].rstrip("GB"))
        target_memory_gb = min(current_memory_gb * scale_factor,
                              float(self.config["resource_limits"][pattern.tier]["memory_max"].rstrip("GB")))
        
        target_resources = {
            **current_resources,
            "cpu": target_cpu,
            "memory": f"{target_memory_gb}GB"
        }
        
        justification = f"Performance degradation: response time {pattern.response_time_avg:.1f}ms, error rate {pattern.error_rate:.1f}%"
        cost_impact = self._calculate_cost_impact(current_resources, target_resources, pattern.tier)
        
        return ScalingDecision(
            customer_id=pattern.customer_id,
            action=ScalingAction.SCALE_UP,
            resource_type=ResourceType.CPU,  # Primary constraint
            current_allocation=current_resources,
            target_allocation=target_resources,
            justification=justification,
            cost_impact_daily=cost_impact,
            confidence_score=0.9,  # High confidence for performance issues
            created_at=datetime.utcnow()
        )
    
    async def _evaluate_tier_migration(self, pattern: CustomerUsagePattern) -> Optional[ScalingDecision]:
        """Evaluate if customer should migrate to different tier"""
        tier_config = self.config["tier_migration"]
        
        # Check if customer consistently exceeds current tier limits
        if (pattern.avg_cpu_usage > tier_config["upgrade_threshold"] * 100 and 
            pattern.avg_memory_usage > tier_config["upgrade_threshold"] * 100 and
            pattern.usage_trend in ["increasing", "stable"]):
            
            next_tier = self._get_next_tier_up(pattern.tier)
            if next_tier:
                current_resources = await self._get_current_resources(pattern.customer_id)
                target_resources = self._get_default_tier_resources(next_tier)
                cost_impact = self._calculate_tier_cost_impact(pattern.tier, next_tier)
                
                return ScalingDecision(
                    customer_id=pattern.customer_id,
                    action=ScalingAction.MIGRATE_TIER,
                    resource_type=ResourceType.CPU,
                    current_allocation={"tier": pattern.tier, **current_resources},
                    target_allocation={"tier": next_tier, **target_resources},
                    justification=f"Consistent high usage: CPU {pattern.avg_cpu_usage:.1f}%, Memory {pattern.avg_memory_usage:.1f}%",
                    cost_impact_daily=cost_impact,
                    confidence_score=0.85,
                    created_at=datetime.utcnow()
                )
        
        # Check if customer consistently under-utilizes current tier
        elif (pattern.avg_cpu_usage < tier_config["downgrade_threshold"] * 100 and
              pattern.avg_memory_usage < tier_config["downgrade_threshold"] * 100 and
              pattern.usage_trend in ["decreasing", "stable"] and
              pattern.cost_efficiency_score < self.config["cost_optimization"]["cost_efficiency_threshold"]):
            
            next_tier = self._get_next_tier_down(pattern.tier)
            if next_tier:
                current_resources = await self._get_current_resources(pattern.customer_id)
                target_resources = self._get_default_tier_resources(next_tier)
                cost_impact = self._calculate_tier_cost_impact(pattern.tier, next_tier)
                
                return ScalingDecision(
                    customer_id=pattern.customer_id,
                    action=ScalingAction.MIGRATE_TIER,
                    resource_type=ResourceType.CPU,
                    current_allocation={"tier": pattern.tier, **current_resources},
                    target_allocation={"tier": next_tier, **target_resources},
                    justification=f"Under-utilization: CPU {pattern.avg_cpu_usage:.1f}%, Memory {pattern.avg_memory_usage:.1f}%, Cost efficiency {pattern.cost_efficiency_score:.2f}",
                    cost_impact_daily=cost_impact,
                    confidence_score=0.75,
                    created_at=datetime.utcnow()
                )
        
        return None
    
    async def _get_current_resources(self, customer_id: str) -> Dict[str, Any]:
        """Get current resource allocation for customer"""
        try:
            containers = self.docker_client.containers.list(
                filters={"label": f"ai-agency.customer-id={customer_id}"}
            )
            
            if containers:
                container = containers[0]  # Use MCP server container as reference
                
                # Get CPU and memory limits from container
                cpu_limit = container.attrs.get('HostConfig', {}).get('CpuQuota', 100000) / 100000.0
                memory_limit_bytes = container.attrs.get('HostConfig', {}).get('Memory', 2147483648)
                memory_limit_gb = memory_limit_bytes / (1024**3)
                
                return {
                    "cpu": cpu_limit,
                    "memory": f"{memory_limit_gb:.1f}GB",
                    "container_id": container.id
                }
        except Exception:
            pass
        
        # Default resources if unable to detect
        return {"cpu": 1.0, "memory": "2GB", "container_id": None}
    
    def _get_next_tier_up(self, current_tier: str) -> Optional[str]:
        """Get next higher tier"""
        tier_order = ["starter", "professional", "enterprise"]
        try:
            current_index = tier_order.index(current_tier.lower())
            if current_index < len(tier_order) - 1:
                return tier_order[current_index + 1]
        except ValueError:
            pass
        return None
    
    def _get_next_tier_down(self, current_tier: str) -> Optional[str]:
        """Get next lower tier"""
        tier_order = ["starter", "professional", "enterprise"]
        try:
            current_index = tier_order.index(current_tier.lower())
            if current_index > 0:
                return tier_order[current_index - 1]
        except ValueError:
            pass
        return None
    
    def _get_default_tier_resources(self, tier: str) -> Dict[str, Any]:
        """Get default resource allocation for tier"""
        limits = self.config["resource_limits"][tier.lower()]
        return {
            "cpu": (limits["cpu_min"] + limits["cpu_max"]) / 2,  # Use middle of range
            "memory": limits["memory_min"]  # Start with minimum memory
        }
    
    def _calculate_cost_impact(self, current: Dict, target: Dict, tier: str) -> float:
        """Calculate daily cost impact of resource change"""
        cost_per_cpu_hour = 0.05  # $0.05 per CPU hour
        cost_per_gb_hour = 0.02   # $0.02 per GB memory hour
        
        cpu_diff = target.get("cpu", current.get("cpu", 1.0)) - current.get("cpu", 1.0)
        
        current_memory_gb = float(str(current.get("memory", "2GB")).rstrip("GB"))
        target_memory_gb = float(str(target.get("memory", "2GB")).rstrip("GB"))
        memory_diff = target_memory_gb - current_memory_gb
        
        daily_cost_change = (cpu_diff * cost_per_cpu_hour * 24) + (memory_diff * cost_per_gb_hour * 24)
        return daily_cost_change
    
    def _calculate_tier_cost_impact(self, current_tier: str, target_tier: str) -> float:
        """Calculate daily cost impact of tier migration"""
        tier_costs = {"starter": 2.40, "professional": 6.00, "enterprise": 12.00}  # Daily costs
        
        current_cost = tier_costs.get(current_tier.lower(), 2.40)
        target_cost = tier_costs.get(target_tier.lower(), 2.40)
        
        return target_cost - current_cost
    
    async def _execute_scaling_decisions(self):
        """Execute approved scaling decisions"""
        while self.scaling_active:
            try:
                # Process pending scaling decisions
                decisions_to_execute = self.scaling_decisions[:10]  # Execute up to 10 at a time
                self.scaling_decisions = self.scaling_decisions[10:]
                
                for decision in decisions_to_execute:
                    if await self._should_execute_decision(decision):
                        success = await self._execute_scaling_action(decision)
                        if success:
                            await self._log_scaling_action(decision)
                        else:
                            logger.error(f"Failed to execute scaling action for {decision.customer_id}")
                
                if decisions_to_execute:
                    logger.info(f"Executed {len(decisions_to_execute)} scaling decisions")
                
            except Exception as e:
                logger.error(f"Error executing scaling decisions: {e}")
            
            await asyncio.sleep(60)  # Execute every minute
    
    async def _should_execute_decision(self, decision: ScalingDecision) -> bool:
        """Check if scaling decision should be executed"""
        # Check cooldown period
        last_scaling = await self._get_last_scaling_time(decision.customer_id)
        if last_scaling:
            cooldown_minutes = self.config["scaling_policies"]["cooldown_minutes"]
            if (datetime.utcnow() - last_scaling).total_seconds() < cooldown_minutes * 60:
                return False
        
        # Check daily limits
        daily_scalings = await self._get_daily_scaling_count(decision.customer_id, decision.action)
        max_daily = self.config["scaling_policies"].get(f"max_{decision.action.value}_per_day", 3)
        
        if daily_scalings >= max_daily:
            return False
        
        # Check cost impact limits
        max_cost_increase = self.config["cost_optimization"]["max_cost_increase_percent"]
        if decision.cost_impact_daily > 0:  # Cost increase
            current_daily_cost = await self._get_current_daily_cost(decision.customer_id)
            cost_increase_percent = (decision.cost_impact_daily / current_daily_cost) * 100
            
            if cost_increase_percent > max_cost_increase:
                logger.warning(f"Scaling decision for {decision.customer_id} exceeds cost limit: {cost_increase_percent:.1f}%")
                return False
        
        return True
    
    async def _execute_scaling_action(self, decision: ScalingDecision) -> bool:
        """Execute the actual scaling action"""
        try:
            # Get scaling lock for customer
            if decision.customer_id in self.scaling_locks:
                return False  # Already scaling
            
            self.scaling_locks[decision.customer_id] = time.time()
            
            try:
                if decision.action == ScalingAction.MIGRATE_TIER:
                    success = await self._migrate_customer_tier(decision)
                elif decision.action in [ScalingAction.SCALE_UP, ScalingAction.SCALE_DOWN]:
                    success = await self._scale_customer_resources(decision)
                else:
                    success = False
                
                return success
                
            finally:
                # Release scaling lock
                self.scaling_locks.pop(decision.customer_id, None)
                
        except Exception as e:
            logger.error(f"Error executing scaling action: {e}")
            return False
    
    async def _scale_customer_resources(self, decision: ScalingDecision) -> bool:
        """Scale customer container resources"""
        try:
            container_id = decision.current_allocation.get("container_id")
            if not container_id:
                return False
            
            container = self.docker_client.containers.get(container_id)
            
            # Calculate new resource limits
            target_cpu = decision.target_allocation["cpu"]
            target_memory_str = decision.target_allocation["memory"]
            target_memory_bytes = int(float(target_memory_str.rstrip("GB")) * 1024**3)
            
            # Update container resources
            container.update(
                cpu_period=100000,
                cpu_quota=int(target_cpu * 100000),
                mem_limit=target_memory_bytes
            )
            
            logger.info(f"Scaled customer {decision.customer_id}: CPU={target_cpu}, Memory={target_memory_str}")
            return True
            
        except Exception as e:
            logger.error(f"Error scaling customer resources: {e}")
            return False
    
    async def _migrate_customer_tier(self, decision: ScalingDecision) -> bool:
        """Migrate customer to different tier"""
        try:
            # This would involve more complex operations in production:
            # 1. Update customer tier in database
            # 2. Recreate containers with new resource limits
            # 3. Update billing information
            # 4. Notify customer of tier change
            
            logger.info(f"Would migrate customer {decision.customer_id} from {decision.current_allocation['tier']} to {decision.target_allocation['tier']}")
            
            # For now, just log the migration
            async with self.postgres_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE customer_infrastructure 
                    SET tier = $1, updated_at = NOW()
                    WHERE customer_id = $2
                """, decision.target_allocation["tier"], decision.customer_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Error migrating customer tier: {e}")
            return False
    
    async def _log_scaling_action(self, decision: ScalingDecision):
        """Log successful scaling action"""
        try:
            async with self.postgres_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO scaling_actions (
                        customer_id, action, resource_type, justification,
                        cost_impact, confidence_score, executed_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                    decision.customer_id, decision.action.value, decision.resource_type.value,
                    decision.justification, decision.cost_impact_daily, decision.confidence_score,
                    datetime.utcnow()
                )
        except Exception as e:
            logger.error(f"Error logging scaling action: {e}")
    
    async def _get_last_scaling_time(self, customer_id: str) -> Optional[datetime]:
        """Get timestamp of last scaling action for customer"""
        try:
            async with self.postgres_pool.acquire() as conn:
                result = await conn.fetchval("""
                    SELECT MAX(executed_at) FROM scaling_actions 
                    WHERE customer_id = $1
                """, customer_id)
                return result
        except Exception:
            return None
    
    async def _get_daily_scaling_count(self, customer_id: str, action: ScalingAction) -> int:
        """Get number of scaling actions for customer today"""
        try:
            async with self.postgres_pool.acquire() as conn:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM scaling_actions
                    WHERE customer_id = $1 
                    AND action = $2
                    AND executed_at > CURRENT_DATE
                """, customer_id, action.value)
                return count or 0
        except Exception:
            return 0
    
    async def _get_current_daily_cost(self, customer_id: str) -> float:
        """Get current estimated daily cost for customer"""
        try:
            pattern = self.customer_patterns.get(customer_id)
            if pattern:
                return pattern.cost_efficiency_score * 10.0  # Rough estimation
        except Exception:
            pass
        return 5.0  # Default daily cost
    
    async def _analyze_tier_migrations(self):
        """Analyze and suggest tier migrations"""
        while self.scaling_active:
            try:
                # This task runs less frequently to analyze tier migration opportunities
                logger.info("🎯 Analyzing tier migration opportunities...")
                
                migration_candidates = []
                for customer_id, pattern in self.customer_patterns.items():
                    if pattern.cost_efficiency_score < 0.6:  # Low efficiency
                        migration_candidates.append(pattern)
                
                logger.info(f"Found {len(migration_candidates)} tier migration candidates")
                
            except Exception as e:
                logger.error(f"Error analyzing tier migrations: {e}")
            
            await asyncio.sleep(3600)  # Analyze hourly
    
    async def _predictive_scaling(self):
        """Implement predictive scaling based on patterns"""
        while self.scaling_active:
            try:
                # Predictive scaling for anticipated load
                logger.info("🔮 Running predictive scaling analysis...")
                
                for customer_id, pattern in self.customer_patterns.items():
                    if pattern.seasonal_patterns:
                        predicted_load = await self._predict_future_load(pattern)
                        if predicted_load > 80:  # Predicted high load
                            # Create preemptive scaling decision
                            logger.info(f"Predictive scaling recommended for {customer_id}: {predicted_load}% predicted load")
                
            except Exception as e:
                logger.error(f"Error in predictive scaling: {e}")
            
            await asyncio.sleep(1800)  # Run every 30 minutes
    
    async def _predict_future_load(self, pattern: CustomerUsagePattern) -> float:
        """Predict future load based on seasonal patterns"""
        current_hour = datetime.utcnow().hour
        
        # Find matching seasonal pattern
        for seasonal in pattern.seasonal_patterns:
            if seasonal["hour"] == current_hour:
                return seasonal["avg_cpu_usage"]
        
        return pattern.avg_cpu_usage  # Fallback to average
    
    async def _cost_optimization_cleanup(self):
        """Perform cost optimization cleanup tasks"""
        while self.scaling_active:
            try:
                # Weekend resource optimization
                if datetime.utcnow().weekday() >= 5 and self.config["cost_optimization"]["optimize_on_weekends"]:
                    logger.info("💰 Running weekend cost optimization...")
                    
                    for customer_id, pattern in self.customer_patterns.items():
                        if pattern.cost_efficiency_score < 0.5:
                            # Suggest temporary scale-down for weekend
                            logger.info(f"Weekend optimization opportunity for {customer_id}")
                
            except Exception as e:
                logger.error(f"Error in cost optimization cleanup: {e}")
            
            await asyncio.sleep(7200)  # Run every 2 hours
    
    async def get_scaling_metrics(self) -> Dict[str, Any]:
        """Get auto-scaling metrics and statistics"""
        return {
            "customers_monitored": len(self.customer_patterns),
            "pending_decisions": len(self.scaling_decisions),
            "active_scaling_locks": len(self.scaling_locks),
            "avg_cost_efficiency": sum(p.cost_efficiency_score for p in self.customer_patterns.values()) / len(self.customer_patterns) if self.customer_patterns else 0,
            "customers_by_trend": {
                trend: len([p for p in self.customer_patterns.values() if p.usage_trend == trend])
                for trend in ["increasing", "decreasing", "stable"]
            },
            "tier_distribution": {
                tier: len([p for p in self.customer_patterns.values() if p.tier == tier])
                for tier in ["starter", "professional", "enterprise"]
            }
        }
    
    async def stop_auto_scaling(self):
        """Stop auto-scaling and cleanup"""
        self.scaling_active = False
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        logger.info("Auto-scaling manager stopped")


# Example usage
async def main():
    """Example usage of Auto-Scaling Manager"""
    scaling_manager = AutoScalingManager()
    
    try:
        # Start auto-scaling (this would run continuously in production)
        await asyncio.wait_for(scaling_manager.start_auto_scaling(), timeout=30)
    except asyncio.TimeoutError:
        # Get sample metrics
        metrics = await scaling_manager.get_scaling_metrics()
        print(f"Scaling metrics: {metrics}")
        
        await scaling_manager.stop_auto_scaling()


if __name__ == "__main__":
    asyncio.run(main())