"""
Voice Quality Analyzer
Comprehensive quality assessment for voice interactions
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import statistics
import json
import re

# Analysis imports
import numpy as np
from textstat import flesch_reading_ease, lexicon_count
from langdetect import detect, detect_langs

# Monitoring imports
from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

# Local imports
from .models import VoiceQualityMetrics, PersonalityConsistencyScore
from ..monitoring.voice_performance_monitor import VoiceInteractionMetrics

logger = structlog.get_logger(__name__)

@dataclass
class QualityAssessmentResult:
    """Result of quality assessment"""
    interaction_id: str
    customer_id: str
    assessment_timestamp: datetime
    
    # Quality scores
    overall_quality: float  # 0-1
    audio_quality: float
    transcription_quality: float
    response_quality: float
    user_experience_quality: float
    
    # Detailed analysis
    quality_metrics: VoiceQualityMetrics
    issues_identified: List[str]
    improvement_suggestions: List[str]
    quality_trend: str  # improving, stable, declining
    
    # Benchmarking
    performance_vs_baseline: float  # -1 to 1
    percentile_ranking: float  # 0-100
    
    # Confidence
    assessment_confidence: float  # 0-1

@dataclass
class QualityBenchmark:
    """Quality benchmark standards"""
    benchmark_id: str
    benchmark_name: str
    created_date: datetime
    
    # Quality thresholds
    minimum_acceptable: Dict[str, float]  # metric -> threshold
    target_performance: Dict[str, float]  # metric -> target
    excellent_performance: Dict[str, float]  # metric -> excellent
    
    # SLA requirements
    sla_requirements: Dict[str, float]
    
    # Context
    applies_to: str  # all, customer_segment, interaction_type
    context_filters: Dict[str, Any]

class VoiceQualityAnalyzer:
    """
    Comprehensive voice quality analysis system
    
    Features:
    - Real-time quality assessment across all dimensions
    - Audio quality and transcription accuracy analysis
    - Response quality and relevance evaluation
    - User experience and satisfaction measurement
    - Personality consistency tracking
    - Quality trend analysis and prediction
    - Benchmarking against performance standards
    - Automated quality improvement recommendations
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Quality configuration
        self.quality_assessment_enabled = self.config.get("quality_assessment_enabled", True)
        self.real_time_analysis = self.config.get("real_time_analysis", True)
        self.store_audio_samples = self.config.get("store_audio_samples", False)
        
        # Quality thresholds
        self.quality_thresholds = {
            "minimum_overall": self.config.get("minimum_overall_quality", 0.7),
            "target_overall": self.config.get("target_overall_quality", 0.85),
            "excellent_overall": self.config.get("excellent_overall_quality", 0.95),
            "transcription_accuracy": self.config.get("transcription_accuracy_threshold", 0.9),
            "response_relevance": self.config.get("response_relevance_threshold", 0.8),
            "audio_clarity": self.config.get("audio_clarity_threshold", 0.85)
        }
        
        # Data storage
        self.quality_assessments: deque = deque(maxlen=5000)
        self.customer_quality_history: Dict[str, List[QualityAssessmentResult]] = defaultdict(list)
        self.quality_benchmarks: List[QualityBenchmark] = []
        self.personality_consistency_scores: Dict[str, List[PersonalityConsistencyScore]] = defaultdict(list)
        
        # Analysis models and tools
        self.sentiment_analyzer = None  # Would initialize sentiment analysis
        self.readability_analyzer = None  # Would initialize readability analysis
        self.audio_analyzer = None  # Would initialize audio quality analysis
        
        # Quality trends
        self.quality_trends = {
            "overall_trend": "stable",
            "audio_trend": "stable",
            "transcription_trend": "stable",
            "response_trend": "stable"
        }
        
        # Performance tracking
        self.analysis_stats = {
            "total_assessments": 0,
            "quality_issues_found": 0,
            "improvement_suggestions_generated": 0,
            "average_assessment_time_ms": 0
        }
        
        self.setup_metrics()
        self._initialize_default_benchmarks()
        logger.info("Voice quality analyzer initialized")
    
    def setup_metrics(self):
        """Setup Prometheus metrics for quality analysis"""
        self.quality_score_histogram = Histogram(
            'voice_quality_score',
            'Voice interaction quality scores',
            ['quality_dimension', 'customer_segment', 'time_bucket']
        )
        
        self.quality_issues_counter = Counter(
            'voice_quality_issues_total',
            'Total quality issues detected',
            ['issue_type', 'severity', 'customer_segment']
        )
        
        self.transcription_accuracy_gauge = Gauge(
            'voice_transcription_accuracy',
            'Speech-to-text transcription accuracy',
            ['language', 'customer_segment']
        )
        
        self.response_relevance_gauge = Gauge(
            'voice_response_relevance',
            'Response relevance and quality score',
            ['interaction_type', 'customer_segment']
        )
        
        self.personality_consistency_gauge = Gauge(
            'voice_personality_consistency',
            'EA personality consistency score',
            ['customer_id', 'time_period']
        )
    
    def _initialize_default_benchmarks(self):
        """Initialize default quality benchmarks"""
        
        # Standard benchmark for all interactions
        standard_benchmark = QualityBenchmark(
            benchmark_id="standard_voice_quality",
            benchmark_name="Standard Voice Interaction Quality",
            created_date=datetime.now(),
            minimum_acceptable={
                "overall_quality": 0.7,
                "audio_clarity": 0.8,
                "transcription_accuracy": 0.9,
                "response_relevance": 0.75,
                "response_coherence": 0.8,
                "latency_score": 0.8
            },
            target_performance={
                "overall_quality": 0.85,
                "audio_clarity": 0.9,
                "transcription_accuracy": 0.95,
                "response_relevance": 0.85,
                "response_coherence": 0.9,
                "latency_score": 0.9
            },
            excellent_performance={
                "overall_quality": 0.95,
                "audio_clarity": 0.98,
                "transcription_accuracy": 0.98,
                "response_relevance": 0.95,
                "response_coherence": 0.95,
                "latency_score": 0.95
            },
            sla_requirements={
                "response_time": 2.0,  # seconds
                "success_rate": 0.95,
                "availability": 0.999
            },
            applies_to="all",
            context_filters={}
        )
        
        self.quality_benchmarks.append(standard_benchmark)
        
        # High-value customer benchmark
        premium_benchmark = QualityBenchmark(
            benchmark_id="premium_customer_quality",
            benchmark_name="Premium Customer Quality Standards",
            created_date=datetime.now(),
            minimum_acceptable={
                "overall_quality": 0.8,
                "audio_clarity": 0.85,
                "transcription_accuracy": 0.93,
                "response_relevance": 0.8,
                "response_coherence": 0.85,
                "latency_score": 0.85
            },
            target_performance={
                "overall_quality": 0.9,
                "audio_clarity": 0.93,
                "transcription_accuracy": 0.97,
                "response_relevance": 0.9,
                "response_coherence": 0.93,
                "latency_score": 0.93
            },
            excellent_performance={
                "overall_quality": 0.97,
                "audio_clarity": 0.99,
                "transcription_accuracy": 0.99,
                "response_relevance": 0.97,
                "response_coherence": 0.97,
                "latency_score": 0.97
            },
            sla_requirements={
                "response_time": 1.5,  # seconds
                "success_rate": 0.98,
                "availability": 0.9995
            },
            applies_to="customer_segment",
            context_filters={"customer_segment": "high_value"}
        )
        
        self.quality_benchmarks.append(premium_benchmark)
    
    async def analyze_interaction_quality(
        self,
        metrics: VoiceInteractionMetrics,
        conversation_context: Dict[str, Any] = None,
        audio_data: Optional[bytes] = None
    ) -> QualityAssessmentResult:
        """Comprehensive quality analysis of voice interaction"""
        
        start_time = datetime.now()
        
        try:
            # Extract conversation data
            context = conversation_context or {}
            message_text = context.get("message_text", "")
            response_text = context.get("response_text", "")
            
            # Assess audio quality
            audio_quality_score = await self._assess_audio_quality(
                metrics, audio_data, context
            )
            
            # Assess transcription quality
            transcription_quality_score = await self._assess_transcription_quality(
                message_text, metrics, context
            )
            
            # Assess response quality
            response_quality_score = await self._assess_response_quality(
                message_text, response_text, metrics, context
            )
            
            # Assess user experience
            ux_quality_score = await self._assess_user_experience(
                metrics, context
            )
            
            # Create comprehensive quality metrics
            quality_metrics = VoiceQualityMetrics(
                interaction_id=metrics.interaction_id,
                customer_id=metrics.customer_id,
                assessment_timestamp=datetime.now(),
                audio_clarity_score=audio_quality_score["clarity"],
                noise_level=audio_quality_score["noise_level"],
                audio_compression_quality=audio_quality_score["compression"],
                transcription_accuracy=transcription_quality_score["accuracy"],
                language_detection_confidence=transcription_quality_score["language_confidence"],
                accent_handling_score=transcription_quality_score["accent_handling"],
                response_relevance=response_quality_score["relevance"],
                response_completeness=response_quality_score["completeness"],
                response_coherence=response_quality_score["coherence"],
                grammar_accuracy=response_quality_score["grammar"],
                vocabulary_appropriateness=response_quality_score["vocabulary"],
                cultural_sensitivity=response_quality_score["cultural_sensitivity"],
                latency_score=ux_quality_score["latency"],
                system_reliability=ux_quality_score["reliability"],
                overall_quality_score=0.0,  # Will be calculated
                quality_issues=[],
                improvement_suggestions=[]
            )
            
            # Calculate overall quality score
            quality_metrics.overall_quality_score = self._calculate_overall_quality(quality_metrics)
            
            # Identify issues and suggestions
            issues, suggestions = await self._identify_quality_issues(quality_metrics, metrics)
            quality_metrics.quality_issues = issues
            quality_metrics.improvement_suggestions = suggestions
            
            # Get quality trend for customer
            quality_trend = await self._analyze_quality_trend(metrics.customer_id, quality_metrics)
            
            # Benchmark against standards
            performance_vs_baseline, percentile = await self._benchmark_quality(
                metrics.customer_id, quality_metrics
            )
            
            # Create assessment result
            assessment = QualityAssessmentResult(
                interaction_id=metrics.interaction_id,
                customer_id=metrics.customer_id,
                assessment_timestamp=datetime.now(),
                overall_quality=quality_metrics.overall_quality_score,
                audio_quality=statistics.mean([
                    quality_metrics.audio_clarity_score,
                    1.0 - quality_metrics.noise_level,  # Lower noise is better
                    quality_metrics.audio_compression_quality
                ]),
                transcription_quality=statistics.mean([
                    quality_metrics.transcription_accuracy,
                    quality_metrics.language_detection_confidence,
                    quality_metrics.accent_handling_score
                ]),
                response_quality=statistics.mean([
                    quality_metrics.response_relevance,
                    quality_metrics.response_completeness,
                    quality_metrics.response_coherence,
                    quality_metrics.grammar_accuracy
                ]),
                user_experience_quality=statistics.mean([
                    quality_metrics.latency_score,
                    quality_metrics.system_reliability
                ]),
                quality_metrics=quality_metrics,
                issues_identified=issues,
                improvement_suggestions=suggestions,
                quality_trend=quality_trend,
                performance_vs_baseline=performance_vs_baseline,
                percentile_ranking=percentile,
                assessment_confidence=self._calculate_assessment_confidence(quality_metrics, context)
            )
            
            # Store assessment
            self.quality_assessments.append(assessment)
            self.customer_quality_history[metrics.customer_id].append(assessment)
            
            # Keep customer history manageable
            self.customer_quality_history[metrics.customer_id] = (
                self.customer_quality_history[metrics.customer_id][-50:]
            )
            
            # Update metrics
            customer_segment = self._get_customer_segment(metrics.customer_id)
            time_bucket = metrics.timestamp.strftime("%Y-%m-%d-%H")
            
            self.quality_score_histogram.labels(
                quality_dimension="overall",
                customer_segment=customer_segment,
                time_bucket=time_bucket
            ).observe(assessment.overall_quality)
            
            self.transcription_accuracy_gauge.labels(
                language=metrics.detected_language,
                customer_segment=customer_segment
            ).set(quality_metrics.transcription_accuracy)
            
            # Record quality issues
            for issue in issues:
                issue_severity = self._get_issue_severity(issue)
                self.quality_issues_counter.labels(
                    issue_type=issue.replace(" ", "_").lower(),
                    severity=issue_severity,
                    customer_segment=customer_segment
                ).inc()
            
            # Update analysis stats
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.analysis_stats["total_assessments"] += 1
            self.analysis_stats["quality_issues_found"] += len(issues)
            self.analysis_stats["improvement_suggestions_generated"] += len(suggestions)
            self.analysis_stats["average_assessment_time_ms"] = (
                (self.analysis_stats["average_assessment_time_ms"] * 
                 (self.analysis_stats["total_assessments"] - 1) + processing_time) /
                self.analysis_stats["total_assessments"]
            )
            
            logger.info("Quality assessment completed",
                       interaction_id=metrics.interaction_id,
                       overall_quality=assessment.overall_quality,
                       issues_count=len(issues),
                       processing_time_ms=processing_time)
            
            return assessment
            
        except Exception as e:
            logger.error("Error during quality assessment",
                        interaction_id=metrics.interaction_id,
                        error=str(e))
            raise
    
    async def _assess_audio_quality(
        self,
        metrics: VoiceInteractionMetrics,
        audio_data: Optional[bytes],
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Assess audio quality aspects"""
        
        audio_quality = {}
        
        # Audio clarity assessment (heuristic-based for now)
        if metrics.audio_input_size_bytes > 0:
            # Heuristic: larger audio files for same duration typically indicate better quality
            duration_estimate = metrics.speech_to_text_time or 5.0  # Default 5 seconds
            bytes_per_second = metrics.audio_input_size_bytes / duration_estimate
            
            # Typical good quality: 16kHz * 16bit = 32KB/s
            if bytes_per_second >= 30000:  # Good quality
                audio_quality["clarity"] = 0.9
            elif bytes_per_second >= 16000:  # Acceptable quality
                audio_quality["clarity"] = 0.8
            else:  # Lower quality
                audio_quality["clarity"] = 0.7
        else:
            audio_quality["clarity"] = 0.5  # Unknown quality
        
        # Noise level assessment (placeholder - would use actual audio analysis)
        # For now, infer from transcription quality
        if metrics.success and metrics.transcript_length > 0:
            # If transcription was successful, likely low noise
            audio_quality["noise_level"] = 0.1  # Low noise
        elif not metrics.success:
            # Failed transcription might indicate high noise
            audio_quality["noise_level"] = 0.6  # Higher noise
        else:
            audio_quality["noise_level"] = 0.3  # Moderate noise
        
        # Compression quality (heuristic)
        if metrics.audio_output_size_bytes > 0 and metrics.response_length > 0:
            # Estimate compression efficiency
            chars_per_byte = metrics.response_length / metrics.audio_output_size_bytes
            
            if chars_per_byte > 0.1:  # Good compression
                audio_quality["compression"] = 0.9
            elif chars_per_byte > 0.05:  # Acceptable compression
                audio_quality["compression"] = 0.8
            else:  # Poor compression
                audio_quality["compression"] = 0.7
        else:
            audio_quality["compression"] = 0.8  # Default
        
        return audio_quality
    
    async def _assess_transcription_quality(
        self,
        message_text: str,
        metrics: VoiceInteractionMetrics,
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Assess speech-to-text transcription quality"""
        
        transcription_quality = {}
        
        # Transcription accuracy (heuristic-based)
        if not message_text or len(message_text.strip()) == 0:
            transcription_quality["accuracy"] = 0.0
        elif metrics.success:
            # Successful interaction suggests good transcription
            # Check for common transcription errors
            error_indicators = [
                "unintelligible", "[inaudible]", "???", "***",
                "unclear", "mumbled"
            ]
            
            has_errors = any(indicator in message_text.lower() for indicator in error_indicators)
            
            if has_errors:
                transcription_quality["accuracy"] = 0.6
            elif len(message_text) < 10:  # Very short, might be incomplete
                transcription_quality["accuracy"] = 0.7
            else:
                transcription_quality["accuracy"] = 0.95
        else:
            # Failed interaction might indicate transcription issues
            transcription_quality["accuracy"] = 0.3
        
        # Language detection confidence
        if message_text:
            try:
                # Use langdetect library
                detected_langs = detect_langs(message_text)
                if detected_langs:
                    confidence = detected_langs[0].prob
                    expected_lang = metrics.detected_language
                    detected_lang = detected_langs[0].lang
                    
                    # Check if detected language matches expected
                    if detected_lang == expected_lang or detected_lang[:2] == expected_lang:
                        transcription_quality["language_confidence"] = confidence
                    else:
                        # Language mismatch reduces confidence
                        transcription_quality["language_confidence"] = confidence * 0.7
                else:
                    transcription_quality["language_confidence"] = 0.5
            except:
                # Fallback if language detection fails
                transcription_quality["language_confidence"] = 0.8
        else:
            transcription_quality["language_confidence"] = 0.0
        
        # Accent handling (heuristic based on transcription success)
        if transcription_quality["accuracy"] > 0.9 and metrics.detected_language != "en":
            # Good transcription of non-English suggests good accent handling
            transcription_quality["accent_handling"] = 0.9
        elif transcription_quality["accuracy"] > 0.8:
            transcription_quality["accent_handling"] = 0.8
        else:
            transcription_quality["accent_handling"] = 0.7
        
        return transcription_quality
    
    async def _assess_response_quality(
        self,
        message_text: str,
        response_text: str,
        metrics: VoiceInteractionMetrics,
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Assess response quality and relevance"""
        
        response_quality = {}
        
        if not response_text or len(response_text.strip()) == 0:
            return {
                "relevance": 0.0,
                "completeness": 0.0,
                "coherence": 0.0,
                "grammar": 0.0,
                "vocabulary": 0.0,
                "cultural_sensitivity": 0.0
            }
        
        # Response relevance (keyword-based heuristic)
        relevance_score = await self._calculate_response_relevance(message_text, response_text)
        response_quality["relevance"] = relevance_score
        
        # Response completeness
        if len(response_text) < 10:  # Very short response
            response_quality["completeness"] = 0.3
        elif len(response_text) < 50:  # Short but potentially complete
            response_quality["completeness"] = 0.7
        elif len(response_text) < 200:  # Good length
            response_quality["completeness"] = 0.9
        else:  # Very long, might be too verbose
            response_quality["completeness"] = 0.8
        
        # Response coherence (basic text analysis)
        coherence_score = await self._assess_response_coherence(response_text)
        response_quality["coherence"] = coherence_score
        
        # Grammar accuracy (basic checks)
        grammar_score = await self._assess_grammar_quality(response_text)
        response_quality["grammar"] = grammar_score
        
        # Vocabulary appropriateness
        vocabulary_score = await self._assess_vocabulary_quality(response_text, context)
        response_quality["vocabulary"] = vocabulary_score
        
        # Cultural sensitivity (basic keyword checks)
        cultural_score = await self._assess_cultural_sensitivity(response_text, context)
        response_quality["cultural_sensitivity"] = cultural_score
        
        return response_quality
    
    async def _calculate_response_relevance(self, message_text: str, response_text: str) -> float:
        """Calculate response relevance to input message"""
        
        if not message_text or not response_text:
            return 0.0
        
        # Simple keyword overlap approach
        message_words = set(message_text.lower().split())
        response_words = set(response_text.lower().split())
        
        # Remove common stop words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", 
            "of", "with", "by", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could", "should"
        }
        
        message_content_words = message_words - stop_words
        response_content_words = response_words - stop_words
        
        if not message_content_words:
            return 0.5  # Neutral if no content words in message
        
        # Calculate overlap
        overlap = len(message_content_words.intersection(response_content_words))
        overlap_ratio = overlap / len(message_content_words)
        
        # Boost score if response addresses the message
        contextual_indicators = [
            "yes", "no", "sure", "certainly", "of course", "absolutely",
            "however", "but", "although", "because", "since", "therefore"
        ]
        
        has_contextual_response = any(
            indicator in response_text.lower() 
            for indicator in contextual_indicators
        )
        
        relevance_score = overlap_ratio * 0.7 + (0.3 if has_contextual_response else 0.0)
        
        return min(1.0, relevance_score + 0.2)  # Baseline boost
    
    async def _assess_response_coherence(self, response_text: str) -> float:
        """Assess logical flow and coherence of response"""
        
        # Basic coherence checks
        sentences = response_text.split('.')
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= 1:
            return 0.9  # Single sentence is typically coherent
        
        coherence_score = 0.8  # Start with good baseline
        
        # Check for basic coherence issues
        coherence_issues = [
            "but but", "and and", "the the", "is is", "are are",  # Repetition
            "however but", "although but",  # Contradictory connectors
        ]
        
        response_lower = response_text.lower()
        issues_found = sum(1 for issue in coherence_issues if issue in response_lower)
        
        # Penalize for issues
        coherence_score -= issues_found * 0.1
        
        # Check sentence transitions
        transition_words = [
            "however", "therefore", "furthermore", "moreover", "additionally",
            "consequently", "nevertheless", "nonetheless", "meanwhile", "subsequently"
        ]
        
        has_transitions = any(word in response_lower for word in transition_words)
        if has_transitions and len(sentences) > 2:
            coherence_score += 0.1  # Bonus for good transitions
        
        return max(0.0, min(1.0, coherence_score))
    
    async def _assess_grammar_quality(self, response_text: str) -> float:
        """Assess grammatical correctness of response"""
        
        # Basic grammar checks (would use proper grammar checking in production)
        grammar_score = 0.9  # Start optimistic
        
        # Common grammar issues to check
        grammar_issues = [
            r"\b(is|are) (is|are)\b",  # Double auxiliary verbs
            r"\b(a|an) (a|an)\b",      # Double articles
            r"\b(the) (the)\b",        # Double definite articles
            r"\bMe am\b",              # Subject-verb disagreement
            r"\bI is\b",               # Subject-verb disagreement
            r"\byou am\b",             # Subject-verb disagreement
        ]
        
        issues_found = 0
        for pattern in grammar_issues:
            if re.search(pattern, response_text, re.IGNORECASE):
                issues_found += 1
        
        # Penalize for grammar issues
        grammar_score -= issues_found * 0.15
        
        # Check for proper capitalization
        sentences = [s.strip() for s in response_text.split('.') if s.strip()]
        capitalization_issues = sum(
            1 for sentence in sentences 
            if sentence and not sentence[0].isupper()
        )
        
        if capitalization_issues > 0:
            grammar_score -= capitalization_issues * 0.05
        
        return max(0.0, min(1.0, grammar_score))
    
    async def _assess_vocabulary_quality(self, response_text: str, context: Dict[str, Any]) -> float:
        """Assess appropriateness of vocabulary used"""
        
        # Basic vocabulary assessment
        vocabulary_score = 0.8  # Good baseline
        
        # Check for inappropriate language (basic filter)
        inappropriate_words = [
            "damn", "shit", "fuck", "bitch", "asshole", "stupid", "idiot",
            "hate", "sucks", "crap", "bullshit"
        ]
        
        response_lower = response_text.lower()
        inappropriate_count = sum(
            1 for word in inappropriate_words 
            if word in response_lower
        )
        
        if inappropriate_count > 0:
            vocabulary_score -= inappropriate_count * 0.2
        
        # Check for overly complex vocabulary (readability)
        try:
            reading_ease = flesch_reading_ease(response_text)
            word_count = lexicon_count(response_text)
            
            # Adjust for readability
            if reading_ease < 30:  # Very difficult
                vocabulary_score -= 0.1
            elif reading_ease > 90:  # Very easy (might be too simple)
                if word_count > 20:  # Only penalize if response is substantial
                    vocabulary_score -= 0.05
        except:
            pass  # Skip readability check if it fails
        
        # Bonus for professional vocabulary in business context
        professional_indicators = [
            "business", "strategy", "analysis", "optimize", "efficient",
            "professional", "strategic", "implementation", "solution"
        ]
        
        if any(word in response_lower for word in professional_indicators):
            vocabulary_score += 0.1
        
        return max(0.0, min(1.0, vocabulary_score))
    
    async def _assess_cultural_sensitivity(self, response_text: str, context: Dict[str, Any]) -> float:
        """Assess cultural sensitivity of response"""
        
        # Basic cultural sensitivity assessment
        sensitivity_score = 0.9  # Start optimistic
        
        # Check for potentially insensitive content
        insensitive_terms = [
            "weird", "strange", "foreign", "exotic", "primitive",
            "backwards", "uncivilized", "third world"
        ]
        
        response_lower = response_text.lower()
        issues_found = sum(
            1 for term in insensitive_terms 
            if term in response_lower
        )
        
        if issues_found > 0:
            sensitivity_score -= issues_found * 0.2
        
        # Check for inclusive language
        inclusive_indicators = [
            "everyone", "all people", "inclusive", "diverse", "respectful",
            "understanding", "cultural", "global", "international"
        ]
        
        if any(indicator in response_lower for indicator in inclusive_indicators):
            sensitivity_score += 0.05
        
        return max(0.0, min(1.0, sensitivity_score))
    
    async def _assess_user_experience(
        self,
        metrics: VoiceInteractionMetrics,
        context: Dict[str, Any]
    ) -> Dict[str, float]:
        """Assess user experience aspects"""
        
        ux_quality = {}
        
        # Latency/response time quality
        if metrics.total_response_time <= 1.0:
            ux_quality["latency"] = 1.0
        elif metrics.total_response_time <= 2.0:
            ux_quality["latency"] = 0.9
        elif metrics.total_response_time <= 3.0:
            ux_quality["latency"] = 0.7
        else:
            # Penalize exponentially for very slow responses
            ux_quality["latency"] = max(0.1, 0.7 - (metrics.total_response_time - 3.0) * 0.2)
        
        # System reliability (based on success/failure)
        if metrics.success:
            ux_quality["reliability"] = 0.95
        elif metrics.error_type:
            # Different error types have different reliability scores
            if "timeout" in metrics.error_type.lower():
                ux_quality["reliability"] = 0.3
            elif "network" in metrics.error_type.lower():
                ux_quality["reliability"] = 0.5
            elif "processing" in metrics.error_type.lower():
                ux_quality["reliability"] = 0.4
            else:
                ux_quality["reliability"] = 0.2
        else:
            ux_quality["reliability"] = 0.6  # Unknown error
        
        return ux_quality
    
    def _calculate_overall_quality(self, quality_metrics: VoiceQualityMetrics) -> float:
        """Calculate weighted overall quality score"""
        
        # Quality dimension weights
        weights = {
            "audio": 0.20,
            "transcription": 0.25,
            "response": 0.35,
            "experience": 0.20
        }
        
        # Calculate component scores
        audio_score = statistics.mean([
            quality_metrics.audio_clarity_score,
            1.0 - quality_metrics.noise_level,  # Lower noise is better
            quality_metrics.audio_compression_quality
        ])
        
        transcription_score = statistics.mean([
            quality_metrics.transcription_accuracy,
            quality_metrics.language_detection_confidence,
            quality_metrics.accent_handling_score
        ])
        
        response_score = statistics.mean([
            quality_metrics.response_relevance,
            quality_metrics.response_completeness,
            quality_metrics.response_coherence,
            quality_metrics.grammar_accuracy,
            quality_metrics.vocabulary_appropriateness,
            quality_metrics.cultural_sensitivity
        ])
        
        experience_score = statistics.mean([
            quality_metrics.latency_score,
            quality_metrics.system_reliability
        ])
        
        # Weighted overall score
        overall_score = (
            audio_score * weights["audio"] +
            transcription_score * weights["transcription"] +
            response_score * weights["response"] +
            experience_score * weights["experience"]
        )
        
        return min(1.0, max(0.0, overall_score))
    
    async def _identify_quality_issues(
        self,
        quality_metrics: VoiceQualityMetrics,
        metrics: VoiceInteractionMetrics
    ) -> Tuple[List[str], List[str]]:
        """Identify quality issues and generate improvement suggestions"""
        
        issues = []
        suggestions = []
        
        # Audio quality issues
        if quality_metrics.audio_clarity_score < 0.7:
            issues.append("Low audio clarity detected")
            suggestions.append("Improve audio input quality or check microphone settings")
        
        if quality_metrics.noise_level > 0.5:
            issues.append("High background noise level")
            suggestions.append("Use noise cancellation or record in quieter environment")
        
        # Transcription issues
        if quality_metrics.transcription_accuracy < 0.8:
            issues.append("Poor transcription accuracy")
            suggestions.append("Speak more clearly or check audio quality")
        
        if quality_metrics.language_detection_confidence < 0.7:
            issues.append("Uncertain language detection")
            suggestions.append("Specify language preference or use more consistent language")
        
        # Response quality issues
        if quality_metrics.response_relevance < 0.7:
            issues.append("Response not relevant to input")
            suggestions.append("Improve context understanding or provide more specific input")
        
        if quality_metrics.response_completeness < 0.6:
            issues.append("Response appears incomplete")
            suggestions.append("Ensure response addresses all aspects of the question")
        
        if quality_metrics.response_coherence < 0.7:
            issues.append("Response lacks coherence")
            suggestions.append("Improve response structure and logical flow")
        
        if quality_metrics.grammar_accuracy < 0.8:
            issues.append("Grammar errors detected")
            suggestions.append("Review and improve grammar checking algorithms")
        
        # Experience issues
        if quality_metrics.latency_score < 0.8:
            issues.append("Slow response time")
            suggestions.append("Optimize processing pipeline for faster responses")
        
        if quality_metrics.system_reliability < 0.9:
            issues.append("System reliability concerns")
            suggestions.append("Investigate system errors and improve error handling")
        
        # Overall quality issues
        if quality_metrics.overall_quality_score < 0.7:
            issues.append("Overall quality below acceptable threshold")
            suggestions.append("Comprehensive quality improvement needed across multiple dimensions")
        
        return issues, suggestions
    
    async def _analyze_quality_trend(
        self,
        customer_id: str,
        current_metrics: VoiceQualityMetrics
    ) -> str:
        """Analyze quality trend for customer"""
        
        customer_history = self.customer_quality_history.get(customer_id, [])
        
        if len(customer_history) < 3:
            return "insufficient_data"
        
        # Get recent quality scores
        recent_scores = [assessment.overall_quality for assessment in customer_history[-5:]]
        older_scores = [assessment.overall_quality for assessment in customer_history[-10:-5]]
        
        if not older_scores:
            return "stable"
        
        recent_avg = statistics.mean(recent_scores)
        older_avg = statistics.mean(older_scores)
        
        change = recent_avg - older_avg
        
        if change > 0.05:
            return "improving"
        elif change < -0.05:
            return "declining"
        else:
            return "stable"
    
    async def _benchmark_quality(
        self,
        customer_id: str,
        quality_metrics: VoiceQualityMetrics
    ) -> Tuple[float, float]:
        """Benchmark quality against standards"""
        
        # Get applicable benchmark
        benchmark = self._get_applicable_benchmark(customer_id)
        
        if not benchmark:
            return 0.0, 50.0  # Neutral if no benchmark
        
        # Compare against target performance
        target_overall = benchmark.target_performance.get("overall_quality", 0.85)
        performance_vs_baseline = (quality_metrics.overall_quality_score - target_overall) / target_overall
        
        # Calculate percentile ranking (simplified)
        recent_assessments = list(self.quality_assessments)[-100:]  # Last 100 assessments
        if recent_assessments:
            scores = [assessment.overall_quality for assessment in recent_assessments]
            scores.sort()
            
            # Find position of current score
            position = sum(1 for score in scores if score < quality_metrics.overall_quality_score)
            percentile = (position / len(scores)) * 100
        else:
            percentile = 50.0  # Neutral if no data
        
        return max(-1.0, min(1.0, performance_vs_baseline)), percentile
    
    def _get_applicable_benchmark(self, customer_id: str) -> Optional[QualityBenchmark]:
        """Get applicable quality benchmark for customer"""
        
        customer_segment = self._get_customer_segment(customer_id)
        
        # Find most specific applicable benchmark
        applicable_benchmarks = []
        
        for benchmark in self.quality_benchmarks:
            if benchmark.applies_to == "all":
                applicable_benchmarks.append((0, benchmark))  # Lower priority
            elif (benchmark.applies_to == "customer_segment" and
                  benchmark.context_filters.get("customer_segment") == customer_segment):
                applicable_benchmarks.append((1, benchmark))  # Higher priority
        
        if applicable_benchmarks:
            # Return highest priority benchmark
            applicable_benchmarks.sort(key=lambda x: x[0], reverse=True)
            return applicable_benchmarks[0][1]
        
        return None
    
    def _calculate_assessment_confidence(
        self,
        quality_metrics: VoiceQualityMetrics,
        context: Dict[str, Any]
    ) -> float:
        """Calculate confidence in quality assessment"""
        
        confidence_factors = []
        
        # Audio data availability
        if context.get("audio_data_available", False):
            confidence_factors.append(0.9)
        else:
            confidence_factors.append(0.7)
        
        # Text length (more text = more confident assessment)
        message_length = len(context.get("message_text", ""))
        response_length = len(context.get("response_text", ""))
        
        text_confidence = min(1.0, (message_length + response_length) / 100)
        confidence_factors.append(text_confidence)
        
        # Language detection confidence
        confidence_factors.append(quality_metrics.language_detection_confidence)
        
        # System success (successful interactions are easier to assess)
        if context.get("interaction_success", True):
            confidence_factors.append(0.9)
        else:
            confidence_factors.append(0.6)
        
        return statistics.mean(confidence_factors)
    
    def _get_customer_segment(self, customer_id: str) -> str:
        """Get customer segment for quality analysis"""
        
        # Simple segmentation based on quality history
        customer_history = self.customer_quality_history.get(customer_id, [])
        
        if not customer_history:
            return "new"
        
        if len(customer_history) >= 20:
            avg_quality = statistics.mean([assessment.overall_quality for assessment in customer_history])
            
            if avg_quality >= 0.9:
                return "high_value"
            elif avg_quality >= 0.8:
                return "engaged"
            else:
                return "active"
        else:
            return "new"
    
    def _get_issue_severity(self, issue: str) -> str:
        """Determine severity of quality issue"""
        
        critical_keywords = ["critical", "failed", "error", "broken"]
        high_keywords = ["poor", "low", "bad", "unacceptable"]
        medium_keywords = ["slow", "delayed", "unclear", "incomplete"]
        
        issue_lower = issue.lower()
        
        if any(keyword in issue_lower for keyword in critical_keywords):
            return "critical"
        elif any(keyword in issue_lower for keyword in high_keywords):
            return "high"
        elif any(keyword in issue_lower for keyword in medium_keywords):
            return "medium"
        else:
            return "low"
    
    def get_quality_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive quality dashboard data"""
        
        recent_assessments = list(self.quality_assessments)[-100:] if self.quality_assessments else []
        
        if not recent_assessments:
            return {
                "status": "no_data",
                "message": "No quality assessments available"
            }
        
        # Overall quality metrics
        overall_scores = [assessment.overall_quality for assessment in recent_assessments]
        avg_overall_quality = statistics.mean(overall_scores)
        
        # Quality dimension breakdown
        audio_scores = [assessment.audio_quality for assessment in recent_assessments]
        transcription_scores = [assessment.transcription_quality for assessment in recent_assessments]
        response_scores = [assessment.response_quality for assessment in recent_assessments]
        ux_scores = [assessment.user_experience_quality for assessment in recent_assessments]
        
        # Quality issues analysis
        all_issues = []
        for assessment in recent_assessments:
            all_issues.extend(assessment.issues_identified)
        
        issue_counts = defaultdict(int)
        for issue in all_issues:
            issue_counts[issue] += 1
        
        top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Quality trends
        if len(recent_assessments) >= 20:
            recent_quality = statistics.mean([a.overall_quality for a in recent_assessments[-10:]])
            older_quality = statistics.mean([a.overall_quality for a in recent_assessments[-20:-10]])
            quality_trend = "improving" if recent_quality > older_quality + 0.02 else "declining" if recent_quality < older_quality - 0.02 else "stable"
        else:
            quality_trend = "stable"
        
        # Customer segment analysis
        segment_quality = defaultdict(list)
        for assessment in recent_assessments:
            segment = self._get_customer_segment(assessment.customer_id)
            segment_quality[segment].append(assessment.overall_quality)
        
        segment_averages = {
            segment: statistics.mean(scores)
            for segment, scores in segment_quality.items()
        }
        
        return {
            "overall_metrics": {
                "average_quality": round(avg_overall_quality, 3),
                "quality_trend": quality_trend,
                "assessments_count": len(recent_assessments),
                "quality_distribution": {
                    "excellent": len([s for s in overall_scores if s >= 0.9]),
                    "good": len([s for s in overall_scores if 0.8 <= s < 0.9]),
                    "acceptable": len([s for s in overall_scores if 0.7 <= s < 0.8]),
                    "needs_improvement": len([s for s in overall_scores if s < 0.7])
                }
            },
            "quality_dimensions": {
                "audio_quality": round(statistics.mean(audio_scores), 3),
                "transcription_quality": round(statistics.mean(transcription_scores), 3),
                "response_quality": round(statistics.mean(response_scores), 3),
                "user_experience": round(statistics.mean(ux_scores), 3)
            },
            "top_quality_issues": [
                {"issue": issue, "count": count, "percentage": round(count/len(recent_assessments)*100, 1)}
                for issue, count in top_issues
            ],
            "customer_segment_quality": {
                segment: round(avg_quality, 3)
                for segment, avg_quality in segment_averages.items()
            },
            "performance_statistics": self.analysis_stats.copy(),
            "quality_recommendations": self._get_system_quality_recommendations(recent_assessments)
        }
    
    def _get_system_quality_recommendations(self, recent_assessments: List[QualityAssessmentResult]) -> List[str]:
        """Get system-level quality improvement recommendations"""
        
        recommendations = []
        
        if not recent_assessments:
            return recommendations
        
        # Overall quality recommendation
        avg_quality = statistics.mean([a.overall_quality for a in recent_assessments])
        if avg_quality < 0.8:
            recommendations.append("Overall quality below target - implement comprehensive quality improvement program")
        
        # Audio quality recommendations
        audio_scores = [a.audio_quality for a in recent_assessments]
        if statistics.mean(audio_scores) < 0.8:
            recommendations.append("Audio quality issues detected - improve audio processing pipeline")
        
        # Response quality recommendations
        response_scores = [a.response_quality for a in recent_assessments]
        if statistics.mean(response_scores) < 0.8:
            recommendations.append("Response quality needs improvement - enhance language model and response generation")
        
        # Performance recommendations
        ux_scores = [a.user_experience_quality for a in recent_assessments]
        if statistics.mean(ux_scores) < 0.8:
            recommendations.append("User experience issues - optimize response times and system reliability")
        
        # Issue-based recommendations
        all_issues = []
        for assessment in recent_assessments:
            all_issues.extend(assessment.issues_identified)
        
        if len(all_issues) > len(recent_assessments) * 0.5:  # More than 50% have issues
            recommendations.append("High issue rate detected - prioritize quality assurance and testing")
        
        return recommendations

# Global quality analyzer instance
voice_quality_analyzer = VoiceQualityAnalyzer()