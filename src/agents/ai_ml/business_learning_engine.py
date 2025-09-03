"""
AI/ML Business Learning Engine - Semantic Business Pattern Recognition

Advanced AI/ML algorithms for extracting business insights from conversations:
- Natural language processing for business context extraction
- Pattern recognition for automation opportunities
- Semantic similarity matching for workflow templates
- Confidence scoring and learning quality assessment
- Business intelligence generation from conversation data

This is the core AI/ML component that makes the EA truly intelligent about business.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum

import numpy as np
from sentence_transformers import SentenceTransformer
import spacy

logger = logging.getLogger(__name__)


class BusinessEntityType(Enum):
    COMPANY_NAME = "company_name"
    INDUSTRY = "industry"
    PROCESS = "process"
    TOOL_INTEGRATION = "tool_integration"
    PAIN_POINT = "pain_point"
    AUTOMATION_OPPORTUNITY = "automation_opportunity"
    FREQUENCY = "frequency"
    TIME_DURATION = "time_duration"
    FINANCIAL_METRIC = "financial_metric"
    TEAM_SIZE = "team_size"


@dataclass
class BusinessEntity:
    """Structured business entity extracted from conversations"""
    entity_type: BusinessEntityType
    value: str
    confidence: float
    context: str
    position: Tuple[int, int]  # Start and end positions in text
    metadata: Dict[str, Any]


@dataclass
class BusinessPattern:
    """Identified business pattern with automation potential"""
    pattern_type: str
    description: str
    confidence: float
    automation_score: float
    frequency_indicators: List[str]
    complexity_score: float
    template_matches: List[str]
    extracted_entities: List[BusinessEntity]
    supporting_evidence: List[str]


class BusinessLearningEngine:
    """
    Advanced AI/ML engine for extracting business insights from conversations.
    
    Uses NLP, pattern matching, and semantic analysis to understand:
    - Business processes and workflows
    - Pain points and inefficiencies  
    - Automation opportunities
    - Tool integration possibilities
    - Business goals and priorities
    """
    
    def __init__(self, model_config: Optional[Dict[str, Any]] = None):
        """
        Initialize business learning engine.
        
        Args:
            model_config: Configuration for AI/ML models
        """
        self.config = model_config or self._default_config()
        
        # Initialize NLP models
        self.sentence_transformer = None
        self.nlp_model = None
        self._model_initialized = False
        
        # Business pattern templates
        self.business_patterns = self._load_business_patterns()
        self.automation_templates = self._load_automation_templates()
        
        # Performance tracking
        self.processing_stats = {
            "conversations_processed": 0,
            "patterns_identified": 0,
            "entities_extracted": 0,
            "average_processing_time": 0.0
        }
        
        logger.info("Initialized Business Learning Engine")
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration for business learning"""
        return {
            "sentence_transformer_model": "all-MiniLM-L6-v2",
            "spacy_model": "en_core_web_sm", 
            "confidence_threshold": 0.7,
            "automation_threshold": 0.6,
            "similarity_threshold": 0.8,
            "max_entities_per_conversation": 50,
            "enable_gpu": False,
            "cache_embeddings": True
        }
    
    async def initialize_models(self) -> None:
        """Initialize AI/ML models (async to avoid blocking)"""
        if self._model_initialized:
            return
        
        try:
            # Initialize sentence transformer for semantic similarity
            self.sentence_transformer = SentenceTransformer(
                self.config["sentence_transformer_model"]
            )
            
            # Initialize spaCy for NER and linguistic analysis
            self.nlp_model = spacy.load(self.config["spacy_model"])
            
            self._model_initialized = True
            logger.info("AI/ML models initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI/ML models: {e}")
            # Fallback to simplified processing without advanced models
            self._model_initialized = False
    
    async def extract_business_insights(self, conversation_text: str, 
                                       conversation_history: List[Dict[str, str]] = None,
                                       context_memories: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract comprehensive business insights from conversation.
        
        Args:
            conversation_text: Current conversation text
            conversation_history: Previous conversation messages
            context_memories: Existing business context from memory
            
        Returns:
            Dictionary with extracted insights, patterns, and recommendations
        """
        start_time = time.time()
        
        try:
            # Ensure models are initialized
            await self.initialize_models()
            
            # Extract business entities
            entities = await self._extract_business_entities(conversation_text)
            
            # Identify business patterns
            patterns = await self._identify_business_patterns(
                conversation_text, entities, context_memories or []
            )
            
            # Calculate automation opportunities
            automation_opportunities = await self._calculate_automation_opportunities(
                patterns, entities, conversation_history or []
            )
            
            # Generate workflow template recommendations
            template_recommendations = await self._recommend_workflow_templates(
                automation_opportunities, entities
            )
            
            # Assess business understanding quality
            understanding_metrics = await self._assess_business_understanding(
                entities, patterns, context_memories or []
            )
            
            # Generate business intelligence insights
            intelligence_insights = await self._generate_business_intelligence(
                entities, patterns, automation_opportunities
            )
            
            processing_time = time.time() - start_time
            
            # Update processing statistics
            self.processing_stats["conversations_processed"] += 1
            self.processing_stats["patterns_identified"] += len(patterns)
            self.processing_stats["entities_extracted"] += len(entities)
            self.processing_stats["average_processing_time"] = (
                (self.processing_stats["average_processing_time"] * 
                 (self.processing_stats["conversations_processed"] - 1) + processing_time) /
                self.processing_stats["conversations_processed"]
            )
            
            insights = {
                "extraction_timestamp": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "processing_successful": True,
                
                # Core extractions
                "business_entities": [asdict(entity) for entity in entities],
                "business_patterns": [asdict(pattern) for pattern in patterns],
                "automation_opportunities": automation_opportunities,
                "template_recommendations": template_recommendations,
                
                # Quality metrics
                "understanding_metrics": understanding_metrics,
                "extraction_confidence": self._calculate_overall_confidence(entities, patterns),
                "business_completeness_score": understanding_metrics["completeness_score"],
                
                # Intelligence insights
                "intelligence_insights": intelligence_insights,
                "priority_actions": intelligence_insights.get("priority_actions", []),
                "risk_factors": intelligence_insights.get("risk_factors", []),
                
                # Processing metadata
                "entities_count": len(entities),
                "patterns_count": len(patterns),
                "high_confidence_insights": len([e for e in entities if e.confidence > 0.8]),
                "ready_for_automation": len([o for o in automation_opportunities if o.get("readiness_score", 0) > 0.8])
            }
            
            logger.info(f"Extracted business insights: {len(entities)} entities, "
                       f"{len(patterns)} patterns, {len(automation_opportunities)} opportunities")
            
            return insights
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Failed to extract business insights: {e}")
            return {
                "extraction_timestamp": datetime.utcnow().isoformat(),
                "processing_time_seconds": processing_time,
                "processing_successful": False,
                "error": str(e),
                "business_entities": [],
                "business_patterns": [],
                "automation_opportunities": []
            }
    
    async def _extract_business_entities(self, text: str) -> List[BusinessEntity]:
        """Extract structured business entities from text using NLP"""
        entities = []
        
        try:
            # Use spaCy for named entity recognition if available
            if self._model_initialized and self.nlp_model:
                doc = self.nlp_model(text)
                
                for ent in doc.ents:
                    if ent.label_ in ["ORG", "PRODUCT", "MONEY", "PERCENT", "DATE", "TIME"]:
                        entity = BusinessEntity(
                            entity_type=self._map_spacy_label_to_business_type(ent.label_),
                            value=ent.text,
                            confidence=0.8,  # spaCy confidence (simplified)
                            context=text[max(0, ent.start_char - 50):ent.end_char + 50],
                            position=(ent.start_char, ent.end_char),
                            metadata={"spacy_label": ent.label_, "source": "spacy_ner"}
                        )
                        entities.append(entity)
            
            # Rule-based entity extraction for business-specific patterns
            business_entities = await self._extract_business_entities_rules(text)
            entities.extend(business_entities)
            
            # Deduplicate and sort by confidence
            entities = self._deduplicate_entities(entities)
            entities.sort(key=lambda x: x.confidence, reverse=True)
            
            return entities[:self.config["max_entities_per_conversation"]]
            
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []
    
    async def _extract_business_entities_rules(self, text: str) -> List[BusinessEntity]:
        """Rule-based extraction of business-specific entities"""
        entities = []
        text_lower = text.lower()
        
        # Process patterns
        process_patterns = [
            (r"every\s+(?:day|week|month)", "daily/weekly/monthly process", BusinessEntityType.FREQUENCY),
            (r"takes?\s+(\d+)\s+(?:hours?|minutes?|days?)", "time duration", BusinessEntityType.TIME_DURATION),
            (r"manually\s+\w+", "manual process", BusinessEntityType.PROCESS),
            (r"automate?\s+\w+", "automation opportunity", BusinessEntityType.AUTOMATION_OPPORTUNITY)
        ]
        
        for pattern, description, entity_type in process_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                start, end = match.span()
                entity = BusinessEntity(
                    entity_type=entity_type,
                    value=text[start:end],
                    confidence=0.7,
                    context=text[max(0, start - 30):end + 30],
                    position=(start, end),
                    metadata={"pattern": pattern, "description": description}
                )
                entities.append(entity)
        
        # Tool integration patterns
        tools = [
            "excel", "google sheets", "slack", "email", "trello", "asana", 
            "salesforce", "hubspot", "mailchimp", "instagram", "facebook",
            "twitter", "linkedin", "quickbooks", "shopify", "wordpress"
        ]
        
        for tool in tools:
            if tool in text_lower:
                start_idx = text_lower.index(tool)
                entity = BusinessEntity(
                    entity_type=BusinessEntityType.TOOL_INTEGRATION,
                    value=tool,
                    confidence=0.9,
                    context=text[max(0, start_idx - 30):start_idx + len(tool) + 30],
                    position=(start_idx, start_idx + len(tool)),
                    metadata={"tool_category": self._get_tool_category(tool)}
                )
                entities.append(entity)
        
        # Financial metrics
        financial_patterns = [
            (r"\$\d+(?:,\d+)*(?:\.\d{2})?", "financial_amount"),
            (r"\d+%\s+(?:growth|increase|decrease)", "percentage_metric"),
            (r"revenue|profit|cost|expense", "financial_term")
        ]
        
        for pattern, description in financial_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                start, end = match.span()
                entity = BusinessEntity(
                    entity_type=BusinessEntityType.FINANCIAL_METRIC,
                    value=text[start:end],
                    confidence=0.8,
                    context=text[max(0, start - 30):end + 30],
                    position=(start, end),
                    metadata={"metric_type": description}
                )
                entities.append(entity)
        
        return entities
    
    def _map_spacy_label_to_business_type(self, spacy_label: str) -> BusinessEntityType:
        """Map spaCy entity labels to business entity types"""
        mapping = {
            "ORG": BusinessEntityType.COMPANY_NAME,
            "PRODUCT": BusinessEntityType.TOOL_INTEGRATION,
            "MONEY": BusinessEntityType.FINANCIAL_METRIC,
            "PERCENT": BusinessEntityType.FINANCIAL_METRIC,
            "DATE": BusinessEntityType.FREQUENCY,
            "TIME": BusinessEntityType.TIME_DURATION
        }
        return mapping.get(spacy_label, BusinessEntityType.PROCESS)
    
    def _get_tool_category(self, tool: str) -> str:
        """Get category for business tool"""
        categories = {
            "excel": "spreadsheet", "google sheets": "spreadsheet",
            "slack": "communication", "email": "communication",
            "trello": "project_management", "asana": "project_management",
            "salesforce": "crm", "hubspot": "crm",
            "mailchimp": "email_marketing",
            "instagram": "social_media", "facebook": "social_media", 
            "twitter": "social_media", "linkedin": "social_media",
            "quickbooks": "accounting", "shopify": "ecommerce",
            "wordpress": "website"
        }
        return categories.get(tool, "business_tool")
    
    def _deduplicate_entities(self, entities: List[BusinessEntity]) -> List[BusinessEntity]:
        """Remove duplicate entities based on value and type"""
        seen = set()
        unique_entities = []
        
        for entity in entities:
            key = (entity.entity_type, entity.value.lower())
            if key not in seen:
                seen.add(key)
                unique_entities.append(entity)
        
        return unique_entities
    
    async def _identify_business_patterns(self, text: str, entities: List[BusinessEntity], 
                                        context_memories: List[Dict[str, Any]]) -> List[BusinessPattern]:
        """Identify business patterns that indicate automation opportunities"""
        patterns = []
        
        try:
            # Frequency-based patterns (daily, weekly processes)
            frequency_patterns = await self._identify_frequency_patterns(text, entities)
            patterns.extend(frequency_patterns)
            
            # Pain point patterns (inefficient, manual, time-consuming)
            pain_patterns = await self._identify_pain_point_patterns(text, entities)
            patterns.extend(pain_patterns)
            
            # Tool integration patterns
            integration_patterns = await self._identify_integration_patterns(text, entities)
            patterns.extend(integration_patterns)
            
            # Workflow patterns (sequential processes)
            workflow_patterns = await self._identify_workflow_patterns(text, entities)
            patterns.extend(workflow_patterns)
            
            # Context-aware patterns (based on previous conversations)
            context_patterns = await self._identify_context_patterns(text, entities, context_memories)
            patterns.extend(context_patterns)
            
            # Score and sort patterns
            patterns = await self._score_and_rank_patterns(patterns)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Pattern identification failed: {e}")
            return []
    
    async def _identify_frequency_patterns(self, text: str, entities: List[BusinessEntity]) -> List[BusinessPattern]:
        """Identify patterns with frequency indicators (daily, weekly, etc.)"""
        patterns = []
        text_lower = text.lower()
        
        frequency_indicators = ["daily", "weekly", "monthly", "every day", "each week", "regularly"]
        
        for indicator in frequency_indicators:
            if indicator in text_lower:
                # Find context around frequency indicator
                start_idx = text_lower.index(indicator)
                context_start = max(0, start_idx - 100)
                context_end = min(len(text), start_idx + len(indicator) + 100)
                context = text[context_start:context_end]
                
                # Extract related entities
                related_entities = [
                    e for e in entities 
                    if context_start <= e.position[0] <= context_end or context_start <= e.position[1] <= context_end
                ]
                
                pattern = BusinessPattern(
                    pattern_type="frequency_process",
                    description=f"Regular process with {indicator} frequency: {context}",
                    confidence=0.8,
                    automation_score=0.9,  # High automation potential for regular processes
                    frequency_indicators=[indicator],
                    complexity_score=0.3,  # Regular processes are typically simple to automate
                    template_matches=["scheduled_automation", "recurring_workflow"],
                    extracted_entities=related_entities,
                    supporting_evidence=[f"Frequency indicator: {indicator}", f"Context: {context[:50]}..."]
                )
                patterns.append(pattern)
        
        return patterns
    
    async def _identify_pain_point_patterns(self, text: str, entities: List[BusinessEntity]) -> List[BusinessPattern]:
        """Identify pain points that suggest automation opportunities"""
        patterns = []
        text_lower = text.lower()
        
        pain_indicators = [
            ("takes too long", 0.9, "time_inefficiency"),
            ("waste time", 0.9, "time_waste"),
            ("manually", 0.8, "manual_process"),
            ("repetitive", 0.8, "repetitive_task"),
            ("boring", 0.6, "monotonous_work"),
            ("error prone", 0.9, "error_risk"),
            ("frustrating", 0.7, "workflow_frustration")
        ]
        
        for indicator, confidence, pain_type in pain_indicators:
            if indicator in text_lower:
                start_idx = text_lower.index(indicator)
                context = text[max(0, start_idx - 80):start_idx + len(indicator) + 80]
                
                related_entities = [
                    e for e in entities 
                    if abs(e.position[0] - start_idx) < 100
                ]
                
                pattern = BusinessPattern(
                    pattern_type="pain_point",
                    description=f"Pain point identified: {pain_type} - {context}",
                    confidence=confidence,
                    automation_score=0.8,  # Pain points often indicate good automation candidates
                    frequency_indicators=[],
                    complexity_score=0.5,
                    template_matches=self._get_pain_point_templates(pain_type),
                    extracted_entities=related_entities,
                    supporting_evidence=[f"Pain indicator: {indicator}", f"Type: {pain_type}"]
                )
                patterns.append(pattern)
        
        return patterns
    
    def _get_pain_point_templates(self, pain_type: str) -> List[str]:
        """Get workflow templates that address specific pain points"""
        template_map = {
            "time_inefficiency": ["time_optimizer", "process_accelerator"],
            "manual_process": ["automation_workflow", "manual_eliminator"], 
            "repetitive_task": ["task_scheduler", "batch_processor"],
            "error_risk": ["validation_workflow", "error_checker"],
            "workflow_frustration": ["process_improver", "ux_optimizer"]
        }
        return template_map.get(pain_type, ["generic_automation"])
    
    async def _identify_integration_patterns(self, text: str, entities: List[BusinessEntity]) -> List[BusinessPattern]:
        """Identify tool integration patterns"""
        patterns = []
        
        # Find tool entities
        tool_entities = [e for e in entities if e.entity_type == BusinessEntityType.TOOL_INTEGRATION]
        
        if len(tool_entities) >= 2:
            # Multiple tools suggest integration opportunities
            tool_names = [e.value for e in tool_entities]
            pattern = BusinessPattern(
                pattern_type="tool_integration",
                description=f"Multiple tools identified for integration: {', '.join(tool_names)}",
                confidence=0.7,
                automation_score=0.8,
                frequency_indicators=[],
                complexity_score=0.6,  # Integration can be moderately complex
                template_matches=["app_connector", "data_sync", "multi_tool_workflow"],
                extracted_entities=tool_entities,
                supporting_evidence=[f"Tools: {tool_names}"]
            )
            patterns.append(pattern)
        
        return patterns
    
    async def _identify_workflow_patterns(self, text: str, entities: List[BusinessEntity]) -> List[BusinessPattern]:
        """Identify sequential workflow patterns"""
        patterns = []
        text_lower = text.lower()
        
        workflow_indicators = [
            "step by step", "first", "then", "next", "finally", "process", "workflow",
            "after that", "following", "sequence"
        ]
        
        workflow_count = sum(1 for indicator in workflow_indicators if indicator in text_lower)
        
        if workflow_count >= 2:  # Multiple workflow indicators suggest a process
            pattern = BusinessPattern(
                pattern_type="sequential_workflow",
                description=f"Sequential workflow pattern detected with {workflow_count} indicators",
                confidence=0.7,
                automation_score=0.8,
                frequency_indicators=[],
                complexity_score=0.7,  # Sequential workflows can be complex
                template_matches=["process_automation", "sequential_workflow", "step_by_step_automation"],
                extracted_entities=entities,
                supporting_evidence=[f"Workflow indicators: {workflow_count}"]
            )
            patterns.append(pattern)
        
        return patterns
    
    async def _identify_context_patterns(self, text: str, entities: List[BusinessEntity], 
                                       context_memories: List[Dict[str, Any]]) -> List[BusinessPattern]:
        """Identify patterns based on conversation context and memory"""
        patterns = []
        
        if not context_memories:
            return patterns
        
        # Semantic similarity matching if sentence transformer is available
        if self._model_initialized and self.sentence_transformer:
            try:
                # Get embeddings for current text
                current_embedding = self.sentence_transformer.encode([text])
                
                # Compare with context memories
                for memory in context_memories:
                    memory_text = memory.get("memory", "")
                    if memory_text:
                        memory_embedding = self.sentence_transformer.encode([memory_text])
                        similarity = np.dot(current_embedding[0], memory_embedding[0]) / (
                            np.linalg.norm(current_embedding[0]) * np.linalg.norm(memory_embedding[0])
                        )
                        
                        if similarity > self.config["similarity_threshold"]:
                            pattern = BusinessPattern(
                                pattern_type="context_similarity",
                                description=f"Similar pattern to previous conversation (similarity: {similarity:.2f})",
                                confidence=similarity,
                                automation_score=0.7,
                                frequency_indicators=[],
                                complexity_score=0.4,
                                template_matches=["similar_process_automation"],
                                extracted_entities=entities,
                                supporting_evidence=[f"Similar to: {memory_text[:100]}..."]
                            )
                            patterns.append(pattern)
                            
            except Exception as e:
                logger.error(f"Context pattern matching failed: {e}")
        
        return patterns
    
    async def _score_and_rank_patterns(self, patterns: List[BusinessPattern]) -> List[BusinessPattern]:
        """Score and rank patterns by automation potential"""
        for pattern in patterns:
            # Calculate composite score
            composite_score = (
                pattern.confidence * 0.3 +
                pattern.automation_score * 0.4 +
                (1 - pattern.complexity_score) * 0.2 +  # Lower complexity = higher score
                len(pattern.supporting_evidence) * 0.1
            )
            pattern.metadata = {"composite_score": composite_score}
        
        # Sort by composite score
        patterns.sort(key=lambda p: p.metadata.get("composite_score", 0), reverse=True)
        return patterns
    
    async def _calculate_automation_opportunities(self, patterns: List[BusinessPattern],
                                                entities: List[BusinessEntity],
                                                conversation_history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Calculate specific automation opportunities from patterns"""
        opportunities = []
        
        for pattern in patterns:
            if pattern.automation_score >= self.config["automation_threshold"]:
                opportunity = {
                    "id": f"opportunity_{len(opportunities)}_{int(time.time())}",
                    "title": self._generate_opportunity_title(pattern),
                    "description": pattern.description,
                    "pattern_type": pattern.pattern_type,
                    "automation_score": pattern.automation_score,
                    "confidence": pattern.confidence,
                    "complexity": pattern.complexity_score,
                    "readiness_score": self._calculate_readiness_score(pattern, entities),
                    "estimated_impact": self._estimate_automation_impact(pattern),
                    "implementation_effort": self._estimate_implementation_effort(pattern),
                    "template_recommendations": pattern.template_matches,
                    "related_entities": [asdict(e) for e in pattern.extracted_entities],
                    "supporting_evidence": pattern.supporting_evidence,
                    "priority": self._calculate_opportunity_priority(pattern)
                }
                opportunities.append(opportunity)
        
        return sorted(opportunities, key=lambda x: x["readiness_score"], reverse=True)
    
    def _generate_opportunity_title(self, pattern: BusinessPattern) -> str:
        """Generate a human-readable title for automation opportunity"""
        titles = {
            "frequency_process": "Automate Regular Process",
            "pain_point": "Eliminate Process Inefficiency",
            "tool_integration": "Integrate Business Tools",
            "sequential_workflow": "Automate Sequential Workflow",
            "context_similarity": "Apply Similar Automation"
        }
        return titles.get(pattern.pattern_type, "Business Process Automation")
    
    def _calculate_readiness_score(self, pattern: BusinessPattern, entities: List[BusinessEntity]) -> float:
        """Calculate how ready the opportunity is for implementation"""
        readiness_factors = [
            pattern.confidence * 0.3,
            pattern.automation_score * 0.3,
            (1 - pattern.complexity_score) * 0.2,
            min(len(pattern.extracted_entities) / 3, 1.0) * 0.1,  # More entities = better understanding
            min(len(pattern.template_matches) / 2, 1.0) * 0.1     # Template availability
        ]
        return sum(readiness_factors)
    
    def _estimate_automation_impact(self, pattern: BusinessPattern) -> Dict[str, Any]:
        """Estimate the impact of implementing this automation"""
        impact_indicators = {
            "time_savings": "medium",
            "error_reduction": "low",
            "cost_savings": "medium",
            "scalability": "high"
        }
        
        # Adjust based on pattern type and characteristics
        if "frequency" in pattern.pattern_type:
            impact_indicators["time_savings"] = "high"
        if "pain_point" in pattern.pattern_type:
            impact_indicators["error_reduction"] = "high"
        if "integration" in pattern.pattern_type:
            impact_indicators["scalability"] = "high"
        
        return {
            "impact_areas": impact_indicators,
            "overall_impact": "medium",  # Simplified
            "confidence": pattern.confidence
        }
    
    def _estimate_implementation_effort(self, pattern: BusinessPattern) -> Dict[str, Any]:
        """Estimate implementation effort and timeline"""
        if pattern.complexity_score < 0.3:
            effort = {"level": "low", "estimated_hours": "2-4", "timeline": "same day"}
        elif pattern.complexity_score < 0.6:
            effort = {"level": "medium", "estimated_hours": "4-8", "timeline": "1-2 days"}
        else:
            effort = {"level": "high", "estimated_hours": "8-16", "timeline": "3-5 days"}
        
        return effort
    
    def _calculate_opportunity_priority(self, pattern: BusinessPattern) -> str:
        """Calculate priority level for the opportunity"""
        composite_score = pattern.metadata.get("composite_score", 0)
        if composite_score > 0.8:
            return "high"
        elif composite_score > 0.6:
            return "medium"
        else:
            return "low"
    
    async def _recommend_workflow_templates(self, automation_opportunities: List[Dict[str, Any]], 
                                          entities: List[BusinessEntity]) -> List[Dict[str, Any]]:
        """Recommend specific workflow templates based on opportunities"""
        recommendations = []
        
        for opportunity in automation_opportunities:
            if opportunity["readiness_score"] > 0.7:  # High readiness opportunities
                for template in opportunity["template_recommendations"]:
                    recommendation = {
                        "template_id": template,
                        "opportunity_id": opportunity["id"],
                        "match_confidence": opportunity["confidence"],
                        "customization_needed": self._assess_customization_needs(opportunity, template),
                        "setup_complexity": opportunity["implementation_effort"]["level"],
                        "expected_roi": self._estimate_template_roi(opportunity, template),
                        "integration_requirements": self._get_integration_requirements(opportunity, entities)
                    }
                    recommendations.append(recommendation)
        
        return recommendations[:5]  # Top 5 recommendations
    
    def _assess_customization_needs(self, opportunity: Dict[str, Any], template: str) -> List[str]:
        """Assess what customizations are needed for the template"""
        customizations = ["basic_configuration"]
        
        if "integration" in opportunity["pattern_type"]:
            customizations.append("tool_connections")
        if opportunity["complexity"] > 0.5:
            customizations.append("workflow_logic")
        
        return customizations
    
    def _estimate_template_roi(self, opportunity: Dict[str, Any], template: str) -> Dict[str, Any]:
        """Estimate ROI for implementing this template"""
        return {
            "payback_period": "2-4 weeks",  # Simplified
            "time_saved_per_week": "2-6 hours",
            "efficiency_gain": f"{int(opportunity['automation_score'] * 100)}%"
        }
    
    def _get_integration_requirements(self, opportunity: Dict[str, Any], 
                                    entities: List[BusinessEntity]) -> List[str]:
        """Get integration requirements for the opportunity"""
        requirements = []
        
        tool_entities = [e for e in entities if e.entity_type == BusinessEntityType.TOOL_INTEGRATION]
        for entity in tool_entities:
            requirements.append(f"{entity.value}_integration")
        
        return requirements
    
    async def _assess_business_understanding(self, entities: List[BusinessEntity],
                                          patterns: List[BusinessPattern],
                                          context_memories: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess the quality and completeness of business understanding"""
        
        # Entity coverage assessment
        entity_types_found = set(e.entity_type for e in entities)
        expected_entity_types = set(BusinessEntityType)
        coverage_score = len(entity_types_found) / len(expected_entity_types)
        
        # Confidence distribution
        high_confidence_entities = [e for e in entities if e.confidence > 0.8]
        medium_confidence_entities = [e for e in entities if 0.6 <= e.confidence <= 0.8]
        low_confidence_entities = [e for e in entities if e.confidence < 0.6]
        
        # Pattern quality
        high_automation_patterns = [p for p in patterns if p.automation_score > 0.8]
        
        return {
            "completeness_score": coverage_score,
            "confidence_distribution": {
                "high": len(high_confidence_entities),
                "medium": len(medium_confidence_entities), 
                "low": len(low_confidence_entities)
            },
            "entity_coverage": {
                "found_types": len(entity_types_found),
                "total_types": len(expected_entity_types),
                "missing_types": list(expected_entity_types - entity_types_found)
            },
            "automation_readiness": {
                "high_potential_patterns": len(high_automation_patterns),
                "total_patterns": len(patterns),
                "readiness_ratio": len(high_automation_patterns) / len(patterns) if patterns else 0
            },
            "memory_context_utilization": len(context_memories)
        }
    
    async def _generate_business_intelligence(self, entities: List[BusinessEntity],
                                            patterns: List[BusinessPattern],
                                            automation_opportunities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate high-level business intelligence insights"""
        
        # Business maturity assessment
        tool_count = len([e for e in entities if e.entity_type == BusinessEntityType.TOOL_INTEGRATION])
        process_count = len([e for e in entities if e.entity_type == BusinessEntityType.PROCESS])
        automation_maturity = "low" if tool_count < 3 else "medium" if tool_count < 6 else "high"
        
        # Priority actions
        priority_actions = []
        if len(automation_opportunities) > 0:
            top_opportunity = max(automation_opportunities, key=lambda x: x["readiness_score"])
            priority_actions.append(f"Implement {top_opportunity['title'].lower()}")
        
        if tool_count > 3:
            priority_actions.append("Consider tool consolidation and integration")
        
        # Risk factors
        risk_factors = []
        if len([e for e in entities if e.entity_type == BusinessEntityType.PAIN_POINT]) > 3:
            risk_factors.append("Multiple process inefficiencies detected")
        
        return {
            "business_maturity": {
                "automation_level": automation_maturity,
                "tool_ecosystem_size": tool_count,
                "process_complexity": process_count
            },
            "priority_actions": priority_actions,
            "risk_factors": risk_factors,
            "optimization_potential": {
                "automation_opportunities": len(automation_opportunities),
                "high_impact_opportunities": len([o for o in automation_opportunities if o.get("priority") == "high"])
            }
        }
    
    def _calculate_overall_confidence(self, entities: List[BusinessEntity], 
                                    patterns: List[BusinessPattern]) -> float:
        """Calculate overall confidence in business understanding"""
        if not entities and not patterns:
            return 0.0
        
        entity_confidences = [e.confidence for e in entities] if entities else [0.0]
        pattern_confidences = [p.confidence for p in patterns] if patterns else [0.0]
        
        all_confidences = entity_confidences + pattern_confidences
        return sum(all_confidences) / len(all_confidences)
    
    def _load_business_patterns(self) -> Dict[str, Any]:
        """Load business pattern templates (simplified implementation)"""
        return {
            "frequency_patterns": ["daily", "weekly", "monthly", "regularly"],
            "pain_point_patterns": ["manually", "takes too long", "repetitive", "error prone"],
            "integration_patterns": ["excel", "email", "slack", "trello", "salesforce"],
            "workflow_patterns": ["first", "then", "next", "finally", "process"]
        }
    
    def _load_automation_templates(self) -> Dict[str, Any]:
        """Load automation template configurations (simplified implementation)"""
        return {
            "scheduled_automation": {"complexity": 0.3, "impact": "high"},
            "tool_integration": {"complexity": 0.6, "impact": "medium"},
            "data_sync": {"complexity": 0.4, "impact": "medium"},
            "process_automation": {"complexity": 0.7, "impact": "high"}
        }
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics for monitoring"""
        return {
            "stats_timestamp": datetime.utcnow().isoformat(),
            **self.processing_stats,
            "model_initialized": self._model_initialized,
            "config": self.config
        }