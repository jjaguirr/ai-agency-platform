# AI Agent Testing Framework - Executive Assistant

## Overview

> **Status note:** This document describes the *target* testing design — several
> frameworks (Mozilla AnyAgent, Inspect AI) and test files listed below are
> planned but not yet wired in. For the current test layout and how to run the
> suite today, see [`tests/README.md`](../../tests/README.md).

We're building a testing framework that combines traditional TDD with AI agent evaluation methodologies. This approach ensures our Executive Assistant meets the highest standards for conversational AI systems.

## Testing Architecture

### 🏗️ **Hybrid Framework Approach**

Our testing strategy combines multiple frameworks for comprehensive coverage:

1. **Mozilla AnyAgent** - For AI-powered evaluation and agent trace analysis
2. **Inspect AI** - For production-ready agent benchmarking and ReAct pattern testing  
3. **Scenario Framework** - For realistic conversational testing with pytest integration
4. **Traditional TDD** - For core functionality validation

### 📊 **Test Structure**

```
tests/
├── unit/                    # Fast unit tests (see tests/README.md for subdirs)
│   └── test_ea_core_modern.py      # Core EA functionality
├── e2e/                     # Full-app integration, no live services
├── integration/             # Real Postgres/Redis/Qdrant tests
├── acceptance/              # End-to-end scenario tests
│   └── test_customer_scenarios.py  # Customer persona testing
├── business/                # Business-outcome validation
└── conftest.py              # Shared fixtures
```

## 🚀 **Quick Start**

### Run Tests Immediately

```bash
# Fast unit tests (recommended for development)
./scripts/quick_test.sh unit

# Conversational AI evaluation tests
./scripts/quick_test.sh evaluation

# Complete customer scenarios
./scripts/quick_test.sh scenarios

# Watch mode for TDD
./scripts/quick_test.sh watch
```

### Full Test Suite

```bash
# Run comprehensive test suite
python scripts/test_runner.py --suite all

# With real services (requires Docker)
python scripts/test_runner.py --suite all --with-services

# Generate test report
python scripts/test_runner.py --suite all --report test_results.json
```

## 🧪 **Testing Methodologies**

### **1. AI-Powered Evaluation**

Instead of just checking string matches, we use AI judges to evaluate conversation quality:

```python
@pytest.mark.asyncio
async def test_ea_professional_communication(self, basic_ea, conversation_evaluator):
    # Traditional test
    response = await basic_ea.handle_message("This is urgent!", ConversationChannel.PHONE)
    assert len(response) > 0
    
    # AI evaluation  
    evaluation = conversation_evaluator.run(
        context=f"User: This is urgent!\nEA: {response}",
        question="Did the EA respond professionally and appropriately to the urgent request?"
    )
    assert evaluation.passed, f"Professional communication failed: {evaluation.reasoning}"
```

### **2. Scenario-Driven Testing**

Tests simulate real customer conversations with different personas:

```python
@pytest.mark.agent_test
async def test_busy_entrepreneur_onboarding(self, scenario_runner, busy_entrepreneur):
    scenario = {
        "name": "Customer Onboarding",
        "conversation_flow": [
            "EA introduces itself professionally",
            "EA conducts business discovery", 
            "EA identifies automation opportunities",
            "EA creates first automation during call"
        ]
    }
    
    results = await scenario_runner.run_scenario(scenario, busy_entrepreneur)
    assert results["completed_successfully"]
```

### **3. Cross-Channel Continuity**

Validates conversation continuity across phone, WhatsApp, and email:

```python
async def test_phone_to_whatsapp_continuity(self, basic_ea):
    # Phone conversation
    phone_response = await basic_ea.handle_message(
        "I need help with lead management", ConversationChannel.PHONE
    )
    
    # WhatsApp follow-up
    whatsapp_response = await basic_ea.handle_message(
        "Following up on our call", ConversationChannel.WHATSAPP
    )
    
    # AI evaluation of continuity
    evaluator = LlmJudge(model_id="gpt-4o-mini")
    continuity_eval = evaluator.run(
        context=f"Phone: {phone_response}\nWhatsApp: {whatsapp_response}",
        question="Did the EA maintain context from the phone call in the WhatsApp response?"
    )
    assert continuity_eval.passed
```

### **4. Performance Benchmarking**

Validates Phase-1 PRD requirements:

```python
@pytest.mark.performance
async def test_ea_meets_response_time_requirements(self, basic_ea, ea_performance_benchmarks):
    start_time = time.time()
    response = await basic_ea.handle_message("Tell me about automation")
    response_time = time.time() - start_time
    
    # <2 second requirement from PRD
    assert response_time < ea_performance_benchmarks["response_time"]
```

## 📋 **Test Categories & Markers**

### Available Test Markers

- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Service integration tests
- `@pytest.mark.agent_test` - AI agent evaluation tests
- `@pytest.mark.evaluation` - LLM/Agent judge tests
- `@pytest.mark.performance` - Performance benchmarks
- `@pytest.mark.conversation` - Conversational AI tests
- `@pytest.mark.scenario` - Scenario-driven tests
- `@pytest.mark.cross_channel` - Multi-channel tests

### Running Specific Test Types

```bash
# Only AI evaluation tests
uv run pytest -m "evaluation"

# Performance benchmarks only
uv run pytest -m "performance"

# Exclude real API calls (default for fast development)
uv run pytest -m "not real_api"

# Integration tests with real services
uv run pytest -m "integration and real_api"
```

## 🎭 **Customer Personas**

Our tests include realistic customer personas:

### **Busy Entrepreneur (Sarah Chen)**
- **Business**: E-commerce jewelry
- **Traits**: Impatient, results-focused, time-constrained  
- **Pain Points**: Social media management, customer follow-ups, manual invoicing

### **Detail-Oriented Consultant (Michael Rodriguez)**
- **Business**: Business consulting
- **Traits**: Analytical, methodical, detail-oriented
- **Pain Points**: Report generation, time tracking, client communication

### **Skeptical Retailer (Jennifer Walsh)**
- **Business**: Retail clothing
- **Traits**: Cautious, budget-conscious, skeptical
- **Pain Points**: Inventory management, inconsistent social media, customer service

## 📊 **Evaluation Criteria**

### Business Understanding
- Did EA ask relevant business questions?
- Did EA correctly identify business type and industry?
- Did EA remember business context throughout?

### Professionalism  
- Professional, business-appropriate tone?
- Avoided casual language?
- Responded with empathy and understanding?

### Automation Identification
- Identified automation opportunities?
- Prioritized by business impact?
- Provided specific, actionable solutions?

### ROI Communication
- Calculated and communicated time savings?
- Provided ROI projections?
- Quantified business value?

## 🔄 **Development Workflow**

### **TDD Cycle with AI Evaluation**

1. **RED** - Write failing test with AI evaluation criteria
2. **GREEN** - Implement minimal EA code to pass
3. **REFACTOR** - Improve while maintaining test coverage
4. **AI VALIDATE** - Ensure conversation quality meets standards

### **Example TDD Flow**

```bash
# 1. Write failing test
./scripts/quick_test.sh unit  # Should fail

# 2. Implement minimal code
# ... code changes ...

# 3. Run tests until green
./scripts/quick_test.sh unit  # Should pass

# 4. Refactor and validate
./scripts/quick_test.sh evaluation  # AI quality check
```

### **Watch Mode for Continuous Testing**

```bash
# Automatically re-run tests when files change
./scripts/quick_test.sh watch
```

## 🐳 **Docker Integration**

### **Testing with Real Services**

```bash
# Start test infrastructure
docker compose up -d postgres redis

# Run integration tests with real services
python scripts/test_runner.py --suite integration --with-services

# Full end-to-end testing
python scripts/test_runner.py --suite all --with-services
```

### **Mock vs Real Services**

- **Mock Services** (default): Fast, reliable, no dependencies
- **Real Services**: Realistic, catches integration issues, requires Docker

## 📈 **Success Metrics**

Our tests validate Phase-1 PRD requirements:

### **Performance Targets**
- ✅ Response time: <2 seconds
- ✅ Memory recall: <500ms
- ✅ Customer satisfaction: >4.5/5.0
- ✅ Automation accuracy: >95%

### **Business Validation**  
- ✅ Business discovery within 5 minutes
- ✅ Automation identification accuracy
- ✅ ROI calculation precision
- ✅ Cross-channel context retention

## 🔍 **Debugging & Troubleshooting**

### **Test Failures**

```bash
# Detailed test output
uv run pytest tests/unit/test_ea_core_modern.py -v --tb=long

# Run single test with debug
uv run pytest tests/unit/test_ea_core_modern.py::TestEABasicConversation::test_ea_responds_to_greeting_with_evaluation -v -s
```

### **AI Evaluation Debugging**

When AI evaluations fail:

1. **Check the reasoning**: AI judges provide detailed reasoning
2. **Adjust criteria**: Evaluation questions may need refinement  
3. **Improve EA responses**: Fix underlying conversation quality
4. **Validate test scenarios**: Ensure realistic test cases

### **Common Issues**

- **Slow tests**: Use `pytest -m "not real_api"` for development
- **AI evaluation failures**: Review judge reasoning in test output
- **Memory leaks**: Use `pytest --tb=short` to avoid long tracebacks
- **Docker issues**: Ensure services are running with `docker compose ps`

## 🚀 **Advanced Features**

### **Custom Evaluation Schemas**

```python
class EAResponseQuality(BaseModel):
    passed: bool
    professionalism_score: float  # 0-10
    business_relevance_score: float  # 0-10  
    automation_identification: bool
    confidence_score: float  # 0-1
    suggestions: List[str]

judge = LlmJudge(model_id="gpt-4o-mini", output_type=EAResponseQuality)
```

### **Conversation Simulation**

```python
class ConversationSimulator:
    def __init__(self, persona: str, business_context: Dict[str, Any]):
        self.persona = persona
        self.business_context = business_context
    
    async def generate_user_response(self, ea_message: str) -> str:
        # AI-generated realistic responses based on persona
        pass
```

### **Performance Profiling**

```bash
# Memory usage profiling
pytest tests/ --memray

# Performance benchmarks
pytest tests/ -m performance --benchmark-only
```

## 📚 **Further Reading**

- [Phase-1 PRD](../architecture/Phase-1-PRD.md) - Business requirements
- [TDD Research Plan](../development/TDD-Research-Plan.md) - Original TDD strategy
- [Executive Assistant Implementation](../../src/agents/executive_assistant.py) - EA code
- [Mozilla AnyAgent Docs](https://mozilla-ai.github.io/any-agent/) - AI evaluation framework
- [Inspect AI Docs](https://inspect.aisi.org.uk/) - Agent benchmarking platform

---

**Ready to test?** Start with: `./scripts/quick_test.sh unit`

This modern testing approach ensures our Executive Assistant delivers exceptional conversational AI experiences that meet real business needs. 🚀