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
            sla_compliance = await self.calculate_sla_compliance(1)
            
            # Get media processing success rate
            media_metrics_key = f"media_metrics:{datetime.now().strftime('%Y-%m-%d:%H')}"
            media_data = await asyncio.to_thread(self.redis_client.hgetall, media_metrics_key)
            
            total_media = sum(int(media_data.get(f'{media_type}_total', 0)) for media_type in ['image', 'audio', 'document', 'video'])
            success_media = sum(int(media_data.get(f'{media_type}_success', 0)) for media_type in ['image', 'audio', 'document', 'video'])
            media_success_rate = (success_media / max(total_media, 1)) * 100 if total_media > 0 else 100.0
            
            # Get handoff count
            handoff_key = f"handoffs:{datetime.now().strftime('%Y-%m-%d:%H')}"
            handoff_data = await asyncio.to_thread(self.redis_client.lrange, handoff_key, 0, -1)
            handoff_count = len(handoff_data)
            
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                active_channels=0,  # Will be updated by channel manager
                concurrent_users=0,  # Will be updated by channel manager
                message_throughput=message_throughput,
                avg_response_time=avg_response_time,
                sla_compliance_rate=sla_compliance,
                media_processing_success_rate=media_success_rate,
                cross_channel_handoffs=handoff_count,
                personality_adaptation_accuracy=95.0,  # Placeholder - would be calculated from actual data
                error_rate=error_rate
            )
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return PerformanceMetrics(
                timestamp=datetime.now(),
                active_channels=0,
                concurrent_users=0,
                message_throughput=0.0,
                avg_response_time=0.0,
                sla_compliance_rate=0.0,
                media_processing_success_rate=0.0,
                cross_channel_handoffs=0,
                personality_adaptation_accuracy=0.0,
                error_rate=100.0
            )
    
    async def generate_sla_report(self, hours: int = 24) -> SLAReport:
        """Generate comprehensive SLA compliance report"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            
            # Get response times for the period
            response_times = await asyncio.to_thread(self.redis_client.lrange, 'response_times_global', 0, -1)
            response_times = [float(rt) for rt in response_times]
            
            target_response_time = 3.0
            within_sla = sum(1 for rt in response_times if rt <= target_response_time)
            total_messages = len(response_times)
            
            compliance_percentage = (within_sla / max(total_messages, 1)) * 100
            avg_response_time = sum(response_times) / max(total_messages, 1) if response_times else 0.0
            
            # Get peak concurrent users
            peak_key = f"peak_users:{datetime.now().strftime('%Y-%m-%d')}"
            peak_users = int(await asyncio.to_thread(self.redis_client.get, peak_key) or 0)
            
            # Calculate uptime (simplified - assumes 100% if no critical errors)
            uptime_percentage = 100.0  # Would be calculated from actual downtime data
            
            report = SLAReport(
                period_start=start_time,
                period_end=end_time,
                target_response_time=target_response_time,
                actual_avg_response_time=avg_response_time,
                compliance_percentage=compliance_percentage,
                total_messages=total_messages,
                within_sla_messages=within_sla,
                peak_concurrent_users=peak_users,
                uptime_percentage=uptime_percentage
            )
            
            logger.info(f"Generated SLA report: {compliance_percentage:.1f}% compliance over {hours}h")
            return report
            
        except Exception as e:
            logger.error(f"Error generating SLA report: {e}")
            return SLAReport(
                period_start=datetime.now() - timedelta(hours=hours),
                period_end=datetime.now(),
                target_response_time=3.0,
                actual_avg_response_time=0.0,
                compliance_percentage=0.0,
                total_messages=0,
                within_sla_messages=0,
                peak_concurrent_users=0,
                uptime_percentage=0.0
            )
    
    async def store_performance_snapshot(self):
        """Store current performance metrics snapshot to database"""
        if not self.db_connection:
            return
            
        try:
            metrics = await self.get_current_performance_metrics()
            
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO whatsapp_performance_snapshots 
                    (timestamp, active_channels, concurrent_users, message_throughput,
                     avg_response_time, sla_compliance_rate, media_processing_success_rate,
                     cross_channel_handoffs, personality_adaptation_accuracy, error_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    metrics.timestamp,
                    metrics.active_channels,
                    metrics.concurrent_users,
                    metrics.message_throughput,
                    metrics.avg_response_time,
                    metrics.sla_compliance_rate,
                    metrics.media_processing_success_rate,
                    metrics.cross_channel_handoffs,
                    metrics.personality_adaptation_accuracy,
                    metrics.error_rate
                ))
                
                self.db_connection.commit()
                logger.debug("Performance snapshot stored to database")
                
        except Exception as e:
            logger.error(f"Error storing performance snapshot: {e}")
    
    async def create_monitoring_tables(self):
        """Create monitoring database tables"""
        if not self.db_connection:
            return
            
        try:
            with self.db_connection.cursor() as cursor:
                # Performance snapshots table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS whatsapp_performance_snapshots (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL,
                        active_channels INTEGER NOT NULL,
                        concurrent_users INTEGER NOT NULL,
                        message_throughput DECIMAL(10,3) NOT NULL,
                        avg_response_time DECIMAL(10,3) NOT NULL,
                        sla_compliance_rate DECIMAL(5,2) NOT NULL,
                        media_processing_success_rate DECIMAL(5,2) NOT NULL,
                        cross_channel_handoffs INTEGER NOT NULL,
                        personality_adaptation_accuracy DECIMAL(5,2) NOT NULL,
                        error_rate DECIMAL(5,2) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON whatsapp_performance_snapshots(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_performance_sla ON whatsapp_performance_snapshots(sla_compliance_rate);
                """)
                
                # SLA reports table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS whatsapp_sla_reports (
                        id SERIAL PRIMARY KEY,
                        period_start TIMESTAMP NOT NULL,
                        period_end TIMESTAMP NOT NULL,
                        target_response_time DECIMAL(5,2) NOT NULL,
                        actual_avg_response_time DECIMAL(10,3) NOT NULL,
                        compliance_percentage DECIMAL(5,2) NOT NULL,
                        total_messages INTEGER NOT NULL,
                        within_sla_messages INTEGER NOT NULL,
                        peak_concurrent_users INTEGER NOT NULL,
                        uptime_percentage DECIMAL(5,2) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_sla_period ON whatsapp_sla_reports(period_start, period_end);
                """)
                
                self.db_connection.commit()
                logger.info("Monitoring database tables created")
                
        except Exception as e:
            logger.error(f"Error creating monitoring tables: {e}")
    
    async def start_monitoring_loop(self, interval_seconds: int = 60):
        """Start continuous performance monitoring loop"""
        logger.info(f"Starting WhatsApp performance monitoring (interval: {interval_seconds}s)")
        
        # Create tables if needed
        await self.create_monitoring_tables()
        
        while True:
            try:
                # Store performance snapshot
                await self.store_performance_snapshot()
                
                # Update SLA compliance
                await self.calculate_sla_compliance()
                
                # Log current metrics
                metrics = await self.get_current_performance_metrics()
                logger.info(
                    f"Performance snapshot: "
                    f"throughput={metrics.message_throughput:.2f}msg/s, "
                    f"avg_response={metrics.avg_response_time:.2f}s, "
                    f"sla_compliance={metrics.sla_compliance_rate:.1f}%, "
                    f"error_rate={metrics.error_rate:.1f}%"
                )
                
                await asyncio.sleep(interval_seconds)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval_seconds)
    
    def start_prometheus_server(self, port: int = 9090):
        """Start Prometheus metrics server"""
        try:
            start_http_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")
        except Exception as e:
            logger.error(f"Error starting Prometheus server: {e}")
    
    async def get_health_check(self) -> Dict[str, Any]:
        """Get monitoring system health check"""
        try:
            redis_status = "connected"
            try:
                await asyncio.to_thread(self.redis_client.ping)
            except:
                redis_status = "disconnected"
            
            db_status = "connected" if self.db_connection else "disconnected"
            if self.db_connection:
                try:
                    with self.db_connection.cursor() as cursor:
                        cursor.execute("SELECT 1")
                except:
                    db_status = "error"
            
            current_metrics = await self.get_current_performance_metrics()
            
            return {
                "service": "whatsapp_performance_monitor",
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "connections": {
                    "redis": redis_status,
                    "database": db_status
                },
                "current_metrics": asdict(current_metrics),
                "monitoring": {
                    "prometheus_enabled": True,
                    "sla_target": "3.0s response time",
                    "concurrent_user_target": "500+ users",
                    "phase2_features_monitored": [
                        "media_processing",
                        "cross_channel_handoffs",
                        "personality_adaptation",
                        "premium_casual_tone"
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {
                "service": "whatsapp_performance_monitor",
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

# Global monitor instance
performance_monitor = WhatsAppPerformanceMonitor()


if __name__ == "__main__":
    """Run monitoring system standalone"""
    import argparse
    
    parser = argparse.ArgumentParser(description='WhatsApp Performance Monitor')
    parser.add_argument('--prometheus-port', type=int, default=9090, help='Prometheus metrics port')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        # Start Prometheus server
        performance_monitor.start_prometheus_server(args.prometheus_port)
        
        # Start monitoring loop
        await performance_monitor.start_monitoring_loop(args.interval)
    
    asyncio.run(main())