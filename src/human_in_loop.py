#!/usr/bin/env python3
"""
Human-in-the-Loop Digital Uncertainty Detection System
Detects when AI is uncertain and escalates to human operators for judgment
"""

import asyncio
import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import uuid

logger = logging.getLogger(__name__)

class UncertaintyType(Enum):
    """Types of uncertainty that require human intervention"""
    CONFIDENCE_LOW = "confidence_low"           # AI confidence score below threshold
    AMBIGUOUS_INPUT = "ambiguous_input"         # User input unclear or conflicting
    CONTEXT_INSUFFICIENT = "context_insufficient" # Not enough context to respond properly
    ETHICAL_DILEMMA = "ethical_dilemma"         # Response involves ethical considerations
    BUSINESS_CRITICAL = "business_critical"     # High-value or sensitive business decision
    SAFETY_CONCERN = "safety_concern"           # Potential safety or security issue
    TECHNICAL_LIMITATION = "technical_limitation" # AI cannot handle this type of request

@dataclass
class UncertaintySignal:
    """Signal indicating AI uncertainty requiring human review"""
    uncertainty_type: UncertaintyType
    confidence_score: float                    # 0-1 confidence level
    context_summary: str                      # What the AI was trying to do
    user_message: str                         # Original user input
    ai_response: Optional[str]                # AI's attempted response
    escalation_reason: str                    # Why this needs human review
    priority_level: str                       # "low", "medium", "high", "critical"
    customer_id: str
    channel: str
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "id": str(uuid.uuid4()),
            "uncertainty_type": self.uncertainty_type.value,
            "confidence_score": self.confidence_score,
            "context_summary": self.context_summary,
            "user_message": self.user_message,
            "ai_response": self.ai_response,
            "escalation_reason": self.escalation_reason,
            "priority_level": self.priority_level,
            "customer_id": self.customer_id,
            "channel": self.channel,
            "metadata": self.metadata,
            "created_at": datetime.now().isoformat(),
            "status": "pending"
        }

@dataclass
class HumanResolution:
    """Human operator's resolution of an uncertainty"""
    signal_id: str
    operator_id: str
    judgment: str                    # "approve", "modify", "reject", "escalate"
    final_response: str             # Human-approved or modified response
    reasoning: str                  # Human's explanation for the decision
    confidence_score: float         # Human's confidence in the resolution
    resolved_at: datetime
    follow_up_actions: List[str] = field(default_factory=list)

class UncertaintyDetector:
    """Detects various types of uncertainty in AI responses"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.uncertainty_patterns = self._load_uncertainty_patterns()

        # Configuration thresholds
        self.confidence_threshold = self.config.get("confidence_threshold", 0.6)
        self.ambiguity_threshold = self.config.get("ambiguity_threshold", 0.4)
        self.ethical_concern_keywords = self.config.get("ethical_keywords", [
            "delete", "remove", "cancel", "terminate", "fire", "layoff",
            "legal", "lawsuit", "complain", "refund", "chargeback"
        ])

    def _load_uncertainty_patterns(self) -> Dict:
        """Load patterns for detecting different types of uncertainty"""
        return {
            "ambiguous_pronouns": [
                r'\bthis\b', r'\bthat\b', r'\bit\b', r'\bthey\b', r'\bthem\b'
            ],
            "unclear_references": [
                r'\bas I mentioned\b', r'\bas we discussed\b', r'\bas you know\b'
            ],
            "conflicting_instructions": [
                r'\bbut\b', r'\bhowever\b', r'\bon the other hand\b'
            ],
            "uncertainty_phrases": [
                r'\bI think\b', r'\bmaybe\b', r'\bperhaps\b', r'\bpossibly\b',
                r'\bI\'m not sure\b', r'\bunclear\b', r'\bconfusing\b'
            ]
        }

    async def analyze_response_uncertainty(self,
                                         user_input: str,
                                         ai_response: str,
                                         context: Dict,
                                         customer_id: str,
                                         channel: str) -> List[UncertaintySignal]:
        """Analyze AI response for uncertainty signals"""
        signals = []

        # Check confidence thresholds
        confidence_signals = await self._check_confidence_thresholds(user_input, ai_response, customer_id, channel)
        signals.extend(confidence_signals)

        # Check for ambiguous patterns
        ambiguity_signals = await self._detect_ambiguous_patterns(user_input, context, customer_id, channel)
        signals.extend(ambiguity_signals)

        # Check for ethical concerns
        ethical_signals = await self._detect_ethical_concerns(user_input, ai_response, customer_id, channel)
        signals.extend(ethical_signals)

        # Check for business critical decisions
        business_signals = await self._detect_business_critical(user_input, context, customer_id, channel)
        signals.extend(business_signals)

        # Check for technical limitations
        technical_signals = await self._detect_technical_limitations(user_input, ai_response, customer_id, channel)
        signals.extend(technical_signals)

        return signals

    async def _check_confidence_thresholds(self, user_input: str, ai_response: str, customer_id: str = "", channel: str = "") -> List[UncertaintySignal]:
        """Check if AI confidence is below acceptable thresholds"""
        signals = []

        # Calculate confidence score based on response characteristics
        confidence_score = await self._calculate_response_confidence(user_input, ai_response)

        if confidence_score < self.confidence_threshold:
            signals.append(UncertaintySignal(
                uncertainty_type=UncertaintyType.CONFIDENCE_LOW,
                confidence_score=confidence_score,
                context_summary="AI response confidence below threshold",
                user_message=user_input,
                ai_response=ai_response,
                escalation_reason="Confidence {:.2f} < {}".format(confidence_score, self.confidence_threshold),
                priority_level="medium",
                customer_id=customer_id,
                channel=channel
            ))

        return signals

    async def _calculate_response_confidence(self, user_input: str, ai_response: str) -> float:
        """Calculate confidence score for AI response"""
        confidence = 1.0

        # Length-based confidence (too short or too long reduces confidence)
        response_length = len(ai_response)
        if response_length < 50:
            confidence *= 0.7  # Too short
        elif response_length > 2000:
            confidence *= 0.8  # Too long

        # Uncertainty phrase detection
        uncertainty_phrases = self.uncertainty_patterns["uncertainty_phrases"]
        uncertainty_count = sum(1 for pattern in uncertainty_phrases
                              if re.search(pattern, ai_response.lower()))
        confidence *= max(0.3, 1.0 - (uncertainty_count * 0.2))

        # Question ratio (responses with many questions are less confident)
        question_count = ai_response.count('?')
        if question_count > 2:
            confidence *= 0.6

        return max(0.0, min(1.0, confidence))

    async def _detect_ambiguous_patterns(self, user_input: str, context: Dict, customer_id: str = "", channel: str = "") -> List[UncertaintySignal]:
        """Detect ambiguous or unclear user input patterns"""
        signals = []

        # Check for unclear pronouns
        pronoun_patterns = self.uncertainty_patterns["ambiguous_pronouns"]
        pronoun_count = sum(1 for pattern in pronoun_patterns
                           if re.search(pattern, user_input.lower()))

        if pronoun_count > 0:
            # Check if context provides clarification
            context_clarity = await self._assess_context_clarity(user_input, context)

            if context_clarity < 0.5:  # Low context clarity
                signals.append(UncertaintySignal(
                    uncertainty_type=UncertaintyType.AMBIGUOUS_INPUT,
                    confidence_score=0.4,
                    context_summary="User input contains unclear references without sufficient context",
                    user_message=user_input,
                    ai_response="",  # Not available in this context
                    escalation_reason=f"Found {pronoun_count} unclear pronouns without context clarification",
                    priority_level="medium",
                    customer_id=customer_id,
                    channel=channel
                ))

        # Check for conflicting instructions
        conflicting_patterns = self.uncertainty_patterns["conflicting_instructions"]
        conflicting_count = sum(1 for pattern in conflicting_patterns
                               if re.search(pattern, user_input.lower()))

        if conflicting_count > 0:
            signals.append(UncertaintySignal(
                uncertainty_type=UncertaintyType.AMBIGUOUS_INPUT,
                confidence_score=0.3,
                context_summary="User input contains potentially conflicting instructions",
                user_message=user_input,
                ai_response="",  # Not available in this context
                escalation_reason=f"Detected {conflicting_count} conflicting instruction patterns",
                priority_level="medium",
                customer_id=customer_id,
                channel=channel
            ))

        return signals

    async def _assess_context_clarity(self, user_input: str, context: Dict) -> float:
        """Assess how clear the context is for understanding the user input"""
        clarity_score = 1.0

        # Check recent conversation history
        recent_messages = context.get("recent_messages", [])
        if len(recent_messages) < 3:
            clarity_score *= 0.7  # Limited conversation history

        # Check for related topics in context
        input_topics = set(re.findall(r'\b\w{4,}\b', user_input.lower()))
        context_topics = set()

        for msg in recent_messages[-5:]:  # Last 5 messages
            msg_words = re.findall(r'\b\w{4,}\b', msg.get("content", "").lower())
            context_topics.update(msg_words)

        # Calculate topic overlap
        if input_topics and context_topics:
            overlap = len(input_topics.intersection(context_topics))
            topic_clarity = overlap / len(input_topics)
            clarity_score *= topic_clarity

        return max(0.0, min(1.0, clarity_score))

    async def _detect_ethical_concerns(self, user_input: str, ai_response: str, customer_id: str = "", channel: str = "") -> List[UncertaintySignal]:
        """Detect potential ethical concerns in requests or responses"""
        signals = []

        user_lower = user_input.lower()
        response_lower = ai_response.lower()

        # Check for ethical concern keywords
        ethical_matches = [keyword for keyword in self.ethical_concern_keywords
                          if keyword in user_lower or keyword in response_lower]

        if ethical_matches:
            signals.append(UncertaintySignal(
                uncertainty_type=UncertaintyType.ETHICAL_DILEMMA,
                confidence_score=0.2,
                context_summary="Request or response involves potentially sensitive business actions",
                user_message=user_input,
                ai_response=ai_response,
                escalation_reason=f"Detected ethical concern keywords: {', '.join(ethical_matches)}",
                priority_level="high",
                customer_id=customer_id,
                channel=channel
            ))

        return signals

    async def _detect_business_critical(self, user_input: str, context: Dict, customer_id: str = "", channel: str = "") -> List[UncertaintySignal]:
        """Detect business-critical decisions that need human oversight"""
        signals = []

        user_lower = user_input.lower()

        # Business critical keywords
        critical_keywords = [
            "delete all", "remove all", "cancel account", "terminate service",
            "fire employee", "lay off", "legal action", "sue", "lawsuit",
            "refund all", "chargeback", "dispute", "complaint"
        ]

        critical_matches = [keyword for keyword in critical_keywords if keyword in user_lower]

        if critical_matches:
            signals.append(UncertaintySignal(
                uncertainty_type=UncertaintyType.BUSINESS_CRITICAL,
                confidence_score=0.1,
                context_summary="Request involves potentially business-critical actions",
                user_message=user_input,
                ai_response="",  # Not available in this context
                escalation_reason=f"Business-critical keywords detected: {', '.join(critical_matches)}",
                priority_level="critical",
                customer_id=customer_id,
                channel=channel
            ))

        return signals

    async def _detect_technical_limitations(self, user_input: str, ai_response: str, customer_id: str = "", channel: str = "") -> List[UncertaintySignal]:
        """Detect when AI cannot handle certain types of requests"""
        signals = []

        # Technical limitation patterns
        technical_patterns = [
            r"i cannot", r"i'm unable to", r"i don't have access",
            r"this is not supported", r"feature not available",
            r"please contact support", r"human assistance required"
        ]

        limitation_matches = [pattern for pattern in technical_patterns
                            if re.search(pattern, ai_response.lower())]

        if limitation_matches:
            signals.append(UncertaintySignal(
                uncertainty_type=UncertaintyType.TECHNICAL_LIMITATION,
                confidence_score=0.3,
                context_summary="AI response indicates technical limitations",
                user_message=user_input,
                ai_response=ai_response,
                escalation_reason=f"Technical limitation detected: {', '.join(limitation_matches)}",
                priority_level="medium",
                customer_id=customer_id,
                channel=channel
            ))

        return signals

class HumanEscalationManager:
    """Manages escalation of uncertain AI responses to human operators"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.escalation_queue: asyncio.Queue[UncertaintySignal] = asyncio.Queue()
        self.resolution_history: List[HumanResolution] = []

        # Human operator management
        self.available_operators: Dict[str, Dict] = {}
        self.operator_workload: Dict[str, int] = {}

        # Start background processing
        self.processing_task = None

    async def start(self):
        """Start the escalation management system"""
        if self.processing_task is None:
            self.processing_task = asyncio.create_task(self._process_escalation_queue())

    async def stop(self):
        """Stop the escalation management system"""
        if self.processing_task:
            self.processing_task.cancel()
            self.processing_task = None

    async def escalate_uncertainty(self, signal: UncertaintySignal) -> Optional[HumanResolution]:
        """Escalate uncertainty signal to human operator"""
        try:
            # Add to escalation queue
            await self.escalation_queue.put(signal)
            logger.info(f"🚨 Escalated uncertainty: {signal.uncertainty_type.value} for customer {signal.customer_id}")

            # For critical priority, try to get immediate resolution
            if signal.priority_level == "critical":
                return await self._get_human_resolution(self.available_operators.get("operator_1", {"id": "operator_1", "name": "Default Operator"}), signal)

            return None  # Will be processed in background

        except Exception as e:
            logger.error(f"Error escalating uncertainty: {e}")
            return None

    async def _process_escalation_queue(self):
        """Background task to process escalation queue"""
        while True:
            try:
                # Wait for signals in queue
                signal = await self.escalation_queue.get()

                # Find available operator
                operator = await self._find_available_operator(signal.priority_level)

                if operator:
                    resolution = await self._get_human_resolution(operator, signal)
                    if resolution:
                        self.resolution_history.append(resolution)
                        logger.info(f"✅ Human resolution completed for signal {signal.uncertainty_type.value}")

                self.escalation_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing escalation queue: {e}")
                await asyncio.sleep(1)  # Brief pause before retry

    async def _find_available_operator(self, priority_level: str) -> Optional[Dict]:
        """Find available human operator for the priority level"""
        # Simple operator selection (can be enhanced)
        available_ops = [
            op for op_id, op in self.available_operators.items()
            if self.operator_workload.get(op_id, 0) < 5  # Max 5 concurrent resolutions
        ]

        if available_ops:
            # Select operator with lowest workload
            selected_op = min(available_ops, key=lambda x: self.operator_workload.get(x["id"], 0))
            return selected_op

        return None

    async def _get_human_resolution(self, operator: Dict, signal: UncertaintySignal) -> Optional[HumanResolution]:
        """Get human judgment on uncertain AI response"""
        try:
            # Create review context for human operator
            review_context = {
                "signal_id": id(signal),
                "customer_id": signal.customer_id,
                "uncertainty_type": signal.uncertainty_type.value,
                "priority": signal.priority_level,
                "user_message": signal.user_message,
                "ai_response": signal.ai_response,
                "escalation_reason": signal.escalation_reason,
                "context_summary": signal.context_summary,
                "channel": signal.channel
            }

            # Simulate human operator review (in real implementation, this would be a human)
            # For now, create automated resolution based on uncertainty type
            resolution = await self._simulate_human_resolution(operator, signal, review_context)

            return resolution

        except Exception as e:
            logger.error(f"Error getting human resolution: {e}")
            return None

    async def _simulate_human_resolution(self, operator: Dict, signal: UncertaintySignal, context: Dict) -> HumanResolution:
        """Simulate human operator resolution (replace with real human interface)"""
        # In a real implementation, this would present the context to a human operator
        # and get their judgment through a web interface or API

        # For simulation, create reasonable resolutions based on uncertainty type
        if signal.uncertainty_type == UncertaintyType.CONFIDENCE_LOW:
            judgment = "modify"
            final_response = f"I understand you need help with this. Let me clarify: {signal.user_message}"
            reasoning = "Low confidence response needs clarification"

        elif signal.uncertainty_type == UncertaintyType.AMBIGUOUS_INPUT:
            judgment = "modify"
            final_response = f"I want to make sure I understand correctly. Could you provide more details about: {signal.user_message}"
            reasoning = "Ambiguous input requires clarification"

        elif signal.uncertainty_type == UncertaintyType.ETHICAL_DILEMMA:
            judgment = "escalate"
            final_response = "This request involves sensitive business matters that require human review. A specialist will contact you shortly."
            reasoning = "Ethical concerns require human judgment"

        elif signal.uncertainty_type == UncertaintyType.BUSINESS_CRITICAL:
            judgment = "escalate"
            final_response = "This appears to be a business-critical matter that requires human oversight. Our team will review and respond within 2 hours."
            reasoning = "Business-critical decisions need human approval"

        else:
            judgment = "approve"
            final_response = signal.ai_response or "I understand and will help with your request."
            reasoning = "Response appears appropriate for the situation"

        return HumanResolution(
            signal_id=str(id(signal)),
            operator_id=operator["id"],
            judgment=judgment,
            final_response=final_response,
            reasoning=reasoning,
            confidence_score=0.9,
            resolved_at=datetime.now()
        )

    def register_operator(self, operator_id: str, name: str, expertise: List[str]):
        """Register a human operator"""
        self.available_operators[operator_id] = {
            "id": operator_id,
            "name": name,
            "expertise": expertise,
            "registered_at": datetime.now().isoformat()
        }
        self.operator_workload[operator_id] = 0
        logger.info(f"👤 Registered human operator: {name} ({operator_id})")

    def get_escalation_stats(self) -> Dict:
        """Get escalation statistics"""
        return {
            "queue_size": self.escalation_queue.qsize(),
            "resolutions_completed": len(self.resolution_history),
            "available_operators": len(self.available_operators),
            "avg_resolution_time": self._calculate_avg_resolution_time()
        }

    def _calculate_avg_resolution_time(self) -> float:
        """Calculate average resolution time"""
        if len(self.resolution_history) < 2:
            return 0.0

        total_time = 0
        count = 0

        for i in range(1, len(self.resolution_history)):
            current = self.resolution_history[i]
            previous = self.resolution_history[i-1]

            time_diff = (current.resolved_at - previous.resolved_at).seconds
            total_time += time_diff
            count += 1

        return total_time / count if count > 0 else 0.0

# Factory function for easy creation
def create_uncertainty_detector(config: Optional[Dict] = None) -> UncertaintyDetector:
    """Create uncertainty detector with configuration"""
    return UncertaintyDetector(config)

def create_escalation_manager(config: Optional[Dict] = None) -> HumanEscalationManager:
    """Create human escalation manager"""
    manager = HumanEscalationManager(config)
    asyncio.create_task(manager.start())
    return manager

# Example usage and testing
async def test_uncertainty_detection():
    """Test the uncertainty detection system"""
    print("🔍 === Testing Uncertainty Detection System ===\n")

    # Create detector
    detector = create_uncertainty_detector({
        "confidence_threshold": 0.6,
        "ambiguity_threshold": 0.4
    })

    # Register a human operator for testing
    escalation_manager = create_escalation_manager()
    escalation_manager.register_operator("operator_1", "Test Operator", ["general", "business"])

    # Test cases
    test_cases = [
        {
            "name": "Low Confidence Response",
            "user_input": "I need help with something",
            "ai_response": "I think maybe I can help with that, but I'm not entirely sure what you need.",
            "context": {"recent_messages": []}
        },
        {
            "name": "Ambiguous Input",
            "user_input": "Can you handle this for me?",
            "ai_response": "Sure, I'd be happy to help with this.",
            "context": {"recent_messages": []}
        },
        {
            "name": "Business Critical",
            "user_input": "I want to delete all my customer data",
            "ai_response": "I understand you want to delete customer data. This is a critical operation.",
            "context": {"recent_messages": []}
        },
        {
            "name": "Ethical Dilemma",
            "user_input": "I want to fire my employee through the system",
            "ai_response": "I can help you with employee management tasks.",
            "context": {"recent_messages": []}
        }
    ]

    for test_case in test_cases:
        print(f"🧪 Testing: {test_case['name']}")

        signals = await detector.analyze_response_uncertainty(
            test_case["user_input"],
            test_case["ai_response"],
            test_case["context"],
            "test-customer",
            "whatsapp"
        )

        print(f"  User: {test_case['user_input']}")
        print(f"  AI: {test_case['ai_response'][:50]}...")
        print(f"  Signals detected: {len(signals)}")

        for signal in signals:
            print(f"    - {signal.uncertainty_type.value} (priority: {signal.priority_level})")
            print(f"      Reason: {signal.escalation_reason}")

            # Test escalation
            if signal.priority_level in ["high", "critical"]:
                resolution = await escalation_manager.escalate_uncertainty(signal)
                if resolution:
                    print(f"      Human resolution: {resolution.judgment}")
                    print(f"      Final response: {resolution.final_response[:50]}...")

        print()

    # Show stats
    stats = escalation_manager.get_escalation_stats()
    print("📊 Escalation Statistics:")
    print(f"  - Queue size: {stats['queue_size']}")
    print(f"  - Resolutions completed: {stats['resolutions_completed']}")
    print(f"  - Available operators: {stats['available_operators']}")

    await escalation_manager.stop()
    print("\n✅ Uncertainty detection test completed!")

if __name__ == "__main__":
    asyncio.run(test_uncertainty_detection())