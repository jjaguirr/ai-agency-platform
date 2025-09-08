"""
Voice Performance Monitoring System
Tracks voice integration performance metrics and SLA compliance
"""

import asyncio
import logging
import time
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import json

# Monitoring imports
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class VoiceInteractionMetrics:
    """Metrics for a single voice interaction"""
    customer_id: str
    conversation_id: str
    interaction_id: str
    timestamp: datetime
    
    # Performance metrics
    total_response_time: float
    speech_to_text_time: float
    ea_processing_time: float
    text_to_speech_time: float
    
    # Quality metrics
    audio_input_size_bytes: int
    audio_output_size_bytes: int
    transcript_length: int
    response_length: int
    
    # Language metrics
    detected_language: str
    response_language: str
    language_switch: bool
    
    # Success metrics
    success: bool
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    # SLA compliance
    meets_response_time_sla: bool = None
    
    def __post_init__(self):
        if self.meets_response_time_sla is None:
            self.meets_response_time_sla = self.total_response_time <= 2.0

@dataclass
class VoicePerformanceSummary:
    """Summary of voice performance metrics"""
    period_start: datetime
    period_end: datetime
    
    # Volume metrics
    total_interactions: int
    unique_customers: int
    unique_conversations: int
    
    # Performance metrics
    avg_response_time: float
    p50_response_time: float
    p95_response_time: float
    p99_response_time: float
    
    # SLA compliance
    sla_compliance_rate: float
    target_response_time: float = 2.0
    
    # Language distribution
    language_distribution: Dict[str, int] = None
    
    # Error metrics
    error_rate: float = 0.0
    error_types: Dict[str, int] = None
    
    def __post_init__(self):
        if self.language_distribution is None:
            self.language_distribution = {}
        if self.error_types is None:
            self.error_types = {}

class VoicePerformanceMonitor:
    """
    Voice performance monitoring system with real-time metrics and alerts
    
    Features:
    - Real-time performance tracking
    - SLA compliance monitoring
    - Alert generation for performance issues
    - Historical performance analytics
    - Prometheus metrics export
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Performance targets
        self.response_time_sla = self.config.get("response_time_sla", 2.0)
        self.sla_compliance_target = self.config.get("sla_compliance_target", 0.95)
        
        # Monitoring windows
        self.sliding_window_size = self.config.get("sliding_window_size", 1000)
        self.alert_window_minutes = self.config.get("alert_window_minutes", 5)
        
        # Storage for metrics
        self.metrics: deque = deque(maxlen=self.sliding_window_size)
        self.recent_metrics: deque = deque(maxlen=100)  # For alert checking
        
        # Performance summaries
        self.hourly_summaries: Dict[str, VoicePerformanceSummary] = {}
        self.daily_summaries: Dict[str, VoicePerformanceSummary] = {}
        
        # Alert state
        self.alert_conditions = {
            "high_response_time": False,
            "low_sla_compliance": False,
            "high_error_rate": False
        }
        self.last_alert_times: Dict[str, datetime] = {}
        
        # Prometheus metrics
        self.setup_prometheus_metrics()
        
        logger.info("Voice performance monitor initialized", 
                   response_time_sla=self.response_time_sla,
                   sla_compliance_target=self.sla_compliance_target)
    
    def setup_prometheus_metrics(self):
        """Setup Prometheus metrics for monitoring"""
        self.registry = CollectorRegistry()
        
        # Response time histogram
        self.response_time_histogram = Histogram(
            'voice_response_time_seconds',
            'Voice interaction response time in seconds',
            ['customer_id', 'language', 'interaction_type'],
            registry=self.registry,
            buckets=(0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
        )
        
        # Success/failure counters
        self.interaction_counter = Counter(
            'voice_interactions_total',
            'Total number of voice interactions',
            ['customer_id', 'language', 'status'],
            registry=self.registry
        )
        
        # Current SLA compliance gauge
        self.sla_compliance_gauge = Gauge(
            'voice_sla_compliance_rate',
            'Current SLA compliance rate',
            registry=self.registry
        )
        
        # Error rate gauge
        self.error_rate_gauge = Gauge(
            'voice_error_rate',
            'Current error rate',
            registry=self.registry
        )
        
        # Active conversations gauge
        self.active_conversations_gauge = Gauge(
            'voice_active_conversations',
            'Number of active voice conversations',
            registry=self.registry
        )
    
    async def record_interaction(self, metrics: VoiceInteractionMetrics):
        """Record a voice interaction with performance metrics"""
        try:
            # Add to collections
            self.metrics.append(metrics)
            self.recent_metrics.append(metrics)
            
            # Update Prometheus metrics
            self.response_time_histogram.labels(
                customer_id=metrics.customer_id,
                language=metrics.detected_language,
                interaction_type='voice_message'
            ).observe(metrics.total_response_time)
            
            self.interaction_counter.labels(
                customer_id=metrics.customer_id,
                language=metrics.detected_language,
                status='success' if metrics.success else 'error'
            ).inc()
            
            # Update gauges
            await self._update_realtime_gauges()
            
            # Check for alert conditions
            await self._check_alert_conditions()
            
            # Update performance summaries
            await self._update_performance_summaries(metrics)
            
            logger.debug("Voice interaction recorded", 
                        interaction_id=metrics.interaction_id,
                        response_time=metrics.total_response_time,
                        success=metrics.success)
            
        except Exception as e:
            logger.error("Error recording voice interaction", error=str(e))
    
    async def _update_realtime_gauges(self):
        """Update real-time Prometheus gauges"""
        if not self.recent_metrics:
            return
        
        recent_list = list(self.recent_metrics)
        
        # Calculate SLA compliance for recent interactions
        successful_interactions = [m for m in recent_list if m.success]
        if successful_interactions:
            sla_compliant = sum(1 for m in successful_interactions if m.meets_response_time_sla)
            sla_rate = sla_compliant / len(successful_interactions)
            self.sla_compliance_gauge.set(sla_rate)
        
        # Calculate error rate
        total_recent = len(recent_list)
        errors = sum(1 for m in recent_list if not m.success)
        error_rate = errors / total_recent if total_recent > 0 else 0
        self.error_rate_gauge.set(error_rate)
    
    async def _check_alert_conditions(self):
        """Check for alert conditions based on recent metrics"""
        if len(self.recent_metrics) < 10:  # Need minimum data for alerts
            return
        
        recent_list = list(self.recent_metrics)
        now = datetime.now()
        
        # Check high response time alert
        successful_recent = [m for m in recent_list if m.success]
        if successful_recent:
            avg_response_time = statistics.mean(m.total_response_time for m in successful_recent)
            
            if avg_response_time > self.response_time_sla * 1.5:  # 50% above SLA
                await self._trigger_alert("high_response_time", {
                    "avg_response_time": avg_response_time,
                    "sla_target": self.response_time_sla,
                    "sample_size": len(successful_recent)
                })
        
        # Check SLA compliance alert
        if successful_recent:
            sla_compliant = sum(1 for m in successful_recent if m.meets_response_time_sla)
            compliance_rate = sla_compliant / len(successful_recent)
            
            if compliance_rate < self.sla_compliance_target:
                await self._trigger_alert("low_sla_compliance", {
                    "compliance_rate": compliance_rate,
                    "target_rate": self.sla_compliance_target,
                    "sample_size": len(successful_recent)
                })
        
        # Check error rate alert
        error_rate = sum(1 for m in recent_list if not m.success) / len(recent_list)
        if error_rate > 0.1:  # 10% error rate threshold
            await self._trigger_alert("high_error_rate", {
                "error_rate": error_rate,
                "threshold": 0.1,
                "sample_size": len(recent_list)
            })
    
    async def _trigger_alert(self, alert_type: str, context: Dict[str, Any]):
        """Trigger performance alert"""
        now = datetime.now()
        
        # Rate limit alerts (max one per alert type per 5 minutes)
        last_alert = self.last_alert_times.get(alert_type)
        if last_alert and (now - last_alert).seconds < 300:
            return
        
        self.alert_conditions[alert_type] = True
        self.last_alert_times[alert_type] = now
        
        logger.warning("Voice performance alert triggered",
                      alert_type=alert_type,
                      context=context,
                      timestamp=now.isoformat())
        
        # TODO: Integrate with alerting system (Slack, PagerDuty, etc.)
        await self._send_alert_notification(alert_type, context)
    
    async def _send_alert_notification(self, alert_type: str, context: Dict[str, Any]):
        """Send alert notification (placeholder for integration)"""
        # This would integrate with your alerting system
        alert_message = f"Voice Performance Alert: {alert_type}"
        logger.info("Alert notification sent", 
                   alert_type=alert_type, 
                   message=alert_message)
    
    async def _update_performance_summaries(self, metrics: VoiceInteractionMetrics):
        """Update hourly and daily performance summaries"""
        timestamp = metrics.timestamp
        hour_key = timestamp.strftime("%Y-%m-%d-%H")
        day_key = timestamp.strftime("%Y-%m-%d")
        
        # Update hourly summary
        if hour_key not in self.hourly_summaries:
            self.hourly_summaries[hour_key] = await self._create_performance_summary(
                timestamp.replace(minute=0, second=0, microsecond=0),
                timestamp.replace(minute=59, second=59, microsecond=999999)
            )
        
        # Update daily summary
        if day_key not in self.daily_summaries:
            self.daily_summaries[day_key] = await self._create_performance_summary(
                timestamp.replace(hour=0, minute=0, second=0, microsecond=0),
                timestamp.replace(hour=23, minute=59, second=59, microsecond=999999)
            )
    
    async def _create_performance_summary(
        self, 
        start_time: datetime, 
        end_time: datetime
    ) -> VoicePerformanceSummary:
        """Create performance summary for time period"""
        # Filter metrics for time period
        period_metrics = [
            m for m in self.metrics 
            if start_time <= m.timestamp <= end_time
        ]
        
        if not period_metrics:
            return VoicePerformanceSummary(
                period_start=start_time,
                period_end=end_time,
                total_interactions=0,
                unique_customers=0,
                unique_conversations=0,
                avg_response_time=0.0,
                p50_response_time=0.0,
                p95_response_time=0.0,
                p99_response_time=0.0,
                sla_compliance_rate=0.0
            )
        
        # Calculate metrics
        successful_metrics = [m for m in period_metrics if m.success]
        response_times = [m.total_response_time for m in successful_metrics]
        
        # Performance calculations
        avg_response_time = statistics.mean(response_times) if response_times else 0.0
        p50 = statistics.median(response_times) if response_times else 0.0
        p95 = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else 0.0
        p99 = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else 0.0
        
        # SLA compliance
        sla_compliant = sum(1 for m in successful_metrics if m.meets_response_time_sla)
        sla_rate = sla_compliant / len(successful_metrics) if successful_metrics else 0.0
        
        # Language distribution
        language_dist = defaultdict(int)
        for m in period_metrics:
            language_dist[m.detected_language] += 1
        
        # Error metrics
        error_count = len([m for m in period_metrics if not m.success])
        error_rate = error_count / len(period_metrics)
        
        error_types = defaultdict(int)
        for m in period_metrics:
            if not m.success and m.error_type:
                error_types[m.error_type] += 1
        
        return VoicePerformanceSummary(
            period_start=start_time,
            period_end=end_time,
            total_interactions=len(period_metrics),
            unique_customers=len(set(m.customer_id for m in period_metrics)),
            unique_conversations=len(set(m.conversation_id for m in period_metrics)),
            avg_response_time=avg_response_time,
            p50_response_time=p50,
            p95_response_time=p95,
            p99_response_time=p99,
            sla_compliance_rate=sla_rate,
            language_distribution=dict(language_dist),
            error_rate=error_rate,
            error_types=dict(error_types)
        )
    
    async def get_current_performance(self) -> Dict[str, Any]:
        """Get current performance metrics"""
        if not self.metrics:
            return {
                "status": "no_data",
                "message": "No voice interactions recorded yet"
            }
        
        recent_count = min(100, len(self.metrics))
        recent_metrics = list(self.metrics)[-recent_count:]
        
        successful = [m for m in recent_metrics if m.success]
        response_times = [m.total_response_time for m in successful]
        
        performance = {
            "timestamp": datetime.now().isoformat(),
            "sample_size": len(recent_metrics),
            "successful_interactions": len(successful),
            "total_interactions": len(recent_metrics),
            "success_rate": len(successful) / len(recent_metrics) if recent_metrics else 0,
            
            # Response time metrics
            "avg_response_time": statistics.mean(response_times) if response_times else 0,
            "median_response_time": statistics.median(response_times) if response_times else 0,
            "min_response_time": min(response_times) if response_times else 0,
            "max_response_time": max(response_times) if response_times else 0,
            
            # SLA compliance
            "sla_compliance_rate": sum(1 for m in successful if m.meets_response_time_sla) / len(successful) if successful else 0,
            "sla_target": self.response_time_sla,
            
            # Language distribution
            "language_distribution": dict(defaultdict(int, {
                m.detected_language: sum(1 for x in recent_metrics if x.detected_language == m.detected_language)
                for m in recent_metrics
            })),
            
            # Alert status
            "active_alerts": [k for k, v in self.alert_conditions.items() if v],
            "alert_conditions": self.alert_conditions.copy()
        }
        
        return performance
    
    async def get_performance_summary(
        self, 
        period: str = "hour", 
        start_time: Optional[datetime] = None
    ) -> Optional[VoicePerformanceSummary]:
        """Get performance summary for specified period"""
        now = datetime.now()
        
        if period == "hour":
            target_time = start_time or now
            hour_key = target_time.strftime("%Y-%m-%d-%H")
            return self.hourly_summaries.get(hour_key)
        
        elif period == "day":
            target_time = start_time or now
            day_key = target_time.strftime("%Y-%m-%d")
            return self.daily_summaries.get(day_key)
        
        else:
            # Generate custom period summary
            if not start_time:
                start_time = now - timedelta(hours=1)
            end_time = start_time + timedelta(hours=1)
            
            return await self._create_performance_summary(start_time, end_time)
    
    def export_prometheus_metrics(self) -> bytes:
        """Export Prometheus metrics"""
        return generate_latest(self.registry)
    
    async def cleanup_old_data(self, days_to_keep: int = 7):
        """Clean up old performance data"""
        cutoff_time = datetime.now() - timedelta(days=days_to_keep)
        
        # Clean up hourly summaries
        old_hour_keys = [
            k for k, v in self.hourly_summaries.items()
            if v.period_start < cutoff_time
        ]
        for key in old_hour_keys:
            del self.hourly_summaries[key]
        
        # Clean up daily summaries
        old_day_keys = [
            k for k, v in self.daily_summaries.items()
            if v.period_start < cutoff_time
        ]
        for key in old_day_keys:
            del self.daily_summaries[key]
        
        logger.info("Performance data cleanup completed",
                   removed_hourly=len(old_hour_keys),
                   removed_daily=len(old_day_keys))
    
    async def generate_performance_report(
        self, 
        start_time: datetime, 
        end_time: datetime
    ) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        # Filter metrics for report period
        period_metrics = [
            m for m in self.metrics 
            if start_time <= m.timestamp <= end_time
        ]
        
        if not period_metrics:
            return {
                "period": {"start": start_time.isoformat(), "end": end_time.isoformat()},
                "status": "no_data",
                "message": "No data available for requested period"
            }
        
        summary = await self._create_performance_summary(start_time, end_time)
        
        # Additional analytics
        successful_metrics = [m for m in period_metrics if m.success]
        
        # Response time analysis by language
        language_performance = {}
        for lang in summary.language_distribution.keys():
            lang_metrics = [m for m in successful_metrics if m.detected_language == lang]
            if lang_metrics:
                lang_response_times = [m.total_response_time for m in lang_metrics]
                language_performance[lang] = {
                    "count": len(lang_metrics),
                    "avg_response_time": statistics.mean(lang_response_times),
                    "p95_response_time": statistics.quantiles(lang_response_times, n=20)[18] if len(lang_response_times) >= 20 else 0,
                    "sla_compliance": sum(1 for m in lang_metrics if m.meets_response_time_sla) / len(lang_metrics)
                }
        
        # Customer performance analysis
        customer_performance = {}
        for customer_id in set(m.customer_id for m in period_metrics):
            customer_metrics = [m for m in successful_metrics if m.customer_id == customer_id]
            if customer_metrics:
                customer_response_times = [m.total_response_time for m in customer_metrics]
                customer_performance[customer_id] = {
                    "interactions": len(customer_metrics),
                    "avg_response_time": statistics.mean(customer_response_times),
                    "sla_compliance": sum(1 for m in customer_metrics if m.meets_response_time_sla) / len(customer_metrics)
                }
        
        return {
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_hours": (end_time - start_time).total_seconds() / 3600
            },
            "summary": asdict(summary),
            "language_performance": language_performance,
            "top_customers": dict(sorted(
                customer_performance.items(),
                key=lambda x: x[1]["interactions"],
                reverse=True
            )[:10]),
            "recommendations": self._generate_recommendations(summary, language_performance)
        }
    
    def _generate_recommendations(
        self, 
        summary: VoicePerformanceSummary, 
        language_performance: Dict[str, Any]
    ) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []
        
        # SLA compliance recommendations
        if summary.sla_compliance_rate < self.sla_compliance_target:
            recommendations.append(
                f"SLA compliance ({summary.sla_compliance_rate:.2%}) is below target "
                f"({self.sla_compliance_target:.2%}). Consider optimizing response pipeline."
            )
        
        # Response time recommendations
        if summary.p95_response_time > self.response_time_sla:
            recommendations.append(
                f"95th percentile response time ({summary.p95_response_time:.2f}s) exceeds "
                f"SLA ({self.response_time_sla}s). Review slow interactions."
            )
        
        # Language-specific recommendations
        for lang, perf in language_performance.items():
            if perf["sla_compliance"] < 0.9:
                recommendations.append(
                    f"Consider optimizing {lang} voice processing - "
                    f"compliance rate is {perf['sla_compliance']:.2%}"
                )
        
        # Error rate recommendations
        if summary.error_rate > 0.05:
            recommendations.append(
                f"Error rate ({summary.error_rate:.2%}) is high. "
                f"Review common error types: {list(summary.error_types.keys())}"
            )
        
        return recommendations

# Global performance monitor instance
voice_performance_monitor = VoicePerformanceMonitor()

# Helper functions for integration

async def record_voice_interaction(
    customer_id: str,
    conversation_id: str,
    interaction_id: str,
    total_response_time: float,
    speech_to_text_time: float = 0.0,
    ea_processing_time: float = 0.0,
    text_to_speech_time: float = 0.0,
    audio_input_size: int = 0,
    audio_output_size: int = 0,
    transcript_length: int = 0,
    response_length: int = 0,
    detected_language: str = "en",
    response_language: str = "en",
    language_switch: bool = False,
    success: bool = True,
    error_type: str = None,
    error_message: str = None
) -> None:
    """Record voice interaction metrics"""
    
    metrics = VoiceInteractionMetrics(
        customer_id=customer_id,
        conversation_id=conversation_id,
        interaction_id=interaction_id,
        timestamp=datetime.now(),
        total_response_time=total_response_time,
        speech_to_text_time=speech_to_text_time,
        ea_processing_time=ea_processing_time,
        text_to_speech_time=text_to_speech_time,
        audio_input_size_bytes=audio_input_size,
        audio_output_size_bytes=audio_output_size,
        transcript_length=transcript_length,
        response_length=response_length,
        detected_language=detected_language,
        response_language=response_language,
        language_switch=language_switch,
        success=success,
        error_type=error_type,
        error_message=error_message
    )
    
    await voice_performance_monitor.record_interaction(metrics)

async def get_voice_performance_dashboard() -> Dict[str, Any]:
    """Get voice performance dashboard data"""
    current_perf = await voice_performance_monitor.get_current_performance()
    
    # Get hourly and daily summaries
    hourly_summary = await voice_performance_monitor.get_performance_summary("hour")
    daily_summary = await voice_performance_monitor.get_performance_summary("day")
    
    return {
        "current_performance": current_perf,
        "hourly_summary": asdict(hourly_summary) if hourly_summary else None,
        "daily_summary": asdict(daily_summary) if daily_summary else None,
        "prometheus_metrics_url": "/voice/metrics"
    }