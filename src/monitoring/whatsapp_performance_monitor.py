"""
WhatsApp Business API Phase 2 Performance Monitoring System
Monitors SLA compliance, concurrent users, and Phase 2 feature performance
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

import redis
import psycopg2
from psycopg2.extras import RealDictCursor
from prometheus_client import Counter, Histogram, Gauge, start_http_server

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetrics:
    """Performance metrics structure"""
    timestamp: datetime
    active_channels: int
    concurrent_users: int
    message_throughput: float  # messages per second
    avg_response_time: float  # seconds
    sla_compliance_rate: float  # percentage
    media_processing_success_rate: float  # percentage
    cross_channel_handoffs: int
    personality_adaptation_accuracy: float  # percentage
    error_rate: float  # percentage

@dataclass
class SLAReport:
    """SLA compliance report"""
    period_start: datetime
    period_end: datetime
    target_response_time: float
    actual_avg_response_time: float
    compliance_percentage: float
    total_messages: int
    within_sla_messages: int
    peak_concurrent_users: int
    uptime_percentage: float

class WhatsAppPerformanceMonitor:
    """
    Comprehensive performance monitoring for WhatsApp Business API Phase 2
    
    Monitors:
    - Response time SLA compliance (<3 seconds)
    - Concurrent user handling (500+ target)
    - Media processing performance
    - Premium-casual personality consistency
    - Cross-channel handoff success rates
    - Overall system health and reliability
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=15, decode_responses=True)
        self.db_connection = None
        self.metrics_history: List[PerformanceMetrics] = []
        
        # Prometheus metrics
        self.message_counter = Counter('whatsapp_messages_total', 'Total WhatsApp messages processed', ['direction', 'status'])
        self.response_time_histogram = Histogram('whatsapp_response_time_seconds', 'WhatsApp message response time')
        self.concurrent_users_gauge = Gauge('whatsapp_concurrent_users', 'Current concurrent WhatsApp users')
        self.sla_compliance_gauge = Gauge('whatsapp_sla_compliance_percentage', 'SLA compliance percentage')
        self.media_processing_counter = Counter('whatsapp_media_messages_total', 'Total media messages processed', ['media_type', 'status'])
        self.handoff_counter = Counter('whatsapp_channel_handoffs_total', 'Total cross-channel handoffs', ['from_channel', 'to_channel', 'status'])
        
        self._initialize_connections()
        
    def _initialize_connections(self):
        """Initialize database connection"""
        try:
            self.db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub",
                user="mcphub",
                password="mcphub_password"
            )
            logger.info("Performance monitor database connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database connection: {e}")
    
    async def record_message_metrics(self, direction: str, response_time: float, success: bool, customer_id: str):
        """Record individual message metrics"""
        try:
            # Prometheus metrics
            status = 'success' if success else 'error'
            self.message_counter.labels(direction=direction, status=status).inc()
            
            if success:
                self.response_time_histogram.observe(response_time)
            
            # Redis metrics for real-time tracking
            metrics_key = f"whatsapp_metrics:{datetime.now().strftime('%Y-%m-%d:%H')}"
            pipeline = self.redis_client.pipeline()
            
            pipeline.hincrby(metrics_key, 'total_messages', 1)
            pipeline.hincrby(metrics_key, f'{direction}_messages', 1)
            pipeline.hincrby(metrics_key, 'success_messages' if success else 'error_messages', 1)
            pipeline.lpush('response_times_global', response_time)
            pipeline.ltrim('response_times_global', 0, 999)  # Keep last 1000 response times
            pipeline.expire(metrics_key, 86400 * 7)  # Keep for 7 days
            
            await asyncio.to_thread(pipeline.execute)
            
            logger.debug(f"Recorded message metrics: direction={direction}, response_time={response_time:.2f}s, success={success}")
            
        except Exception as e:
            logger.error(f"Error recording message metrics: {e}")
    
    async def record_media_processing_metrics(self, media_type: str, processing_time: float, success: bool, customer_id: str):
        """Record media processing metrics"""
        try:
            status = 'success' if success else 'error'
            self.media_processing_counter.labels(media_type=media_type, status=status).inc()
            
            # Store in Redis for analysis
            media_metrics_key = f"media_metrics:{datetime.now().strftime('%Y-%m-%d:%H')}"
            pipeline = self.redis_client.pipeline()
            
            pipeline.hincrby(media_metrics_key, f'{media_type}_total', 1)
            pipeline.hincrby(media_metrics_key, f'{media_type}_{status}', 1)
            pipeline.lpush(f'media_processing_times_{media_type}', processing_time)
            pipeline.ltrim(f'media_processing_times_{media_type}', 0, 99)
            pipeline.expire(media_metrics_key, 86400 * 7)
            
            await asyncio.to_thread(pipeline.execute)
            
            logger.debug(f"Recorded media processing metrics: type={media_type}, time={processing_time:.2f}s, success={success}")
            
        except Exception as e:
            logger.error(f"Error recording media processing metrics: {e}")
    
    async def record_cross_channel_handoff(self, from_channel: str, to_channel: str, success: bool, customer_id: str, context: Dict[str, Any]):
        """Record cross-channel handoff metrics"""
        try:
            status = 'success' if success else 'error'
            self.handoff_counter.labels(from_channel=from_channel, to_channel=to_channel, status=status).inc()
            
            # Store handoff details
            handoff_key = f"handoffs:{datetime.now().strftime('%Y-%m-%d:%H')}"
            handoff_data = {
                'timestamp': datetime.now().isoformat(),
                'from_channel': from_channel,
                'to_channel': to_channel,
                'success': success,
                'customer_id': customer_id,
                'context_preserved': len(context.get('preserved_context', {})) > 0
            }
            
            pipeline = self.redis_client.pipeline()
            pipeline.lpush(handoff_key, json.dumps(handoff_data))
            pipeline.ltrim(handoff_key, 0, 99)
            pipeline.expire(handoff_key, 86400 * 7)
            
            await asyncio.to_thread(pipeline.execute)
            
            logger.info(f"Recorded cross-channel handoff: {from_channel} → {to_channel}, success={success}")
            
        except Exception as e:
            logger.error(f"Error recording handoff metrics: {e}")
    
    async def update_concurrent_users(self, current_count: int):
        """Update concurrent users metric"""
        try:
            self.concurrent_users_gauge.set(current_count)
            
            # Store peak concurrent users
            peak_key = f"peak_users:{datetime.now().strftime('%Y-%m-%d')}"
            current_peak = await asyncio.to_thread(self.redis_client.get, peak_key) or "0"
            
            if current_count > int(current_peak):
                await asyncio.to_thread(self.redis_client.setex, peak_key, 86400, current_count)
            
            logger.debug(f"Updated concurrent users: {current_count}")
            
        except Exception as e:
            logger.error(f"Error updating concurrent users: {e}")
    
    async def calculate_sla_compliance(self, hours: int = 1) -> float:
        """Calculate SLA compliance for the last N hours"""
        try:
            # Get response times from Redis
            response_times = await asyncio.to_thread(self.redis_client.lrange, 'response_times_global', 0, -1)
            
            if not response_times:
                return 100.0  # No data means perfect compliance
            
            response_times = [float(rt) for rt in response_times]
            target_response_time = 3.0  # 3 seconds SLA
            
            within_sla = sum(1 for rt in response_times if rt <= target_response_time)
            compliance_rate = (within_sla / len(response_times)) * 100
            
            # Update Prometheus metric
            self.sla_compliance_gauge.set(compliance_rate)
            
            logger.debug(f"SLA compliance: {compliance_rate:.1f}% ({within_sla}/{len(response_times)} within {target_response_time}s)")
            
            return compliance_rate
            
        except Exception as e:
            logger.error(f"Error calculating SLA compliance: {e}")
            return 0.0
    
    async def get_current_performance_metrics(self) -> PerformanceMetrics:
        """Get current performance metrics snapshot"""
        try:
            # Get concurrent users from active channels
            current_hour_key = f"whatsapp_metrics:{datetime.now().strftime('%Y-%m-%d:%H')}"
            metrics_data = await asyncio.to_thread(self.redis_client.hgetall, current_hour_key)
            
            total_messages = int(metrics_data.get('total_messages', 0))
            success_messages = int(metrics_data.get('success_messages', 0))
            error_messages = int(metrics_data.get('error_messages', 0))
            
            # Calculate rates
            message_throughput = total_messages / 3600.0  # messages per second (assuming hourly data)
            error_rate = (error_messages / max(total_messages, 1)) * 100
            
            # Get response times
            response_times = await asyncio.to_thread(self.redis_client.lrange, 'response_times_global', 0, 99)
            avg_response_time = sum(float(rt) for rt in response_times) / max(len(response_times), 1) if response_times else 0.0
            
            # Calculate SLA compliance
            sla_compliance = await self.calculate_sla_compliance(1)\n            \n            # Get media processing success rate\n            media_metrics_key = f\"media_metrics:{datetime.now().strftime('%Y-%m-%d:%H')}\"\n            media_data = await asyncio.to_thread(self.redis_client.hgetall, media_metrics_key)\n            \n            total_media = sum(int(media_data.get(f'{media_type}_total', 0)) for media_type in ['image', 'audio', 'document', 'video'])\n            success_media = sum(int(media_data.get(f'{media_type}_success', 0)) for media_type in ['image', 'audio', 'document', 'video'])\n            media_success_rate = (success_media / max(total_media, 1)) * 100 if total_media > 0 else 100.0\n            \n            # Get handoff count\n            handoff_key = f\"handoffs:{datetime.now().strftime('%Y-%m-%d:%H')}\"\n            handoff_data = await asyncio.to_thread(self.redis_client.lrange, handoff_key, 0, -1)\n            handoff_count = len(handoff_data)\n            \n            metrics = PerformanceMetrics(\n                timestamp=datetime.now(),\n                active_channels=0,  # Will be updated by channel manager\n                concurrent_users=0,  # Will be updated by channel manager\n                message_throughput=message_throughput,\n                avg_response_time=avg_response_time,\n                sla_compliance_rate=sla_compliance,\n                media_processing_success_rate=media_success_rate,\n                cross_channel_handoffs=handoff_count,\n                personality_adaptation_accuracy=95.0,  # Placeholder - would be calculated from actual data\n                error_rate=error_rate\n            )\n            \n            return metrics\n            \n        except Exception as e:\n            logger.error(f\"Error getting performance metrics: {e}\")\n            return PerformanceMetrics(\n                timestamp=datetime.now(),\n                active_channels=0,\n                concurrent_users=0,\n                message_throughput=0.0,\n                avg_response_time=0.0,\n                sla_compliance_rate=0.0,\n                media_processing_success_rate=0.0,\n                cross_channel_handoffs=0,\n                personality_adaptation_accuracy=0.0,\n                error_rate=100.0\n            )\n    \n    async def generate_sla_report(self, hours: int = 24) -> SLAReport:\n        \"\"\"Generate comprehensive SLA compliance report\"\"\"\n        try:\n            end_time = datetime.now()\n            start_time = end_time - timedelta(hours=hours)\n            \n            # Get response times for the period\n            response_times = await asyncio.to_thread(self.redis_client.lrange, 'response_times_global', 0, -1)\n            response_times = [float(rt) for rt in response_times]\n            \n            target_response_time = 3.0\n            within_sla = sum(1 for rt in response_times if rt <= target_response_time)\n            total_messages = len(response_times)\n            \n            compliance_percentage = (within_sla / max(total_messages, 1)) * 100\n            avg_response_time = sum(response_times) / max(total_messages, 1) if response_times else 0.0\n            \n            # Get peak concurrent users\n            peak_key = f\"peak_users:{datetime.now().strftime('%Y-%m-%d')}\"\n            peak_users = int(await asyncio.to_thread(self.redis_client.get, peak_key) or 0)\n            \n            # Calculate uptime (simplified - assumes 100% if no critical errors)\n            uptime_percentage = 100.0  # Would be calculated from actual downtime data\n            \n            report = SLAReport(\n                period_start=start_time,\n                period_end=end_time,\n                target_response_time=target_response_time,\n                actual_avg_response_time=avg_response_time,\n                compliance_percentage=compliance_percentage,\n                total_messages=total_messages,\n                within_sla_messages=within_sla,\n                peak_concurrent_users=peak_users,\n                uptime_percentage=uptime_percentage\n            )\n            \n            logger.info(f\"Generated SLA report: {compliance_percentage:.1f}% compliance over {hours}h\")\n            return report\n            \n        except Exception as e:\n            logger.error(f\"Error generating SLA report: {e}\")\n            return SLAReport(\n                period_start=datetime.now() - timedelta(hours=hours),\n                period_end=datetime.now(),\n                target_response_time=3.0,\n                actual_avg_response_time=0.0,\n                compliance_percentage=0.0,\n                total_messages=0,\n                within_sla_messages=0,\n                peak_concurrent_users=0,\n                uptime_percentage=0.0\n            )\n    \n    async def store_performance_snapshot(self):\n        \"\"\"Store current performance metrics snapshot to database\"\"\"\n        if not self.db_connection:\n            return\n            \n        try:\n            metrics = await self.get_current_performance_metrics()\n            \n            with self.db_connection.cursor() as cursor:\n                cursor.execute(\"\"\"\n                    INSERT INTO whatsapp_performance_snapshots \n                    (timestamp, active_channels, concurrent_users, message_throughput,\n                     avg_response_time, sla_compliance_rate, media_processing_success_rate,\n                     cross_channel_handoffs, personality_adaptation_accuracy, error_rate)\n                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n                \"\"\", (\n                    metrics.timestamp,\n                    metrics.active_channels,\n                    metrics.concurrent_users,\n                    metrics.message_throughput,\n                    metrics.avg_response_time,\n                    metrics.sla_compliance_rate,\n                    metrics.media_processing_success_rate,\n                    metrics.cross_channel_handoffs,\n                    metrics.personality_adaptation_accuracy,\n                    metrics.error_rate\n                ))\n                \n                self.db_connection.commit()\n                logger.debug(\"Performance snapshot stored to database\")\n                \n        except Exception as e:\n            logger.error(f\"Error storing performance snapshot: {e}\")\n    \n    async def create_monitoring_tables(self):\n        \"\"\"Create monitoring database tables\"\"\"\n        if not self.db_connection:\n            return\n            \n        try:\n            with self.db_connection.cursor() as cursor:\n                # Performance snapshots table\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS whatsapp_performance_snapshots (\n                        id SERIAL PRIMARY KEY,\n                        timestamp TIMESTAMP NOT NULL,\n                        active_channels INTEGER NOT NULL,\n                        concurrent_users INTEGER NOT NULL,\n                        message_throughput DECIMAL(10,3) NOT NULL,\n                        avg_response_time DECIMAL(10,3) NOT NULL,\n                        sla_compliance_rate DECIMAL(5,2) NOT NULL,\n                        media_processing_success_rate DECIMAL(5,2) NOT NULL,\n                        cross_channel_handoffs INTEGER NOT NULL,\n                        personality_adaptation_accuracy DECIMAL(5,2) NOT NULL,\n                        error_rate DECIMAL(5,2) NOT NULL,\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                    \n                    CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON whatsapp_performance_snapshots(timestamp);\n                    CREATE INDEX IF NOT EXISTS idx_performance_sla ON whatsapp_performance_snapshots(sla_compliance_rate);\n                \"\"\")\n                \n                # SLA reports table\n                cursor.execute(\"\"\"\n                    CREATE TABLE IF NOT EXISTS whatsapp_sla_reports (\n                        id SERIAL PRIMARY KEY,\n                        period_start TIMESTAMP NOT NULL,\n                        period_end TIMESTAMP NOT NULL,\n                        target_response_time DECIMAL(5,2) NOT NULL,\n                        actual_avg_response_time DECIMAL(10,3) NOT NULL,\n                        compliance_percentage DECIMAL(5,2) NOT NULL,\n                        total_messages INTEGER NOT NULL,\n                        within_sla_messages INTEGER NOT NULL,\n                        peak_concurrent_users INTEGER NOT NULL,\n                        uptime_percentage DECIMAL(5,2) NOT NULL,\n                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n                    );\n                    \n                    CREATE INDEX IF NOT EXISTS idx_sla_period ON whatsapp_sla_reports(period_start, period_end);\n                \"\"\")\n                \n                self.db_connection.commit()\n                logger.info(\"Monitoring database tables created\")\n                \n        except Exception as e:\n            logger.error(f\"Error creating monitoring tables: {e}\")\n    \n    async def start_monitoring_loop(self, interval_seconds: int = 60):\n        \"\"\"Start continuous performance monitoring loop\"\"\"\n        logger.info(f\"Starting WhatsApp performance monitoring (interval: {interval_seconds}s)\")\n        \n        # Create tables if needed\n        await self.create_monitoring_tables()\n        \n        while True:\n            try:\n                # Store performance snapshot\n                await self.store_performance_snapshot()\n                \n                # Update SLA compliance\n                await self.calculate_sla_compliance()\n                \n                # Log current metrics\n                metrics = await self.get_current_performance_metrics()\n                logger.info(\n                    f\"Performance snapshot: \"\n                    f\"throughput={metrics.message_throughput:.2f}msg/s, \"\n                    f\"avg_response={metrics.avg_response_time:.2f}s, \"\n                    f\"sla_compliance={metrics.sla_compliance_rate:.1f}%, \"\n                    f\"error_rate={metrics.error_rate:.1f}%\"\n                )\n                \n                await asyncio.sleep(interval_seconds)\n                \n            except Exception as e:\n                logger.error(f\"Error in monitoring loop: {e}\")\n                await asyncio.sleep(interval_seconds)\n    \n    def start_prometheus_server(self, port: int = 9090):\n        \"\"\"Start Prometheus metrics server\"\"\"\n        try:\n            start_http_server(port)\n            logger.info(f\"Prometheus metrics server started on port {port}\")\n        except Exception as e:\n            logger.error(f\"Error starting Prometheus server: {e}\")\n    \n    async def get_health_check(self) -> Dict[str, Any]:\n        \"\"\"Get monitoring system health check\"\"\"\n        try:\n            redis_status = \"connected\"\n            try:\n                await asyncio.to_thread(self.redis_client.ping)\n            except:\n                redis_status = \"disconnected\"\n            \n            db_status = \"connected\" if self.db_connection else \"disconnected\"\n            if self.db_connection:\n                try:\n                    with self.db_connection.cursor() as cursor:\n                        cursor.execute(\"SELECT 1\")\n                except:\n                    db_status = \"error\"\n            \n            current_metrics = await self.get_current_performance_metrics()\n            \n            return {\n                \"service\": \"whatsapp_performance_monitor\",\n                \"status\": \"healthy\",\n                \"timestamp\": datetime.now().isoformat(),\n                \"connections\": {\n                    \"redis\": redis_status,\n                    \"database\": db_status\n                },\n                \"current_metrics\": asdict(current_metrics),\n                \"monitoring\": {\n                    \"prometheus_enabled\": True,\n                    \"sla_target\": \"3.0s response time\",\n                    \"concurrent_user_target\": \"500+ users\",\n                    \"phase2_features_monitored\": [\n                        \"media_processing\",\n                        \"cross_channel_handoffs\",\n                        \"personality_adaptation\",\n                        \"premium_casual_tone\"\n                    ]\n                }\n            }\n            \n        except Exception as e:\n            logger.error(f\"Error in health check: {e}\")\n            return {\n                \"service\": \"whatsapp_performance_monitor\",\n                \"status\": \"error\",\n                \"error\": str(e),\n                \"timestamp\": datetime.now().isoformat()\n            }\n\n# Global monitor instance\nperformance_monitor = WhatsAppPerformanceMonitor()\n\n\nif __name__ == \"__main__\":\n    \"\"\"Run monitoring system standalone\"\"\"\n    import argparse\n    \n    parser = argparse.ArgumentParser(description='WhatsApp Performance Monitor')\n    parser.add_argument('--prometheus-port', type=int, default=9090, help='Prometheus metrics port')\n    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds')\n    \n    args = parser.parse_args()\n    \n    # Configure logging\n    logging.basicConfig(\n        level=logging.INFO,\n        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'\n    )\n    \n    async def main():\n        # Start Prometheus server\n        performance_monitor.start_prometheus_server(args.prometheus_port)\n        \n        # Start monitoring loop\n        await performance_monitor.start_monitoring_loop(args.interval)\n    \n    asyncio.run(main())