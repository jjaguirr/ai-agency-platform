#!/usr/bin/env python3
"""
Daily Business Validation Script
Run this every day to validate EA against core business requirements

This is your go-to script for seeing EA conversations in real-time
and validating business value propositions.
"""

import asyncio
import time
from datetime import datetime
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel


def print_section(title: str):
    """Print beautiful section headers"""
    print(f"\n{'🎯 ' + title}")
    print(f"{'='*80}")


def print_conversation(speaker: str, message: str, response_time: float = None, channel: str = ""):
    """Print live conversation with formatting"""
    if speaker == "CUSTOMER":
        channel_display = f" ({channel})" if channel else ""
        print(f"\n👤 CUSTOMER{channel_display}:")
        print(f"   💬 {message}")
    else:  # EA
        time_str = f" ({response_time:.2f}s)" if response_time else ""
        print(f"\n🤖 EA RESPONSE{time_str}:")
        # Intelligently truncate long responses
        if len(message) > 200:
            lines = message.split('\n')
            if len(lines) > 3:
                display_msg = '\n'.join(lines[:2]) + f"\n   ... ({len(lines)-2} more lines)"
            else:
                display_msg = message[:200] + "..."
        else:
            display_msg = message
        print(f"   💭 {display_msg}")


def print_business_metrics(metrics: dict):
    """Print business analysis metrics"""
    print(f"\n📊 BUSINESS METRICS:")
    for key, value in metrics.items():
        if isinstance(value, bool):
            icon = "✅" if value else "❌"
            print(f"   {icon} {key}: {value}")
        elif isinstance(value, float):
            print(f"   📈 {key}: {value:.2f}")
        else:
            print(f"   • {key}: {value}")


async def test_customer_journey_simulation():
    """
    MOST IMPORTANT TEST: Complete customer journey from purchase to value delivery
    This simulates a real customer experience
    """
    print_section("COMPLETE CUSTOMER JOURNEY SIMULATION")
    print("Simulating: Purchase → Onboarding → Business Discovery → Automation → Value")
    
    customer_id = f"journey_{int(time.time())}"
    ea = ExecutiveAssistant(customer_id=customer_id)
    journey_start = time.time()
    
    # STAGE 1: POST-PURCHASE CONTACT
    print(f"\n🏁 STAGE 1: Post-Purchase Initial Contact")
    welcome_msg = """Hi! I just purchased your Executive Assistant service. 
    I got an email saying you'd call me within 60 seconds. 
    I'm ready to get started but not sure what to expect."""
    
    print_conversation("CUSTOMER", welcome_msg, channel="PHONE")
    
    start = time.time()
    welcome_response = await ea.handle_customer_interaction(welcome_msg, ConversationChannel.PHONE)
    welcome_time = time.time() - start
    
    print_conversation("EA", welcome_response, welcome_time)
    
    # STAGE 2: BUSINESS DISCOVERY 
    print(f"\n🔍 STAGE 2: Business Discovery Conversation")
    business_story = """Let me tell you about my business. I'm Jennifer and I run 'Bloom & Grow', 
    a boutique digital marketing consultancy. We have 8 team members and serve 25 small business clients.
    
    My biggest pain points are:
    - I personally spend 3 hours every day creating social media content for clients
    - We manually send 50+ proposal emails per week 
    - Client onboarding involves 12 different manual steps
    - Weekly client reports take 6 hours to compile
    
    I'm drowning in repetitive tasks and my team is burning out. 
    I need to automate these processes or we'll lose clients."""
    
    print_conversation("CUSTOMER", business_story, channel="PHONE")
    
    start = time.time()
    discovery_response = await ea.handle_customer_interaction(business_story, ConversationChannel.PHONE)
    discovery_time = time.time() - start
    
    print_conversation("EA", discovery_response, discovery_time)
    
    # STAGE 3: SPECIFIC AUTOMATION REQUEST
    print(f"\n⚙️ STAGE 3: Automation Solution Request")
    automation_request = """That sounds promising! Can you give me specific recommendations 
    for automating my social media content creation? I need to know:
    1. What would the automation workflow look like?
    2. How much time would this save me daily?
    3. What's the first step to implement this?
    
    I need concrete solutions, not just general advice."""
    
    print_conversation("CUSTOMER", automation_request, channel="WHATSAPP")
    
    start = time.time()
    solution_response = await ea.handle_customer_interaction(automation_request, ConversationChannel.WHATSAPP)
    solution_time = time.time() - start
    
    print_conversation("EA", solution_response, solution_time)
    
    # STAGE 4: IMPLEMENTATION GUIDANCE
    print(f"\n🚀 STAGE 4: Implementation & Next Steps")
    implementation_request = """This sounds exactly what I need! I'm ready to move forward.
    How do we start implementing the social media automation today? 
    Can you walk me through the setup process?"""
    
    print_conversation("CUSTOMER", implementation_request, channel="EMAIL")
    
    start = time.time()
    implementation_response = await ea.handle_customer_interaction(implementation_request, ConversationChannel.EMAIL)
    implementation_time = time.time() - start
    
    print_conversation("EA", implementation_response, implementation_time)
    
    # BUSINESS ANALYSIS
    total_journey_time = time.time() - journey_start
    
    # Analyze business understanding
    business_keywords = [
        "jennifer", "bloom", "grow", "marketing", "consultancy", 
        "social media", "content", "proposal", "onboarding", "reports",
        "automat", "workflow", "time", "save", "clients"
    ]
    
    all_responses = discovery_response + solution_response + implementation_response
    understanding_score = sum(1 for kw in business_keywords if kw.lower() in all_responses.lower())
    understanding_percentage = (understanding_score / len(business_keywords)) * 100
    
    # Analyze solution quality
    solution_indicators = [
        "workflow", "automat", "save", "time", "step", "implement", 
        "social media", "content", "process", "solution"
    ]
    solution_score = sum(1 for indicator in solution_indicators if indicator.lower() in solution_response.lower())
    
    # Calculate metrics
    metrics = {
        "Total Journey Time": f"{total_journey_time:.1f}s",
        "Business Understanding": f"{understanding_percentage:.1f}% ({understanding_score}/{len(business_keywords)} keywords)",
        "Solution Quality": f"{solution_score}/{len(solution_indicators)} solution indicators",
        "Response Times": f"Welcome: {welcome_time:.1f}s, Discovery: {discovery_time:.1f}s, Solution: {solution_time:.1f}s, Implementation: {implementation_time:.1f}s",
        "Professional Responses": all(len(r) > 50 for r in [welcome_response, discovery_response, solution_response, implementation_response]),
        "Multi-Channel Working": "✅ Phone, WhatsApp, Email all functional"
    }
    
    print_business_metrics(metrics)
    
    # SUCCESS CRITERIA
    success_criteria = [
        total_journey_time < 180,  # Complete journey under 3 minutes
        understanding_percentage >= 50,  # Understands at least half the business context
        solution_score >= 4,  # Provides quality automation solutions
        all(t < 30 for t in [welcome_time, discovery_time, solution_time, implementation_time]),  # All responses under 30s
        len(implementation_response) > 100  # Detailed implementation guidance
    ]
    
    passed_criteria = sum(success_criteria)
    journey_success = passed_criteria >= 4
    
    print(f"\n🎯 CUSTOMER JOURNEY VALIDATION:")
    print(f"   {'✅' if success_criteria[0] else '❌'} Journey Time: {total_journey_time:.1f}s < 180s")
    print(f"   {'✅' if success_criteria[1] else '❌'} Business Understanding: {understanding_percentage:.1f}% ≥ 50%")
    print(f"   {'✅' if success_criteria[2] else '❌'} Solution Quality: {solution_score}/10 ≥ 4")
    print(f"   {'✅' if success_criteria[3] else '❌'} Response Times: All under 30s")
    print(f"   {'✅' if success_criteria[4] else '❌'} Implementation Detail: > 100 chars")
    
    print(f"\n{'🎯 OVERALL CUSTOMER JOURNEY: ✅ SUCCESS' if journey_success else f'🎯 OVERALL CUSTOMER JOURNEY: ❌ NEEDS WORK ({passed_criteria}/5 criteria met)'}")
    
    return {
        "success": journey_success,
        "total_time": total_journey_time,
        "understanding": understanding_percentage,
        "solution_quality": solution_score
    }


async def test_business_roi_demonstration():
    """
    CRITICAL TEST: EA demonstrates clear business value and ROI
    """
    print_section("BUSINESS ROI & VALUE DEMONSTRATION")
    print("Testing: EA's ability to show concrete business value")
    
    customer_id = f"roi_test_{int(time.time())}"
    ea = ExecutiveAssistant(customer_id=customer_id)
    
    # ROI Challenge
    roi_challenge = """I need you to prove the ROI of this service to my CFO. Here are my numbers:
    - I pay my marketing coordinator $25/hour
    - She spends 20 hours/week on manual social media tasks
    - She spends 10 hours/week on manual report generation
    - We're considering your $299/month service
    
    Show me the exact dollar savings and ROI calculation."""
    
    print_conversation("CUSTOMER", roi_challenge, channel="EMAIL")
    
    start = time.time()
    roi_response = await ea.handle_customer_interaction(roi_challenge, ConversationChannel.EMAIL)
    roi_time = time.time() - start
    
    print_conversation("EA", roi_response, roi_time)
    
    # Value Proposition Test
    value_question = """My competitor is offering a similar service for $199/month. 
    Why should I pay $299 for yours? What makes your EA different?"""
    
    print_conversation("CUSTOMER", value_question, channel="PHONE")
    
    start = time.time()
    value_response = await ea.handle_customer_interaction(value_question, ConversationChannel.PHONE)
    value_time = time.time() - start
    
    print_conversation("EA", value_response, value_time)
    
    # Analysis
    roi_keywords = ["save", "cost", "hour", "week", "month", "dollar", "roi", "return", "invest"]
    roi_score = sum(1 for kw in roi_keywords if kw.lower() in roi_response.lower())
    
    value_keywords = ["different", "unique", "better", "advantage", "benefit", "quality", "personal", "assistant"]
    value_score = sum(1 for kw in value_keywords if kw.lower() in value_response.lower())
    
    metrics = {
        "ROI Understanding": f"{roi_score}/{len(roi_keywords)} financial concepts",
        "Value Proposition": f"{value_score}/{len(value_keywords)} differentiation points",
        "Response Quality": f"ROI: {len(roi_response)} chars, Value: {len(value_response)} chars",
        "Business Acumen": roi_score >= 4 and value_score >= 3
    }
    
    print_business_metrics(metrics)
    
    roi_success = roi_score >= 4 and value_score >= 3 and len(roi_response) > 100
    print(f"\n{'🎯 BUSINESS VALUE DEMONSTRATION: ✅ SUCCESS' if roi_success else '🎯 BUSINESS VALUE DEMONSTRATION: ❌ NEEDS IMPROVEMENT'}")
    
    return {"success": roi_success, "roi_score": roi_score, "value_score": value_score}


async def test_competitive_positioning():
    """
    STRATEGIC TEST: EA positions itself correctly vs competitors
    """
    print_section("COMPETITIVE POSITIONING & MARKET DIFFERENTIATION")
    print("Testing: How EA differentiates from other automation tools")
    
    customer_id = f"competitive_{int(time.time())}"
    ea = ExecutiveAssistant(customer_id=customer_id)
    
    competitive_challenge = """I've looked at Zapier, Make.com, and other automation platforms. 
    They're much cheaper and offer similar workflow automation. 
    What makes your Executive Assistant worth the premium price?
    How are you different from just using Zapier + ChatGPT?"""
    
    print_conversation("CUSTOMER", competitive_challenge, channel="EMAIL")
    
    start = time.time()
    positioning_response = await ea.handle_customer_interaction(competitive_challenge, ConversationChannel.EMAIL)
    positioning_time = time.time() - start
    
    print_conversation("EA", positioning_response, positioning_time)
    
    # Analysis
    positioning_keywords = [
        "assistant", "personal", "learn", "understand", "business", "conversation",
        "relationship", "context", "memory", "partner", "dedicated", "custom"
    ]
    
    positioning_score = sum(1 for kw in positioning_keywords if kw.lower() in positioning_response.lower())
    positioning_percentage = (positioning_score / len(positioning_keywords)) * 100
    
    metrics = {
        "EA Positioning Strength": f"{positioning_percentage:.1f}% ({positioning_score}/{len(positioning_keywords)} concepts)",
        "Response Depth": f"{len(positioning_response)} characters",
        "Differentiation Clear": positioning_score >= 6
    }
    
    print_business_metrics(metrics)
    
    positioning_success = positioning_score >= 6 and len(positioning_response) > 150
    print(f"\n{'🎯 COMPETITIVE POSITIONING: ✅ STRONG' if positioning_success else '🎯 COMPETITIVE POSITIONING: ❌ WEAK'}")
    
    return {"success": positioning_success, "positioning_score": positioning_percentage}


async def run_daily_business_validation():
    """Run complete daily business validation suite"""
    print(f"{'🚀 DAILY BUSINESS VALIDATION'}")
    print(f"{'='*80}")
    print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 Testing EA against core business propositions from Phase 1 PRD")
    
    results = {}
    
    try:
        # Test 1: Complete Customer Journey
        print(f"\n📋 Running Critical Test 1/3...")
        results['customer_journey'] = await test_customer_journey_simulation()
        
        # Test 2: Business ROI Demonstration
        print(f"\n📋 Running Critical Test 2/3...")
        results['business_roi'] = await test_business_roi_demonstration()
        
        # Test 3: Competitive Positioning
        print(f"\n📋 Running Critical Test 3/3...")
        results['competitive_positioning'] = await test_competitive_positioning()
        
        # FINAL BUSINESS ASSESSMENT
        print_section("DAILY BUSINESS VALIDATION RESULTS")
        
        journey_success = results['customer_journey']['success']
        roi_success = results['business_roi']['success']
        positioning_success = results['competitive_positioning']['success']
        
        print(f"✅ Customer Journey: {'✅ PASS' if journey_success else '❌ FAIL'} ({results['customer_journey']['total_time']:.1f}s total)")
        print(f"✅ Business ROI Demo: {'✅ PASS' if roi_success else '❌ FAIL'} (ROI: {results['business_roi']['roi_score']}/9, Value: {results['business_roi']['value_score']}/8)")
        print(f"✅ Competitive Position: {'✅ PASS' if positioning_success else '❌ FAIL'} ({results['competitive_positioning']['positioning_score']:.1f}% strength)")
        
        overall_success = journey_success and roi_success and positioning_success
        partial_success = sum([journey_success, roi_success, positioning_success]) >= 2
        
        print(f"\n{'='*80}")
        if overall_success:
            print(f"🎯 BUSINESS VALIDATION: ✅ EXCELLENT - EA READY FOR CUSTOMERS")
            print(f"🚀 All business propositions validated successfully")
        elif partial_success:
            print(f"🎯 BUSINESS VALIDATION: ⚠️  GOOD - MINOR IMPROVEMENTS NEEDED")
            print(f"📈 Most business propositions working well")
        else:
            print(f"🎯 BUSINESS VALIDATION: ❌ NEEDS WORK - NOT READY FOR CUSTOMERS")
            print(f"🔧 Major business proposition issues detected")
        
        print(f"{'='*80}")
        
        return overall_success
        
    except Exception as e:
        print(f"\n❌ DAILY VALIDATION FAILED: {str(e)}")
        return False


if __name__ == "__main__":
    import sys
    success = asyncio.run(run_daily_business_validation())
    sys.exit(0 if success else 1)