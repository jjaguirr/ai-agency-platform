"""
AI Agency Platform - Real AI Evaluation Framework
Replaces mock evaluation with semantic assessment for business logic validation
"""

from .real_business_intelligence_validator import RealBusinessIntelligenceValidator
from .conversation_quality_assessment import ConversationQualityAssessment
from .roi_calculation_validator import ROICalculationValidator
from .evaluation_schemas import (
    EvaluationResult,
    BusinessUnderstandingAssessment,
    ConversationQualityMetrics,
    ROIValidationResult,
    AutomationOpportunityAssessment
)

__all__ = [
    "RealBusinessIntelligenceValidator",
    "ConversationQualityAssessment", 
    "ROICalculationValidator",
    "EvaluationResult",
    "BusinessUnderstandingAssessment",
    "ConversationQualityMetrics",
    "ROIValidationResult",
    "AutomationOpportunityAssessment"
]