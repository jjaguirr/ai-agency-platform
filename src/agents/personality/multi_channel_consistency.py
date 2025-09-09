"""
Multi-Channel Personality Consistency Manager
Ensures >90% personality consistency across email, WhatsApp, voice channels per Phase-2-PRD requirements
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

from .personality_engine import (
    PersonalityEngine, CommunicationChannel, PersonalityTone, 
    PersonalityTransformationResult, PersonalityConsistencyReport
)
from .personality_database import PersonalityDatabase

logger = logging.getLogger(__name__)


@dataclass
class ChannelConsistencyMetrics:
    """Consistency metrics for a specific communication channel"""
    channel: CommunicationChannel
    total_transformations: int
    avg_consistency_score: float
    consistency_trend: List[float]  # Last 10 consistency scores
    personality_indicators_frequency: Dict[str, int]
    tone_distribution: Dict[PersonalityTone, int]
    avg_transformation_time_ms: int
    consistency_issues: List[str]
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CrossChannelAnalysis:
    """Analysis of personality consistency across multiple channels"""
    customer_id: str
    analysis_period_hours: int
    overall_consistency_score: float
    channel_metrics: Dict[CommunicationChannel, ChannelConsistencyMetrics]
    cross_channel_variance: float  # How much channels differ from each other
    consistency_alerts: List[str]
    improvement_recommendations: List[str]
    performance_summary: Dict[str, Any]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MultiChannelConsistencyManager:
    """
    Manager for ensuring personality consistency across all communication channels.
    
    Monitors and maintains >90% personality consistency requirement from Phase-2-PRD
    across email, WhatsApp, voice, and other communication channels.
    """
    
    def __init__(
        self,
        personality_engine: PersonalityEngine,
        personality_database: PersonalityDatabase,
        consistency_target: float = 0.9,  # 90% consistency target from PRD
        monitoring_enabled: bool = True
    ):
        """
        Initialize multi-channel consistency manager.
        
        Args:
            personality_engine: PersonalityEngine instance
            personality_database: PersonalityDatabase instance  
            consistency_target: Target consistency score (default 0.9 = 90%)
            monitoring_enabled: Enable real-time consistency monitoring
        """
        self.personality_engine = personality_engine
        self.personality_database = personality_database
        self.consistency_target = consistency_target
        self.monitoring_enabled = monitoring_enabled
        
        # Real-time consistency tracking
        self.channel_buffers: Dict[str, Dict[CommunicationChannel, List[PersonalityTransformationResult]]] = defaultdict(lambda: defaultdict(list))
        self.consistency_alerts: Dict[str, List[str]] = defaultdict(list)
        self.buffer_max_size = 20  # Keep last 20 transformations per channel per customer
        
        # Performance tracking
        self.consistency_checks_performed = 0
        self.alerts_generated = 0
        self.improvements_suggested = 0
        
        logger.info(f"MultiChannelConsistencyManager initialized with target: {consistency_target}")
    
    async def track_transformation(
        self,
        customer_id: str,
        transformation_result: PersonalityTransformationResult
    ) -> Optional[Dict[str, Any]]:
        """
        Track a transformation result and check for consistency issues.
        
        Args:
            customer_id: Customer identifier
            transformation_result: Result from personality transformation
            
        Returns:
            Optional consistency alert if issues detected
        """
        try:
            # Add to channel buffer
            channel_buffer = self.channel_buffers[customer_id][transformation_result.channel]
            channel_buffer.append(transformation_result)
            
            # Maintain buffer size
            if len(channel_buffer) > self.buffer_max_size:
                channel_buffer.pop(0)  # Remove oldest
            
            # Store in database for historical analysis
            await self.personality_database.store_transformation_result(transformation_result, customer_id)
            
            # Check for immediate consistency issues
            if self.monitoring_enabled:
                consistency_alert = await self._check_real_time_consistency(
                    customer_id, transformation_result.channel
                )
                
                if consistency_alert:
                    self.consistency_alerts[customer_id].append(consistency_alert)
                    self.alerts_generated += 1
                    logger.warning(f"Consistency alert for {customer_id}: {consistency_alert}")
                
                return consistency_alert
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to track transformation: {e}")
            return None
    
    async def analyze_customer_consistency(
        self,
        customer_id: str,
        analysis_period_hours: int = 24,
        include_detailed_analysis: bool = True
    ) -> CrossChannelAnalysis:
        """
        Comprehensive consistency analysis for a customer across all channels.
        
        Args:
            customer_id: Customer identifier
            analysis_period_hours: Hours of history to analyze
            include_detailed_analysis: Whether to include detailed channel breakdowns
            
        Returns:
            CrossChannelAnalysis with comprehensive consistency metrics
        """
        try:
            self.consistency_checks_performed += 1
            start_time = time.time()
            
            # Get transformation history from database
            all_transformations = await self.personality_database.get_transformation_history(
                customer_id=customer_id,
                hours_back=analysis_period_hours,
                limit=500  # Sufficient for comprehensive analysis
            )
            
            if not all_transformations:
                return CrossChannelAnalysis(
                    customer_id=customer_id,
                    analysis_period_hours=analysis_period_hours,
                    overall_consistency_score=1.0,  # Perfect score with no data
                    channel_metrics={},
                    cross_channel_variance=0.0,
                    consistency_alerts=[],
                    improvement_recommendations=[],
                    performance_summary={'total_transformations': 0}
                )
            
            # Group transformations by channel
            channel_groups = defaultdict(list)
            for transformation in all_transformations:
                channel = CommunicationChannel(transformation['channel'])
                channel_groups[channel].append(transformation)
            
            # Analyze each channel
            channel_metrics = {}
            channel_consistency_scores = []
            
            for channel, transformations in channel_groups.items():
                metrics = await self._analyze_channel_consistency(
                    channel, transformations, include_detailed_analysis
                )
                channel_metrics[channel] = metrics
                channel_consistency_scores.append(metrics.avg_consistency_score)
            
            # Calculate overall consistency and variance
            overall_consistency = statistics.mean(channel_consistency_scores) if channel_consistency_scores else 1.0
            cross_channel_variance = statistics.stdev(channel_consistency_scores) if len(channel_consistency_scores) > 1 else 0.0
            
            # Generate alerts and recommendations
            consistency_alerts = self._generate_consistency_alerts(
                customer_id, overall_consistency, channel_metrics, cross_channel_variance
            )
            
            improvement_recommendations = self._generate_improvement_recommendations(
                overall_consistency, channel_metrics, cross_channel_variance
            )
            
            # Performance summary
            analysis_time = int((time.time() - start_time) * 1000)
            performance_summary = {
                'total_transformations': len(all_transformations),
                'channels_analyzed': len(channel_groups),
                'analysis_time_ms': analysis_time,
                'meets_consistency_target': overall_consistency >= self.consistency_target,
                'target_consistency': self.consistency_target
            }
            
            return CrossChannelAnalysis(
                customer_id=customer_id,
                analysis_period_hours=analysis_period_hours,
                overall_consistency_score=overall_consistency,
                channel_metrics=channel_metrics,
                cross_channel_variance=cross_channel_variance,
                consistency_alerts=consistency_alerts,
                improvement_recommendations=improvement_recommendations,
                performance_summary=performance_summary
            )
            
        except Exception as e:
            logger.error(f"Customer consistency analysis failed: {e}")
            return CrossChannelAnalysis(
                customer_id=customer_id,
                analysis_period_hours=analysis_period_hours,
                overall_consistency_score=0.0,
                channel_metrics={},
                cross_channel_variance=0.0,
                consistency_alerts=[f"Analysis failed: {str(e)}"],
                improvement_recommendations=["Fix consistency analysis system"],
                performance_summary={'error': str(e)}
            )
    
    async def optimize_channel_consistency(
        self,
        customer_id: str,
        target_channel: CommunicationChannel,
        reference_channels: Optional[List[CommunicationChannel]] = None
    ) -> Dict[str, Any]:
        """
        Optimize consistency for a specific channel based on successful patterns from other channels.
        
        Args:
            customer_id: Customer identifier
            target_channel: Channel to optimize
            reference_channels: Channels to use as reference (or all others if None)
            
        Returns:
            Dictionary with optimization results and recommendations
        """
        try:
            # Analyze current state
            analysis = await self.analyze_customer_consistency(customer_id)
            
            if target_channel not in analysis.channel_metrics:
                return {
                    'success': False,
                    'error': f"No data found for target channel {target_channel.value}"
                }
            
            target_metrics = analysis.channel_metrics[target_channel]
            
            # Find best-performing reference channels
            if reference_channels is None:
                reference_channels = [
                    ch for ch in analysis.channel_metrics.keys() 
                    if ch != target_channel
                ]
            
            # Get successful patterns from reference channels
            successful_patterns = []
            reference_consistency_scores = []
            
            for ref_channel in reference_channels:
                if ref_channel in analysis.channel_metrics:
                    ref_metrics = analysis.channel_metrics[ref_channel]
                    reference_consistency_scores.append(ref_metrics.avg_consistency_score)
                    
                    # Extract successful personality indicators
                    for indicator, frequency in ref_metrics.personality_indicators_frequency.items():
                        if frequency > 2:  # Used multiple times
                            successful_patterns.append(indicator)
            
            # Generate optimization recommendations
            optimization_recommendations = []
            
            if successful_patterns:
                optimization_recommendations.append(
                    f"Incorporate successful patterns from other channels: {', '.join(set(successful_patterns[:5]))}"
                )
            
            if reference_consistency_scores:
                best_ref_score = max(reference_consistency_scores)
                if best_ref_score > target_metrics.avg_consistency_score:
                    optimization_recommendations.append(
                        f"Target consistency improvement from {target_metrics.avg_consistency_score:.2f} to {best_ref_score:.2f}"
                    )
            
            if target_metrics.avg_transformation_time_ms > 500:
                optimization_recommendations.append(
                    f"Optimize transformation speed from {target_metrics.avg_transformation_time_ms}ms to <500ms"
                )
            
            # Update customer personality profile with successful patterns
            if successful_patterns:
                current_profile = await self.personality_database.load_personality_profile(customer_id)
                if current_profile:
                    await self.personality_engine.update_personality_profile(
                        customer_id=customer_id,
                        preferences={f"{target_channel.value}_optimization": True},
                        successful_patterns=successful_patterns
                    )
            
            self.improvements_suggested += 1
            
            return {
                'success': True,
                'target_channel': target_channel.value,
                'current_consistency_score': target_metrics.avg_consistency_score,
                'consistency_target': self.consistency_target,
                'optimization_recommendations': optimization_recommendations,
                'successful_patterns_identified': len(set(successful_patterns)),
                'reference_channels_analyzed': len(reference_channels)
            }
            
        except Exception as e:
            logger.error(f"Channel consistency optimization failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def generate_consistency_report(
        self,
        customer_id: str,
        include_performance_metrics: bool = True,
        include_recommendations: bool = True
    ) -> PersonalityConsistencyReport:
        """
        Generate comprehensive consistency report for customer.
        
        Args:
            customer_id: Customer identifier  
            include_performance_metrics: Include detailed performance data
            include_recommendations: Include improvement recommendations
            
        Returns:
            PersonalityConsistencyReport with full analysis
        """
        try:
            # Get comprehensive analysis
            analysis = await self.analyze_customer_consistency(customer_id)
            
            # Convert to PersonalityConsistencyReport format
            channel_scores = {
                channel: metrics.avg_consistency_score
                for channel, metrics in analysis.channel_metrics.items()
            }
            
            # Get sample transformations
            sample_transformations = {}
            for channel, metrics in analysis.channel_metrics.items():
                # Get most recent transformation for this channel
                recent_transformations = await self.personality_database.get_transformation_history(
                    customer_id=customer_id,
                    channel=channel,
                    limit=1
                )
                
                if recent_transformations:
                    transformation_data = recent_transformations[0]
                    sample_transformations[channel.value] = PersonalityTransformationResult(
                        transformed_content=transformation_data['transformed_content'],
                        original_content=transformation_data['original_content'],
                        personality_tone=PersonalityTone(transformation_data['personality_tone']),
                        channel=channel,
                        transformation_time_ms=transformation_data['transformation_time_ms'],
                        consistency_score=transformation_data['consistency_score'],
                        premium_casual_indicators=transformation_data['premium_casual_indicators'],
                        timestamp=transformation_data['created_at']
                    )
            
            return PersonalityConsistencyReport(
                customer_id=customer_id,
                overall_consistency_score=analysis.overall_consistency_score,
                channel_scores=channel_scores,
                consistency_issues=analysis.consistency_alerts,
                improvement_suggestions=analysis.improvement_recommendations if include_recommendations else [],
                sample_transformations=sample_transformations
            )
            
        except Exception as e:
            logger.error(f"Consistency report generation failed: {e}")
            return PersonalityConsistencyReport(
                customer_id=customer_id,
                overall_consistency_score=0.0,
                channel_scores={},
                consistency_issues=[f"Report generation failed: {str(e)}"],
                improvement_suggestions=[],
                sample_transformations={}
            )
    
    async def _analyze_channel_consistency(
        self,
        channel: CommunicationChannel,
        transformations: List[Dict[str, Any]],
        include_detailed_analysis: bool
    ) -> ChannelConsistencyMetrics:
        """Analyze consistency metrics for a specific channel"""
        
        if not transformations:
            return ChannelConsistencyMetrics(
                channel=channel,
                total_transformations=0,
                avg_consistency_score=1.0,
                consistency_trend=[],
                personality_indicators_frequency={},
                tone_distribution={},
                avg_transformation_time_ms=0,
                consistency_issues=[]
            )
        
        # Calculate basic metrics
        consistency_scores = [t['consistency_score'] for t in transformations if t['consistency_score'] is not None]
        avg_consistency = statistics.mean(consistency_scores) if consistency_scores else 0.0
        
        transformation_times = [t['transformation_time_ms'] for t in transformations]
        avg_transformation_time = int(statistics.mean(transformation_times)) if transformation_times else 0
        
        # Consistency trend (last 10 scores)
        consistency_trend = consistency_scores[-10:] if consistency_scores else []
        
        # Analyze personality indicators
        indicator_frequency = defaultdict(int)
        tone_distribution = defaultdict(int)
        
        for transformation in transformations:
            # Count personality indicators
            for indicator in transformation['premium_casual_indicators']:
                indicator_frequency[indicator] += 1
            
            # Count tone distribution
            tone = PersonalityTone(transformation['personality_tone'])
            tone_distribution[tone] += 1
        
        # Identify consistency issues
        consistency_issues = []
        
        if avg_consistency < self.consistency_target:
            consistency_issues.append(
                f"Average consistency ({avg_consistency:.2f}) below target ({self.consistency_target})"
            )
        
        if avg_transformation_time > 500:
            consistency_issues.append(
                f"Average transformation time ({avg_transformation_time}ms) exceeds 500ms SLA"
            )
        
        if len(consistency_trend) > 3:
            # Check for declining consistency trend
            recent_avg = statistics.mean(consistency_trend[-3:])
            earlier_avg = statistics.mean(consistency_trend[:3])
            if recent_avg < earlier_avg - 0.1:  # 10% decline
                consistency_issues.append("Consistency declining over recent transformations")
        
        return ChannelConsistencyMetrics(
            channel=channel,
            total_transformations=len(transformations),
            avg_consistency_score=avg_consistency,
            consistency_trend=consistency_trend,
            personality_indicators_frequency=dict(indicator_frequency),
            tone_distribution=dict(tone_distribution),
            avg_transformation_time_ms=avg_transformation_time,
            consistency_issues=consistency_issues
        )
    
    async def _check_real_time_consistency(
        self,
        customer_id: str,
        channel: CommunicationChannel
    ) -> Optional[str]:
        """Check for real-time consistency issues"""
        
        try:
            channel_buffer = self.channel_buffers[customer_id][channel]
            
            if len(channel_buffer) < 3:
                return None  # Need at least 3 transformations to assess consistency
            
            # Check recent consistency scores
            recent_scores = [t.consistency_score for t in channel_buffer[-3:] if t.consistency_score is not None]
            
            if recent_scores:
                recent_avg = statistics.mean(recent_scores)
                
                if recent_avg < self.consistency_target:
                    return f"Recent consistency ({recent_avg:.2f}) below target for {channel.value}"
                
                # Check for sudden drops
                if len(recent_scores) >= 3:
                    if recent_scores[-1] < recent_scores[0] - 0.2:  # 20% drop
                        return f"Consistency drop detected in {channel.value}: {recent_scores[0]:.2f} → {recent_scores[-1]:.2f}"
            
            return None
            
        except Exception as e:
            logger.warning(f"Real-time consistency check failed: {e}")
            return None
    
    def _generate_consistency_alerts(
        self,
        customer_id: str,
        overall_consistency: float,
        channel_metrics: Dict[CommunicationChannel, ChannelConsistencyMetrics],
        cross_channel_variance: float
    ) -> List[str]:
        """Generate consistency alerts based on analysis results"""
        
        alerts = []
        
        # Overall consistency alert
        if overall_consistency < self.consistency_target:
            alerts.append(
                f"Overall consistency ({overall_consistency:.2f}) below target ({self.consistency_target})"
            )
        
        # Cross-channel variance alert
        if cross_channel_variance > 0.15:  # High variance between channels
            alerts.append(
                f"High variance between channels ({cross_channel_variance:.2f}), inconsistent personality"
            )
        
        # Channel-specific alerts
        for channel, metrics in channel_metrics.items():
            if metrics.consistency_issues:
                alerts.extend([
                    f"{channel.value}: {issue}" for issue in metrics.consistency_issues
                ])
        
        # Performance alerts
        slow_channels = [
            channel.value for channel, metrics in channel_metrics.items()
            if metrics.avg_transformation_time_ms > 500
        ]
        
        if slow_channels:
            alerts.append(
                f"Performance SLA violation in channels: {', '.join(slow_channels)}"
            )
        
        return alerts
    
    def _generate_improvement_recommendations(
        self,
        overall_consistency: float,
        channel_metrics: Dict[CommunicationChannel, ChannelConsistencyMetrics],
        cross_channel_variance: float
    ) -> List[str]:
        """Generate improvement recommendations"""
        
        recommendations = []
        
        # Overall consistency recommendations
        if overall_consistency < self.consistency_target:
            recommendations.append(
                f"Focus on improving consistency from {overall_consistency:.2f} to {self.consistency_target}"
            )
        
        # Cross-channel consistency recommendations
        if cross_channel_variance > 0.1:
            best_channel = max(
                channel_metrics.items(),
                key=lambda x: x[1].avg_consistency_score
            )
            recommendations.append(
                f"Use {best_channel[0].value} channel patterns as reference for other channels"
            )
        
        # Channel-specific recommendations
        performance_issues = [
            channel.value for channel, metrics in channel_metrics.items()
            if metrics.avg_transformation_time_ms > 500
        ]
        
        if performance_issues:
            recommendations.append(
                f"Optimize transformation performance for: {', '.join(performance_issues)}"
            )
        
        # Pattern recommendations
        all_successful_patterns = set()
        for metrics in channel_metrics.values():
            for pattern, freq in metrics.personality_indicators_frequency.items():
                if freq > 3:  # Frequently used patterns
                    all_successful_patterns.add(pattern)
        
        if all_successful_patterns:
            recommendations.append(
                f"Standardize successful patterns across channels: {', '.join(list(all_successful_patterns)[:3])}"
            )
        
        if not recommendations:
            recommendations.append("Maintain current consistency standards")
        
        return recommendations
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics"""
        
        return {
            'consistency_checks_performed': self.consistency_checks_performed,
            'alerts_generated': self.alerts_generated,
            'improvements_suggested': self.improvements_suggested,
            'customers_monitored': len(self.channel_buffers),
            'total_channels_tracked': sum(
                len(channels) for channels in self.channel_buffers.values()
            ),
            'consistency_target': self.consistency_target,
            'monitoring_enabled': self.monitoring_enabled
        }