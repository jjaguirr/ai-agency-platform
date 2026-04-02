"""
Real Business Intelligence Validator - Semantic Assessment
Replaces mock evaluation with actual AI-powered business logic validation
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import re

import openai
from openai import OpenAI

from .evaluation_schemas import (
    BusinessUnderstandingAssessment,
    AutomationOpportunityAssessment, 
    IndustryKnowledgeAssessment,
    EvaluationConfidence,
    BusinessMaturity,
    AutomationPriority
)

logger = logging.getLogger(__name__)


class RealBusinessIntelligenceValidator:
    """
    Real AI-powered validator for business intelligence and automation recommendations.
    
    Replaces mock evaluation with semantic understanding using OpenAI API.
    Validates:
    - Business context comprehension
    - Industry-specific knowledge
    - Automation opportunity identification
    - Business logic accuracy
    """
    
    def __init__(self, openai_client: Optional[OpenAI] = None, model: str = "gpt-4o-mini"):
        """
        Initialize validator with OpenAI client.
        
        Args:
            openai_client: OpenAI client instance
            model: Model to use for evaluation
        """
        self.client = openai_client or OpenAI()
        self.model = model
        
        # Industry knowledge base for validation
        self.industry_patterns = self._load_industry_patterns()
        self.business_metrics = self._load_business_metrics()
        
        logger.info(f"Initialized RealBusinessIntelligenceValidator with model: {model}")
    
    async def validate_business_understanding(self, 
                                            business_description: str,
                                            ea_response: str,
                                            conversation_history: Optional[List[Dict[str, str]]] = None) -> BusinessUnderstandingAssessment:
        """
        Validate EA's understanding of business context through semantic analysis.
        
        Args:
            business_description: Customer's business description
            ea_response: EA's response to analyze
            conversation_history: Previous conversation context
            
        Returns:
            BusinessUnderstandingAssessment with detailed analysis
        """
        start_time = time.time()
        
        try:
            # Create comprehensive prompt for business understanding evaluation
            evaluation_prompt = self._create_business_understanding_prompt(
                business_description, ea_response, conversation_history
            )
            
            # Get AI evaluation
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert business analyst evaluating AI assistant comprehension of business contexts."},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent evaluation
                max_tokens=1500
            )
            
            evaluation_text = response.choices[0].message.content
            
            # Parse structured evaluation results
            assessment = self._parse_business_understanding_response(evaluation_text)
            
            # Add metadata
            evaluation_time = int((time.time() - start_time) * 1000)
            assessment.timestamp = datetime.utcnow().isoformat()
            assessment.evaluation_time_ms = evaluation_time
            
            # Extract business entities using AI
            key_entities = await self._extract_business_entities_ai(business_description)
            assessment.key_business_entities = key_entities
            
            # Assess business maturity
            assessment.business_maturity_assessment = self._assess_business_maturity(business_description)
            
            logger.info(f"Business understanding validation completed in {evaluation_time}ms")
            return assessment
            
        except Exception as e:
            logger.error(f"Business understanding validation failed: {e}")
            return self._create_fallback_business_assessment(str(e))
    
    async def validate_automation_opportunities(self,
                                              business_context: str,
                                              ea_recommendations: str,
                                              pain_points: List[str] = None) -> AutomationOpportunityAssessment:
        """
        Validate quality and accuracy of automation opportunity identification.
        
        Args:
            business_context: Business description and context
            ea_recommendations: EA's automation recommendations
            pain_points: Stated pain points from customer
            
        Returns:
            AutomationOpportunityAssessment with detailed analysis
        """
        start_time = time.time()
        
        try:
            # Create automation evaluation prompt
            evaluation_prompt = self._create_automation_evaluation_prompt(
                business_context, ea_recommendations, pain_points or []
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert business process consultant evaluating automation recommendations."},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            evaluation_text = response.choices[0].message.content
            assessment = self._parse_automation_assessment_response(evaluation_text)
            
            # Add metadata
            evaluation_time = int((time.time() - start_time) * 1000)
            assessment.timestamp = datetime.utcnow().isoformat()
            assessment.evaluation_time_ms = evaluation_time
            
            logger.info(f"Automation opportunity validation completed in {evaluation_time}ms")
            return assessment
            
        except Exception as e:
            logger.error(f"Automation opportunity validation failed: {e}")
            return self._create_fallback_automation_assessment(str(e))
    
    async def validate_industry_knowledge(self,
                                        industry: str,
                                        ea_response: str,
                                        business_context: str) -> IndustryKnowledgeAssessment:
        """
        Validate EA's demonstration of industry-specific knowledge.
        
        Args:
            industry: Industry to validate knowledge for
            ea_response: EA's response to analyze
            business_context: Business context for validation
            
        Returns:
            IndustryKnowledgeAssessment with detailed analysis
        """
        start_time = time.time()
        
        try:
            # Get industry-specific validation criteria
            industry_criteria = self.industry_patterns.get(industry.lower(), {})
            
            # Create industry knowledge evaluation prompt
            evaluation_prompt = self._create_industry_knowledge_prompt(
                industry, ea_response, business_context, industry_criteria
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"You are an expert in the {industry} industry evaluating AI assistant knowledge."},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.1,
                max_tokens=1500
            )
            
            evaluation_text = response.choices[0].message.content
            assessment = self._parse_industry_knowledge_response(evaluation_text, industry)
            
            # Add metadata
            evaluation_time = int((time.time() - start_time) * 1000)
            assessment.timestamp = datetime.utcnow().isoformat()
            assessment.evaluation_time_ms = evaluation_time
            
            logger.info(f"Industry knowledge validation for {industry} completed in {evaluation_time}ms")
            return assessment
            
        except Exception as e:
            logger.error(f"Industry knowledge validation failed: {e}")
            return self._create_fallback_industry_assessment(industry, str(e))
    
    def _create_business_understanding_prompt(self, 
                                            business_description: str,
                                            ea_response: str, 
                                            conversation_history: Optional[List[Dict[str, str]]]) -> str:
        """Create comprehensive prompt for business understanding evaluation"""
        
        history_context = ""
        if conversation_history:
            history_context = "\n\nConversation History:\n"
            for i, msg in enumerate(conversation_history[-3:]):  # Last 3 messages for context
                history_context += f"{msg.get('role', 'unknown')}: {msg.get('content', '')}\n"
        
        return f"""
Evaluate the AI Executive Assistant's understanding of the customer's business based on this interaction:

CUSTOMER'S BUSINESS DESCRIPTION:
{business_description}

EA'S RESPONSE:
{ea_response}
{history_context}

Please evaluate the EA's business understanding across these dimensions:

1. BUSINESS TYPE IDENTIFICATION:
   - Did the EA correctly identify the type of business (e-commerce, consulting, etc.)?
   - Score: Yes/No and confidence level

2. INDUSTRY KNOWLEDGE:
   - Does the EA demonstrate understanding of industry-specific challenges?
   - Are industry-relevant terms and concepts used appropriately?
   - Score: Yes/No with examples

3. PAIN POINTS UNDERSTANDING:
   - Which specific pain points did the EA identify from the description?
   - Are these accurate and complete based on what the customer shared?
   - List identified pain points

4. BUSINESS GOALS RECOGNITION:
   - What business goals or objectives did the EA recognize?
   - Are these reasonable inferences from the customer's description?
   - List recognized goals

5. CONTEXT RETENTION:
   - How well does the EA maintain and reference the business context?
   - Scale 0-1 where 1 is perfect retention

6. MISSING UNDERSTANDING:
   - What critical aspects of the business did the EA miss or misunderstand?
   - List gaps in understanding

Please provide your evaluation in this format:
BUSINESS_TYPE_IDENTIFIED: [Yes/No]
INDUSTRY_KNOWLEDGE_DEMONSTRATED: [Yes/No] 
PAIN_POINTS_UNDERSTOOD: [comma-separated list]
BUSINESS_GOALS_RECOGNIZED: [comma-separated list]
CONTEXT_RETENTION_SCORE: [0.0-1.0]
MISSING_CRITICAL_UNDERSTANDING: [comma-separated list]
OVERALL_SCORE: [0.0-1.0]
CONFIDENCE: [low/medium/high]
PASSED: [true/false]
REASONING: [detailed explanation]
"""
    
    def _create_automation_evaluation_prompt(self,
                                           business_context: str,
                                           ea_recommendations: str,
                                           pain_points: List[str]) -> str:
        """Create prompt for automation opportunity evaluation"""
        
        pain_points_text = "\n".join([f"- {point}" for point in pain_points]) if pain_points else "None explicitly stated"
        
        return f"""
Evaluate the quality and accuracy of automation recommendations provided by an AI Executive Assistant:

BUSINESS CONTEXT:
{business_context}

STATED PAIN POINTS:
{pain_points_text}

EA'S AUTOMATION RECOMMENDATIONS:
{ea_recommendations}

Please evaluate the automation recommendations across these dimensions:

1. OPPORTUNITY IDENTIFICATION:
   - List all automation opportunities mentioned by the EA
   - Rate the relevance of each opportunity to the stated pain points (0-1)

2. PRIORITIZATION QUALITY:
   - How well are the opportunities prioritized by business impact?
   - Is the prioritization logic sound? (0-1 scale)

3. IMPLEMENTATION FEASIBILITY:
   - Are the recommended automations realistically implementable?
   - Rate overall feasibility (0-1 scale)

4. BUSINESS IMPACT ACCURACY:
   - Are the business impact claims accurate and realistic?
   - Rate accuracy of impact assessment (0-1 scale)

5. OPPORTUNITY CATEGORIZATION:
   - Which recommendations are high priority/quick wins?
   - Which are long-term strategic opportunities?

6. QUALITY ASSESSMENT:
   - Do opportunities directly address stated pain points?
   - Are recommendations industry-appropriate?
   - Is implementation guidance provided?

7. GAPS AND ISSUES:
   - What obvious opportunities were missed?
   - Are any recommendations unrealistic or impractical?

Please provide evaluation in this format:
OPPORTUNITIES_IDENTIFIED: [JSON array of opportunities with relevance scores]
PRIORITIZATION_QUALITY: [0.0-1.0]
IMPLEMENTATION_FEASIBILITY: [0.0-1.0] 
BUSINESS_IMPACT_ACCURACY: [0.0-1.0]
HIGH_PRIORITY_OPPORTUNITIES: [comma-separated list]
QUICK_WINS_IDENTIFIED: [comma-separated list]
LONG_TERM_OPPORTUNITIES: [comma-separated list]
OPPORTUNITIES_MATCH_PAIN_POINTS: [true/false]
INDUSTRY_SPECIFIC_RECOMMENDATIONS: [true/false]
IMPLEMENTATION_GUIDANCE_PROVIDED: [true/false]
MISSED_OPPORTUNITIES: [comma-separated list]
UNREALISTIC_RECOMMENDATIONS: [comma-separated list]
OVERALL_SCORE: [0.0-1.0]
CONFIDENCE: [low/medium/high]
PASSED: [true/false]
REASONING: [detailed explanation]
"""
    
    def _create_industry_knowledge_prompt(self,
                                        industry: str,
                                        ea_response: str,
                                        business_context: str,
                                        industry_criteria: Dict[str, Any]) -> str:
        """Create prompt for industry knowledge evaluation"""
        
        common_tools = ", ".join(industry_criteria.get("common_tools", []))
        typical_processes = ", ".join(industry_criteria.get("typical_processes", []))
        key_terminology = ", ".join(industry_criteria.get("key_terminology", []))
        
        return f"""
Evaluate the AI Executive Assistant's demonstration of {industry} industry knowledge:

INDUSTRY: {industry}
BUSINESS CONTEXT: {business_context}
EA RESPONSE: {ea_response}

Industry-specific evaluation criteria:
- Common tools: {common_tools}
- Typical processes: {typical_processes}  
- Key terminology: {key_terminology}

Please evaluate industry knowledge across these dimensions:

1. TERMINOLOGY USAGE:
   - Does the EA use industry-specific terminology correctly?
   - Examples of correct/incorrect usage?

2. PROCESS UNDERSTANDING:
   - Does the EA understand common {industry} processes?
   - Are process recommendations industry-appropriate?

3. TOOL AWARENESS:
   - Are mentioned tools commonly used in {industry}?
   - Are important industry tools overlooked?

4. REGULATORY CONSIDERATIONS:
   - Are relevant regulatory/compliance issues addressed?
   - Industry-specific requirements mentioned?

5. BENCHMARKS AND INSIGHTS:
   - Are industry benchmarks or best practices referenced?
   - Competitive insights demonstrated?

6. KNOWLEDGE GAPS:
   - What industry knowledge gaps are evident?
   - Incorrect assumptions about the industry?

Please provide evaluation in this format:
INDUSTRY_TERMINOLOGY_USED: [true/false]
COMMON_PROCESSES_UNDERSTOOD: [true/false]
TYPICAL_TOOLS_MENTIONED: [true/false] 
REGULATORY_CONSIDERATIONS: [true/false]
RELEVANT_BENCHMARKS_PROVIDED: [true/false]
COMPETITIVE_INSIGHTS: [true/false]
INDUSTRY_BEST_PRACTICES: [comma-separated list]
KNOWLEDGE_GAPS: [comma-separated list]
INCORRECT_ASSUMPTIONS: [comma-separated list]
OVERALL_SCORE: [0.0-1.0]
CONFIDENCE: [low/medium/high]
PASSED: [true/false]
REASONING: [detailed explanation]
"""
    
    async def _extract_business_entities_ai(self, business_description: str) -> List[Dict[str, Any]]:
        """Extract business entities using AI analysis"""
        
        try:
            prompt = f"""
Extract key business entities from this description:

{business_description}

Identify:
- Company name (if mentioned)
- Industry/sector
- Business processes mentioned
- Tools/systems used
- Pain points/challenges
- Financial metrics (revenue, costs, etc.)
- Team size indicators

Format as JSON array with entity_type, value, and confidence fields.
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800
            )
            
            # Parse JSON response
            entities_text = response.choices[0].message.content
            try:
                entities = json.loads(entities_text)
                return entities if isinstance(entities, list) else []
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return []
    
    def _assess_business_maturity(self, business_description: str) -> BusinessMaturity:
        """Assess business maturity level from description"""
        
        description_lower = business_description.lower()
        
        # Enterprise indicators
        if any(indicator in description_lower for indicator in 
               ["enterprise", "corporation", "500+", "publicly traded", "multinational"]):
            return BusinessMaturity.ENTERPRISE
        
        # Established business indicators  
        if any(indicator in description_lower for indicator in
               ["established", "25+", "multiple locations", "departments", "managers"]):
            return BusinessMaturity.ESTABLISHED
        
        # Growing business indicators
        if any(indicator in description_lower for indicator in
               ["growing", "expanding", "5-25", "hiring", "scaling"]):
            return BusinessMaturity.GROWING
        
        # Default to startup
        return BusinessMaturity.STARTUP
    
    def _parse_business_understanding_response(self, evaluation_text: str) -> BusinessUnderstandingAssessment:
        """Parse AI evaluation response into structured assessment"""
        
        try:
            # Extract structured fields using regex
            patterns = {
                'business_type_identified': r'BUSINESS_TYPE_IDENTIFIED:\s*(\w+)',
                'industry_knowledge_demonstrated': r'INDUSTRY_KNOWLEDGE_DEMONSTRATED:\s*(\w+)',
                'context_retention_score': r'CONTEXT_RETENTION_SCORE:\s*([\d.]+)',
                'overall_score': r'OVERALL_SCORE:\s*([\d.]+)',
                'confidence': r'CONFIDENCE:\s*(\w+)',
                'passed': r'PASSED:\s*(\w+)',
                'reasoning': r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)'
            }
            
            extracted = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
                extracted[key] = match.group(1).strip() if match else None
            
            # Parse list fields
            pain_points = self._extract_list_field(evaluation_text, 'PAIN_POINTS_UNDERSTOOD')
            business_goals = self._extract_list_field(evaluation_text, 'BUSINESS_GOALS_RECOGNIZED')
            missing_understanding = self._extract_list_field(evaluation_text, 'MISSING_CRITICAL_UNDERSTANDING')
            
            return BusinessUnderstandingAssessment(
                passed=extracted.get('passed', '').lower() == 'true',
                confidence=EvaluationConfidence(extracted.get('confidence', 'medium').lower()),
                score=float(extracted.get('overall_score', 0.5)),
                reasoning=extracted.get('reasoning', 'AI evaluation completed'),
                business_type_identified=extracted.get('business_type_identified', '').lower() == 'yes',
                industry_knowledge_demonstrated=extracted.get('industry_knowledge_demonstrated', '').lower() == 'yes',
                pain_points_understood=pain_points,
                business_goals_recognized=business_goals,
                context_retention_score=float(extracted.get('context_retention_score', 0.5)),
                missing_critical_understanding=missing_understanding,
                business_maturity_assessment=BusinessMaturity.STARTUP,  # Will be set by caller
                timestamp="",  # Will be set by caller
                evaluation_time_ms=0  # Will be set by caller
            )
            
        except Exception as e:
            logger.error(f"Failed to parse business understanding response: {e}")
            return self._create_fallback_business_assessment(str(e))
    
    def _parse_automation_assessment_response(self, evaluation_text: str) -> AutomationOpportunityAssessment:
        """Parse automation opportunity evaluation response"""
        
        try:
            # Extract numeric scores
            patterns = {
                'prioritization_quality': r'PRIORITIZATION_QUALITY:\s*([\d.]+)',
                'implementation_feasibility': r'IMPLEMENTATION_FEASIBILITY:\s*([\d.]+)',
                'business_impact_accuracy': r'BUSINESS_IMPACT_ACCURACY:\s*([\d.]+)',
                'overall_score': r'OVERALL_SCORE:\s*([\d.]+)',
                'confidence': r'CONFIDENCE:\s*(\w+)',
                'passed': r'PASSED:\s*(\w+)',
                'reasoning': r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)'
            }
            
            extracted = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
                extracted[key] = match.group(1).strip() if match else None
            
            # Extract boolean fields
            bool_patterns = {
                'opportunities_match_pain_points': r'OPPORTUNITIES_MATCH_PAIN_POINTS:\s*(\w+)',
                'industry_specific_recommendations': r'INDUSTRY_SPECIFIC_RECOMMENDATIONS:\s*(\w+)',
                'implementation_guidance_provided': r'IMPLEMENTATION_GUIDANCE_PROVIDED:\s*(\w+)'
            }
            
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                extracted[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract list fields
            high_priority = self._extract_list_field(evaluation_text, 'HIGH_PRIORITY_OPPORTUNITIES')
            quick_wins = self._extract_list_field(evaluation_text, 'QUICK_WINS_IDENTIFIED')
            long_term = self._extract_list_field(evaluation_text, 'LONG_TERM_OPPORTUNITIES')
            missed = self._extract_list_field(evaluation_text, 'MISSED_OPPORTUNITIES')
            unrealistic = self._extract_list_field(evaluation_text, 'UNREALISTIC_RECOMMENDATIONS')
            
            return AutomationOpportunityAssessment(
                passed=extracted.get('passed', '').lower() == 'true',
                confidence=EvaluationConfidence(extracted.get('confidence', 'medium').lower()),
                score=float(extracted.get('overall_score', 0.5)),
                reasoning=extracted.get('reasoning', 'Automation opportunity evaluation completed'),
                prioritization_quality=float(extracted.get('prioritization_quality', 0.5)),
                implementation_feasibility=float(extracted.get('implementation_feasibility', 0.5)),
                business_impact_accuracy=float(extracted.get('business_impact_accuracy', 0.5)),
                high_priority_opportunities=high_priority,
                quick_wins_identified=quick_wins,
                long_term_opportunities=long_term,
                opportunities_match_pain_points=extracted.get('opportunities_match_pain_points', False),
                industry_specific_recommendations=extracted.get('industry_specific_recommendations', False),
                implementation_guidance_provided=extracted.get('implementation_guidance_provided', False),
                missed_opportunities=missed,
                unrealistic_recommendations=unrealistic,
                timestamp="",  # Will be set by caller
                evaluation_time_ms=0  # Will be set by caller
            )
            
        except Exception as e:
            logger.error(f"Failed to parse automation assessment response: {e}")
            return self._create_fallback_automation_assessment(str(e))
    
    def _parse_industry_knowledge_response(self, evaluation_text: str, industry: str) -> IndustryKnowledgeAssessment:
        """Parse industry knowledge evaluation response"""
        
        try:
            # Extract boolean fields
            bool_patterns = {
                'industry_terminology_used': r'INDUSTRY_TERMINOLOGY_USED:\s*(\w+)',
                'common_processes_understood': r'COMMON_PROCESSES_UNDERSTOOD:\s*(\w+)',
                'typical_tools_mentioned': r'TYPICAL_TOOLS_MENTIONED:\s*(\w+)',
                'regulatory_considerations': r'REGULATORY_CONSIDERATIONS:\s*(\w+)',
                'relevant_benchmarks_provided': r'RELEVANT_BENCHMARKS_PROVIDED:\s*(\w+)',
                'competitive_insights': r'COMPETITIVE_INSIGHTS:\s*(\w+)'
            }
            
            extracted = {}
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                extracted[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract other fields
            other_patterns = {
                'overall_score': r'OVERALL_SCORE:\s*([\d.]+)',
                'confidence': r'CONFIDENCE:\s*(\w+)',
                'passed': r'PASSED:\s*(\w+)',
                'reasoning': r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)'
            }
            
            for key, pattern in other_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
                extracted[key] = match.group(1).strip() if match else None
            
            # Extract list fields
            best_practices = self._extract_list_field(evaluation_text, 'INDUSTRY_BEST_PRACTICES')
            knowledge_gaps = self._extract_list_field(evaluation_text, 'KNOWLEDGE_GAPS')
            incorrect_assumptions = self._extract_list_field(evaluation_text, 'INCORRECT_ASSUMPTIONS')
            
            return IndustryKnowledgeAssessment(
                passed=extracted.get('passed', '').lower() == 'true',
                confidence=EvaluationConfidence(extracted.get('confidence', 'medium').lower()),
                score=float(extracted.get('overall_score', 0.5)),
                reasoning=extracted.get('reasoning', 'Industry knowledge evaluation completed'),
                industry=industry,
                industry_terminology_used=extracted.get('industry_terminology_used', False),
                common_processes_understood=extracted.get('common_processes_understood', False),
                typical_tools_mentioned=extracted.get('typical_tools_mentioned', False),
                regulatory_considerations=extracted.get('regulatory_considerations', False),
                relevant_benchmarks_provided=extracted.get('relevant_benchmarks_provided', False),
                competitive_insights=extracted.get('competitive_insights', False),
                industry_best_practices=best_practices,
                knowledge_gaps=knowledge_gaps,
                incorrect_assumptions=incorrect_assumptions,
                timestamp="",  # Will be set by caller
                evaluation_time_ms=0  # Will be set by caller
            )
            
        except Exception as e:
            logger.error(f"Failed to parse industry knowledge response: {e}")
            return self._create_fallback_industry_assessment(industry, str(e))
    
    def _extract_list_field(self, text: str, field_name: str) -> List[str]:
        """Extract comma-separated list field from evaluation response"""
        
        pattern = rf'{field_name}:\s*(.+?)(?=\n[A-Z_]+:|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            value = match.group(1).strip()
            if value and value.lower() not in ['none', 'n/a', '']:
                return [item.strip() for item in value.split(',') if item.strip()]
        
        return []
    
    def _create_fallback_business_assessment(self, error_message: str) -> BusinessUnderstandingAssessment:
        """Create fallback assessment when evaluation fails"""
        
        return BusinessUnderstandingAssessment(
            passed=False,
            confidence=EvaluationConfidence.LOW,
            score=0.0,
            reasoning=f"Evaluation failed: {error_message}",
            business_type_identified=False,
            industry_knowledge_demonstrated=False,
            pain_points_understood=[],
            business_goals_recognized=[],
            context_retention_score=0.0,
            missing_critical_understanding=["Evaluation system failure"],
            business_maturity_assessment=BusinessMaturity.STARTUP,
            timestamp=datetime.utcnow().isoformat(),
            evaluation_time_ms=0
        )
    
    def _create_fallback_automation_assessment(self, error_message: str) -> AutomationOpportunityAssessment:
        """Create fallback automation assessment when evaluation fails"""
        
        return AutomationOpportunityAssessment(
            passed=False,
            confidence=EvaluationConfidence.LOW,
            score=0.0,
            reasoning=f"Evaluation failed: {error_message}",
            opportunities_identified=[],
            prioritization_quality=0.0,
            implementation_feasibility=0.0,
            business_impact_accuracy=0.0,
            high_priority_opportunities=[],
            quick_wins_identified=[],
            long_term_opportunities=[],
            opportunities_match_pain_points=False,
            industry_specific_recommendations=False,
            implementation_guidance_provided=False,
            missed_opportunities=["Evaluation system failure"],
            unrealistic_recommendations=[],
            timestamp=datetime.utcnow().isoformat(),
            evaluation_time_ms=0
        )
    
    def _create_fallback_industry_assessment(self, industry: str, error_message: str) -> IndustryKnowledgeAssessment:
        """Create fallback industry assessment when evaluation fails"""
        
        return IndustryKnowledgeAssessment(
            passed=False,
            confidence=EvaluationConfidence.LOW,
            score=0.0,
            reasoning=f"Evaluation failed: {error_message}",
            industry=industry,
            industry_terminology_used=False,
            common_processes_understood=False,
            typical_tools_mentioned=False,
            regulatory_considerations=False,
            relevant_benchmarks_provided=False,
            competitive_insights=False,
            industry_best_practices=[],
            knowledge_gaps=["Evaluation system failure"],
            incorrect_assumptions=[],
            timestamp=datetime.utcnow().isoformat(),
            evaluation_time_ms=0
        )
    
    def _load_industry_patterns(self) -> Dict[str, Any]:
        """Load industry-specific patterns and knowledge"""
        
        return {
            "e-commerce": {
                "common_tools": ["shopify", "woocommerce", "magento", "stripe", "paypal", "mailchimp", "klaviyo"],
                "typical_processes": ["inventory management", "order fulfillment", "customer support", "marketing campaigns"],
                "key_terminology": ["conversion rate", "cart abandonment", "upselling", "cross-selling", "churn rate"]
            },
            "jewelry": {
                "common_tools": ["instagram", "facebook", "shopify", "etsy", "pinterest"],
                "typical_processes": ["product photography", "social media marketing", "custom orders", "inventory tracking"],
                "key_terminology": ["handcrafted", "precious metals", "gemstones", "custom jewelry", "artisan"]
            },
            "consulting": {
                "common_tools": ["zoom", "calendly", "hubspot", "salesforce", "slack", "asana"],
                "typical_processes": ["client onboarding", "project management", "proposal writing", "report generation"],
                "key_terminology": ["billable hours", "retainer", "deliverables", "scope creep", "stakeholder management"]
            },
            "real estate": {
                "common_tools": ["mls", "zillow", "realtor.com", "docusign", "transaction management"],
                "typical_processes": ["lead generation", "property marketing", "client communication", "transaction coordination"],
                "key_terminology": ["listings", "showings", "closing", "commission", "market analysis"]
            },
            "professional services": {
                "common_tools": ["microsoft office", "quickbooks", "time tracking", "project management"],
                "typical_processes": ["client intake", "service delivery", "invoicing", "follow-up"],
                "key_terminology": ["professional liability", "client confidentiality", "service agreements"]
            }
        }
    
    def _load_business_metrics(self) -> Dict[str, Any]:
        """Load business metrics and benchmarks"""
        
        return {
            "time_savings_benchmarks": {
                "social_media_automation": {"hours_per_week": 5, "cost_per_hour": 25},
                "invoice_automation": {"hours_per_week": 4, "cost_per_hour": 30},
                "email_automation": {"hours_per_week": 3, "cost_per_hour": 20}
            },
            "roi_thresholds": {
                "excellent": 300,  # 300% ROI
                "good": 150,       # 150% ROI
                "acceptable": 50   # 50% ROI
            }
        }