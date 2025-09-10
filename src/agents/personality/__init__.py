"""
Personality Engine - Premium-Casual Conversation Transformation System
Enables "Premium capabilities with your best friend's personality" for AI Agency Platform
"""

from .personality_engine import (
    PersonalityEngine,
    CommunicationChannel,
    PersonalityTone,
    ConversationContext,
    PersonalityProfile,
    PersonalityTransformationResult,
    PersonalityConsistencyReport,
    extract_personality_patterns,
    calculate_premium_casual_score
)

from .personality_database import (
    PersonalityDatabase,
    migrate_personality_schema,
    validate_personality_database
)

from .multi_channel_consistency import (
    MultiChannelConsistencyManager,
    ChannelConsistencyMetrics,
    CrossChannelAnalysis
)

from .ab_testing_framework import (
    PersonalityABTestingFramework,
    ABTestConfig,
    ABTestVariation,
    ABTestResult,
    ABTestReport,
    TestStatus,
    TestMetric,
    create_tone_variation_test,
    create_channel_consistency_test
)

from .personality_integration import (
    PersonalityEngineIntegration,
    PersonalityConfig,
    TransformationRequest,
    TransformationResponse,
    initialize_personality_for_customer,
    create_simple_transformation_request,
    quick_personality_transform
)

# Version information
__version__ = "1.0.0"
__author__ = "AI Agency Platform"
__description__ = "Premium-Casual Personality Transformation Engine"

# Package metadata for the personality system
PERSONALITY_SYSTEM_INFO = {
    "name": "Personality Engine",
    "version": __version__,
    "description": __description__,
    "core_positioning": "Premium capabilities with your best friend's personality",
    "performance_target": "<500ms transformation processing time",
    "consistency_requirement": ">90% consistency across all channels",
    "supported_channels": [
        "email", "whatsapp", "voice", "web_chat", "sms"
    ],
    "personality_tones": [
        "professional_warm", "motivational", "supportive", 
        "strategic", "conversational"
    ],
    "features": [
        "Real-time personality transformation",
        "Multi-channel consistency monitoring",
        "A/B testing framework for optimization",
        "Customer isolation with MCP integration",
        "Performance monitoring and SLA compliance",
        "Premium-casual indicator analysis"
    ]
}

# Export all main classes and functions
__all__ = [
    # Core personality engine
    "PersonalityEngine",
    "CommunicationChannel", 
    "PersonalityTone",
    "ConversationContext",
    "PersonalityProfile",
    "PersonalityTransformationResult",
    "PersonalityConsistencyReport",
    
    # Database integration
    "PersonalityDatabase",
    "migrate_personality_schema",
    "validate_personality_database",
    
    # Multi-channel consistency
    "MultiChannelConsistencyManager",
    "ChannelConsistencyMetrics", 
    "CrossChannelAnalysis",
    
    # A/B testing framework
    "PersonalityABTestingFramework",
    "ABTestConfig",
    "ABTestVariation",
    "ABTestResult", 
    "ABTestReport",
    "TestStatus",
    "TestMetric",
    "create_tone_variation_test",
    "create_channel_consistency_test",
    
    # Integration API
    "PersonalityEngineIntegration",
    "PersonalityConfig",
    "TransformationRequest",
    "TransformationResponse",
    "initialize_personality_for_customer",
    "create_simple_transformation_request", 
    "quick_personality_transform",
    
    # Utility functions
    "extract_personality_patterns",
    "calculate_premium_casual_score",
    
    # Package information
    "PERSONALITY_SYSTEM_INFO"
]