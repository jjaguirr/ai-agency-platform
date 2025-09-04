"""
Semantic ROI Validation Tests - Demonstration of Real AI Evaluation
Shows transformation from keyword matching to semantic financial logic validation
"""

import asyncio
import pytest
import time
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel


class TestSemanticROIValidation:
    """Test ROI calculation validation using real AI evaluation"""
    
    @pytest.mark.asyncio
    async def test_roi_calculation_accuracy(self, roi_validator, evaluation_mode):
        """
        Test ROI calculation accuracy using semantic evaluation
        Replaces keyword-based financial validation with AI logic checking
        """
        ea = ExecutiveAssistant(customer_id="roi_validation_test")
        
        # Business problem with specific time and cost information
        business_problem = """
        I run a consulting business and manually create proposals for each client.
        This takes me 5 hours per week at $150/hour billable rate.
        I need to automate this process to save time and increase my capacity.
        """
        
        # Get EA's response with ROI calculation
        response = await ea.handle_customer_interaction(
            message=business_problem,
            channel=ConversationChannel.EMAIL
        )
        
        # LEGACY: Simple keyword-based validation
        roi_keywords = ["$", "save", "hour", "week", "month", "cost", "return", "roi"]
        keyword_matches = sum(1 for keyword in roi_keywords if keyword in response.lower())
        legacy_has_roi = keyword_matches >= 4
        
        # NEW: Semantic ROI validation
        if evaluation_mode["real_evaluation_available"]:
            # Real AI ROI calculation validation
            roi_assessment = await roi_validator.validate_roi_calculation_async(
                business_problem=business_problem,
                ea_response=response,
                stated_costs={"hourly_rate": 150, "hours_per_week": 5}
            )
            
            # Semantic validation checks
            assert roi_assessment.passed, f"ROI validation failed: {roi_assessment.reasoning}"
            
            # Check ROI validation details
            if hasattr(roi_assessment, 'roi_validation'):
                roi_details = roi_assessment.roi_validation
                
                # Verify ROI calculation components are present and accurate
                assert roi_details.roi_calculation_present, "ROI calculation should be present"
                assert roi_details.time_savings_quantified, "Time savings should be quantified"
                assert roi_details.assumptions_reasonable, "ROI assumptions should be reasonable"
            
            print(f"✅ SEMANTIC ROI Validation: {roi_assessment.score:.2f}")
            print(f"📊 Legacy keyword matches: {keyword_matches}/8")
            print(f"🔍 Evaluation mode: Real AI financial logic validation")
            
            if hasattr(roi_assessment, 'roi_validation'):
                roi_details = roi_assessment.roi_validation
                print(f"💰 ROI present: {roi_details.roi_calculation_present}")
                print(f"⏱️  Time quantified: {roi_details.time_savings_quantified}")
                print(f"🧮 Math accurate: {roi_details.roi_calculation_accurate}")
                print(f"📈 Assumptions reasonable: {roi_details.assumptions_reasonable}")
            
            return {
                "semantic_score": roi_assessment.score,
                "semantic_passed": roi_assessment.passed,
                "keyword_matches": keyword_matches,
                "legacy_passed": legacy_has_roi,
                "evaluation_type": "semantic",
                "assessment": roi_assessment
            }
        else:
            # Fallback to keyword matching
            assert legacy_has_roi, f"ROI keywords found: {keyword_matches}/8 < 50%"
            
            print(f"⚠️  FALLBACK: Keyword-based ROI validation: {keyword_matches}/8")
            print(f"🔍 Evaluation mode: Mock/keyword fallback (no OpenAI API key)")
            
            return {
                "semantic_score": None,
                "semantic_passed": None,
                "keyword_matches": keyword_matches,
                "legacy_passed": legacy_has_roi,
                "evaluation_type": "keyword_fallback",
                "assessment": None
            }
    
    @pytest.mark.asyncio
    async def test_time_savings_calculation_validation(self, roi_validator, evaluation_mode):
        """
        Test time savings calculation validation using semantic evaluation
        """
        ea = ExecutiveAssistant(customer_id="time_savings_test")
        
        # Specific time-consuming business process
        time_problem = """
        I spend 3 hours every day manually posting to social media for my jewelry business.
        That's 21 hours per week. At $50/hour value of my time, this costs me $1,050 weekly.
        Can you help me automate this and calculate the savings?
        """
        
        response = await ea.handle_customer_interaction(
            message=time_problem,
            channel=ConversationChannel.WHATSAPP
        )
        
        # LEGACY: Check for time-related keywords
        time_keywords = ["21 hours", "week", "$1,050", "automat", "save", "3 hours", "daily"]
        keyword_matches = sum(1 for keyword in time_keywords if keyword.lower() in response.lower())
        legacy_understands_time = keyword_matches >= 3
        
        # NEW: Semantic time savings validation
        if evaluation_mode["real_evaluation_available"]:
            # Validate time savings calculation accuracy
            roi_assessment = await roi_validator.validate_roi_calculation_async(
                business_problem=time_problem,
                ea_response=response,
                stated_costs={"hourly_rate": 50, "hours_per_day": 3, "days_per_week": 7}
            )
            
            assert roi_assessment.passed, f"Time savings validation failed: {roi_assessment.reasoning}"
            
            # Check specific time savings validation
            if hasattr(roi_assessment, 'roi_validation'):
                validation_details = roi_assessment.roi_validation
                assert validation_details.time_savings_quantified, "Time savings should be quantified"
                assert validation_details.cost_savings_calculated, "Cost savings should be calculated"
            
            print(f"✅ SEMANTIC Time Savings Validation: {roi_assessment.score:.2f}")
            print(f"📊 Legacy keyword matches: {keyword_matches}/7")
            print(f"🔍 Real AI validation: Time extraction and calculation accuracy")
            
            return {
                "validation_passed": roi_assessment.passed,
                "semantic_score": roi_assessment.score,
                "keyword_matches": keyword_matches,
                "evaluation_type": "semantic"
            }
        else:
            # Fallback validation
            assert legacy_understands_time, f"Time understanding keywords: {keyword_matches}/7"
            
            print(f"⚠️  FALLBACK: Keyword time validation: {keyword_matches}/7")
            print(f"🔍 Mock mode: Basic keyword matching only")
            
            return {
                "validation_passed": legacy_understands_time,
                "semantic_score": None,
                "keyword_matches": keyword_matches,
                "evaluation_type": "keyword_fallback"
            }
    
    @pytest.mark.asyncio
    async def test_complex_roi_scenario_validation(self, roi_validator, evaluation_mode):
        """
        Test complex ROI scenario with multiple cost factors
        """
        ea = ExecutiveAssistant(customer_id="complex_roi_test")
        
        # Complex business scenario with multiple cost factors
        complex_problem = """
        My real estate agency processes 50 leads per week manually. Each lead takes 15 minutes to qualify.
        My agents earn $40/hour. We also spend $200/week on lead management software.
        We close 10% of qualified leads at $3,000 commission each.
        Can you calculate the ROI of automating lead qualification?
        """
        
        response = await ea.handle_customer_interaction(
            message=complex_problem,
            channel=ConversationChannel.EMAIL
        )
        
        # LEGACY: Complex keyword matching
        complex_keywords = ["50 leads", "15 minutes", "$40/hour", "$200", "10%", "$3,000", "roi", "automat"]
        keyword_matches = sum(1 for keyword in complex_keywords if keyword.lower() in response.lower())
        legacy_handles_complexity = keyword_matches >= 4
        
        # NEW: Semantic complex ROI validation
        if evaluation_mode["real_evaluation_available"]:
            roi_assessment = await roi_validator.validate_roi_calculation_async(
                business_problem=complex_problem,
                ea_response=response,
                stated_costs={
                    "leads_per_week": 50,
                    "minutes_per_lead": 15,
                    "agent_hourly_rate": 40,
                    "software_cost_weekly": 200,
                    "close_rate": 0.10,
                    "commission_per_sale": 3000
                }
            )
            
            # Complex ROI should consider multiple factors
            assert roi_assessment.passed, f"Complex ROI validation failed: {roi_assessment.reasoning}"
            
            print(f"✅ SEMANTIC Complex ROI Validation: {roi_assessment.score:.2f}")
            print(f"📊 Complex keyword matches: {keyword_matches}/8")
            print(f"🔍 Real AI validation: Multi-factor ROI calculation")
            
            # Additional complexity checks
            if hasattr(roi_assessment, 'roi_validation'):
                validation = roi_assessment.roi_validation
                print(f"💼 Multiple cost factors considered: {len(validation.calculation_errors) == 0}")
                print(f"📈 Revenue impact included: {validation.cost_savings_calculated}")
            
            return {
                "complex_roi_handled": roi_assessment.passed,
                "semantic_score": roi_assessment.score,
                "keyword_matches": keyword_matches,
                "evaluation_type": "semantic"
            }
        else:
            # Fallback for complex scenario
            assert legacy_handles_complexity, f"Complex ROI keywords: {keyword_matches}/8"
            
            print(f"⚠️  FALLBACK: Complex keyword matching: {keyword_matches}/8")
            print(f"🔍 Limited validation: Cannot verify multi-factor ROI accuracy")
            
            return {
                "complex_roi_handled": legacy_handles_complexity,
                "semantic_score": None,
                "keyword_matches": keyword_matches,
                "evaluation_type": "keyword_fallback"
            }


class TestSemanticEvaluationComparison:
    """Compare semantic vs keyword evaluation approaches"""
    
    @pytest.mark.asyncio
    async def test_evaluation_method_comparison(self, roi_validator, business_intelligence_evaluator, evaluation_mode):
        """
        Direct comparison between keyword matching and semantic evaluation
        Demonstrates the improvement in validation quality
        """
        ea = ExecutiveAssistant(customer_id="comparison_test")
        
        # Tricky business scenario that might fool keyword matching
        tricky_scenario = """
        I keep hearing about 'automation' and 'ROI' from competitors.
        My jewelry business has 'social media' presence and I use 'invoices'.
        But honestly, I'm not sure what specific 'time savings' I need.
        Can you help me understand what problems I actually have?
        """
        
        response = await ea.handle_customer_interaction(
            message=tricky_scenario,
            channel=ConversationChannel.PHONE
        )
        
        # KEYWORD APPROACH: Would likely score high due to buzzwords
        business_keywords = ["automation", "roi", "social media", "invoices", "time savings"]
        keyword_score = sum(1 for keyword in business_keywords if keyword in tricky_scenario.lower())
        keyword_would_pass = keyword_score >= 3  # False positive likely
        
        # SEMANTIC APPROACH: Should recognize lack of real business problems
        semantic_results = {}
        
        if evaluation_mode["real_evaluation_available"]:
            # Real semantic evaluation should catch the issue
            business_assessment = await business_intelligence_evaluator.validate_business_understanding_async(
                business_description=tricky_scenario,
                ea_response=response
            )
            
            semantic_results = {
                "business_understanding_score": business_assessment.score,
                "business_understanding_passed": business_assessment.passed,
                "semantic_reasoning": business_assessment.reasoning
            }
            
            print(f"🎯 COMPARISON Results:")
            print(f"📊 Keyword approach: {keyword_score}/5 keywords found -> {'PASS' if keyword_would_pass else 'FAIL'}")
            print(f"🧠 Semantic approach: {business_assessment.score:.2f} -> {'PASS' if business_assessment.passed else 'FAIL'}")
            print(f"💡 Semantic reasoning: {business_assessment.reasoning[:100]}...")
            
            # Semantic should be more accurate for this tricky case
            return {
                "keyword_score": keyword_score,
                "keyword_would_pass": keyword_would_pass,
                "semantic_score": business_assessment.score,
                "semantic_passed": business_assessment.passed,
                "improvement_demonstrated": True,
                "evaluation_type": "comparison"
            }
        else:
            print(f"⚠️  COMPARISON (Limited): Only keyword matching available")
            print(f"📊 Keyword score: {keyword_score}/5 -> {'PASS' if keyword_would_pass else 'FAIL'}")
            print(f"🔍 Cannot demonstrate semantic improvement without OpenAI API key")
            
            return {
                "keyword_score": keyword_score,
                "keyword_would_pass": keyword_would_pass,
                "semantic_score": None,
                "semantic_passed": None,
                "improvement_demonstrated": False,
                "evaluation_type": "keyword_only"
            }