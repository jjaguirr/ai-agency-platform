"""
EA-Mem0 Memory Integration Layer - AI/ML Enhanced Business Learning

Integrates the Executive Assistant with Mem0 memory system for:
- Intelligent business discovery and learning
- Semantic pattern recognition for automation opportunities
- Cross-channel conversation continuity
- Memory-driven template selection for workflow creation
- Real-time business insights and recommendations

This bridges the gap between the EA agent and the Mem0 infrastructure.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from memory.mem0_manager import EAMemoryManager, OptimizedMemoryRouter, maintain_conversation_continuity
from memory.performance_monitor import MemoryPerformanceMonitor, global_monitor
from ..ai_ml.business_learning_engine import BusinessLearningEngine
from ..ai_ml.workflow_template_matcher import WorkflowTemplateMatcher

logger = logging.getLogger(__name__)


class BusinessInsightType(Enum):
    PROCESS_DISCOVERY = "process_discovery"
    AUTOMATION_OPPORTUNITY = "automation_opportunity"
    PAIN_POINT_IDENTIFICATION = "pain_point_identification"
    TOOL_INTEGRATION = "tool_integration"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"
    BUSINESS_GOAL = "business_goal"


@dataclass
class BusinessLearning:
    """Structured business learning extracted from conversations"""
    insight_type: BusinessInsightType
    content: str
    confidence_score: float  # 0.0 to 1.0
    automation_potential: float  # 0.0 to 1.0
    priority_score: float  # 0.0 to 1.0
    related_tools: List[str]
    extracted_entities: Dict[str, Any]
    conversation_context: str
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_type": self.insight_type.value,
            "content": self.content,
            "confidence_score": self.confidence_score,
            "automation_potential": self.automation_potential,
            "priority_score": self.priority_score,
            "related_tools": self.related_tools,
            "extracted_entities": self.extracted_entities,
            "conversation_context": self.conversation_context,
            "timestamp": self.timestamp
        }


@dataclass
class ConversationContext:
    """Rich conversation context for memory operations"""
    customer_id: str
    conversation_id: str
    channel: str
    message_history: List[Dict[str, str]]
    current_intent: str
    business_context: Optional[Dict[str, Any]] = None
    previous_learnings: List[BusinessLearning] = None
    
    def __post_init__(self):
        if self.previous_learnings is None:
            self.previous_learnings = []


class EAMemoryIntegration:
    """
    AI/ML-enhanced integration between Executive Assistant and Mem0 memory system.
    
    Provides intelligent business learning, semantic pattern recognition,
    and conversation continuity across all communication channels.
    """
    
    def __init__(self, customer_id: str):
        """
        Initialize EA-Mem0 integration for customer.
        
        Args:
            customer_id: Unique customer identifier
        """
        self.customer_id = customer_id
        
        # Initialize memory layers
        self.memory_manager = EAMemoryManager(customer_id)
        self.memory_router = OptimizedMemoryRouter(self.memory_manager)
        
        # Performance monitoring
        self.performance_monitor = global_monitor.get_customer_monitor(customer_id)
        
        # AI/ML components for enhanced business learning
        self.business_learning_engine = BusinessLearningEngine()
        self.workflow_template_matcher = WorkflowTemplateMatcher()
        
        # Business learning configuration
        self.learning_config = {
            "min_confidence_score": 0.7,
            "automation_threshold": 0.6,
            "priority_threshold": 0.5,
            "max_context_history": 10,
            "semantic_similarity_threshold": 0.8,
            "enable_ai_ml_processing": True,
            "template_matching_enabled": True
        }
        
        # Pattern recognition cache
        self._pattern_cache = {}
        self._last_pattern_update = None
        
        logger.info(f"Initialized EA-Mem0 integration with AI/ML enhancements for customer {customer_id}")
    
    async def process_business_conversation(self, conversation_context: ConversationContext) -> Dict[str, Any]:
        """
        Process business conversation and extract learnings for memory storage.
        
        This is the core AI/ML method that analyzes conversations to understand
        business context, identify automation opportunities, and build semantic knowledge.
        
        Args:
            conversation_context: Rich conversation context with history
            
        Returns:
            Processing results with extracted learnings and recommendations
        """
        start_time = time.time()
        
        try:
            # Extract current message for processing
            current_message = conversation_context.message_history[-1] if conversation_context.message_history else {}
            user_message = current_message.get("content", "")
            
            # Retrieve relevant business context from memory
            context_memories = await self._retrieve_relevant_context(
                query=user_message,
                conversation_context=conversation_context
            )
            
            # Use AI/ML Business Learning Engine for advanced analysis
            if self.learning_config["enable_ai_ml_processing"]:
                business_insights = await self.business_learning_engine.extract_business_insights(
                    conversation_text=user_message,
                    conversation_history=conversation_context.message_history,
                    context_memories=context_memories
                )
                
                # Convert AI/ML insights to legacy format for backward compatibility
                business_learnings = await self._convert_insights_to_learnings(business_insights)
            else:
                # Fallback to legacy pattern extraction
                business_learnings = await self._extract_business_learnings(
                    user_message=user_message,
                    conversation_history=conversation_context.message_history,
                    existing_context=context_memories
                )
            
            # Store high-confidence learnings in memory
            stored_learnings = []
            for learning in business_learnings:
                if learning.confidence_score >= self.learning_config["min_confidence_score"]:
                    memory_id = await self._store_business_learning(learning, conversation_context.conversation_id)
                    if memory_id:
                        stored_learnings.append({
                            "learning": learning.to_dict(),
                            "memory_id": memory_id
                        })
            
            # Identify automation opportunities
            automation_opportunities = await self._identify_automation_opportunities(
                business_learnings=business_learnings,
                conversation_context=conversation_context
            )
            
            # Generate workflow template recommendations using AI/ML matcher
            if self.learning_config["template_matching_enabled"] and hasattr(self, 'workflow_template_matcher'):
                template_recommendations_result = await self.workflow_template_matcher.recommend_templates(
                    business_insights=business_insights if self.learning_config["enable_ai_ml_processing"] else {
                        "automation_opportunities": automation_opportunities,
                        "business_entities": [],
                        "business_patterns": []
                    },
                    customer_context={"customer_id": self.customer_id}
                )
                template_recommendations = template_recommendations_result.get("template_recommendations", [])
            else:
                # Fallback to legacy template recommendation
                template_recommendations = await self._recommend_workflow_templates(
                    automation_opportunities=automation_opportunities,
                    business_context=context_memories
                )
            
            # Maintain conversation continuity
            continuity_result = await maintain_conversation_continuity(
                ea_memory=self.memory_manager,
                channel=conversation_context.channel,
                message=user_message,
                user_context={
                    "conversation_id": conversation_context.conversation_id,
                    "current_intent": conversation_context.current_intent,
                    "business_learnings": [l.to_dict() for l in business_learnings]
                }
            )
            
            processing_time = time.time() - start_time
            
            # Track performance
            await self.performance_monitor.track_memory_operation(
                operation="business_conversation_processing",
                latency=processing_time,
                success=True,
                metadata={
                    "learnings_extracted": len(business_learnings),
                    "learnings_stored": len(stored_learnings),
                    "automation_opportunities": len(automation_opportunities),
                    "channel": conversation_context.channel
                }
            )
            
            processing_results = {
                "processing_timestamp": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "customer_id": self.customer_id,
                "conversation_id": conversation_context.conversation_id,
                
                # Business learning results
                "business_learnings": [l.to_dict() for l in business_learnings],
                "stored_learnings": stored_learnings,
                "high_confidence_learnings": len([l for l in business_learnings if l.confidence_score >= 0.8]),
                
                # Automation insights
                "automation_opportunities": automation_opportunities,
                "template_recommendations": template_recommendations,
                "workflow_ready_opportunities": len([o for o in automation_opportunities if o.get("readiness_score", 0) > 0.8]),
                
                # Memory context
                "relevant_context_retrieved": len(context_memories),
                "conversation_continuity": continuity_result,
                
                # Performance metrics
                "memory_operations_successful": True,
                "performance_within_sla": processing_time < 2.0  # 2 second SLA for conversation processing
            }
            
            logger.info(f"Processed business conversation for customer {self.customer_id}: "
                       f"{len(business_learnings)} learnings extracted, {len(automation_opportunities)} opportunities identified")
            
            return processing_results
            
        except Exception as e:
            processing_time = time.time() - start_time
            
            # Track error in performance monitoring
            await self.performance_monitor.track_memory_operation(
                operation="business_conversation_processing",
                latency=processing_time,
                success=False,
                metadata={"error": str(e)}
            )
            
            logger.error(f"Error processing business conversation for customer {self.customer_id}: {e}")
            return {
                "processing_timestamp": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "customer_id": self.customer_id,
                "error": str(e),
                "memory_operations_successful": False
            }
    
    async def _retrieve_relevant_context(self, query: str, conversation_context: ConversationContext) -> List[Dict[str, Any]]:
        """Retrieve relevant business context from memory using semantic search"""
        try:
            # Use optimized memory router for intelligent retrieval
            semantic_memories = await self.memory_router.intelligent_memory_retrieval(
                query=query,
                query_type="business_knowledge"
            )
            
            # Also get immediate conversation context
            immediate_context = await self.memory_router.intelligent_memory_retrieval(
                query=f"conversation:{conversation_context.conversation_id}",
                query_type="immediate_context"
            )
            
            # Combine and rank by relevance
            all_memories = []
            
            if isinstance(semantic_memories, list):
                all_memories.extend(semantic_memories)
            
            if immediate_context:
                all_memories.append({
                    "memory": json.dumps(immediate_context),
                    "score": 1.0,
                    "metadata": {"type": "immediate_context"}
                })
            
            # Sort by relevance score
            all_memories.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            return all_memories[:self.learning_config["max_context_history"]]
            
        except Exception as e:
            logger.error(f"Error retrieving relevant context: {e}")
            return []
    
    async def _extract_business_learnings(self, user_message: str, conversation_history: List[Dict[str, str]], 
                                        existing_context: List[Dict[str, Any]]) -> List[BusinessLearning]:
        """
        Extract structured business learnings from conversation using AI/ML analysis.
        
        This method uses pattern matching and semantic analysis to identify:
        - Business processes that can be automated
        - Pain points and inefficiencies
        - Integration opportunities with existing tools
        - Business goals and priorities
        """
        learnings = []
        
        try:
            # Analyze message for business patterns
            process_patterns = await self._identify_process_patterns(user_message)
            automation_patterns = await self._identify_automation_patterns(user_message)
            pain_point_patterns = await self._identify_pain_point_patterns(user_message)
            tool_patterns = await self._identify_tool_integration_patterns(user_message)
            
            # Create business learnings from patterns
            for pattern in process_patterns:
                learning = BusinessLearning(
                    insight_type=BusinessInsightType.PROCESS_DISCOVERY,
                    content=pattern["description"],
                    confidence_score=pattern["confidence"],
                    automation_potential=pattern.get("automation_score", 0.5),
                    priority_score=self._calculate_priority_score(pattern, existing_context),
                    related_tools=pattern.get("tools", []),
                    extracted_entities=pattern.get("entities", {}),
                    conversation_context=user_message[:200],
                    timestamp=datetime.utcnow().isoformat()
                )
                learnings.append(learning)
            
            for pattern in automation_patterns:
                learning = BusinessLearning(
                    insight_type=BusinessInsightType.AUTOMATION_OPPORTUNITY,
                    content=pattern["description"],
                    confidence_score=pattern["confidence"],
                    automation_potential=pattern.get("automation_score", 0.8),
                    priority_score=self._calculate_priority_score(pattern, existing_context),
                    related_tools=pattern.get("tools", []),
                    extracted_entities=pattern.get("entities", {}),
                    conversation_context=user_message[:200],
                    timestamp=datetime.utcnow().isoformat()
                )
                learnings.append(learning)
            
            for pattern in pain_point_patterns:
                learning = BusinessLearning(
                    insight_type=BusinessInsightType.PAIN_POINT_IDENTIFICATION,
                    content=pattern["description"],
                    confidence_score=pattern["confidence"],
                    automation_potential=pattern.get("automation_score", 0.7),
                    priority_score=self._calculate_priority_score(pattern, existing_context),
                    related_tools=pattern.get("tools", []),
                    extracted_entities=pattern.get("entities", {}),
                    conversation_context=user_message[:200],
                    timestamp=datetime.utcnow().isoformat()
                )
                learnings.append(learning)
            
            for pattern in tool_patterns:
                learning = BusinessLearning(
                    insight_type=BusinessInsightType.TOOL_INTEGRATION,
                    content=pattern["description"],
                    confidence_score=pattern["confidence"],
                    automation_potential=pattern.get("automation_score", 0.6),
                    priority_score=self._calculate_priority_score(pattern, existing_context),
                    related_tools=pattern.get("tools", []),
                    extracted_entities=pattern.get("entities", {}),
                    conversation_context=user_message[:200],
                    timestamp=datetime.utcnow().isoformat()
                )
                learnings.append(learning)
            
            return learnings
            
        except Exception as e:
            logger.error(f"Error extracting business learnings: {e}")
            return []
    
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
                    "automation_score": 0.7,  # Processes are generally automatable
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
                    "automation_score": 0.9,  # High automation potential
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
                    "automation_score": 0.8,  # Pain points often indicate automation opportunities
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
            ("calendly", "scheduling", ["calendly"])
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
        """Extract relevant entities from context (simplified implementation)"""
        entities = {}
        
        # Time entities
        time_patterns = ["daily", "weekly", "monthly", "hourly", "every", "each"]
        for pattern in time_patterns:
            if pattern in context.lower():
                entities["frequency"] = pattern
        
        # Number entities (simplified)
        import re
        numbers = re.findall(r'\b\d+\b', context)
        if numbers:
            entities["numbers"] = numbers
        
        # Tool entities (already handled in tool patterns)
        
        return entities
    
    def _calculate_priority_score(self, pattern: Dict[str, Any], existing_context: List[Dict[str, Any]]) -> float:
        """Calculate priority score based on pattern and existing context"""
        base_score = pattern.get("automation_score", 0.5)
        confidence = pattern.get("confidence", 0.5)
        
        # Boost priority if similar patterns exist in context
        similarity_boost = 0.0
        for context_item in existing_context:
            if self._calculate_semantic_similarity(pattern.get("description", ""), 
                                                 context_item.get("memory", "")) > 0.7:
                similarity_boost += 0.1
        
        # Cap the boost
        similarity_boost = min(similarity_boost, 0.3)
        
        priority_score = min(1.0, (base_score + confidence) / 2 + similarity_boost)
        return priority_score
    
    def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between two texts (simplified implementation)"""
        # Simplified implementation using word overlap
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    async def _store_business_learning(self, learning: BusinessLearning, session_id: str) -> Optional[str]:
        """Store business learning in Mem0 memory system"""
        try:
            # Prepare learning data for storage
            learning_context = {
                "business_description": learning.content,
                "phase": "business_learning",
                "insight_type": learning.insight_type.value,
                "automation_potential": learning.automation_potential,
                "priority_score": learning.priority_score,
                "confidence_score": learning.confidence_score,
                "related_tools": learning.related_tools,
                "extracted_entities": learning.extracted_entities
            }
            
            memory_id = await self.memory_manager.store_business_context(
                context=learning_context,
                session_id=session_id
            )
            
            if memory_id:
                logger.info(f"Stored business learning {memory_id}: {learning.insight_type.value}")
            
            return memory_id
            
        except Exception as e:
            logger.error(f"Error storing business learning: {e}")
            return None
    
    async def _identify_automation_opportunities(self, business_learnings: List[BusinessLearning],
                                               conversation_context: ConversationContext) -> List[Dict[str, Any]]:
        """Identify specific automation opportunities from business learnings"""
        opportunities = []
        
        for learning in business_learnings:
            if (learning.automation_potential >= self.learning_config["automation_threshold"] and
                learning.confidence_score >= self.learning_config["min_confidence_score"]):
                
                opportunity = {
                    "id": str(uuid.uuid4()),
                    "type": learning.insight_type.value,
                    "description": learning.content,
                    "automation_potential": learning.automation_potential,
                    "priority_score": learning.priority_score,
                    "readiness_score": self._calculate_readiness_score(learning),
                    "related_tools": learning.related_tools,
                    "estimated_impact": self._estimate_automation_impact(learning),
                    "implementation_complexity": self._estimate_implementation_complexity(learning),
                    "recommended_templates": await self._get_matching_templates(learning)
                }
                
                opportunities.append(opportunity)
        
        # Sort by combined score (readiness * priority * impact)
        opportunities.sort(
            key=lambda x: x["readiness_score"] * x["priority_score"] * x["estimated_impact"],
            reverse=True
        )
        
        return opportunities
    
    def _calculate_readiness_score(self, learning: BusinessLearning) -> float:
        """Calculate how ready an opportunity is for automation"""
        readiness_factors = [
            learning.confidence_score * 0.4,  # Confidence in understanding
            learning.automation_potential * 0.3,  # Technical feasibility
            (len(learning.related_tools) > 0) * 0.2,  # Tool availability
            (len(learning.extracted_entities) > 0) * 0.1  # Structured data available
        ]
        
        return sum(readiness_factors)
    
    def _estimate_automation_impact(self, learning: BusinessLearning) -> float:
        """Estimate the impact of automating this opportunity"""
        # Simplified impact estimation based on keywords and context
        high_impact_keywords = ["daily", "weekly", "hours", "repetitive", "manual", "time consuming"]
        impact_score = 0.5  # Base score
        
        content_lower = learning.content.lower()
        for keyword in high_impact_keywords:
            if keyword in content_lower:
                impact_score += 0.1
        
        return min(1.0, impact_score)
    
    def _estimate_implementation_complexity(self, learning: BusinessLearning) -> str:
        """Estimate implementation complexity (low, medium, high)"""
        if learning.automation_potential >= 0.8 and len(learning.related_tools) > 0:
            return "low"
        elif learning.automation_potential >= 0.6:
            return "medium"
        else:
            return "high"
    
    async def _get_matching_templates(self, learning: BusinessLearning) -> List[str]:
        """Get workflow templates that match the automation opportunity"""
        # Simplified template matching based on insight type and tools
        template_map = {
            BusinessInsightType.PROCESS_DISCOVERY: ["process_automation", "task_scheduler"],
            BusinessInsightType.AUTOMATION_OPPORTUNITY: ["workflow_automation", "task_automation"],
            BusinessInsightType.PAIN_POINT_IDENTIFICATION: ["efficiency_optimizer", "error_reducer"],
            BusinessInsightType.TOOL_INTEGRATION: ["app_connector", "data_sync"],
            BusinessInsightType.WORKFLOW_OPTIMIZATION: ["workflow_optimizer", "process_improver"]
        }
        
        base_templates = template_map.get(learning.insight_type, ["generic_automation"])
        
        # Add tool-specific templates
        tool_templates = []
        for tool in learning.related_tools:
            if "social" in tool.lower():
                tool_templates.append("social_media_automation")
            elif "email" in tool.lower():
                tool_templates.append("email_automation")
            elif "sheet" in tool.lower() or "excel" in tool.lower():
                tool_templates.append("spreadsheet_automation")
        
        return base_templates + tool_templates
    
    async def _recommend_workflow_templates(self, automation_opportunities: List[Dict[str, Any]],
                                          business_context: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recommend specific workflow templates based on opportunities and context"""
        recommendations = []
        
        for opportunity in automation_opportunities:
            if opportunity["readiness_score"] > 0.7:  # Only recommend high-readiness opportunities
                for template in opportunity["recommended_templates"]:
                    recommendation = {
                        "template_id": template,
                        "opportunity_id": opportunity["id"],
                        "match_score": opportunity["readiness_score"],
                        "priority": "high" if opportunity["priority_score"] > 0.7 else "medium",
                        "estimated_setup_time": self._estimate_setup_time(template, opportunity),
                        "required_integrations": opportunity["related_tools"],
                        "expected_benefits": self._describe_expected_benefits(opportunity)
                    }
                    recommendations.append(recommendation)
        
        # Remove duplicates and sort by match score
        seen_templates = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec["template_id"] not in seen_templates:
                seen_templates.add(rec["template_id"])
                unique_recommendations.append(rec)
        
        unique_recommendations.sort(key=lambda x: x["match_score"], reverse=True)
        return unique_recommendations[:5]  # Top 5 recommendations
    
    def _estimate_setup_time(self, template: str, opportunity: Dict[str, Any]) -> str:
        """Estimate setup time for template implementation"""
        if opportunity["implementation_complexity"] == "low":
            return "5-10 minutes"
        elif opportunity["implementation_complexity"] == "medium":
            return "15-30 minutes"
        else:
            return "45-60 minutes"
    
    def _describe_expected_benefits(self, opportunity: Dict[str, Any]) -> List[str]:
        """Describe expected benefits of automating the opportunity"""
        benefits = []
        
        if opportunity["estimated_impact"] > 0.8:
            benefits.append("Significant time savings")
        if opportunity["automation_potential"] > 0.8:
            benefits.append("High automation success rate")
        if "repetitive" in opportunity["description"].lower():
            benefits.append("Eliminates repetitive manual work")
        if "error" in opportunity["description"].lower():
            benefits.append("Reduces human error risk")
        
        if not benefits:
            benefits.append("Improved efficiency and consistency")
        
        return benefits
    
    async def get_business_intelligence_summary(self) -> Dict[str, Any]:
        """Generate comprehensive business intelligence summary from memory"""
        try:
            # Retrieve all business context
            all_business_memories = await self.memory_manager.retrieve_business_context(
                query="business processes automation opportunities tools",
                limit=50
            )
            
            # Analyze patterns and generate insights
            intelligence_summary = {
                "generation_timestamp": datetime.utcnow().isoformat(),
                "customer_id": self.customer_id,
                "total_memories": len(all_business_memories),
                
                # Business understanding
                "business_processes_identified": self._count_insights_by_type(all_business_memories, "process"),
                "automation_opportunities_found": self._count_insights_by_type(all_business_memories, "automation"),
                "pain_points_identified": self._count_insights_by_type(all_business_memories, "pain"),
                "tools_discovered": self._extract_discovered_tools(all_business_memories),
                
                # Automation readiness
                "high_priority_opportunities": self._get_high_priority_opportunities(all_business_memories),
                "recommended_next_actions": await self._generate_next_actions(all_business_memories),
                
                # Learning effectiveness
                "learning_confidence_distribution": self._analyze_confidence_distribution(all_business_memories),
                "memory_quality_score": self._calculate_memory_quality_score(all_business_memories),
                
                # Performance metrics
                "memory_system_performance": await self.performance_monitor.get_current_performance_snapshot()
            }
            
            return intelligence_summary
            
        except Exception as e:
            logger.error(f"Error generating business intelligence summary: {e}")
            return {
                "generation_timestamp": datetime.utcnow().isoformat(),
                "customer_id": self.customer_id,
                "error": str(e)
            }
    
    def _count_insights_by_type(self, memories: List[Dict[str, Any]], insight_type: str) -> int:
        """Count memories containing specific insight type"""
        count = 0
        for memory in memories:
            memory_content = memory.get("memory", "").lower()
            if insight_type in memory_content:
                count += 1
        return count
    
    def _extract_discovered_tools(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Extract unique tools discovered from memories"""
        tools = set()
        common_tools = ["excel", "sheets", "slack", "email", "trello", "asana", "salesforce", 
                       "hubspot", "mailchimp", "instagram", "facebook", "twitter", "linkedin"]
        
        for memory in memories:
            memory_content = memory.get("memory", "").lower()
            for tool in common_tools:
                if tool in memory_content:
                    tools.add(tool)
        
        return list(tools)
    
    def _get_high_priority_opportunities(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract high-priority automation opportunities"""
        opportunities = []
        
        for memory in memories:
            memory_content = memory.get("memory", "")
            metadata = memory.get("metadata", {})
            
            # Check for high automation potential
            if (isinstance(metadata, dict) and 
                metadata.get("automation_potential", 0) > 0.7 and
                metadata.get("priority_score", 0) > 0.7):
                
                opportunities.append({
                    "description": memory_content[:150],
                    "automation_potential": metadata.get("automation_potential"),
                    "priority_score": metadata.get("priority_score"),
                    "confidence": metadata.get("confidence_score", 0)
                })
        
        return sorted(opportunities, key=lambda x: x.get("priority_score", 0), reverse=True)[:5]
    
    async def _generate_next_actions(self, memories: List[Dict[str, Any]]) -> List[str]:
        """Generate recommended next actions based on business learnings"""
        actions = []
        
        # Analyze memory patterns to suggest actions
        tool_count = len(self._extract_discovered_tools(memories))
        automation_count = self._count_insights_by_type(memories, "automation")
        process_count = self._count_insights_by_type(memories, "process")
        
        if automation_count > 3:
            actions.append("Consider implementing top 3 automation opportunities")
        if tool_count > 5:
            actions.append("Evaluate tool integration and consolidation opportunities")
        if process_count > 5:
            actions.append("Document and optimize core business processes")
        
        if not actions:
            actions.append("Continue business discovery conversations to identify opportunities")
        
        return actions
    
    def _analyze_confidence_distribution(self, memories: List[Dict[str, Any]]) -> Dict[str, int]:
        """Analyze confidence score distribution of memories"""
        distribution = {"high": 0, "medium": 0, "low": 0}
        
        for memory in memories:
            metadata = memory.get("metadata", {})
            confidence = metadata.get("confidence_score", 0)
            
            if confidence >= 0.8:
                distribution["high"] += 1
            elif confidence >= 0.6:
                distribution["medium"] += 1
            else:
                distribution["low"] += 1
        
        return distribution
    
    def _calculate_memory_quality_score(self, memories: List[Dict[str, Any]]) -> float:
        """Calculate overall quality score of stored memories"""
        if not memories:
            return 0.0
        
        confidence_sum = 0
        valid_memories = 0
        
        for memory in memories:
            metadata = memory.get("metadata", {})
            confidence = metadata.get("confidence_score")
            
            if isinstance(confidence, (int, float)):
                confidence_sum += confidence
                valid_memories += 1
        
        return confidence_sum / valid_memories if valid_memories > 0 else 0.0
    
    async def _convert_insights_to_learnings(self, business_insights: Dict[str, Any]) -> List[BusinessLearning]:
        """Convert AI/ML business insights to legacy BusinessLearning format"""
        learnings = []
        
        try:
            # Convert business entities to learnings
            entities = business_insights.get("business_entities", [])
            for entity in entities:
                if entity.get("confidence", 0) >= self.learning_config["min_confidence_score"]:
                    learning = BusinessLearning(
                        insight_type=self._map_entity_type_to_insight_type(entity.get("entity_type", "")),
                        content=f"{entity.get('entity_type', '')}: {entity.get('value', '')}",
                        confidence_score=entity.get("confidence", 0.0),
                        automation_potential=0.7,  # Default automation potential
                        priority_score=entity.get("confidence", 0.0),
                        related_tools=entity.get("metadata", {}).get("tool_category", []) if isinstance(entity.get("metadata", {}), dict) else [],
                        extracted_entities=entity.get("metadata", {}),
                        conversation_context=entity.get("context", ""),
                        timestamp=datetime.utcnow().isoformat()
                    )
                    learnings.append(learning)
            
            # Convert business patterns to learnings
            patterns = business_insights.get("business_patterns", [])
            for pattern in patterns:
                if pattern.get("confidence", 0) >= self.learning_config["min_confidence_score"]:
                    learning = BusinessLearning(
                        insight_type=self._map_pattern_type_to_insight_type(pattern.get("pattern_type", "")),
                        content=pattern.get("description", ""),
                        confidence_score=pattern.get("confidence", 0.0),
                        automation_potential=pattern.get("automation_score", 0.0),
                        priority_score=pattern.get("confidence", 0.0),
                        related_tools=pattern.get("template_matches", []),
                        extracted_entities=pattern.get("extracted_entities", []),
                        conversation_context=pattern.get("supporting_evidence", [""])[0] if pattern.get("supporting_evidence") else "",
                        timestamp=datetime.utcnow().isoformat()
                    )
                    learnings.append(learning)
            
            return learnings
            
        except Exception as e:
            logger.error(f"Error converting insights to learnings: {e}")
            return []
    
    def _map_entity_type_to_insight_type(self, entity_type: str) -> BusinessInsightType:
        """Map AI/ML entity types to legacy insight types"""
        mapping = {
            "tool_integration": BusinessInsightType.TOOL_INTEGRATION,
            "process": BusinessInsightType.PROCESS_DISCOVERY,
            "automation_opportunity": BusinessInsightType.AUTOMATION_OPPORTUNITY,
            "pain_point": BusinessInsightType.PAIN_POINT_IDENTIFICATION,
            "business_goal": BusinessInsightType.BUSINESS_GOAL
        }
        return mapping.get(entity_type.lower(), BusinessInsightType.PROCESS_DISCOVERY)
    
    def _map_pattern_type_to_insight_type(self, pattern_type: str) -> BusinessInsightType:
        """Map AI/ML pattern types to legacy insight types"""
        mapping = {
            "frequency_process": BusinessInsightType.PROCESS_DISCOVERY,
            "pain_point": BusinessInsightType.PAIN_POINT_IDENTIFICATION,
            "tool_integration": BusinessInsightType.TOOL_INTEGRATION,
            "sequential_workflow": BusinessInsightType.WORKFLOW_OPTIMIZATION,
            "context_similarity": BusinessInsightType.PROCESS_DISCOVERY
        }
        return mapping.get(pattern_type, BusinessInsightType.PROCESS_DISCOVERY)
    
    async def get_ai_ml_business_intelligence(self) -> Dict[str, Any]:
        """Get comprehensive AI/ML-powered business intelligence summary"""
        try:
            # Get base business intelligence from memory
            base_intelligence = await self.get_business_intelligence_summary()
            
            # If AI/ML processing is enabled, enhance with advanced insights
            if self.learning_config["enable_ai_ml_processing"]:
                # Get processing stats from business learning engine
                learning_stats = self.business_learning_engine.get_processing_stats()
                
                # Get template library statistics
                template_stats = self.workflow_template_matcher.get_template_library_stats()
                
                # Enhance intelligence with AI/ML insights
                base_intelligence["ai_ml_enhancements"] = {
                    "business_learning_engine": {
                        "processing_stats": learning_stats,
                        "model_status": learning_stats.get("model_initialized", False),
                        "advanced_pattern_recognition": True
                    },
                    "workflow_template_matcher": {
                        "template_library_stats": template_stats,
                        "matching_algorithm": "semantic_similarity_v1.0",
                        "roi_calculation_enabled": True
                    },
                    "ai_ml_processing_enabled": True,
                    "processing_capabilities": [
                        "Advanced business entity extraction",
                        "Semantic pattern recognition", 
                        "Intelligent template matching",
                        "ROI projections and impact analysis",
                        "Context-aware recommendations"
                    ]
                }
            
            return base_intelligence
            
        except Exception as e:
            logger.error(f"Error getting AI/ML business intelligence: {e}")
            # Fallback to base intelligence
            return await self.get_business_intelligence_summary()
    
    async def close(self):
        """Close memory connections and cleanup"""
        try:
            await self.memory_manager.close()
            logger.info(f"Closed EA-Mem0 integration for customer {self.customer_id}")
        except Exception as e:
            logger.error(f"Error closing EA-Mem0 integration: {e}")


# Utility functions for EA integration
async def create_ea_memory_integration(customer_id: str) -> EAMemoryIntegration:
    """Factory function to create EA memory integration"""
    return EAMemoryIntegration(customer_id)


async def process_ea_conversation(customer_id: str, message: str, channel: str, 
                                conversation_id: str, message_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """Convenient function to process EA conversations with memory integration"""
    if message_history is None:
        message_history = [{"role": "user", "content": message}]
    
    integration = EAMemoryIntegration(customer_id)
    
    try:
        conversation_context = ConversationContext(
            customer_id=customer_id,
            conversation_id=conversation_id,
            channel=channel,
            message_history=message_history,
            current_intent="business_assistance"
        )
        
        return await integration.process_business_conversation(conversation_context)
        
    finally:
        await integration.close()