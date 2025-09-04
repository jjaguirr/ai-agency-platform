"""
Structured evaluation schemas for real AI assessment
Replaces mock evaluation with semantic validation
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum


class EvaluationConfidence(str, Enum):
    """Confidence levels for evaluation results"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BusinessMaturity(str, Enum):
    """Business maturity assessment levels"""
    STARTUP = "startup"
    GROWING = "growing"
    ESTABLISHED = "established"
    ENTERPRISE = "enterprise"


class AutomationPriority(str, Enum):
    """Priority levels for automation opportunities"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvaluationResult(BaseModel):
    """Base evaluation result with common fields"""
    passed: bool = Field(..., description="Whether the evaluation passed")
    confidence: EvaluationConfidence = Field(..., description="Confidence in the evaluation")
    score: float = Field(..., ge=0.0, le=1.0, description="Numerical score (0-1)")
    reasoning: str = Field(..., description="Detailed reasoning for the evaluation")
    timestamp: str = Field(..., description="ISO timestamp of evaluation")
    evaluation_time_ms: int = Field(..., description="Time taken for evaluation in milliseconds")


class BusinessUnderstandingAssessment(EvaluationResult):
    """Assessment of EA's understanding of business context"""
    business_type_identified: bool = Field(..., description="Whether business type was correctly identified")
    industry_knowledge_demonstrated: bool = Field(..., description="Whether industry-specific knowledge was shown")
    pain_points_understood: List[str] = Field(default_factory=list, description="Pain points correctly identified")
    business_goals_recognized: List[str] = Field(default_factory=list, description="Business goals understood")
    context_retention_score: float = Field(..., ge=0.0, le=1.0, description="How well business context was retained")
    
    # Semantic analysis results
    key_business_entities: List[Dict[str, Any]] = Field(default_factory=list, description="Business entities identified")
    missing_critical_understanding: List[str] = Field(default_factory=list, description="Critical gaps in understanding")
    business_maturity_assessment: BusinessMaturity = Field(..., description="Assessed business maturity level")


class ConversationQualityMetrics(EvaluationResult):
    """Quality assessment of EA conversation performance"""
    professionalism_score: float = Field(..., ge=0.0, le=1.0, description="Professional tone and language")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance to customer needs")
    completeness_score: float = Field(..., ge=0.0, le=1.0, description="Completeness of response")
    actionability_score: float = Field(..., ge=0.0, le=1.0, description="Actionable recommendations provided")
    empathy_score: float = Field(..., ge=0.0, le=1.0, description="Empathy and understanding shown")
    
    # Conversation flow analysis
    maintains_context: bool = Field(..., description="Whether context is maintained throughout conversation")
    asks_clarifying_questions: bool = Field(..., description="Whether EA asks appropriate clarifying questions")
    provides_specific_solutions: bool = Field(..., description="Whether specific solutions are provided")
    
    # Quality issues identified
    quality_issues: List[str] = Field(default_factory=list, description="Quality issues identified")
    improvement_suggestions: List[str] = Field(default_factory=list, description="Suggestions for improvement")


class ROIValidationResult(EvaluationResult):
    """Validation of ROI calculations and business value assessments"""
    roi_calculation_present: bool = Field(..., description="Whether ROI calculation is present")
    roi_calculation_accurate: bool = Field(..., description="Whether ROI calculation is mathematically accurate")
    time_savings_quantified: bool = Field(..., description="Whether time savings are quantified")
    cost_savings_calculated: bool = Field(..., description="Whether cost savings are calculated")
    assumptions_reasonable: bool = Field(..., description="Whether assumptions are reasonable")
    
    # Financial metrics validation
    extracted_time_savings: Optional[Dict[str, Any]] = Field(None, description="Extracted time savings information")
    extracted_cost_savings: Optional[Dict[str, Any]] = Field(None, description="Extracted cost savings information")
    calculated_roi_percentage: Optional[float] = Field(None, description="Calculated ROI percentage")
    payback_period: Optional[str] = Field(None, description="Estimated payback period")
    
    # Validation details
    calculation_errors: List[str] = Field(default_factory=list, description="Mathematical or logical errors found")
    missing_considerations: List[str] = Field(default_factory=list, description="Important considerations not addressed")


class AutomationOpportunityAssessment(EvaluationResult):
    """Assessment of identified automation opportunities"""
    opportunities_identified: List[Dict[str, Any]] = Field(default_factory=list, description="Automation opportunities identified")
    prioritization_quality: float = Field(..., ge=0.0, le=1.0, description="Quality of opportunity prioritization")
    implementation_feasibility: float = Field(..., ge=0.0, le=1.0, description="Feasibility of implementation")
    business_impact_accuracy: float = Field(..., ge=0.0, le=1.0, description="Accuracy of business impact assessment")
    
    # Opportunity analysis
    high_priority_opportunities: List[str] = Field(default_factory=list, description="High priority opportunities")
    quick_wins_identified: List[str] = Field(default_factory=list, description="Quick win opportunities")
    long_term_opportunities: List[str] = Field(default_factory=list, description="Long-term automation opportunities")
    
    # Quality assessment
    opportunities_match_pain_points: bool = Field(..., description="Whether opportunities match stated pain points")
    industry_specific_recommendations: bool = Field(..., description="Whether recommendations are industry-specific")
    implementation_guidance_provided: bool = Field(..., description="Whether implementation guidance is provided")
    
    # Issues and gaps
    missed_opportunities: List[str] = Field(default_factory=list, description="Obvious opportunities that were missed")
    unrealistic_recommendations: List[str] = Field(default_factory=list, description="Unrealistic or impractical recommendations")


class IndustryKnowledgeAssessment(EvaluationResult):
    """Assessment of industry-specific knowledge demonstration"""
    industry: str = Field(..., description="Industry being assessed")
    industry_terminology_used: bool = Field(..., description="Whether industry terminology is used correctly")
    common_processes_understood: bool = Field(..., description="Whether common industry processes are understood")
    typical_tools_mentioned: bool = Field(..., description="Whether typical industry tools are mentioned")
    regulatory_considerations: bool = Field(..., description="Whether regulatory considerations are addressed")
    
    # Industry-specific metrics
    relevant_benchmarks_provided: bool = Field(..., description="Whether relevant industry benchmarks are provided")
    competitive_insights: bool = Field(..., description="Whether competitive insights are demonstrated")
    industry_best_practices: List[str] = Field(default_factory=list, description="Industry best practices mentioned")
    
    # Knowledge gaps
    knowledge_gaps: List[str] = Field(default_factory=list, description="Knowledge gaps identified")
    incorrect_assumptions: List[str] = Field(default_factory=list, description="Incorrect industry assumptions")


class ComprehensiveEvaluationResult(BaseModel):
    """Comprehensive evaluation combining all assessment types"""
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Overall evaluation score")
    overall_passed: bool = Field(..., description="Whether overall evaluation passed")
    evaluation_summary: str = Field(..., description="Summary of evaluation results")
    
    # Individual assessments
    business_understanding: Optional[BusinessUnderstandingAssessment] = None
    conversation_quality: Optional[ConversationQualityMetrics] = None
    roi_validation: Optional[ROIValidationResult] = None
    automation_assessment: Optional[AutomationOpportunityAssessment] = None
    industry_knowledge: Optional[IndustryKnowledgeAssessment] = None
    
    # Aggregate insights
    strengths: List[str] = Field(default_factory=list, description="Key strengths identified")
    weaknesses: List[str] = Field(default_factory=list, description="Key weaknesses identified")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations for improvement")
    
    # Metadata
    total_evaluation_time_ms: int = Field(..., description="Total evaluation time in milliseconds")
    evaluations_performed: List[str] = Field(default_factory=list, description="List of evaluations performed")