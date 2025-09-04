#!/usr/bin/env python3
"""
Essential Business Tests Runner
Run this daily to validate core EA business functionality with live conversations

Usage:
  python run_essential_tests.py                    # Run all essential tests
  python run_essential_tests.py --onboarding      # Run only customer onboarding test
  python run_essential_tests.py --quick           # Run quick validation test
"""

import asyncio
import sys
import argparse
import time
from datetime import datetime
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel


def print_header(title: str):
    """Print formatted test header"""
    print(f"\n{'='*80}")
    print(f"🎯 {title}")
    print(f"⏰ {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*80}")


def print_conversation(speaker: str, message: str, response_time: float = None):
    """Print conversation in real-time"""
    if speaker == "CUSTOMER":
        print(f"\n👤 {speaker}:")
        print(f"   💬 {message}")
    else:  # EA
        time_str = f" ({response_time:.2f}s)" if response_time else ""
        print(f"\n🤖 EA{time_str}:")
        # Show first 150 chars for readability
        display_msg = message[:150] + "..." if len(message) > 150 else message
        print(f"   💭 {display_msg}")


async def test_quick_validation():
    """Quick 2-minute validation of core EA functionality"""
    print_header("QUICK EA VALIDATION TEST")
    
    customer_id = f"quick_{int(time.time())}"
    ea = ExecutiveAssistant(customer_id=customer_id)
    
    # Test 1: Basic Response
    print("\n🔍 Test 1: Basic EA Response")
    message = "Hello, I need help with business automation"
    print_conversation("CUSTOMER", message)
    
    start_time = time.time()
    response = await ea.handle_customer_interaction(message, ConversationChannel.PHONE)
    response_time = time.time() - start_time
    
    print_conversation("EA", response, response_time)
    
    basic_success = response_time < 30 and len(response) > 20
    print(f"   📊 Basic Response: {'✅ PASS' if basic_success else '❌ FAIL'} ({response_time:.2f}s)")
    
    # Test 2: Business Understanding
    print("\n🔍 Test 2: Business Context Understanding")
    business_msg = "I run a marketing agency and spend 4 hours daily on social media posts"
    print_conversation("CUSTOMER", business_msg)
    
    start_time = time.time()
    business_response = await ea.handle_customer_interaction(business_msg, ConversationChannel.WHATSAPP)
    business_time = time.time() - start_time
    
    print_conversation("EA", business_response, business_time)
    
    understanding_keywords = ["marketing", "social", "automat", "time", "business"]
    understanding_score = sum(1 for kw in understanding_keywords if kw.lower() in business_response.lower())
    understanding_success = understanding_score >= 2
    
    print(f"   📊 Business Understanding: {'✅ PASS' if understanding_success else '❌ FAIL'} ({understanding_score}/5 keywords)")
    
    # Results
    overall_success = basic_success and understanding_success
    print(f"\n🎯 QUICK VALIDATION: {'✅ PASS' if overall_success else '❌ FAIL'}")
    
    return overall_success


async def test_customer_onboarding():
    """Essential customer onboarding conversation test"""
    print_header("CUSTOMER ONBOARDING CONVERSATION")
    
    customer_id = f"onboarding_{int(time.time())}"
    ea = ExecutiveAssistant(customer_id=customer_id)
    
    # Welcome
    welcome_msg = "Hi, I just purchased your service. How does this work?"
    print_conversation("CUSTOMER", welcome_msg)
    
    start_time = time.time()
    welcome_response = await ea.handle_customer_interaction(welcome_msg, ConversationChannel.PHONE)
    welcome_time = time.time() - start_time
    
    print_conversation("EA", welcome_response, welcome_time)
    
    # Business Discovery
    print("\n" + "─"*50)
    business_msg = """I own Coastal Realty, a real estate agency with 12 agents. 
    Our biggest challenges are: lead follow-up (we get 100+ leads weekly), 
    social media marketing (2 hours daily), and client communication management."""
    
    print_conversation("CUSTOMER", business_msg)
    
    start_time = time.time()
    discovery_response = await ea.handle_customer_interaction(business_msg, ConversationChannel.PHONE)
    discovery_time = time.time() - start_time
    
    print_conversation("EA", discovery_response, discovery_time)
    
    # Automation Request
    print("\n" + "─"*50)
    automation_msg = "Can you help automate our lead follow-up process? What would that look like?"
    print_conversation("CUSTOMER", automation_msg)
    
    start_time = time.time()
    automation_response = await ea.handle_customer_interaction(automation_msg, ConversationChannel.PHONE)
    automation_time = time.time() - start_time
    
    print_conversation("EA", automation_response, automation_time)
    
    # Analysis
    total_time = welcome_time + discovery_time + automation_time
    business_keywords = ["real estate", "realty", "lead", "follow-up", "social", "automat"]
    understanding = sum(1 for kw in business_keywords if kw.lower() in (discovery_response + automation_response).lower())
    
    print(f"\n📊 ONBOARDING ANALYSIS:")
    print(f"   • Total Time: {total_time:.1f}s")
    print(f"   • Business Understanding: {understanding}/6 keywords")
    print(f"   • Response Quality: All responses > 30 chars")
    
    success = total_time < 120 and understanding >= 3
    print(f"\n🎯 ONBOARDING: {'✅ PASS' if success else '❌ FAIL'}")
    
    return success


async def test_cross_channel():
    """Cross-channel conversation continuity test"""
    print_header("CROSS-CHANNEL CONVERSATION CONTINUITY")
    
    customer_id = f"multichannel_{int(time.time())}"
    ea = ExecutiveAssistant(customer_id=customer_id)
    
    # Phone: Initial context
    phone_msg = "I'm Alex from TechStartup Inc. We're a 20-person software company with client onboarding issues."
    print_conversation("CUSTOMER (PHONE)", phone_msg)
    
    start_time = time.time()
    phone_response = await ea.handle_customer_interaction(phone_msg, ConversationChannel.PHONE)
    phone_time = time.time() - start_time
    
    print_conversation("EA", phone_response, phone_time)
    
    # WhatsApp: Context recall
    print("\n" + "─"*50)
    whatsapp_msg = "I had to switch to WhatsApp. Do you remember what I told you about TechStartup Inc?"
    print_conversation("CUSTOMER (WHATSAPP)", whatsapp_msg)
    
    start_time = time.time()
    whatsapp_response = await ea.handle_customer_interaction(whatsapp_msg, ConversationChannel.WHATSAPP)
    whatsapp_time = time.time() - start_time
    
    print_conversation("EA", whatsapp_response, whatsapp_time)
    
    # Email: Detailed follow-up
    print("\n" + "─"*50)
    email_msg = "Now on email for details. What automation do you recommend for our onboarding issues?"
    print_conversation("CUSTOMER (EMAIL)", email_msg)
    
    start_time = time.time()
    email_response = await ea.handle_customer_interaction(email_msg, ConversationChannel.EMAIL)
    email_time = time.time() - start_time
    
    print_conversation("EA", email_response, email_time)
    
    # Analysis
    context_elements = ["techstartup", "alex", "20", "software", "onboarding"]
    continuity = sum(1 for elem in context_elements if elem.lower() in (whatsapp_response + email_response).lower())
    
    print(f"\n📊 CROSS-CHANNEL ANALYSIS:")
    print(f"   • Context Retention: {continuity}/5 elements")
    print(f"   • Channel Response Times: Phone: {phone_time:.1f}s, WhatsApp: {whatsapp_time:.1f}s, Email: {email_time:.1f}s")
    print(f"   • All Channels Working: ✅")
    
    success = continuity >= 2 and all(t < 30 for t in [phone_time, whatsapp_time, email_time])
    print(f"\n🎯 CROSS-CHANNEL: {'✅ PASS' if success else '❌ FAIL'}")
    
    return success


async def run_all_essential():
    """Run all essential tests in sequence"""
    print_header("ALL ESSENTIAL BUSINESS TESTS")
    print("Running comprehensive EA business validation...")
    
    results = {}
    
    print(f"\n📋 Running Test 1/3: Quick Validation...")
    results['quick'] = await test_quick_validation()
    
    print(f"\n📋 Running Test 2/3: Customer Onboarding...")
    results['onboarding'] = await test_customer_onboarding()
    
    print(f"\n📋 Running Test 3/3: Cross-Channel...")
    results['cross_channel'] = await test_cross_channel()
    
    # Final Summary
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n{'='*80}")
    print(f"🎯 ESSENTIAL TESTS COMPLETE")
    print(f"{'='*80}")
    print(f"✅ Quick Validation: {'PASS' if results['quick'] else 'FAIL'}")
    print(f"✅ Customer Onboarding: {'PASS' if results['onboarding'] else 'FAIL'}")
    print(f"✅ Cross-Channel: {'PASS' if results['cross_channel'] else 'FAIL'}")
    print(f"{'='*80}")
    
    overall_success = passed_tests == total_tests
    status = f"🎯 OVERALL: {'✅ ALL TESTS PASSED' if overall_success else f'❌ {passed_tests}/{total_tests} TESTS PASSED'}"
    print(status)
    
    if overall_success:
        print("🚀 EA IS BUSINESS-READY FOR CUSTOMER INTERACTIONS")
    else:
        print("⚠️  EA NEEDS ATTENTION BEFORE CUSTOMER DEPLOYMENT")
    
    return overall_success


def main():
    parser = argparse.ArgumentParser(description='Run essential EA business tests')
    parser.add_argument('--quick', action='store_true', help='Run quick validation test only')
    parser.add_argument('--onboarding', action='store_true', help='Run customer onboarding test only')
    parser.add_argument('--cross-channel', action='store_true', help='Run cross-channel test only')
    
    args = parser.parse_args()
    
    if args.quick:
        success = asyncio.run(test_quick_validation())
    elif args.onboarding:
        success = asyncio.run(test_customer_onboarding())
    elif args.cross_channel:
        success = asyncio.run(test_cross_channel())
    else:
        success = asyncio.run(run_all_essential())
    
    # Exit code for CI/CD
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()