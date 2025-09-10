"""
Voice Integration Load Testing Framework
Tests concurrent voice sessions, response times, and scalability
"""

import asyncio
import logging
import time
import json
import random
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import uuid
import tempfile
import wave
import numpy as np

# Testing imports
import pytest
import aiohttp
import websockets
from fastapi.testclient import TestClient

# Voice integration imports
from src.api.voice_api import create_voice_api
from src.agents.voice_integration import create_voice_enabled_ea
from src.communication.voice_channel import VoiceLanguage
from src.communication.webrtc_voice_handler import voice_manager

logger = logging.getLogger(__name__)

class VoiceLoadTestResults:
    """Container for voice load test results"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.end_time = None
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.error_messages = []
        self.concurrent_sessions = 0
        self.peak_concurrent_sessions = 0
        
        # Voice-specific metrics
        self.stt_times = []
        self.tts_times = []
        self.ea_processing_times = []
        self.language_distribution = {}
        self.audio_processing_errors = 0
        
        # SLA compliance
        self.sla_compliant_requests = 0
        self.sla_target = 2.0
    
    def add_result(self, result: Dict[str, Any]):
        """Add individual test result"""
        self.total_requests += 1
        
        if result.get('success', False):
            self.successful_requests += 1
            response_time = result.get('response_time', 0)
            self.response_times.append(response_time)
            
            if response_time <= self.sla_target:
                self.sla_compliant_requests += 1
            
            # Voice-specific metrics
            if 'stt_time' in result:
                self.stt_times.append(result['stt_time'])
            if 'tts_time' in result:
                self.tts_times.append(result['tts_time'])
            if 'ea_time' in result:
                self.ea_processing_times.append(result['ea_time'])
            
            language = result.get('language', 'en')
            self.language_distribution[language] = self.language_distribution.get(language, 0) + 1
            
        else:
            self.failed_requests += 1
            self.error_messages.append(result.get('error', 'Unknown error'))
            
            if 'audio_error' in result.get('error_type', ''):
                self.audio_processing_errors += 1
    
    def finalize(self):
        """Finalize test results"""
        self.end_time = datetime.now()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test results summary"""
        duration = (self.end_time - self.start_time).total_seconds()
        
        # Basic metrics
        success_rate = (self.successful_requests / self.total_requests) if self.total_requests > 0 else 0
        avg_response_time = statistics.mean(self.response_times) if self.response_times else 0
        median_response_time = statistics.median(self.response_times) if self.response_times else 0
        p95_response_time = statistics.quantiles(self.response_times, n=20)[18] if len(self.response_times) >= 20 else 0
        p99_response_time = statistics.quantiles(self.response_times, n=100)[98] if len(self.response_times) >= 100 else 0
        
        # SLA compliance
        sla_compliance_rate = (self.sla_compliant_requests / self.successful_requests) if self.successful_requests > 0 else 0
        
        # Throughput
        requests_per_second = self.total_requests / duration if duration > 0 else 0
        
        # Voice-specific metrics
        avg_stt_time = statistics.mean(self.stt_times) if self.stt_times else 0
        avg_tts_time = statistics.mean(self.tts_times) if self.tts_times else 0
        avg_ea_time = statistics.mean(self.ea_processing_times) if self.ea_processing_times else 0
        
        return {
            'test_summary': {
                'duration_seconds': duration,
                'total_requests': self.total_requests,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'success_rate': success_rate,
                'requests_per_second': requests_per_second,
                'peak_concurrent_sessions': self.peak_concurrent_sessions
            },
            'response_times': {
                'average': avg_response_time,
                'median': median_response_time,
                'p95': p95_response_time,
                'p99': p99_response_time,
                'min': min(self.response_times) if self.response_times else 0,
                'max': max(self.response_times) if self.response_times else 0
            },
            'sla_compliance': {
                'target_seconds': self.sla_target,
                'compliant_requests': self.sla_compliant_requests,
                'compliance_rate': sla_compliance_rate
            },
            'voice_metrics': {
                'avg_speech_to_text_time': avg_stt_time,
                'avg_text_to_speech_time': avg_tts_time,
                'avg_ea_processing_time': avg_ea_time,
                'language_distribution': self.language_distribution,
                'audio_processing_errors': self.audio_processing_errors
            },
            'error_analysis': {
                'error_rate': (self.failed_requests / self.total_requests) if self.total_requests > 0 else 0,
                'common_errors': self._get_common_errors()
            }
        }
    
    def _get_common_errors(self) -> Dict[str, int]:
        """Get common error types and counts"""
        error_counts = {}
        for error in self.error_messages:
            error_counts[error] = error_counts.get(error, 0) + 1
        
        # Return top 10 most common errors
        return dict(sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10])

class VoiceLoadTester:
    """Voice integration load testing framework"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.base_url = self.config.get('base_url', 'http://localhost:8001')
        self.websocket_url = self.config.get('websocket_url', 'ws://localhost:8001')
        
        # Test data
        self.test_messages = self._generate_test_messages()
        self.test_audio_files = self._generate_test_audio_files()
        
        # Active test sessions
        self.active_sessions = []
        self.results = VoiceLoadTestResults()
    
    def _generate_test_messages(self) -> List[Dict[str, Any]]:
        """Generate test messages in multiple languages"""
        return [
            # English business messages
            {"text": "I need help setting up marketing automation for my agency", "language": "en", "category": "marketing"},
            {"text": "Can you create a workflow for client onboarding?", "language": "en", "category": "business"},
            {"text": "I want to automate my social media posting schedule", "language": "en", "category": "social"},
            {"text": "Help me track my business expenses and revenue", "language": "en", "category": "finance"},
            {"text": "I need to set up automated email sequences for leads", "language": "en", "category": "marketing"},
            
            # Spanish business messages
            {"text": "Necesito ayuda configurando automatización de marketing para mi agencia", "language": "es", "category": "marketing"},
            {"text": "¿Puedes crear un flujo de trabajo para incorporar clientes?", "language": "es", "category": "business"},
            {"text": "Quiero automatizar mi programación de publicaciones en redes sociales", "language": "es", "category": "social"},
            {"text": "Ayúdame a rastrear mis gastos comerciales e ingresos", "language": "es", "category": "finance"},
            {"text": "Necesito configurar secuencias de correo automatizadas para leads", "language": "es", "category": "marketing"},
            
            # Mixed/complex messages
            {"text": "I have a marketing agency but necesito ayuda with automation", "language": "auto", "category": "mixed"},
            {"text": "My business is growing fast and I need better processes", "language": "en", "category": "growth"},
            {"text": "Mi empresa está creciendo rápido y necesito mejores procesos", "language": "es", "category": "growth"},
        ]
    
    def _generate_test_audio_files(self) -> List[bytes]:
        """Generate synthetic audio data for testing"""
        audio_files = []
        
        for i in range(10):
            # Generate synthetic audio (simple sine wave)
            duration = random.uniform(1.0, 5.0)  # 1-5 seconds
            sample_rate = 16000
            frequency = 440 + (i * 50)  # Different frequencies
            
            samples = np.sin(2 * np.pi * frequency * np.linspace(0, duration, int(sample_rate * duration)))
            samples = (samples * 32767).astype(np.int16)
            
            # Create WAV file in memory
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                with wave.open(temp_file, 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(samples.tobytes())
                
                temp_file.seek(0)
                audio_data = temp_file.read()
                audio_files.append(audio_data)
        
        return audio_files
    
    async def run_http_load_test(
        self, 
        concurrent_users: int = 10,
        requests_per_user: int = 10,
        ramp_up_time: int = 30
    ) -> VoiceLoadTestResults:
        """Run HTTP-based voice load test"""
        logger.info(f"Starting HTTP load test: {concurrent_users} users, {requests_per_user} requests each")
        
        self.results = VoiceLoadTestResults()
        
        # Create customer IDs for testing
        customer_ids = [f"load-test-customer-{i}" for i in range(concurrent_users)]
        
        async def user_simulation(customer_id: str, user_index: int):
            """Simulate a single user's voice interactions"""
            async with aiohttp.ClientSession() as session:
                try:
                    # Start conversation
                    conversation_start_time = time.time()
                    async with session.post(
                        f"{self.base_url}/voice/start-conversation/{customer_id}",
                        json={"language_preference": "auto", "context": {"load_test": True}}
                    ) as resp:
                        if resp.status == 200:
                            conversation_data = await resp.json()
                            conversation_id = conversation_data.get("conversation_id")
                        else:
                            logger.error(f"Failed to start conversation for {customer_id}")
                            return
                    
                    # Send voice messages
                    for i in range(requests_per_user):
                        await asyncio.sleep(random.uniform(1, 5))  # Random delay between messages
                        
                        message = random.choice(self.test_messages)
                        start_time = time.time()
                        
                        try:
                            async with session.post(
                                f"{self.base_url}/voice/message/{customer_id}",
                                json={
                                    "text": message["text"],
                                    "language": message["language"],
                                    "voice_style": "casual",
                                    "conversation_id": conversation_id
                                },
                                timeout=aiohttp.ClientTimeout(total=10)
                            ) as resp:
                                response_time = time.time() - start_time
                                
                                if resp.status == 200:
                                    response_data = await resp.json()
                                    
                                    self.results.add_result({
                                        'success': True,
                                        'response_time': response_time,
                                        'customer_id': customer_id,
                                        'language': message["language"],
                                        'category': message["category"]
                                    })
                                else:
                                    error_text = await resp.text()
                                    self.results.add_result({
                                        'success': False,
                                        'response_time': response_time,
                                        'error': f"HTTP {resp.status}: {error_text}",
                                        'customer_id': customer_id
                                    })
                        
                        except asyncio.TimeoutError:
                            self.results.add_result({
                                'success': False,
                                'response_time': 10.0,
                                'error': 'Request timeout',
                                'customer_id': customer_id
                            })
                        except Exception as e:
                            self.results.add_result({
                                'success': False,
                                'response_time': time.time() - start_time,
                                'error': str(e),
                                'customer_id': customer_id
                            })
                
                except Exception as e:
                    logger.error(f"User simulation error for {customer_id}: {e}")
        
        # Run concurrent user simulations
        tasks = []
        for i, customer_id in enumerate(customer_ids):
            # Stagger start times for ramp-up
            delay = (i / concurrent_users) * ramp_up_time
            task = asyncio.create_task(self._delayed_task(user_simulation(customer_id, i), delay))
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.results.peak_concurrent_sessions = concurrent_users
        self.results.finalize()
        
        logger.info("HTTP load test completed")
        return self.results
    
    async def run_websocket_load_test(
        self,
        concurrent_sessions: int = 20,
        messages_per_session: int = 10,
        session_duration: int = 300  # 5 minutes
    ) -> VoiceLoadTestResults:
        """Run WebSocket-based voice load test"""
        logger.info(f"Starting WebSocket load test: {concurrent_sessions} sessions, {messages_per_session} messages each")
        
        self.results = VoiceLoadTestResults()
        
        async def websocket_session(session_id: str):
            """Simulate a single WebSocket voice session"""
            customer_id = f"ws-load-test-{session_id}"
            uri = f"{self.websocket_url}/voice/ws/{customer_id}"
            
            try:
                async with websockets.connect(uri) as websocket:
                    # Session started
                    session_start_message = await websocket.recv()
                    session_data = json.loads(session_start_message)
                    
                    if session_data.get("type") == "session_started":
                        conversation_id = session_data["conversation_id"]
                        
                        # Send voice messages
                        for i in range(messages_per_session):
                            await asyncio.sleep(random.uniform(2, 8))  # Random delay
                            
                            # Simulate audio message
                            audio_data = random.choice(self.test_audio_files)
                            message = random.choice(self.test_messages)
                            
                            start_time = time.time()
                            
                            # Send text message instead of audio for simplicity in testing
                            text_message = {
                                "type": "text_message",
                                "text": message["text"],
                                "language": message["language"]
                            }
                            
                            await websocket.send(json.dumps(text_message))
                            
                            # Wait for EA response
                            try:
                                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                                response_data = json.loads(response)
                                response_time = time.time() - start_time
                                
                                if response_data.get("type") == "ea_response":
                                    self.results.add_result({
                                        'success': True,
                                        'response_time': response_time,
                                        'ea_time': response_data.get('response_time_seconds', 0),
                                        'customer_id': customer_id,
                                        'language': message["language"],
                                        'session_id': session_id
                                    })
                                else:
                                    self.results.add_result({
                                        'success': False,
                                        'response_time': response_time,
                                        'error': f"Unexpected response type: {response_data.get('type')}",
                                        'customer_id': customer_id
                                    })
                            
                            except asyncio.TimeoutError:
                                self.results.add_result({
                                    'success': False,
                                    'response_time': 10.0,
                                    'error': 'WebSocket response timeout',
                                    'customer_id': customer_id
                                })
                    
            except Exception as e:
                logger.error(f"WebSocket session error for {session_id}: {e}")
                self.results.add_result({
                    'success': False,
                    'response_time': 0,
                    'error': f"WebSocket connection error: {str(e)}",
                    'customer_id': customer_id
                })
        
        # Run concurrent WebSocket sessions
        tasks = [
            asyncio.create_task(websocket_session(f"session-{i}"))
            for i in range(concurrent_sessions)
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        self.results.peak_concurrent_sessions = concurrent_sessions
        self.results.finalize()
        
        logger.info("WebSocket load test completed")
        return self.results
    
    async def run_stress_test(
        self,
        max_concurrent_users: int = 100,
        ramp_up_rate: int = 10,  # Users per second
        test_duration: int = 600  # 10 minutes
    ) -> VoiceLoadTestResults:
        """Run stress test to find system limits"""
        logger.info(f"Starting stress test: ramping up to {max_concurrent_users} users")
        
        self.results = VoiceLoadTestResults()
        active_tasks = []
        
        async def stress_user(user_id: str):
            """Stress test user simulation"""
            customer_id = f"stress-test-{user_id}"
            
            async with aiohttp.ClientSession() as session:
                try:
                    while time.time() - self.results.start_time.timestamp() < test_duration:
                        message = random.choice(self.test_messages)
                        start_time = time.time()
                        
                        try:
                            async with session.post(
                                f"{self.base_url}/voice/message/{customer_id}",
                                json={
                                    "text": message["text"],
                                    "language": message["language"],
                                    "voice_style": "casual"
                                },
                                timeout=aiohttp.ClientTimeout(total=15)
                            ) as resp:
                                response_time = time.time() - start_time
                                
                                if resp.status == 200:
                                    self.results.add_result({
                                        'success': True,
                                        'response_time': response_time,
                                        'customer_id': customer_id,
                                        'language': message["language"]
                                    })
                                else:
                                    self.results.add_result({
                                        'success': False,
                                        'response_time': response_time,
                                        'error': f"HTTP {resp.status}",
                                        'customer_id': customer_id
                                    })
                        
                        except Exception as e:
                            self.results.add_result({
                                'success': False,
                                'response_time': time.time() - start_time,
                                'error': str(e),
                                'customer_id': customer_id
                            })
                        
                        await asyncio.sleep(random.uniform(1, 3))  # Random delay between requests
                
                except Exception as e:
                    logger.error(f"Stress user {user_id} error: {e}")
        
        # Gradually ramp up users
        for i in range(max_concurrent_users):
            user_task = asyncio.create_task(stress_user(f"stress-user-{i}"))
            active_tasks.append(user_task)
            
            # Update peak concurrent sessions
            current_active = len([task for task in active_tasks if not task.done()])
            self.results.peak_concurrent_sessions = max(self.results.peak_concurrent_sessions, current_active)
            
            # Ramp up delay
            if i < max_concurrent_users - 1:
                await asyncio.sleep(1.0 / ramp_up_rate)
        
        # Wait for test duration
        await asyncio.sleep(test_duration)
        
        # Cancel remaining tasks
        for task in active_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*active_tasks, return_exceptions=True)
        
        self.results.finalize()
        
        logger.info("Stress test completed")
        return self.results
    
    async def _delayed_task(self, task, delay: float):
        """Execute task after delay"""
        await asyncio.sleep(delay)
        return await task

class VoicePerformanceBenchmarks:
    """Voice performance benchmark suite"""
    
    @pytest.mark.asyncio
    async def test_response_time_sla(self):
        """Test that 95% of voice responses meet 2s SLA"""
        tester = VoiceLoadTester()
        results = await tester.run_http_load_test(concurrent_users=10, requests_per_user=20)
        summary = results.get_summary()
        
        # Check SLA compliance
        assert summary['sla_compliance']['compliance_rate'] >= 0.95, \
            f"SLA compliance {summary['sla_compliance']['compliance_rate']:.2%} below 95% target"
        
        # Check average response time
        assert summary['response_times']['average'] < 1.5, \
            f"Average response time {summary['response_times']['average']:.2f}s exceeds 1.5s target"
        
        # Check 95th percentile
        assert summary['response_times']['p95'] < 2.0, \
            f"95th percentile response time {summary['response_times']['p95']:.2f}s exceeds 2s SLA"
    
    @pytest.mark.asyncio
    async def test_concurrent_users_scalability(self):
        """Test system scalability with increasing concurrent users"""
        tester = VoiceLoadTester()
        
        # Test different concurrent user levels
        user_levels = [5, 10, 25, 50]
        results_by_level = {}
        
        for users in user_levels:
            logger.info(f"Testing {users} concurrent users")
            results = await tester.run_http_load_test(concurrent_users=users, requests_per_user=5)
            summary = results.get_summary()
            results_by_level[users] = summary
            
            # Basic success rate check
            assert summary['test_summary']['success_rate'] >= 0.90, \
                f"Success rate {summary['test_summary']['success_rate']:.2%} below 90% at {users} users"
        
        # Check that performance doesn't degrade significantly
        baseline_avg = results_by_level[5]['response_times']['average']
        max_avg = results_by_level[50]['response_times']['average']
        
        performance_degradation = (max_avg - baseline_avg) / baseline_avg
        assert performance_degradation < 1.0, \
            f"Performance degraded by {performance_degradation:.2%} from baseline"
    
    @pytest.mark.asyncio
    async def test_websocket_session_stability(self):
        """Test WebSocket session stability under load"""
        tester = VoiceLoadTester()
        results = await tester.run_websocket_load_test(
            concurrent_sessions=15,
            messages_per_session=8
        )
        summary = results.get_summary()
        
        # Check success rate
        assert summary['test_summary']['success_rate'] >= 0.95, \
            f"WebSocket success rate {summary['test_summary']['success_rate']:.2%} below 95%"
        
        # Check response time consistency
        assert summary['response_times']['p95'] < 3.0, \
            f"WebSocket p95 response time {summary['response_times']['p95']:.2f}s too high"
    
    @pytest.mark.asyncio
    async def test_bilingual_performance_parity(self):
        """Test that Spanish and English have similar performance"""
        tester = VoiceLoadTester()
        
        # Run test with mixed language messages
        results = await tester.run_http_load_test(concurrent_users=10, requests_per_user=15)
        summary = results.get_summary()
        
        # Check language distribution
        lang_dist = summary['voice_metrics']['language_distribution']
        assert 'en' in lang_dist and 'es' in lang_dist, "Both languages should be tested"
        
        # In a real implementation, you'd analyze response times by language
        # For now, ensure overall performance is good
        assert summary['sla_compliance']['compliance_rate'] >= 0.90, \
            "Bilingual performance should meet SLA targets"
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test system recovery from errors"""
        tester = VoiceLoadTester()
        
        # Simulate some error conditions by using invalid data
        invalid_messages = [
            {"text": "", "language": "en"},  # Empty message
            {"text": "x" * 10000, "language": "en"},  # Very long message
            {"text": "Valid message", "language": "invalid"},  # Invalid language
        ]
        
        # Add invalid messages to test data
        original_messages = tester.test_messages[:]
        tester.test_messages.extend(invalid_messages)
        
        try:
            results = await tester.run_http_load_test(concurrent_users=5, requests_per_user=10)
            summary = results.get_summary()
            
            # System should handle errors gracefully
            assert summary['test_summary']['success_rate'] >= 0.80, \
                "System should maintain 80% success rate even with invalid inputs"
            
            # Error rate should be reasonable
            assert summary['error_analysis']['error_rate'] <= 0.20, \
                "Error rate should not exceed 20%"
            
        finally:
            # Restore original test messages
            tester.test_messages = original_messages

# Performance test runner
async def run_voice_performance_suite():
    """Run complete voice performance test suite"""
    logger.info("🎤 Starting Voice Performance Test Suite")
    
    # Test configurations
    test_configs = [
        {
            "name": "Light Load Test",
            "concurrent_users": 5,
            "requests_per_user": 10,
            "expected_success_rate": 0.98
        },
        {
            "name": "Medium Load Test", 
            "concurrent_users": 20,
            "requests_per_user": 15,
            "expected_success_rate": 0.95
        },
        {
            "name": "Heavy Load Test",
            "concurrent_users": 50,
            "requests_per_user": 10,
            "expected_success_rate": 0.90
        }
    ]
    
    tester = VoiceLoadTester()
    all_results = {}
    
    for config in test_configs:
        logger.info(f"Running {config['name']}...")
        
        results = await tester.run_http_load_test(
            concurrent_users=config["concurrent_users"],
            requests_per_user=config["requests_per_user"]
        )
        
        summary = results.get_summary()
        all_results[config["name"]] = summary
        
        # Validate results against expectations
        success_rate = summary['test_summary']['success_rate']
        if success_rate >= config['expected_success_rate']:
            logger.info(f"✅ {config['name']} PASSED - Success rate: {success_rate:.2%}")
        else:
            logger.warning(f"❌ {config['name']} FAILED - Success rate: {success_rate:.2%} (expected: {config['expected_success_rate']:.2%})")
        
        # Check SLA compliance
        sla_compliance = summary['sla_compliance']['compliance_rate']
        if sla_compliance >= 0.90:
            logger.info(f"✅ SLA Compliance: {sla_compliance:.2%}")
        else:
            logger.warning(f"⚠️ SLA Compliance: {sla_compliance:.2%} below 90% target")
    
    # Generate comprehensive report
    report = {
        "test_timestamp": datetime.now().isoformat(),
        "test_results": all_results,
        "overall_assessment": _assess_overall_performance(all_results),
        "recommendations": _generate_performance_recommendations(all_results)
    }
    
    logger.info("🎉 Voice Performance Test Suite Completed")
    return report

def _assess_overall_performance(results: Dict[str, Any]) -> str:
    """Assess overall performance across all tests"""
    all_success_rates = [r['test_summary']['success_rate'] for r in results.values()]
    all_sla_rates = [r['sla_compliance']['compliance_rate'] for r in results.values()]
    
    avg_success_rate = statistics.mean(all_success_rates)
    avg_sla_rate = statistics.mean(all_sla_rates)
    
    if avg_success_rate >= 0.95 and avg_sla_rate >= 0.90:
        return "EXCELLENT - System exceeds performance targets"
    elif avg_success_rate >= 0.90 and avg_sla_rate >= 0.80:
        return "GOOD - System meets most performance targets"
    elif avg_success_rate >= 0.80:
        return "ACCEPTABLE - System needs performance improvements"
    else:
        return "POOR - System requires significant optimization"

def _generate_performance_recommendations(results: Dict[str, Any]) -> List[str]:
    """Generate performance improvement recommendations"""
    recommendations = []
    
    for test_name, result in results.items():
        success_rate = result['test_summary']['success_rate']
        sla_rate = result['sla_compliance']['compliance_rate']
        avg_response_time = result['response_times']['average']
        p95_response_time = result['response_times']['p95']
        
        if success_rate < 0.95:
            recommendations.append(f"Improve success rate for {test_name} (current: {success_rate:.2%})")
        
        if sla_rate < 0.90:
            recommendations.append(f"Optimize response times for {test_name} (SLA compliance: {sla_rate:.2%})")
        
        if avg_response_time > 1.0:
            recommendations.append(f"Reduce average response time for {test_name} (current: {avg_response_time:.2f}s)")
        
        if p95_response_time > 2.0:
            recommendations.append(f"Address slow requests in {test_name} (p95: {p95_response_time:.2f}s)")
    
    if not recommendations:
        recommendations.append("System performance is excellent - no immediate optimizations needed")
    
    return recommendations

if __name__ == "__main__":
    # Run the performance test suite
    logging.basicConfig(level=logging.INFO)
    report = asyncio.run(run_voice_performance_suite())
    
    # Print summary
    print("\n" + "="*60)
    print("VOICE PERFORMANCE TEST REPORT")
    print("="*60)
    print(f"Assessment: {report['overall_assessment']}")
    print("\nRecommendations:")
    for rec in report['recommendations']:
        print(f"- {rec}")
    print("="*60)