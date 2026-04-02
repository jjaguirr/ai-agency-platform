"""
AI/ML Workflow Template Matching Engine

Uses business insights and semantic analysis to recommend optimal n8n workflow templates:
- Template similarity matching based on business context
- Customization requirement analysis
- ROI and impact estimation for template implementation
- Template-business process alignment scoring
- Dynamic template recommendation based on learned patterns

This bridges the gap between business understanding and practical automation implementation.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class TemplateCategory(Enum):
    SOCIAL_MEDIA = "social_media"
    EMAIL_AUTOMATION = "email_automation"
    DATA_PROCESSING = "data_processing"
    LEAD_MANAGEMENT = "lead_management"
    CUSTOMER_SUPPORT = "customer_support"
    CONTENT_CREATION = "content_creation"
    SCHEDULING = "scheduling"
    REPORTING = "reporting"
    INTEGRATION = "integration"
    NOTIFICATION = "notification"


@dataclass
class WorkflowTemplate:
    """Structured workflow template with AI/ML matching capabilities"""
    template_id: str
    name: str
    description: str
    category: TemplateCategory
    complexity_score: float  # 0.0 to 1.0
    setup_time_minutes: int
    required_integrations: List[str]
    business_patterns: List[str]  # Patterns this template addresses
    automation_impact: Dict[str, float]  # Impact metrics
    customization_difficulty: float  # 0.0 to 1.0
    success_rate: float  # Historical success rate
    roi_metrics: Dict[str, Any]
    tags: List[str]
    prerequisites: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['category'] = self.category.value
        return data


class WorkflowTemplateMatcher:
    """
    AI/ML-powered workflow template matching engine.
    
    Analyzes business context and automatically recommends the most suitable
    workflow templates with customization guidance and ROI projections.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize workflow template matcher.
        
        Args:
            config: Configuration for matching algorithms
        """
        self.config = config or self._default_config()
        
        # Load template library
        self.templates = self._load_template_library()
        self.category_templates = self._organize_by_category()
        
        # Matching algorithms
        self.pattern_weights = self._initialize_pattern_weights()
        self.business_context_cache = {}
        
        # Performance tracking
        self.matching_stats = {
            "recommendations_generated": 0,
            "successful_matches": 0,
            "average_confidence": 0.0,
            "template_usage_stats": {},
            "customer_feedback_scores": []
        }
        
        logger.info(f"Initialized Workflow Template Matcher with {len(self.templates)} templates")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration for template matching"""
        return {
            "similarity_threshold": 0.7,
            "max_recommendations": 5,
            "confidence_threshold": 0.6,
            "customization_weight": 0.3,
            "complexity_weight": 0.2,
            "roi_weight": 0.3,
            "pattern_match_weight": 0.2,
            "enable_learning": True,
            "feedback_integration": True
        }
    
    async def recommend_templates(self, business_insights: Dict[str, Any], 
                                customer_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Recommend workflow templates based on business insights.
        
        Args:
            business_insights: Output from BusinessLearningEngine
            customer_context: Additional customer context (industry, size, etc.)
            
        Returns:
            Dictionary with template recommendations and matching analysis
        """
        start_time = time.time()
        
        try:
            # Extract key information from business insights
            automation_opportunities = business_insights.get("automation_opportunities", [])
            business_entities = business_insights.get("business_entities", [])
            business_patterns = business_insights.get("business_patterns", [])
            
            # Generate template matches for each automation opportunity
            all_recommendations = []
            
            for opportunity in automation_opportunities:
                opportunity_recommendations = await self._match_templates_for_opportunity(
                    opportunity, business_entities, business_patterns, customer_context or {}
                )
                all_recommendations.extend(opportunity_recommendations)
            
            # Global pattern-based recommendations
            global_recommendations = await self._generate_global_recommendations(
                business_insights, customer_context or {}
            )
            all_recommendations.extend(global_recommendations)
            
            # Deduplicate and rank recommendations
            final_recommendations = await self._deduplicate_and_rank(all_recommendations)
            
            # Generate implementation guidance
            implementation_guidance = await self._generate_implementation_guidance(
                final_recommendations, business_insights
            )
            
            # Calculate ROI projections
            roi_analysis = await self._calculate_roi_projections(
                final_recommendations, business_insights, customer_context or {}
            )
            
            processing_time = time.time() - start_time
            
            # Update statistics
            self.matching_stats["recommendations_generated"] += len(final_recommendations)
            if final_recommendations:
                avg_confidence = sum(r["match_confidence"] for r in final_recommendations) / len(final_recommendations)
                self.matching_stats["average_confidence"] = (
                    (self.matching_stats["average_confidence"] * 
                     (self.matching_stats["recommendations_generated"] - len(final_recommendations)) +
                     avg_confidence * len(final_recommendations)) /
                    self.matching_stats["recommendations_generated"]
                )
            
            result = {
                "recommendation_timestamp": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "recommendation_successful": True,
                
                # Core recommendations
                "template_recommendations": final_recommendations[:self.config["max_recommendations"]],
                "total_templates_analyzed": len(self.templates),
                "opportunities_processed": len(automation_opportunities),
                
                # Implementation guidance
                "implementation_guidance": implementation_guidance,
                "recommended_implementation_order": self._recommend_implementation_order(final_recommendations),
                
                # ROI and impact analysis
                "roi_analysis": roi_analysis,
                "estimated_total_impact": self._calculate_total_impact(final_recommendations),
                
                # Matching insights
                "matching_confidence": avg_confidence if final_recommendations else 0.0,
                "customization_complexity": self._assess_overall_customization_complexity(final_recommendations),
                "integration_requirements": self._consolidate_integration_requirements(final_recommendations),
                
                # Performance metadata
                "templates_in_library": len(self.templates),
                "matching_algorithm_version": "1.0",
                "business_context_quality": business_insights.get("extraction_confidence", 0.0)
            }
            
            logger.info(f"Generated {len(final_recommendations)} template recommendations in {processing_time:.3f}s")
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Template recommendation failed: {e}")
            return {
                "recommendation_timestamp": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "recommendation_successful": False,
                "error": str(e),
                "template_recommendations": []
            }
    
    async def _match_templates_for_opportunity(self, opportunity: Dict[str, Any], 
                                             business_entities: List[Dict[str, Any]],
                                             business_patterns: List[Dict[str, Any]],
                                             customer_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Match templates for a specific automation opportunity"""
        recommendations = []
        
        # Extract opportunity characteristics
        opportunity_type = opportunity.get("pattern_type", "")
        automation_score = opportunity.get("automation_score", 0.0)
        complexity = opportunity.get("complexity", 0.5)
        related_entities = opportunity.get("related_entities", [])
        
        # Get tools mentioned in entities
        mentioned_tools = []
        for entity in related_entities:
            if entity.get("entity_type") == "tool_integration":
                mentioned_tools.append(entity.get("value", "").lower())
        
        # Score each template for this opportunity
        for template in self.templates:
            match_score = await self._calculate_template_match_score(
                template, opportunity, mentioned_tools, business_patterns, customer_context
            )
            
            if match_score >= self.config["confidence_threshold"]:
                customization_analysis = await self._analyze_customization_requirements(
                    template, opportunity, related_entities
                )
                
                recommendation = {
                    "template_id": template.template_id,
                    "template_name": template.name,
                    "template_category": template.category.value,
                    "opportunity_id": opportunity.get("id"),
                    "opportunity_title": opportunity.get("title", ""),
                    "match_confidence": match_score,
                    "match_reasons": self._explain_template_match(template, opportunity, mentioned_tools),
                    
                    # Implementation details
                    "setup_complexity": template.complexity_score,
                    "estimated_setup_time": template.setup_time_minutes,
                    "customization_requirements": customization_analysis,
                    "required_integrations": template.required_integrations,
                    
                    # Business impact
                    "automation_impact": template.automation_impact,
                    "expected_roi": await self._estimate_opportunity_roi(template, opportunity),
                    "success_probability": template.success_rate * match_score,
                    
                    # Template metadata
                    "template_description": template.description,
                    "template_tags": template.tags,
                    "prerequisites": template.prerequisites
                }
                recommendations.append(recommendation)
        
        return sorted(recommendations, key=lambda x: x["match_confidence"], reverse=True)
    
    async def _calculate_template_match_score(self, template: WorkflowTemplate,
                                            opportunity: Dict[str, Any], 
                                            mentioned_tools: List[str],
                                            business_patterns: List[Dict[str, Any]],
                                            customer_context: Dict[str, Any]) -> float:
        """Calculate how well a template matches an automation opportunity"""
        
        scores = []
        weights = []
        
        # Pattern matching score
        pattern_score = self._calculate_pattern_match_score(template, opportunity, business_patterns)
        scores.append(pattern_score)
        weights.append(self.config["pattern_match_weight"])
        
        # Tool integration score
        tool_score = self._calculate_tool_integration_score(template, mentioned_tools)
        scores.append(tool_score)
        weights.append(0.25)
        
        # Complexity alignment score (lower complexity preferred for higher automation scores)
        complexity_alignment = 1.0 - abs(template.complexity_score - opportunity.get("complexity", 0.5))
        scores.append(complexity_alignment)
        weights.append(self.config["complexity_weight"])
        
        # ROI potential score
        roi_score = self._calculate_roi_match_score(template, opportunity)
        scores.append(roi_score)
        weights.append(self.config["roi_weight"])
        
        # Customization difficulty (prefer easier customization)
        customization_score = 1.0 - template.customization_difficulty
        scores.append(customization_score)
        weights.append(self.config["customization_weight"])
        
        # Historical success rate
        scores.append(template.success_rate)
        weights.append(0.1)
        
        # Customer context fit
        context_score = self._calculate_context_fit_score(template, customer_context)
        scores.append(context_score)
        weights.append(0.1)
        
        # Weighted average
        total_weight = sum(weights)
        weighted_score = sum(score * weight for score, weight in zip(scores, weights)) / total_weight
        
        return min(1.0, max(0.0, weighted_score))
    
    def _calculate_pattern_match_score(self, template: WorkflowTemplate,
                                     opportunity: Dict[str, Any],
                                     business_patterns: List[Dict[str, Any]]) -> float:
        """Calculate how well template patterns match opportunity patterns"""
        opportunity_type = opportunity.get("pattern_type", "")
        
        # Direct pattern type matching
        direct_match_score = 0.0
        for template_pattern in template.business_patterns:
            if template_pattern.lower() in opportunity_type.lower():
                direct_match_score = 0.8
                break
        
        # Semantic pattern matching
        semantic_score = 0.0
        opportunity_description = opportunity.get("description", "").lower()
        for template_pattern in template.business_patterns:
            if template_pattern.lower() in opportunity_description:
                semantic_score += 0.2
        
        semantic_score = min(semantic_score, 0.6)  # Cap semantic score
        
        return max(direct_match_score, semantic_score)
    
    def _calculate_tool_integration_score(self, template: WorkflowTemplate, 
                                        mentioned_tools: List[str]) -> float:
        """Calculate tool integration alignment score"""
        if not mentioned_tools:
            return 0.5  # Neutral score if no tools mentioned
        
        # Check how many required integrations are covered by mentioned tools
        covered_integrations = 0
        for integration in template.required_integrations:
            for tool in mentioned_tools:
                if tool in integration.lower() or integration.lower() in tool:
                    covered_integrations += 1
                    break
        
        if not template.required_integrations:
            return 0.7  # Good score for templates with no integration requirements
        
        coverage_ratio = covered_integrations / len(template.required_integrations)
        return coverage_ratio
    
    def _calculate_roi_match_score(self, template: WorkflowTemplate, 
                                 opportunity: Dict[str, Any]) -> float:
        """Calculate ROI potential alignment"""
        opportunity_impact = opportunity.get("estimated_impact", {})
        template_impact = template.automation_impact
        
        # Compare impact categories
        impact_alignment = 0.0
        impact_categories = ["time_savings", "error_reduction", "cost_savings", "scalability"]
        
        for category in impact_categories:
            if (category in opportunity_impact and category in template_impact):
                # Simplified alignment calculation
                impact_alignment += 0.25
        
        return impact_alignment
    
    def _calculate_context_fit_score(self, template: WorkflowTemplate, 
                                   customer_context: Dict[str, Any]) -> float:
        """Calculate how well template fits customer context"""
        if not customer_context:
            return 0.5
        
        fit_score = 0.5  # Base score
        
        # Industry alignment
        customer_industry = customer_context.get("industry", "").lower()
        if customer_industry:
            for tag in template.tags:
                if customer_industry in tag.lower():
                    fit_score += 0.3
                    break
        
        # Company size alignment
        company_size = customer_context.get("company_size", "small")
        if company_size == "small" and template.complexity_score < 0.5:
            fit_score += 0.2
        elif company_size in ["medium", "large"] and template.complexity_score > 0.3:
            fit_score += 0.2
        
        return min(1.0, fit_score)
    
    def _explain_template_match(self, template: WorkflowTemplate, 
                              opportunity: Dict[str, Any], 
                              mentioned_tools: List[str]) -> List[str]:
        """Generate human-readable explanations for why template matches"""
        reasons = []
        
        # Pattern matching reasons
        opportunity_type = opportunity.get("pattern_type", "")
        for pattern in template.business_patterns:
            if pattern.lower() in opportunity_type.lower():
                reasons.append(f"Template specifically designed for {pattern} patterns")
        
        # Tool integration reasons
        for tool in mentioned_tools:
            for integration in template.required_integrations:
                if tool in integration.lower():
                    reasons.append(f"Supports {tool} integration mentioned in conversation")
        
        # Complexity alignment
        opp_complexity = opportunity.get("complexity", 0.5)
        if abs(template.complexity_score - opp_complexity) < 0.2:
            reasons.append("Complexity level matches opportunity requirements")
        
        # Impact alignment
        if template.automation_impact.get("time_savings", 0) > 0.7:
            reasons.append("High time-saving potential aligns with process inefficiency")
        
        return reasons[:3]  # Top 3 reasons
    
    async def _analyze_customization_requirements(self, template: WorkflowTemplate,
                                                opportunity: Dict[str, Any],
                                                related_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze what customizations are needed for the template"""
        customizations = {
            "configuration_changes": [],
            "integration_setup": [],
            "workflow_modifications": [],
            "data_mapping": [],
            "estimated_effort": "low"
        }
        
        # Basic configuration
        customizations["configuration_changes"].append("Basic template configuration")
        
        # Integration setup based on mentioned tools
        for entity in related_entities:
            if entity.get("entity_type") == "tool_integration":
                tool_name = entity.get("value", "")
                if any(tool_name.lower() in req.lower() for req in template.required_integrations):
                    customizations["integration_setup"].append(f"Configure {tool_name} connection")
        
        # Workflow modifications based on complexity
        complexity = opportunity.get("complexity", 0.5)
        if complexity > 0.7:
            customizations["workflow_modifications"].append("Complex workflow logic customization")
            customizations["estimated_effort"] = "high"
        elif complexity > 0.4:
            customizations["workflow_modifications"].append("Moderate workflow adjustments")
            customizations["estimated_effort"] = "medium"
        
        # Data mapping requirements
        if template.category in [TemplateCategory.DATA_PROCESSING, TemplateCategory.INTEGRATION]:
            customizations["data_mapping"].append("Configure data field mapping")
        
        return customizations
    
    async def _estimate_opportunity_roi(self, template: WorkflowTemplate, 
                                      opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate ROI for implementing template for this opportunity"""
        base_roi = template.roi_metrics.copy()
        
        # Adjust based on opportunity characteristics
        automation_score = opportunity.get("automation_score", 0.0)
        readiness_score = opportunity.get("readiness_score", 0.0)
        
        # Scale ROI by automation potential
        roi_multiplier = (automation_score + readiness_score) / 2
        
        return {
            "payback_period_weeks": int(base_roi.get("payback_weeks", 4) / max(roi_multiplier, 0.5)),
            "time_saved_per_week_hours": base_roi.get("time_saved_hours", 2) * roi_multiplier,
            "efficiency_gain_percent": int(base_roi.get("efficiency_gain", 30) * roi_multiplier),
            "cost_savings_monthly": base_roi.get("cost_savings", 500) * roi_multiplier,
            "confidence": min(0.9, roi_multiplier)
        }
    
    async def _generate_global_recommendations(self, business_insights: Dict[str, Any],
                                             customer_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate template recommendations based on overall business context"""
        recommendations = []
        
        # Get business patterns summary
        entities = business_insights.get("business_entities", [])
        patterns = business_insights.get("business_patterns", [])
        
        # Tool ecosystem analysis
        tool_entities = [e for e in entities if e.get("entity_type") == "tool_integration"]
        if len(tool_entities) >= 3:
            # Recommend integration templates for multi-tool environments
            integration_templates = [t for t in self.templates if t.category == TemplateCategory.INTEGRATION]
            for template in integration_templates[:2]:  # Top 2 integration templates
                recommendation = {
                    "template_id": template.template_id,
                    "template_name": template.name,
                    "template_category": template.category.value,
                    "opportunity_id": "global_integration_opportunity",
                    "opportunity_title": "Multi-tool Integration Opportunity",
                    "match_confidence": 0.75,
                    "match_reasons": [
                        f"Multiple tools detected ({len(tool_entities)} tools)",
                        "Integration template reduces tool fragmentation",
                        "Improves overall workflow efficiency"
                    ],
                    "setup_complexity": template.complexity_score,
                    "estimated_setup_time": template.setup_time_minutes,
                    "customization_requirements": {
                        "integration_setup": [f"{e.get('value', '')} integration" for e in tool_entities],
                        "estimated_effort": "medium"
                    },
                    "expected_roi": {
                        "payback_period_weeks": 3,
                        "time_saved_per_week_hours": 4,
                        "efficiency_gain_percent": 40
                    }
                }
                recommendations.append(recommendation)
        
        return recommendations
    
    async def _deduplicate_and_rank(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate templates and rank by match confidence"""
        seen_templates = set()
        unique_recommendations = []
        
        # Sort by confidence first
        recommendations.sort(key=lambda x: x["match_confidence"], reverse=True)
        
        for rec in recommendations:
            template_id = rec["template_id"]
            if template_id not in seen_templates:
                seen_templates.add(template_id)
                unique_recommendations.append(rec)
        
        return unique_recommendations
    
    async def _generate_implementation_guidance(self, recommendations: List[Dict[str, Any]],
                                              business_insights: Dict[str, Any]) -> Dict[str, Any]:
        """Generate guidance for implementing the recommended templates"""
        if not recommendations:
            return {"guidance": "No templates recommended", "steps": []}
        
        guidance = {
            "overview": f"Implementation plan for {len(recommendations)} recommended workflow templates",
            "total_estimated_time": sum(r.get("estimated_setup_time", 30) for r in recommendations),
            "complexity_distribution": {
                "low": len([r for r in recommendations if r.get("setup_complexity", 0.5) < 0.4]),
                "medium": len([r for r in recommendations if 0.4 <= r.get("setup_complexity", 0.5) < 0.7]),
                "high": len([r for r in recommendations if r.get("setup_complexity", 0.5) >= 0.7])
            },
            "implementation_steps": self._generate_implementation_steps(recommendations),
            "success_factors": [
                "Start with highest confidence templates",
                "Implement low-complexity templates first",
                "Ensure all required integrations are available",
                "Test each template thoroughly before full deployment"
            ],
            "risk_mitigation": [
                "Create backup plans for high-complexity implementations",
                "Monitor automation performance after deployment",
                "Have rollback procedures ready"
            ]
        }
        
        return guidance
    
    def _generate_implementation_steps(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate step-by-step implementation plan"""
        steps = []
        
        # Sort recommendations by implementation priority
        sorted_recs = sorted(recommendations, key=lambda x: (
            x.get("setup_complexity", 0.5),  # Lower complexity first
            -x.get("match_confidence", 0.0)  # Higher confidence first
        ))
        
        for i, rec in enumerate(sorted_recs, 1):
            step = {
                "step_number": i,
                "template_name": rec["template_name"],
                "estimated_time": rec.get("estimated_setup_time", 30),
                "complexity": "low" if rec.get("setup_complexity", 0.5) < 0.4 else 
                            "medium" if rec.get("setup_complexity", 0.5) < 0.7 else "high",
                "prerequisites": rec.get("prerequisites", []),
                "integrations_needed": rec.get("required_integrations", []),
                "key_actions": [
                    "Configure template parameters",
                    "Set up required integrations",
                    "Test workflow functionality",
                    "Deploy and monitor"
                ]
            }
            steps.append(step)
        
        return steps
    
    def _recommend_implementation_order(self, recommendations: List[Dict[str, Any]]) -> List[str]:
        """Recommend the order for implementing templates"""
        # Sort by: low complexity first, then high confidence
        sorted_recs = sorted(recommendations, key=lambda x: (
            x.get("setup_complexity", 0.5),
            -x.get("match_confidence", 0.0)
        ))
        
        return [rec["template_id"] for rec in sorted_recs]
    
    async def _calculate_roi_projections(self, recommendations: List[Dict[str, Any]],
                                       business_insights: Dict[str, Any],
                                       customer_context: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate comprehensive ROI projections"""
        if not recommendations:
            return {"total_roi": 0, "projections": []}
        
        total_time_savings = sum(r.get("expected_roi", {}).get("time_saved_per_week_hours", 0) 
                               for r in recommendations)
        total_setup_time = sum(r.get("estimated_setup_time", 30) for r in recommendations)
        
        # Calculate payback period
        setup_hours = total_setup_time / 60  # Convert minutes to hours
        payback_weeks = setup_hours / total_time_savings if total_time_savings > 0 else float('inf')
        
        return {
            "total_weekly_time_savings": total_time_savings,
            "total_setup_time_hours": setup_hours,
            "payback_period_weeks": payback_weeks,
            "annual_time_savings_hours": total_time_savings * 52,
            "efficiency_improvement_percent": min(80, int(total_time_savings * 5)),  # Estimate
            "cost_benefit_ratio": max(1.0, total_time_savings * 52 / max(setup_hours, 1)),
            "individual_template_projections": [
                {
                    "template_id": rec["template_id"],
                    "template_name": rec["template_name"],
                    "roi_projection": rec.get("expected_roi", {})
                }
                for rec in recommendations
            ]
        }
    
    def _calculate_total_impact(self, recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate total impact of implementing all recommendations"""
        impact_categories = ["time_savings", "error_reduction", "cost_savings", "scalability"]
        total_impact = {category: 0.0 for category in impact_categories}
        
        for rec in recommendations:
            automation_impact = rec.get("automation_impact", {})
            for category in impact_categories:
                if category in automation_impact:
                    total_impact[category] += automation_impact[category] * rec.get("match_confidence", 0.0)
        
        # Normalize to 0-1 scale
        max_possible = len(recommendations)
        for category in impact_categories:
            if max_possible > 0:
                total_impact[category] = min(1.0, total_impact[category] / max_possible)
        
        return total_impact
    
    def _assess_overall_customization_complexity(self, recommendations: List[Dict[str, Any]]) -> str:
        """Assess overall complexity of customizing all recommended templates"""
        if not recommendations:
            return "none"
        
        avg_complexity = sum(r.get("setup_complexity", 0.5) for r in recommendations) / len(recommendations)
        
        if avg_complexity < 0.4:
            return "low"
        elif avg_complexity < 0.7:
            return "medium"
        else:
            return "high"
    
    def _consolidate_integration_requirements(self, recommendations: List[Dict[str, Any]]) -> List[str]:
        """Consolidate all integration requirements across recommendations"""
        all_integrations = set()
        
        for rec in recommendations:
            integrations = rec.get("required_integrations", [])
            all_integrations.update(integrations)
        
        return sorted(list(all_integrations))
    
    def _load_template_library(self) -> List[WorkflowTemplate]:
        """Load workflow template library with business-ready templates"""
        templates = [
            # Social Media Templates
            WorkflowTemplate(
                template_id="social_media_scheduler",
                name="Social Media Post Scheduler",
                description="Automatically schedule and post content across multiple social media platforms",
                category=TemplateCategory.SOCIAL_MEDIA,
                complexity_score=0.4,
                setup_time_minutes=15,
                required_integrations=["instagram", "facebook", "twitter", "linkedin"],
                business_patterns=["frequency_process", "content_creation", "social_media"],
                automation_impact={"time_savings": 0.8, "error_reduction": 0.6, "scalability": 0.9},
                customization_difficulty=0.3,
                success_rate=0.85,
                roi_metrics={"payback_weeks": 2, "time_saved_hours": 5, "efficiency_gain": 60},
                tags=["social_media", "content", "marketing", "scheduling"],
                prerequisites=["social_media_accounts", "content_calendar"]
            ),
            
            # Email Automation Templates
            WorkflowTemplate(
                template_id="email_follow_up_sequence",
                name="Automated Email Follow-up Sequence",
                description="Create automated email sequences for lead nurturing and customer engagement",
                category=TemplateCategory.EMAIL_AUTOMATION,
                complexity_score=0.5,
                setup_time_minutes=25,
                required_integrations=["email", "crm", "mailchimp"],
                business_patterns=["lead_management", "customer_support", "frequency_process"],
                automation_impact={"time_savings": 0.9, "error_reduction": 0.8, "cost_savings": 0.7},
                customization_difficulty=0.4,
                success_rate=0.90,
                roi_metrics={"payback_weeks": 1, "time_saved_hours": 8, "efficiency_gain": 70},
                tags=["email", "marketing", "crm", "lead_nurturing"],
                prerequisites=["email_service", "customer_database"]
            ),
            
            # Data Processing Templates  
            WorkflowTemplate(
                template_id="spreadsheet_data_processor",
                name="Spreadsheet Data Processor",
                description="Automatically process, validate, and organize spreadsheet data",
                category=TemplateCategory.DATA_PROCESSING,
                complexity_score=0.6,
                setup_time_minutes=30,
                required_integrations=["excel", "google_sheets"],
                business_patterns=["manual_process", "data_processing", "repetitive_task"],
                automation_impact={"time_savings": 0.9, "error_reduction": 0.9, "accuracy": 0.95},
                customization_difficulty=0.5,
                success_rate=0.88,
                roi_metrics={"payback_weeks": 1, "time_saved_hours": 10, "efficiency_gain": 80},
                tags=["data", "spreadsheet", "validation", "processing"],
                prerequisites=["data_sources", "validation_rules"]
            ),
            
            # Lead Management Templates
            WorkflowTemplate(
                template_id="lead_qualification_automation",
                name="Lead Qualification Automation",
                description="Automatically score, qualify, and route leads based on predefined criteria",
                category=TemplateCategory.LEAD_MANAGEMENT,
                complexity_score=0.7,
                setup_time_minutes=45,
                required_integrations=["crm", "email", "web_forms"],
                business_patterns=["lead_management", "customer_acquisition", "qualification"],
                automation_impact={"time_savings": 0.8, "conversion_rate": 0.7, "efficiency": 0.9},
                customization_difficulty=0.6,
                success_rate=0.82,
                roi_metrics={"payback_weeks": 3, "time_saved_hours": 6, "efficiency_gain": 65},
                tags=["lead", "sales", "crm", "qualification"],
                prerequisites=["crm_system", "lead_scoring_criteria"]
            ),
            
            # Customer Support Templates
            WorkflowTemplate(
                template_id="support_ticket_router",
                name="Support Ticket Router",
                description="Automatically categorize and route support tickets to appropriate team members",
                category=TemplateCategory.CUSTOMER_SUPPORT,
                complexity_score=0.5,
                setup_time_minutes=35,
                required_integrations=["email", "slack", "helpdesk"],
                business_patterns=["customer_support", "ticket_management", "routing"],
                automation_impact={"time_savings": 0.7, "response_time": 0.8, "satisfaction": 0.6},
                customization_difficulty=0.4,
                success_rate=0.87,
                roi_metrics={"payback_weeks": 2, "time_saved_hours": 4, "efficiency_gain": 50},
                tags=["support", "tickets", "routing", "customer_service"],
                prerequisites=["support_categories", "team_structure"]
            ),
            
            # Integration Templates
            WorkflowTemplate(
                template_id="multi_tool_data_sync",
                name="Multi-Tool Data Synchronizer",
                description="Keep data synchronized across multiple business tools and platforms",
                category=TemplateCategory.INTEGRATION,
                complexity_score=0.8,
                setup_time_minutes=60,
                required_integrations=["crm", "excel", "email", "project_management"],
                business_patterns=["tool_integration", "data_sync", "consistency"],
                automation_impact={"time_savings": 0.8, "data_accuracy": 0.9, "consistency": 0.95},
                customization_difficulty=0.7,
                success_rate=0.75,
                roi_metrics={"payback_weeks": 4, "time_saved_hours": 12, "efficiency_gain": 75},
                tags=["integration", "sync", "data", "multi_tool"],
                prerequisites=["api_access", "data_mapping"]
            ),
            
            # Reporting Templates
            WorkflowTemplate(
                template_id="automated_business_reports",
                name="Automated Business Reports",
                description="Generate and distribute regular business reports automatically",
                category=TemplateCategory.REPORTING,
                complexity_score=0.6,
                setup_time_minutes=40,
                required_integrations=["excel", "email", "database"],
                business_patterns=["reporting", "frequency_process", "analytics"],
                automation_impact={"time_savings": 0.9, "accuracy": 0.8, "timeliness": 0.9},
                customization_difficulty=0.5,
                success_rate=0.89,
                roi_metrics={"payback_weeks": 2, "time_saved_hours": 6, "efficiency_gain": 85},
                tags=["reporting", "analytics", "automation", "business_intelligence"],
                prerequisites=["data_sources", "report_templates"]
            )
        ]
        
        return templates
    
    def _organize_by_category(self) -> Dict[TemplateCategory, List[WorkflowTemplate]]:
        """Organize templates by category for efficient lookup"""
        category_map = {}
        for template in self.templates:
            if template.category not in category_map:
                category_map[template.category] = []
            category_map[template.category].append(template)
        return category_map
    
    def _initialize_pattern_weights(self) -> Dict[str, float]:
        """Initialize pattern matching weights"""
        return {
            "frequency_process": 0.9,
            "pain_point": 0.8,
            "tool_integration": 0.7,
            "manual_process": 0.85,
            "repetitive_task": 0.8,
            "customer_support": 0.7,
            "data_processing": 0.75
        }
    
    def get_template_library_stats(self) -> Dict[str, Any]:
        """Get statistics about the template library"""
        category_counts = {}
        for template in self.templates:
            category = template.category.value
            category_counts[category] = category_counts.get(category, 0) + 1
        
        return {
            "total_templates": len(self.templates),
            "categories": list(category_counts.keys()),
            "category_distribution": category_counts,
            "average_complexity": sum(t.complexity_score for t in self.templates) / len(self.templates),
            "average_setup_time": sum(t.setup_time_minutes for t in self.templates) / len(self.templates),
            "matching_stats": self.matching_stats
        }