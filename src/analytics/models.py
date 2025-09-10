"""
Analytics Data Models
Comprehensive data models for voice interaction analytics
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import uuid

class VoiceLanguage(Enum):
    """Supported voice languages"""
    ENGLISH = "en"
    SPANISH = "es"

class InteractionType(Enum):
    """Types of voice interactions"""
    VOICE_MESSAGE = "voice_message"
    VOICE_CALL = "voice_call"
    VOICE_COMMAND = "voice_command"

class CustomerSegment(Enum):
    """Customer segments for analytics"""
    NEW = "new"
    ACTIVE = "active"
    ENGAGED = "engaged"
    HIGH_VALUE = "high_value"
    AT_RISK = "at_risk"

class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    URGENT = "urgent"

@dataclass
class VoiceAnalyticsEvent:
    """Individual analytics event"""
    event_id: str
    event_type: str  # From AnalyticsEventType enum
    timestamp: datetime
    customer_id: str
    interaction_id: str
    data: Dict[str, Any]
    
    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())

@dataclass
class CustomerEngagementMetrics:
    """Customer engagement metrics"""
    customer_id: str
    measurement_period_start: datetime
    measurement_period_end: datetime
    
    # Volume metrics
    total_interactions: int
    voice_interactions: int
    successful_interactions: int
    
    # Engagement indicators
    average_session_length: float
    interaction_frequency_per_day: float
    response_rate: float  # How often customer responds to EA
    
    # Quality metrics
    average_satisfaction_score: float
    completion_rate: float  # How often interactions complete successfully
    feature_adoption_score: float  # How many features are being used
    
    # Language preferences
    preferred_language: VoiceLanguage
    language_consistency: float  # How often they stick to preferred language
    
    # Behavioral patterns
    peak_usage_hours: List[int]  # Hours of day when most active
    usage_pattern: str  # regular, sporadic, declining, growing
    
    # Predictive metrics
    engagement_trend: str  # increasing, stable, declining
    churn_risk_score: float  # 0-1 scale
    lifetime_value_estimate: float

@dataclass
class PersonalityConsistencyScore:
    """EA personality consistency analysis"""
    customer_id: str
    conversation_id: str
    assessment_date: datetime
    
    # Consistency dimensions
    tone_consistency: float  # 0-1, how consistent is the tone
    style_consistency: float  # 0-1, how consistent is communication style
    knowledge_consistency: float  # 0-1, how consistent is knowledge application
    
    # Personality traits measured
    personality_traits: Dict[str, float]  # trait_name: score (0-1)
    
    # Comparison metrics
    deviation_from_baseline: float  # How much this differs from customer's EA baseline
    improvement_from_previous: float  # How much better/worse than last assessment
    
    # Recommendations
    consistency_score: float  # Overall consistency (0-1)
    improvement_suggestions: List[str]

@dataclass
class BusinessImpactMetrics:
    """Business impact measurement"""
    customer_id: str
    measurement_period_start: datetime
    measurement_period_end: datetime
    
    # ROI metrics
    total_investment: float  # Total cost of voice interactions
    estimated_time_saved_hours: float  # Time saved for the customer
    estimated_value_created: float  # Dollar value created
    roi_percentage: float  # Return on investment percentage
    
    # Personal brand impact
    brand_perception_score: float  # -1 to 1 scale
    professional_image_enhancement: float  # 0-1 scale  
    client_satisfaction_impact: float  # -1 to 1 scale
    
    # Productivity metrics
    tasks_automated: int
    decisions_supported: int
    insights_provided: int
    connections_facilitated: int
    
    # Growth indicators
    business_opportunities_identified: int
    strategic_insights_count: int
    process_improvements_suggested: int
    
    # Competitive advantage
    market_intelligence_points: int
    competitive_insights_generated: int
    innovation_suggestions: int

@dataclass
class VoiceCostBreakdown:
    """Detailed cost breakdown for voice interactions"""
    interaction_id: str
    customer_id: str
    timestamp: datetime
    
    # API costs
    elevenlabs_tts_cost: float  # Text-to-speech cost
    whisper_stt_cost: float  # Speech-to-text cost
    openai_api_cost: float  # LLM processing cost
    
    # Infrastructure costs
    compute_cost: float  # Processing compute cost
    storage_cost: float  # Memory and data storage
    bandwidth_cost: float  # Network usage
    
    # Service costs
    monitoring_cost: float  # Observability and monitoring
    security_cost: float  # Security services
    
    # Total costs
    total_direct_cost: float  # Sum of all direct costs
    allocated_overhead: float  # Allocated infrastructure overhead
    total_cost: float  # Total cost including overhead
    
    # Cost efficiency metrics
    cost_per_second: float  # Cost per second of interaction
    cost_per_word: float  # Cost per word in response
    cost_per_business_value_point: float  # Cost efficiency metric

@dataclass
class VoiceQualityMetrics:
    """Voice interaction quality assessment"""
    interaction_id: str
    customer_id: str
    assessment_timestamp: datetime
    
    # Audio quality
    audio_clarity_score: float  # 0-1, clarity of input/output audio
    noise_level: float  # 0-1, background noise assessment
    audio_compression_quality: float  # 0-1, compression artifacts
    
    # Speech recognition quality  
    transcription_accuracy: float  # 0-1, accuracy of speech-to-text
    language_detection_confidence: float  # 0-1, confidence in language detection
    accent_handling_score: float  # 0-1, how well system handles accents
    
    # Response quality
    response_relevance: float  # 0-1, relevance to input
    response_completeness: float  # 0-1, completeness of response
    response_coherence: float  # 0-1, logical flow and coherence
    
    # Language quality
    grammar_accuracy: float  # 0-1, grammatical correctness
    vocabulary_appropriateness: float  # 0-1, appropriate word choice
    cultural_sensitivity: float  # 0-1, cultural appropriateness
    
    # Technical quality
    latency_score: float  # 0-1, response time quality
    system_reliability: float  # 0-1, system uptime during interaction
    
    # Overall quality
    overall_quality_score: float  # 0-1, weighted average of all metrics
    quality_issues: List[str]  # List of identified issues
    improvement_suggestions: List[str]

@dataclass
class CustomerJourneyStage:
    """Customer journey stage analysis"""
    customer_id: str
    stage_date: datetime
    
    # Journey stage
    current_stage: str  # onboarding, adoption, growth, maturity, at_risk, churn
    days_in_stage: int
    previous_stage: Optional[str]
    
    # Stage characteristics
    interactions_in_stage: int
    success_rate_in_stage: float
    engagement_level: float
    satisfaction_trend: str  # improving, stable, declining
    
    # Transition probability
    next_stage_probabilities: Dict[str, float]  # stage: probability
    transition_triggers: List[str]  # What might trigger next transition
    
    # Stage-specific metrics
    stage_metrics: Dict[str, Any]  # Stage-specific data
    
    # Recommendations for stage progression
    stage_recommendations: List[str]

@dataclass
class AlertDefinition:
    """Definition of an analytics alert"""
    alert_id: str
    alert_name: str
    alert_description: str
    
    # Alert conditions
    metric_name: str
    threshold_value: float
    comparison_operator: str  # >, <, >=, <=, ==, !=
    evaluation_window_minutes: int
    
    # Alert behavior
    severity: AlertSeverity
    cooldown_minutes: int  # Minimum time between alerts
    auto_resolve: bool  # Whether alert auto-resolves when condition clears
    
    # Notification settings
    notification_channels: List[str]  # email, slack, webhook
    escalation_rules: List[Dict[str, Any]]  # Escalation conditions and targets
    
    # Metadata
    created_date: datetime
    created_by: str
    is_active: bool = True

@dataclass
class TriggeredAlert:
    """An active or historical alert"""
    alert_instance_id: str
    alert_definition_id: str
    customer_id: Optional[str]  # Some alerts are system-wide
    
    # Alert details
    triggered_timestamp: datetime
    resolved_timestamp: Optional[datetime]
    current_value: float
    threshold_breached: float
    
    # Status
    status: str  # active, acknowledged, resolved
    severity: AlertSeverity
    
    # Context
    triggering_data: Dict[str, Any]  # Data that triggered the alert
    business_context: Dict[str, Any]  # Additional business context
    
    # Response
    acknowledged_by: Optional[str]
    acknowledgement_timestamp: Optional[datetime]
    resolution_notes: Optional[str]
    actions_taken: List[str] = field(default_factory=list)

@dataclass
class AnalyticsDashboardConfig:
    """Configuration for analytics dashboard"""
    dashboard_id: str
    dashboard_name: str
    created_by: str
    created_date: datetime
    
    # Layout configuration
    widgets: List[Dict[str, Any]]  # Widget configurations
    refresh_interval_seconds: int
    auto_refresh: bool
    
    # Data settings
    default_time_range: str  # 1h, 24h, 7d, 30d
    customer_filters: List[str]  # Default customer filters
    metric_filters: List[str]  # Default metric filters
    
    # Access control
    allowed_users: List[str]
    permission_level: str  # view, edit, admin
    
    # Customization
    theme_settings: Dict[str, Any]
    chart_preferences: Dict[str, Any]
    
    # Metadata
    is_active: bool = True
    last_modified: Optional[datetime] = None
    last_modified_by: Optional[str] = None

@dataclass
class BusinessIntelligenceInsight:
    """AI-generated business intelligence insight"""
    insight_id: str
    generated_timestamp: datetime
    customer_id: Optional[str]  # None for system-wide insights
    
    # Insight details
    insight_type: str  # trend, anomaly, recommendation, prediction, opportunity
    title: str
    description: str
    confidence_score: float  # 0-1, confidence in insight
    
    # Supporting data
    data_points: List[Dict[str, Any]]  # Data supporting this insight
    metrics_involved: List[str]  # Which metrics contributed
    time_period: Dict[str, datetime]  # start_date, end_date
    
    # Business impact
    potential_impact: str  # high, medium, low
    impact_category: str  # cost_savings, revenue_opportunity, risk_mitigation, efficiency
    estimated_value: Optional[float]  # Dollar impact if quantifiable
    
    # Recommendations
    recommended_actions: List[str]
    implementation_priority: str  # urgent, high, medium, low
    expected_timeline: Optional[str]  # How long to implement/see results
    
    # Tracking
    status: str  # new, reviewed, implemented, dismissed
    reviewed_by: Optional[str]
    review_date: Optional[datetime]
    implementation_notes: Optional[str] = None

@dataclass
class CompetitiveIntelligence:
    """Competitive intelligence from voice interactions"""
    intelligence_id: str
    collected_timestamp: datetime
    customer_id: str
    
    # Competitive mentions
    competitors_mentioned: List[str]
    competitive_context: str  # comparison, switch_consideration, market_analysis
    sentiment_toward_competitors: Dict[str, float]  # competitor: sentiment (-1 to 1)
    
    # Market intelligence
    market_trends_mentioned: List[str]
    pricing_intelligence: Dict[str, Any]  # Any pricing information discussed
    feature_comparisons: Dict[str, Any]  # Feature comparison data
    
    # Strategic intelligence
    customer_pain_points: List[str]  # Unmet needs mentioned
    opportunity_areas: List[str]  # Areas where we could improve
    differentiation_opportunities: List[str]  # Ways to differentiate
    
    # Metadata
    confidence_score: float  # 0-1, confidence in extracted intelligence
    extraction_method: str  # keyword, nlp, manual
    validation_status: str  # unvalidated, validated, disputed
    
    # Actions
    intelligence_priority: str  # high, medium, low
    assigned_to: Optional[str]  # Who should act on this intelligence
    follow_up_required: bool = False

@dataclass
class ROIMeasurement:
    """ROI measurement for voice interactions"""
    measurement_id: str
    customer_id: str
    measurement_period_start: datetime
    measurement_period_end: datetime
    
    # Investment (costs)
    total_voice_interaction_cost: float
    infrastructure_allocation: float
    development_cost_allocation: float
    support_cost_allocation: float
    total_investment: float
    
    # Returns (benefits)
    time_saved_hours: float
    time_saved_value: float  # Hours * hourly rate
    process_efficiency_gains: float
    decision_quality_improvement_value: float
    customer_satisfaction_value: float
    brand_enhancement_value: float
    
    # Calculated ROI
    total_quantified_return: float
    roi_percentage: float  # (Return - Investment) / Investment * 100
    payback_period_days: Optional[float]  # How long to break even
    
    # Qualitative benefits
    qualitative_benefits: List[str]  # Benefits hard to quantify
    strategic_value: str  # high, medium, low
    
    # Confidence and validation
    measurement_confidence: float  # 0-1, confidence in ROI calculation
    validation_method: str  # survey, behavioral_analysis, business_metrics
    validated_by: Optional[str]
    validation_date: Optional[datetime]