# Performance SLA Standards

**Version:** 1.0  
**Date:** 2025-01-09  
**Status:** Implemented  
**Aligned with:** Phase-1 PRD Requirements

---

## Overview

This document defines standardized performance SLA expectations across all test types for the AI Agency Platform. All performance benchmarks are aligned with Phase-1 PRD business requirements.

## Performance Categories & SLA Targets

### Core Business Requirements (Phase-1 PRD)

| Category | SLA Target | PRD Source | Usage |
|----------|------------|------------|-------|
| **Text Response** | <2 seconds | Phase-1 PRD: EA response time | Phone/WhatsApp interactions |
| **Voice Response** | <500ms | Phase-1 PRD: Voice latency target | ElevenLabs TTS + Whisper STT |
| **Memory Recall** | <500ms | Phase-1 PRD: Memory context retrieval | Business knowledge lookup |

### Test Categories

| Category | SLA Target | Test Scope | Examples |
|----------|------------|------------|----------|
| **Unit Performance** | <100ms | Isolated function tests | Function calls, data parsing |
| **Integration Performance** | <2s | Service-to-service communication | Database ops, API calls |
| **E2E Performance** | <10s | Full user workflow tests | Complete onboarding flow |

### Specialized Scenarios

| Category | SLA Target | Business Context | Examples |
|----------|------------|------------------|----------|
| **Concurrent** | <5s | Multi-customer operations | Parallel EA interactions |
| **Provisioning** | <30s target, <60s limit | EA provisioning (PRD target/limit) | New customer setup |
| **Template Matching** | <5min | Complex AI operations | Workflow template selection |

---

## Implementation Guide

### 1. Using Performance Utilities

**Standard Import:**
```python
from tests.utils.performance_utils import assert_performance_within_sla, get_performance_category_limit
```

**Basic Performance Assertion:**
```python
# Measure performance
start_time = time.time()
response = await ea.handle_message(message, ConversationChannel.PHONE)
response_time = time.time() - start_time

# Assert performance SLA
assert_performance_within_sla(response_time, "text_response", "EA message handling")
```

**Advanced Performance Validation:**
```python
# Get category limit for custom logic
max_time = get_performance_category_limit("memory_recall")
if response_time > max_time * 0.8:  # 80% of limit
    warnings.warn(f"Performance approaching limit: {response_time:.3f}s")

assert_performance_within_sla(response_time, "memory_recall", "business context lookup")
```

### 2. Test Markers

**Use appropriate pytest markers for categorization:**

```python
@pytest.mark.unit_performance
def test_fast_function():
    """Unit test - should complete <100ms."""
    pass

@pytest.mark.integration_performance  
def test_database_operation():
    """Integration test - should complete <2s."""
    pass

@pytest.mark.memory_performance
def test_memory_recall():
    """Memory operation - should complete <500ms."""
    pass

@pytest.mark.provisioning_performance
def test_ea_provisioning():
    """EA provisioning - should complete <30s target, <60s limit."""
    pass
```

### 3. Error Messages

**Standardized error format:**
```
Text Response performance SLA violated (EA message handling): 2.341s > 2.0s (Phase-1 PRD requirement)
```

**Context-aware messages:**
```python
assert_performance_within_sla(
    response_time, 
    "integration", 
    "customer onboarding flow step 3"
)
# Error: Integration performance SLA violated (customer onboarding flow step 3): 2.5s > 2.0s (Phase-1 PRD requirement)
```

---

## Migration Guide

### From Legacy Assertions

**BEFORE (inconsistent):**
```python
assert response_time < 2.0, f"Response time {response_time:.3f}s exceeds 2s requirement"
assert recall_time < 0.5, f"Memory recall: {recall_time:.3f}s > 500ms limit"
assert provisioning_time < 60, f"EA took {provisioning_time:.2f}s > 60s business requirement"
```

**AFTER (standardized):**
```python
assert_performance_within_sla(response_time, "text_response", "specific test context")
assert_performance_within_sla(recall_time, "memory_recall", "memory operation")
assert_performance_within_sla(provisioning_time, "provisioning_limit", "EA provisioning")
```

### Fixture Migration

**BEFORE (deprecated fixture):**
```python
def test_performance(self, ea_performance_benchmarks):
    max_time = ea_performance_benchmarks["response_time"]  # Deprecated
```

**AFTER (standardized utilities):**
```python
def test_performance(self):
    from tests.utils.performance_utils import get_performance_category_limit
    max_time = get_performance_category_limit("text_response")
```

---

## Performance Regression Detection

### Baseline Tracking
```python
# Record baseline performance
baseline_time = 1.2  # seconds
current_time = 1.1   # seconds
regression_threshold = 1.2  # 20% regression allowed

if current_time > baseline_time * regression_threshold:
    raise AssertionError(f"Performance regression detected: {current_time}s > {baseline_time * regression_threshold}s")
```

### Continuous Monitoring
- Track performance trends across test runs
- Alert on >20% performance degradation
- Celebrate >20% performance improvements

---

## Quality Gates

### Pre-Implementation Checklist
- [ ] All requirements have corresponding performance tests
- [ ] Performance categories properly assigned with pytest markers
- [ ] SLA targets align with Phase-1 PRD requirements
- [ ] Test contexts provide meaningful error messages

### CI/CD Integration
- **Green Gate:** All performance tests pass within SLA
- **Yellow Warning:** Performance >80% of SLA limit
- **Red Failure:** Any performance SLA violation

### Test Coverage Requirements
- **Unit Tests:** >95% of core functions have performance validation
- **Integration Tests:** All service interactions have SLA validation  
- **E2E Tests:** All critical user flows validated for performance
- **Memory Tests:** All memory operations validated <500ms

---

## Available Categories Reference

### Performance Categories
```python
VALID_CATEGORIES = [
    "unit",                    # <100ms - isolated function tests
    "integration",             # <2s - service integration  
    "e2e",                     # <10s - full workflow tests
    "text_response",           # <2s - Phase-1 PRD requirement
    "voice_response",          # <500ms - Phase-1 PRD requirement
    "memory_recall",           # <500ms - Phase-1 PRD requirement
    "concurrent",              # <5s - concurrent operations
    "provisioning",            # <30s - EA provisioning target
    "provisioning_limit",      # <60s - EA provisioning limit
    "template_matching"        # <300s - complex AI operations
]
```

### Pytest Markers
```python
AVAILABLE_MARKERS = [
    "unit_performance",        # Unit performance tests (<100ms target)
    "integration_performance", # Integration tests (<2s target)
    "e2e_performance",         # End-to-end tests (<10s target)
    "memory_performance",      # Memory operations (<500ms target)
    "voice_performance",       # Voice operations (<500ms target)
    "provisioning_performance" # EA provisioning tests (<30s target)
]
```

---

## Validation Commands

### Run Performance Framework Tests
```bash
# Test the performance framework itself
pytest tests/test_performance_sla_framework.py -v

# Run all performance-marked tests
pytest -m "performance or unit_performance or integration_performance" -v

# Run specific performance category
pytest -m "memory_performance" -v

# Validate PRD alignment
python -c "from tests.utils.performance_utils import check_prd_alignment; print('PRD Aligned:', check_prd_alignment())"
```

### Performance Reporting
```bash
# Performance test summary
pytest -m "performance" --tb=short -v

# Performance regression detection
pytest tests/test_performance_sla_framework.py::TestPerformanceRegressionDetection -v
```

---

## Success Metrics

### Framework Adoption (Target: 100%)
- [ ] All performance assertions use standardized utilities
- [ ] All tests have appropriate performance markers
- [ ] All SLA targets align with Phase-1 PRD requirements

### Quality Improvements (Target: >95%)
- [ ] Test coverage >80% for critical performance paths
- [ ] Performance SLA compliance >95% across all test categories
- [ ] Zero ad-hoc performance assertions in codebase

### Business Alignment (Target: 100%)
- [ ] Text response: <2s (Phase-1 PRD compliance)
- [ ] Voice response: <500ms (Phase-1 PRD compliance) 
- [ ] Memory recall: <500ms (Phase-1 PRD compliance)
- [ ] EA provisioning: <30s target, <60s limit (Phase-1 PRD compliance)

---

**Document Owner:** Test-QA Agent  
**Next Review:** Weekly during implementation  
**Success Criteria:** Standardized performance SLA expectations across all test types