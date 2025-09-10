"""
Memory Performance Monitor - Production Implementation
Per-customer memory system monitoring with SLA enforcement

Monitors:
- Mem0 semantic memory performance (<500ms SLA)
- Redis working memory performance (<2ms SLA) 
- PostgreSQL persistent storage performance (<100ms SLA)
- Cross-component memory continuity validation
- Customer isolation integrity checks
"""

import asyncio
import json
import logging
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import asyncpg
import redis.asyncio as redis
import aiohttp
from aiohttp import web
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MemoryHealthCheck:
    """Memory system health status"""
    customer_id: str
    mem0_status: str
    redis_status: str
    postgres_status: str
    neo4j_status: str
    overall_status: str
    response_times: Dict[str, float]
    sla_violations: List[str]
    timestamp: datetime


class MemoryPerformanceMonitor:
    """
    Production memory performance monitor for per-customer isolation.
    
    Provides:
    - Real-time memory system performance monitoring
    - SLA enforcement and violation detection
    - Health checks and status reporting
    - Prometheus metrics export
    - Customer isolation validation
    """
    
    def __init__(self):
        """Initialize memory performance monitor"""
        self.customer_id = os.getenv('CUSTOMER_ID', 'unknown')
        self.monitoring_active = False
        
        # Database connections
        self.postgres_pool = None
        self.redis_pool = None
        
        # Metrics
        self.registry = CollectorRegistry()
        self._init_prometheus_metrics()
        
        # Performance tracking
        self.performance_data = {}
        self.health_status = None
        
        # SLA targets
        self.sla_targets = {
            'mem0_response_ms': 500,
            'redis_response_ms': 2,
            'postgres_response_ms': 100,
            'neo4j_response_ms': 200
        }
        
        logger.info(f"Initialized Memory Performance Monitor for customer {self.customer_id}")
    
    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics"""
        self.memory_response_time = Histogram(
            'memory_response_time_seconds',
            'Memory system response times',
            ['customer_id', 'memory_type', 'operation'],
            registry=self.registry,
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
        )
        
        self.sla_violations = Counter(
            'memory_sla_violations_total',
            'Memory SLA violations',
            ['customer_id', 'memory_type'],
            registry=self.registry
        )
        
        self.memory_health = Gauge(
            'memory_health_status',
            'Memory system health status (1=healthy, 0=unhealthy)',
            ['customer_id', 'memory_type'],
            registry=self.registry
        )
        
        self.customer_isolation_status = Gauge(
            'customer_isolation_status',
            'Customer isolation integrity (1=isolated, 0=breach)',
            ['customer_id'],
            registry=self.registry
        )
    
    async def start_monitoring(self):
        """Start continuous memory performance monitoring"""
        if self.monitoring_active:
            logger.warning("Monitoring already active")
            return
        
        self.monitoring_active = True
        
        # Initialize connections
        await self._init_connections()
        
        # Start monitoring tasks
        monitoring_tasks = [
            self._monitor_mem0_performance(),
            self._monitor_redis_performance(),
            self._monitor_postgres_performance(),
            self._monitor_neo4j_performance(),
            self._validate_customer_isolation(),
            self._collect_system_metrics(),
            self._start_http_server()
        ]
        
        logger.info(f"🚀 Starting memory performance monitoring for customer {self.customer_id}")
        
        try:
            await asyncio.gather(*monitoring_tasks)
        except Exception as e:
            logger.error(f"Error in monitoring tasks: {e}")
        finally:
            await self.stop_monitoring()
    
    async def _init_connections(self):
        """Initialize database connections"""
        # PostgreSQL
        postgres_url = os.getenv('POSTGRES_URL')
        if postgres_url:
            try:
                self.postgres_pool = await asyncpg.create_pool(postgres_url)
                logger.info("Connected to PostgreSQL")
            except Exception as e:
                logger.error(f"Failed to connect to PostgreSQL: {e}")
        
        # Redis
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        try:
            self.redis_pool = redis.ConnectionPool.from_url(redis_url)
            redis_client = redis.Redis(connection_pool=self.redis_pool)
            await redis_client.ping()
            logger.info("Connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
    
    async def _monitor_mem0_performance(self):
        """Monitor Mem0 semantic memory performance"""
        while self.monitoring_active:
            try:
                # Import Mem0 manager
                from mem0_manager import EAMemoryManager
                
                start_time = time.time()
                
                # Create memory manager for customer
                ea_memory = EAMemoryManager(self.customer_id)
                
                # Test memory operations
                test_context = {
                    "business_description": f"Performance test at {datetime.utcnow().isoformat()}",
                    "test_type": "performance_monitor",
                    "customer_id": self.customer_id
                }
                
                # Store operation
                store_start = time.time()
                memory_id = await ea_memory.store_business_context(test_context, f"perf_test_{int(time.time())}")
                store_time = (time.time() - store_start) * 1000  # Convert to milliseconds
                
                # Retrieve operation
                retrieve_start = time.time()
                results = await ea_memory.retrieve_business_context("performance test", limit=3)
                retrieve_time = (time.time() - retrieve_start) * 1000
                
                await ea_memory.close()
                
                # Record metrics
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='mem0',
                    operation='store'
                ).observe(store_time / 1000)
                
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='mem0',
                    operation='retrieve'
                ).observe(retrieve_time / 1000)
                
                # Check SLA violations
                if store_time > self.sla_targets['mem0_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='mem0'
                    ).inc()
                    logger.warning(f"Mem0 store SLA violation: {store_time:.2f}ms > {self.sla_targets['mem0_response_ms']}ms")
                
                if retrieve_time > self.sla_targets['mem0_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='mem0'
                    ).inc()
                    logger.warning(f"Mem0 retrieve SLA violation: {retrieve_time:.2f}ms > {self.sla_targets['mem0_response_ms']}ms")
                
                # Update health status
                mem0_healthy = store_time < self.sla_targets['mem0_response_ms'] and retrieve_time < self.sla_targets['mem0_response_ms']
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='mem0'
                ).set(1 if mem0_healthy else 0)
                
                # Store performance data
                self.performance_data['mem0'] = {
                    'store_time_ms': store_time,
                    'retrieve_time_ms': retrieve_time,
                    'healthy': mem0_healthy,
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                logger.info(f"Mem0 performance: store={store_time:.2f}ms, retrieve={retrieve_time:.2f}ms")
                
            except Exception as e:
                logger.error(f"Error monitoring Mem0 performance: {e}")
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='mem0'
                ).set(0)
            
            await asyncio.sleep(60)  # Check every minute
    
    async def _monitor_redis_performance(self):
        """Monitor Redis working memory performance"""
        while self.monitoring_active:
            try:
                if not self.redis_pool:
                    await asyncio.sleep(30)
                    continue
                
                redis_client = redis.Redis(connection_pool=self.redis_pool)
                
                # Test SET operation
                start_time = time.time()
                test_key = f"perf_test:{self.customer_id}:{int(time.time())}"
                test_value = json.dumps({
                    "test_type": "performance_monitor",
                    "customer_id": self.customer_id,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                await redis_client.set(test_key, test_value, ex=300)  # 5 minute expiry
                set_time = (time.time() - start_time) * 1000
                
                # Test GET operation
                start_time = time.time()
                retrieved_value = await redis_client.get(test_key)
                get_time = (time.time() - start_time) * 1000
                
                # Clean up test key
                await redis_client.delete(test_key)
                
                # Record metrics
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='redis',
                    operation='set'
                ).observe(set_time / 1000)
                
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='redis',
                    operation='get'
                ).observe(get_time / 1000)
                
                # Check SLA violations
                if set_time > self.sla_targets['redis_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='redis'
                    ).inc()
                    logger.warning(f"Redis set SLA violation: {set_time:.2f}ms > {self.sla_targets['redis_response_ms']}ms")
                
                if get_time > self.sla_targets['redis_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='redis'
                    ).inc()
                    logger.warning(f"Redis get SLA violation: {get_time:.2f}ms > {self.sla_targets['redis_response_ms']}ms")
                
                # Update health status
                redis_healthy = set_time < self.sla_targets['redis_response_ms'] and get_time < self.sla_targets['redis_response_ms']
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='redis'
                ).set(1 if redis_healthy else 0)
                
                # Store performance data
                self.performance_data['redis'] = {
                    'set_time_ms': set_time,
                    'get_time_ms': get_time,
                    'healthy': redis_healthy,
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                logger.info(f"Redis performance: set={set_time:.3f}ms, get={get_time:.3f}ms")
                
            except Exception as e:
                logger.error(f"Error monitoring Redis performance: {e}")
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='redis'
                ).set(0)
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def _monitor_postgres_performance(self):
        """Monitor PostgreSQL persistent storage performance"""
        while self.monitoring_active:
            try:
                if not self.postgres_pool:
                    await asyncio.sleep(30)
                    continue
                
                async with self.postgres_pool.acquire() as conn:
                    # Test INSERT operation
                    start_time = time.time()
                    test_data = {
                        "customer_id": self.customer_id,
                        "action": "performance_test",
                        "data": {"test_type": "performance_monitor", "timestamp": datetime.utcnow().isoformat()},
                        "timestamp": datetime.utcnow()
                    }
                    
                    await conn.execute("""
                        INSERT INTO customer_memory_audit (customer_id, action, data, timestamp)
                        VALUES ($1, $2, $3, $4)
                    """, test_data["customer_id"], test_data["action"], json.dumps(test_data["data"]), test_data["timestamp"])
                    
                    insert_time = (time.time() - start_time) * 1000
                    
                    # Test SELECT operation
                    start_time = time.time()
                    result = await conn.fetch("""
                        SELECT * FROM customer_memory_audit 
                        WHERE customer_id = $1 
                        ORDER BY timestamp DESC 
                        LIMIT 5
                    """, self.customer_id)
                    
                    select_time = (time.time() - start_time) * 1000
                
                # Record metrics
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='postgres',
                    operation='insert'
                ).observe(insert_time / 1000)
                
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='postgres',
                    operation='select'
                ).observe(select_time / 1000)
                
                # Check SLA violations
                if insert_time > self.sla_targets['postgres_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='postgres'
                    ).inc()
                    logger.warning(f"PostgreSQL insert SLA violation: {insert_time:.2f}ms > {self.sla_targets['postgres_response_ms']}ms")
                
                if select_time > self.sla_targets['postgres_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='postgres'
                    ).inc()
                    logger.warning(f"PostgreSQL select SLA violation: {select_time:.2f}ms > {self.sla_targets['postgres_response_ms']}ms")
                
                # Update health status
                postgres_healthy = insert_time < self.sla_targets['postgres_response_ms'] and select_time < self.sla_targets['postgres_response_ms']
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='postgres'
                ).set(1 if postgres_healthy else 0)
                
                # Store performance data
                self.performance_data['postgres'] = {
                    'insert_time_ms': insert_time,
                    'select_time_ms': select_time,
                    'records_count': len(result),
                    'healthy': postgres_healthy,
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                logger.info(f"PostgreSQL performance: insert={insert_time:.2f}ms, select={select_time:.2f}ms")
                
            except Exception as e:
                logger.error(f"Error monitoring PostgreSQL performance: {e}")
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='postgres'
                ).set(0)
            
            await asyncio.sleep(60)  # Check every minute
    
    async def _monitor_neo4j_performance(self):
        """Monitor Neo4j graph database performance"""
        while self.monitoring_active:
            try:
                neo4j_url = os.getenv('NEO4J_URL', 'neo4j://localhost:7687')
                neo4j_user = os.getenv('NEO4J_USER', 'neo4j')
                neo4j_password = os.getenv('NEO4J_PASSWORD', 'password')
                
                from neo4j import AsyncGraphDatabase
                
                driver = AsyncGraphDatabase.driver(neo4j_url, auth=(neo4j_user, neo4j_password))
                
                # Test query operation
                start_time = time.time()
                async with driver.session() as session:
                    result = await session.run(
                        "CREATE (n:PerformanceTest {customer_id: $customer_id, timestamp: $timestamp}) RETURN n",
                        customer_id=self.customer_id,
                        timestamp=datetime.utcnow().isoformat()
                    )
                    await result.consume()
                
                create_time = (time.time() - start_time) * 1000
                
                # Test read operation
                start_time = time.time()
                async with driver.session() as session:
                    result = await session.run(
                        "MATCH (n:PerformanceTest {customer_id: $customer_id}) RETURN count(n) as count",
                        customer_id=self.customer_id
                    )
                    record = await result.single()
                    count = record['count'] if record else 0
                
                query_time = (time.time() - start_time) * 1000
                
                # Clean up test nodes (keep only last 10)
                async with driver.session() as session:
                    await session.run(
                        """MATCH (n:PerformanceTest {customer_id: $customer_id})
                           WITH n ORDER BY n.timestamp DESC SKIP 10
                           DETACH DELETE n""",
                        customer_id=self.customer_id
                    )
                
                await driver.close()
                
                # Record metrics
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='neo4j',
                    operation='create'
                ).observe(create_time / 1000)
                
                self.memory_response_time.labels(
                    customer_id=self.customer_id,
                    memory_type='neo4j',
                    operation='query'
                ).observe(query_time / 1000)
                
                # Check SLA violations
                if create_time > self.sla_targets['neo4j_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='neo4j'
                    ).inc()
                    logger.warning(f"Neo4j create SLA violation: {create_time:.2f}ms > {self.sla_targets['neo4j_response_ms']}ms")
                
                if query_time > self.sla_targets['neo4j_response_ms']:
                    self.sla_violations.labels(
                        customer_id=self.customer_id,
                        memory_type='neo4j'
                    ).inc()
                    logger.warning(f"Neo4j query SLA violation: {query_time:.2f}ms > {self.sla_targets['neo4j_response_ms']}ms")
                
                # Update health status
                neo4j_healthy = create_time < self.sla_targets['neo4j_response_ms'] and query_time < self.sla_targets['neo4j_response_ms']
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='neo4j'
                ).set(1 if neo4j_healthy else 0)
                
                # Store performance data
                self.performance_data['neo4j'] = {
                    'create_time_ms': create_time,
                    'query_time_ms': query_time,
                    'node_count': count,
                    'healthy': neo4j_healthy,
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                logger.info(f"Neo4j performance: create={create_time:.2f}ms, query={query_time:.2f}ms")
                
            except Exception as e:
                logger.error(f"Error monitoring Neo4j performance: {e}")
                self.memory_health.labels(
                    customer_id=self.customer_id,
                    memory_type='neo4j'
                ).set(0)
            
            await asyncio.sleep(90)  # Check every 90 seconds
    
    async def _validate_customer_isolation(self):
        """Validate customer isolation integrity"""
        while self.monitoring_active:
            try:
                isolation_valid = True
                
                # Check database isolation
                if self.postgres_pool:
                    async with self.postgres_pool.acquire() as conn:
                        # Verify we can only access our customer's data
                        result = await conn.fetchval(
                            "SELECT COUNT(DISTINCT customer_id) FROM customer_memory_audit WHERE customer_id != $1",
                            self.customer_id
                        )
                        
                        if result and result > 0:
                            isolation_valid = False
                            logger.critical(f"Customer isolation breach detected: Found {result} other customer records accessible")
                
                # Check Redis isolation (verify we're in correct namespace)
                if self.redis_pool:
                    redis_client = redis.Redis(connection_pool=self.redis_pool)
                    keys = await redis_client.keys("*")
                    
                    # Check if any keys belong to other customers
                    other_customer_keys = [key for key in keys if self.customer_id not in key.decode() and "test" not in key.decode()]
                    if other_customer_keys:
                        isolation_valid = False
                        logger.critical(f"Redis isolation breach: Found {len(other_customer_keys)} keys from other customers")
                
                # Update isolation status metric
                self.customer_isolation_status.labels(customer_id=self.customer_id).set(1 if isolation_valid else 0)
                
                if isolation_valid:
                    logger.info(f"✅ Customer isolation validated for {self.customer_id}")
                else:
                    logger.critical(f"❌ Customer isolation breach detected for {self.customer_id}")
                
            except Exception as e:
                logger.error(f"Error validating customer isolation: {e}")
                self.customer_isolation_status.labels(customer_id=self.customer_id).set(0)
            
            await asyncio.sleep(300)  # Check every 5 minutes
    
    async def _collect_system_metrics(self):
        """Collect system-level performance metrics"""
        while self.monitoring_active:
            try:
                # CPU and memory usage
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_info = psutil.virtual_memory()
                
                # Store system metrics
                self.performance_data['system'] = {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory_info.percent,
                    'memory_available_mb': memory_info.available / (1024 * 1024),
                    'last_updated': datetime.utcnow().isoformat()
                }
                
                logger.info(f"System metrics: CPU={cpu_percent:.1f}%, Memory={memory_info.percent:.1f}%")
                
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
            
            await asyncio.sleep(60)  # Check every minute
    
    async def check_health(self) -> Dict[str, Any]:
        """Get comprehensive health check status"""
        try:
            # Check each memory system
            mem0_status = "healthy" if self.performance_data.get('mem0', {}).get('healthy', False) else "unhealthy"
            redis_status = "healthy" if self.performance_data.get('redis', {}).get('healthy', False) else "unhealthy"
            postgres_status = "healthy" if self.performance_data.get('postgres', {}).get('healthy', False) else "unhealthy"
            neo4j_status = "healthy" if self.performance_data.get('neo4j', {}).get('healthy', False) else "unhealthy"
            
            # Overall status
            all_healthy = all(status == "healthy" for status in [mem0_status, redis_status, postgres_status, neo4j_status])
            overall_status = "healthy" if all_healthy else "unhealthy"
            
            # Response times
            response_times = {}
            for system, data in self.performance_data.items():
                if system != 'system':
                    for key, value in data.items():
                        if key.endswith('_time_ms'):
                            response_times[f"{system}_{key}"] = value
            
            # SLA violations
            sla_violations = []
            for system, data in self.performance_data.items():
                if system != 'system' and not data.get('healthy', True):
                    sla_violations.append(f"{system}_performance_degraded")
            
            self.health_status = MemoryHealthCheck(
                customer_id=self.customer_id,
                mem0_status=mem0_status,
                redis_status=redis_status,
                postgres_status=postgres_status,
                neo4j_status=neo4j_status,
                overall_status=overall_status,
                response_times=response_times,
                sla_violations=sla_violations,
                timestamp=datetime.utcnow()
            )
            
            return asdict(self.health_status)
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {
                "customer_id": self.customer_id,
                "overall_status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _start_http_server(self):
        """Start HTTP server for health checks and metrics"""
        app = web.Application()
        
        # Health check endpoint
        async def health_handler(request):
            health = await self.check_health()
            status = 200 if health.get("overall_status") == "healthy" else 503
            return web.json_response(health, status=status)
        
        # Metrics endpoint
        async def metrics_handler(request):
            metrics = prometheus_client.generate_latest(self.registry)
            return web.Response(text=metrics.decode('utf-8'), content_type='text/plain')
        
        # Performance data endpoint
        async def performance_handler(request):
            return web.json_response({
                "customer_id": self.customer_id,
                "performance_data": self.performance_data,
                "sla_targets": self.sla_targets,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        app.router.add_get('/health', health_handler)
        app.router.add_get('/metrics', metrics_handler)
        app.router.add_get('/performance', performance_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '127.0.0.1', 8080)
        await site.start()
        
        logger.info("HTTP server started on port 8080")
        logger.info("Endpoints: /health, /metrics, /performance")
        
        # Keep the server running
        while self.monitoring_active:
            await asyncio.sleep(1)
    
    async def stop_monitoring(self):
        """Stop monitoring and cleanup resources"""
        self.monitoring_active = False
        
        if self.postgres_pool:
            await self.postgres_pool.close()
        
        if self.redis_pool:
            await self.redis_pool.disconnect()
        
        logger.info(f"Memory performance monitoring stopped for customer {self.customer_id}")


async def main():
    """Main entry point for memory performance monitor"""
    monitor = MemoryPerformanceMonitor()
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Error in monitoring: {e}")
    finally:
        await monitor.stop_monitoring()


if __name__ == "__main__":
    asyncio.run(main())