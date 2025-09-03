"""
Memory Performance Monitor - <500ms SLA Enforcement and Monitoring

Monitors and enforces memory performance SLA requirements:
- Memory recall: <500ms for semantic search (Mem0)
- Working memory: <2ms for immediate context (Redis) 
- Persistent queries: <100ms for audit history (PostgreSQL)

Provides real-time alerting, performance metrics, and optimization recommendations.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Deque
import json

logger = logging.getLogger(__name__)


class MemoryPerformanceMonitor:
    """
    Performance monitoring and SLA enforcement for memory operations.
    
    Tracks latency, throughput, and error rates across all memory layers
    with real-time alerting for SLA violations.
    """
    
    def __init__(self, customer_id: str, config: Optional[Dict[str, Any]] = None):
        """
        Initialize performance monitor for customer.
        
        Args:
            customer_id: Customer identifier
            config: Optional performance configuration override
        """
        self.customer_id = customer_id
        self.config = config or self._default_performance_config()
        
        # Performance metrics storage
        self.metrics = {
            "operation_counts": defaultdict(int),
            "latency_history": defaultdict(lambda: deque(maxlen=1000)),  # Last 1000 operations
            "error_counts": defaultdict(int),
            "sla_violations": defaultdict(int),
            "throughput_samples": defaultdict(lambda: deque(maxlen=100))  # Last 100 samples
        }
        
        # Real-time performance state
        self.performance_state = {
            "current_alert_level": "normal",  # normal, warning, critical
            "consecutive_violations": 0,
            "last_alert_time": None,
            "performance_degradation_detected": False
        }
        
        # SLA targets
        self.sla_targets = {
            "mem0_search": 0.5,      # 500ms
            "redis_access": 0.002,   # 2ms
            "postgres_query": 0.1,   # 100ms
            "hybrid_retrieval": 1.0,  # 1s for combined operations
            "memory_storage": 0.3    # 300ms for storage operations
        }
        
        logger.info(f"Initialized performance monitor for customer {customer_id}")
    
    def _default_performance_config(self) -> Dict[str, Any]:
        """Default performance monitoring configuration"""
        return {
            "monitoring_enabled": True,
            "alerting_enabled": True,
            "metrics_retention_hours": 24,
            "violation_threshold": 3,  # Consecutive violations before alert
            "alert_cooldown_minutes": 15,
            "performance_sampling_rate": 1.0,  # Monitor 100% of operations
            "metrics_export": {
                "enabled": True,
                "format": "prometheus",
                "endpoint": "/metrics"
            }
        }
    
    async def track_memory_operation(self, operation: str, latency: float, success: bool, 
                                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Track memory operation performance and check SLA compliance.
        
        Args:
            operation: Operation type (mem0_search, redis_access, postgres_query, etc.)
            latency: Operation latency in seconds
            success: Whether operation was successful
            metadata: Optional operation metadata
            
        Returns:
            Performance tracking results with alerts if any
        """
        tracking_timestamp = datetime.utcnow()
        
        # Update metrics
        self.metrics["operation_counts"][operation] += 1
        self.metrics["latency_history"][operation].append(latency)
        
        if not success:
            self.metrics["error_counts"][operation] += 1
        
        # Check SLA compliance
        sla_target = self.sla_targets.get(operation, 1.0)  # Default 1s if not specified
        sla_violation = latency > sla_target
        
        if sla_violation:
            self.metrics["sla_violations"][operation] += 1
            self.performance_state["consecutive_violations"] += 1
        else:
            self.performance_state["consecutive_violations"] = 0
        
        # Update throughput sampling
        current_minute = int(time.time() // 60)
        self.metrics["throughput_samples"][operation].append({
            "timestamp": current_minute,
            "latency": latency,
            "success": success
        })
        
        # Generate alerts if needed
        alert_result = await self._check_performance_alerts(operation, latency, sla_violation)
        
        # Performance tracking result
        tracking_result = {
            "timestamp": tracking_timestamp.isoformat(),
            "customer_id": self.customer_id,
            "operation": operation,
            "latency_seconds": latency,
            "success": success,
            "sla_target_seconds": sla_target,
            "sla_violation": sla_violation,
            "consecutive_violations": self.performance_state["consecutive_violations"],
            "alert_generated": alert_result.get("alert_generated", False),
            "current_alert_level": self.performance_state["current_alert_level"]
        }
        
        # Add metadata if provided
        if metadata:
            tracking_result["metadata"] = metadata
        
        # Log performance issues
        if sla_violation:
            logger.warning(
                f"SLA VIOLATION - Customer {self.customer_id}: {operation} took {latency:.3f}s "
                f"(target: {sla_target:.3f}s)"
            )
        
        return tracking_result
    
    async def _check_performance_alerts(self, operation: str, latency: float, sla_violation: bool) -> Dict[str, Any]:
        """Check if performance alerts should be generated"""
        alert_result = {"alert_generated": False, "alert_type": None, "alert_message": None}
        
        if not self.config.get("alerting_enabled", True):
            return alert_result
        
        current_time = datetime.utcnow()
        
        # Check alert cooldown
        if (self.performance_state["last_alert_time"] and 
            current_time - self.performance_state["last_alert_time"] < 
            timedelta(minutes=self.config.get("alert_cooldown_minutes", 15))):
            return alert_result
        
        # Critical alert: Multiple consecutive violations
        if self.performance_state["consecutive_violations"] >= self.config.get("violation_threshold", 3):
            alert_result.update({
                "alert_generated": True,
                "alert_type": "critical",
                "alert_message": (
                    f"CRITICAL: Customer {self.customer_id} - {self.performance_state['consecutive_violations']} "
                    f"consecutive SLA violations for {operation}. Latest: {latency:.3f}s"
                )
            })
            
            self.performance_state["current_alert_level"] = "critical"
            self.performance_state["last_alert_time"] = current_time
            
            await self._send_alert(alert_result)
            
        # Warning alert: Significant performance degradation
        elif sla_violation and latency > self.sla_targets.get(operation, 1.0) * 2:
            alert_result.update({
                "alert_generated": True,
                "alert_type": "warning", 
                "alert_message": (
                    f"WARNING: Customer {self.customer_id} - Significant performance degradation "
                    f"for {operation}: {latency:.3f}s (>2x SLA target)"
                )
            })
            
            self.performance_state["current_alert_level"] = "warning"
            self.performance_state["last_alert_time"] = current_time
            
            await self._send_alert(alert_result)
        
        return alert_result
    
    async def _send_alert(self, alert_result: Dict[str, Any]) -> None:
        """Send performance alert (placeholder for integration with monitoring systems)"""
        # In production, this would integrate with:
        # - PagerDuty/Slack for critical alerts
        # - Prometheus AlertManager
        # - Custom monitoring dashboards
        
        alert_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "customer_id": self.customer_id,
            "severity": alert_result["alert_type"],
            "message": alert_result["alert_message"],
            "metrics_snapshot": self.get_current_performance_snapshot()
        }
        
        # Log alert (in production, send to external systems)
        if alert_result["alert_type"] == "critical":
            logger.critical(f"🚨 PERFORMANCE ALERT: {alert_result['alert_message']}")
        else:
            logger.warning(f"⚠️ PERFORMANCE WARNING: {alert_result['alert_message']}")
        
        # Store alert history
        if not hasattr(self, 'alert_history'):
            self.alert_history = deque(maxlen=100)
        
        self.alert_history.append(alert_data)
    
    def get_current_performance_snapshot(self) -> Dict[str, Any]:
        """Get current performance metrics snapshot"""
        snapshot_time = datetime.utcnow()
        
        # Calculate performance statistics
        performance_stats = {}
        
        for operation in self.sla_targets.keys():
            if operation in self.metrics["latency_history"]:
                latencies = list(self.metrics["latency_history"][operation])
                if latencies:
                    performance_stats[operation] = {
                        "count": len(latencies),
                        "avg_latency": sum(latencies) / len(latencies),
                        "p95_latency": self._calculate_percentile(latencies, 95),
                        "p99_latency": self._calculate_percentile(latencies, 99),
                        "max_latency": max(latencies),
                        "sla_target": self.sla_targets[operation],
                        "sla_violations": self.metrics["sla_violations"][operation],
                        "error_count": self.metrics["error_counts"][operation],
                        "success_rate": (
                            (len(latencies) - self.metrics["error_counts"][operation]) / len(latencies) * 100
                            if len(latencies) > 0 else 0
                        )
                    }
        
        return {
            "snapshot_timestamp": snapshot_time.isoformat(),
            "customer_id": self.customer_id,
            "current_alert_level": self.performance_state["current_alert_level"],
            "consecutive_violations": self.performance_state["consecutive_violations"],
            "operation_statistics": performance_stats,
            "total_operations": sum(self.metrics["operation_counts"].values()),
            "total_errors": sum(self.metrics["error_counts"].values()),
            "total_sla_violations": sum(self.metrics["sla_violations"].values())
        }
    
    def _calculate_percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile from data list"""
        if not data:
            return 0.0
        
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    async def generate_performance_report(self, time_window_hours: int = 24) -> Dict[str, Any]:
        """
        Generate comprehensive performance report for time window.
        
        Args:
            time_window_hours: Time window for report generation
            
        Returns:
            Detailed performance analysis report
        """
        report_time = datetime.utcnow()
        window_start = report_time - timedelta(hours=time_window_hours)
        
        # Get current snapshot
        current_snapshot = self.get_current_performance_snapshot()
        
        # Calculate SLA compliance
        sla_compliance = {}
        total_operations = 0
        total_violations = 0
        
        for operation, target in self.sla_targets.items():
            op_count = self.metrics["operation_counts"][operation]
            op_violations = self.metrics["sla_violations"][operation]
            
            if op_count > 0:
                compliance_rate = (op_count - op_violations) / op_count * 100
                sla_compliance[operation] = {
                    "target_seconds": target,
                    "total_operations": op_count,
                    "violations": op_violations,
                    "compliance_rate_percent": compliance_rate,
                    "average_latency": (
                        sum(self.metrics["latency_history"][operation]) / 
                        len(self.metrics["latency_history"][operation])
                        if self.metrics["latency_history"][operation] else 0
                    )
                }
                
                total_operations += op_count
                total_violations += op_violations
        
        overall_compliance = (
            (total_operations - total_violations) / total_operations * 100
            if total_operations > 0 else 100
        )
        
        # Performance recommendations
        recommendations = await self._generate_performance_recommendations(current_snapshot)
        
        return {
            "report_timestamp": report_time.isoformat(),
            "customer_id": self.customer_id,
            "time_window_hours": time_window_hours,
            "window_start": window_start.isoformat(),
            
            # Overall performance
            "overall_sla_compliance_percent": overall_compliance,
            "total_operations": total_operations,
            "total_sla_violations": total_violations,
            "current_alert_level": self.performance_state["current_alert_level"],
            
            # Operation-specific performance
            "operation_sla_compliance": sla_compliance,
            "current_performance_snapshot": current_snapshot,
            
            # Performance insights
            "performance_recommendations": recommendations,
            "alert_history": list(getattr(self, 'alert_history', [])),
            
            # Trending analysis
            "performance_trend": self._analyze_performance_trend(),
            
            # Configuration
            "monitoring_config": self.config,
            "sla_targets": self.sla_targets
        }
    
    async def _generate_performance_recommendations(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate performance optimization recommendations"""
        recommendations = []
        
        operation_stats = snapshot.get("operation_statistics", {})
        
        for operation, stats in operation_stats.items():
            # High latency recommendation
            if stats["avg_latency"] > self.sla_targets[operation] * 0.8:  # >80% of SLA target
                recommendations.append({
                    "priority": "high",
                    "operation": operation,
                    "issue": "High average latency",
                    "current_value": f"{stats['avg_latency']:.3f}s",
                    "target_value": f"{self.sla_targets[operation]:.3f}s",
                    "recommendation": self._get_latency_optimization_advice(operation),
                    "impact": "SLA violation risk"
                })
            
            # High error rate recommendation
            if stats["success_rate"] < 95.0:  # <95% success rate
                recommendations.append({
                    "priority": "critical",
                    "operation": operation,
                    "issue": "High error rate",
                    "current_value": f"{stats['success_rate']:.1f}%",
                    "target_value": "99.0%",
                    "recommendation": "Investigate error causes and implement retry mechanisms",
                    "impact": "System reliability"
                })
            
            # P99 latency recommendation
            if stats["p99_latency"] > self.sla_targets[operation] * 3:  # P99 >3x SLA target
                recommendations.append({
                    "priority": "medium",
                    "operation": operation,
                    "issue": "High P99 latency",
                    "current_value": f"{stats['p99_latency']:.3f}s",
                    "target_value": f"{self.sla_targets[operation] * 2:.3f}s",
                    "recommendation": "Investigate outlier performance cases and optimize slow queries",
                    "impact": "Worst-case user experience"
                })
        
        return recommendations
    
    def _get_latency_optimization_advice(self, operation: str) -> str:
        """Get operation-specific optimization advice"""
        advice_map = {
            "mem0_search": "Consider indexing optimization, reduce embedding dimensions, or implement caching",
            "redis_access": "Check Redis memory usage, network latency, and connection pooling",
            "postgres_query": "Optimize queries with indexes, consider connection pooling, or implement read replicas",
            "hybrid_retrieval": "Implement parallel retrieval and optimize slower components",
            "memory_storage": "Optimize batch operations and consider async processing"
        }
        
        return advice_map.get(operation, "Review operation implementation and consider caching strategies")
    
    def _analyze_performance_trend(self) -> Dict[str, Any]:
        """Analyze performance trends over time"""
        # Simplified trend analysis - in production would use more sophisticated algorithms
        trend_data = {
            "overall_trend": "stable",  # improving, stable, degrading
            "trend_confidence": "medium",
            "trend_analysis": "Insufficient data for comprehensive trend analysis"
        }
        
        # Check if we have enough data points
        total_samples = sum(len(history) for history in self.metrics["latency_history"].values())
        
        if total_samples > 100:
            # Calculate recent vs historical performance
            recent_violations = self.performance_state["consecutive_violations"]
            
            if recent_violations > 5:
                trend_data["overall_trend"] = "degrading"
                trend_data["trend_analysis"] = f"Performance degrading with {recent_violations} consecutive violations"
            elif recent_violations == 0:
                trend_data["overall_trend"] = "stable"
                trend_data["trend_analysis"] = "Performance stable within SLA targets"
        
        return trend_data
    
    async def reset_metrics(self, operation: Optional[str] = None) -> None:
        """Reset performance metrics (for testing or maintenance)"""
        if operation:
            # Reset specific operation metrics
            self.metrics["operation_counts"][operation] = 0
            self.metrics["latency_history"][operation].clear()
            self.metrics["error_counts"][operation] = 0
            self.metrics["sla_violations"][operation] = 0
            logger.info(f"Reset performance metrics for operation {operation}")
        else:
            # Reset all metrics
            for metric_dict in self.metrics.values():
                if isinstance(metric_dict, defaultdict):
                    metric_dict.clear()
                elif hasattr(metric_dict, 'clear'):
                    metric_dict.clear()
            
            self.performance_state["consecutive_violations"] = 0
            self.performance_state["current_alert_level"] = "normal"
            logger.info(f"Reset all performance metrics for customer {self.customer_id}")
    
    def export_metrics_prometheus(self) -> str:
        """Export metrics in Prometheus format"""
        metrics_lines = []
        timestamp = int(time.time() * 1000)
        
        # Operation counts
        for operation, count in self.metrics["operation_counts"].items():
            metrics_lines.append(
                f'memory_operation_total{{customer_id="{self.customer_id}",operation="{operation}"}} {count} {timestamp}'
            )
        
        # Average latencies
        for operation, latencies in self.metrics["latency_history"].items():
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                metrics_lines.append(
                    f'memory_operation_latency_seconds{{customer_id="{self.customer_id}",operation="{operation}"}} {avg_latency} {timestamp}'
                )
        
        # SLA violations
        for operation, violations in self.metrics["sla_violations"].items():
            metrics_lines.append(
                f'memory_sla_violations_total{{customer_id="{self.customer_id}",operation="{operation}"}} {violations} {timestamp}'
            )
        
        return '\n'.join(metrics_lines)


class GlobalPerformanceMonitor:
    """
    Global performance monitor for tracking system-wide memory performance
    across all customers and identifying system-level issues.
    """
    
    def __init__(self):
        self.customer_monitors: Dict[str, MemoryPerformanceMonitor] = {}
        self.global_metrics = {
            "system_performance": defaultdict(list),
            "customer_count": 0,
            "total_operations": 0,
            "system_alerts": deque(maxlen=1000)
        }
        
        logger.info("Initialized global performance monitor")
    
    def get_customer_monitor(self, customer_id: str) -> MemoryPerformanceMonitor:
        """Get or create performance monitor for customer"""
        if customer_id not in self.customer_monitors:
            self.customer_monitors[customer_id] = MemoryPerformanceMonitor(customer_id)
            self.global_metrics["customer_count"] = len(self.customer_monitors)
            logger.info(f"Created performance monitor for customer {customer_id}")
        
        return self.customer_monitors[customer_id]
    
    async def generate_system_performance_report(self) -> Dict[str, Any]:
        """Generate system-wide performance report"""
        report_time = datetime.utcnow()
        
        # Aggregate customer performance data
        system_stats = {
            "total_customers": len(self.customer_monitors),
            "total_operations": 0,
            "total_sla_violations": 0,
            "customers_with_violations": 0,
            "average_system_latency": {},
            "system_sla_compliance": 0.0
        }
        
        operation_aggregates = defaultdict(list)
        
        for customer_id, monitor in self.customer_monitors.items():
            snapshot = monitor.get_current_performance_snapshot()
            
            for operation, stats in snapshot.get("operation_statistics", {}).items():
                operation_aggregates[operation].append(stats)
                system_stats["total_operations"] += stats["count"]
                system_stats["total_sla_violations"] += stats["sla_violations"]
        
        # Calculate system averages
        for operation, stats_list in operation_aggregates.items():
            if stats_list:
                avg_latency = sum(s["avg_latency"] for s in stats_list) / len(stats_list)
                system_stats["average_system_latency"][operation] = avg_latency
        
        # Calculate overall SLA compliance
        if system_stats["total_operations"] > 0:
            system_stats["system_sla_compliance"] = (
                (system_stats["total_operations"] - system_stats["total_sla_violations"]) / 
                system_stats["total_operations"] * 100
            )
        
        return {
            "report_timestamp": report_time.isoformat(),
            "system_statistics": system_stats,
            "customer_performance_summary": {
                customer_id: monitor.get_current_performance_snapshot()
                for customer_id, monitor in self.customer_monitors.items()
            },
            "system_recommendations": await self._generate_system_recommendations(system_stats)
        }
    
    async def _generate_system_recommendations(self, system_stats: Dict[str, Any]) -> List[str]:
        """Generate system-level performance recommendations"""
        recommendations = []
        
        if system_stats["system_sla_compliance"] < 95.0:
            recommendations.append(
                f"System SLA compliance ({system_stats['system_sla_compliance']:.1f}%) below target (95%). "
                "Consider infrastructure scaling or optimization."
            )
        
        if system_stats["total_customers"] > 100:
            recommendations.append(
                "High customer count detected. Monitor resource utilization and consider horizontal scaling."
            )
        
        return recommendations


# Global instance for system-wide monitoring
global_monitor = GlobalPerformanceMonitor()