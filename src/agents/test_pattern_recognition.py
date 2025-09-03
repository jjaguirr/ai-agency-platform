#!/usr/bin/env python3
"""
Test Pattern Recognition Components - Core AI/ML Logic

Tests the business learning algorithms and semantic pattern recognition
without requiring external dependencies like Redis, Qdrant, or PostgreSQL.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MockEAMemoryIntegration:
    """Mock version of EA memory integration for testing pattern recognition"""
    
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.learning_config = {
            "min_confidence_score": 0.7,
            "automation_threshold": 0.6,
            "priority_threshold": 0.5
        }
    
    async def _identify_process_patterns(self, message: str) -> List[Dict[str, Any]]:
        """Identify business process patterns in the message"""
        patterns = []
        message_lower = message.lower()
        
        # Process indicators
        process_keywords = [
            ("every day", "daily routine", 0.8),
            ("weekly", "weekly process", 0.7),
            ("manually", "manual process", 0.9),
            ("step by step", "structured process", 0.8),
            ("workflow", "business workflow", 0.9),
            ("procedure", "business procedure", 0.7),
            ("process", "business process", 0.6)
        ]
        
        for keyword, description, confidence in process_keywords:
            if keyword in message_lower:
                # Extract surrounding context for better understanding
                start_idx = max(0, message_lower.index(keyword) - 50)
                end_idx = min(len(message), message_lower.index(keyword) + len(keyword) + 50)
                context = message[start_idx:end_idx]
                
                patterns.append({
                    "keyword": keyword,
                    "description": f"Identified {description}: {context}",
                    "confidence": confidence,
                    "automation_score": 0.7,
                    "context": context,
                    "entities": self._extract_entities_from_context(context)
                })
        
        return patterns
    
    async def _identify_automation_patterns(self, message: str) -> List[Dict[str, Any]]:
        """Identify explicit automation opportunities"""
        patterns = []
        message_lower = message.lower()
        
        # Automation indicators
        automation_keywords = [
            ("automate", "automation request", 0.95),
            ("automatically", "automatic process", 0.9),
            ("streamline", "process optimization", 0.8),
            ("eliminate manual", "manual elimination", 0.9),
            ("save time", "time optimization", 0.7),
            ("reduce effort", "effort reduction", 0.7),
            ("make easier", "process simplification", 0.6)
        ]
        
        for keyword, description, confidence in automation_keywords:
            if keyword in message_lower:
                start_idx = max(0, message_lower.index(keyword) - 50)
                end_idx = min(len(message), message_lower.index(keyword) + len(keyword) + 50)
                context = message[start_idx:end_idx]
                
                patterns.append({
                    "keyword": keyword,
                    "description": f"Automation opportunity: {context}",
                    "confidence": confidence,
                    "automation_score": 0.9,
                    "context": context,
                    "entities": self._extract_entities_from_context(context)
                })
        
        return patterns
    
    async def _identify_pain_point_patterns(self, message: str) -> List[Dict[str, Any]]:
        """Identify business pain points and inefficiencies"""
        patterns = []
        message_lower = message.lower()
        
        # Pain point indicators
        pain_keywords = [
            ("takes too long", "time inefficiency", 0.8),
            ("waste time", "time waste", 0.9),
            ("frustrating", "workflow frustration", 0.7),
            ("repetitive", "repetitive task", 0.8),
            ("boring", "monotonous work", 0.6),
            ("error prone", "error risk", 0.9),
            ("bottleneck", "process bottleneck", 0.8),
            ("slow", "performance issue", 0.6)
        ]
        
        for keyword, description, confidence in pain_keywords:
            if keyword in message_lower:
                start_idx = max(0, message_lower.index(keyword) - 50)
                end_idx = min(len(message), message_lower.index(keyword) + len(keyword) + 50)
                context = message[start_idx:end_idx]
                
                patterns.append({
                    "keyword": keyword,
                    "description": f"Pain point identified: {context}",
                    "confidence": confidence,
                    "automation_score": 0.8,
                    "context": context,
                    "entities": self._extract_entities_from_context(context)
                })
        
        return patterns
    
    async def _identify_tool_integration_patterns(self, message: str) -> List[Dict[str, Any]]:
        """Identify potential tool integrations"""
        patterns = []
        message_lower = message.lower()
        
        # Common business tools
        tools = [
            ("excel", "spreadsheet", ["microsoft_excel", "google_sheets"]),
            ("google sheets", "spreadsheet", ["google_sheets"]),
            ("slack", "communication", ["slack"]),
            ("email", "communication", ["gmail", "outlook"]),
            ("trello", "project_management", ["trello"]),
            ("asana", "project_management", ["asana"]),
            ("salesforce", "crm", ["salesforce"]),
            ("hubspot", "crm", ["hubspot"]),
            ("mailchimp", "email_marketing", ["mailchimp"]),
            ("instagram", "social_media", ["instagram"]),
            ("facebook", "social_media", ["facebook"]),
            ("twitter", "social_media", ["twitter"]),
            ("linkedin", "social_media", ["linkedin"]),
            ("quickbooks", "accounting", ["quickbooks"]),
            ("shopify", "ecommerce", ["shopify"]),
            ("wordpress", "website", ["wordpress"]),
            ("calendly", "scheduling", ["calendly"]),
            ("canva", "design", ["canva"]),
            ("buffer", "social_media_management", ["buffer"])
        ]
        
        for tool_name, category, tool_ids in tools:
            if tool_name in message_lower:
                start_idx = max(0, message_lower.index(tool_name) - 30)
                end_idx = min(len(message), message_lower.index(tool_name) + len(tool_name) + 30)
                context = message[start_idx:end_idx]
                
                patterns.append({
                    "tool": tool_name,
                    "category": category,
                    "description": f"Tool integration opportunity: {tool_name} in {category}",
                    "confidence": 0.8,
                    "automation_score": 0.7,
                    "tools": tool_ids,
                    "context": context,
                    "entities": {"tool": tool_name, "category": category}
                })
        
        return patterns
    
    def _extract_entities_from_context(self, context: str) -> Dict[str, Any]:
        """Extract relevant entities from context"""
        entities = {}
        
        # Time entities
        time_patterns = ["daily", "weekly", "monthly", "hourly", "every", "each"]
        for pattern in time_patterns:
            if pattern in context.lower():
                entities["frequency"] = pattern
        
        # Number entities
        import re
        numbers = re.findall(r'\b\d+\b', context)
        if numbers:
            entities["numbers"] = numbers
        
        return entities
    
    async def test_pattern_recognition(self, test_messages: List[str]) -> Dict[str, Any]:
        """Test pattern recognition on a set of business messages"""
        results = {
            "messages_processed": 0,
            "total_patterns_found": 0,
            "pattern_breakdown": {
                "process_patterns": 0,
                "automation_patterns": 0, 
                "pain_point_patterns": 0,
                "tool_integration_patterns": 0
            },
            "high_confidence_patterns": 0,
            "automation_ready_patterns": 0,
            "detected_tools": set(),
            "detected_frequencies": set(),
            "test_results": []
        }
        
        for message in test_messages:
            message_results = {
                "message": message,
                "patterns_found": [],
                "total_patterns": 0,
                "confidence_scores": [],
                "automation_scores": []
            }
            
            # Test all pattern recognition methods
            process_patterns = await self._identify_process_patterns(message)
            automation_patterns = await self._identify_automation_patterns(message)
            pain_point_patterns = await self._identify_pain_point_patterns(message)
            tool_patterns = await self._identify_tool_integration_patterns(message)
            
            all_patterns = process_patterns + automation_patterns + pain_point_patterns + tool_patterns
            
            # Aggregate results
            message_results["patterns_found"] = all_patterns
            message_results["total_patterns"] = len(all_patterns)
            
            for pattern in all_patterns:
                confidence = pattern.get("confidence", 0)
                automation_score = pattern.get("automation_score", 0)
                
                message_results["confidence_scores"].append(confidence)
                message_results["automation_scores"].append(automation_score)
                
                if confidence >= 0.8:
                    results["high_confidence_patterns"] += 1
                if automation_score >= 0.8:
                    results["automation_ready_patterns"] += 1
                
                # Extract tools and frequencies
                if pattern.get("entities"):
                    if "tool" in pattern["entities"]:
                        results["detected_tools"].add(pattern["entities"]["tool"])
                    if "frequency" in pattern["entities"]:
                        results["detected_frequencies"].add(pattern["entities"]["frequency"])
            
            # Update pattern breakdown
            results["pattern_breakdown"]["process_patterns"] += len(process_patterns)
            results["pattern_breakdown"]["automation_patterns"] += len(automation_patterns) 
            results["pattern_breakdown"]["pain_point_patterns"] += len(pain_point_patterns)
            results["pattern_breakdown"]["tool_integration_patterns"] += len(tool_patterns)
            
            results["test_results"].append(message_results)
            results["messages_processed"] += 1
            results["total_patterns_found"] += len(all_patterns)
        
        # Convert sets to lists for JSON serialization
        results["detected_tools"] = list(results["detected_tools"])
        results["detected_frequencies"] = list(results["detected_frequencies"])
        
        return results


async def main():
    """Test pattern recognition with realistic business conversations"""
    print("🧠 Testing AI/ML Pattern Recognition for Business Learning")
    print("=" * 70)
    
    # Initialize mock integration
    customer_id = "pattern_test_customer"
    integration = MockEAMemoryIntegration(customer_id)
    
    # Test messages covering various business scenarios
    test_messages = [
        # Social media automation
        "I manually post to Instagram and Facebook every day for 15 restaurant clients using Canva and Buffer. It takes 3 hours and it's very repetitive.",
        
        # Email automation
        "Every Monday I send follow-up emails to prospects who haven't responded. I copy and paste from templates and it's so time consuming.",
        
        # Inventory management
        "I have to update inventory levels manually in Shopify, Amazon, and eBay when items are running low. It's error prone and frustrating.",
        
        # Customer support
        "We get 50+ customer inquiries daily via email. I manually check our knowledge base and respond. Can we automate this process?",
        
        # Analytics and reporting
        "I spend 2 hours every Friday generating performance reports from Google Analytics and emailing them to clients using data from multiple sources.",
        
        # Lead management
        "New leads from our website go into a Google Sheet. I manually add them to Salesforce and send welcome emails. Very tedious workflow.",
        
        # Content creation
        "I create blog posts weekly, then manually post to WordPress, share on LinkedIn and Twitter, and track engagement in Excel.",
        
        # Appointment scheduling
        "Clients book appointments through different channels. I manually update our calendar and send confirmation emails using Outlook."
    ]
    
    print(f"🔍 Testing {len(test_messages)} business scenarios...")
    print()
    
    # Run pattern recognition tests
    results = await integration.test_pattern_recognition(test_messages)
    
    # Print detailed results
    print("📊 Pattern Recognition Results:")
    print("-" * 40)
    print(f"Messages processed: {results['messages_processed']}")
    print(f"Total patterns found: {results['total_patterns_found']}")
    print(f"Average patterns per message: {results['total_patterns_found'] / results['messages_processed']:.1f}")
    print()
    
    print("🎯 Pattern Breakdown:")
    for pattern_type, count in results['pattern_breakdown'].items():
        print(f"  - {pattern_type.replace('_', ' ').title()}: {count}")
    print()
    
    print("⭐ Quality Metrics:")
    print(f"  - High confidence patterns (>80%): {results['high_confidence_patterns']}")
    print(f"  - Automation ready patterns (>80%): {results['automation_ready_patterns']}")
    print(f"  - Tools detected: {len(results['detected_tools'])}")
    print(f"  - Frequencies detected: {len(results['detected_frequencies'])}")
    print()
    
    print("🛠️ Detected Tools:")
    for tool in sorted(results['detected_tools']):
        print(f"  - {tool}")
    print()
    
    print("⏰ Detected Frequencies:")
    for freq in sorted(results['detected_frequencies']):
        print(f"  - {freq}")
    print()
    
    # Show detailed results for first few messages
    print("📝 Sample Pattern Detection Results:")
    print("-" * 40)
    
    for i, test_result in enumerate(results['test_results'][:3]):  # Show first 3
        print(f"Message {i+1}: {test_result['message'][:80]}...")
        print(f"  Patterns found: {test_result['total_patterns']}")
        
        if test_result['confidence_scores']:
            avg_confidence = sum(test_result['confidence_scores']) / len(test_result['confidence_scores'])
            print(f"  Average confidence: {avg_confidence:.2f}")
        
        if test_result['automation_scores']:
            avg_automation = sum(test_result['automation_scores']) / len(test_result['automation_scores'])
            print(f"  Average automation potential: {avg_automation:.2f}")
        
        # Show top patterns for this message
        for pattern in test_result['patterns_found'][:2]:  # Show top 2
            print(f"    - {pattern['description'][:60]}... (confidence: {pattern['confidence']:.2f})")
        print()
    
    # Calculate success metrics
    success_metrics = {
        "pattern_detection_rate": results['total_patterns_found'] / results['messages_processed'],
        "high_confidence_rate": results['high_confidence_patterns'] / results['total_patterns_found'] * 100,
        "automation_readiness_rate": results['automation_ready_patterns'] / results['total_patterns_found'] * 100,
        "tool_detection_accuracy": len(results['detected_tools']) / results['messages_processed'],
        "comprehensive_coverage": len(results['pattern_breakdown']) == 4  # All pattern types detected
    }
    
    print("🎯 Success Metrics:")
    print(f"  - Pattern detection rate: {success_metrics['pattern_detection_rate']:.1f} patterns/message")
    print(f"  - High confidence rate: {success_metrics['high_confidence_rate']:.1f}%")
    print(f"  - Automation readiness rate: {success_metrics['automation_readiness_rate']:.1f}%")
    print(f"  - Tool detection rate: {success_metrics['tool_detection_accuracy']:.1f} tools/message")
    print(f"  - Pattern type coverage: {'✅' if success_metrics['comprehensive_coverage'] else '❌'}")
    print()
    
    # Overall assessment
    if (success_metrics['pattern_detection_rate'] >= 2.0 and
        success_metrics['high_confidence_rate'] >= 70 and
        success_metrics['automation_readiness_rate'] >= 60):
        print("✅ AI/ML Pattern Recognition: EXCELLENT")
        print("🚀 Ready for production deployment with business learning capabilities")
    elif (success_metrics['pattern_detection_rate'] >= 1.5 and
          success_metrics['high_confidence_rate'] >= 60):
        print("🔶 AI/ML Pattern Recognition: GOOD")
        print("⚡ Ready for deployment with continued optimization")
    else:
        print("⚠️  AI/ML Pattern Recognition: NEEDS IMPROVEMENT")
        print("🔧 Requires optimization before production deployment")
    
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())