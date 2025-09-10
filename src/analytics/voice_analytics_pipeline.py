"""
Voice Analytics Pipeline
Real-time processing and analytics for voice interactions
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import json
import statistics
import uuid
from enum import Enum

# Analytics imports
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# Monitoring imports
from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

# Local imports
from ..monitoring.voice_performance_monitor import VoiceInteractionMetrics
from .models import (
    VoiceAnalyticsEvent,
    CustomerEngagementMetrics,
    PersonalityConsistencyScore,
    BusinessImpactMetrics
)

logger = structlog.get_logger(__name__)

class AnalyticsEventType(Enum):
    """Types of analytics events"""
    INTERACTION_START = "interaction_start"
    INTERACTION_COMPLETE = "interaction_complete" 
    COST_CALCULATED = "cost_calculated"
    QUALITY_ASSESSED = "quality_assessed"
    BUSINESS_INSIGHT = "business_insight"
    ALERT_TRIGGERED = "alert_triggered"

@dataclass
class VoiceInteractionAnalytics:
    """Extended analytics data for voice interactions"""
    # Base interaction data
    interaction_id: str
    customer_id: str
    conversation_id: str
    timestamp: datetime
    
    # Enhanced metrics
    performance_metrics: VoiceInteractionMetrics
    cost_breakdown: Dict[str, float]
    quality_scores: Dict[str, float]
    engagement_indicators: Dict[str, Any]
    business_context: Dict[str, Any]
    
    # AI-derived insights
    conversation_sentiment: float  # -1 to 1
    personality_consistency: float  # 0 to 1
    customer_satisfaction_estimate: float  # 0 to 1
    business_value_score: float  # 0 to 100
    
    # Predictive indicators
    churn_risk_score: float  # 0 to 1
    upsell_opportunity_score: float  # 0 to 1
    personal_brand_impact: float  # -1 to 1

class VoiceAnalyticsPipeline:
    """
    Real-time analytics pipeline for voice interactions
    
    Features:
    - Stream processing of voice interaction data
    - Real-time cost tracking and optimization
    - Quality assessment and personality consistency
    - Business intelligence and predictive analytics
    - Customer journey mapping and insights
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Pipeline configuration
        self.batch_size = self.config.get("batch_size", 100)
        self.processing_interval = self.config.get("processing_interval", 30)  # seconds
        self.retention_days = self.config.get("retention_days", 90)
        
        # Data storage
        self.raw_events: deque = deque(maxlen=10000)
        self.processed_analytics: deque = deque(maxlen=5000)
        self.customer_profiles: Dict[str, Dict] = {}
        self.conversation_histories: Dict[str, List] = defaultdict(list)
        
        # Processing state
        self.is_processing = False
        self.last_processing_time = datetime.now()
        self.processing_stats = {
            "events_processed": 0,
            "errors": 0,
            "last_batch_size": 0,
            "processing_time_ms": 0
        }
        
        # Analytics models
        self.engagement_analyzer = None
        self.sentiment_analyzer = None
        self.personality_detector = None
        self.business_intelligence = None
        
        # Metrics
        self.setup_metrics()
        
        logger.info("Voice analytics pipeline initialized",
                   batch_size=self.batch_size,
                   processing_interval=self.processing_interval)
    
    def setup_metrics(self):
        """Setup Prometheus metrics for analytics pipeline"""
        self.analytics_events_counter = Counter(
            'voice_analytics_events_total',
            'Total voice analytics events processed',
            ['event_type', 'customer_segment', 'success']
        )
        
        self.processing_time_histogram = Histogram(
            'voice_analytics_processing_seconds',
            'Time taken to process analytics batch',
            ['batch_size_range', 'processing_type']
        )
        
        self.business_value_gauge = Gauge(
            'voice_interaction_business_value',
            'Business value score of voice interactions',
            ['customer_id', 'time_bucket']
        )
        
        self.cost_per_interaction_gauge = Gauge(
            'voice_cost_per_interaction_dollars',
            'Cost per voice interaction in dollars',
            ['customer_segment', 'interaction_type']
        )
        
        self.quality_score_summary = Summary(
            'voice_quality_score',
            'Voice interaction quality scores',
            ['quality_dimension', 'customer_segment']
        )
    
    async def process_interaction(
        self,
        interaction_metrics: VoiceInteractionMetrics,
        conversation_context: Dict[str, Any] = None,
        business_context: Dict[str, Any] = None
    ) -> VoiceInteractionAnalytics:
        """Process individual voice interaction for analytics"""
        
        start_time = datetime.now()
        
        try:
            # Create analytics event
            analytics_event = VoiceAnalyticsEvent(
                event_id=str(uuid.uuid4()),
                event_type=AnalyticsEventType.INTERACTION_START,
                timestamp=start_time,
                customer_id=interaction_metrics.customer_id,
                interaction_id=interaction_metrics.interaction_id,
                data=asdict(interaction_metrics)
            )
            
            self.raw_events.append(analytics_event)
            
            # Calculate comprehensive analytics
            analytics = await self._create_comprehensive_analytics(
                interaction_metrics,
                conversation_context or {},
                business_context or {}
            )
            
            # Store processed analytics
            self.processed_analytics.append(analytics)
            
            # Update customer profile
            await self._update_customer_profile(analytics)
            
            # Update conversation history
            self.conversation_histories[analytics.conversation_id].append(analytics)
            
            # Record completion event
            completion_event = VoiceAnalyticsEvent(
                event_id=str(uuid.uuid4()),
                event_type=AnalyticsEventType.INTERACTION_COMPLETE,
                timestamp=datetime.now(),
                customer_id=interaction_metrics.customer_id,
                interaction_id=interaction_metrics.interaction_id,
                data={
                    "processing_time_ms": (datetime.now() - start_time).total_seconds() * 1000,
                    "business_value_score": analytics.business_value_score,
                    "cost_total": sum(analytics.cost_breakdown.values())
                }
            )
            
            self.raw_events.append(completion_event)
            
            # Update metrics
            self.analytics_events_counter.labels(
                event_type="interaction_processed",
                customer_segment=self._get_customer_segment(analytics.customer_id),
                success="true"
            ).inc()
            
            processing_time = (datetime.now() - start_time).total_seconds()
            self.processing_time_histogram.labels(
                batch_size_range="single",
                processing_type="interaction"
            ).observe(processing_time)
            
            self.business_value_gauge.labels(
                customer_id=analytics.customer_id,
                time_bucket=start_time.strftime("%Y-%m-%d-%H")
            ).set(analytics.business_value_score)
            
            logger.info("Voice interaction analytics processed",
                       interaction_id=analytics.interaction_id,
                       business_value=analytics.business_value_score,
                       processing_time_ms=processing_time * 1000)
            
            return analytics
            
        except Exception as e:
            logger.error("Error processing voice interaction analytics",
                        interaction_id=interaction_metrics.interaction_id,
                        error=str(e))
            
            self.analytics_events_counter.labels(
                event_type="interaction_processed",
                customer_segment="unknown",
                success="false"
            ).inc()
            
            raise
    
    async def _create_comprehensive_analytics(
        self,
        metrics: VoiceInteractionMetrics,
        conversation_context: Dict[str, Any],
        business_context: Dict[str, Any]
    ) -> VoiceInteractionAnalytics:
        """Create comprehensive analytics for voice interaction"""
        
        # Calculate cost breakdown
        cost_breakdown = await self._calculate_interaction_costs(metrics)
        
        # Assess quality scores
        quality_scores = await self._assess_interaction_quality(metrics, conversation_context)
        
        # Analyze engagement
        engagement_indicators = await self._analyze_customer_engagement(
            metrics, conversation_context
        )
        
        # Analyze sentiment and personality
        sentiment_score = await self._analyze_conversation_sentiment(conversation_context)
        personality_consistency = await self._assess_personality_consistency(
            metrics.customer_id, conversation_context
        )
        
        # Estimate customer satisfaction
        satisfaction_estimate = await self._estimate_customer_satisfaction(
            quality_scores, engagement_indicators, sentiment_score
        )
        
        # Calculate business value
        business_value_score = await self._calculate_business_value(
            metrics, engagement_indicators, business_context
        )
        
        # Predictive analytics
        churn_risk = await self._predict_churn_risk(metrics.customer_id, engagement_indicators)
        upsell_opportunity = await self._predict_upsell_opportunity(
            metrics.customer_id, business_context
        )
        brand_impact = await self._assess_personal_brand_impact(
            conversation_context, business_context
        )
        
        return VoiceInteractionAnalytics(
            interaction_id=metrics.interaction_id,
            customer_id=metrics.customer_id,
            conversation_id=metrics.conversation_id,
            timestamp=metrics.timestamp,
            performance_metrics=metrics,
            cost_breakdown=cost_breakdown,
            quality_scores=quality_scores,
            engagement_indicators=engagement_indicators,
            business_context=business_context,
            conversation_sentiment=sentiment_score,
            personality_consistency=personality_consistency,
            customer_satisfaction_estimate=satisfaction_estimate,
            business_value_score=business_value_score,
            churn_risk_score=churn_risk,
            upsell_opportunity_score=upsell_opportunity,
            personal_brand_impact=brand_impact
        )
    
    async def _calculate_interaction_costs(
        self, 
        metrics: VoiceInteractionMetrics
    ) -> Dict[str, float]:
        """Calculate detailed cost breakdown for interaction"""
        
        costs = {}
        
        # ElevenLabs TTS costs (estimated)
        # Typical pricing: ~$0.30 per 1K characters
        if metrics.response_length > 0:
            tts_cost = (metrics.response_length / 1000) * 0.30
            costs["text_to_speech"] = round(tts_cost, 4)
        else:
            costs["text_to_speech"] = 0.0
        
        # Whisper STT costs (estimated)
        # Typical pricing: ~$0.006 per minute
        if metrics.speech_to_text_time > 0:
            stt_minutes = metrics.speech_to_text_time / 60
            stt_cost = stt_minutes * 0.006
            costs["speech_to_text"] = round(stt_cost, 4)
        else:
            costs["speech_to_text"] = 0.0
        
        # EA processing costs (compute)
        processing_cost = metrics.ea_processing_time * 0.001  # $0.001 per second
        costs["ea_processing"] = round(processing_cost, 4)
        
        # Infrastructure costs (estimated)
        base_infrastructure = 0.005  # $0.005 per interaction
        costs["infrastructure"] = base_infrastructure
        
        # Memory storage costs
        memory_cost = 0.001  # $0.001 per interaction for memory storage
        costs["memory_storage"] = memory_cost
        
        # Total cost
        costs["total"] = round(sum(costs.values()), 4)
        
        return costs
    
    async def _assess_interaction_quality(
        self,
        metrics: VoiceInteractionMetrics,
        conversation_context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Assess various quality dimensions of the interaction"""
        
        quality_scores = {}
        
        # Response time quality (0-1, higher is better)
        if metrics.total_response_time <= 1.0:
            quality_scores["response_time"] = 1.0
        elif metrics.total_response_time <= 2.0:
            quality_scores["response_time"] = 0.8
        elif metrics.total_response_time <= 3.0:
            quality_scores["response_time"] = 0.6
        else:
            quality_scores["response_time"] = max(0.0, 1.0 - (metrics.total_response_time - 2.0) / 5.0)
        
        # Audio quality (based on size ratios and processing time)
        if metrics.audio_input_size_bytes > 0 and metrics.audio_output_size_bytes > 0:
            # Heuristic: good quality should have reasonable audio sizes
            audio_ratio = metrics.audio_output_size_bytes / metrics.audio_input_size_bytes
            if 0.5 <= audio_ratio <= 3.0:  # Reasonable ratio
                quality_scores["audio_quality"] = 0.9
            else:
                quality_scores["audio_quality"] = 0.7
        else:
            quality_scores["audio_quality"] = 0.5  # Unknown quality
        
        # Language consistency
        if metrics.language_switch:
            quality_scores["language_consistency"] = 0.7  # Penalize switches
        else:
            quality_scores["language_consistency"] = 1.0
        
        # Response completeness (based on response length)
        if metrics.response_length >= 50:  # Substantial response
            quality_scores["response_completeness"] = 1.0
        elif metrics.response_length >= 20:
            quality_scores["response_completeness"] = 0.8
        else:
            quality_scores["response_completeness"] = 0.6
        
        # Context relevance (from conversation context)
        context_score = conversation_context.get("relevance_score", 0.8)
        quality_scores["context_relevance"] = min(1.0, max(0.0, context_score))
        
        # Overall quality score
        quality_scores["overall"] = statistics.mean(quality_scores.values())
        
        return quality_scores
    
    async def _analyze_customer_engagement(
        self,
        metrics: VoiceInteractionMetrics,
        conversation_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze customer engagement indicators"""
        
        engagement = {}
        
        # Conversation length as engagement indicator
        engagement["message_length"] = metrics.transcript_length
        engagement["response_generated"] = metrics.response_length > 0
        engagement["interaction_duration"] = metrics.total_response_time
        
        # Historical context
        customer_history = self.customer_profiles.get(metrics.customer_id, {})
        previous_interactions = customer_history.get("total_interactions", 0)
        
        engagement["is_returning_customer"] = previous_interactions > 0
        engagement["interaction_frequency"] = self._calculate_interaction_frequency(metrics.customer_id)
        
        # Language preference consistency
        preferred_language = customer_history.get("preferred_language", metrics.detected_language)
        engagement["language_preference_match"] = preferred_language == metrics.detected_language
        
        # Success rate
        recent_success_rate = self._get_recent_success_rate(metrics.customer_id)
        engagement["recent_success_rate"] = recent_success_rate
        
        # Engagement score (0-1)
        factors = [
            min(1.0, metrics.transcript_length / 100),  # Normalized message length
            1.0 if metrics.response_length > 0 else 0.0,  # Response generated
            min(1.0, previous_interactions / 10),  # Customer loyalty
            recent_success_rate,  # Success rate
            1.0 if engagement["language_preference_match"] else 0.8  # Language consistency
        ]
        
        engagement["engagement_score"] = statistics.mean(factors)
        
        return engagement
    
    async def _analyze_conversation_sentiment(
        self, 
        conversation_context: Dict[str, Any]
    ) -> float:
        """Analyze sentiment of the conversation (-1 to 1)"""
        
        # Placeholder for sentiment analysis
        # In production, integrate with sentiment analysis service
        
        # Basic heuristics for now
        text_content = conversation_context.get("message_text", "")
        response_text = conversation_context.get("response_text", "")
        
        # Simple keyword-based sentiment
        positive_words = ["great", "excellent", "good", "thanks", "perfect", "amazing"]
        negative_words = ["bad", "terrible", "awful", "hate", "problem", "issue"]
        
        combined_text = f"{text_content} {response_text}".lower()
        
        positive_count = sum(1 for word in positive_words if word in combined_text)
        negative_count = sum(1 for word in negative_words if word in combined_text)
        
        if positive_count + negative_count == 0:
            return 0.0  # Neutral
        
        sentiment = (positive_count - negative_count) / (positive_count + negative_count)
        return max(-1.0, min(1.0, sentiment))
    
    async def _assess_personality_consistency(
        self,
        customer_id: str,
        conversation_context: Dict[str, Any]
    ) -> float:
        """Assess EA personality consistency across interactions (0-1)"""
        
        # Placeholder for personality consistency analysis
        # In production, analyze EA response patterns and consistency
        
        customer_history = self.customer_profiles.get(customer_id, {})
        previous_personality_scores = customer_history.get("personality_scores", [])
        
        # For now, assume good consistency if response is substantial
        response_text = conversation_context.get("response_text", "")
        current_score = 0.9 if len(response_text) > 30 else 0.7
        
        if not previous_personality_scores:
            return current_score
        
        # Calculate consistency with previous interactions
        recent_scores = previous_personality_scores[-5:]  # Last 5 interactions
        avg_previous = statistics.mean(recent_scores)
        
        # Consistency is inverse of deviation
        deviation = abs(current_score - avg_previous)
        consistency = max(0.0, 1.0 - deviation)
        
        return consistency
    
    async def _estimate_customer_satisfaction(
        self,
        quality_scores: Dict[str, float],
        engagement_indicators: Dict[str, Any],
        sentiment_score: float
    ) -> float:
        """Estimate customer satisfaction based on multiple factors (0-1)"""
        
        factors = [
            quality_scores.get("overall", 0.8) * 0.3,  # Quality weight: 30%
            engagement_indicators.get("engagement_score", 0.7) * 0.3,  # Engagement: 30%
            (sentiment_score + 1) / 2 * 0.2,  # Sentiment (normalized): 20%
            quality_scores.get("response_time", 0.8) * 0.2  # Response time: 20%
        ]
        
        satisfaction = sum(factors)
        return max(0.0, min(1.0, satisfaction))
    
    async def _calculate_business_value(
        self,
        metrics: VoiceInteractionMetrics,
        engagement_indicators: Dict[str, Any],
        business_context: Dict[str, Any]
    ) -> float:
        """Calculate business value score for interaction (0-100)"""
        
        base_value = 10.0  # Base value for any successful interaction
        
        # Success bonus
        if metrics.success:
            base_value += 20.0
        
        # Engagement bonus
        engagement_score = engagement_indicators.get("engagement_score", 0.5)
        base_value += engagement_score * 30.0
        
        # Returning customer bonus
        if engagement_indicators.get("is_returning_customer", False):
            base_value += 15.0
        
        # Response quality bonus
        if metrics.response_length > 50:
            base_value += 10.0
        
        # Language consistency bonus
        if not metrics.language_switch:
            base_value += 5.0
        
        # Business context bonuses
        if business_context.get("high_value_customer", False):
            base_value *= 1.5
        
        if business_context.get("strategic_conversation", False):
            base_value += 20.0
        
        return min(100.0, base_value)
    
    async def _predict_churn_risk(
        self, 
        customer_id: str, 
        engagement_indicators: Dict[str, Any]
    ) -> float:
        """Predict customer churn risk (0-1, higher is more risk)"""
        
        customer_profile = self.customer_profiles.get(customer_id, {})
        
        risk_factors = []
        
        # Low engagement
        engagement_score = engagement_indicators.get("engagement_score", 0.5)
        risk_factors.append(1.0 - engagement_score)
        
        # Declining success rate
        success_rate = engagement_indicators.get("recent_success_rate", 0.8)
        risk_factors.append(1.0 - success_rate)
        
        # Infrequent usage
        frequency = engagement_indicators.get("interaction_frequency", 0.5)
        risk_factors.append(1.0 - frequency)
        
        # Historical patterns
        total_interactions = customer_profile.get("total_interactions", 1)
        if total_interactions < 5:  # New customers have higher churn risk
            risk_factors.append(0.3)
        
        churn_risk = statistics.mean(risk_factors)
        return max(0.0, min(1.0, churn_risk))
    
    async def _predict_upsell_opportunity(
        self,
        customer_id: str,
        business_context: Dict[str, Any]
    ) -> float:
        """Predict upsell opportunity score (0-1)"""
        
        customer_profile = self.customer_profiles.get(customer_id, {})
        
        opportunity_factors = []
        
        # High engagement customers are good upsell candidates
        avg_engagement = customer_profile.get("average_engagement", 0.5)
        opportunity_factors.append(avg_engagement)
        
        # Frequent users
        total_interactions = customer_profile.get("total_interactions", 1)
        frequency_score = min(1.0, total_interactions / 20)  # Normalize to 20 interactions
        opportunity_factors.append(frequency_score)
        
        # High satisfaction
        avg_satisfaction = customer_profile.get("average_satisfaction", 0.5)
        opportunity_factors.append(avg_satisfaction)
        
        # Business context indicators
        if business_context.get("premium_features_mentioned", False):
            opportunity_factors.append(0.8)
        
        if business_context.get("growth_indicators", False):
            opportunity_factors.append(0.7)
        
        opportunity_score = statistics.mean(opportunity_factors)
        return max(0.0, min(1.0, opportunity_score))
    
    async def _assess_personal_brand_impact(
        self,
        conversation_context: Dict[str, Any],
        business_context: Dict[str, Any]
    ) -> float:
        """Assess impact on personal brand (-1 to 1)"""
        
        # Placeholder for brand impact analysis
        # In production, analyze conversation content for brand alignment
        
        impact_factors = []
        
        # Professional tone and quality
        response_text = conversation_context.get("response_text", "")
        if len(response_text) > 30:  # Substantial response
            impact_factors.append(0.3)
        
        # Successful interaction
        if conversation_context.get("interaction_success", True):
            impact_factors.append(0.2)
        
        # Business value created
        if business_context.get("value_created", False):
            impact_factors.append(0.4)
        
        # Language and communication quality
        language_quality = conversation_context.get("language_quality", 0.8)
        impact_factors.append(language_quality * 0.3)
        
        if not impact_factors:
            return 0.0
        
        brand_impact = statistics.mean(impact_factors)
        return max(-1.0, min(1.0, brand_impact))
    
    async def _update_customer_profile(self, analytics: VoiceInteractionAnalytics):
        """Update customer profile with analytics data"""
        
        customer_id = analytics.customer_id
        
        if customer_id not in self.customer_profiles:
            self.customer_profiles[customer_id] = {
                "first_interaction": analytics.timestamp,
                "total_interactions": 0,
                "total_cost": 0.0,
                "engagement_scores": [],
                "satisfaction_scores": [],
                "personality_scores": [],
                "preferred_language": analytics.performance_metrics.detected_language,
                "success_count": 0,
                "error_count": 0
            }
        
        profile = self.customer_profiles[customer_id]
        
        # Update counters
        profile["total_interactions"] += 1
        profile["total_cost"] += analytics.cost_breakdown["total"]
        profile["last_interaction"] = analytics.timestamp
        
        # Update scores (keep last 20)
        profile["engagement_scores"].append(analytics.engagement_indicators["engagement_score"])
        profile["satisfaction_scores"].append(analytics.customer_satisfaction_estimate)
        profile["personality_scores"].append(analytics.personality_consistency)
        
        # Trim to last 20 interactions
        for key in ["engagement_scores", "satisfaction_scores", "personality_scores"]:
            profile[key] = profile[key][-20:]
        
        # Update success/error counts
        if analytics.performance_metrics.success:
            profile["success_count"] += 1
        else:
            profile["error_count"] += 1
        
        # Update averages
        profile["average_engagement"] = statistics.mean(profile["engagement_scores"])
        profile["average_satisfaction"] = statistics.mean(profile["satisfaction_scores"])
        profile["success_rate"] = profile["success_count"] / profile["total_interactions"]
        
    def _get_customer_segment(self, customer_id: str) -> str:
        """Get customer segment for metrics labeling"""
        profile = self.customer_profiles.get(customer_id, {})
        
        total_interactions = profile.get("total_interactions", 0)
        avg_engagement = profile.get("average_engagement", 0.5)
        
        if total_interactions >= 20 and avg_engagement >= 0.8:
            return "high_value"
        elif total_interactions >= 5 and avg_engagement >= 0.6:
            return "engaged"
        elif total_interactions >= 1:
            return "active"
        else:
            return "new"
    
    def _calculate_interaction_frequency(self, customer_id: str) -> float:
        """Calculate interaction frequency score (0-1)"""
        profile = self.customer_profiles.get(customer_id, {})
        
        if "first_interaction" not in profile:
            return 0.0
        
        days_since_first = (datetime.now() - profile["first_interaction"]).days
        total_interactions = profile.get("total_interactions", 0)
        
        if days_since_first == 0:
            return 1.0 if total_interactions > 0 else 0.0
        
        # Interactions per day, normalized
        frequency = min(1.0, (total_interactions / max(1, days_since_first)) / 2.0)
        return frequency
    
    def _get_recent_success_rate(self, customer_id: str) -> float:
        """Get recent success rate for customer"""
        profile = self.customer_profiles.get(customer_id, {})
        
        if profile.get("total_interactions", 0) == 0:
            return 0.8  # Default for new customers
        
        return profile.get("success_rate", 0.8)
    
    async def get_customer_analytics_summary(self, customer_id: str) -> Dict[str, Any]:
        """Get comprehensive analytics summary for customer"""
        
        profile = self.customer_profiles.get(customer_id, {})
        
        if not profile:
            return {"error": "Customer not found"}
        
        # Get recent interactions for this customer
        recent_analytics = [
            a for a in self.processed_analytics 
            if a.customer_id == customer_id
        ][-20:]  # Last 20 interactions
        
        if not recent_analytics:
            return {"error": "No analytics data available"}
        
        # Calculate trends
        business_value_trend = [a.business_value_score for a in recent_analytics]
        cost_trend = [sum(a.cost_breakdown.values()) for a in recent_analytics]
        satisfaction_trend = [a.customer_satisfaction_estimate for a in recent_analytics]
        
        return {
            "customer_id": customer_id,
            "profile_summary": {
                "first_interaction": profile.get("first_interaction", "").isoformat() if profile.get("first_interaction") else "",
                "total_interactions": profile.get("total_interactions", 0),
                "total_cost": round(profile.get("total_cost", 0), 2),
                "success_rate": round(profile.get("success_rate", 0), 3),
                "average_engagement": round(profile.get("average_engagement", 0), 3),
                "average_satisfaction": round(profile.get("average_satisfaction", 0), 3),
                "preferred_language": profile.get("preferred_language", "en"),
                "customer_segment": self._get_customer_segment(customer_id)
            },
            "trends": {
                "business_value": {
                    "current": business_value_trend[-1] if business_value_trend else 0,
                    "average": statistics.mean(business_value_trend) if business_value_trend else 0,
                    "trend": "increasing" if len(business_value_trend) >= 2 and business_value_trend[-1] > business_value_trend[-2] else "stable"
                },
                "cost_efficiency": {
                    "current_cost": cost_trend[-1] if cost_trend else 0,
                    "average_cost": statistics.mean(cost_trend) if cost_trend else 0,
                    "cost_trend": "increasing" if len(cost_trend) >= 2 and cost_trend[-1] > cost_trend[-2] else "stable"
                },
                "satisfaction": {
                    "current": satisfaction_trend[-1] if satisfaction_trend else 0,
                    "average": statistics.mean(satisfaction_trend) if satisfaction_trend else 0,
                    "trend": "improving" if len(satisfaction_trend) >= 2 and satisfaction_trend[-1] > satisfaction_trend[-2] else "stable"
                }
            },
            "predictions": {
                "churn_risk": recent_analytics[-1].churn_risk_score if recent_analytics else 0.5,
                "upsell_opportunity": recent_analytics[-1].upsell_opportunity_score if recent_analytics else 0.3,
                "brand_impact": recent_analytics[-1].personal_brand_impact if recent_analytics else 0.0
            },
            "recommendations": self._generate_customer_recommendations(customer_id, profile, recent_analytics)
        }
    
    def _generate_customer_recommendations(
        self,
        customer_id: str,
        profile: Dict[str, Any],
        recent_analytics: List[VoiceInteractionAnalytics]
    ) -> List[str]:
        """Generate recommendations for customer engagement"""
        
        recommendations = []
        
        # Engagement recommendations
        avg_engagement = profile.get("average_engagement", 0.5)
        if avg_engagement < 0.6:
            recommendations.append("Consider personalizing interactions to increase engagement")
        
        # Cost optimization
        if profile.get("total_cost", 0) > 10.0:  # High cost customer
            recommendations.append("Review interaction efficiency to optimize costs")
        
        # Satisfaction improvements
        avg_satisfaction = profile.get("average_satisfaction", 0.5)
        if avg_satisfaction < 0.7:
            recommendations.append("Focus on improving response quality and relevance")
        
        # Upsell opportunities
        if recent_analytics:
            latest_upsell_score = recent_analytics[-1].upsell_opportunity_score
            if latest_upsell_score > 0.7:
                recommendations.append("High upsell potential - consider premium feature introduction")
        
        # Churn prevention
        if recent_analytics:
            latest_churn_risk = recent_analytics[-1].churn_risk_score
            if latest_churn_risk > 0.6:
                recommendations.append("Churn risk detected - implement retention strategy")
        
        return recommendations
    
    async def start_background_processing(self):
        """Start background analytics processing"""
        self.is_processing = True
        
        async def process_loop():
            while self.is_processing:
                try:
                    await self._process_pending_events()
                    await asyncio.sleep(self.processing_interval)
                except Exception as e:
                    logger.error("Error in analytics processing loop", error=str(e))
                    await asyncio.sleep(5)  # Brief pause before retrying
        
        asyncio.create_task(process_loop())
        logger.info("Background analytics processing started")
    
    async def _process_pending_events(self):
        """Process pending analytics events in batch"""
        if not self.raw_events:
            return
        
        start_time = datetime.now()
        events_to_process = min(self.batch_size, len(self.raw_events))
        
        batch = []
        for _ in range(events_to_process):
            if self.raw_events:
                batch.append(self.raw_events.popleft())
        
        if not batch:
            return
        
        # Process batch (placeholder for complex analytics)
        processed_count = 0
        errors = 0
        
        for event in batch:
            try:
                # Complex analytics processing would go here
                processed_count += 1
            except Exception as e:
                logger.error("Error processing analytics event", event_id=event.event_id, error=str(e))
                errors += 1
        
        # Update processing stats
        processing_time = (datetime.now() - start_time).total_seconds()
        self.processing_stats.update({
            "events_processed": self.processing_stats["events_processed"] + processed_count,
            "errors": self.processing_stats["errors"] + errors,
            "last_batch_size": len(batch),
            "processing_time_ms": processing_time * 1000
        })
        
        self.last_processing_time = datetime.now()
        
        logger.info("Analytics batch processed",
                   batch_size=len(batch),
                   processed=processed_count,
                   errors=errors,
                   processing_time_ms=processing_time * 1000)
    
    async def stop_background_processing(self):
        """Stop background analytics processing"""
        self.is_processing = False
        logger.info("Background analytics processing stopped")
    
    def get_analytics_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        
        # Overall metrics
        total_interactions = sum(
            profile.get("total_interactions", 0) 
            for profile in self.customer_profiles.values()
        )
        
        total_customers = len(self.customer_profiles)
        total_cost = sum(
            profile.get("total_cost", 0) 
            for profile in self.customer_profiles.values()
        )
        
        # Customer segments
        segments = defaultdict(int)
        for customer_id in self.customer_profiles.keys():
            segment = self._get_customer_segment(customer_id)
            segments[segment] += 1
        
        # Recent analytics summary
        recent_analytics = list(self.processed_analytics)[-100:] if self.processed_analytics else []
        
        business_values = [a.business_value_score for a in recent_analytics]
        satisfaction_scores = [a.customer_satisfaction_estimate for a in recent_analytics]
        costs = [sum(a.cost_breakdown.values()) for a in recent_analytics]
        
        return {
            "overview": {
                "total_interactions": total_interactions,
                "total_customers": total_customers,
                "total_cost": round(total_cost, 2),
                "average_cost_per_interaction": round(total_cost / max(1, total_interactions), 4),
                "customer_segments": dict(segments)
            },
            "performance_metrics": {
                "average_business_value": round(statistics.mean(business_values), 2) if business_values else 0,
                "average_satisfaction": round(statistics.mean(satisfaction_scores), 3) if satisfaction_scores else 0,
                "cost_efficiency": {
                    "average_cost": round(statistics.mean(costs), 4) if costs else 0,
                    "cost_trend": "stable"  # Would calculate actual trend
                }
            },
            "processing_stats": self.processing_stats.copy(),
            "top_customers": self._get_top_customers(10),
            "alerts": self._get_active_alerts(),
            "recommendations": self._get_system_recommendations()
        }
    
    def _get_top_customers(self, limit: int) -> List[Dict[str, Any]]:
        """Get top customers by value"""
        
        customers = []
        for customer_id, profile in self.customer_profiles.items():
            customers.append({
                "customer_id": customer_id,
                "total_interactions": profile.get("total_interactions", 0),
                "total_cost": round(profile.get("total_cost", 0), 2),
                "average_engagement": round(profile.get("average_engagement", 0), 3),
                "success_rate": round(profile.get("success_rate", 0), 3),
                "segment": self._get_customer_segment(customer_id)
            })
        
        # Sort by total interactions and engagement
        customers.sort(
            key=lambda x: (x["total_interactions"] * x["average_engagement"]), 
            reverse=True
        )
        
        return customers[:limit]
    
    def _get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active system alerts"""
        alerts = []
        
        # High cost alerts
        if self.customer_profiles:
            avg_cost_per_customer = sum(
                p.get("total_cost", 0) for p in self.customer_profiles.values()
            ) / len(self.customer_profiles)
            
            if avg_cost_per_customer > 5.0:  # Threshold
                alerts.append({
                    "type": "high_cost",
                    "severity": "warning",
                    "message": f"Average cost per customer is ${avg_cost_per_customer:.2f}",
                    "timestamp": datetime.now().isoformat()
                })
        
        # Low satisfaction alerts
        recent_analytics = list(self.processed_analytics)[-50:] if self.processed_analytics else []
        if recent_analytics:
            avg_satisfaction = statistics.mean(a.customer_satisfaction_estimate for a in recent_analytics)
            if avg_satisfaction < 0.6:
                alerts.append({
                    "type": "low_satisfaction",
                    "severity": "critical",
                    "message": f"Average satisfaction score is {avg_satisfaction:.2f}",
                    "timestamp": datetime.now().isoformat()
                })
        
        return alerts
    
    def _get_system_recommendations(self) -> List[str]:
        """Get system-level recommendations"""
        recommendations = []
        
        # Cost optimization
        total_cost = sum(
            profile.get("total_cost", 0) 
            for profile in self.customer_profiles.values()
        )
        
        if total_cost > 100.0:
            recommendations.append("Consider implementing cost optimization strategies")
        
        # Engagement improvement
        if self.customer_profiles:
            avg_engagement = statistics.mean(
                profile.get("average_engagement", 0) 
                for profile in self.customer_profiles.values()
            )
            
            if avg_engagement < 0.7:
                recommendations.append("Focus on improving overall customer engagement")
        
        # Processing efficiency
        if self.processing_stats["errors"] > self.processing_stats["events_processed"] * 0.05:
            recommendations.append("Review analytics processing pipeline for error reduction")
        
        return recommendations

# Global analytics pipeline instance
voice_analytics_pipeline = VoiceAnalyticsPipeline()