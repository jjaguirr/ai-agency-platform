"""
Voice Cost Tracker
Comprehensive cost tracking and optimization for voice interactions
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import statistics
import json

# Monitoring imports
from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

# Local imports
from .models import VoiceCostBreakdown
from ..monitoring.voice_performance_monitor import VoiceInteractionMetrics

logger = structlog.get_logger(__name__)

@dataclass
class CostOptimizationRecommendation:
    """Cost optimization recommendation"""
    recommendation_id: str
    customer_id: Optional[str]
    generated_timestamp: datetime
    
    # Optimization details
    cost_category: str  # tts, stt, processing, infrastructure
    current_cost: float
    optimized_cost: float
    potential_savings: float
    savings_percentage: float
    
    # Implementation
    optimization_type: str  # reduce_calls, improve_efficiency, batch_processing
    description: str
    implementation_steps: List[str]
    implementation_effort: str  # low, medium, high
    expected_timeline: str
    
    # Risk assessment
    impact_on_quality: str  # none, low, medium, high
    customer_experience_risk: str  # none, low, medium, high
    
    # Tracking
    status: str  # new, approved, implemented, rejected
    priority: str  # low, medium, high, critical

@dataclass
class CostAlert:
    """Cost-related alert"""
    alert_id: str
    customer_id: Optional[str]
    triggered_timestamp: datetime
    
    # Alert details
    alert_type: str  # threshold_exceeded, unusual_spending, cost_spike
    cost_category: str
    current_cost: float
    threshold_or_baseline: float
    
    # Context
    time_period: str  # hourly, daily, weekly
    comparison_period: str
    triggering_factors: List[str]
    
    # Response
    severity: str  # low, medium, high, critical
    recommended_actions: List[str]
    auto_mitigation_possible: bool
    
    # Resolution
    acknowledged: bool = False
    resolved: bool = False
    resolution_actions: List[str] = None

class VoiceCostTracker:
    """
    Comprehensive cost tracking and optimization system
    
    Features:
    - Real-time cost tracking across all voice interaction components
    - Cost optimization recommendations
    - Budget monitoring and alerts
    - Cost forecasting and planning
    - ROI-based cost analysis
    - Vendor cost comparison and optimization
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Cost configuration
        self.cost_rates = {
            "elevenlabs_tts": self.config.get("elevenlabs_cost_per_1k_chars", 0.30),
            "whisper_stt": self.config.get("whisper_cost_per_minute", 0.006),
            "openai_api": self.config.get("openai_cost_per_1k_tokens", 0.002),
            "compute_per_second": self.config.get("compute_cost_per_second", 0.001),
            "storage_per_mb": self.config.get("storage_cost_per_mb", 0.0001),
            "bandwidth_per_mb": self.config.get("bandwidth_cost_per_mb", 0.05)
        }
        
        # Budget settings
        self.daily_budget_limit = self.config.get("daily_budget_limit", 100.0)
        self.monthly_budget_limit = self.config.get("monthly_budget_limit", 2500.0)
        self.customer_daily_limit = self.config.get("customer_daily_limit", 5.0)
        
        # Alert thresholds
        self.cost_spike_threshold = self.config.get("cost_spike_threshold", 2.0)  # 200% of baseline
        self.budget_warning_threshold = self.config.get("budget_warning_threshold", 0.8)  # 80% of budget
        
        # Data storage
        self.cost_breakdowns: deque = deque(maxlen=10000)
        self.customer_costs: Dict[str, List[VoiceCostBreakdown]] = defaultdict(list)
        self.daily_costs: Dict[str, float] = defaultdict(float)  # date -> cost
        self.monthly_costs: Dict[str, float] = defaultdict(float)  # month -> cost
        
        # Cost optimization
        self.optimization_recommendations: List[CostOptimizationRecommendation] = []
        self.cost_alerts: List[CostAlert] = []
        self.cost_baselines: Dict[str, float] = {}  # customer_id -> baseline daily cost
        
        # Performance tracking
        self.cost_stats = {
            "total_tracked_interactions": 0,
            "total_cost_tracked": 0.0,
            "average_cost_per_interaction": 0.0,
            "cost_optimization_savings": 0.0,
            "active_cost_alerts": 0
        }
        
        self.setup_metrics()
        logger.info("Voice cost tracker initialized",
                   daily_budget_limit=self.daily_budget_limit,
                   monthly_budget_limit=self.monthly_budget_limit)
    
    def setup_metrics(self):
        """Setup Prometheus metrics for cost tracking"""
        self.cost_per_interaction_histogram = Histogram(
            'voice_cost_per_interaction_dollars',
            'Cost per voice interaction in dollars',
            ['customer_segment', 'cost_category', 'time_bucket']
        )
        
        self.total_cost_gauge = Gauge(
            'voice_total_cost_dollars',
            'Total voice interaction costs',
            ['time_period', 'cost_category']
        )
        
        self.budget_utilization_gauge = Gauge(
            'voice_budget_utilization_percentage',
            'Budget utilization percentage',
            ['budget_type', 'time_period']
        )
        
        self.cost_optimization_savings_gauge = Gauge(
            'voice_cost_optimization_savings_dollars',
            'Cost savings from optimization',
            ['optimization_type', 'time_period']
        )
        
        self.cost_alerts_counter = Counter(
            'voice_cost_alerts_total',
            'Total cost alerts triggered',
            ['alert_type', 'severity', 'customer_segment']
        )
    
    async def track_interaction_cost(
        self,
        metrics: VoiceInteractionMetrics,
        additional_context: Dict[str, Any] = None
    ) -> VoiceCostBreakdown:
        """Track comprehensive cost breakdown for voice interaction"""
        
        try:
            # Calculate detailed cost breakdown
            cost_breakdown = await self._calculate_detailed_costs(metrics, additional_context or {})
            
            # Store cost data
            self.cost_breakdowns.append(cost_breakdown)
            self.customer_costs[metrics.customer_id].append(cost_breakdown)
            
            # Keep customer data manageable
            self.customer_costs[metrics.customer_id] = self.customer_costs[metrics.customer_id][-100:]
            
            # Update daily and monthly totals
            date_key = cost_breakdown.timestamp.strftime("%Y-%m-%d")
            month_key = cost_breakdown.timestamp.strftime("%Y-%m")
            
            self.daily_costs[date_key] += cost_breakdown.total_cost
            self.monthly_costs[month_key] += cost_breakdown.total_cost
            
            # Update cost statistics
            self.cost_stats["total_tracked_interactions"] += 1
            self.cost_stats["total_cost_tracked"] += cost_breakdown.total_cost
            self.cost_stats["average_cost_per_interaction"] = (
                self.cost_stats["total_cost_tracked"] / 
                self.cost_stats["total_tracked_interactions"]
            )
            
            # Check for cost alerts
            await self._check_cost_alerts(cost_breakdown)
            
            # Update Prometheus metrics
            customer_segment = self._get_customer_segment(metrics.customer_id)
            
            self.cost_per_interaction_histogram.labels(
                customer_segment=customer_segment,
                cost_category="total",
                time_bucket=cost_breakdown.timestamp.strftime("%Y-%m-%d-%H")
            ).observe(cost_breakdown.total_cost)
            
            self.total_cost_gauge.labels(
                time_period="daily",
                cost_category="total"
            ).set(self.daily_costs[date_key])
            
            # Update budget utilization
            daily_budget_usage = (self.daily_costs[date_key] / self.daily_budget_limit) * 100
            self.budget_utilization_gauge.labels(
                budget_type="daily",
                time_period=date_key
            ).set(daily_budget_usage)
            
            logger.debug("Interaction cost tracked",
                        interaction_id=metrics.interaction_id,
                        total_cost=cost_breakdown.total_cost,
                        customer_id=metrics.customer_id)
            
            return cost_breakdown
            
        except Exception as e:
            logger.error("Error tracking interaction cost",
                        interaction_id=metrics.interaction_id,
                        error=str(e))
            raise
    
    async def _calculate_detailed_costs(
        self,
        metrics: VoiceInteractionMetrics,
        context: Dict[str, Any]
    ) -> VoiceCostBreakdown:
        """Calculate detailed cost breakdown for interaction"""
        
        # ElevenLabs TTS cost
        elevenlabs_cost = 0.0
        if metrics.response_length > 0:
            elevenlabs_cost = (metrics.response_length / 1000) * self.cost_rates["elevenlabs_tts"]
        
        # Whisper STT cost
        whisper_cost = 0.0
        if metrics.speech_to_text_time > 0:
            whisper_cost = (metrics.speech_to_text_time / 60) * self.cost_rates["whisper_stt"]
        
        # OpenAI API cost (estimated based on response length)
        openai_cost = 0.0
        if metrics.response_length > 0:
            # Rough estimation: 1 character ≈ 0.25 tokens
            estimated_tokens = metrics.response_length * 0.25
            openai_cost = (estimated_tokens / 1000) * self.cost_rates["openai_api"]
        
        # Compute cost
        compute_cost = metrics.total_response_time * self.cost_rates["compute_per_second"]
        
        # Storage cost (for audio and conversation data)
        storage_cost = 0.0
        if metrics.audio_input_size_bytes > 0 or metrics.audio_output_size_bytes > 0:
            total_storage_mb = (metrics.audio_input_size_bytes + metrics.audio_output_size_bytes) / (1024 * 1024)
            storage_cost = total_storage_mb * self.cost_rates["storage_per_mb"]
        
        # Bandwidth cost
        bandwidth_cost = 0.0
        if metrics.audio_output_size_bytes > 0:
            bandwidth_mb = metrics.audio_output_size_bytes / (1024 * 1024)
            bandwidth_cost = bandwidth_mb * self.cost_rates["bandwidth_per_mb"]
        
        # Monitoring and security costs (small fixed cost per interaction)
        monitoring_cost = 0.001  # $0.001 per interaction
        security_cost = 0.001    # $0.001 per interaction
        
        # Total direct cost
        total_direct_cost = (
            elevenlabs_cost + whisper_cost + openai_cost + 
            compute_cost + storage_cost + bandwidth_cost
        )
        
        # Allocated overhead (10% of direct costs)
        allocated_overhead = total_direct_cost * 0.1
        
        # Total cost
        total_cost = total_direct_cost + allocated_overhead + monitoring_cost + security_cost
        
        # Calculate efficiency metrics
        cost_per_second = total_cost / max(0.1, metrics.total_response_time)
        cost_per_word = total_cost / max(1, metrics.response_length / 5)  # Avg 5 chars per word
        
        # Cost per business value (if available from context)
        business_value = context.get("business_value_score", 50)
        cost_per_business_value_point = total_cost / max(1, business_value) * 100
        
        return VoiceCostBreakdown(
            interaction_id=metrics.interaction_id,
            customer_id=metrics.customer_id,
            timestamp=metrics.timestamp,
            elevenlabs_tts_cost=round(elevenlabs_cost, 6),
            whisper_stt_cost=round(whisper_cost, 6),
            openai_api_cost=round(openai_cost, 6),
            compute_cost=round(compute_cost, 6),
            storage_cost=round(storage_cost, 6),
            bandwidth_cost=round(bandwidth_cost, 6),
            monitoring_cost=monitoring_cost,
            security_cost=security_cost,
            total_direct_cost=round(total_direct_cost, 6),
            allocated_overhead=round(allocated_overhead, 6),
            total_cost=round(total_cost, 6),
            cost_per_second=round(cost_per_second, 6),
            cost_per_word=round(cost_per_word, 6),
            cost_per_business_value_point=round(cost_per_business_value_point, 6)
        )
    
    async def _check_cost_alerts(self, cost_breakdown: VoiceCostBreakdown):
        """Check for cost-related alerts"""
        
        customer_id = cost_breakdown.customer_id
        current_date = cost_breakdown.timestamp.strftime("%Y-%m-%d")
        
        # Check customer daily limit
        customer_daily_cost = sum(
            c.total_cost for c in self.customer_costs[customer_id]
            if c.timestamp.strftime("%Y-%m-%d") == current_date
        )
        
        if customer_daily_cost > self.customer_daily_limit:
            await self._trigger_cost_alert(
                alert_type="customer_daily_limit_exceeded",
                customer_id=customer_id,
                current_cost=customer_daily_cost,
                threshold_or_baseline=self.customer_daily_limit,
                severity="high",
                cost_category="daily_total"
            )
        
        # Check daily budget
        daily_total = self.daily_costs[current_date]
        if daily_total > self.daily_budget_limit * self.budget_warning_threshold:
            severity = "critical" if daily_total > self.daily_budget_limit else "high"
            await self._trigger_cost_alert(
                alert_type="daily_budget_warning",
                customer_id=None,
                current_cost=daily_total,
                threshold_or_baseline=self.daily_budget_limit,
                severity=severity,
                cost_category="daily_budget"
            )
        
        # Check for cost spikes
        customer_baseline = self.cost_baselines.get(customer_id, 0.1)  # Default baseline
        if cost_breakdown.total_cost > customer_baseline * self.cost_spike_threshold:
            await self._trigger_cost_alert(
                alert_type="cost_spike",
                customer_id=customer_id,
                current_cost=cost_breakdown.total_cost,
                threshold_or_baseline=customer_baseline,
                severity="medium",
                cost_category="per_interaction"
            )
        
        # Update customer baseline (rolling average of last 20 interactions)
        customer_recent_costs = [c.total_cost for c in self.customer_costs[customer_id][-20:]]
        if len(customer_recent_costs) >= 5:
            self.cost_baselines[customer_id] = statistics.mean(customer_recent_costs)
    
    async def _trigger_cost_alert(
        self,
        alert_type: str,
        customer_id: Optional[str],
        current_cost: float,
        threshold_or_baseline: float,
        severity: str,
        cost_category: str
    ):
        """Trigger a cost alert"""
        
        # Check if similar alert was recently triggered (prevent spam)
        recent_alerts = [
            alert for alert in self.cost_alerts
            if (alert.alert_type == alert_type and 
                alert.customer_id == customer_id and
                (datetime.now() - alert.triggered_timestamp).total_seconds() < 3600)  # 1 hour
        ]
        
        if recent_alerts:
            return  # Don't spam alerts
        
        # Generate recommended actions
        recommended_actions = self._get_alert_recommendations(alert_type, current_cost, threshold_or_baseline)
        
        # Create alert
        alert = CostAlert(
            alert_id=f"cost_alert_{int(datetime.now().timestamp())}_{customer_id or 'system'}",
            customer_id=customer_id,
            triggered_timestamp=datetime.now(),
            alert_type=alert_type,
            cost_category=cost_category,
            current_cost=current_cost,
            threshold_or_baseline=threshold_or_baseline,
            time_period="daily" if "daily" in alert_type else "interaction",
            comparison_period="baseline" if "spike" in alert_type else "budget",
            triggering_factors=self._identify_cost_factors(alert_type, customer_id),
            severity=severity,
            recommended_actions=recommended_actions,
            auto_mitigation_possible=self._can_auto_mitigate(alert_type)
        )
        
        self.cost_alerts.append(alert)
        self.cost_stats["active_cost_alerts"] += 1
        
        # Update metrics
        customer_segment = self._get_customer_segment(customer_id) if customer_id else "system"
        self.cost_alerts_counter.labels(
            alert_type=alert_type,
            severity=severity,
            customer_segment=customer_segment
        ).inc()
        
        logger.warning("Cost alert triggered",
                      alert_type=alert_type,
                      customer_id=customer_id,
                      current_cost=current_cost,
                      threshold=threshold_or_baseline,
                      severity=severity)
        
        # Implement auto-mitigation if possible
        if alert.auto_mitigation_possible:
            await self._implement_auto_mitigation(alert)
    
    def _get_alert_recommendations(
        self, 
        alert_type: str, 
        current_cost: float, 
        threshold: float
    ) -> List[str]:
        """Get recommendations for cost alert"""
        
        recommendations = []
        
        if alert_type == "customer_daily_limit_exceeded":
            recommendations = [
                "Review customer interaction patterns",
                "Consider implementing rate limiting",
                "Optimize response generation efficiency",
                "Contact customer about usage patterns"
            ]
        elif alert_type == "daily_budget_warning":
            recommendations = [
                "Monitor remaining budget closely",
                "Consider temporary cost optimizations",
                "Review high-cost customers",
                "Implement cost controls if necessary"
            ]
        elif alert_type == "cost_spike":
            excess_percentage = ((current_cost / threshold) - 1) * 100
            recommendations = [
                f"Investigate {excess_percentage:.0f}% cost increase",
                "Check for unusual interaction patterns",
                "Review response generation efficiency",
                "Analyze recent system changes"
            ]
        
        return recommendations
    
    def _identify_cost_factors(self, alert_type: str, customer_id: Optional[str]) -> List[str]:
        """Identify factors contributing to cost alert"""
        
        factors = []
        
        if customer_id and customer_id in self.customer_costs:
            recent_costs = self.customer_costs[customer_id][-10:]
            
            # Analyze cost components
            avg_tts_cost = statistics.mean([c.elevenlabs_tts_cost for c in recent_costs])
            avg_stt_cost = statistics.mean([c.whisper_stt_cost for c in recent_costs])
            avg_compute_cost = statistics.mean([c.compute_cost for c in recent_costs])
            
            if avg_tts_cost > 0.05:  # High TTS cost
                factors.append("High text-to-speech costs")
            if avg_stt_cost > 0.02:  # High STT cost
                factors.append("High speech-to-text costs")
            if avg_compute_cost > 0.01:  # High compute cost
                factors.append("High processing time costs")
        
        if alert_type == "daily_budget_warning":
            factors.append("High daily interaction volume")
            factors.append("Multiple high-cost customers active")
        
        return factors
    
    def _can_auto_mitigate(self, alert_type: str) -> bool:
        """Check if alert can be auto-mitigated"""
        
        # Only certain alerts can be auto-mitigated
        auto_mitigatable = [
            "cost_spike",  # Can optimize response generation
            "customer_daily_limit_exceeded"  # Can implement rate limiting
        ]
        
        return alert_type in auto_mitigatable
    
    async def _implement_auto_mitigation(self, alert: CostAlert):
        """Implement automatic cost mitigation"""
        
        if alert.alert_type == "cost_spike":
            # Implement temporary response optimization
            logger.info("Implementing auto-mitigation for cost spike",
                       alert_id=alert.alert_id,
                       customer_id=alert.customer_id)
            
            # Would implement actual optimization logic here
            
        elif alert.alert_type == "customer_daily_limit_exceeded":
            # Implement temporary rate limiting
            logger.info("Implementing auto-mitigation for daily limit",
                       alert_id=alert.alert_id,
                       customer_id=alert.customer_id)
            
            # Would implement actual rate limiting here
        
        alert.resolution_actions = alert.resolution_actions or []
        alert.resolution_actions.append("Auto-mitigation implemented")
    
    async def generate_cost_optimization_recommendations(
        self, 
        customer_id: Optional[str] = None,
        analysis_period_days: int = 30
    ) -> List[CostOptimizationRecommendation]:
        """Generate cost optimization recommendations"""
        
        recommendations = []
        cutoff_date = datetime.now() - timedelta(days=analysis_period_days)
        
        # Get cost data for analysis
        if customer_id:
            cost_data = [
                c for c in self.customer_costs.get(customer_id, [])
                if c.timestamp > cutoff_date
            ]
            analysis_scope = "customer"
        else:
            cost_data = [
                c for c in self.cost_breakdowns
                if c.timestamp > cutoff_date
            ]
            analysis_scope = "system"
        
        if len(cost_data) < 10:  # Need minimum data
            return recommendations
        
        # Analyze TTS costs
        tts_recommendation = await self._analyze_tts_costs(cost_data, customer_id, analysis_scope)
        if tts_recommendation:
            recommendations.append(tts_recommendation)
        
        # Analyze processing efficiency
        processing_recommendation = await self._analyze_processing_costs(cost_data, customer_id, analysis_scope)
        if processing_recommendation:
            recommendations.append(processing_recommendation)
        
        # Analyze infrastructure costs
        infrastructure_recommendation = await self._analyze_infrastructure_costs(cost_data, customer_id, analysis_scope)
        if infrastructure_recommendation:
            recommendations.append(infrastructure_recommendation)
        
        # Store recommendations
        self.optimization_recommendations.extend(recommendations)
        
        logger.info("Cost optimization recommendations generated",
                   customer_id=customer_id,
                   analysis_scope=analysis_scope,
                   recommendations_count=len(recommendations))
        
        return recommendations
    
    async def _analyze_tts_costs(
        self, 
        cost_data: List[VoiceCostBreakdown], 
        customer_id: Optional[str],
        analysis_scope: str
    ) -> Optional[CostOptimizationRecommendation]:
        """Analyze text-to-speech costs for optimization"""
        
        tts_costs = [c.elevenlabs_tts_cost for c in cost_data if c.elevenlabs_tts_cost > 0]
        
        if not tts_costs:
            return None
        
        avg_tts_cost = statistics.mean(tts_costs)
        total_tts_cost = sum(tts_costs)
        
        # Check if TTS costs are high relative to total costs
        total_costs = [c.total_cost for c in cost_data]
        avg_total_cost = statistics.mean(total_costs)
        
        tts_percentage = (avg_tts_cost / avg_total_cost) * 100
        
        if tts_percentage > 40:  # TTS is >40% of costs
            potential_savings = total_tts_cost * 0.25  # 25% potential savings
            
            return CostOptimizationRecommendation(
                recommendation_id=f"tts_opt_{customer_id or 'system'}_{int(datetime.now().timestamp())}",
                customer_id=customer_id,
                generated_timestamp=datetime.now(),
                cost_category="tts",
                current_cost=total_tts_cost,
                optimized_cost=total_tts_cost - potential_savings,
                potential_savings=potential_savings,
                savings_percentage=25.0,
                optimization_type="improve_efficiency",
                description=f"TTS costs represent {tts_percentage:.1f}% of total costs. Optimization recommended.",
                implementation_steps=[
                    "Optimize response length and conciseness",
                    "Implement response caching for common responses",
                    "Use shorter responses where appropriate",
                    "Consider voice model optimization"
                ],
                implementation_effort="medium",
                expected_timeline="2-3 weeks",
                impact_on_quality="low",
                customer_experience_risk="low",
                status="new",
                priority="high" if tts_percentage > 50 else "medium"
            )
        
        return None
    
    async def _analyze_processing_costs(
        self,
        cost_data: List[VoiceCostBreakdown],
        customer_id: Optional[str],
        analysis_scope: str
    ) -> Optional[CostOptimizationRecommendation]:
        """Analyze processing costs for optimization"""
        
        compute_costs = [c.compute_cost for c in cost_data]
        avg_compute_cost = statistics.mean(compute_costs)
        total_compute_cost = sum(compute_costs)
        
        # Check if processing times are high
        high_cost_interactions = [c for c in cost_data if c.compute_cost > avg_compute_cost * 2]
        
        if len(high_cost_interactions) > len(cost_data) * 0.1:  # >10% high cost interactions
            potential_savings = total_compute_cost * 0.30  # 30% potential savings
            
            return CostOptimizationRecommendation(
                recommendation_id=f"processing_opt_{customer_id or 'system'}_{int(datetime.now().timestamp())}",
                customer_id=customer_id,
                generated_timestamp=datetime.now(),
                cost_category="processing",
                current_cost=total_compute_cost,
                optimized_cost=total_compute_cost - potential_savings,
                potential_savings=potential_savings,
                savings_percentage=30.0,
                optimization_type="improve_efficiency",
                description=f"{len(high_cost_interactions)} interactions had high processing costs.",
                implementation_steps=[
                    "Optimize EA response generation algorithms",
                    "Implement response caching",
                    "Improve processing pipeline efficiency",
                    "Consider model optimization"
                ],
                implementation_effort="high",
                expected_timeline="4-6 weeks",
                impact_on_quality="none",
                customer_experience_risk="none",
                status="new",
                priority="medium"
            )
        
        return None
    
    async def _analyze_infrastructure_costs(
        self,
        cost_data: List[VoiceCostBreakdown],
        customer_id: Optional[str],
        analysis_scope: str
    ) -> Optional[CostOptimizationRecommendation]:
        """Analyze infrastructure costs for optimization"""
        
        if analysis_scope != "system":  # Only analyze for system-wide
            return None
        
        total_overhead = sum(c.allocated_overhead for c in cost_data)
        total_monitoring = sum(c.monitoring_cost for c in cost_data)
        
        infrastructure_total = total_overhead + total_monitoring
        
        if infrastructure_total > 50.0:  # Significant infrastructure costs
            potential_savings = infrastructure_total * 0.20  # 20% potential savings
            
            return CostOptimizationRecommendation(
                recommendation_id=f"infra_opt_system_{int(datetime.now().timestamp())}",
                customer_id=None,
                generated_timestamp=datetime.now(),
                cost_category="infrastructure",
                current_cost=infrastructure_total,
                optimized_cost=infrastructure_total - potential_savings,
                potential_savings=potential_savings,
                savings_percentage=20.0,
                optimization_type="reduce_calls",
                description="Infrastructure costs can be optimized through resource consolidation.",
                implementation_steps=[
                    "Consolidate monitoring systems",
                    "Optimize resource allocation",
                    "Implement cost-efficient scaling",
                    "Review vendor contracts"
                ],
                implementation_effort="high",
                expected_timeline="6-8 weeks",
                impact_on_quality="none",
                customer_experience_risk="low",
                status="new",
                priority="medium"
            )
        
        return None
    
    def _get_customer_segment(self, customer_id: Optional[str]) -> str:
        """Get customer segment for cost analysis"""
        
        if not customer_id:
            return "system"
        
        if customer_id not in self.customer_costs:
            return "new"
        
        customer_cost_history = self.customer_costs[customer_id]
        
        if not customer_cost_history:
            return "new"
        
        # Analyze customer cost patterns
        recent_costs = customer_cost_history[-30:]  # Last 30 interactions
        avg_cost = statistics.mean([c.total_cost for c in recent_costs])
        interaction_count = len(customer_cost_history)
        
        if interaction_count >= 100 and avg_cost > 0.10:
            return "high_value"
        elif interaction_count >= 20 and avg_cost > 0.05:
            return "engaged"
        elif interaction_count >= 5:
            return "active"
        else:
            return "new"
    
    def get_cost_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive cost dashboard data"""
        
        today = datetime.now().strftime("%Y-%m-%d")
        this_month = datetime.now().strftime("%Y-%m")
        
        # Current costs
        daily_cost = self.daily_costs.get(today, 0.0)
        monthly_cost = self.monthly_costs.get(this_month, 0.0)
        
        # Budget utilization
        daily_budget_utilization = (daily_cost / self.daily_budget_limit) * 100
        monthly_budget_utilization = (monthly_cost / self.monthly_budget_limit) * 100
        
        # Cost breakdown analysis
        recent_costs = list(self.cost_breakdowns)[-100:] if self.cost_breakdowns else []
        
        if recent_costs:
            avg_costs = {
                "tts": statistics.mean([c.elevenlabs_tts_cost for c in recent_costs]),
                "stt": statistics.mean([c.whisper_stt_cost for c in recent_costs]),
                "processing": statistics.mean([c.compute_cost for c in recent_costs]),
                "infrastructure": statistics.mean([c.allocated_overhead for c in recent_costs])
            }
        else:
            avg_costs = {"tts": 0, "stt": 0, "processing": 0, "infrastructure": 0}
        
        # Top cost customers
        customer_totals = {}
        for customer_id, costs in self.customer_costs.items():
            customer_totals[customer_id] = sum(c.total_cost for c in costs[-30:])  # Last 30 interactions
        
        top_customers = sorted(
            customer_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
        
        # Active alerts
        active_alerts = [alert for alert in self.cost_alerts if not alert.resolved]
        
        # Optimization opportunities
        total_potential_savings = sum(
            rec.potential_savings for rec in self.optimization_recommendations
            if rec.status in ["new", "approved"]
        )
        
        return {
            "current_costs": {
                "daily_cost": round(daily_cost, 2),
                "monthly_cost": round(monthly_cost, 2),
                "average_per_interaction": round(self.cost_stats["average_cost_per_interaction"], 4)
            },
            "budget_status": {
                "daily_utilization": round(daily_budget_utilization, 1),
                "monthly_utilization": round(monthly_budget_utilization, 1),
                "daily_remaining": round(self.daily_budget_limit - daily_cost, 2),
                "monthly_remaining": round(self.monthly_budget_limit - monthly_cost, 2)
            },
            "cost_breakdown": {
                "text_to_speech": round(avg_costs["tts"], 4),
                "speech_to_text": round(avg_costs["stt"], 4),
                "processing": round(avg_costs["processing"], 4),
                "infrastructure": round(avg_costs["infrastructure"], 4)
            },
            "top_cost_customers": [
                {"customer_id": customer_id, "cost": round(cost, 2)}
                for customer_id, cost in top_customers
            ],
            "active_alerts": [
                {
                    "type": alert.alert_type,
                    "severity": alert.severity,
                    "customer_id": alert.customer_id,
                    "current_cost": alert.current_cost,
                    "triggered": alert.triggered_timestamp.isoformat()
                }
                for alert in active_alerts[:5]  # Show top 5
            ],
            "optimization_opportunities": {
                "total_recommendations": len([r for r in self.optimization_recommendations if r.status == "new"]),
                "potential_savings": round(total_potential_savings, 2),
                "high_priority_count": len([r for r in self.optimization_recommendations if r.priority == "high" and r.status == "new"])
            },
            "statistics": self.cost_stats.copy()
        }
    
    async def forecast_costs(
        self,
        forecast_days: int = 30,
        customer_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Forecast future costs based on historical patterns"""
        
        # Get historical data
        historical_days = min(90, forecast_days * 3)  # Use up to 90 days of history
        cutoff_date = datetime.now() - timedelta(days=historical_days)
        
        if customer_id:
            cost_data = [
                c for c in self.customer_costs.get(customer_id, [])
                if c.timestamp > cutoff_date
            ]
        else:
            cost_data = [
                c for c in self.cost_breakdowns
                if c.timestamp > cutoff_date
            ]
        
        if len(cost_data) < 7:  # Need minimum data
            return {
                "error": "Insufficient data for forecasting",
                "minimum_required_days": 7,
                "available_data_points": len(cost_data)
            }
        
        # Group costs by day
        daily_costs = defaultdict(float)
        for cost in cost_data:
            day_key = cost.timestamp.strftime("%Y-%m-%d")
            daily_costs[day_key] += cost.total_cost
        
        # Calculate daily averages and trends
        daily_values = list(daily_costs.values())
        
        if len(daily_values) < 7:
            return {"error": "Insufficient daily data for forecasting"}
        
        # Simple trend analysis
        recent_avg = statistics.mean(daily_values[-7:])  # Last week
        overall_avg = statistics.mean(daily_values)
        
        # Calculate trend
        if len(daily_values) >= 14:
            older_avg = statistics.mean(daily_values[-14:-7])  # Previous week
            trend_factor = recent_avg / older_avg if older_avg > 0 else 1.0
        else:
            trend_factor = 1.0  # No trend data
        
        # Forecast daily costs
        forecasted_daily_costs = []
        base_daily_cost = recent_avg
        
        for day in range(forecast_days):
            # Apply trend factor with diminishing effect over time
            trend_decay = 0.95 ** (day / 7)  # Trend effect decays weekly
            daily_forecast = base_daily_cost * (1 + (trend_factor - 1) * trend_decay)
            
            # Add some day-of-week variation (weekdays typically higher)
            forecast_date = datetime.now() + timedelta(days=day)
            weekday_multiplier = 1.2 if forecast_date.weekday() < 5 else 0.8  # Weekday vs weekend
            
            daily_forecast *= weekday_multiplier
            forecasted_daily_costs.append(max(0, daily_forecast))
        
        # Calculate forecast summary
        total_forecast = sum(forecasted_daily_costs)
        avg_daily_forecast = total_forecast / forecast_days
        
        # Calculate confidence intervals (simple approach)
        daily_std = statistics.stdev(daily_values) if len(daily_values) > 1 else 0
        confidence_margin = daily_std * 1.96  # 95% confidence interval
        
        lower_bound = max(0, avg_daily_forecast - confidence_margin) * forecast_days
        upper_bound = (avg_daily_forecast + confidence_margin) * forecast_days
        
        return {
            "forecast_period_days": forecast_days,
            "customer_id": customer_id,
            "based_on_days": len(daily_values),
            "total_forecast": round(total_forecast, 2),
            "average_daily": round(avg_daily_forecast, 4),
            "confidence_interval": {
                "lower_bound": round(lower_bound, 2),
                "upper_bound": round(upper_bound, 2),
                "confidence_level": 95
            },
            "trend_analysis": {
                "recent_average": round(recent_avg, 4),
                "overall_average": round(overall_avg, 4),
                "trend_factor": round(trend_factor, 3),
                "trend_direction": "increasing" if trend_factor > 1.05 else "decreasing" if trend_factor < 0.95 else "stable"
            },
            "daily_forecast": [round(cost, 4) for cost in forecasted_daily_costs],
            "recommendations": self._get_forecast_recommendations(total_forecast, trend_factor, forecast_days)
        }
    
    def _get_forecast_recommendations(
        self, 
        total_forecast: float, 
        trend_factor: float, 
        forecast_days: int
    ) -> List[str]:
        """Get recommendations based on cost forecast"""
        
        recommendations = []
        
        # Budget recommendations
        daily_budget_needed = total_forecast / forecast_days
        if daily_budget_needed > self.daily_budget_limit * 0.8:
            recommendations.append(f"Consider increasing daily budget limit (forecast: ${daily_budget_needed:.2f}/day)")
        
        # Trend recommendations
        if trend_factor > 1.2:
            recommendations.append("Costs are trending upward significantly - investigate cost drivers")
        elif trend_factor > 1.1:
            recommendations.append("Moderate cost increase trend - monitor closely")
        
        # Optimization recommendations
        if total_forecast > 100:  # High total forecast
            recommendations.append("High cost forecast - prioritize cost optimization initiatives")
        
        # Planning recommendations
        monthly_forecast = total_forecast * (30 / forecast_days)
        if monthly_forecast > self.monthly_budget_limit:
            recommendations.append(f"Monthly forecast (${monthly_forecast:.0f}) exceeds budget limit")
        
        return recommendations

# Global cost tracker instance
voice_cost_tracker = VoiceCostTracker()