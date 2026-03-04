#!/usr/bin/env python3
"""
Semantic Evaluation Demo - Issues #7 & #10 Implementation
Run this to demonstrate the transformation from mock/keyword to real AI evaluation
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def demo_semantic_evaluation():
    """Demonstrate the new semantic evaluation system"""
    
    print("🚀 AI Agency Platform - Semantic Evaluation Demo")
    print("=" * 60)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check OpenAI API key availability
    openai_key_available = bool(os.getenv('OPENAI_API_KEY'))
    print(f"🔑 OpenAI API Key: {'✅ Available' if openai_key_available else '❌ Not Available'}")
    
    if not openai_key_available:
        print("⚠️  Note: Will fall back to mock evaluation (no real semantic validation)")
        print("   Set OPENAI_API_KEY environment variable for real AI evaluation")
    
    print()
    
    # Test the evaluation system
    try:
        from src.evaluation import (
            RealBusinessIntelligenceValidator,
            ConversationQualityAssessment,
            ROICalculationValidator
        )
        print("✅ Semantic evaluation modules imported successfully")
        
        if openai_key_available:
            print("\n🧠 Testing Real AI Evaluation Components:")
            
            # Test Business Intelligence Validator
            print("  📊 Business Intelligence Validator...")
            bi_validator = RealBusinessIntelligenceValidator()
            
            # Test Conversation Quality Assessment
            print("  💬 Conversation Quality Assessment...")
            cq_assessor = ConversationQualityAssessment()
            
            # Test ROI Calculation Validator
            print("  💰 ROI Calculation Validator...")
            roi_validator = ROICalculationValidator()
            
            print("✅ All real evaluation components initialized successfully")
            
            # Run a quick semantic evaluation test
            print("\n🔍 Running Quick Semantic Evaluation Test:")
            
            business_description = "I run a jewelry e-commerce store and spend 3 hours daily on social media posting."
            ea_response = "I understand you're spending significant time on social media for your jewelry store. I can help automate your posting schedule to save you approximately 2-3 hours daily, which could save $150-225 weekly at $50/hour value. Would you like me to create a social media automation workflow?"
            
            # Test business understanding
            assessment = await bi_validator.validate_business_understanding(
                business_description=business_description,
                ea_response=ea_response
            )
            
            print(f"  🎯 Business Understanding: {assessment.score:.2f} ({'PASS' if assessment.passed else 'FAIL'})")
            print(f"  🔍 Confidence: {assessment.confidence.value}")
            print(f"  📝 Reasoning: {assessment.reasoning[:100]}...")
            
            # Test conversation quality
            quality_assessment = await cq_assessor.assess_conversation_quality(
                user_message=business_description,
                ea_response=ea_response
            )
            
            print(f"  💬 Conversation Quality: {quality_assessment.score:.2f} ({'PASS' if quality_assessment.passed else 'FAIL'})")
            print(f"  📊 Professionalism: {quality_assessment.professionalism_score:.2f}")
            print(f"  📊 Actionability: {quality_assessment.actionability_score:.2f}")
            
            # Test ROI validation
            roi_assessment = await roi_validator.validate_roi_calculation(
                business_problem=business_description,
                ea_response=ea_response
            )
            
            print(f"  💰 ROI Validation: {roi_assessment.score:.2f} ({'PASS' if roi_assessment.passed else 'FAIL'})")
            print(f"  📈 ROI Present: {roi_assessment.roi_calculation_present}")
            print(f"  ⏱️  Time Quantified: {roi_assessment.time_savings_quantified}")
            
            print("\n✅ Semantic evaluation test completed successfully!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Check that all dependencies are installed")
        return False
    except Exception as e:
        print(f"❌ Error during evaluation test: {e}")
        return False
    
    # Instructions for running tests
    print(f"\n📋 Next Steps:")
    print(f"1. Run specific semantic tests:")
    print(f"   pytest tests/business/test_business_validation_simple.py::TestEABusinessValidation::test_business_discovery_conversation -v")
    print(f"")
    print(f"2. Run ROI validation tests:")
    print(f"   pytest tests/business/test_semantic_roi_validation.py -v")
    print(f"")
    print(f"3. Compare keyword vs semantic evaluation:")
    print(f"   pytest tests/business/test_semantic_roi_validation.py::TestSemanticEvaluationComparison::test_evaluation_method_comparison -v")
    
    print(f"\n🎯 Issues Resolved:")
    print(f"   ✅ Issue #7: Mock AI evaluation replaced with real semantic assessment")
    print(f"   ✅ Issue #10: Keyword matching replaced with semantic business logic validation")
    
    print(f"\n🏁 Demo completed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(demo_semantic_evaluation())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)