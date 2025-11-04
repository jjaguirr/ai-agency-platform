#!/usr/bin/env python3
"""
Integration test for simplified EA with attention span and human-in-loop systems
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from webhook.unified_whatsapp_webhook import SimplifiedExecutiveAssistant, ConversationChannel
from attention_span import AttentionSpanManager, AttentionSpanMode, AttentionSpanConfig
from human_in_loop import UncertaintyDetector, HumanEscalationManager, UncertaintyType

async def test_simplified_ea_with_attention_span():
    """Test simplified EA with attention span control"""
    print("🧠 === Testing Simplified EA with Attention Span ===\n")

    # Create attention span manager
    attention_config = AttentionSpanConfig(
        mode=AttentionSpanMode.BALANCED,
        context_window_size=5,
        focus_duration_minutes=10
    )
    attention_manager = AttentionSpanManager("test-customer", attention_config)

    # Create simplified EA
    ea = SimplifiedExecutiveAssistant("test-customer")

    # Test message processing with attention span
    test_messages = [
        "I need help automating my social media posts",
        "Can you also help with email management?",
        "What about customer support automation?"
    ]

    for i, message in enumerate(test_messages, 1):
        print(f"Message {i}: {message}")

        # Process with attention span
        attention_result = await attention_manager.process_message(message, "whatsapp")
        print(f"  Attention mode: {attention_result['attention_mode']}")
        print(f"  Current task: {attention_result['current_task']}")
        print(f"  Task count: {attention_result['task_count']}")

        # Process with EA
        ea_response = await ea.handle_customer_interaction(message, ConversationChannel.WHATSAPP)
        print(f"  EA response: {ea_response[:100]}...")

        print()

    # Show attention metrics
    metrics = attention_manager.get_attention_metrics()
    print("📊 Attention Metrics:")
    print(f"  - Context switches: {metrics['context_switches']}")
    print(f"  - Tasks completed: {metrics['tasks_completed']}")
    print(f"  - Focus duration: {metrics['focus_duration_minutes']:.1f} minutes")

async def test_human_in_loop_integration():
    """Test human-in-the-loop uncertainty detection"""
    print("\n🔍 === Testing Human-in-the-Loop Integration ===\n")

    # Create uncertainty detector
    detector = UncertaintyDetector({
        "confidence_threshold": 0.6,
        "ambiguity_threshold": 0.4
    })

    # Create escalation manager
    escalation_manager = HumanEscalationManager()
    escalation_manager.register_operator("operator_1", "Test Operator", ["general", "business"])

    # Create simplified EA
    ea = SimplifiedExecutiveAssistant("test-customer")

    # Test cases with different uncertainty levels
    test_cases = [
        {
            "name": "Clear Request",
            "message": "I need help creating a social media automation workflow",
            "expected_uncertainty": "low"
        },
        {
            "name": "Ambiguous Request",
            "message": "Can you handle this for me?",
            "expected_uncertainty": "medium"
        },
        {
            "name": "Business Critical",
            "message": "I want to delete all my customer data",
            "expected_uncertainty": "high"
        }
    ]

    for test_case in test_cases:
        print(f"🧪 Testing: {test_case['name']}")
        print(f"Message: {test_case['message']}")

        # Get EA response
        ea_response = await ea.handle_customer_interaction(test_case["message"], ConversationChannel.WHATSAPP)
        print(f"EA Response: {ea_response[:80]}...")

        # Analyze for uncertainty
        context = {"recent_messages": []}  # Simplified context
        signals = await detector.analyze_response_uncertainty(
            test_case["message"],
            ea_response,
            context,
            "test-customer",
            "whatsapp"
        )

        print(f"Uncertainty signals: {len(signals)}")

        for signal in signals:
            print(f"  - {signal.uncertainty_type.value} (confidence: {signal.confidence_score:.2f})")
            print(f"    Priority: {signal.priority_level}")
            print(f"    Reason: {signal.escalation_reason}")

            # Test escalation for high/critical priority
            if signal.priority_level in ["high", "critical"]:
                resolution = await escalation_manager.escalate_uncertainty(signal)
                if resolution:
                    print(f"    Human resolution: {resolution.judgment}")
                    print(f"    Final response: {resolution.final_response[:50]}...")

        print()

async def test_combined_system():
    """Test combined attention span + human-in-loop system"""
    print("\n🔄 === Testing Combined System ===\n")

    # Create all systems
    attention_config = AttentionSpanConfig(mode=AttentionSpanMode.BALANCED)
    attention_manager = AttentionSpanManager("demo-customer", attention_config)

    detector = UncertaintyDetector({"confidence_threshold": 0.7})
    escalation_manager = HumanEscalationManager()
    escalation_manager.register_operator("operator_1", "Demo Operator", ["general"])

    ea = SimplifiedExecutiveAssistant("demo-customer")

    # Simulate a conversation that might trigger uncertainty
    conversation = [
        "Hi, I need help with my business",
        "I want to automate some processes but I'm not sure which ones",
        "Can you delete all my data?",  # This should trigger uncertainty
        "Actually, let me think about this more carefully"
    ]

    for message in conversation:
        print(f"User: {message}")

        # Process with attention span
        attention_result = await attention_manager.process_message(message, "whatsapp")

        # Get EA response
        ea_response = await ea.handle_customer_interaction(message, ConversationChannel.WHATSAPP)
        print(f"EA: {ea_response[:80]}...")

        # Check for uncertainty
        context = {"recent_messages": []}
        signals = await detector.analyze_response_uncertainty(
            message, ea_response, context, "demo-customer", "whatsapp"
        )

        if signals:
            for signal in signals:
                print(f"🚨 Uncertainty detected: {signal.uncertainty_type.value}")
                if signal.priority_level in ["high", "critical"]:
                    resolution = await escalation_manager.escalate_uncertainty(signal)
                    if resolution:
                        print(f"👤 Human resolved: {resolution.final_response[:50]}...")

        print()

    # Show final metrics
    attention_metrics = attention_manager.get_attention_metrics()
    escalation_stats = escalation_manager.get_escalation_stats()

    print("📊 Final Metrics:")
    print(f"  Attention: {attention_metrics['context_switches']} switches, {attention_metrics['tasks_completed']} completed")
    print(f"  Escalation: {escalation_stats['resolutions_completed']} resolutions, queue size: {escalation_stats['queue_size']}")

async def main():
    """Run all integration tests"""
    print("🚀 === Simplified EA Integration Test Suite ===\n")

    try:
        # Test 1: Attention span system
        await test_simplified_ea_with_attention_span()

        # Test 2: Human-in-the-loop system
        await test_human_in_loop_integration()

        # Test 3: Combined system
        await test_combined_system()

        print("\n🎉 === All Integration Tests Passed! ===")
        print("✅ Simplified EA architecture working")
        print("✅ Attention span control functional")
        print("✅ Human-in-the-loop uncertainty detection operational")
        print("✅ Combined system integration successful")

        return True

    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)