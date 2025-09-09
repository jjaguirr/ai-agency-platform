"""
A/B Testing Framework for Personality Variations
Enables systematic testing of personality variations to optimize premium-casual messaging effectiveness
"""

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import statistics

from .personality_engine import (
    PersonalityEngine, CommunicationChannel, PersonalityTone, ConversationContext,
    PersonalityTransformationResult
)
from .personality_database import PersonalityDatabase

logger = logging.getLogger(__name__)


class TestStatus(Enum):
    """A/B test status"""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TestMetric(Enum):
    """Metrics for A/B test evaluation"""
    CONSISTENCY_SCORE = "consistency_score"
    USER_PREFERENCE = "user_preference"
    ENGAGEMENT_RATE = "engagement_rate"
    TRANSFORMATION_TIME = "transformation_time"
    PREMIUM_CASUAL_INDICATORS = "premium_casual_indicators"


@dataclass
class ABTestVariation:
    """Configuration for a single A/B test variation"""
    name: str
    description: str
    personality_tone: PersonalityTone
    conversation_context: Optional[ConversationContext] = None
    custom_prompt_additions: List[str] = field(default_factory=list)
    expected_improvement: Optional[str] = None
    traffic_allocation: float = 0.5  # Percentage of traffic (0.0 to 1.0)


@dataclass
class ABTestConfig:
    """Complete A/B test configuration"""
    test_id: str
    test_name: str
    description: str
    customer_id: str
    channels: List[CommunicationChannel]
    control_variation: ABTestVariation
    test_variations: List[ABTestVariation]
    primary_metric: TestMetric
    secondary_metrics: List[TestMetric]
    minimum_sample_size: int = 30
    test_duration_hours: int = 168  # 1 week default
    statistical_significance_threshold: float = 0.05
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ABTestResult:
    """Results from an A/B test variation"""
    variation_name: str
    sample_size: int
    primary_metric_value: float
    secondary_metric_values: Dict[TestMetric, float]
    confidence_interval: Tuple[float, float]
    statistical_significance: bool
    improvement_over_control: float
    raw_results: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ABTestReport:
    """Complete A/B test report with analysis"""
    test_config: ABTestConfig
    test_status: TestStatus
    start_time: str
    end_time: Optional[str]
    control_results: ABTestResult
    test_results: List[ABTestResult]
    winning_variation: Optional[str]
    statistical_confidence: float
    business_impact_analysis: Dict[str, Any]
    recommendations: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class PersonalityABTestingFramework:
    """
    A/B testing framework for personality variations.
    
    Enables systematic testing of different personality approaches to optimize
    premium-casual messaging effectiveness across different customer segments
    and communication channels.
    """
    
    def __init__(
        self,
        personality_engine: PersonalityEngine,
        personality_database: PersonalityDatabase,
        enable_automatic_rollout: bool = True,
        confidence_threshold: float = 0.95
    ):
        """
        Initialize A/B testing framework.
        
        Args:
            personality_engine: PersonalityEngine instance
            personality_database: PersonalityDatabase instance
            enable_automatic_rollout: Automatically rollout winning variations
            confidence_threshold: Statistical confidence threshold for decisions
        """
        self.personality_engine = personality_engine
        self.personality_database = personality_database
        self.enable_automatic_rollout = enable_automatic_rollout
        self.confidence_threshold = confidence_threshold
        
        # Active tests tracking
        self.active_tests: Dict[str, ABTestConfig] = {}
        self.test_assignments: Dict[str, Dict[str, str]] = {}  # customer_id -> test_id -> variation
        self.test_results_cache: Dict[str, List[Dict[str, Any]]] = {}
        
        # Performance tracking
        self.tests_created = 0
        self.tests_completed = 0
        self.variations_deployed = 0
        
        logger.info("PersonalityABTestingFramework initialized")
    
    async def create_ab_test(
        self,
        test_name: str,
        description: str,
        customer_id: str,
        channels: List[CommunicationChannel],
        test_variations: List[ABTestVariation],
        control_variation: Optional[ABTestVariation] = None,
        primary_metric: TestMetric = TestMetric.CONSISTENCY_SCORE,
        secondary_metrics: Optional[List[TestMetric]] = None,
        test_duration_hours: int = 168  # 1 week
    ) -> str:
        """
        Create a new A/B test for personality variations.
        
        Args:
            test_name: Human-readable test name
            description: Test description and objectives
            customer_id: Customer to run test for
            channels: Communication channels to test
            test_variations: List of test variations to evaluate
            control_variation: Control variation (default if None)
            primary_metric: Primary success metric
            secondary_metrics: Additional metrics to track
            test_duration_hours: Test duration in hours
            
        Returns:
            Test ID for tracking
        """
        try:
            test_id = f"ab_test_{uuid.uuid4().hex[:8]}"
            
            # Create control variation if not provided
            if control_variation is None:
                control_variation = ABTestVariation(
                    name="control",
                    description="Current default personality",
                    personality_tone=PersonalityTone.PROFESSIONAL_WARM,
                    traffic_allocation=0.5
                )
            
            # Normalize traffic allocation
            total_allocation = control_variation.traffic_allocation + sum(v.traffic_allocation for v in test_variations)
            if total_allocation > 1.0:
                # Normalize to 1.0
                control_variation.traffic_allocation /= total_allocation
                for variation in test_variations:
                    variation.traffic_allocation /= total_allocation
            
            # Create test configuration
            test_config = ABTestConfig(
                test_id=test_id,
                test_name=test_name,
                description=description,
                customer_id=customer_id,
                channels=channels,
                control_variation=control_variation,
                test_variations=test_variations,
                primary_metric=primary_metric,
                secondary_metrics=secondary_metrics or [TestMetric.TRANSFORMATION_TIME],
                test_duration_hours=test_duration_hours
            )
            
            # Store test configuration
            self.active_tests[test_id] = test_config
            self.test_results_cache[test_id] = []
            
            # Initialize customer assignment tracking
            if customer_id not in self.test_assignments:
                self.test_assignments[customer_id] = {}
            
            self.tests_created += 1
            
            logger.info(f"Created A/B test '{test_name}' (ID: {test_id}) for customer {customer_id}")
            
            return test_id
            
        except Exception as e:
            logger.error(f"Failed to create A/B test: {e}")
            raise
    
    async def get_test_variation(
        self,
        customer_id: str,
        channel: CommunicationChannel,
        test_id: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[ABTestVariation]]:
        """
        Get the assigned test variation for a customer.
        
        Args:
            customer_id: Customer identifier
            channel: Communication channel
            test_id: Specific test ID (optional, will find active tests if None)
            
        Returns:
            Tuple of (test_id, variation) or (None, None) if no active test
        """
        try:
            # Find active tests for this customer
            active_customer_tests = []
            
            if test_id:
                if test_id in self.active_tests and self.active_tests[test_id].customer_id == customer_id:
                    active_customer_tests = [test_id]
            else:
                active_customer_tests = [
                    tid for tid, config in self.active_tests.items()
                    if config.customer_id == customer_id and channel in config.channels
                ]
            
            if not active_customer_tests:
                return None, None
            
            # Use the first active test (prioritize by creation order)
            selected_test_id = active_customer_tests[0]
            test_config = self.active_tests[selected_test_id]
            
            # Check if customer already has assignment for this test
            if (customer_id in self.test_assignments and 
                selected_test_id in self.test_assignments[customer_id]):
                variation_name = self.test_assignments[customer_id][selected_test_id]
                
                # Find variation by name
                if variation_name == test_config.control_variation.name:
                    return selected_test_id, test_config.control_variation
                else:
                    for variation in test_config.test_variations:
                        if variation.name == variation_name:
                            return selected_test_id, variation
            
            # Assign customer to a variation based on traffic allocation
            variation = self._assign_customer_to_variation(customer_id, test_config)
            
            # Store assignment
            if customer_id not in self.test_assignments:
                self.test_assignments[customer_id] = {}
            self.test_assignments[customer_id][selected_test_id] = variation.name
            
            return selected_test_id, variation
            
        except Exception as e:
            logger.error(f"Failed to get test variation: {e}")
            return None, None
    
    async def record_test_result(
        self,
        test_id: str,
        customer_id: str,
        transformation_result: PersonalityTransformationResult,
        variation_name: str,
        additional_metrics: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Record a test result for analysis.
        
        Args:
            test_id: Test identifier
            customer_id: Customer identifier
            transformation_result: Transformation result from personality engine
            variation_name: Name of the variation that was used
            additional_metrics: Additional metrics (engagement, user preference, etc.)
            
        Returns:
            True if recorded successfully
        """
        try:
            if test_id not in self.active_tests:
                logger.warning(f"Attempted to record result for inactive test: {test_id}")
                return False
            
            # Prepare test result record
            test_result = {
                'test_id': test_id,
                'customer_id': customer_id,
                'variation_name': variation_name,
                'channel': transformation_result.channel.value,
                'transformation_time_ms': transformation_result.transformation_time_ms,
                'consistency_score': transformation_result.consistency_score,
                'premium_casual_indicators': transformation_result.premium_casual_indicators,
                'original_content_length': len(transformation_result.original_content),
                'transformed_content_length': len(transformation_result.transformed_content),
                'additional_metrics': additional_metrics or {},
                'recorded_at': datetime.now().isoformat()
            }
            
            # Add to results cache
            if test_id not in self.test_results_cache:
                self.test_results_cache[test_id] = []
            self.test_results_cache[test_id].append(test_result)
            
            # Store in database
            await self.personality_database.store_ab_test_result(
                customer_id=customer_id,
                test_name=self.active_tests[test_id].test_name,
                variation_name=variation_name,
                result=transformation_result,
                user_preference_score=additional_metrics.get('user_preference_score') if additional_metrics else None,
                engagement_metrics=additional_metrics
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to record test result: {e}")
            return False
    
    async def analyze_test_results(
        self,
        test_id: str,
        force_analysis: bool = False
    ) -> Optional[ABTestReport]:
        """
        Analyze A/B test results and generate report.
        
        Args:
            test_id: Test identifier
            force_analysis: Force analysis even if test isn't complete
            
        Returns:
            ABTestReport with analysis or None if insufficient data
        """
        try:
            if test_id not in self.active_tests:
                logger.error(f"Test not found: {test_id}")
                return None
            
            test_config = self.active_tests[test_id]
            
            # Get test results from database
            db_results = await self.personality_database.get_ab_test_results(
                customer_id=test_config.customer_id,
                test_name=test_config.test_name
            )
            
            # Combine with cached results
            all_results = db_results + self.test_results_cache.get(test_id, [])
            
            if not all_results:
                logger.warning(f"No results found for test {test_id}")
                return None
            
            # Group results by variation
            variation_results = {}
            for result in all_results:
                variation = result.get('variation_name', 'unknown')
                if variation not in variation_results:
                    variation_results[variation] = []
                variation_results[variation].append(result)
            
            # Check if we have minimum sample size
            total_samples = len(all_results)
            if not force_analysis and total_samples < test_config.minimum_sample_size:
                logger.info(f"Test {test_id} needs more samples: {total_samples}/{test_config.minimum_sample_size}")
                return None
            
            # Analyze control variation
            control_name = test_config.control_variation.name
            control_results = self._analyze_variation_results(
                variation_results.get(control_name, []),
                control_name,
                test_config.primary_metric,
                test_config.secondary_metrics
            )
            
            # Analyze test variations
            test_results = []
            for variation in test_config.test_variations:
                variation_data = variation_results.get(variation.name, [])
                if variation_data:
                    analysis = self._analyze_variation_results(
                        variation_data,
                        variation.name,
                        test_config.primary_metric,
                        test_config.secondary_metrics
                    )
                    
                    # Calculate improvement over control
                    if control_results.primary_metric_value > 0:
                        improvement = (
                            (analysis.primary_metric_value - control_results.primary_metric_value) 
                            / control_results.primary_metric_value * 100
                        )
                        analysis.improvement_over_control = improvement
                    
                    test_results.append(analysis)
            
            # Determine winning variation
            winning_variation = None
            max_primary_metric = control_results.primary_metric_value
            
            for result in test_results:
                if (result.statistical_significance and 
                    result.primary_metric_value > max_primary_metric):
                    max_primary_metric = result.primary_metric_value
                    winning_variation = result.variation_name
            
            # Calculate statistical confidence
            statistical_confidence = self._calculate_overall_confidence(control_results, test_results)
            
            # Generate business impact analysis
            business_impact = self._analyze_business_impact(control_results, test_results, test_config)
            
            # Generate recommendations
            recommendations = self._generate_test_recommendations(
                control_results, test_results, winning_variation, business_impact
            )
            
            # Create test report
            report = ABTestReport(
                test_config=test_config,
                test_status=TestStatus.ACTIVE,
                start_time=test_config.created_at,
                end_time=None,
                control_results=control_results,
                test_results=test_results,
                winning_variation=winning_variation,
                statistical_confidence=statistical_confidence,
                business_impact_analysis=business_impact,
                recommendations=recommendations
            )
            
            logger.info(f"Generated A/B test report for {test_id}, winning variation: {winning_variation}")
            
            return report
            
        except Exception as e:
            logger.error(f"Failed to analyze test results: {e}")
            return None
    
    async def complete_test(
        self,
        test_id: str,
        auto_deploy_winner: bool = None
    ) -> Optional[ABTestReport]:
        """
        Complete an A/B test and optionally deploy the winning variation.
        
        Args:
            test_id: Test identifier
            auto_deploy_winner: Whether to auto-deploy winner (uses instance setting if None)
            
        Returns:
            Final test report
        """
        try:
            # Generate final analysis
            final_report = await self.analyze_test_results(test_id, force_analysis=True)
            
            if not final_report:
                logger.error(f"Could not generate final report for test {test_id}")
                return None
            
            # Mark test as completed
            final_report.test_status = TestStatus.COMPLETED
            final_report.end_time = datetime.now().isoformat()
            
            # Deploy winning variation if enabled
            deploy_winner = auto_deploy_winner if auto_deploy_winner is not None else self.enable_automatic_rollout
            
            if deploy_winner and final_report.winning_variation:
                await self._deploy_winning_variation(test_id, final_report)
            
            # Remove from active tests
            if test_id in self.active_tests:
                del self.active_tests[test_id]
            
            # Clean up cache
            if test_id in self.test_results_cache:
                del self.test_results_cache[test_id]
            
            self.tests_completed += 1
            
            logger.info(f"Completed A/B test {test_id}, winner: {final_report.winning_variation}")
            
            return final_report
            
        except Exception as e:
            logger.error(f"Failed to complete test: {e}")
            return None
    
    def _assign_customer_to_variation(
        self,
        customer_id: str,
        test_config: ABTestConfig
    ) -> ABTestVariation:
        """Assign customer to a test variation based on traffic allocation"""
        
        # Use customer ID as seed for consistent assignment
        random.seed(hash(customer_id + test_config.test_id))
        
        assignment_value = random.random()
        
        # Check control variation
        if assignment_value < test_config.control_variation.traffic_allocation:
            return test_config.control_variation
        
        # Check test variations
        cumulative_allocation = test_config.control_variation.traffic_allocation
        for variation in test_config.test_variations:
            cumulative_allocation += variation.traffic_allocation
            if assignment_value < cumulative_allocation:
                return variation
        
        # Fallback to control
        return test_config.control_variation
    
    def _analyze_variation_results(
        self,
        results: List[Dict[str, Any]],
        variation_name: str,
        primary_metric: TestMetric,
        secondary_metrics: List[TestMetric]
    ) -> ABTestResult:
        """Analyze results for a single variation"""
        
        if not results:
            return ABTestResult(
                variation_name=variation_name,
                sample_size=0,
                primary_metric_value=0.0,
                secondary_metric_values={},
                confidence_interval=(0.0, 0.0),
                statistical_significance=False,
                improvement_over_control=0.0
            )
        
        sample_size = len(results)
        
        # Extract primary metric values
        primary_values = []
        for result in results:
            if primary_metric == TestMetric.CONSISTENCY_SCORE:
                primary_values.append(result.get('consistency_score', 0.0))
            elif primary_metric == TestMetric.TRANSFORMATION_TIME:
                primary_values.append(result.get('transformation_time_ms', 0))
            elif primary_metric == TestMetric.PREMIUM_CASUAL_INDICATORS:
                indicators = result.get('premium_casual_indicators', [])
                primary_values.append(len(indicators))
            elif primary_metric == TestMetric.USER_PREFERENCE:
                additional_metrics = result.get('additional_metrics', {})
                primary_values.append(additional_metrics.get('user_preference_score', 0.0))
        
        # Filter out None values
        primary_values = [v for v in primary_values if v is not None]
        
        if not primary_values:
            primary_metric_value = 0.0
            confidence_interval = (0.0, 0.0)
        else:
            primary_metric_value = statistics.mean(primary_values)
            
            # Calculate confidence interval (approximate)
            if len(primary_values) > 1:
                std_error = statistics.stdev(primary_values) / (len(primary_values) ** 0.5)
                margin = 1.96 * std_error  # 95% confidence interval
                confidence_interval = (
                    primary_metric_value - margin,
                    primary_metric_value + margin
                )
            else:
                confidence_interval = (primary_metric_value, primary_metric_value)
        
        # Calculate secondary metrics
        secondary_metric_values = {}
        for metric in secondary_metrics:
            if metric == TestMetric.CONSISTENCY_SCORE:
                values = [r.get('consistency_score', 0.0) for r in results if r.get('consistency_score') is not None]
            elif metric == TestMetric.TRANSFORMATION_TIME:
                values = [r.get('transformation_time_ms', 0) for r in results if r.get('transformation_time_ms') is not None]
            elif metric == TestMetric.PREMIUM_CASUAL_INDICATORS:
                values = [len(r.get('premium_casual_indicators', [])) for r in results]
            else:
                values = []
            
            if values:
                secondary_metric_values[metric] = statistics.mean(values)
            else:
                secondary_metric_values[metric] = 0.0
        
        # Statistical significance (simplified)
        statistical_significance = sample_size >= 30 and len(primary_values) >= 30
        
        return ABTestResult(
            variation_name=variation_name,
            sample_size=sample_size,
            primary_metric_value=primary_metric_value,
            secondary_metric_values=secondary_metric_values,
            confidence_interval=confidence_interval,
            statistical_significance=statistical_significance,
            improvement_over_control=0.0,  # Will be calculated later
            raw_results=results
        )
    
    def _calculate_overall_confidence(
        self,
        control_results: ABTestResult,
        test_results: List[ABTestResult]
    ) -> float:
        """Calculate overall statistical confidence of the test"""
        
        if not test_results:
            return 0.0
        
        # Simplified confidence calculation based on sample sizes and significance
        total_samples = control_results.sample_size + sum(r.sample_size for r in test_results)
        
        if total_samples < 60:  # Minimum for reasonable confidence
            return 0.5
        
        significant_results = sum(1 for r in test_results if r.statistical_significance)
        confidence_score = min(0.95, 0.5 + (significant_results / len(test_results)) * 0.45)
        
        return confidence_score
    
    def _analyze_business_impact(
        self,
        control_results: ABTestResult,
        test_results: List[ABTestResult],
        test_config: ABTestConfig
    ) -> Dict[str, Any]:
        """Analyze business impact of test results"""
        
        business_impact = {
            'total_samples': control_results.sample_size + sum(r.sample_size for r in test_results),
            'test_duration_days': test_config.test_duration_hours / 24,
            'channels_tested': len(test_config.channels),
            'performance_improvements': {},
            'consistency_improvements': {},
            'potential_rollout_impact': {}
        }
        
        # Analyze performance improvements
        best_performance = control_results.secondary_metric_values.get(TestMetric.TRANSFORMATION_TIME, 0)
        for result in test_results:
            performance = result.secondary_metric_values.get(TestMetric.TRANSFORMATION_TIME, 0)
            if performance > 0 and (best_performance == 0 or performance < best_performance):
                best_performance = performance
                improvement_ms = control_results.secondary_metric_values.get(TestMetric.TRANSFORMATION_TIME, 0) - performance
                business_impact['performance_improvements'][result.variation_name] = {
                    'improvement_ms': improvement_ms,
                    'percentage_improvement': (improvement_ms / control_results.secondary_metric_values.get(TestMetric.TRANSFORMATION_TIME, 1)) * 100
                }
        
        # Analyze consistency improvements
        control_consistency = control_results.primary_metric_value
        for result in test_results:
            if result.primary_metric_value > control_consistency:
                improvement = result.primary_metric_value - control_consistency
                business_impact['consistency_improvements'][result.variation_name] = {
                    'improvement': improvement,
                    'percentage_improvement': (improvement / control_consistency) * 100 if control_consistency > 0 else 0
                }
        
        return business_impact
    
    def _generate_test_recommendations(
        self,
        control_results: ABTestResult,
        test_results: List[ABTestResult],
        winning_variation: Optional[str],
        business_impact: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on test results"""
        
        recommendations = []
        
        # Winning variation recommendation
        if winning_variation:
            recommendations.append(f"Deploy '{winning_variation}' as it shows significant improvement over control")
        else:
            recommendations.append("No clear winner identified - consider extending test duration or testing new variations")
        
        # Performance recommendations
        if business_impact.get('performance_improvements'):
            best_performance_variation = min(
                business_impact['performance_improvements'].items(),
                key=lambda x: x[1]['improvement_ms']
            )
            recommendations.append(
                f"Consider adopting performance optimizations from '{best_performance_variation[0]}'"
            )
        
        # Consistency recommendations
        if business_impact.get('consistency_improvements'):
            best_consistency_variation = max(
                business_impact['consistency_improvements'].items(),
                key=lambda x: x[1]['improvement']
            )
            recommendations.append(
                f"Incorporate consistency patterns from '{best_consistency_variation[0]}' variation"
            )
        
        # Sample size recommendations
        if control_results.sample_size < 50:
            recommendations.append("Increase sample size for more reliable results")
        
        return recommendations
    
    async def _deploy_winning_variation(
        self,
        test_id: str,
        final_report: ABTestReport
    ) -> bool:
        """Deploy the winning variation to customer's personality profile"""
        
        try:
            if not final_report.winning_variation:
                return False
            
            test_config = final_report.test_config
            winning_variation = None
            
            # Find the winning variation configuration
            if final_report.winning_variation == test_config.control_variation.name:
                winning_variation = test_config.control_variation
            else:
                for variation in test_config.test_variations:
                    if variation.name == final_report.winning_variation:
                        winning_variation = variation
                        break
            
            if not winning_variation:
                logger.error(f"Could not find winning variation configuration: {final_report.winning_variation}")
                return False
            
            # Update customer personality profile
            preferences = {
                'ab_test_winner': final_report.winning_variation,
                'ab_test_deployment_date': datetime.now().isoformat(),
                'ab_test_id': test_id
            }
            
            successful_patterns = []
            if winning_variation.custom_prompt_additions:
                successful_patterns.extend(winning_variation.custom_prompt_additions)
            
            await self.personality_engine.update_personality_profile(
                customer_id=test_config.customer_id,
                preferences=preferences,
                successful_patterns=successful_patterns
            )
            
            self.variations_deployed += 1
            
            logger.info(f"Deployed winning variation '{final_report.winning_variation}' for customer {test_config.customer_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to deploy winning variation: {e}")
            return False
    
    def get_framework_stats(self) -> Dict[str, Any]:
        """Get A/B testing framework statistics"""
        
        return {
            'tests_created': self.tests_created,
            'tests_completed': self.tests_completed,
            'variations_deployed': self.variations_deployed,
            'active_tests': len(self.active_tests),
            'customers_in_tests': len(self.test_assignments),
            'enable_automatic_rollout': self.enable_automatic_rollout,
            'confidence_threshold': self.confidence_threshold
        }


# Utility functions for A/B testing
def create_tone_variation_test(
    customer_id: str,
    channels: List[CommunicationChannel],
    test_name: str = "Personality Tone Optimization"
) -> List[ABTestVariation]:
    """Create standard personality tone variation test"""
    
    return [
        ABTestVariation(
            name="control",
            description="Current professional warm tone",
            personality_tone=PersonalityTone.PROFESSIONAL_WARM,
            traffic_allocation=0.25
        ),
        ABTestVariation(
            name="motivational",
            description="More motivational and encouraging",
            personality_tone=PersonalityTone.MOTIVATIONAL,
            traffic_allocation=0.25
        ),
        ABTestVariation(
            name="supportive",
            description="More supportive and understanding",
            personality_tone=PersonalityTone.SUPPORTIVE,
            traffic_allocation=0.25
        ),
        ABTestVariation(
            name="strategic",
            description="More strategic and business-focused",
            personality_tone=PersonalityTone.STRATEGIC,
            traffic_allocation=0.25
        )
    ]


def create_channel_consistency_test(
    customer_id: str,
    primary_channel: CommunicationChannel,
    secondary_channels: List[CommunicationChannel]
) -> List[ABTestVariation]:
    """Create test for optimizing cross-channel consistency"""
    
    variations = [
        ABTestVariation(
            name="control",
            description="Current channel-specific adaptation",
            personality_tone=PersonalityTone.PROFESSIONAL_WARM,
            traffic_allocation=0.5
        ),
        ABTestVariation(
            name="unified_consistency",
            description="Unified personality across all channels",
            personality_tone=PersonalityTone.PROFESSIONAL_WARM,
            custom_prompt_additions=[
                "Maintain identical personality across all communication channels",
                "Prioritize consistency over channel-specific adaptation"
            ],
            traffic_allocation=0.5
        )
    ]
    
    return variations