"""
ROI Calculation Validator - Financial Logic Verification
Validates ROI calculations, time savings, and business value assessments using AI analysis
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
    ROIValidationResult,
    EvaluationConfidence
)

logger = logging.getLogger(__name__)


class ROICalculationValidator:
    """
    AI-powered validator for ROI calculations and financial logic.
    
    Validates:
    - Mathematical accuracy of ROI calculations
    - Time savings quantification
    - Cost savings analysis
    - Business value assessments
    - Assumption reasonableness
    """
    
    def __init__(self, openai_client: Optional[OpenAI] = None, model: str = "gpt-4o-mini"):
        """
        Initialize ROI calculation validator.
        
        Args:
            openai_client: OpenAI client instance
            model: Model to use for evaluation
        """
        self.client = openai_client or OpenAI()
        self.model = model
        
        # Financial validation benchmarks
        self.roi_benchmarks = self._load_roi_benchmarks()
        self.cost_assumptions = self._load_cost_assumptions()
        
        logger.info(f"Initialized ROICalculationValidator with model: {model}")
    
    async def validate_roi_calculation(self,
                                     business_problem: str,
                                     ea_response: str,
                                     stated_costs: Optional[Dict[str, Any]] = None) -> ROIValidationResult:
        """
        Validate ROI calculation accuracy and business logic.
        
        Args:
            business_problem: Customer's stated business problem
            ea_response: EA's response with ROI calculation
            stated_costs: Any costs/rates stated by customer
            
        Returns:
            ROIValidationResult with detailed validation analysis
        """
        start_time = time.time()
        
        try:
            # Extract financial information from EA response
            extracted_financials = await self._extract_financial_information(ea_response)
            
            # Create ROI validation prompt
            evaluation_prompt = self._create_roi_validation_prompt(
                business_problem, ea_response, extracted_financials, stated_costs
            )
            
            # Get AI evaluation
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert financial analyst validating ROI calculations and business value assessments."},
                    {"role": "user", "content": evaluation_prompt}
                ],
                temperature=0.1,  # Low temperature for consistent evaluation
                max_tokens=2000
            )
            
            evaluation_text = response.choices[0].message.content
            
            # Parse structured validation results
            validation = self._parse_roi_validation_response(evaluation_text)
            
            # Add extracted financial data
            validation.extracted_time_savings = extracted_financials.get("time_savings")
            validation.extracted_cost_savings = extracted_financials.get("cost_savings")
            validation.calculated_roi_percentage = extracted_financials.get("roi_percentage")
            validation.payback_period = extracted_financials.get("payback_period")
            
            # Add metadata
            evaluation_time = int((time.time() - start_time) * 1000)
            validation.timestamp = datetime.utcnow().isoformat()
            validation.evaluation_time_ms = evaluation_time
            
            logger.info(f"ROI validation completed in {evaluation_time}ms")
            return validation
            
        except Exception as e:
            logger.error(f"ROI validation failed: {e}")
            return self._create_fallback_roi_validation(str(e))
    
    async def validate_time_savings_calculation(self,
                                              time_description: str,
                                              ea_calculation: str,
                                              hourly_rate: Optional[float] = None) -> Dict[str, Any]:
        """
        Validate time savings calculation accuracy.
        
        Args:
            time_description: Customer's description of time spent
            ea_calculation: EA's time savings calculation
            hourly_rate: Hourly rate for cost calculation
            
        Returns:
            Dictionary with time savings validation results
        """
        try:
            prompt = f"""
Validate this time savings calculation for accuracy:

CUSTOMER'S TIME DESCRIPTION:
{time_description}

EA'S TIME SAVINGS CALCULATION:
{ea_calculation}

HOURLY RATE: {hourly_rate if hourly_rate else "Not specified"}

Please validate:

1. TIME EXTRACTION ACCURACY:
   - Are the time values correctly extracted from the description?
   - Are units (hours, minutes, daily, weekly) handled correctly?
   - Are frequencies properly converted to consistent units?

2. MATHEMATICAL ACCURACY:
   - Are the calculations mathematically correct?
   - Are time period conversions accurate (daily to weekly, etc.)?
   - Are totals and summations correct?

3. BUSINESS LOGIC:
   - Are the time savings realistic for the described tasks?
   - Are automation assumptions reasonable?
   - Are efficiency gains realistic (typically 70-90% for full automation)?

4. COST CALCULATION:
   - If hourly rate provided, are cost savings calculated correctly?
   - Are time periods consistently applied (weekly, monthly, annual)?
   - Are the financial projections reasonable?

Please provide validation results in this format:
TIME_EXTRACTION_ACCURATE: [true/false]
MATHEMATICAL_ACCURACY: [true/false]
REALISTIC_ASSUMPTIONS: [true/false]
COST_CALCULATION_CORRECT: [true/false]
EXTRACTED_TIME_PER_PERIOD: [e.g., "5 hours per week"]
CALCULATED_SAVINGS_PER_PERIOD: [e.g., "4.5 hours per week"]
ANNUAL_TIME_SAVINGS: [e.g., "234 hours per year"]
CALCULATION_ERRORS: [comma-separated list or 'none']
UNREALISTIC_ASSUMPTIONS: [comma-separated list or 'none']
OVERALL_ACCURACY: [0.0-1.0]
REASONING: [detailed explanation]
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500
            )
            
            evaluation_text = response.choices[0].message.content
            return self._parse_time_savings_validation(evaluation_text)
            
        except Exception as e:
            logger.error(f"Time savings validation failed: {e}")
            return {"overall_accuracy": 0.5, "error": str(e)}
    
    async def validate_cost_savings_logic(self,
                                        business_context: str,
                                        cost_savings_claim: str,
                                        industry: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate cost savings logic and assumptions.
        
        Args:
            business_context: Business context for cost validation
            cost_savings_claim: EA's cost savings claim
            industry: Industry for benchmarking
            
        Returns:
            Dictionary with cost savings validation results
        """
        try:
            industry_benchmarks = self.roi_benchmarks.get(industry, {}) if industry else {}
            
            prompt = f"""
Validate this cost savings analysis for business logic and accuracy:

BUSINESS CONTEXT:
{business_context}

COST SAVINGS CLAIM:
{cost_savings_claim}

INDUSTRY: {industry or "General"}
INDUSTRY BENCHMARKS: {json.dumps(industry_benchmarks, indent=2) if industry_benchmarks else "None available"}

Please validate:

1. COST BASIS ACCURACY:
   - Are the base costs (labor, overhead, etc.) reasonable?
   - Are hourly rates realistic for the industry/role?
   - Are hidden costs appropriately considered?

2. SAVINGS CALCULATION LOGIC:
   - Are savings percentages realistic (typically 50-90% for automation)?
   - Are one-time vs recurring costs distinguished?
   - Are implementation costs considered?

3. ASSUMPTION REASONABLENESS:
   - Are efficiency gain assumptions realistic?
   - Are scaling assumptions appropriate?
   - Are maintenance costs considered?

4. INDUSTRY APPROPRIATENESS:
   - Are cost assumptions appropriate for the industry?
   - Are typical industry rates and costs considered?
   - Are industry-specific factors accounted for?

5. RISK FACTORS:
   - Are potential cost overruns mentioned?
   - Are adoption/change management costs considered?
   - Are ongoing maintenance costs included?

Format response as:
COST_BASIS_ACCURATE: [true/false]
SAVINGS_LOGIC_SOUND: [true/false]
ASSUMPTIONS_REASONABLE: [true/false]
INDUSTRY_APPROPRIATE: [true/false]
RISK_FACTORS_CONSIDERED: [true/false]
EXTRACTED_HOURLY_RATE: [rate or 'not specified']
EXTRACTED_ANNUAL_SAVINGS: [amount or 'not specified']
SAVINGS_PERCENTAGE: [percentage or 'not specified']
QUESTIONABLE_ASSUMPTIONS: [comma-separated list or 'none']
MISSING_COSTS: [comma-separated list or 'none']
OVERALL_VALIDITY: [0.0-1.0]
REASONING: [detailed explanation]
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1800
            )
            
            evaluation_text = response.choices[0].message.content
            return self._parse_cost_savings_validation(evaluation_text)
            
        except Exception as e:
            logger.error(f"Cost savings validation failed: {e}")
            return {"overall_validity": 0.5, "error": str(e)}
    
    async def validate_payback_period_calculation(self,
                                                implementation_cost: str,
                                                monthly_savings: str,
                                                ea_payback_claim: str) -> Dict[str, Any]:
        """
        Validate payback period calculation.
        
        Args:
            implementation_cost: Stated or implied implementation cost
            monthly_savings: Stated monthly savings
            ea_payback_claim: EA's payback period claim
            
        Returns:
            Dictionary with payback period validation
        """
        try:
            prompt = f"""
Validate this payback period calculation:

IMPLEMENTATION COST:
{implementation_cost}

MONTHLY SAVINGS:
{monthly_savings}

EA'S PAYBACK PERIOD CLAIM:
{ea_payback_claim}

Please validate:

1. COST EXTRACTION:
   - Are implementation costs correctly identified?
   - Are one-time vs recurring costs separated?
   - Are all relevant costs included?

2. SAVINGS EXTRACTION:
   - Are monthly/annual savings correctly calculated?
   - Are savings consistent with previous calculations?
   - Are net savings (after ongoing costs) used?

3. PAYBACK CALCULATION:
   - Is the payback formula applied correctly (Cost ÷ Monthly Savings)?
   - Are time units consistent (months, years)?
   - Is the calculation mathematically accurate?

4. REASONABLENESS CHECK:
   - Is the payback period realistic for this type of automation?
   - Are typical automation payback periods considered (usually 3-18 months)?
   - Are business factors appropriately weighted?

Format response as:
IMPLEMENTATION_COST_EXTRACTED: [amount or 'not found']
MONTHLY_SAVINGS_EXTRACTED: [amount or 'not found']
PAYBACK_CALCULATION_CORRECT: [true/false]
CALCULATED_PAYBACK_MONTHS: [number or 'cannot calculate']
EA_CLAIMED_PAYBACK: [period or 'not specified']
PAYBACK_REALISTIC: [true/false]
CALCULATION_ERRORS: [comma-separated list or 'none']
MISSING_CONSIDERATIONS: [comma-separated list or 'none']
OVERALL_ACCURACY: [0.0-1.0]
REASONING: [detailed explanation]
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500
            )
            
            evaluation_text = response.choices[0].message.content
            return self._parse_payback_validation(evaluation_text)
            
        except Exception as e:
            logger.error(f"Payback period validation failed: {e}")
            return {"overall_accuracy": 0.5, "error": str(e)}
    
    async def _extract_financial_information(self, ea_response: str) -> Dict[str, Any]:
        """Extract financial information from EA response using AI"""
        
        try:
            prompt = f"""
Extract all financial information from this response:

{ea_response}

Please extract:
- Time savings (hours per day/week/month)
- Cost savings (dollar amounts)
- ROI percentage
- Payback period
- Hourly rates mentioned
- Implementation costs
- Annual projections

Format as JSON with these fields:
{{
    "time_savings": {{"amount": "X hours", "period": "per week", "annual_hours": number}},
    "cost_savings": {{"amount": "X dollars", "period": "per month", "annual_amount": number}},
    "roi_percentage": number,
    "payback_period": "X months",
    "hourly_rate": number,
    "implementation_cost": number,
    "annual_projections": {{"savings": number, "roi": number}}
}}

Only include fields where specific values are mentioned.
"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800
            )
            
            # Parse JSON response
            financials_text = response.choices[0].message.content
            try:
                return json.loads(financials_text)
            except json.JSONDecodeError:
                # Fallback: extract using regex
                return self._extract_financials_regex(ea_response)
                
        except Exception as e:
            logger.error(f"Financial extraction failed: {e}")
            return {}
    
    def _extract_financials_regex(self, text: str) -> Dict[str, Any]:
        """Fallback regex-based financial extraction"""
        
        financials = {}
        
        # Extract dollar amounts
        dollar_pattern = r'\$[\d,]+(?:\.\d{2})?'
        dollars = re.findall(dollar_pattern, text)
        if dollars:
            financials["dollar_amounts"] = dollars
        
        # Extract percentages
        percent_pattern = r'(\d+(?:\.\d+)?)\s*%'
        percentages = re.findall(percent_pattern, text)
        if percentages:
            financials["percentages"] = [float(p) for p in percentages]
        
        # Extract time periods
        time_pattern = r'(\d+(?:\.\d+)?)\s*(hours?|minutes?|days?)\s*(per|/)\s*(week|month|year|day)'
        times = re.findall(time_pattern, text, re.IGNORECASE)
        if times:
            financials["time_periods"] = times
        
        return financials
    
    def _create_roi_validation_prompt(self,
                                    business_problem: str,
                                    ea_response: str,
                                    extracted_financials: Dict[str, Any],
                                    stated_costs: Optional[Dict[str, Any]]) -> str:
        """Create comprehensive ROI validation prompt"""
        
        financials_text = json.dumps(extracted_financials, indent=2) if extracted_financials else "None extracted"
        costs_text = json.dumps(stated_costs, indent=2) if stated_costs else "None provided"
        
        return f"""
Validate the ROI calculation and financial logic in this business automation response:

CUSTOMER'S BUSINESS PROBLEM:
{business_problem}

EA'S RESPONSE WITH ROI CALCULATION:
{ea_response}

EXTRACTED FINANCIAL INFORMATION:
{financials_text}

CUSTOMER'S STATED COSTS/RATES:
{costs_text}

Please validate the ROI calculation across these dimensions:

1. ROI CALCULATION PRESENCE:
   - Is an ROI calculation present in the response?
   - Are specific financial benefits quantified?
   - Is business value clearly articulated?

2. MATHEMATICAL ACCURACY:
   - Are the mathematical calculations correct?
   - Are formulas applied properly (ROI = (Gain - Cost) / Cost * 100)?
   - Are unit conversions accurate (hourly to annual, etc.)?

3. TIME SAVINGS QUANTIFICATION:
   - Are time savings specifically quantified?
   - Are time periods and frequencies correctly handled?
   - Are automation efficiency assumptions reasonable (typically 70-90%)?

4. COST SAVINGS CALCULATION:
   - Are labor cost savings calculated correctly?
   - Are hourly rates realistic and appropriate?
   - Are additional costs (overhead, benefits) considered appropriately?

5. ASSUMPTION REASONABLENESS:
   - Are underlying assumptions clearly stated and reasonable?
   - Are efficiency gains realistic for the type of automation?
   - Are implementation and maintenance costs considered?

6. MISSING CONSIDERATIONS:
   - What important financial considerations are missing?
   - Are one-time vs recurring costs distinguished?
   - Are risk factors and potential cost overruns mentioned?

Please provide validation in this format:
ROI_CALCULATION_PRESENT: [true/false]
ROI_CALCULATION_ACCURATE: [true/false]
TIME_SAVINGS_QUANTIFIED: [true/false]
COST_SAVINGS_CALCULATED: [true/false]
ASSUMPTIONS_REASONABLE: [true/false]
CALCULATION_ERRORS: [comma-separated list or 'none']
MISSING_CONSIDERATIONS: [comma-separated list or 'none']
OVERALL_SCORE: [0.0-1.0]
CONFIDENCE: [low/medium/high]
PASSED: [true/false]
REASONING: [detailed explanation with specific examples]
"""
    
    def _parse_roi_validation_response(self, evaluation_text: str) -> ROIValidationResult:
        """Parse ROI validation response into structured result"""
        
        try:
            # Extract boolean fields
            bool_patterns = {
                'roi_calculation_present': r'ROI_CALCULATION_PRESENT:\s*(\w+)',
                'roi_calculation_accurate': r'ROI_CALCULATION_ACCURATE:\s*(\w+)',
                'time_savings_quantified': r'TIME_SAVINGS_QUANTIFIED:\s*(\w+)',
                'cost_savings_calculated': r'COST_SAVINGS_CALCULATED:\s*(\w+)',
                'assumptions_reasonable': r'ASSUMPTIONS_REASONABLE:\s*(\w+)',
                'passed': r'PASSED:\s*(\w+)'
            }
            
            extracted = {}
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                extracted[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract other fields
            score_match = re.search(r'OVERALL_SCORE:\s*([\d.]+)', evaluation_text, re.IGNORECASE)
            overall_score = float(score_match.group(1)) if score_match else 0.5
            
            confidence_match = re.search(r'CONFIDENCE:\s*(\w+)', evaluation_text, re.IGNORECASE)
            confidence = confidence_match.group(1).lower() if confidence_match else 'medium'
            
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else 'ROI validation completed'
            
            # Extract list fields
            calculation_errors = self._extract_list_field(evaluation_text, 'CALCULATION_ERRORS')
            missing_considerations = self._extract_list_field(evaluation_text, 'MISSING_CONSIDERATIONS')
            
            return ROIValidationResult(
                passed=extracted.get('passed', False),
                confidence=EvaluationConfidence(confidence),
                score=overall_score,
                reasoning=reasoning,
                roi_calculation_present=extracted.get('roi_calculation_present', False),
                roi_calculation_accurate=extracted.get('roi_calculation_accurate', False),
                time_savings_quantified=extracted.get('time_savings_quantified', False),
                cost_savings_calculated=extracted.get('cost_savings_calculated', False),
                assumptions_reasonable=extracted.get('assumptions_reasonable', False),
                calculation_errors=calculation_errors,
                missing_considerations=missing_considerations,
                timestamp="",  # Will be set by caller
                evaluation_time_ms=0  # Will be set by caller
            )
            
        except Exception as e:
            logger.error(f"Failed to parse ROI validation response: {e}")
            return self._create_fallback_roi_validation(str(e))
    
    def _parse_time_savings_validation(self, evaluation_text: str) -> Dict[str, Any]:
        """Parse time savings validation response"""
        
        try:
            # Extract boolean fields
            bool_patterns = {
                'time_extraction_accurate': r'TIME_EXTRACTION_ACCURATE:\s*(\w+)',
                'mathematical_accuracy': r'MATHEMATICAL_ACCURACY:\s*(\w+)',
                'realistic_assumptions': r'REALISTIC_ASSUMPTIONS:\s*(\w+)',
                'cost_calculation_correct': r'COST_CALCULATION_CORRECT:\s*(\w+)'
            }
            
            results = {}
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                results[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract time periods
            time_fields = {
                'extracted_time_per_period': r'EXTRACTED_TIME_PER_PERIOD:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'calculated_savings_per_period': r'CALCULATED_SAVINGS_PER_PERIOD:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'annual_time_savings': r'ANNUAL_TIME_SAVINGS:\s*(.+?)(?=\n[A-Z_]+:|$)'
            }
            
            for key, pattern in time_fields.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
                results[key] = match.group(1).strip() if match else None
            
            # Extract accuracy score
            accuracy_match = re.search(r'OVERALL_ACCURACY:\s*([\d.]+)', evaluation_text, re.IGNORECASE)
            results['overall_accuracy'] = float(accuracy_match.group(1)) if accuracy_match else 0.5
            
            # Extract lists
            results['calculation_errors'] = self._extract_list_field(evaluation_text, 'CALCULATION_ERRORS')
            results['unrealistic_assumptions'] = self._extract_list_field(evaluation_text, 'UNREALISTIC_ASSUMPTIONS')
            
            # Extract reasoning
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            results['reasoning'] = reasoning_match.group(1).strip() if reasoning_match else ''
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse time savings validation: {e}")
            return {"overall_accuracy": 0.5, "error": str(e)}
    
    def _parse_cost_savings_validation(self, evaluation_text: str) -> Dict[str, Any]:
        """Parse cost savings validation response"""
        
        try:
            # Extract boolean fields
            bool_patterns = {
                'cost_basis_accurate': r'COST_BASIS_ACCURATE:\s*(\w+)',
                'savings_logic_sound': r'SAVINGS_LOGIC_SOUND:\s*(\w+)',
                'assumptions_reasonable': r'ASSUMPTIONS_REASONABLE:\s*(\w+)',
                'industry_appropriate': r'INDUSTRY_APPROPRIATE:\s*(\w+)',
                'risk_factors_considered': r'RISK_FACTORS_CONSIDERED:\s*(\w+)'
            }
            
            results = {}
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                results[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract financial values
            value_patterns = {
                'extracted_hourly_rate': r'EXTRACTED_HOURLY_RATE:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'extracted_annual_savings': r'EXTRACTED_ANNUAL_SAVINGS:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'savings_percentage': r'SAVINGS_PERCENTAGE:\s*(.+?)(?=\n[A-Z_]+:|$)'
            }
            
            for key, pattern in value_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
                results[key] = match.group(1).strip() if match else None
            
            # Extract validity score
            validity_match = re.search(r'OVERALL_VALIDITY:\s*([\d.]+)', evaluation_text, re.IGNORECASE)
            results['overall_validity'] = float(validity_match.group(1)) if validity_match else 0.5
            
            # Extract lists
            results['questionable_assumptions'] = self._extract_list_field(evaluation_text, 'QUESTIONABLE_ASSUMPTIONS')
            results['missing_costs'] = self._extract_list_field(evaluation_text, 'MISSING_COSTS')
            
            # Extract reasoning
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            results['reasoning'] = reasoning_match.group(1).strip() if reasoning_match else ''
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse cost savings validation: {e}")
            return {"overall_validity": 0.5, "error": str(e)}
    
    def _parse_payback_validation(self, evaluation_text: str) -> Dict[str, Any]:
        """Parse payback period validation response"""
        
        try:
            # Extract extracted values
            value_patterns = {
                'implementation_cost_extracted': r'IMPLEMENTATION_COST_EXTRACTED:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'monthly_savings_extracted': r'MONTHLY_SAVINGS_EXTRACTED:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'calculated_payback_months': r'CALCULATED_PAYBACK_MONTHS:\s*(.+?)(?=\n[A-Z_]+:|$)',
                'ea_claimed_payback': r'EA_CLAIMED_PAYBACK:\s*(.+?)(?=\n[A-Z_]+:|$)'
            }
            
            results = {}
            for key, pattern in value_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE | re.DOTALL)
                results[key] = match.group(1).strip() if match else None
            
            # Extract boolean fields
            bool_patterns = {
                'payback_calculation_correct': r'PAYBACK_CALCULATION_CORRECT:\s*(\w+)',
                'payback_realistic': r'PAYBACK_REALISTIC:\s*(\w+)'
            }
            
            for key, pattern in bool_patterns.items():
                match = re.search(pattern, evaluation_text, re.IGNORECASE)
                results[key] = match.group(1).strip().lower() == 'true' if match else False
            
            # Extract accuracy score
            accuracy_match = re.search(r'OVERALL_ACCURACY:\s*([\d.]+)', evaluation_text, re.IGNORECASE)
            results['overall_accuracy'] = float(accuracy_match.group(1)) if accuracy_match else 0.5
            
            # Extract lists
            results['calculation_errors'] = self._extract_list_field(evaluation_text, 'CALCULATION_ERRORS')
            results['missing_considerations'] = self._extract_list_field(evaluation_text, 'MISSING_CONSIDERATIONS')
            
            # Extract reasoning
            reasoning_match = re.search(r'REASONING:\s*(.+?)(?=\n[A-Z_]+:|$)', evaluation_text, re.IGNORECASE | re.DOTALL)
            results['reasoning'] = reasoning_match.group(1).strip() if reasoning_match else ''
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to parse payback validation: {e}")
            return {"overall_accuracy": 0.5, "error": str(e)}
    
    def _extract_list_field(self, text: str, field_name: str) -> List[str]:
        """Extract comma-separated list field from evaluation response"""
        
        pattern = rf'{field_name}:\s*(.+?)(?=\n[A-Z_]+:|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            value = match.group(1).strip()
            if value and value.lower() not in ['none', 'n/a', '']:
                return [item.strip() for item in value.split(',') if item.strip()]
        
        return []
    
    def _create_fallback_roi_validation(self, error_message: str) -> ROIValidationResult:
        """Create fallback ROI validation when evaluation fails"""
        
        return ROIValidationResult(
            passed=False,
            confidence=EvaluationConfidence.LOW,
            score=0.0,
            reasoning=f"ROI validation failed: {error_message}",
            roi_calculation_present=False,
            roi_calculation_accurate=False,
            time_savings_quantified=False,
            cost_savings_calculated=False,
            assumptions_reasonable=False,
            calculation_errors=["Evaluation system failure"],
            missing_considerations=["Unable to validate due to system error"],
            timestamp=datetime.utcnow().isoformat(),
            evaluation_time_ms=0
        )
    
    def _load_roi_benchmarks(self) -> Dict[str, Any]:
        """Load ROI benchmarks by industry"""
        
        return {
            "e-commerce": {
                "typical_hourly_rates": {"owner": 50, "employee": 25},
                "automation_efficiency": {"social_media": 0.8, "inventory": 0.7, "customer_service": 0.6},
                "typical_roi_range": {"min": 150, "max": 400}
            },
            "professional_services": {
                "typical_hourly_rates": {"partner": 200, "associate": 100, "admin": 30},
                "automation_efficiency": {"scheduling": 0.9, "invoicing": 0.8, "reporting": 0.7},
                "typical_roi_range": {"min": 200, "max": 500}
            },
            "consulting": {
                "typical_hourly_rates": {"senior": 150, "junior": 75, "admin": 25},
                "automation_efficiency": {"proposal_writing": 0.6, "client_management": 0.7, "reporting": 0.8},
                "typical_roi_range": {"min": 100, "max": 300}
            },
            "real_estate": {
                "typical_hourly_rates": {"agent": 40, "admin": 20},
                "automation_efficiency": {"lead_management": 0.8, "marketing": 0.7, "paperwork": 0.9},
                "typical_roi_range": {"min": 150, "max": 350}
            }
        }
    
    def _load_cost_assumptions(self) -> Dict[str, Any]:
        """Load cost assumptions and validation rules"""
        
        return {
            "hourly_rate_ranges": {
                "business_owner": {"min": 25, "max": 200},
                "manager": {"min": 30, "max": 100},
                "employee": {"min": 15, "max": 75},
                "admin": {"min": 12, "max": 40}
            },
            "automation_efficiency_ranges": {
                "full_automation": {"min": 0.7, "max": 0.95},
                "partial_automation": {"min": 0.3, "max": 0.7},
                "workflow_improvement": {"min": 0.1, "max": 0.5}
            },
            "typical_payback_periods": {
                "simple_automation": {"min": 1, "max": 6},  # months
                "complex_automation": {"min": 3, "max": 18},
                "enterprise_automation": {"min": 6, "max": 36}
            }
        }