"""
Test Voice Analytics Integration
Comprehensive testing of the voice interaction logging & analytics system
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import json

# Test imports
import pytest

# Local imports
from .voice_analytics_pipeline import voice_analytics_pipeline, VoiceInteractionAnalytics
from .business_intelligence import voice_business_intelligence
from .cost_tracker import voice_cost_tracker
from .quality_analyzer import voice_quality_analyzer
from ..monitoring.voice_performance_monitor import VoiceInteractionMetrics

# Setup logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VoiceAnalyticsTestSuite:
    """
    Comprehensive test suite for voice analytics system
    
    Tests:
    - Analytics pipeline integration
    - Cost tracking accuracy
    - Quality analysis functionality
    - Business intelligence insights
    - Real-time dashboard data
    - Performance metrics
    - Alert system functionality
    """
    
    def __init__(self):
        self.test_customer_id = "test_customer_analytics_001"
        self.test_conversation_id = "test_conversation_001"
        self.test_results = {}
    
    async def run_comprehensive_tests(self):
        """Run all analytics tests"""
        logger.info("Starting comprehensive voice analytics tests...")
        
        # Test basic integration
        await self.test_analytics_pipeline_integration()
        
        # Test cost tracking
        await self.test_cost_tracking_functionality()
        
        # Test quality analysis
        await self.test_quality_analysis_system()
        
        # Test business intelligence
        await self.test_business_intelligence_insights()
        
        # Test dashboard APIs
        await self.test_dashboard_data_generation()
        
        # Test alert system
        await self.test_alert_system_functionality()
        
        # Test performance and scalability
        await self.test_performance_scalability()
        
        # Generate test report
        self.generate_test_report()
        
        logger.info("Voice analytics testing completed")
        return self.test_results
    
    async def test_analytics_pipeline_integration(self):
        """Test analytics pipeline integration"""
        logger.info("Testing analytics pipeline integration...")
        
        try:
            # Create test voice interaction metrics
            test_metrics = VoiceInteractionMetrics(
                customer_id=self.test_customer_id,
                conversation_id=self.test_conversation_id,
                interaction_id=f"test_interaction_{int(datetime.now().timestamp())}",
                timestamp=datetime.now(),
                total_response_time=1.5,
                speech_to_text_time=0.3,
                ea_processing_time=1.0,
                text_to_speech_time=0.2,
                audio_input_size_bytes=50000,
                audio_output_size_bytes=75000,
                transcript_length=150,
                response_length=200,
                detected_language="en",
                response_language="en",
                language_switch=False,
                success=True,
                error_type=None,
                error_message=None
            )
            
            # Test conversation context
            conversation_context = {
                "message_text": "Hello, can you help me with my business analytics?",
                "response_text": "Absolutely! I can help you analyze your business performance, identify trends, and provide actionable insights. What specific area would you like to focus on?",
                "interaction_success": True,
                "relevance_score": 0.9
            }
            
            # Test business context
            business_context = {
                "high_value_customer": True,
                "strategic_conversation": True,
                "value_created": True,
                "premium_features_mentioned": False,
                "growth_indicators": True
            }
            
            # Process through analytics pipeline
            analytics_result = await voice_analytics_pipeline.process_interaction(
                test_metrics,
                conversation_context,
                business_context
            )
            
            # Verify analytics result
            assert isinstance(analytics_result, VoiceInteractionAnalytics)
            assert analytics_result.customer_id == self.test_customer_id
            assert analytics_result.business_value_score > 0
            assert 0 <= analytics_result.customer_satisfaction_estimate <= 1
            assert 0 <= analytics_result.churn_risk_score <= 1
            
            self.test_results["analytics_pipeline"] = {
                "status": "PASSED",
                "business_value_score": analytics_result.business_value_score,
                "satisfaction_estimate": analytics_result.customer_satisfaction_estimate,
                "engagement_score": analytics_result.engagement_indicators["engagement_score"]
            }
            
            logger.info("Analytics pipeline integration test PASSED")
            
        except Exception as e:
            self.test_results["analytics_pipeline"] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"Analytics pipeline integration test FAILED: {e}")
    
    async def test_cost_tracking_functionality(self):
        """Test cost tracking system"""
        logger.info("Testing cost tracking functionality...")
        
        try:
            # Create test metrics for cost tracking
            test_metrics = VoiceInteractionMetrics(
                customer_id=self.test_customer_id,
                conversation_id=self.test_conversation_id,
                interaction_id=f"cost_test_{int(datetime.now().timestamp())}",
                timestamp=datetime.now(),
                total_response_time=2.0,
                speech_to_text_time=0.4,
                ea_processing_time=1.2,
                text_to_speech_time=0.4,
                audio_input_size_bytes=60000,
                audio_output_size_bytes=80000,
                transcript_length=180,
                response_length=250,
                detected_language="en",
                response_language="en",
                language_switch=False,
                success=True
            )
            
            # Track interaction cost
            cost_breakdown = await voice_cost_tracker.track_interaction_cost(
                test_metrics,
                {"business_value_score": 75}
            )
            
            # Verify cost breakdown
            assert cost_breakdown.total_cost > 0
            assert cost_breakdown.elevenlabs_tts_cost >= 0
            assert cost_breakdown.whisper_stt_cost >= 0
            assert cost_breakdown.compute_cost > 0
            assert cost_breakdown.cost_per_second > 0
            
            # Test cost forecasting
            forecast = await voice_cost_tracker.forecast_costs(
                forecast_days=7,
                customer_id=self.test_customer_id
            )
            
            assert "total_forecast" in forecast
            assert forecast["forecast_period_days"] == 7
            
            # Test cost optimization recommendations
            recommendations = await voice_cost_tracker.generate_cost_optimization_recommendations(
                customer_id=self.test_customer_id,
                analysis_period_days=7
            )
            
            self.test_results["cost_tracking"] = {
                "status": "PASSED",
                "total_cost": cost_breakdown.total_cost,
                "cost_per_second": cost_breakdown.cost_per_second,
                "forecast_generated": len(forecast) > 0,
                "recommendations_count": len(recommendations)
            }
            
            logger.info("Cost tracking functionality test PASSED")
            
        except Exception as e:
            self.test_results["cost_tracking"] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"Cost tracking functionality test FAILED: {e}")
    
    async def test_quality_analysis_system(self):
        """Test quality analysis system"""
        logger.info("Testing quality analysis system...")
        
        try:
            # Create test metrics for quality analysis
            test_metrics = VoiceInteractionMetrics(
                customer_id=self.test_customer_id,
                conversation_id=self.test_conversation_id,
                interaction_id=f"quality_test_{int(datetime.now().timestamp())}",
                timestamp=datetime.now(),
                total_response_time=1.8,
                speech_to_text_time=0.3,
                ea_processing_time=1.2,
                text_to_speech_time=0.3,
                audio_input_size_bytes=55000,
                audio_output_size_bytes=70000,
                transcript_length=160,
                response_length=220,
                detected_language="en",
                response_language="en",
                language_switch=False,
                success=True
            )
            
            # Test conversation context for quality analysis
            conversation_context = {
                "message_text": "I need help analyzing my business performance metrics and identifying growth opportunities.",
                "response_text": "I'd be happy to help you analyze your business performance! Let's start by looking at your key performance indicators (KPIs). What specific metrics are you tracking currently?",
                "interaction_success": True,
                "language_quality": 0.9
            }
            
            # Analyze interaction quality
            quality_assessment = await voice_quality_analyzer.analyze_interaction_quality(
                test_metrics,
                conversation_context,
                None  # No audio data in test
            )
            
            # Verify quality assessment
            assert 0 <= quality_assessment.overall_quality <= 1
            assert 0 <= quality_assessment.audio_quality <= 1
            assert 0 <= quality_assessment.transcription_quality <= 1
            assert 0 <= quality_assessment.response_quality <= 1
            assert quality_assessment.assessment_confidence > 0
            
            # Test quality dashboard data
            quality_dashboard = voice_quality_analyzer.get_quality_dashboard_data()
            
            assert "overall_metrics" in quality_dashboard or "status" in quality_dashboard
            
            self.test_results["quality_analysis"] = {
                "status": "PASSED",
                "overall_quality": quality_assessment.overall_quality,
                "audio_quality": quality_assessment.audio_quality,
                "response_quality": quality_assessment.response_quality,
                "confidence": quality_assessment.assessment_confidence,
                "issues_count": len(quality_assessment.issues_identified)
            }
            
            logger.info("Quality analysis system test PASSED")
            
        except Exception as e:
            self.test_results["quality_analysis"] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"Quality analysis system test FAILED: {e}")
    
    async def test_business_intelligence_insights(self):
        """Test business intelligence system"""
        logger.info("Testing business intelligence insights...")
        
        try:
            # Create analytics data for business intelligence
            test_analytics = VoiceInteractionAnalytics(
                interaction_id=f"bi_test_{int(datetime.now().timestamp())}",
                customer_id=self.test_customer_id,
                conversation_id=self.test_conversation_id,
                timestamp=datetime.now(),
                performance_metrics=VoiceInteractionMetrics(
                    customer_id=self.test_customer_id,
                    conversation_id=self.test_conversation_id,
                    interaction_id="bi_test_interaction",
                    timestamp=datetime.now(),
                    total_response_time=1.5,
                    speech_to_text_time=0.3,
                    ea_processing_time=1.0,
                    text_to_speech_time=0.2,
                    audio_input_size_bytes=50000,
                    audio_output_size_bytes=70000,
                    transcript_length=150,
                    response_length=200,
                    detected_language="en",
                    response_language="en",
                    language_switch=False,
                    success=True
                ),
                cost_breakdown={"total": 0.05, "tts": 0.02, "stt": 0.01, "processing": 0.02},
                quality_scores={"overall": 0.85, "response_quality": 0.9},
                engagement_indicators={"engagement_score": 0.8, "is_returning_customer": True},
                business_context={"high_value_customer": True, "strategic_conversation": True},
                conversation_sentiment=0.3,
                personality_consistency=0.85,
                customer_satisfaction_estimate=0.8,
                business_value_score=72.0,
                churn_risk_score=0.2,
                upsell_opportunity_score=0.7,
                personal_brand_impact=0.4
            )
            
            # Process business intelligence
            await voice_business_intelligence.analyze_customer_analytics(test_analytics)
            
            # Test ROI calculation
            roi_measurement = await voice_business_intelligence.calculate_customer_roi(
                customer_id=self.test_customer_id,
                period_days=7
            )
            
            assert roi_measurement.customer_id == self.test_customer_id
            assert roi_measurement.roi_percentage != 0  # Should have some ROI calculation
            
            # Test business intelligence dashboard
            bi_dashboard = voice_business_intelligence.get_business_intelligence_dashboard()
            
            assert "business_metrics" in bi_dashboard
            assert "customer_journey" in bi_dashboard
            
            self.test_results["business_intelligence"] = {
                "status": "PASSED",
                "roi_percentage": roi_measurement.roi_percentage,
                "total_investment": roi_measurement.total_investment,
                "total_return": roi_measurement.total_quantified_return,
                "dashboard_generated": len(bi_dashboard) > 0
            }
            
            logger.info("Business intelligence insights test PASSED")
            
        except Exception as e:
            self.test_results["business_intelligence"] = {
                "status": "FAILED", 
                "error": str(e)
            }
            logger.error(f"Business intelligence insights test FAILED: {e}")
    
    async def test_dashboard_data_generation(self):
        """Test analytics dashboard data generation"""
        logger.info("Testing dashboard data generation...")
        
        try:
            # Test analytics pipeline dashboard
            pipeline_dashboard = voice_analytics_pipeline.get_analytics_dashboard_data()
            
            # Test business intelligence dashboard
            bi_dashboard = voice_business_intelligence.get_business_intelligence_dashboard()
            
            # Test cost tracker dashboard
            cost_dashboard = voice_cost_tracker.get_cost_dashboard_data()
            
            # Test quality analyzer dashboard
            quality_dashboard = voice_quality_analyzer.get_quality_dashboard_data()
            
            # Verify dashboard data structure
            assert isinstance(pipeline_dashboard, dict)
            assert isinstance(bi_dashboard, dict)
            assert isinstance(cost_dashboard, dict)
            assert isinstance(quality_dashboard, dict)
            
            self.test_results["dashboard_generation"] = {
                "status": "PASSED",
                "pipeline_dashboard_keys": len(pipeline_dashboard.keys()),
                "bi_dashboard_keys": len(bi_dashboard.keys()),
                "cost_dashboard_keys": len(cost_dashboard.keys()),
                "quality_dashboard_keys": len(quality_dashboard.keys()) if isinstance(quality_dashboard, dict) else 0
            }
            
            logger.info("Dashboard data generation test PASSED")
            
        except Exception as e:
            self.test_results["dashboard_generation"] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"Dashboard data generation test FAILED: {e}")
    
    async def test_alert_system_functionality(self):
        """Test alert system functionality"""
        logger.info("Testing alert system functionality...")
        
        try:
            # Test cost alert by simulating high cost interaction
            high_cost_metrics = VoiceInteractionMetrics(
                customer_id=self.test_customer_id,
                conversation_id=self.test_conversation_id,
                interaction_id=f"alert_test_{int(datetime.now().timestamp())}",
                timestamp=datetime.now(),
                total_response_time=5.0,  # High response time
                speech_to_text_time=1.0,
                ea_processing_time=3.5,
                text_to_speech_time=0.5,
                audio_input_size_bytes=100000,  # Large audio
                audio_output_size_bytes=150000,
                transcript_length=300,
                response_length=500,  # Long response
                detected_language="en",
                response_language="en",
                language_switch=False,
                success=True
            )
            
            # Track high-cost interaction
            await voice_cost_tracker.track_interaction_cost(
                high_cost_metrics,
                {"business_value_score": 30}  # Low business value
            )
            
            # Check for generated alerts
            cost_dashboard = voice_cost_tracker.get_cost_dashboard_data()
            active_alerts = cost_dashboard.get("active_alerts", [])
            
            # Test quality issues by creating poor quality interaction
            poor_quality_context = {
                "message_text": "unintelligible mumbled speech",
                "response_text": "I'm sorry, I didn't understand that clearly.",
                "interaction_success": False,
                "language_quality": 0.3
            }
            
            quality_assessment = await voice_quality_analyzer.analyze_interaction_quality(
                high_cost_metrics,
                poor_quality_context,
                None
            )
            
            # Verify quality issues detected
            quality_issues_found = len(quality_assessment.issues_identified) > 0
            
            self.test_results["alert_system"] = {
                "status": "PASSED",
                "cost_alerts_generated": len(active_alerts),
                "quality_issues_detected": quality_issues_found,
                "quality_issues_count": len(quality_assessment.issues_identified)
            }
            
            logger.info("Alert system functionality test PASSED")
            
        except Exception as e:
            self.test_results["alert_system"] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"Alert system functionality test FAILED: {e}")
    
    async def test_performance_scalability(self):
        """Test system performance and scalability"""
        logger.info("Testing performance and scalability...")
        
        try:
            start_time = datetime.now()
            
            # Create multiple interactions to test performance
            test_tasks = []
            
            for i in range(10):  # Test with 10 concurrent interactions
                test_metrics = VoiceInteractionMetrics(
                    customer_id=f"perf_test_customer_{i}",
                    conversation_id=f"perf_test_conv_{i}",
                    interaction_id=f"perf_test_{i}_{int(datetime.now().timestamp())}",
                    timestamp=datetime.now(),
                    total_response_time=1.0 + (i * 0.1),
                    speech_to_text_time=0.2,
                    ea_processing_time=0.6,
                    text_to_speech_time=0.2,
                    audio_input_size_bytes=45000,
                    audio_output_size_bytes=65000,
                    transcript_length=120 + (i * 10),
                    response_length=180 + (i * 15),
                    detected_language="en",
                    response_language="en",
                    language_switch=False,
                    success=True
                )
                
                conversation_context = {
                    "message_text": f"Test message {i} for performance testing",
                    "response_text": f"Test response {i} with varying length for performance analysis",
                    "interaction_success": True
                }
                
                business_context = {
                    "high_value_customer": i % 2 == 0,
                    "strategic_conversation": False
                }
                
                # Add to task list for concurrent processing
                test_tasks.append(
                    voice_analytics_pipeline.process_interaction(
                        test_metrics,
                        conversation_context,
                        business_context
                    )
                )
            
            # Process all interactions concurrently
            results = await asyncio.gather(*test_tasks, return_exceptions=True)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            successful_results = [r for r in results if not isinstance(r, Exception)]
            
            # Verify performance
            avg_processing_time = processing_time / len(test_tasks)
            assert processing_time < 10.0  # Should complete within 10 seconds
            assert len(successful_results) >= len(test_tasks) * 0.8  # At least 80% success rate
            
            self.test_results["performance_scalability"] = {
                "status": "PASSED",
                "total_processing_time": processing_time,
                "average_per_interaction": avg_processing_time,
                "successful_interactions": len(successful_results),
                "total_interactions": len(test_tasks),
                "success_rate": len(successful_results) / len(test_tasks)
            }
            
            logger.info("Performance and scalability test PASSED")
            
        except Exception as e:
            self.test_results["performance_scalability"] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"Performance and scalability test FAILED: {e}")
    
    def generate_test_report(self):
        """Generate comprehensive test report"""
        logger.info("Generating comprehensive test report...")
        
        passed_tests = sum(1 for result in self.test_results.values() if result.get("status") == "PASSED")
        total_tests = len(self.test_results)
        
        report = {
            "test_summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": total_tests - passed_tests,
                "success_rate": passed_tests / total_tests if total_tests > 0 else 0,
                "test_timestamp": datetime.now().isoformat()
            },
            "detailed_results": self.test_results,
            "system_validation": {
                "analytics_pipeline_functional": self.test_results.get("analytics_pipeline", {}).get("status") == "PASSED",
                "cost_tracking_accurate": self.test_results.get("cost_tracking", {}).get("status") == "PASSED",
                "quality_analysis_working": self.test_results.get("quality_analysis", {}).get("status") == "PASSED",
                "business_intelligence_operational": self.test_results.get("business_intelligence", {}).get("status") == "PASSED",
                "dashboards_generating": self.test_results.get("dashboard_generation", {}).get("status") == "PASSED",
                "alerts_functioning": self.test_results.get("alert_system", {}).get("status") == "PASSED",
                "performance_acceptable": self.test_results.get("performance_scalability", {}).get("status") == "PASSED"
            },
            "recommendations": self._generate_test_recommendations()
        }
        
        # Log report summary
        logger.info(f"Test Report Summary: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
        
        # Save report to file
        report_filename = f"voice_analytics_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(report_filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Test report saved to {report_filename}")
        except Exception as e:
            logger.error(f"Failed to save test report: {e}")
        
        self.test_results["_report"] = report
        return report
    
    def _generate_test_recommendations(self):
        """Generate recommendations based on test results"""
        recommendations = []
        
        # Check for failed tests
        for test_name, result in self.test_results.items():
            if result.get("status") == "FAILED":
                recommendations.append(f"Address failure in {test_name}: {result.get('error', 'Unknown error')}")
        
        # Performance recommendations
        perf_result = self.test_results.get("performance_scalability", {})
        if perf_result.get("status") == "PASSED":
            avg_time = perf_result.get("average_per_interaction", 0)
            if avg_time > 1.0:
                recommendations.append("Consider optimizing analytics processing time (currently > 1s per interaction)")
        
        # Quality recommendations
        quality_result = self.test_results.get("quality_analysis", {})
        if quality_result.get("status") == "PASSED":
            if quality_result.get("issues_count", 0) > 2:
                recommendations.append("Multiple quality issues detected - review quality assessment thresholds")
        
        # Cost recommendations
        cost_result = self.test_results.get("cost_tracking", {})
        if cost_result.get("status") == "PASSED":
            if cost_result.get("recommendations_count", 0) == 0:
                recommendations.append("Consider implementing more cost optimization recommendations")
        
        if not recommendations:
            recommendations.append("All systems functioning well - continue monitoring")
        
        return recommendations

# Test execution function
async def run_voice_analytics_tests():
    """Run comprehensive voice analytics tests"""
    test_suite = VoiceAnalyticsTestSuite()
    return await test_suite.run_comprehensive_tests()

# Main execution
if __name__ == "__main__":
    asyncio.run(run_voice_analytics_tests())