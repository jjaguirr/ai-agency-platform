"""
Conversation Quality Assessment - Real EA Response Evaluation
Replaces MockLlmJudge with semantic conversation quality analysis
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import re

import openai
from openai import OpenAI

from .evaluation_schemas import (
    ConversationQualityMetrics,
    EvaluationConfidence
)

logger = logging.getLogger(__name__)


class ConversationQualityAssessment:
    """
    Real AI-powered assessment of EA conversation quality.
    
    Replaces MockLlmJudge with semantic evaluation of:
    - Professional communication
    - Relevance and completeness
    - Actionability of recommendations
    - Empathy and understanding
    - Context maintenance
    """
    
    def __init__(self, openai_client: Optional[OpenAI] = None, model: str = "gpt-4o-mini"):
        """
        Initialize conversation quality assessor.
        
        Args:
            openai_client: OpenAI client instance
            model: Model to use for evaluation
        """
        self.client = openai_client or OpenAI()
        self.model = model
        
        # Quality assessment criteria
        self.quality_criteria = self._load_quality_criteria()
        self.professional_standards = self._load_professional_standards()
        
        logger.info(f"Initialized ConversationQualityAssessment with model: {model}")
    
    async def assess_conversation_quality(self,
                                        user_message: str,
                                        ea_response: str,
                                        conversation_context: Optional[List[Dict[str, str]]] = None,
                                        business_context: Optional[str] = None) -> ConversationQualityMetrics:
        """
        Assess overall quality of EA conversation response.
        
        Args:
            user_message: Customer's message
            ea_response: EA's response to evaluate
            conversation_context: Previous conversation messages
            business_context: Business context information
            
        Returns:
            ConversationQualityMetrics with detailed quality assessment
        """
        start_time = time.time()
        
        try:
            # Create comprehensive quality assessment prompt
            evaluation_prompt = self._create_quality_assessment_prompt(
                user_message, ea_response, conversation_context, business_context
            )
            
            # Get AI evaluation
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert conversation analyst evaluating AI assistant communication quality."},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent evaluation
                max_tokens=2000
            )
            
            evaluation_text = response.choices[0].message.content
            
            # Parse structured evaluation results
            assessment = self._parse_quality_assessment_response(evaluation_text)
            
            # Add metadata
            evaluation_time = int((time.time() - start_time) * 1000)
            assessment.timestamp = datetime.utcnow().isoformat()
            assessment.evaluation_time_ms = evaluation_time
            
            logger.info(f"Conversation quality assessment completed in {evaluation_time}ms")
            return assessment
            
        except Exception as e:
            logger.error(f"Conversation quality assessment failed: {e}")
            return self._create_fallback_quality_assessment(str(e))
    
    async def assess_professionalism(self,
                                   ea_response: str,
                                   business_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Assess professionalism of EA response.
        
        Args:
            ea_response: EA's response to evaluate
            business_context: Business context for appropriateness
            
        Returns:
            Dictionary with professionalism assessment
        """
        try:
            prompt = f"""
Evaluate the professionalism of this AI Executive Assistant response:

EA RESPONSE:
{ea_response}

BUSINESS CONTEXT:
{business_context or "General business context"}

Assess professionalism across these dimensions:

1. TONE AND LANGUAGE:
   - Is the tone professional and business-appropriate?
   - Are formal business communication standards met?
   - Any inappropriate casual language?

2. COMMUNICATION CLARITY:
   - Is the message clear and well-structured?
   - Are complex concepts explained appropriately?
   - Is the language accessible but professional?

3. BUSINESS APPROPRIATENESS:
   - Is the response appropriate for a business context?
   - Does it maintain executive assistant standards?
   - Are boundaries maintained appropriately?

4. CONFIDENCE AND COMPETENCE:
   - Does the response demonstrate competence?
   - Is uncertainty handled professionally?
   - Are limitations acknowledged appropriately?

Rate each dimension 0-1 and provide overall professionalism score.

Format:
TONE_AND_LANGUAGE: [0.0-1.0]
COMMUNICATION_CLARITY: [0.0-1.0] 
BUSINESS_APPROPRIATENESS: [0.0-1.0]
CONFIDENCE_AND_COMPETENCE: [0.0-1.0]
OVERALL_PROFESSIONALISM: [0.0-1.0]
ISSUES_IDENTIFIED: [comma-separated list or 'none']
REASONING: [explanation]
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            evaluation_text = response.choices[0].message.content
            return self._parse_professionalism_response(evaluation_text)
            
        except Exception as e:
            logger.error(f"Professionalism assessment failed: {e}")
            return {"overall_professionalism": 0.5, "error": str(e)}
    
    async def assess_relevance_and_completeness(self,
                                              user_message: str,
                                              ea_response: str,
                                              business_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Assess relevance and completeness of EA response to user's needs.
        
        Args:
            user_message: Customer's message/question
            ea_response: EA's response
            business_context: Business context information
            
        Returns:
            Dictionary with relevance and completeness assessment
        """
        try:
            prompt = f"""
Evaluate how well this AI Executive Assistant response addresses the customer's needs:

CUSTOMER MESSAGE:
{user_message}

EA RESPONSE:
{ea_response}

BUSINESS CONTEXT:
{business_context or "General business context"}

Assess across these dimensions:

1. RELEVANCE TO QUESTION:
   - Does the response directly address what the customer asked?
   - Are all aspects of the question covered?
   - Is the response on-topic throughout?

2. COMPLETENESS OF ANSWER:
   - Is the response complete enough to be actionable?
   - Are important details provided?
   - Are next steps clearly outlined?

3. CONTEXTUAL APPROPRIATENESS:
   - Is the response appropriate for the business context?
   - Does it consider the customer's situation?
   - Are recommendations realistic and applicable?

4. VALUE PROVIDED:
   - Does the response provide clear business value?
   - Are insights or recommendations valuable?
   - Would this help the customer achieve their goals?

Rate each dimension 0-1 and identify any gaps.

Format:
RELEVANCE_TO_QUESTION: [0.0-1.0]
COMPLETENESS_OF_ANSWER: [0.0-1.0]
CONTEXTUAL_APPROPRIATENESS: [0.0-1.0] 
VALUE_PROVIDED: [0.0-1.0]
OVERALL_RELEVANCE_COMPLETENESS: [0.0-1.0]
GAPS_IDENTIFIED: [comma-separated list or 'none']
REASONING: [explanation]
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1200
            )
            
            evaluation_text = response.choices[0].message.content
            return self._parse_relevance_completeness_response(evaluation_text)
            
        except Exception as e:
            logger.error(f"Relevance and completeness assessment failed: {e}")
            return {"overall_relevance_completeness": 0.5, "error": str(e)}
    
    async def assess_actionability(self, ea_response: str) -> Dict[str, Any]:
        """
        Assess how actionable the EA's recommendations are.
        
        Args:
            ea_response: EA's response to evaluate
            
        Returns:
            Dictionary with actionability assessment
        """
        try:
            prompt = f"""
Evaluate how actionable this AI Executive Assistant response is:

EA RESPONSE:
{ea_response}

Assess actionability across these dimensions:

1. SPECIFIC RECOMMENDATIONS:
   - Are specific, concrete recommendations provided?
   - Are recommendations clear and unambiguous?
   - Can the customer act on these immediately?

2. IMPLEMENTATION GUIDANCE:
   - Are implementation steps provided?
   - Is the guidance detailed enough to follow?
   - Are resources or tools mentioned?

3. PRIORITIZATION:
   - Are recommendations prioritized by importance/impact?
   - Is there guidance on what to do first?
   - Are quick wins vs long-term actions distinguished?

4. PRACTICAL FEASIBILITY:
   - Are recommendations realistically implementable?
   - Are resource requirements reasonable?
   - Are timelines realistic?

Rate each dimension 0-1 and identify actionable elements.

Format:
SPECIFIC_RECOMMENDATIONS: [0.0-1.0]
IMPLEMENTATION_GUIDANCE: [0.0-1.0]
PRIORITIZATION: [0.0-1.0]
PRACTICAL_FEASIBILITY: [0.0-1.0]
OVERALL_ACTIONABILITY: [0.0-1.0]
ACTIONABLE_ITEMS_COUNT: [number]
NON_ACTIONABLE_CONTENT: [list or 'none']
REASONING: [explanation]
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000
            )
            
            evaluation_text = response.choices[0].message.content
            return self._parse_actionability_response(evaluation_text)
            
        except Exception as e:
            logger.error(f"Actionability assessment failed: {e}")
            return {"overall_actionability": 0.5, "error": str(e)}
    
    def _create_quality_assessment_prompt(self,
                                        user_message: str,
                                        ea_response: str,
                                        conversation_context: Optional[List[Dict[str, str]]],
                                        business_context: Optional[str]) -> str:
        """Create comprehensive quality assessment prompt"""
        
        context_text = ""
        if conversation_context:
            context_text = "\n\nCONVERSATION HISTORY:\n"
            for i, msg in enumerate(conversation_context[-3:]):  # Last 3 messages
                context_text += f"{msg.get('role', 'unknown')}: {msg.get('content', '')}\n"
        
        business_text = f"\n\nBUSINESS CONTEXT:\n{business_context}" if business_context else ""
        
        return f"""
Evaluate the overall quality of this AI Executive Assistant conversation response:

CUSTOMER MESSAGE:
{user_message}

EA RESPONSE:
{ea_response}
{context_text}{business_text}

Please evaluate the conversation quality across these comprehensive dimensions:

1. PROFESSIONALISM (0-1 scale):
   - Professional tone and business-appropriate language
   - Proper executive assistant communication standards
   - Confidence and competence demonstration

2. RELEVANCE (0-1 scale):
   - Direct addressing of customer's question/needs
   - On-topic response throughout
   - Appropriate context consideration

3. COMPLETENESS (0-1 scale):
   - Complete answer to customer's question
   - Sufficient detail for actionability
   - Important considerations covered

4. ACTIONABILITY (0-1 scale):
   - Specific, concrete recommendations provided
   - Clear implementation guidance
   - Practical and feasible suggestions

5. EMPATHY (0-1 scale):
   - Understanding of customer situation
   - Appropriate empathy and support
   - Customer-focused communication

6. CONVERSATION FLOW ANALYSIS:
   - Does the EA maintain context from previous messages?
   - Are clarifying questions asked when appropriate?
   - Are specific solutions provided rather than generic advice?

7. QUALITY ISSUES AND IMPROVEMENTS:
   - Identify specific quality issues
   - Suggest concrete improvements
   - Highlight strengths to maintain

Please provide your evaluation in this format:
PROFESSIONALISM_SCORE: [0.0-1.0]
RELEVANCE_SCORE: [0.0-1.0]
COMPLETENESS_SCORE: [0.0-1.0]
ACTIONABILITY_SCORE: [0.0-1.0]
EMPATHY_SCORE: [0.0-1.0]
MAINTAINS_CONTEXT: [true/false]
ASKS_CLARIFYING_QUESTIONS: [true/false] 
PROVIDES_SPECIFIC_SOLUTIONS: [true/false]
QUALITY_ISSUES: [comma-separated list or 'none']
IMPROVEMENT_SUGGESTIONS: [comma-separated list or 'none']
OVERALL_SCORE: [0.0-1.0]
CONFIDENCE: [low/medium/high]
PASSED: [true/false]
REASONING: [detailed explanation]
"""
    
    def _parse_quality_assessment_response(self, evaluation_text: str) -> ConversationQualityMetrics:
        """Parse AI evaluation response into structured quality metrics"""
        
        try:
            # Extract numeric scores
            score_patterns = {
                'professionalism_score': r'PROFESSIONALISM_SCORE:\s*([\d.]+)',
                'relevance_score': r'RELEVANCE_SCORE:\s*([\d.]+)',
                'completeness_score': r'COMPLETENESS_SCORE:\s*([\d.]+)',
                'actionability_score': r'ACTIONABILITY_SCORE:\s*([\d.]+)',
                'empathy_score': r'EMPATHY_SCORE:\s*([\d.]+)',
                'overall_score': r'OVERALL_SCORE:\s*([\d.]+)'
            }
            
            scores = {}
            for key, pattern in score_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                scores[key] = float(match.group(1)) if match else 0.5
            
            # Extract boolean fields
            bool_patterns = {
                'maintains_context': r'MAINTAINS_CONTEXT:\s*(\w+)',
                'asks_clarifying_questions': r'ASKS_CLARIFYING_QUESTIONS:\s*(\w+)',
                'provides_specific_solutions': r'PROVIDES_SPECIFIC_SOLUTIONS:\s*(\w+)',
                'passed': r'PASSED:\s*(\w+)'
            }
            
            bools = {}
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                bools[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract other fields
            confidence_match = re.search(r'CONFIDENCE:\s*(\w+)', evaluation_text, re.IGNORECASE)
            confidence = confidence_match.group(1).lower() if confidence_match else 'medium'
            
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else 'Quality assessment completed'
            
            # Extract list fields
            quality_issues = self._extract_list_field(evaluation_text, 'QUALITY_ISSUES')
            improvements = self._extract_list_field(evaluation_text, 'IMPROVEMENT_SUGGESTIONS')
            
            return ConversationQualityMetrics(
                passed=bools.get('passed', False),
                confidence=EvaluationConfidence(confidence),
                score=scores.get('overall_score', 0.5),
                reasoning=reasoning,
                professionalism_score=scores.get('professionalism_score', 0.5),
                relevance_score=scores.get('relevance_score', 0.5),
                completeness_score=scores.get('completeness_score', 0.5),
                actionability_score=scores.get('actionability_score', 0.5),
                empathy_score=scores.get('empathy_score', 0.5),
                maintains_context=bools.get('maintains_context', False),
                asks_clarifying_questions=bools.get('asks_clarifying_questions', False),
                provides_specific_solutions=bools.get('provides_specific_solutions', False),
                quality_issues=quality_issues,
                improvement_suggestions=improvements,
                timestamp="",  # Will be set by caller
                evaluation_time_ms=0  # Will be set by caller
            )
            
        except Exception as e:
            logger.error(f"Failed to parse quality assessment response: {e}")
            return self._create_fallback_quality_assessment(str(e))
    
    def _parse_professionalism_response(self, evaluation_text: str) -> Dict[str, Any]:
        """Parse professionalism evaluation response"""
        
        try:
            patterns = {
                'tone_and_language': r'TONE_AND_LANGUAGE:\s*([\d.]+)',
                'communication_clarity': r'COMMUNICATION_CLARITY:\s*([\d.]+)',
                'business_appropriateness': r'BUSINESS_APPROPRIATENESS:\s*([\d.]+)',
                'confidence_and_competence': r'CONFIDENCE_AND_COMPETENCE:\s*([\d.]+)',
                'overall_professionalism': r'OVERALL_PROFESSIONALISM:\s*([\d.]+)'
            }
            
            scores = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                scores[key] = float(match.group(1)) if match else 0.5
            
            issues = self._extract_list_field(evaluation_text, 'ISSUES_IDENTIFIED')
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ''
            
            return {
                **scores,
                'issues_identified': issues,
                'reasoning': reasoning
            }
            
        except Exception as e:
            logger.error(f"Failed to parse professionalism response: {e}")
            return {'overall_professionalism': 0.5, 'error': str(e)}
    
    def _parse_relevance_completeness_response(self, evaluation_text: str) -> Dict[str, Any]:
        """Parse relevance and completeness evaluation response"""
        
        try:
            patterns = {
                'relevance_to_question': r'RELEVANCE_TO_QUESTION:\s*([\d.]+)',
                'completeness_of_answer': r'COMPLETENESS_OF_ANSWER:\s*([\d.]+)',
                'contextual_appropriateness': r'CONTEXTUAL_APPROPRIATENESS:\s*([\d.]+)',
                'value_provided': r'VALUE_PROVIDED:\s*([\d.]+)',
                'overall_relevance_completeness': r'OVERALL_RELEVANCE_COMPLETENESS:\s*([\d.]+)'
            }
            
            scores = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                scores[key] = float(match.group(1)) if match else 0.5
            
            gaps = self._extract_list_field(evaluation_text, 'GAPS_IDENTIFIED')
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ''
            
            return {
                **scores,
                'gaps_identified': gaps,
                'reasoning': reasoning
            }
            
        except Exception as e:
            logger.error(f"Failed to parse relevance/completeness response: {e}")
            return {'overall_relevance_completeness': 0.5, 'error': str(e)}
    
    def _parse_actionability_response(self, evaluation_text: str) -> Dict[str, Any]:
        """Parse actionability evaluation response"""
        
        try:
            patterns = {
                'specific_recommendations': r'SPECIFIC_RECOMMENDATIONS:\s*([\d.]+)',
                'implementation_guidance': r'IMPLEMENTATION_GUIDANCE:\s*([\d.]+)',
                'prioritization': r'PRIORITIZATION:\s*([\d.]+)',
                'practical_feasibility': r'PRACTICAL_FEASIBILITY:\s*([\d.]+)',
                'overall_actionability': r'OVERALL_ACTIONABILITY:\s*([\d.]+)'
            }
            
            scores = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                scores[key] = float(match.group(1)) if match else 0.5
            
            # Extract count
            count_match = re.search(r'ACTIONABLE_ITEMS_COUNT:\s*(\d+)', evaluation_text, re.IGNORECASE)
            actionable_count = int(count_match.group(1)) if count_match else 0
            
            non_actionable = self._extract_list_field(evaluation_text, 'NON_ACTIONABLE_CONTENT')
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ''
            
            return {
                **scores,
                'actionable_items_count': actionable_count,
                'non_actionable_content': non_actionable,
                'reasoning': reasoning
            }
            
        except Exception as e:
            logger.error(f"Failed to parse actionability response: {e}")
            return {'overall_actionability': 0.5, 'error': str(e)}
    
    def _extract_list_field(self, text: str, field_name: str) -> List[str]:
        """Extract comma-separated list field from evaluation response"""
        
        pattern = rf'{field_name}:\s*(.+?)(?=\n[A-Z_]+:|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            value = match.group(1).strip()
            if value and value.lower() not in ['none', 'n/a', '']:
                return [item.strip() for item in value.split(',') if item.strip()]
        
        return []
    
    def _create_fallback_quality_assessment(self, error_message: str) -> ConversationQualityMetrics:
        """Create fallback quality assessment when evaluation fails"""
        
        return ConversationQualityMetrics(
            passed=False,
            confidence=EvaluationConfidence.LOW,
            score=0.0,
            reasoning=f"Quality assessment failed: {error_message}",
            professionalism_score=0.0,
            relevance_score=0.0,
            completeness_score=0.0,
            actionability_score=0.0,
            empathy_score=0.0,
            maintains_context=False,
            asks_clarifying_questions=False,
            provides_specific_solutions=False,
            quality_issues=["Evaluation system failure"],
            improvement_suggestions=["Fix evaluation system"],
            timestamp=datetime.utcnow().isoformat(),
            evaluation_time_ms=0
        )
    
    def _load_quality_criteria(self) -> Dict[str, Any]:
        """Load conversation quality criteria"""
        
        return {
            "professionalism_thresholds": {
                "excellent": 0.9,
                "good": 0.7,
                "acceptable": 0.5,
                "poor": 0.3
            },
            "completeness_indicators": [
                "specific recommendations",
                "implementation steps",
                "clear next actions",
                "timeline provided",
                "resource requirements"
            ],
            "empathy_indicators": [
                "understanding customer pain",
                "acknowledging challenges", 
                "supportive language",
                "customer-focused solutions"
            ]
        }
    
    def _load_professional_standards(self) -> Dict[str, Any]:
        """Load professional communication standards"""
        
        return {
            "required_elements": [
                "professional greeting",
                "clear communication",
                "actionable advice",
                "professional closing"
            ],
            "avoid_elements": [
                "overly casual language",
                "inappropriate humor",
                "personal opinions",
                "unprofessional slang"
            ],
            "tone_requirements": [
                "helpful and supportive",
                "confident but not arrogant", 
                "business-appropriate",
                "customer-focused"
            ]
        }