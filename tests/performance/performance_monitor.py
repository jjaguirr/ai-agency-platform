#!/usr/bin/env python3
"""
Real-time Performance Monitoring and Alerting System

Comprehensive performance monitoring framework for continuous SLA validation
and automatic alerting when performance degrades below acceptable thresholds.

Features:
1. Real-time SLA monitoring
2. Performance regression detection  
3. Alert system for SLA violations
4. Performance dashboard generation
5. Resource utilization tracking
6. Customer experience impact measurement

Author: AI Agency Platform - Performance Engineering
Version: 1.0.0
"""

import asyncio
import time
import json
import statistics
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import psutil
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"

class MetricType(Enum):
    """Performance metric types"""
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"  
    THROUGHPUT = "throughput"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DATABASE_LATENCY = "database_latency"
    MEMORY_RECALL_TIME = "memory_recall_time"

@dataclass
class SLAThreshold:
    """SLA threshold definition"""
    metric_type: MetricType
    threshold_value: float
    comparison: str  # 'less_than', 'greater_than', 'equals'
    measurement_window_seconds: int = 60
    violation_threshold_percentage: float = 0.05  # 5% violation rate triggers alert

@dataclass 
class PerformanceAlert:
    """Performance alert data structure"""
    alert_id: str
    severity: AlertSeverity
    metric_type: MetricType
    current_value: float
    threshold_value: float
    message: str
    timestamp: datetime
    customer_impact_estimated: int = 0  # Number of customers potentially affected
    resolution_suggestions: List[str] = None

@dataclass
class PerformanceMetric:
    """Individual performance measurement"""
    metric_type: MetricType
    value: float
    timestamp: datetime
    customer_id: Optional[str] = None
    additional_context: Dict[str, Any] = None

class PerformanceMonitor:
    """Real-time performance monitoring system"""
    
    def __init__(self, monitoring_config: Dict[str, Any] = None):
        self.config = monitoring_config or self._default_config()
        self.sla_thresholds = self._initialize_sla_thresholds()
        self.metrics_buffer: List[PerformanceMetric] = []
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_callbacks: List[Callable] = []
        self.is_monitoring = False
        self.monitoring_task = None
        
    def _default_config(self) -> Dict[str, Any]:
        """Default monitoring configuration"""
        return {
            "monitoring_interval_seconds": 10,
            "metrics_retention_seconds": 3600,  # 1 hour
            "alert_cooldown_seconds": 300,      # 5 minutes
            "dashboard_update_interval": 30,    # 30 seconds
            "enable_auto_alerts": True,
            "metrics_export_path": "./performance_metrics",
            "dashboard_export_path": "./performance_dashboard.html"
        }
    
    def _initialize_sla_thresholds(self) -> List[SLAThreshold]:
        """Initialize production SLA thresholds"""
        return [
            # Core EA Performance SLAs
            SLAThreshold(
                metric_type=MetricType.RESPONSE_TIME,
                threshold_value=0.2,  # 200ms
                comparison="less_than",
                measurement_window_seconds=60
            ),
            SLAThreshold(
                metric_type=MetricType.ERROR_RATE, 
                threshold_value=0.05,  # 5%
                comparison="less_than",
                measurement_window_seconds=300  # 5 minutes
            ),
            SLAThreshold(
                metric_type=MetricType.THROUGHPUT,
                threshold_value=10.0,  # 10 RPS minimum
                comparison="greater_than",
                measurement_window_seconds=120
            ),
            SLAThreshold(
                metric_type=MetricType.CPU_USAGE,
                threshold_value=80.0,  # 80% CPU
                comparison="less_than",
                measurement_window_seconds=60
            ),
            SLAThreshold(
                metric_type=MetricType.MEMORY_USAGE,
                threshold_value=85.0,  # 85% Memory
                comparison="less_than", 
                measurement_window_seconds=60
            ),
            SLAThreshold(
                metric_type=MetricType.DATABASE_LATENCY,
                threshold_value=0.1,   # 100ms
                comparison="less_than",
                measurement_window_seconds=60
            ),
            SLAThreshold(
                metric_type=MetricType.MEMORY_RECALL_TIME,
                threshold_value=0.5,   # 500ms
                comparison="less_than", 
                measurement_window_seconds=60
            )
        ]
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """Add callback function for alert notifications"""
        self.alert_callbacks.append(callback)
    
    async def start_monitoring(self):
        """Start real-time performance monitoring"""
        if self.is_monitoring:
            logger.warning("Performance monitoring already running")
            return
            
        self.is_monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop performance monitoring"""
        self.is_monitoring = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitoring stopped")
    
    async def record_metric(self, metric: PerformanceMetric):
        """Record a performance metric"""
        self.metrics_buffer.append(metric)
        
        # Cleanup old metrics
        cutoff_time = datetime.now() - timedelta(seconds=self.config["metrics_retention_seconds"])
        self.metrics_buffer = [
            m for m in self.metrics_buffer 
            if m.timestamp > cutoff_time
        ]
        
        # Check for SLA violations
        if self.config["enable_auto_alerts"]:
            await self._check_sla_violations(metric.metric_type)
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.is_monitoring:
            try:
                # Collect system metrics
                await self._collect_system_metrics()
                
                # Update dashboard
                if self.config.get("dashboard_export_path"):
                    await self._update_dashboard()
                
                # Export metrics
                if self.config.get("metrics_export_path"):
                    await self._export_metrics()
                
                await asyncio.sleep(self.config["monitoring_interval_seconds"])
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _collect_system_metrics(self):
        """Collect system resource metrics"""
        current_time = datetime.now()
        
        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        await self.record_metric(PerformanceMetric(
            metric_type=MetricType.CPU_USAGE,
            value=cpu_percent,
            timestamp=current_time
        ))
        
        # Memory Usage
        memory_percent = psutil.virtual_memory().percent
        await self.record_metric(PerformanceMetric(
            metric_type=MetricType.MEMORY_USAGE,
            value=memory_percent,
            timestamp=current_time
        ))
    
    async def _check_sla_violations(self, metric_type: MetricType):
        """Check for SLA violations and trigger alerts"""
        relevant_thresholds = [t for t in self.sla_thresholds if t.metric_type == metric_type]
        
        for threshold in relevant_thresholds:
            # Get metrics within the measurement window
            cutoff_time = datetime.now() - timedelta(seconds=threshold.measurement_window_seconds)
            window_metrics = [
                m for m in self.metrics_buffer
                if m.metric_type == metric_type and m.timestamp > cutoff_time
            ]
            
            if not window_metrics:
                continue
                
            # Calculate violation rate
            violations = []
            for metric in window_metrics:
                is_violation = False
                if threshold.comparison == "less_than" and metric.value >= threshold.threshold_value:
                    is_violation = True
                elif threshold.comparison == "greater_than" and metric.value <= threshold.threshold_value:
                    is_violation = True
                elif threshold.comparison == "equals" and metric.value != threshold.threshold_value:
                    is_violation = True
                    
                if is_violation:
                    violations.append(metric)
            
            # Check if violation rate exceeds threshold
            violation_rate = len(violations) / len(window_metrics)
            if violation_rate >= threshold.violation_threshold_percentage:
                await self._trigger_alert(threshold, violations, window_metrics)
    
    async def _trigger_alert(self, threshold: SLAThreshold, violations: List[PerformanceMetric], all_metrics: List[PerformanceMetric]):
        """Trigger performance alert"""
        current_values = [m.value for m in all_metrics]
        current_avg = statistics.mean(current_values)
        violation_rate = len(violations) / len(all_metrics)
        
        # Determine severity
        if violation_rate >= 0.5:  # 50% or more violations
            severity = AlertSeverity.CRITICAL
        elif violation_rate >= 0.25:  # 25-50% violations
            severity = AlertSeverity.HIGH
        elif violation_rate >= 0.10:  # 10-25% violations
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW
        
        # Create alert ID
        alert_id = f"{threshold.metric_type.value}_{int(time.time())}"
        
        # Check alert cooldown
        if alert_id in self.active_alerts:
            last_alert_time = self.active_alerts[alert_id].timestamp
            if (datetime.now() - last_alert_time).total_seconds() < self.config["alert_cooldown_seconds"]:
                return  # Skip alert due to cooldown
        
        # Estimate customer impact
        customer_impact = self._estimate_customer_impact(threshold.metric_type, violation_rate)
        
        # Generate resolution suggestions
        resolution_suggestions = self._generate_resolution_suggestions(threshold.metric_type, current_avg)
        
        # Create alert
        alert = PerformanceAlert(
            alert_id=alert_id,
            severity=severity,
            metric_type=threshold.metric_type,
            current_value=current_avg,
            threshold_value=threshold.threshold_value,
            message=f"SLA violation: {threshold.metric_type.value} {current_avg:.3f} violates threshold {threshold.threshold_value} ({violation_rate*100:.1f}% violation rate)",
            timestamp=datetime.now(),
            customer_impact_estimated=customer_impact,
            resolution_suggestions=resolution_suggestions
        )
        
        self.active_alerts[alert_id] = alert
        
        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                await callback(alert) if asyncio.iscoroutinefunction(callback) else callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        logger.warning(f"Performance Alert: {alert.message}")
    
    def _estimate_customer_impact(self, metric_type: MetricType, violation_rate: float) -> int:
        """Estimate number of customers potentially affected"""
        # Simple estimation - could be enhanced with real customer data
        base_customers = 100  # Assumed concurrent customers
        
        if metric_type in [MetricType.RESPONSE_TIME, MetricType.ERROR_RATE]:
            return int(base_customers * violation_rate)
        elif metric_type in [MetricType.CPU_USAGE, MetricType.MEMORY_USAGE]:
            return int(base_customers * min(violation_rate * 2, 1.0))  # System issues affect more customers
        else:
            return int(base_customers * violation_rate * 0.5)
    
    def _generate_resolution_suggestions(self, metric_type: MetricType, current_value: float) -> List[str]:
        """Generate automated resolution suggestions"""
        suggestions = []
        
        if metric_type == MetricType.RESPONSE_TIME:
            suggestions = [
                "Check database connection pool utilization",
                "Review recent code deployments for performance regressions", 
                "Consider scaling up application instances",
                "Analyze slow API endpoints and optimize queries"
            ]
        elif metric_type == MetricType.ERROR_RATE:
            suggestions = [
                "Review application logs for error patterns",
                "Check external service dependencies health",
                "Validate recent configuration changes",
                "Monitor database connection stability"
            ]
        elif metric_type == MetricType.CPU_USAGE:
            suggestions = [
                "Scale up CPU resources or add more instances",
                "Identify CPU-intensive processes and optimize",
                "Review background job scheduling",
                "Consider implementing request throttling"
            ]
        elif metric_type == MetricType.MEMORY_USAGE:
            suggestions = [
                "Increase available memory or scale instances",
                "Check for memory leaks in application code",
                "Review memory-intensive operations",
                "Optimize data caching strategies"
            ]
        elif metric_type == MetricType.DATABASE_LATENCY:
            suggestions = [
                "Check database performance metrics",
                "Review and optimize slow queries",  
                "Consider database connection pooling tuning",
                "Monitor database server resource usage"
            ]
        elif metric_type == MetricType.MEMORY_RECALL_TIME:
            suggestions = [
                "Check Qdrant vector database performance",
                "Review memory search query complexity",
                "Consider memory index optimization",
                "Monitor vector database resource usage"
            ]
        
        return suggestions
    
    async def _update_dashboard(self):
        """Update performance dashboard"""
        dashboard_html = self._generate_dashboard_html()
        dashboard_path = Path(self.config["dashboard_export_path"])
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dashboard_path, 'w') as f:
            f.write(dashboard_html)
    
    def _generate_dashboard_html(self) -> str:
        """Generate HTML performance dashboard"""
        current_time = datetime.now()
        recent_metrics = [
            m for m in self.metrics_buffer
            if (current_time - m.timestamp).total_seconds() <= 300  # Last 5 minutes
        ]
        
        # Calculate current status for each metric type
        metric_status = {}
        for metric_type in MetricType:
            type_metrics = [m for m in recent_metrics if m.metric_type == metric_type]
            if type_metrics:
                values = [m.value for m in type_metrics]
                metric_status[metric_type.value] = {
                    'current': values[-1],
                    'average': statistics.mean(values),
                    'min': min(values),
                    'max': max(values),
                    'count': len(values)
                }
        
        # Generate HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>AI Agency Platform - Performance Dashboard</title>
    <meta http-equiv="refresh" content="{self.config['dashboard_update_interval']}">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .header {{ background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px; text-align: center; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }}
        .metric-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .metric-title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; margin-bottom: 5px; }}
        .metric-details {{ font-size: 12px; color: #7f8c8d; }}
        .status-good {{ color: #27ae60; }}
        .status-warning {{ color: #f39c12; }}
        .status-critical {{ color: #e74c3c; }}
        .alerts-section {{ background: white; margin-top: 20px; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .alert-item {{ padding: 10px; margin: 10px 0; border-left: 4px solid #e74c3c; background-color: #fdf2f2; }}
        .timestamp {{ text-align: center; margin-top: 20px; color: #7f8c8d; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 AI Agency Platform - Performance Dashboard</h1>
        <p>Real-time SLA monitoring and performance metrics</p>
    </div>
    
    <div class="metrics-grid">
"""
        
        # Add metric cards
        for metric_name, stats in metric_status.items():
            status_class = self._get_metric_status_class(metric_name, stats['current'])
            html += f"""
        <div class="metric-card">
            <div class="metric-title">{metric_name.replace('_', ' ').title()}</div>
            <div class="metric-value {status_class}">{stats['current']:.2f}</div>
            <div class="metric-details">
                Avg: {stats['average']:.2f} | Min: {stats['min']:.2f} | Max: {stats['max']:.2f}<br>
                Samples: {stats['count']} (last 5 minutes)
            </div>
        </div>
"""
        
        html += """
    </div>
    
    <div class="alerts-section">
        <h2>🚨 Active Alerts</h2>
"""
        
        if self.active_alerts:
            for alert in self.active_alerts.values():
                html += f"""
        <div class="alert-item">
            <strong>{alert.severity.value.upper()}</strong>: {alert.message}<br>
            <small>Customer Impact: ~{alert.customer_impact_estimated} customers | {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</small>
        </div>
"""
        else:
            html += "<p>No active alerts ✅</p>"
        
        html += f"""
    </div>
    
    <div class="timestamp">
        Last updated: {current_time.strftime('%Y-%m-%d %H:%M:%S')}
    </div>
</body>
</html>
"""
        
        return html
    
    def _get_metric_status_class(self, metric_name: str, current_value: float) -> str:
        """Get CSS class based on metric thresholds"""
        # Find relevant threshold
        metric_type = MetricType(metric_name)
        threshold = next((t for t in self.sla_thresholds if t.metric_type == metric_type), None)
        
        if not threshold:
            return "status-good"
        
        if threshold.comparison == "less_than":
            if current_value >= threshold.threshold_value * 0.9:  # Within 90% of threshold
                return "status-critical" if current_value >= threshold.threshold_value else "status-warning"
        elif threshold.comparison == "greater_than":
            if current_value <= threshold.threshold_value * 1.1:  # Within 110% of threshold
                return "status-critical" if current_value <= threshold.threshold_value else "status-warning"
        
        return "status-good"
    
    async def _export_metrics(self):
        """Export metrics to file"""
        export_path = Path(self.config["metrics_export_path"])
        export_path.mkdir(parents=True, exist_ok=True)
        
        # Export recent metrics as JSON
        current_time = datetime.now()
        recent_metrics = [
            {
                "metric_type": m.metric_type.value,
                "value": m.value,
                "timestamp": m.timestamp.isoformat(),
                "customer_id": m.customer_id,
                "additional_context": m.additional_context
            }
            for m in self.metrics_buffer
            if (current_time - m.timestamp).total_seconds() <= 3600  # Last hour
        ]
        
        metrics_file = export_path / f"metrics_{current_time.strftime('%Y%m%d_%H%M')}.json"
        with open(metrics_file, 'w') as f:
            json.dump(recent_metrics, f, indent=2)
        
        # Clean up old metric files (keep last 24 hours)
        cutoff_time = current_time - timedelta(hours=24)
        for old_file in export_path.glob("metrics_*.json"):
            try:
                file_time = datetime.strptime(old_file.stem.split('_')[1] + old_file.stem.split('_')[2], '%Y%m%d%H%M')
                if file_time < cutoff_time:
                    old_file.unlink()
            except (ValueError, IndexError):
                pass  # Skip files that don't match expected format
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get current performance summary"""
        current_time = datetime.now()
        recent_metrics = [
            m for m in self.metrics_buffer
            if (current_time - m.timestamp).total_seconds() <= 300  # Last 5 minutes
        ]
        
        summary = {
            "timestamp": current_time.isoformat(),
            "monitoring_status": "active" if self.is_monitoring else "stopped",
            "total_metrics_collected": len(self.metrics_buffer),
            "active_alerts_count": len(self.active_alerts),
            "recent_metrics_count": len(recent_metrics),
            "metric_types": {}
        }
        
        # Summarize by metric type
        for metric_type in MetricType:
            type_metrics = [m for m in recent_metrics if m.metric_type == metric_type]
            if type_metrics:
                values = [m.value for m in type_metrics]
                summary["metric_types"][metric_type.value] = {
                    "count": len(values),
                    "current": values[-1],
                    "average": statistics.mean(values),
                    "min": min(values),
                    "max": max(values)
                }
        
        return summary

# Alert callback functions
async def console_alert_callback(alert: PerformanceAlert):
    """Simple console alert callback"""
    severity_emoji = {
        AlertSeverity.LOW: "💡",
        AlertSeverity.MEDIUM: "⚠️", 
        AlertSeverity.HIGH: "🚨",
        AlertSeverity.CRITICAL: "🔥"
    }
    
    print(f"\n{severity_emoji[alert.severity]} PERFORMANCE ALERT")
    print(f"Time: {alert.timestamp}")
    print(f"Metric: {alert.metric_type.value}")
    print(f"Message: {alert.message}")
    print(f"Customer Impact: ~{alert.customer_impact_estimated} customers")
    
    if alert.resolution_suggestions:
        print("Resolution Suggestions:")
        for i, suggestion in enumerate(alert.resolution_suggestions, 1):
            print(f"  {i}. {suggestion}")
    print("-" * 50)

async def log_alert_callback(alert: PerformanceAlert):
    """Log-based alert callback"""
    log_level = {
        AlertSeverity.LOW: logging.INFO,
        AlertSeverity.MEDIUM: logging.WARNING,
        AlertSeverity.HIGH: logging.ERROR,
        AlertSeverity.CRITICAL: logging.CRITICAL
    }
    
    logger.log(log_level[alert.severity], 
              f"Performance Alert [{alert.severity.value}]: {alert.message} "
              f"(Customer Impact: {alert.customer_impact_estimated})")

# Factory function for easy setup
def create_performance_monitor(config: Dict[str, Any] = None) -> PerformanceMonitor:
    """Create a performance monitor with default alert callbacks"""
    monitor = PerformanceMonitor(config)
    monitor.add_alert_callback(console_alert_callback)
    monitor.add_alert_callback(log_alert_callback)
    return monitor