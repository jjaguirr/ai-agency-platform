"""
Memory Infrastructure Monitor Service

HTTP service that monitors Mem0 infrastructure performance, SLA compliance,
and customer memory isolation across Qdrant, Neo4j, Redis, and PostgreSQL.

Provides:
- Real-time performance monitoring
- SLA violation alerting
- Customer isolation validation
- Prometheus metrics export
- Health checks for all memory components
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import structlog

from performance_monitor import GlobalPerformanceMonitor, global_monitor
from isolation_validator import MemoryIsolationValidator
from mem0_manager import EAMemoryManager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# FastAPI app
app = FastAPI(
    title="Memory Infrastructure Monitor",
    description="Monitors Mem0 infrastructure performance and SLA compliance",
    version="1.0.0"
)

# Configuration from environment
CONFIG = {
    "postgres_url": os.getenv("POSTGRES_URL", "postgresql://mcphub:mcphub_password@localhost:5432/mcphub"),
    "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
    "qdrant_url": os.getenv("QDRANT_URL", "http://localhost:6333"),
    "neo4j_url": os.getenv("NEO4J_URL", "neo4j://localhost:7687"),
    "neo4j_user": os.getenv("NEO4J_USER", "neo4j"),
    "neo4j_password": os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    "monitoring_interval": int(os.getenv("MONITORING_INTERVAL", "30")),
    "sla_enforcement": os.getenv("SLA_ENFORCEMENT", "true").lower() == "true",
    "log_level": os.getenv("LOG_LEVEL", "INFO")
}

# Global state
monitoring_active = False
health_status = {
    "postgres": False,
    "redis": False, 
    "qdrant": False,
    "neo4j": False,
    "overall": False
}


class HealthCheckResponse(BaseModel):
    """Health check response model"""
    status: str
    timestamp: str
    services: Dict[str, bool]
    monitoring_active: bool


class PerformanceReportRequest(BaseModel):
    """Performance report request model"""
    customer_id: Optional[str] = None
    time_window_hours: int = 24


class IsolationTestRequest(BaseModel):
    """Isolation test request model"""
    customer_a_id: str
    customer_b_id: str


@app.on_event("startup")
async def startup_event():
    """Initialize monitoring service"""
    logger.info("Starting Memory Infrastructure Monitor")
    
    # Start background monitoring
    asyncio.create_task(continuous_health_monitoring())
    
    if CONFIG["sla_enforcement"]:
        logger.info("SLA enforcement enabled - starting performance monitoring")
        asyncio.create_task(continuous_performance_monitoring())


@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup on shutdown"""
    global monitoring_active
    monitoring_active = False
    logger.info("Memory Infrastructure Monitor shutting down")


@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    return HealthCheckResponse(
        status="healthy" if health_status["overall"] else "unhealthy",
        timestamp=datetime.utcnow().isoformat(),
        services=health_status.copy(),
        monitoring_active=monitoring_active
    )


@app.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with component diagnostics"""
    detailed_status = {}
    
    # Check PostgreSQL
    try:
        import asyncpg
        conn = await asyncpg.connect(CONFIG["postgres_url"])
        await conn.execute("SELECT 1")
        await conn.close()
        detailed_status["postgres"] = {"status": "healthy", "latency_ms": 0}  # Would measure actual latency
    except Exception as e:
        detailed_status["postgres"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Redis
    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(CONFIG["redis_url"])
        await redis_client.ping()
        await redis_client.aclose()
        detailed_status["redis"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        detailed_status["redis"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Qdrant
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{CONFIG['qdrant_url']}/health")
            response.raise_for_status()
        detailed_status["qdrant"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        detailed_status["qdrant"] = {"status": "unhealthy", "error": str(e)}
    
    # Check Neo4j
    try:
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            CONFIG["neo4j_url"], 
            auth=(CONFIG["neo4j_user"], CONFIG["neo4j_password"])
        )
        async with driver.session() as session:
            await session.run("RETURN 1")
        await driver.close()
        detailed_status["neo4j"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        detailed_status["neo4j"] = {"status": "unhealthy", "error": str(e)}
    
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "overall_healthy": all(s.get("status") == "healthy" for s in detailed_status.values()),
        "services": detailed_status
    }


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    try:
        # Get system performance report
        system_report = await global_monitor.generate_system_performance_report()
        
        # Generate Prometheus metrics
        metrics_lines = [
            "# HELP memory_system_customers_total Total number of customers with memory monitoring",
            "# TYPE memory_system_customers_total counter",
            f"memory_system_customers_total {system_report['system_statistics']['total_customers']}",
            "",
            "# HELP memory_system_operations_total Total number of memory operations",
            "# TYPE memory_system_operations_total counter", 
            f"memory_system_operations_total {system_report['system_statistics']['total_operations']}",
            "",
            "# HELP memory_system_sla_compliance_percent System-wide SLA compliance percentage",
            "# TYPE memory_system_sla_compliance_percent gauge",
            f"memory_system_sla_compliance_percent {system_report['system_statistics']['system_sla_compliance']}",
        ]
        
        # Add per-customer metrics
        for customer_id, customer_monitor in global_monitor.customer_monitors.items():
            customer_metrics = customer_monitor.export_metrics_prometheus()
            if customer_metrics:
                metrics_lines.extend(["", f"# Customer {customer_id} metrics", customer_metrics])
        
        return PlainTextResponse("\n".join(metrics_lines))
        
    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return PlainTextResponse("# Error generating metrics")


@app.post("/performance/report")
async def generate_performance_report(request: PerformanceReportRequest):
    """Generate performance report for customer or system-wide"""
    try:
        if request.customer_id:
            # Customer-specific report
            customer_monitor = global_monitor.get_customer_monitor(request.customer_id)
            report = await customer_monitor.generate_performance_report(
                time_window_hours=request.time_window_hours
            )
        else:
            # System-wide report
            report = await global_monitor.generate_system_performance_report()
        
        return report
        
    except Exception as e:
        logger.error(f"Failed to generate performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/isolation/test")
async def test_customer_isolation(request: IsolationTestRequest, background_tasks: BackgroundTasks):
    """Test memory isolation between two customers"""
    try:
        logger.info(f"Starting isolation test between customers {request.customer_a_id} and {request.customer_b_id}")
        
        # Run isolation validation
        validation_result = await MemoryIsolationValidator.validate_customer_isolation(
            request.customer_a_id, 
            request.customer_b_id
        )
        
        if not validation_result.get("isolation_verified", False):
            logger.critical(f"ISOLATION VIOLATION detected: {validation_result}")
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Isolation test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/isolation/test/multiple")
async def test_multiple_customer_isolation(customer_ids: List[str]):
    """Test memory isolation across multiple customers"""
    try:
        if len(customer_ids) < 2:
            raise HTTPException(status_code=400, detail="At least 2 customer IDs required")
        
        logger.info(f"Starting multi-customer isolation test for {len(customer_ids)} customers")
        
        validation_result = await MemoryIsolationValidator.validate_multiple_customers(
            customer_ids=customer_ids,
            max_concurrent=5
        )
        
        return validation_result
        
    except Exception as e:
        logger.error(f"Multi-customer isolation test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/customers/{customer_id}/performance")
async def get_customer_performance(customer_id: str):
    """Get real-time performance metrics for specific customer"""
    try:
        customer_monitor = global_monitor.get_customer_monitor(customer_id)
        snapshot = customer_monitor.get_current_performance_snapshot()
        
        return snapshot
        
    except Exception as e:
        logger.error(f"Failed to get customer performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/customers/{customer_id}/memory/test")
async def test_customer_memory(customer_id: str):
    """Test customer memory operations and performance"""
    try:
        # Initialize customer memory manager
        memory_manager = EAMemoryManager(customer_id)
        
        # Perform test operations
        test_context = {
            "business_description": f"Test business for customer {customer_id}",
            "test_timestamp": datetime.utcnow().isoformat()
        }
        
        # Store test data
        start_time = time.time()
        memory_id = await memory_manager.store_business_context(
            context=test_context,
            session_id=f"test_session_{int(time.time())}"
        )
        storage_time = time.time() - start_time
        
        # Retrieve test data
        start_time = time.time()
        results = await memory_manager.retrieve_business_context(
            query="Test business",
            limit=5
        )
        retrieval_time = time.time() - start_time
        
        # Cleanup
        await memory_manager.cleanup_test_data()
        await memory_manager.close()
        
        # Track performance
        customer_monitor = global_monitor.get_customer_monitor(customer_id)
        await customer_monitor.track_memory_operation(
            operation="memory_storage",
            latency=storage_time,
            success=memory_id is not None
        )
        await customer_monitor.track_memory_operation(
            operation="mem0_search", 
            latency=retrieval_time,
            success=len(results) > 0
        )
        
        return {
            "customer_id": customer_id,
            "test_timestamp": datetime.utcnow().isoformat(),
            "storage_latency_seconds": storage_time,
            "retrieval_latency_seconds": retrieval_time,
            "memory_id": memory_id,
            "results_count": len(results),
            "sla_compliant": {
                "storage": storage_time < 0.3,  # 300ms target
                "retrieval": retrieval_time < 0.5  # 500ms SLA
            }
        }
        
    except Exception as e:
        logger.error(f"Customer memory test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def continuous_health_monitoring():
    """Background task for continuous health monitoring"""
    global monitoring_active, health_status
    monitoring_active = True
    
    logger.info("Starting continuous health monitoring")
    
    while monitoring_active:
        try:
            # Check all services
            health_results = await check_all_services_health()
            health_status.update(health_results)
            health_status["overall"] = all(health_results.values())
            
            if not health_status["overall"]:
                logger.warning(f"Health check failed: {health_status}")
            
            await asyncio.sleep(CONFIG["monitoring_interval"])
            
        except Exception as e:
            logger.error(f"Health monitoring error: {e}")
            await asyncio.sleep(10)  # Short delay on error


async def continuous_performance_monitoring():
    """Background task for continuous performance monitoring"""
    logger.info("Starting continuous performance monitoring with SLA enforcement")
    
    while monitoring_active:
        try:
            # Generate system performance report
            system_report = await global_monitor.generate_system_performance_report()
            
            # Check for system-wide performance issues
            system_sla_compliance = system_report["system_statistics"]["system_sla_compliance"]
            
            if system_sla_compliance < 95.0:
                logger.warning(
                    f"System SLA compliance degraded: {system_sla_compliance:.1f}% "
                    f"(target: 95.0%)"
                )
            
            # Log performance summary
            logger.info(
                f"Performance monitoring: {system_report['system_statistics']['total_customers']} customers, "
                f"{system_report['system_statistics']['total_operations']} operations, "
                f"{system_sla_compliance:.1f}% SLA compliance"
            )
            
            await asyncio.sleep(CONFIG["monitoring_interval"] * 2)  # Less frequent than health checks
            
        except Exception as e:
            logger.error(f"Performance monitoring error: {e}")
            await asyncio.sleep(60)


async def check_all_services_health() -> Dict[str, bool]:
    """Check health of all memory infrastructure services"""
    health_results = {}
    
    # PostgreSQL health check
    try:
        import asyncpg
        conn = await asyncpg.connect(CONFIG["postgres_url"])
        await conn.execute("SELECT 1")
        await conn.close()
        health_results["postgres"] = True
    except Exception as e:
        logger.warning(f"PostgreSQL health check failed: {e}")
        health_results["postgres"] = False
    
    # Redis health check
    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(CONFIG["redis_url"])
        await redis_client.ping()
        await redis_client.aclose()
        health_results["redis"] = True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        health_results["redis"] = False
    
    # Qdrant health check
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{CONFIG['qdrant_url']}/health")
            response.raise_for_status()
        health_results["qdrant"] = True
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        health_results["qdrant"] = False
    
    # Neo4j health check
    try:
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            CONFIG["neo4j_url"],
            auth=(CONFIG["neo4j_user"], CONFIG["neo4j_password"])
        )
        async with driver.session() as session:
            await session.run("RETURN 1")
        await driver.close()
        health_results["neo4j"] = True
    except Exception as e:
        logger.warning(f"Neo4j health check failed: {e}")
        health_results["neo4j"] = False
    
    return health_results


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=getattr(logging, CONFIG["log_level"]))
    
    # Run the service
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8080,
        log_config=None  # Use structlog configuration
    )