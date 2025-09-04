"""
Performance Testing Utilities

Standardized performance assertion utilities for consistent SLA validation
across all test files. Aligned with Phase-1 PRD requirements.
"""

# Standard performance benchmarks aligned with Phase-1 PRD
PERFORMANCE_BENCHMARKS = {
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
    "provisioning_limit_time": 60.0,   # <60s for EA provisioning (PRD limit)
    "template_matching_max_time": 300.0, # <5min for complex AI operations
}

def assert_performance_within_sla(response_time: float, test_category: str, context: str = "", benchmarks: dict = None):
    """
    Standardized performance assertion with clear error messages.
    
    Args:
        response_time: Measured response time in seconds
        test_category: Performance category (e.g., 'text_response', 'memory_recall', 'integration')
        context: Optional context for error message
        benchmarks: Optional custom benchmarks dict (defaults to PERFORMANCE_BENCHMARKS)
    
    Raises:
        ValueError: If test_category is unknown
        AssertionError: If performance SLA is violated
    """
    if benchmarks is None:
        benchmarks = PERFORMANCE_BENCHMARKS
        
    category_mapping = {
        "unit": "unit_max_time",
        "integration": "integration_max_time", 
        "e2e": "e2e_max_time",
        "text_response": "text_response_max_time",
        "voice_response": "voice_response_max_time",
        "memory_recall": "memory_recall_max_time",
        "concurrent": "concurrent_max_time",
        "provisioning": "provisioning_max_time",
        "provisioning_limit": "provisioning_limit_time",
        "template_matching": "template_matching_max_time"
    }
    
    max_time_key = category_mapping.get(test_category)
    if not max_time_key:
        raise ValueError(f"Unknown test category: {test_category}. Valid categories: {list(category_mapping.keys())}")
        
    max_time = benchmarks[max_time_key]
    context_msg = f" ({context})" if context else ""
    
    assert response_time < max_time, (
        f"{test_category.title().replace('_', ' ')} performance SLA violated{context_msg}: "
        f"{response_time:.3f}s > {max_time}s (Phase-1 PRD requirement)"
    )

def get_performance_category_limit(test_category: str, benchmarks: dict = None) -> float:
    """
    Get performance limit for a test category.
    
    Args:
        test_category: Performance category
        benchmarks: Optional custom benchmarks dict (defaults to PERFORMANCE_BENCHMARKS)
    
    Returns:
        Performance limit in seconds
    """
    if benchmarks is None:
        benchmarks = PERFORMANCE_BENCHMARKS
        
    category_mapping = {
        "unit": "unit_max_time",
        "integration": "integration_max_time", 
        "e2e": "e2e_max_time",
        "text_response": "text_response_max_time",
        "voice_response": "voice_response_max_time",
        "memory_recall": "memory_recall_max_time",
        "concurrent": "concurrent_max_time",
        "provisioning": "provisioning_max_time",
        "provisioning_limit": "provisioning_limit_time",
        "template_matching": "template_matching_max_time"
    }
    
    max_time_key = category_mapping.get(test_category)
    if not max_time_key:
        raise ValueError(f"Unknown test category: {test_category}")
        
    return benchmarks[max_time_key]

def check_prd_alignment():
    """Verify that benchmarks align with Phase-1 PRD requirements."""
    prd_requirements = {
        "text_response": 2.0,     # Phase-1 PRD: <2 seconds response time
        "voice_response": 0.5,    # Phase-1 PRD: <500ms voice latency
        "memory_recall": 0.5,     # Phase-1 PRD: <500ms memory recall
        "provisioning": 30.0,     # Phase-1 PRD: <30s provisioning target
    }
    
    for req_name, expected_limit in prd_requirements.items():
        actual_limit = get_performance_category_limit(req_name)
        assert actual_limit == expected_limit, (
            f"PRD misalignment: {req_name} limit {actual_limit}s != {expected_limit}s PRD requirement"
        )
    
    return True

def format_performance_assertion_legacy(response_time: float, limit_time: float, context: str = "") -> str:
    """
    Format legacy performance assertion for backward compatibility.
    DEPRECATED: Use assert_performance_within_sla instead.
    """
    import warnings
    warnings.warn(
        "format_performance_assertion_legacy is deprecated. Use assert_performance_within_sla instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    context_msg = f" ({context})" if context else ""
    return f"Performance SLA violated{context_msg}: {response_time:.3f}s > {limit_time}s"