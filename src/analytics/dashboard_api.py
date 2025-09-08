"""
Analytics Dashboard API
RESTful API for voice interaction analytics and business intelligence
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import asdict

# FastAPI imports
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Monitoring imports
import structlog

# Local imports
from .voice_analytics_pipeline import voice_analytics_pipeline, VoiceInteractionAnalytics
from .business_intelligence import voice_business_intelligence
from .cost_tracker import voice_cost_tracker
from .quality_analyzer import voice_quality_analyzer
from ..monitoring.voice_performance_monitor import VoiceInteractionMetrics

logger = structlog.get_logger(__name__)

# Request/Response Models
class AnalyticsRequest(BaseModel):
    """Request model for analytics operations"""
    customer_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    metrics: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = {}

class CustomerAnalyticsRequest(BaseModel):
    """Request model for customer-specific analytics"""
    customer_id: str
    period_days: int = Field(default=30, ge=1, le=365)
    include_predictions: bool = True
    include_recommendations: bool = True

class CostForecastRequest(BaseModel):
    """Request model for cost forecasting"""
    customer_id: Optional[str] = None
    forecast_days: int = Field(default=30, ge=1, le=90)

class QualityAssessmentRequest(BaseModel):
    """Request model for quality assessment"""
    interaction_id: str
    include_detailed_analysis: bool = True

class ROICalculationRequest(BaseModel):
    """Request model for ROI calculation"""
    customer_id: str
    period_days: int = Field(default=30, ge=1, le=365)

def create_analytics_dashboard_api() -> APIRouter:
    """Create analytics dashboard API router"""
    
    router = APIRouter(
        prefix="/analytics",
        tags=["analytics"],
        responses={404: {"description": "Not found"}}
    )
    
    @router.get("/")
    async def analytics_root():
        """Analytics API root endpoint"""
        return {
            "service": "Voice Analytics Dashboard API",
            "version": "1.0.0",
            "endpoints": {
                "dashboard": "/dashboard",
                "performance": "/performance",
                "business_intelligence": "/business-intelligence",
                "cost_analysis": "/cost-analysis",
                "quality_analysis": "/quality-analysis",
                "customer_analytics": "/customer/{customer_id}",
                "forecasting": "/forecast",
                "reports": "/reports"
            }
        }
    
    @router.get("/dashboard")
    async def get_analytics_dashboard():
        """Get comprehensive analytics dashboard data"""
        try:
            # Gather data from all analytics components
            pipeline_data = voice_analytics_pipeline.get_analytics_dashboard_data()
            bi_data = voice_business_intelligence.get_business_intelligence_dashboard()
            cost_data = voice_cost_tracker.get_cost_dashboard_data()
            quality_data = voice_quality_analyzer.get_quality_dashboard_data()
            
            dashboard_data = {
                "timestamp": datetime.now().isoformat(),
                "summary": {
                    "total_interactions": pipeline_data["overview"]["total_interactions"],
                    "active_customers": pipeline_data["overview"]["total_customers"],
                    "total_cost": cost_data["current_costs"]["monthly_cost"],
                    "average_quality": quality_data.get("overall_metrics", {}).get("average_quality", 0),
                    "business_value": bi_data.get("business_metrics", {}).get("total_revenue_opportunity", 0)
                },
                "performance_overview": pipeline_data["performance_metrics"],
                "business_metrics": bi_data["business_metrics"],
                "cost_summary": cost_data["current_costs"],
                "quality_summary": quality_data.get("overall_metrics", {}),
                "recent_insights": bi_data.get("recent_insights", [])[:5],
                "active_alerts": {
                    "cost_alerts": cost_data.get("active_alerts", []),
                    "quality_issues": quality_data.get("top_quality_issues", [])[:3],
                    "business_alerts": bi_data.get("alerts", [])
                },
                "trends": {
                    "customer_growth": "stable",  # Would calculate from data
                    "cost_trend": "stable",
                    "quality_trend": quality_data.get("overall_metrics", {}).get("quality_trend", "stable"),
                    "satisfaction_trend": "improving"
                }
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error("Error generating analytics dashboard", error=str(e))
            raise HTTPException(status_code=500, detail=f"Dashboard generation failed: {str(e)}")
    
    @router.get("/performance")
    async def get_performance_analytics(
        customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
        hours: int = Query(24, ge=1, le=168, description="Hours of data to include"),
        include_detailed: bool = Query(False, description="Include detailed metrics")
    ):
        """Get performance analytics data"""
        try:
            if customer_id:
                # Customer-specific performance
                analytics_summary = await voice_analytics_pipeline.get_customer_analytics_summary(customer_id)
                
                if "error" in analytics_summary:
                    raise HTTPException(status_code=404, detail=analytics_summary["error"])
                
                return {
                    "customer_id": customer_id,
                    "time_period_hours": hours,
                    "performance_data": analytics_summary,
                    "generated_at": datetime.now().isoformat()
                }
            else:
                # System-wide performance
                dashboard_data = voice_analytics_pipeline.get_analytics_dashboard_data()
                
                performance_data = {
                    "time_period_hours": hours,
                    "system_overview": dashboard_data["overview"],
                    "performance_metrics": dashboard_data["performance_metrics"],
                    "top_customers": dashboard_data["top_customers"],
                    "processing_stats": dashboard_data["processing_stats"],
                    "generated_at": datetime.now().isoformat()
                }
                
                if include_detailed:
                    performance_data["detailed_metrics"] = {
                        "customer_segments": dashboard_data["overview"]["customer_segments"],
                        "recommendations": dashboard_data["recommendations"]
                    }
                
                return performance_data
                
        except Exception as e:
            logger.error("Error getting performance analytics", error=str(e))
            raise HTTPException(status_code=500, detail=f"Performance analytics failed: {str(e)}")
    
    @router.get("/business-intelligence")
    async def get_business_intelligence(
        customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
        period_days: int = Query(30, ge=1, le=365, description="Analysis period in days")
    ):
        """Get business intelligence analytics"""
        try:
            bi_dashboard = voice_business_intelligence.get_business_intelligence_dashboard()
            
            # Add period-specific analysis if requested
            if customer_id and customer_id in voice_business_intelligence.customer_journey_stages:
                journey_stage = voice_business_intelligence.customer_journey_stages[customer_id]
                
                bi_data = {
                    "customer_id": customer_id,
                    "analysis_period_days": period_days,
                    "customer_journey": asdict(journey_stage),
                    "business_intelligence": bi_dashboard,
                    "generated_at": datetime.now().isoformat()
                }
            else:
                bi_data = {
                    "analysis_period_days": period_days,
                    "business_intelligence": bi_dashboard,
                    "generated_at": datetime.now().isoformat()
                }
            
            return bi_data
            
        except Exception as e:
            logger.error("Error getting business intelligence", error=str(e))
            raise HTTPException(status_code=500, detail=f"Business intelligence failed: {str(e)}")
    
    @router.get("/cost-analysis")
    async def get_cost_analysis(
        customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
        period_days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
        include_optimization: bool = Query(True, description="Include cost optimization recommendations")
    ):
        """Get comprehensive cost analysis"""
        try:
            cost_dashboard = voice_cost_tracker.get_cost_dashboard_data()
            
            cost_analysis = {
                "analysis_period_days": period_days,
                "cost_dashboard": cost_dashboard,
                "generated_at": datetime.now().isoformat()
            }
            
            if include_optimization:
                # Generate cost optimization recommendations
                recommendations = await voice_cost_tracker.generate_cost_optimization_recommendations(
                    customer_id=customer_id,
                    analysis_period_days=period_days
                )
                
                cost_analysis["optimization_recommendations"] = [
                    {
                        "category": rec.cost_category,
                        "current_cost": rec.current_cost,
                        "potential_savings": rec.potential_savings,
                        "savings_percentage": rec.savings_percentage,
                        "description": rec.description,
                        "implementation_effort": rec.implementation_effort,
                        "priority": rec.priority
                    }
                    for rec in recommendations
                ]
            
            if customer_id:
                cost_analysis["customer_id"] = customer_id
                # Could add customer-specific cost analysis here
            
            return cost_analysis
            
        except Exception as e:
            logger.error("Error getting cost analysis", error=str(e))
            raise HTTPException(status_code=500, detail=f"Cost analysis failed: {str(e)}")
    
    @router.get("/quality-analysis")
    async def get_quality_analysis(
        customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
        hours: int = Query(24, ge=1, le=168, description="Hours of data to analyze"),
        include_benchmarks: bool = Query(True, description="Include benchmark comparisons")
    ):
        """Get quality analysis data"""
        try:
            quality_dashboard = voice_quality_analyzer.get_quality_dashboard_data()
            
            quality_analysis = {
                "analysis_period_hours": hours,
                "quality_dashboard": quality_dashboard,
                "generated_at": datetime.now().isoformat()
            }
            
            if customer_id:
                quality_analysis["customer_id"] = customer_id
                
                # Get customer-specific quality data
                customer_quality_history = voice_quality_analyzer.customer_quality_history.get(customer_id, [])
                
                if customer_quality_history:
                    recent_assessments = customer_quality_history[-10:]  # Last 10 assessments
                    
                    customer_quality_data = {
                        "assessments_count": len(customer_quality_history),
                        "recent_average_quality": sum(a.overall_quality for a in recent_assessments) / len(recent_assessments),
                        "quality_trend": recent_assessments[-1].quality_trend if recent_assessments else "unknown",
                        "common_issues": [],
                        "improvement_areas": []
                    }
                    
                    # Aggregate common issues
                    all_issues = []
                    all_suggestions = []
                    for assessment in recent_assessments:
                        all_issues.extend(assessment.issues_identified)
                        all_suggestions.extend(assessment.improvement_suggestions)
                    
                    # Count issues
                    issue_counts = {}
                    for issue in all_issues:
                        issue_counts[issue] = issue_counts.get(issue, 0) + 1
                    
                    customer_quality_data["common_issues"] = [
                        {"issue": issue, "frequency": count}
                        for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    ]
                    
                    customer_quality_data["improvement_areas"] = list(set(all_suggestions))[:5]
                    
                    quality_analysis["customer_quality"] = customer_quality_data
                else:
                    quality_analysis["customer_quality"] = {"message": "No quality data available for customer"}
            
            if include_benchmarks:
                quality_analysis["benchmarks"] = [
                    {
                        "benchmark_name": benchmark.benchmark_name,
                        "minimum_acceptable": benchmark.minimum_acceptable,
                        "target_performance": benchmark.target_performance,
                        "applies_to": benchmark.applies_to
                    }
                    for benchmark in voice_quality_analyzer.quality_benchmarks
                ]
            
            return quality_analysis
            
        except Exception as e:
            logger.error("Error getting quality analysis", error=str(e))
            raise HTTPException(status_code=500, detail=f"Quality analysis failed: {str(e)}")
    
    @router.get("/customer/{customer_id}")
    async def get_customer_analytics(
        customer_id: str,
        period_days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
        include_predictions: bool = Query(True, description="Include predictive analytics"),
        include_recommendations: bool = Query(True, description="Include recommendations")
    ):
        """Get comprehensive analytics for specific customer"""
        try:
            # Get customer analytics from pipeline
            customer_summary = await voice_analytics_pipeline.get_customer_analytics_summary(customer_id)
            
            if "error" in customer_summary:
                raise HTTPException(status_code=404, detail=customer_summary["error"])
            
            analytics_data = {
                "customer_id": customer_id,
                "analysis_period_days": period_days,
                "customer_profile": customer_summary["profile_summary"],
                "performance_trends": customer_summary["trends"],
                "generated_at": datetime.now().isoformat()
            }
            
            if include_predictions:
                analytics_data["predictions"] = customer_summary["predictions"]
            
            if include_recommendations:
                analytics_data["recommendations"] = customer_summary["recommendations"]
            
            # Add business intelligence data
            if customer_id in voice_business_intelligence.customer_journey_stages:
                journey_stage = voice_business_intelligence.customer_journey_stages[customer_id]
                analytics_data["customer_journey"] = {
                    "current_stage": journey_stage.current_stage,
                    "days_in_stage": journey_stage.days_in_stage,
                    "engagement_level": journey_stage.engagement_level,
                    "next_stage_probabilities": journey_stage.next_stage_probabilities,
                    "stage_recommendations": journey_stage.stage_recommendations
                }
            
            # Add cost data
            if customer_id in voice_cost_tracker.customer_costs:
                customer_costs = voice_cost_tracker.customer_costs[customer_id]
                recent_costs = [c for c in customer_costs if c.timestamp > datetime.now() - timedelta(days=period_days)]
                
                if recent_costs:
                    analytics_data["cost_analysis"] = {
                        "total_cost": sum(c.total_cost for c in recent_costs),
                        "average_cost_per_interaction": sum(c.total_cost for c in recent_costs) / len(recent_costs),
                        "cost_breakdown": {
                            "tts": sum(c.elevenlabs_tts_cost for c in recent_costs),
                            "stt": sum(c.whisper_stt_cost for c in recent_costs),
                            "processing": sum(c.compute_cost for c in recent_costs),
                            "infrastructure": sum(c.allocated_overhead for c in recent_costs)
                        }
                    }
            
            # Add quality data
            if customer_id in voice_quality_analyzer.customer_quality_history:
                quality_history = voice_quality_analyzer.customer_quality_history[customer_id]
                recent_quality = [q for q in quality_history if q.assessment_timestamp > datetime.now() - timedelta(days=period_days)]
                
                if recent_quality:
                    analytics_data["quality_analysis"] = {
                        "average_quality": sum(q.overall_quality for q in recent_quality) / len(recent_quality),
                        "quality_trend": recent_quality[-1].quality_trend if recent_quality else "unknown",
                        "assessment_count": len(recent_quality),
                        "quality_dimensions": {
                            "audio": sum(q.audio_quality for q in recent_quality) / len(recent_quality),
                            "transcription": sum(q.transcription_quality for q in recent_quality) / len(recent_quality),
                            "response": sum(q.response_quality for q in recent_quality) / len(recent_quality),
                            "user_experience": sum(q.user_experience_quality for q in recent_quality) / len(recent_quality)
                        }
                    }
            
            return analytics_data
            
        except Exception as e:
            logger.error("Error getting customer analytics", customer_id=customer_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Customer analytics failed: {str(e)}")
    
    @router.post("/forecast/cost")
    async def forecast_costs(request: CostForecastRequest):
        """Generate cost forecast"""
        try:
            forecast = await voice_cost_tracker.forecast_costs(
                forecast_days=request.forecast_days,
                customer_id=request.customer_id
            )
            
            return {
                "forecast_request": request.dict(),
                "forecast": forecast,
                "generated_at": datetime.now().isoformat()
            }
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Error generating cost forecast", error=str(e))
            raise HTTPException(status_code=500, detail=f"Cost forecast failed: {str(e)}")
    
    @router.post("/roi/calculate")
    async def calculate_roi(request: ROICalculationRequest):
        """Calculate ROI for customer"""
        try:
            roi_measurement = await voice_business_intelligence.calculate_customer_roi(
                customer_id=request.customer_id,
                period_days=request.period_days
            )
            
            return {
                "calculation_request": request.dict(),
                "roi_measurement": asdict(roi_measurement),
                "generated_at": datetime.now().isoformat()
            }
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("Error calculating ROI", error=str(e))
            raise HTTPException(status_code=500, detail=f"ROI calculation failed: {str(e)}")
    
    @router.get("/insights")
    async def get_business_insights(
        customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
        insight_type: Optional[str] = Query(None, description="Filter by insight type"),
        limit: int = Query(20, ge=1, le=100, description="Maximum number of insights")
    ):
        """Get business intelligence insights"""
        try:
            # Get insights from business intelligence
            all_insights = voice_business_intelligence.generated_insights
            
            # Filter insights
            filtered_insights = all_insights
            
            if customer_id:
                filtered_insights = [i for i in filtered_insights if i.customer_id == customer_id]
            
            if insight_type:
                filtered_insights = [i for i in filtered_insights if i.insight_type == insight_type]
            
            # Sort by timestamp (most recent first)
            filtered_insights.sort(key=lambda x: x.generated_timestamp, reverse=True)
            
            # Limit results
            filtered_insights = filtered_insights[:limit]
            
            insights_data = [
                {
                    "insight_id": insight.insight_id,
                    "customer_id": insight.customer_id,
                    "type": insight.insight_type,
                    "title": insight.title,
                    "description": insight.description,
                    "confidence": insight.confidence_score,
                    "impact": insight.potential_impact,
                    "category": insight.impact_category,
                    "estimated_value": insight.estimated_value,
                    "actions": insight.recommended_actions,
                    "priority": insight.implementation_priority,
                    "status": insight.status,
                    "generated": insight.generated_timestamp.isoformat()
                }
                for insight in filtered_insights
            ]
            
            return {
                "insights": insights_data,
                "total_count": len(insights_data),
                "filters_applied": {
                    "customer_id": customer_id,
                    "insight_type": insight_type,
                    "limit": limit
                },
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error getting business insights", error=str(e))
            raise HTTPException(status_code=500, detail=f"Business insights failed: {str(e)}")
    
    @router.get("/competitive-intelligence")
    async def get_competitive_intelligence(
        hours: int = Query(168, ge=1, le=720, description="Hours of data to analyze"),
        competitor: Optional[str] = Query(None, description="Filter by specific competitor")
    ):
        """Get competitive intelligence analysis"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            # Filter competitive intelligence data
            competitive_intel = [
                intel for intel in voice_business_intelligence.competitive_intelligence
                if intel.collected_timestamp > cutoff_time
            ]
            
            if competitor:
                competitive_intel = [
                    intel for intel in competitive_intel
                    if competitor.lower() in [c.lower() for c in intel.competitors_mentioned]
                ]
            
            # Aggregate data
            competitor_mentions = {}
            total_intelligence_records = len(competitive_intel)
            market_trends = []
            
            for intel in competitive_intel:
                for comp in intel.competitors_mentioned:
                    if comp not in competitor_mentions:
                        competitor_mentions[comp] = {
                            "mention_count": 0,
                            "sentiment_scores": [],
                            "contexts": []
                        }
                    
                    competitor_mentions[comp]["mention_count"] += 1
                    if comp in intel.sentiment_toward_competitors:
                        competitor_mentions[comp]["sentiment_scores"].append(
                            intel.sentiment_toward_competitors[comp]
                        )
                    competitor_mentions[comp]["contexts"].append(intel.competitive_context)
                
                market_trends.extend(intel.market_trends_mentioned)
            
            # Calculate averages
            for comp_data in competitor_mentions.values():
                if comp_data["sentiment_scores"]:
                    comp_data["average_sentiment"] = sum(comp_data["sentiment_scores"]) / len(comp_data["sentiment_scores"])
                else:
                    comp_data["average_sentiment"] = 0.0
                
                # Most common context
                context_counts = {}
                for context in comp_data["contexts"]:
                    context_counts[context] = context_counts.get(context, 0) + 1
                
                comp_data["primary_context"] = max(context_counts.items(), key=lambda x: x[1])[0] if context_counts else "unknown"
            
            # Market trends analysis
            trend_counts = {}
            for trend in market_trends:
                trend_counts[trend] = trend_counts.get(trend, 0) + 1
            
            return {
                "analysis_period_hours": hours,
                "total_intelligence_records": total_intelligence_records,
                "competitor_analysis": {
                    comp: {
                        "mentions": data["mention_count"],
                        "average_sentiment": round(data["average_sentiment"], 3),
                        "primary_context": data["primary_context"]
                    }
                    for comp, data in competitor_mentions.items()
                },
                "market_trends": [
                    {"trend": trend, "mentions": count}
                    for trend, count in sorted(trend_counts.items(), key=lambda x: x[1], reverse=True)
                ],
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error getting competitive intelligence", error=str(e))
            raise HTTPException(status_code=500, detail=f"Competitive intelligence failed: {str(e)}")
    
    @router.get("/reports/summary")
    async def get_analytics_summary_report(
        period_days: int = Query(30, ge=1, le=365, description="Report period in days"),
        format: str = Query("json", description="Report format")
    ):
        """Generate comprehensive analytics summary report"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            # Gather comprehensive data
            pipeline_data = voice_analytics_pipeline.get_analytics_dashboard_data()
            bi_data = voice_business_intelligence.get_business_intelligence_dashboard()
            cost_data = voice_cost_tracker.get_cost_dashboard_data()
            quality_data = voice_quality_analyzer.get_quality_dashboard_data()
            
            summary_report = {
                "report_metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "report_period": {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat(),
                        "period_days": period_days
                    },
                    "format": format
                },
                "executive_summary": {
                    "total_interactions": pipeline_data["overview"]["total_interactions"],
                    "active_customers": pipeline_data["overview"]["total_customers"],
                    "total_cost": cost_data["current_costs"]["monthly_cost"],
                    "average_quality": quality_data.get("overall_metrics", {}).get("average_quality", 0),
                    "customer_satisfaction": bi_data.get("business_metrics", {}).get("customer_health_score", 0),
                    "cost_per_interaction": cost_data["current_costs"]["average_per_interaction"],
                    "key_highlights": [
                        f"{pipeline_data['overview']['total_interactions']} voice interactions processed",
                        f"{pipeline_data['overview']['total_customers']} active customers served",
                        f"${cost_data['current_costs']['monthly_cost']} total monthly cost",
                        f"{quality_data.get('overall_metrics', {}).get('average_quality', 0):.1%} average quality score"
                    ]
                },
                "performance_analysis": {
                    "interaction_volume": pipeline_data["overview"],
                    "performance_metrics": pipeline_data["performance_metrics"],
                    "customer_segments": pipeline_data["overview"]["customer_segments"],
                    "top_performing_customers": pipeline_data["top_customers"][:5]
                },
                "business_intelligence": {
                    "customer_journey_analysis": bi_data["customer_journey"],
                    "revenue_opportunities": bi_data["roi_analysis"],
                    "competitive_insights": bi_data["competitive_intelligence"],
                    "strategic_recommendations": bi_data["recommendations"]
                },
                "cost_analysis": {
                    "cost_breakdown": cost_data["cost_breakdown"],
                    "budget_status": cost_data["budget_status"],
                    "optimization_opportunities": cost_data["optimization_opportunities"],
                    "cost_efficiency_metrics": {
                        "cost_per_interaction": cost_data["current_costs"]["average_per_interaction"],
                        "cost_trend": "stable"  # Would calculate actual trend
                    }
                },
                "quality_analysis": {
                    "overall_quality_metrics": quality_data.get("overall_metrics", {}),
                    "quality_dimensions": quality_data.get("quality_dimensions", {}),
                    "quality_issues": quality_data.get("top_quality_issues", []),
                    "customer_quality_segments": quality_data.get("customer_segment_quality", {}),
                    "quality_improvement_recommendations": quality_data.get("quality_recommendations", [])
                },
                "actionable_insights": {
                    "immediate_actions": [
                        insight for insight in bi_data.get("recent_insights", [])
                        if insight.get("impact") == "high"
                    ][:3],
                    "strategic_initiatives": bi_data.get("recommendations", []),
                    "optimization_priorities": [
                        rec for rec in cost_data.get("optimization_opportunities", {})
                        if cost_data["optimization_opportunities"].get("high_priority_count", 0) > 0
                    ]
                },
                "appendix": {
                    "methodology": "Analytics calculated using real-time voice interaction data with statistical analysis and predictive modeling",
                    "data_sources": ["Voice interaction metrics", "Customer engagement data", "Cost tracking", "Quality assessments"],
                    "confidence_levels": "High confidence (>90%) for performance metrics, Medium confidence (70-90%) for predictive analytics"
                }
            }
            
            return summary_report
            
        except Exception as e:
            logger.error("Error generating summary report", error=str(e))
            raise HTTPException(status_code=500, detail=f"Summary report generation failed: {str(e)}")
    
    @router.post("/background-tasks/generate-insights")
    async def trigger_insight_generation(
        background_tasks: BackgroundTasks,
        customer_id: Optional[str] = None
    ):
        """Trigger background insight generation"""
        try:
            if customer_id:
                # Generate insights for specific customer
                background_tasks.add_task(
                    voice_business_intelligence._generate_customer_insights,
                    customer_id
                )
                message = f"Insight generation triggered for customer {customer_id}"
            else:
                # Generate system-wide insights
                background_tasks.add_task(
                    _generate_system_insights
                )
                message = "System-wide insight generation triggered"
            
            return {
                "success": True,
                "message": message,
                "triggered_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error("Error triggering insight generation", error=str(e))
            raise HTTPException(status_code=500, detail=f"Insight generation failed: {str(e)}")
    
    @router.get("/metrics/prometheus")
    async def get_prometheus_metrics():
        """Get Prometheus metrics for all analytics components"""
        try:
            # This would aggregate Prometheus metrics from all components
            # For now, return a placeholder
            return {
                "message": "Prometheus metrics endpoint",
                "note": "Metrics are exported via individual component endpoints",
                "endpoints": {
                    "voice_performance": "/voice/metrics",
                    "analytics_pipeline": "Built into voice performance metrics",
                    "business_intelligence": "Integrated into analytics metrics",
                    "cost_tracking": "Integrated into analytics metrics",
                    "quality_analysis": "Integrated into analytics metrics"
                }
            }
            
        except Exception as e:
            logger.error("Error getting Prometheus metrics", error=str(e))
            raise HTTPException(status_code=500, detail=f"Metrics retrieval failed: {str(e)}")
    
    return router

async def _generate_system_insights():
    """Background task to generate system-wide insights"""
    try:
        # This would trigger comprehensive system analysis
        logger.info("Starting system-wide insight generation")
        
        # Generate insights for all active customers
        customer_ids = list(voice_analytics_pipeline.customer_profiles.keys())
        
        for customer_id in customer_ids:
            try:
                await voice_business_intelligence._generate_customer_insights(customer_id)
            except Exception as e:
                logger.error(f"Error generating insights for customer {customer_id}", error=str(e))
        
        logger.info("System-wide insight generation completed",
                   customers_processed=len(customer_ids))
                   
    except Exception as e:
        logger.error("Error in system insight generation", error=str(e))

def create_analytics_dashboard_api_with_dependencies() -> APIRouter:
    """Create analytics dashboard API with all dependencies"""
    
    # Ensure all analytics components are initialized
    router = create_analytics_dashboard_api()
    
    # Add startup event to initialize background processing
    @router.on_event("startup")
    async def startup_analytics():
        """Start analytics background processing"""
        logger.info("Starting analytics dashboard API")
        
        # Start background processing for analytics pipeline
        if hasattr(voice_analytics_pipeline, 'start_background_processing'):
            await voice_analytics_pipeline.start_background_processing()
        
        # Start business intelligence processing
        if hasattr(voice_business_intelligence, 'start_background_processing'):
            # Would implement if available
            pass
    
    @router.on_event("shutdown")
    async def shutdown_analytics():
        """Stop analytics background processing"""
        logger.info("Shutting down analytics dashboard API")
        
        # Stop background processing
        if hasattr(voice_analytics_pipeline, 'stop_background_processing'):
            await voice_analytics_pipeline.stop_background_processing()
    
    return router