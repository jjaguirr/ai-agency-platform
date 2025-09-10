"""
Personality Engine Integration - API Layer for Executive Assistant Integration
Provides seamless integration between PersonalityEngine and existing EA system
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict

from openai import AsyncOpenAI

from .personality_engine import (
    PersonalityEngine, PersonalityTone, CommunicationChannel, ConversationContext,
    PersonalityTransformationResult, PersonalityConsistencyReport
)
from .personality_database import PersonalityDatabase
from .multi_channel_consistency import MultiChannelConsistencyManager
from .ab_testing_framework import PersonalityABTestingFramework
from ..memory.mcp_memory_client import MCPMemoryServiceClient

logger = logging.getLogger(__name__)


@dataclass
class PersonalityConfig:
    """Configuration for personality engine initialization"""
    customer_id: str
    openai_api_key: str
    database_url: str
    memory_service_url: str
    personality_model: str = "gpt-4o-mini"
    enable_caching: bool = True
    enable_ab_testing: bool = True
    enable_consistency_monitoring: bool = True
    consistency_target: float = 0.9


@dataclass
class TransformationRequest:
    """Request for personality transformation"""
    customer_id: str
    original_content: str
    channel: str  # Will be converted to CommunicationChannel
    conversation_context: Optional[str] = None  # Will be converted to ConversationContext
    target_tone: Optional[str] = None  # Will be converted to PersonalityTone
    include_performance_metrics: bool = True
    enable_ab_testing: bool = True


@dataclass
class TransformationResponse:
    """Response from personality transformation"""
    success: bool
    transformed_content: str
    original_content: str
    transformation_time_ms: int
    consistency_score: float
    personality_tone: str
    channel: str
    premium_casual_indicators: List[str]
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    ab_test_info: Optional[Dict[str, Any]] = None


class PersonalityEngineIntegration:
    """
    Integration layer that provides a clean API for EA system to use personality transformation.
    
    Handles initialization, coordination between components, and provides simplified interfaces
    for the existing Executive Assistant system.
    """
    
    def __init__(self, config: PersonalityConfig):
        """
        Initialize personality engine integration.
        
        Args:
            config: PersonalityConfig with all necessary configuration
        """
        self.config = config
        self.customer_id = config.customer_id
        
        # Initialize components (will be done in async initialize method)
        self.personality_engine: Optional[PersonalityEngine] = None
        self.personality_database: Optional[PersonalityDatabase] = None
        self.consistency_manager: Optional[MultiChannelConsistencyManager] = None
        self.ab_testing_framework: Optional[PersonalityABTestingFramework] = None
        self.memory_client: Optional[MCPMemoryServiceClient] = None
        
        self._initialized = False
        self._performance_stats = {
            'transformations_performed': 0,
            'total_transformation_time_ms': 0,
            'cache_hits': 0,
            'consistency_alerts': 0,
            'ab_tests_active': 0
        }
        
        logger.info(f"PersonalityEngineIntegration created for customer {config.customer_id}")
    
    async def initialize(self) -> bool:
        """
        Initialize all personality engine components.
        
        Returns:
            True if initialization successful
        """
        try:
            # Initialize OpenAI client
            openai_client = AsyncOpenAI(api_key=self.config.openai_api_key)
            
            # Initialize MCP memory client for customer isolation
            self.memory_client = MCPMemoryServiceClient(
                base_url=self.config.memory_service_url,
                customer_id=self.customer_id
            )
            
            # Initialize personality database
            self.personality_database = PersonalityDatabase(self.config.database_url)
            await self.personality_database.initialize()
            
            # Initialize personality engine
            self.personality_engine = PersonalityEngine(
                openai_client=openai_client,
                memory_client=self.memory_client,
                personality_model=self.config.personality_model,
                enable_caching=self.config.enable_caching
            )
            
            # Initialize consistency manager if enabled
            if self.config.enable_consistency_monitoring:
                self.consistency_manager = MultiChannelConsistencyManager(
                    personality_engine=self.personality_engine,
                    personality_database=self.personality_database,
                    consistency_target=self.config.consistency_target
                )
            
            # Initialize A/B testing framework if enabled
            if self.config.enable_ab_testing:
                self.ab_testing_framework = PersonalityABTestingFramework(
                    personality_engine=self.personality_engine,
                    personality_database=self.personality_database
                )
            
            self._initialized = True
            logger.info(f"PersonalityEngineIntegration initialized successfully for customer {self.customer_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize PersonalityEngineIntegration: {e}")
            return False
    
    async def transform_message(self, request: TransformationRequest) -> TransformationResponse:
        """
        Transform a message using personality engine with full integration features.
        
        Args:
            request: TransformationRequest with message and parameters
            
        Returns:
            TransformationResponse with transformed content and metrics
        """
        if not self._initialized:
            if not await self.initialize():
                return TransformationResponse(
                    success=False,
                    transformed_content=request.original_content,
                    original_content=request.original_content,
                    transformation_time_ms=0,
                    consistency_score=0.0,
                    personality_tone="professional_warm",
                    channel=request.channel,
                    premium_casual_indicators=[],
                    error_message="Personality engine not initialized"
                )
        
        start_time = time.time()
        
        try:
            # Convert string parameters to enums
            channel = CommunicationChannel(request.channel)
            conversation_context = ConversationContext(request.conversation_context) if request.conversation_context else None
            target_tone = PersonalityTone(request.target_tone) if request.target_tone else None
            
            # Check for active A/B tests
            ab_test_info = None
            if request.enable_ab_testing and self.ab_testing_framework:
                test_id, test_variation = await self.ab_testing_framework.get_test_variation(
                    customer_id=request.customer_id,
                    channel=channel
                )
                
                if test_variation:
                    target_tone = test_variation.personality_tone
                    ab_test_info = {
                        'test_id': test_id,
                        'variation_name': test_variation.name,
                        'variation_description': test_variation.description
                    }
                    self._performance_stats['ab_tests_active'] = 1
            
            # Perform personality transformation
            transformation_result = await self.personality_engine.transform_message(
                customer_id=request.customer_id,
                original_content=request.original_content,
                channel=channel,
                conversation_context=conversation_context,
                target_tone=target_tone
            )
            
            # Track transformation for consistency monitoring
            consistency_alert = None
            if self.consistency_manager:
                consistency_alert = await self.consistency_manager.track_transformation(
                    customer_id=request.customer_id,
                    transformation_result=transformation_result
                )
                
                if consistency_alert:
                    self._performance_stats['consistency_alerts'] += 1
            
            # Record A/B test result if applicable
            if ab_test_info and self.ab_testing_framework:
                await self.ab_testing_framework.record_test_result(
                    test_id=ab_test_info['test_id'],
                    customer_id=request.customer_id,
                    transformation_result=transformation_result,
                    variation_name=ab_test_info['variation_name']
                )
            
            # Update performance stats
            self._performance_stats['transformations_performed'] += 1
            self._performance_stats['total_transformation_time_ms'] += transformation_result.transformation_time_ms
            
            if transformation_result.transformation_metadata.get('cache_hit'):
                self._performance_stats['cache_hits'] += 1
            
            # Prepare performance metrics if requested
            performance_metrics = None
            if request.include_performance_metrics:
                performance_metrics = {
                    'transformation_time_ms': transformation_result.transformation_time_ms,
                    'consistency_score': transformation_result.consistency_score,
                    'cache_hit': transformation_result.transformation_metadata.get('cache_hit', False),
                    'model_used': transformation_result.transformation_metadata.get('model_used'),
                    'consistency_alert': consistency_alert,
                    'premium_casual_score': len(transformation_result.premium_casual_indicators) / 10.0  # Normalized score
                }
            
            return TransformationResponse(
                success=True,
                transformed_content=transformation_result.transformed_content,
                original_content=transformation_result.original_content,
                transformation_time_ms=transformation_result.transformation_time_ms,
                consistency_score=transformation_result.consistency_score,
                personality_tone=transformation_result.personality_tone.value,
                channel=transformation_result.channel.value,
                premium_casual_indicators=transformation_result.premium_casual_indicators,
                performance_metrics=performance_metrics,
                ab_test_info=ab_test_info
            )
            
        except Exception as e:
            error_time = int((time.time() - start_time) * 1000)
            logger.error(f"Personality transformation failed: {e}")
            
            return TransformationResponse(
                success=False,
                transformed_content=request.original_content,  # Fallback to original
                original_content=request.original_content,
                transformation_time_ms=error_time,
                consistency_score=0.0,
                personality_tone=request.target_tone or "professional_warm",
                channel=request.channel,
                premium_casual_indicators=[],
                error_message=str(e)
            )
    
    async def get_consistency_report(self, analysis_period_hours: int = 24) -> Dict[str, Any]:
        """
        Get personality consistency report for the customer.
        
        Args:
            analysis_period_hours: Hours of history to analyze
            
        Returns:
            Dictionary with consistency analysis
        """
        if not self._initialized or not self.consistency_manager:
            return {
                'success': False,
                'error': 'Consistency manager not initialized'
            }
        
        try:
            analysis = await self.consistency_manager.analyze_customer_consistency(
                customer_id=self.customer_id,
                analysis_period_hours=analysis_period_hours
            )
            
            return {
                'success': True,
                'customer_id': analysis.customer_id,
                'overall_consistency_score': analysis.overall_consistency_score,
                'meets_target': analysis.overall_consistency_score >= self.config.consistency_target,
                'channel_scores': {
                    channel.value: score for channel, score in analysis.channel_metrics.items()
                },
                'cross_channel_variance': analysis.cross_channel_variance,
                'consistency_alerts': analysis.consistency_alerts,
                'improvement_recommendations': analysis.improvement_recommendations,
                'performance_summary': analysis.performance_summary,
                'analysis_period_hours': analysis_period_hours,
                'generated_at': analysis.generated_at
            }
            
        except Exception as e:
            logger.error(f"Failed to get consistency report: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def create_ab_test(
        self,
        test_name: str,
        description: str,
        channels: List[str],
        test_variations: List[Dict[str, Any]],
        test_duration_hours: int = 168
    ) -> Dict[str, Any]:
        """
        Create an A/B test for personality optimization.
        
        Args:
            test_name: Human-readable test name
            description: Test description
            channels: List of channel names to test
            test_variations: List of variation configurations
            test_duration_hours: Test duration in hours
            
        Returns:
            Dictionary with test creation results
        """
        if not self._initialized or not self.ab_testing_framework:
            return {
                'success': False,
                'error': 'A/B testing framework not initialized'
            }
        
        try:
            # Convert channel names to enums
            channel_enums = [CommunicationChannel(ch) for ch in channels]
            
            # Convert variation configs to ABTestVariation objects
            from .ab_testing_framework import ABTestVariation
            
            variations = []
            for var_config in test_variations:
                variation = ABTestVariation(
                    name=var_config['name'],
                    description=var_config['description'],
                    personality_tone=PersonalityTone(var_config['personality_tone']),
                    conversation_context=ConversationContext(var_config['conversation_context']) if var_config.get('conversation_context') else None,
                    custom_prompt_additions=var_config.get('custom_prompt_additions', []),
                    traffic_allocation=var_config.get('traffic_allocation', 0.5)
                )
                variations.append(variation)
            
            # Create test
            test_id = await self.ab_testing_framework.create_ab_test(
                test_name=test_name,
                description=description,
                customer_id=self.customer_id,
                channels=channel_enums,
                test_variations=variations,
                test_duration_hours=test_duration_hours
            )
            
            return {
                'success': True,
                'test_id': test_id,
                'test_name': test_name,
                'customer_id': self.customer_id,
                'channels': channels,
                'variations': len(variations),
                'duration_hours': test_duration_hours
            }
            
        except Exception as e:
            logger.error(f"Failed to create A/B test: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_ab_test_results(self, test_id: str) -> Dict[str, Any]:
        """
        Get results from an A/B test.
        
        Args:
            test_id: Test identifier
            
        Returns:
            Dictionary with test results
        """
        if not self._initialized or not self.ab_testing_framework:
            return {
                'success': False,
                'error': 'A/B testing framework not initialized'
            }
        
        try:
            report = await self.ab_testing_framework.analyze_test_results(test_id)
            
            if not report:
                return {
                    'success': False,
                    'error': 'Test results not available or insufficient data'
                }
            
            return {
                'success': True,
                'test_id': test_id,
                'test_name': report.test_config.test_name,
                'test_status': report.test_status.value,
                'overall_confidence': report.statistical_confidence,
                'winning_variation': report.winning_variation,
                'control_results': {
                    'variation_name': report.control_results.variation_name,
                    'sample_size': report.control_results.sample_size,
                    'primary_metric_value': report.control_results.primary_metric_value,
                    'statistical_significance': report.control_results.statistical_significance
                },
                'test_results': [
                    {
                        'variation_name': result.variation_name,
                        'sample_size': result.sample_size,
                        'primary_metric_value': result.primary_metric_value,
                        'improvement_over_control': result.improvement_over_control,
                        'statistical_significance': result.statistical_significance
                    }
                    for result in report.test_results
                ],
                'business_impact': report.business_impact_analysis,
                'recommendations': report.recommendations,
                'generated_at': report.generated_at
            }
            
        except Exception as e:
            logger.error(f"Failed to get A/B test results: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def update_personality_preferences(
        self,
        preferences: Dict[str, Any],
        successful_patterns: Optional[List[str]] = None,
        avoided_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Update customer personality preferences based on feedback.
        
        Args:
            preferences: Updated personality preferences
            successful_patterns: Communication patterns that worked well
            avoided_patterns: Communication patterns to avoid
            
        Returns:
            Dictionary with update results
        """
        if not self._initialized:
            return {
                'success': False,
                'error': 'Personality engine not initialized'
            }
        
        try:
            updated_profile = await self.personality_engine.update_personality_profile(
                customer_id=self.customer_id,
                preferences=preferences,
                successful_patterns=successful_patterns,
                avoided_patterns=avoided_patterns
            )
            
            return {
                'success': True,
                'customer_id': self.customer_id,
                'updated_preferences': updated_profile.communication_style_preferences,
                'successful_patterns_count': len(updated_profile.successful_patterns),
                'avoided_patterns_count': len(updated_profile.avoided_patterns),
                'consistency_score': updated_profile.personality_consistency_score,
                'updated_at': updated_profile.updated_at
            }
            
        except Exception as e:
            logger.error(f"Failed to update personality preferences: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for personality engine.
        
        Returns:
            Dictionary with performance metrics
        """
        try:
            # Get database performance metrics
            db_metrics = {}
            if self.personality_database:
                db_metrics = await self.personality_database.get_performance_metrics(
                    customer_id=self.customer_id,
                    hours_back=24
                )
            
            # Get consistency manager stats
            consistency_stats = {}
            if self.consistency_manager:
                consistency_stats = self.consistency_manager.get_monitoring_stats()
            
            # Get A/B testing stats
            ab_testing_stats = {}
            if self.ab_testing_framework:
                ab_testing_stats = self.ab_testing_framework.get_framework_stats()
            
            # Calculate average transformation time
            avg_transformation_time = 0
            if self._performance_stats['transformations_performed'] > 0:
                avg_transformation_time = (
                    self._performance_stats['total_transformation_time_ms'] / 
                    self._performance_stats['transformations_performed']
                )
            
            # Calculate cache hit rate
            cache_hit_rate = 0.0
            if self._performance_stats['transformations_performed'] > 0:
                cache_hit_rate = (
                    self._performance_stats['cache_hits'] / 
                    self._performance_stats['transformations_performed']
                )
            
            return {
                'success': True,
                'customer_id': self.customer_id,
                'integration_stats': {
                    'transformations_performed': self._performance_stats['transformations_performed'],
                    'avg_transformation_time_ms': int(avg_transformation_time),
                    'cache_hit_rate': cache_hit_rate,
                    'consistency_alerts': self._performance_stats['consistency_alerts'],
                    'ab_tests_active': self._performance_stats['ab_tests_active'],
                    'performance_sla_met': avg_transformation_time < 500,  # <500ms SLA
                    'initialized': self._initialized
                },
                'database_metrics': db_metrics,
                'consistency_stats': consistency_stats,
                'ab_testing_stats': ab_testing_stats,
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {
                'success': False,
                'error': str(e),
                'generated_at': datetime.now().isoformat()
            }
    
    async def cleanup(self) -> None:
        """Clean up resources and close connections"""
        
        try:
            if self.memory_client:
                await self.memory_client._close_session()
            
            if self.personality_database:
                await self.personality_database.close()
            
            self._initialized = False
            logger.info(f"PersonalityEngineIntegration cleanup completed for customer {self.customer_id}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Utility functions for EA system integration
async def initialize_personality_for_customer(
    customer_id: str,
    openai_api_key: str,
    database_url: str,
    memory_service_url: str,
    **kwargs
) -> PersonalityEngineIntegration:
    """
    Initialize personality engine for a customer with default configuration.
    
    Args:
        customer_id: Customer identifier
        openai_api_key: OpenAI API key
        database_url: PostgreSQL connection string
        memory_service_url: MCP memory service URL
        **kwargs: Additional configuration options
        
    Returns:
        Initialized PersonalityEngineIntegration
    """
    config = PersonalityConfig(
        customer_id=customer_id,
        openai_api_key=openai_api_key,
        database_url=database_url,
        memory_service_url=memory_service_url,
        **kwargs
    )
    
    integration = PersonalityEngineIntegration(config)
    await integration.initialize()
    
    return integration


def create_simple_transformation_request(
    customer_id: str,
    content: str,
    channel: str = "web_chat",
    **kwargs
) -> TransformationRequest:
    """
    Create a simple transformation request with defaults.
    
    Args:
        customer_id: Customer identifier
        content: Content to transform
        channel: Communication channel
        **kwargs: Additional request options
        
    Returns:
        TransformationRequest ready for processing
    """
    return TransformationRequest(
        customer_id=customer_id,
        original_content=content,
        channel=channel,
        **kwargs
    )


async def quick_personality_transform(
    customer_id: str,
    content: str,
    channel: str,
    integration: PersonalityEngineIntegration
) -> str:
    """
    Quick personality transformation with minimal setup.
    
    Args:
        customer_id: Customer identifier
        content: Content to transform
        channel: Communication channel
        integration: Initialized PersonalityEngineIntegration
        
    Returns:
        Transformed content string
    """
    try:
        request = create_simple_transformation_request(
            customer_id=customer_id,
            content=content,
            channel=channel
        )
        
        response = await integration.transform_message(request)
        
        if response.success:
            return response.transformed_content
        else:
            logger.warning(f"Transformation failed: {response.error_message}")
            return content  # Return original on failure
            
    except Exception as e:
        logger.error(f"Quick transformation failed: {e}")
        return content  # Return original on error