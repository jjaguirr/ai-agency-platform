# Scripts Directory

Organized executable scripts for the AI Agency Platform.

## Directory Structure

### 📁 demos/
Interactive demonstration scripts:
- `run_analytics_demo.py` - Business analytics demonstration
- `run_semantic_evaluation_demo.py` - Semantic evaluation demo
- `run_voice_system.py` - Voice interaction system demo
- `start_chat_demo.py` - Basic chat interface demo

### 📁 testing/
Test execution scripts:
- `run_essential_tests.py` - Core business functionality tests
- `test_complete_integration.py` - Full integration test suite
- `test_ea_basic.py` - Basic Executive Assistant tests
- `test_performance_sla.py` - Performance SLA validation

### 📁 validation/
System validation and monitoring:
- `daily_business_validation.py` - Daily business logic validation
- `quick_performance_test.py` - Quick performance checks
- `run_performance_tests.py` - Comprehensive performance testing
- `validate_performance_framework.py` - Performance framework validation

## Usage Examples

```bash
# Run essential business tests
./scripts/testing/run_essential_tests.py

# Start voice system demo
python scripts/demos/run_voice_system.py

# Validate performance framework
python scripts/validation/validate_performance_framework.py

# Quick performance check
python scripts/validation/quick_performance_test.py
```

## Legacy Scripts (Root Level)
Infrastructure and deployment scripts remain in the root scripts directory:
- Shell scripts (.sh) for infrastructure and deployment
- Migration scripts for database updates
- Production validation scripts

---
*All scripts should be executed from the project root directory to ensure proper import paths.*