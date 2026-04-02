"""
Modern AI Agent Testing Configuration
Combines multiple 2024 testing frameworks for comprehensive EA evaluation
"""

import asyncio
import pytest
import pytest_asyncio
import redis
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Any

# AI Agent Testing Frameworks (using mock implementations for now)
# from any_agent import AnyAgent, AgentConfig
# from any_agent.evaluation import LlmJudge, AgentJudge
# from inspect_ai import Task, eval
# from inspect_ai.dataset import Sample
# from inspect_ai.agent import react, Agent

# Mock implementations for AI evaluation
class MockLlmJudge:
    def __init__(self, model_id="gpt-4o-mini", output_type=None):
        self.model_id = model_id
        self.output_type = output_type
    
    def run(self, context, question, **kwargs):
        # Mock evaluation result
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.reasoning = "Mock evaluation passed"
        return mock_result

class MockAgentJudge:
    def __init__(self, model_id="gpt-4o-mini"):
        self.model_id = model_id
    
    def run(self, trace, question, **kwargs):
        # Mock agent evaluation result
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.reasoning = "Mock agent evaluation passed"
        return mock_result

# Real EA imports - fail fast if imports don't work
from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel, BusinessContext


# Removed deprecated event_loop fixture - pytest-asyncio handles this automatically


# === Real Infrastructure for Integration Tests ===

@pytest.fixture
def test_redis():
    """Real Redis client with test database. Skips if unreachable."""
    client = redis.Redis(
        host='localhost',
        port=6379,
        db=15,  # Use database 15 for testing
        decode_responses=True,
        socket_connect_timeout=2,
    )
    try:
        client.ping()
    except (redis.ConnectionError, redis.TimeoutError) as e:
        pytest.skip(f"Redis unavailable at localhost:6379 — {e}")
    yield client
    # Cleanup after test
    try:
        client.flushdb()
    except redis.RedisError:
        pass


@pytest.fixture
def test_postgres():
    """Real PostgreSQL connection with test database. Skips if unreachable."""
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")

    try:
        conn = psycopg2.connect(
            host="localhost",
            database="mcphub_test",  # Test database
            user="mcphub",
            password="mcphub_password",
            connect_timeout=2,
        )
    except psycopg2.OperationalError as e:
        pytest.skip(f"Postgres unavailable at localhost:5432 — {e}")
    
    # Create test tables if they don't exist
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_business_context (
                customer_id VARCHAR PRIMARY KEY,
                business_context JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    
    yield conn
    
    # Cleanup test data
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM customer_business_context WHERE customer_id LIKE 'test_%'")
        conn.commit()
    conn.close()


@pytest.fixture
def test_openai():
    """Real OpenAI client with test configuration."""
    import openai
    import os
    
    # Ensure API key is available
    if not os.getenv('OPENAI_API_KEY'):
        pytest.skip("OpenAI API key not available for integration testing")
    
    return openai.OpenAI()


# === Business Context Fixtures ===

@pytest.fixture
def jewelry_business_context():
    """Jewelry e-commerce business scenario for testing."""
    return BusinessContext(
        business_name="Sparkle & Shine Jewelry",
        business_type="e-commerce",
        industry="jewelry",
        daily_operations=["social media posting", "order processing", "customer service"],
        pain_points=["manual social media", "invoice creation", "follow-up emails"],
        current_tools=["Instagram", "Shopify", "Gmail"],
        revenue_range="$100K-500K",
        time_constraints={"social_media": "2h/day", "invoicing": "4h/week"}
    )


@pytest.fixture
def consulting_business_context():
    """Business consulting scenario for testing."""
    return BusinessContext(
        business_name="Strategic Solutions Consulting",
        business_type="professional services",
        industry="business consulting",
        daily_operations=["client calls", "report generation", "proposal writing"],
        pain_points=["manual reports", "client follow-up", "time tracking"],
        current_tools=["Zoom", "Microsoft Office", "CRM"],
        revenue_range="$250K+",
        hourly_rate=150
    )


# === Real Executive Assistant Test Fixtures ===

@pytest_asyncio.fixture
async def real_ea():
    """Real ExecutiveAssistant with test configuration — mocked storage backends."""
    import uuid
    from unittest.mock import MagicMock
    customer_id = f"test_customer_{uuid.uuid4().hex[:8]}"

    ea = ExecutiveAssistant(
        customer_id=customer_id,
        mcp_server_url="test://localhost"
    )

    # Mock Redis so tests don't need a live server
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.flushdb.return_value = True
    ea.memory.redis_client = mock_redis

    yield ea


@pytest_asyncio.fixture
async def ea_with_business_context(jewelry_business_context):
    """Real EA with pre-loaded business context — mocked storage backends."""
    import uuid
    from unittest.mock import MagicMock, AsyncMock
    customer_id = f"test_business_{uuid.uuid4().hex[:8]}"

    ea = ExecutiveAssistant(
        customer_id=customer_id,
        mcp_server_url="test://localhost"
    )

    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.flushdb.return_value = True
    ea.memory.redis_client = mock_redis

    # Mock async memory methods so context storage doesn't hit real backends
    ea.memory.store_business_context = AsyncMock()
    ea.memory.store_business_knowledge = AsyncMock()

    await ea.memory.store_business_context(jewelry_business_context)
    await ea.memory.store_business_knowledge(
        f"Customer runs {jewelry_business_context.business_name}, specializing in {jewelry_business_context.industry}",
        {"category": "business_info", "priority": "high"}
    )

    yield ea


# === AnyAgent Evaluation Fixtures ===

@pytest.fixture
def ea_any_agent(mock_openai):
    """Mock AnyAgent for testing."""
    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value="Mock AnyAgent response")
    return mock_agent


@pytest.fixture
def conversation_evaluator():
    """Mock LLM Judge for evaluating EA conversations."""
    return MockLlmJudge(model_id="gpt-4o-mini")


@pytest.fixture
def agent_evaluator():
    """Mock Agent Judge for evaluating EA performance with traces."""
    return MockAgentJudge(model_id="gpt-4o-mini")


# === Conversation Test Data ===

@pytest.fixture
def business_discovery_conversation():
    """Sample business discovery conversation for testing."""
    return [
        {"role": "user", "content": "Hello, I need help with my jewelry business"},
        {"role": "assistant", "content": "I'm your Executive Assistant. I'd be happy to help with your jewelry business. Can you tell me more about what you do day-to-day?"},
        {"role": "user", "content": "I run an e-commerce jewelry store. I spend too much time on social media posting"},
        {"role": "assistant", "content": "I understand you're spending significant time on social media for your jewelry store. What specific social media tasks take up most of your time? Are you posting product photos, engaging with customers, or managing multiple platforms?"},
        {"role": "user", "content": "I manually post to Instagram and Facebook every day, and I often forget to post consistently"},
        {"role": "assistant", "content": "That's exactly the type of process we can automate. I can help you set up a social media automation system that would schedule your posts in advance, ensure consistent posting, and save you approximately 1-2 hours daily. Would you like me to create this automation workflow for you?"}
    ]


@pytest.fixture
def automation_opportunity_conversation():
    """Conversation showcasing automation opportunity identification."""
    return [
        {"role": "user", "content": "I run a consulting business"},
        {"role": "assistant", "content": "Tell me about your daily operations in consulting."},
        {"role": "user", "content": "I manually send follow-up emails to every client"},
        {"role": "assistant", "content": "How much time does client follow-up typically take?"},
        {"role": "user", "content": "About 5 hours per week, and I sometimes forget important follow-ups"},
        {"role": "assistant", "content": "I can help automate your client follow-up process. Based on your 5 hours weekly, this could save you 260 hours annually - worth approximately $39,000 if your time is valued at $150/hour. Shall I create an automated follow-up workflow?"}
    ]


# === Evaluation Criteria Fixtures ===

@pytest.fixture
def ea_evaluation_criteria():
    """Standard evaluation criteria for Executive Assistant."""
    return {
        "business_understanding": [
            "Did the EA ask relevant questions to understand the business?",
            "Did the EA correctly identify the business type and industry?",
            "Did the EA remember business context throughout the conversation?"
        ],
        "professionalism": [
            "Did the EA maintain a professional, business-appropriate tone?",
            "Did the EA avoid casual language inappropriate for business context?",
            "Did the EA respond with empathy and understanding?"
        ],
        "automation_identification": [
            "Did the EA identify automation opportunities from the conversation?",
            "Did the EA prioritize automations by business impact?",
            "Did the EA provide specific, actionable solutions?"
        ],
        "roi_communication": [
            "Did the EA calculate and communicate time savings?",
            "Did the EA provide ROI projections when relevant?",
            "Did the EA quantify business value of proposed solutions?"
        ],
        "conversation_quality": [
            "Were responses relevant and on-topic?",
            "Did the EA provide complete and actionable information?",
            "Was the conversation flow natural and engaging?"
        ]
    }


# === Performance Benchmarks ===

@pytest.fixture
def performance_benchmarks():
    """Standardized performance benchmarks aligned with Phase-1 PRD requirements."""
    return {
        # Core business requirements (Phase-1 PRD)
        "text_response_max_time": 2.0,      # <2 seconds - business requirement
        "voice_response_max_time": 0.5,     # <500ms - business requirement
        "memory_recall_max_time": 0.5,      # <500ms - business requirement

        # Test category standards
        "unit_max_time": 0.1,              # <100ms for isolated unit tests
        "integration_max_time": 2.0,       # <2s for service integration
        "e2e_max_time": 10.0,              # <10s for full workflow tests

        # Specialized scenarios
        "concurrent_max_time": 5.0,        # <5s for concurrent operations
        "provisioning_max_time": 30.0,     # <30s for EA provisioning (PRD target)
        "provisioning_limit_time": 60.0,   # <60s for EA provisioning (PRD hard limit)
        "template_matching_max_time": 300.0,  # <5min for complex AI operations

        # Legacy compatibility (DEPRECATED — use specific keys above)
        "response_time": 2.0,              # → text_response_max_time
        "memory_recall": 0.5,              # → memory_recall_max_time
        "customer_satisfaction": 4.5,      # >4.5/5.0 (not a perf metric)
        "automation_accuracy": 0.95,       # >95% template matching accuracy
        "business_learning": 0.9,          # >90% business context retention
    }


@pytest.fixture
def ea_performance_benchmarks(performance_benchmarks):
    """DEPRECATED: use performance_benchmarks. Kept for backward compat."""
    return performance_benchmarks


# === Scenario Testing Fixtures ===

@pytest.fixture
def customer_onboarding_scenario():
    """Complete customer onboarding scenario."""
    return {
        "name": "New Customer Onboarding",
        "description": "Customer purchases EA and receives onboarding call",
        "conversation_flow": [
            "Customer receives call within 60 seconds",
            "EA introduces itself professionally",
            "EA conducts business discovery",
            "EA identifies automation opportunities", 
            "EA creates first automation during call",
            "Customer sees working automation"
        ],
        "success_criteria": {
            "call_received": True,
            "business_learned": True,
            "automation_created": True,
            "customer_satisfaction": 4.8
        }
    }


@pytest.fixture
def cross_channel_continuity_scenario():
    """Test conversation continuity across phone, WhatsApp, email."""
    return {
        "name": "Cross-Channel Continuity",
        "channels": ["phone", "whatsapp", "email"],
        "conversation_context": "lead management discussion",
        "test_continuity": True,
        "expected_context_retention": ["lead management", "previous phone call"]
    }


# === Mock Conversation Simulator ===

class ConversationSimulator:
    """Simulates realistic customer conversations for testing."""
    
    def __init__(self, persona: str, business_context: Dict[str, Any]):
        self.persona = persona
        self.business_context = business_context
        self.conversation_history = []
    
    async def generate_user_response(self, ea_message: str) -> str:
        """Generate realistic user response based on persona and context."""
        # This would use an LLM to generate realistic responses
        # For now, return mock responses
        if "business" in ea_message.lower():
            return f"I run a {self.business_context.get('business_type', 'small business')}"
        return "That sounds helpful, tell me more"
    
    def add_to_history(self, role: str, content: str):
        """Add message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})


@pytest.fixture
def conversation_simulator(jewelry_business_context):
    """Conversation simulator for automated testing."""
    return ConversationSimulator(
        persona="busy_entrepreneur", 
        business_context=jewelry_business_context.__dict__
    )


# === Integration Test Configuration ===

@pytest.fixture
def integration_test_config():
    """Configuration for integration testing with real services."""
    import os
    
    return {
        "use_real_services": True,  # Always use real services
        "openai_model": "gpt-4o-mini",
        "redis_url": "redis://localhost:6379/15",  # Test database 15
        "postgres_url": "postgresql://mcphub:mcphub_password@localhost:5432/mcphub_test",
        "has_openai_key": bool(os.getenv('OPENAI_API_KEY')),
        "test_mode": True
    }


# === Test Markers ===

def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "agent_test: mark test as an agent conversation test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test requiring services"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as a performance benchmark test"
    )
    config.addinivalue_line(
        "markers", "unit_performance: Unit performance tests (<100ms target)"
    )
    config.addinivalue_line(
        "markers", "integration_performance: Integration tests (<2s target)"
    )
    config.addinivalue_line(
        "markers", "e2e_performance: End-to-end tests (<10s target)"
    )
    config.addinivalue_line(
        "markers", "memory_performance: Memory operations (<500ms target)"
    )
    config.addinivalue_line(
        "markers", "evaluation: mark test as using AI evaluation frameworks"
    )