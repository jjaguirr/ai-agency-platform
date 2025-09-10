"""
Voice Business Intelligence
Advanced business analytics and insights for voice interactions
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import statistics
import json

# Analytics imports
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier

# Monitoring imports
from prometheus_client import Gauge, Counter, Histogram
import structlog

# Local imports  
from .models import (
    BusinessIntelligenceInsight,
    CompetitiveIntelligence,
    ROIMeasurement,
    CustomerJourneyStage,
    CustomerSegment
)
from .voice_analytics_pipeline import VoiceInteractionAnalytics

logger = structlog.get_logger(__name__)

class VoiceBusinessIntelligence:
    """
    Advanced business intelligence system for voice interactions
    
    Features:
    - Customer lifecycle analytics and prediction
    - ROI measurement and optimization recommendations  
    - Competitive intelligence extraction
    - Market trend analysis and insights
    - Personal brand impact measurement
    - Predictive customer segmentation
    - Revenue opportunity identification
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Analysis configuration
        self.insight_generation_interval = self.config.get("insight_interval_hours", 4)
        self.roi_calculation_period = self.config.get("roi_period_days", 30)
        self.competitive_analysis_sensitivity = self.config.get("competitive_sensitivity", 0.7)
        
        # Data storage
        self.customer_analytics: Dict[str, List[VoiceInteractionAnalytics]] = defaultdict(list)
        self.generated_insights: List[BusinessIntelligenceInsight] = []
        self.competitive_intelligence: List[CompetitiveIntelligence] = []
        self.roi_measurements: List[ROIMeasurement] = []
        self.customer_journey_stages: Dict[str, CustomerJourneyStage] = {}
        
        # ML models
        self.churn_prediction_model = None
        self.customer_segmentation_model = None
        self.value_prediction_model = None
        
        # Business metrics
        self.business_metrics = {
            "total_customers": 0,
            "active_customers": 0,
            "high_value_customers": 0,
            "at_risk_customers": 0,
            "total_revenue_opportunity": 0.0,
            "average_customer_lifetime_value": 0.0,
            "customer_acquisition_cost": 0.0,
            "monthly_recurring_revenue": 0.0
        }
        
        # Performance tracking
        self.insight_generation_stats = {
            "insights_generated": 0,
            "accuracy_score": 0.0,
            "last_generation_time": None,
            "processing_time_avg_ms": 0
        }
        
        self.setup_metrics()
        logger.info("Voice business intelligence system initialized")
    
    def setup_metrics(self):
        """Setup Prometheus metrics for business intelligence"""
        self.business_value_gauge = Gauge(
            'voice_bi_business_value_score',
            'Business value score from voice interactions',
            ['customer_segment', 'value_type']
        )
        
        self.roi_gauge = Gauge(
            'voice_bi_roi_percentage',
            'ROI percentage for voice interactions',
            ['customer_segment', 'measurement_period']
        )
        
        self.customer_lifetime_value_gauge = Gauge(
            'voice_bi_customer_lifetime_value',
            'Predicted customer lifetime value',
            ['customer_segment', 'prediction_confidence']
        )
        
        self.insights_counter = Counter(
            'voice_bi_insights_generated_total',
            'Total business insights generated',
            ['insight_type', 'impact_level']
        )
        
        self.competitive_mentions_counter = Counter(
            'voice_bi_competitive_mentions_total',
            'Competitive mentions in voice interactions',
            ['competitor', 'sentiment', 'customer_segment']
        )
    
    async def analyze_customer_analytics(
        self, 
        analytics: VoiceInteractionAnalytics
    ):
        """Analyze customer interaction for business intelligence"""
        
        customer_id = analytics.customer_id
        self.customer_analytics[customer_id].append(analytics)
        
        # Keep only recent analytics (performance optimization)
        self.customer_analytics[customer_id] = self.customer_analytics[customer_id][-100:]
        
        # Update customer journey stage
        await self._update_customer_journey_stage(customer_id, analytics)
        
        # Extract competitive intelligence
        await self._extract_competitive_intelligence(analytics)
        
        # Update business metrics
        await self._update_business_metrics()
        
        # Generate insights if conditions are met
        if self._should_generate_insights(customer_id):
            await self._generate_customer_insights(customer_id)
    
    async def _update_customer_journey_stage(
        self, 
        customer_id: str, 
        analytics: VoiceInteractionAnalytics
    ):
        """Update customer journey stage based on analytics"""
        
        current_analytics = self.customer_analytics[customer_id]
        
        # Determine current stage
        total_interactions = len(current_analytics)
        avg_engagement = statistics.mean([a.engagement_indicators["engagement_score"] for a in current_analytics[-10:]])
        recent_success_rate = sum(1 for a in current_analytics[-10:] if a.performance_metrics.success) / min(10, len(current_analytics))
        avg_business_value = statistics.mean([a.business_value_score for a in current_analytics[-5:]])
        
        # Stage determination logic
        if total_interactions <= 3:
            stage = "onboarding"
        elif total_interactions <= 10 and avg_engagement >= 0.7:
            stage = "adoption"
        elif avg_engagement >= 0.8 and avg_business_value >= 70:
            stage = "growth"
        elif avg_engagement >= 0.6 and recent_success_rate >= 0.8:
            stage = "maturity"
        elif avg_engagement < 0.4 or recent_success_rate < 0.5:
            stage = "at_risk"
        else:
            stage = "active"
        
        # Get previous stage
        previous_stage = None
        if customer_id in self.customer_journey_stages:
            previous_stage = self.customer_journey_stages[customer_id].current_stage
        
        # Calculate days in stage
        days_in_stage = 1
        if customer_id in self.customer_journey_stages and self.customer_journey_stages[customer_id].current_stage == stage:
            days_in_stage = (datetime.now() - self.customer_journey_stages[customer_id].stage_date).days
        
        # Calculate transition probabilities
        transition_probabilities = await self._calculate_transition_probabilities(
            customer_id, stage, current_analytics
        )
        
        # Generate stage recommendations
        stage_recommendations = await self._generate_stage_recommendations(
            customer_id, stage, current_analytics
        )
        
        # Update journey stage
        self.customer_journey_stages[customer_id] = CustomerJourneyStage(
            customer_id=customer_id,
            stage_date=datetime.now(),
            current_stage=stage,
            days_in_stage=days_in_stage,
            previous_stage=previous_stage,
            interactions_in_stage=total_interactions,
            success_rate_in_stage=recent_success_rate,
            engagement_level=avg_engagement,
            satisfaction_trend="improving" if len(current_analytics) >= 2 and current_analytics[-1].customer_satisfaction_estimate > current_analytics[-2].customer_satisfaction_estimate else "stable",
            next_stage_probabilities=transition_probabilities,
            transition_triggers=self._identify_transition_triggers(stage, current_analytics),
            stage_metrics=self._calculate_stage_metrics(stage, current_analytics),
            stage_recommendations=stage_recommendations
        )
        
        logger.debug("Customer journey stage updated",
                    customer_id=customer_id,
                    stage=stage,
                    previous_stage=previous_stage,
                    engagement=avg_engagement)
    
    async def _extract_competitive_intelligence(
        self, 
        analytics: VoiceInteractionAnalytics
    ):
        """Extract competitive intelligence from voice interaction"""
        
        # This would integrate with NLP services to extract competitive mentions
        # For now, implementing basic keyword detection
        
        business_context = analytics.business_context
        conversation_text = business_context.get("conversation_text", "").lower()
        
        # Competitive keywords (would be expanded and made more sophisticated)
        competitors = {
            "salesforce": ["salesforce", "sf", "crm"],
            "hubspot": ["hubspot", "hub spot"],
            "pipedrive": ["pipedrive", "pipe drive"],
            "zoho": ["zoho"],
            "monday": ["monday.com", "monday"],
            "asana": ["asana"],
            "notion": ["notion"],
            "clickup": ["clickup", "click up"]
        }
        
        competitors_mentioned = []
        competitive_context = "neutral"
        sentiment_scores = {}
        
        for competitor, keywords in competitors.items():
            for keyword in keywords:
                if keyword in conversation_text:
                    competitors_mentioned.append(competitor)
                    
                    # Simple sentiment analysis around competitor mention
                    # In production, use proper NLP sentiment analysis
                    context_window = self._extract_context_around_keyword(conversation_text, keyword, 50)
                    sentiment = self._analyze_context_sentiment(context_window)
                    sentiment_scores[competitor] = sentiment
                    
                    # Determine competitive context
                    if "better than" in context_window or "switch from" in context_window:
                        competitive_context = "comparison"
                    elif "considering" in context_window or "looking at" in context_window:
                        competitive_context = "switch_consideration"
                    
                    break  # Found this competitor, move to next
        
        # Extract market intelligence
        market_trends = self._extract_market_trends(conversation_text)
        pricing_intel = self._extract_pricing_intelligence(conversation_text)
        pain_points = self._extract_pain_points(conversation_text)
        
        # Only create intelligence record if we found something relevant
        if competitors_mentioned or market_trends or pain_points:
            competitive_intel = CompetitiveIntelligence(
                intelligence_id=f"ci_{analytics.interaction_id}_{int(datetime.now().timestamp())}",
                collected_timestamp=analytics.timestamp,
                customer_id=analytics.customer_id,
                competitors_mentioned=competitors_mentioned,
                competitive_context=competitive_context,
                sentiment_toward_competitors=sentiment_scores,
                market_trends_mentioned=market_trends,
                pricing_intelligence=pricing_intel,
                feature_comparisons={},  # Would extract feature comparisons
                customer_pain_points=pain_points,
                opportunity_areas=self._identify_opportunity_areas(pain_points),
                differentiation_opportunities=self._identify_differentiation_opportunities(competitors_mentioned, pain_points),
                confidence_score=0.7,  # Basic confidence score
                extraction_method="keyword",
                validation_status="unvalidated",
                intelligence_priority="medium" if competitors_mentioned else "low",
                assigned_to=None
            )
            
            self.competitive_intelligence.append(competitive_intel)
            
            # Update metrics
            for competitor in competitors_mentioned:
                sentiment = "positive" if sentiment_scores.get(competitor, 0) > 0.2 else "negative" if sentiment_scores.get(competitor, 0) < -0.2 else "neutral"
                self.competitive_mentions_counter.labels(
                    competitor=competitor,
                    sentiment=sentiment,
                    customer_segment=self._get_customer_segment(analytics.customer_id)
                ).inc()
            
            logger.info("Competitive intelligence extracted",
                       interaction_id=analytics.interaction_id,
                       competitors=competitors_mentioned,
                       market_trends=len(market_trends))
    
    async def _calculate_transition_probabilities(
        self, 
        customer_id: str, 
        current_stage: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> Dict[str, float]:
        """Calculate probabilities of transitioning to different journey stages"""
        
        # This would use ML models trained on historical data
        # For now, implementing rule-based probabilities
        
        recent_analytics = analytics_history[-5:] if len(analytics_history) >= 5 else analytics_history
        
        avg_engagement = statistics.mean([a.engagement_indicators["engagement_score"] for a in recent_analytics])
        avg_satisfaction = statistics.mean([a.customer_satisfaction_estimate for a in recent_analytics])
        success_rate = sum(1 for a in recent_analytics if a.performance_metrics.success) / len(recent_analytics)
        
        probabilities = {}
        
        if current_stage == "onboarding":
            probabilities = {
                "adoption": 0.6 if avg_engagement > 0.6 else 0.3,
                "at_risk": 0.3 if success_rate < 0.5 else 0.1,
                "churn": 0.1 if success_rate < 0.3 else 0.05
            }
        elif current_stage == "adoption":
            probabilities = {
                "growth": 0.4 if avg_engagement > 0.7 and avg_satisfaction > 0.8 else 0.2,
                "maturity": 0.3 if success_rate > 0.8 else 0.1,
                "at_risk": 0.2 if avg_engagement < 0.5 else 0.1
            }
        elif current_stage == "growth":
            probabilities = {
                "maturity": 0.5 if success_rate > 0.8 else 0.3,
                "at_risk": 0.1 if avg_engagement < 0.6 else 0.05
            }
        elif current_stage == "maturity":
            probabilities = {
                "at_risk": 0.2 if avg_engagement < 0.5 or avg_satisfaction < 0.6 else 0.1
            }
        elif current_stage == "at_risk":
            probabilities = {
                "active": 0.4 if avg_engagement > 0.6 else 0.2,
                "churn": 0.6 if success_rate < 0.4 else 0.3
            }
        
        return probabilities
    
    async def _generate_stage_recommendations(
        self,
        customer_id: str,
        stage: str,
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> List[str]:
        """Generate recommendations based on customer journey stage"""
        
        recommendations = []
        recent_analytics = analytics_history[-5:] if len(analytics_history) >= 5 else analytics_history
        
        avg_engagement = statistics.mean([a.engagement_indicators["engagement_score"] for a in recent_analytics])
        avg_satisfaction = statistics.mean([a.customer_satisfaction_estimate for a in recent_analytics])
        
        if stage == "onboarding":
            if avg_engagement < 0.6:
                recommendations.append("Increase onboarding support and guidance")
            if avg_satisfaction < 0.7:
                recommendations.append("Improve initial user experience and response quality")
            recommendations.append("Introduce key features gradually")
            
        elif stage == "adoption":
            if avg_engagement > 0.8:
                recommendations.append("Introduce advanced features to drive growth")
            else:
                recommendations.append("Focus on feature adoption and training")
            recommendations.append("Monitor usage patterns for optimization opportunities")
            
        elif stage == "growth":
            recommendations.append("Identify upsell and cross-sell opportunities")
            recommendations.append("Gather success stories and case studies")
            if avg_satisfaction > 0.8:
                recommendations.append("Request referrals and reviews")
                
        elif stage == "maturity":
            recommendations.append("Focus on retention and loyalty programs")
            recommendations.append("Identify innovation opportunities")
            recommendations.append("Leverage as customer advocate")
            
        elif stage == "at_risk":
            recommendations.append("URGENT: Implement retention strategy")
            recommendations.append("Schedule success manager check-in")
            recommendations.append("Identify and address pain points")
            if avg_satisfaction < 0.6:
                recommendations.append("Investigate satisfaction issues immediately")
        
        return recommendations
    
    def _identify_transition_triggers(
        self, 
        stage: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> List[str]:
        """Identify what might trigger transition to next stage"""
        
        triggers = []
        
        if stage == "onboarding":
            triggers = [
                "Complete 5+ successful interactions",
                "Use voice features consistently for 1 week",
                "Achieve >70% satisfaction score"
            ]
        elif stage == "adoption":
            triggers = [
                "Maintain >80% engagement for 2 weeks",
                "Generate high business value (>70 points average)",
                "Use advanced features"
            ]
        elif stage == "growth":
            triggers = [
                "Consistent high satisfaction (>0.8)",
                "Regular usage pattern established",
                "Business value creation demonstrated"
            ]
        elif stage == "maturity":
            triggers = [
                "Declining engagement or satisfaction",
                "Reduced usage frequency",
                "Support ticket increase"
            ]
        elif stage == "at_risk":
            triggers = [
                "Improved response quality",
                "Successful support intervention",
                "Feature adoption increase"
            ]
        
        return triggers
    
    def _calculate_stage_metrics(
        self, 
        stage: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> Dict[str, Any]:
        """Calculate stage-specific metrics"""
        
        metrics = {}
        recent_analytics = analytics_history[-10:] if len(analytics_history) >= 10 else analytics_history
        
        if stage == "onboarding":
            metrics = {
                "onboarding_completion_rate": len(recent_analytics) / 10.0,  # Assuming 10 interactions for onboarding
                "feature_discovery_count": len(set(a.performance_metrics.detected_language for a in recent_analytics)),
                "initial_satisfaction": statistics.mean([a.customer_satisfaction_estimate for a in recent_analytics[:3]])
            }
        elif stage == "adoption":
            metrics = {
                "feature_adoption_rate": 0.7,  # Placeholder - would calculate actual feature usage
                "usage_consistency": len([a for a in recent_analytics if a.engagement_indicators["engagement_score"] > 0.6]) / len(recent_analytics),
                "value_realization": statistics.mean([a.business_value_score for a in recent_analytics])
            }
        elif stage == "growth":
            metrics = {
                "growth_rate": 1.2,  # Placeholder - would calculate actual growth metrics
                "advanced_feature_usage": 0.8,  # Placeholder
                "advocacy_potential": statistics.mean([a.personal_brand_impact for a in recent_analytics])
            }
        elif stage == "maturity":
            metrics = {
                "retention_score": 0.9,  # High retention for mature customers
                "lifetime_value": sum(a.business_value_score for a in analytics_history),
                "loyalty_indicators": len([a for a in recent_analytics if a.customer_satisfaction_estimate > 0.8]) / len(recent_analytics)
            }
        elif stage == "at_risk":
            metrics = {
                "churn_risk_level": statistics.mean([a.churn_risk_score for a in recent_analytics]),
                "intervention_urgency": "high" if any(a.churn_risk_score > 0.7 for a in recent_analytics) else "medium",
                "recovery_potential": 1.0 - statistics.mean([a.churn_risk_score for a in recent_analytics])
            }
        
        return metrics
    
    def _extract_context_around_keyword(self, text: str, keyword: str, window: int) -> str:
        """Extract context window around keyword"""
        keyword_pos = text.find(keyword)
        if keyword_pos == -1:
            return ""
        
        start = max(0, keyword_pos - window)
        end = min(len(text), keyword_pos + len(keyword) + window)
        return text[start:end]
    
    def _analyze_context_sentiment(self, context: str) -> float:
        """Analyze sentiment of context (-1 to 1)"""
        positive_words = ["better", "superior", "excellent", "prefer", "love", "great"]
        negative_words = ["worse", "inferior", "terrible", "hate", "dislike", "awful", "problems"]
        
        context_lower = context.lower()
        positive_count = sum(1 for word in positive_words if word in context_lower)
        negative_count = sum(1 for word in negative_words if word in context_lower)
        
        if positive_count + negative_count == 0:
            return 0.0
        
        return (positive_count - negative_count) / (positive_count + negative_count)
    
    def _extract_market_trends(self, text: str) -> List[str]:
        """Extract market trends mentioned in conversation"""
        trend_keywords = {
            "ai_adoption": ["ai", "artificial intelligence", "machine learning", "automation"],
            "remote_work": ["remote", "work from home", "distributed team", "virtual"],
            "digital_transformation": ["digital", "cloud", "saas", "transformation"],
            "customer_experience": ["customer experience", "cx", "user experience", "ux"],
            "data_analytics": ["analytics", "business intelligence", "data-driven", "insights"]
        }
        
        trends = []
        text_lower = text.lower()
        
        for trend, keywords in trend_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                trends.append(trend)
        
        return trends
    
    def _extract_pricing_intelligence(self, text: str) -> Dict[str, Any]:
        """Extract pricing intelligence from conversation"""
        # Placeholder for pricing intelligence extraction
        # In production, would use NLP to extract pricing information
        
        pricing_intel = {}
        
        if "price" in text.lower() or "cost" in text.lower() or "$" in text:
            pricing_intel["pricing_mentioned"] = True
            # Could extract specific pricing information with more sophisticated NLP
        
        return pricing_intel
    
    def _extract_pain_points(self, text: str) -> List[str]:
        """Extract customer pain points from conversation"""
        pain_point_indicators = [
            "problem", "issue", "difficult", "challenging", "frustrating",
            "doesn't work", "broken", "slow", "complicated", "confusing"
        ]
        
        pain_points = []
        text_lower = text.lower()
        
        for indicator in pain_point_indicators:
            if indicator in text_lower:
                # Extract context around pain point
                context = self._extract_context_around_keyword(text_lower, indicator, 30)
                pain_points.append(context.strip())
        
        return pain_points
    
    def _identify_opportunity_areas(self, pain_points: List[str]) -> List[str]:
        """Identify opportunity areas based on pain points"""
        opportunities = []
        
        for pain_point in pain_points:
            pain_lower = pain_point.lower()
            
            if "slow" in pain_lower or "performance" in pain_lower:
                opportunities.append("Performance optimization")
            elif "complicated" in pain_lower or "confusing" in pain_lower:
                opportunities.append("User experience improvement")
            elif "integration" in pain_lower or "connect" in pain_lower:
                opportunities.append("Integration capabilities")
            elif "support" in pain_lower or "help" in pain_lower:
                opportunities.append("Customer support enhancement")
        
        return list(set(opportunities))  # Remove duplicates
    
    def _identify_differentiation_opportunities(
        self, 
        competitors: List[str], 
        pain_points: List[str]
    ) -> List[str]:
        """Identify differentiation opportunities"""
        opportunities = []
        
        if competitors:
            opportunities.append("Highlight unique voice AI capabilities")
            opportunities.append("Emphasize personal brand enhancement features")
        
        if pain_points:
            opportunities.append("Address unmet needs in market")
            opportunities.append("Develop solutions for common pain points")
        
        opportunities.append("Focus on bilingual capabilities")
        opportunities.append("Emphasize real-time analytics and insights")
        
        return opportunities
    
    async def _update_business_metrics(self):
        """Update overall business metrics"""
        total_customers = len(self.customer_analytics)
        
        # Active customers (interacted in last 30 days)
        cutoff_date = datetime.now() - timedelta(days=30)
        active_customers = sum(
            1 for analytics_list in self.customer_analytics.values()
            if any(a.timestamp > cutoff_date for a in analytics_list)
        )
        
        # High value customers (high business value scores)
        high_value_customers = sum(
            1 for analytics_list in self.customer_analytics.values()
            if statistics.mean([a.business_value_score for a in analytics_list[-5:]]) > 70
        )
        
        # At risk customers
        at_risk_customers = sum(
            1 for customer_id, journey_stage in self.customer_journey_stages.items()
            if journey_stage.current_stage == "at_risk"
        )
        
        # Calculate revenue opportunity (placeholder)
        total_revenue_opportunity = high_value_customers * 1000.0  # Simplified calculation
        
        self.business_metrics.update({
            "total_customers": total_customers,
            "active_customers": active_customers,
            "high_value_customers": high_value_customers,
            "at_risk_customers": at_risk_customers,
            "total_revenue_opportunity": total_revenue_opportunity,
            "customer_health_score": (active_customers / max(1, total_customers)) * 100
        })
        
        # Update Prometheus metrics
        self.business_value_gauge.labels(
            customer_segment="all",
            value_type="total_opportunity"
        ).set(total_revenue_opportunity)
        
        logger.debug("Business metrics updated",
                    total_customers=total_customers,
                    active_customers=active_customers,
                    high_value_customers=high_value_customers)
    
    def _should_generate_insights(self, customer_id: str) -> bool:
        """Determine if insights should be generated for customer"""
        analytics_count = len(self.customer_analytics[customer_id])
        
        # Generate insights every 10 interactions or every 4 hours
        if analytics_count % 10 == 0:
            return True
        
        if self.insight_generation_stats["last_generation_time"]:
            time_since_last = datetime.now() - self.insight_generation_stats["last_generation_time"]
            if time_since_last.total_seconds() > self.insight_generation_interval * 3600:
                return True
        
        return False
    
    async def _generate_customer_insights(self, customer_id: str):
        """Generate business intelligence insights for specific customer"""
        
        start_time = datetime.now()
        analytics_history = self.customer_analytics[customer_id]
        
        insights = []
        
        # Trend analysis insights
        if len(analytics_history) >= 10:
            trend_insight = await self._analyze_customer_trends(customer_id, analytics_history)
            if trend_insight:
                insights.append(trend_insight)
        
        # Engagement insights
        engagement_insight = await self._analyze_engagement_patterns(customer_id, analytics_history)
        if engagement_insight:
            insights.append(engagement_insight)
        
        # Value optimization insights
        value_insight = await self._analyze_value_optimization(customer_id, analytics_history)
        if value_insight:
            insights.append(value_insight)
        
        # Cost optimization insights
        cost_insight = await self._analyze_cost_optimization(customer_id, analytics_history)
        if cost_insight:
            insights.append(cost_insight)
        
        # Store generated insights
        self.generated_insights.extend(insights)
        
        # Update metrics
        for insight in insights:
            self.insights_counter.labels(
                insight_type=insight.insight_type,
                impact_level=insight.potential_impact
            ).inc()
        
        # Update generation stats
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        self.insight_generation_stats.update({
            "insights_generated": self.insight_generation_stats["insights_generated"] + len(insights),
            "last_generation_time": datetime.now(),
            "processing_time_avg_ms": (self.insight_generation_stats["processing_time_avg_ms"] + processing_time) / 2
        })
        
        logger.info("Customer insights generated",
                   customer_id=customer_id,
                   insights_count=len(insights),
                   processing_time_ms=processing_time)
    
    async def _analyze_customer_trends(
        self, 
        customer_id: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> Optional[BusinessIntelligenceInsight]:
        """Analyze customer trends and generate insights"""
        
        if len(analytics_history) < 10:
            return None
        
        # Analyze engagement trend
        recent_engagement = [a.engagement_indicators["engagement_score"] for a in analytics_history[-5:]]
        older_engagement = [a.engagement_indicators["engagement_score"] for a in analytics_history[-15:-5]]
        
        recent_avg = statistics.mean(recent_engagement)
        older_avg = statistics.mean(older_engagement)
        
        trend_change = recent_avg - older_avg
        
        if abs(trend_change) > 0.2:  # Significant change
            trend_direction = "increasing" if trend_change > 0 else "declining"
            
            return BusinessIntelligenceInsight(
                insight_id=f"trend_{customer_id}_{int(datetime.now().timestamp())}",
                generated_timestamp=datetime.now(),
                customer_id=customer_id,
                insight_type="trend",
                title=f"Customer Engagement Trend: {trend_direction.title()}",
                description=f"Customer engagement has been {trend_direction} by {abs(trend_change):.2f} points over recent interactions.",
                confidence_score=0.8,
                data_points=[
                    {"metric": "recent_engagement", "value": recent_avg},
                    {"metric": "previous_engagement", "value": older_avg},
                    {"metric": "change", "value": trend_change}
                ],
                metrics_involved=["engagement_score"],
                time_period={"start_date": analytics_history[-15].timestamp, "end_date": analytics_history[-1].timestamp},
                potential_impact="high" if abs(trend_change) > 0.3 else "medium",
                impact_category="engagement" if trend_change > 0 else "retention",
                estimated_value=None,
                recommended_actions=self._get_trend_recommendations(trend_direction, trend_change),
                implementation_priority="high" if trend_change < -0.3 else "medium",
                expected_timeline="1-2 weeks",
                status="new"
            )
        
        return None
    
    def _get_trend_recommendations(self, trend_direction: str, trend_change: float) -> List[str]:
        """Get recommendations based on trend analysis"""
        
        if trend_direction == "declining":
            if trend_change < -0.3:
                return [
                    "URGENT: Schedule customer success check-in",
                    "Review recent interaction quality",
                    "Identify and address pain points",
                    "Consider retention incentives"
                ]
            else:
                return [
                    "Monitor engagement closely",
                    "Proactively reach out for feedback",
                    "Optimize interaction quality"
                ]
        else:  # increasing
            return [
                "Leverage positive momentum",
                "Introduce advanced features",
                "Request testimonial or case study",
                "Identify upsell opportunities"
            ]
    
    async def _analyze_engagement_patterns(
        self, 
        customer_id: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> Optional[BusinessIntelligenceInsight]:
        """Analyze engagement patterns and generate insights"""
        
        if len(analytics_history) < 5:
            return None
        
        # Analyze usage patterns
        interaction_times = [a.timestamp.hour for a in analytics_history[-20:]]
        peak_hours = [hour for hour in range(24) if interaction_times.count(hour) >= 2]
        
        # Analyze language preferences
        languages = [a.performance_metrics.detected_language for a in analytics_history[-10:]]
        language_consistency = len(set(languages)) == 1
        
        # Analyze session lengths
        avg_response_time = statistics.mean([a.performance_metrics.total_response_time for a in analytics_history[-10:]])
        
        recommendations = []
        
        if peak_hours:
            recommendations.append(f"Customer most active during hours: {', '.join(map(str, peak_hours))}")
        
        if not language_consistency:
            recommendations.append("Customer uses multiple languages - ensure consistent quality across languages")
        
        if avg_response_time > 3.0:
            recommendations.append("Response times are high - optimize for better performance")
        
        if recommendations:
            return BusinessIntelligenceInsight(
                insight_id=f"engagement_{customer_id}_{int(datetime.now().timestamp())}",
                generated_timestamp=datetime.now(),
                customer_id=customer_id,
                insight_type="recommendation",
                title="Engagement Pattern Analysis",
                description="Analysis of customer engagement patterns reveals optimization opportunities.",
                confidence_score=0.7,
                data_points=[
                    {"metric": "peak_hours", "value": peak_hours},
                    {"metric": "language_consistency", "value": language_consistency},
                    {"metric": "avg_response_time", "value": avg_response_time}
                ],
                metrics_involved=["engagement_score", "response_time", "language_usage"],
                time_period={"start_date": analytics_history[-10].timestamp, "end_date": analytics_history[-1].timestamp},
                potential_impact="medium",
                impact_category="efficiency",
                estimated_value=None,
                recommended_actions=recommendations,
                implementation_priority="medium",
                expected_timeline="1 week",
                status="new"
            )
        
        return None
    
    async def _analyze_value_optimization(
        self, 
        customer_id: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> Optional[BusinessIntelligenceInsight]:
        """Analyze value optimization opportunities"""
        
        if len(analytics_history) < 5:
            return None
        
        recent_value_scores = [a.business_value_score for a in analytics_history[-10:]]
        avg_value = statistics.mean(recent_value_scores)
        
        # Check for value optimization opportunities
        if avg_value < 50:  # Low business value
            return BusinessIntelligenceInsight(
                insight_id=f"value_{customer_id}_{int(datetime.now().timestamp())}",
                generated_timestamp=datetime.now(),
                customer_id=customer_id,
                insight_type="opportunity",
                title="Business Value Optimization Opportunity",
                description=f"Current average business value score is {avg_value:.1f}. Significant improvement potential identified.",
                confidence_score=0.8,
                data_points=[{"metric": "avg_business_value", "value": avg_value}],
                metrics_involved=["business_value_score"],
                time_period={"start_date": analytics_history[-10].timestamp, "end_date": analytics_history[-1].timestamp},
                potential_impact="high",
                impact_category="revenue_opportunity",
                estimated_value=1000.0,  # Estimated value improvement
                recommended_actions=[
                    "Analyze low-value interactions for improvement opportunities",
                    "Implement value-enhancing features",
                    "Provide additional training or guidance",
                    "Focus on high-impact use cases"
                ],
                implementation_priority="high",
                expected_timeline="2-4 weeks",
                status="new"
            )
        
        return None
    
    async def _analyze_cost_optimization(
        self, 
        customer_id: str, 
        analytics_history: List[VoiceInteractionAnalytics]
    ) -> Optional[BusinessIntelligenceInsight]:
        """Analyze cost optimization opportunities"""
        
        if len(analytics_history) < 5:
            return None
        
        recent_costs = [sum(a.cost_breakdown.values()) for a in analytics_history[-10:]]
        avg_cost = statistics.mean(recent_costs)
        
        # Check if costs are high relative to value
        recent_values = [a.business_value_score for a in analytics_history[-10:]]
        avg_value = statistics.mean(recent_values)
        
        cost_per_value = avg_cost / max(1, avg_value) * 100  # Cost per business value point
        
        if cost_per_value > 0.05:  # Threshold for cost optimization
            return BusinessIntelligenceInsight(
                insight_id=f"cost_{customer_id}_{int(datetime.now().timestamp())}",
                generated_timestamp=datetime.now(),
                customer_id=customer_id,
                insight_type="recommendation",
                title="Cost Optimization Opportunity",
                description=f"Cost-to-value ratio is {cost_per_value:.3f}. Optimization recommended.",
                confidence_score=0.7,
                data_points=[
                    {"metric": "avg_cost", "value": avg_cost},
                    {"metric": "cost_per_value", "value": cost_per_value}
                ],
                metrics_involved=["cost_breakdown", "business_value_score"],
                time_period={"start_date": analytics_history[-10].timestamp, "end_date": analytics_history[-1].timestamp},
                potential_impact="medium",
                impact_category="cost_savings",
                estimated_value=avg_cost * 0.3 * 30,  # 30% savings over 30 interactions
                recommended_actions=[
                    "Optimize response length and quality",
                    "Improve first-response accuracy",
                    "Implement cost-efficient processing",
                    "Review interaction patterns for efficiency"
                ],
                implementation_priority="medium",
                expected_timeline="2-3 weeks",
                status="new"
            )
        
        return None
    
    def _get_customer_segment(self, customer_id: str) -> str:
        """Get customer segment for analytics"""
        journey_stage = self.customer_journey_stages.get(customer_id)
        
        if not journey_stage:
            return "new"
        
        stage = journey_stage.current_stage
        engagement = journey_stage.engagement_level
        
        if stage in ["growth", "maturity"] and engagement > 0.8:
            return "high_value"
        elif stage == "at_risk":
            return "at_risk"
        elif engagement > 0.6:
            return "engaged"
        else:
            return "active"
    
    async def calculate_customer_roi(
        self, 
        customer_id: str, 
        period_days: int = 30
    ) -> ROIMeasurement:
        """Calculate ROI for specific customer"""
        
        cutoff_date = datetime.now() - timedelta(days=period_days)
        customer_analytics = [
            a for a in self.customer_analytics.get(customer_id, [])
            if a.timestamp > cutoff_date
        ]
        
        if not customer_analytics:
            raise ValueError(f"No analytics data for customer {customer_id} in last {period_days} days")
        
        # Calculate investment (costs)
        total_interaction_cost = sum(sum(a.cost_breakdown.values()) for a in customer_analytics)
        infrastructure_allocation = len(customer_analytics) * 0.01  # $0.01 per interaction
        total_investment = total_interaction_cost + infrastructure_allocation
        
        # Calculate returns (benefits)
        # Time saved estimation: assume each successful interaction saves 15 minutes
        successful_interactions = [a for a in customer_analytics if a.performance_metrics.success]
        time_saved_hours = len(successful_interactions) * 0.25  # 15 minutes = 0.25 hours
        
        # Assume customer's hourly rate is $50 (would be configurable in production)
        hourly_rate = 50.0
        time_saved_value = time_saved_hours * hourly_rate
        
        # Business value estimation
        avg_business_value = statistics.mean([a.business_value_score for a in customer_analytics])
        business_value_monetary = avg_business_value * 2.0  # $2 per business value point
        
        # Total return
        total_return = time_saved_value + business_value_monetary
        
        # Calculate ROI
        roi_percentage = ((total_return - total_investment) / max(0.01, total_investment)) * 100
        payback_period = None
        if total_return > 0:
            daily_return = total_return / period_days
            payback_period = total_investment / daily_return if daily_return > 0 else None
        
        roi_measurement = ROIMeasurement(
            measurement_id=f"roi_{customer_id}_{int(datetime.now().timestamp())}",
            customer_id=customer_id,
            measurement_period_start=cutoff_date,
            measurement_period_end=datetime.now(),
            total_voice_interaction_cost=total_interaction_cost,
            infrastructure_allocation=infrastructure_allocation,
            development_cost_allocation=0.0,  # Would allocate development costs
            support_cost_allocation=0.0,  # Would allocate support costs
            total_investment=total_investment,
            time_saved_hours=time_saved_hours,
            time_saved_value=time_saved_value,
            process_efficiency_gains=business_value_monetary,
            decision_quality_improvement_value=0.0,  # Would calculate if available
            customer_satisfaction_value=0.0,  # Would monetize satisfaction
            brand_enhancement_value=0.0,  # Would calculate brand impact value
            total_quantified_return=total_return,
            roi_percentage=roi_percentage,
            payback_period_days=payback_period,
            qualitative_benefits=[
                "Improved response time",
                "24/7 availability",
                "Consistent service quality",
                "Reduced manual effort"
            ],
            strategic_value="high" if roi_percentage > 200 else "medium" if roi_percentage > 100 else "low",
            measurement_confidence=0.8,
            validation_method="behavioral_analysis",
            validated_by=None,
            validation_date=None
        )
        
        self.roi_measurements.append(roi_measurement)
        
        # Update metrics
        self.roi_gauge.labels(
            customer_segment=self._get_customer_segment(customer_id),
            measurement_period=f"{period_days}d"
        ).set(roi_percentage)
        
        logger.info("Customer ROI calculated",
                   customer_id=customer_id,
                   roi_percentage=roi_percentage,
                   total_investment=total_investment,
                   total_return=total_return)
        
        return roi_measurement
    
    def get_business_intelligence_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive business intelligence dashboard data"""
        
        # Recent insights
        recent_insights = sorted(
            [i for i in self.generated_insights if i.status in ["new", "reviewed"]],
            key=lambda x: x.generated_timestamp,
            reverse=True
        )[:10]
        
        # Competitive intelligence summary
        competitive_summary = defaultdict(int)
        for intel in self.competitive_intelligence[-50:]:  # Last 50 records
            for competitor in intel.competitors_mentioned:
                competitive_summary[competitor] += 1
        
        # Customer journey distribution
        journey_distribution = defaultdict(int)
        for stage_info in self.customer_journey_stages.values():
            journey_distribution[stage_info.current_stage] += 1
        
        # ROI summary
        recent_roi = [roi for roi in self.roi_measurements if roi.measurement_period_start > datetime.now() - timedelta(days=30)]
        avg_roi = statistics.mean([roi.roi_percentage for roi in recent_roi]) if recent_roi else 0
        
        return {
            "business_metrics": self.business_metrics,
            "customer_journey": {
                "stage_distribution": dict(journey_distribution),
                "at_risk_count": journey_distribution["at_risk"],
                "high_value_opportunities": journey_distribution["growth"] + journey_distribution["maturity"]
            },
            "recent_insights": [
                {
                    "title": insight.title,
                    "type": insight.insight_type,
                    "impact": insight.potential_impact,
                    "customer_id": insight.customer_id,
                    "generated": insight.generated_timestamp.isoformat(),
                    "actions": insight.recommended_actions[:2]  # First 2 actions
                }
                for insight in recent_insights
            ],
            "competitive_intelligence": {
                "competitor_mentions": dict(competitive_summary),
                "total_intelligence_records": len(self.competitive_intelligence),
                "recent_trends": []  # Would analyze trends
            },
            "roi_analysis": {
                "average_roi_percentage": round(avg_roi, 1),
                "total_measurements": len(self.roi_measurements),
                "high_roi_customers": len([roi for roi in recent_roi if roi.roi_percentage > 200]),
                "roi_trend": "stable"  # Would calculate trend
            },
            "recommendations": self._get_strategic_recommendations(),
            "alerts": self._get_high_priority_alerts()
        }
    
    def _get_strategic_recommendations(self) -> List[str]:
        """Get strategic recommendations based on BI analysis"""
        recommendations = []
        
        # Customer journey recommendations
        at_risk_count = sum(1 for stage in self.customer_journey_stages.values() if stage.current_stage == "at_risk")
        if at_risk_count > 0:
            recommendations.append(f"Implement retention strategy for {at_risk_count} at-risk customers")
        
        # Growth opportunities
        growth_customers = sum(1 for stage in self.customer_journey_stages.values() if stage.current_stage == "growth")
        if growth_customers > 0:
            recommendations.append(f"Focus on upselling to {growth_customers} growth-stage customers")
        
        # Competitive positioning
        if self.competitive_intelligence:
            recommendations.append("Leverage competitive intelligence to enhance positioning")
        
        # ROI optimization
        recent_roi = [roi for roi in self.roi_measurements if roi.measurement_period_start > datetime.now() - timedelta(days=30)]
        if recent_roi:
            low_roi_count = len([roi for roi in recent_roi if roi.roi_percentage < 100])
            if low_roi_count > 0:
                recommendations.append(f"Optimize value delivery for {low_roi_count} low-ROI customers")
        
        return recommendations
    
    def _get_high_priority_alerts(self) -> List[Dict[str, Any]]:
        """Get high-priority business intelligence alerts"""
        alerts = []
        
        # At-risk customer alerts
        for customer_id, stage in self.customer_journey_stages.items():
            if stage.current_stage == "at_risk":
                alerts.append({
                    "type": "customer_at_risk",
                    "severity": "high",
                    "customer_id": customer_id,
                    "message": f"Customer {customer_id} is at risk of churn",
                    "actions": stage.stage_recommendations[:2]
                })
        
        # Competitive intelligence alerts
        recent_competitive = [
            intel for intel in self.competitive_intelligence
            if intel.collected_timestamp > datetime.now() - timedelta(hours=24)
        ]
        
        if recent_competitive:
            competitor_mentions = {}
            for intel in recent_competitive:
                for competitor in intel.competitors_mentioned:
                    competitor_mentions[competitor] = competitor_mentions.get(competitor, 0) + 1
            
            for competitor, count in competitor_mentions.items():
                if count >= 3:  # Multiple mentions in 24h
                    alerts.append({
                        "type": "competitive_activity",
                        "severity": "medium",
                        "message": f"Increased mentions of {competitor} ({count} times in 24h)",
                        "competitor": competitor,
                        "mention_count": count
                    })
        
        return alerts

# Global business intelligence instance
voice_business_intelligence = VoiceBusinessIntelligence()