#!/usr/bin/env python3
"""
Test script to verify real ExecutiveAssistant imports work correctly
Run this to validate the test infrastructure fixes
"""

import sys
import traceback
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

def test_imports():
    """Test that all ExecutiveAssistant imports work without fallbacks."""
    print("🔍 Testing Real ExecutiveAssistant Imports...")
    
    try:
        print("  ✓ Importing core classes...")
        from src.agents.executive_assistant import (
            ExecutiveAssistant, 
            ConversationChannel, 
            BusinessContext,
            ConversationIntent,
            ConversationPhase,
            ExecutiveAssistantMemory,
            WorkflowCreator
        )
        print("  ✅ Core imports successful")
        
        print("  ✓ Testing enum values...")
        assert ConversationChannel.PHONE.value == "phone"
        assert ConversationChannel.WHATSAPP.value == "whatsapp" 
        assert ConversationChannel.EMAIL.value == "email"
        assert ConversationChannel.CHAT.value == "chat"
        print("  ✅ Enum values correct")
        
        print("  ✓ Testing BusinessContext dataclass...")
        context = BusinessContext(
            business_name="Test Business",
            industry="technology",
            daily_operations=["coding", "meetings"]
        )
        assert context.business_name == "Test Business"
        assert context.industry == "technology"
        assert "coding" in context.daily_operations
        print("  ✅ BusinessContext working")
        
        print("  ✓ Testing ExecutiveAssistant instantiation...")
        ea = ExecutiveAssistant(customer_id="test_123")
        assert ea.customer_id == "test_123"
        assert ea.memory is not None
        assert ea.workflow_creator is not None
        assert ea.graph is not None
        print("  ✅ ExecutiveAssistant instantiation successful")
        
        print("  ✓ Testing memory components...")
        assert ea.memory.customer_id == "test_123"
        assert ea.memory.redis_client is not None
        assert ea.memory.memory_client is not None
        assert ea.memory.db_connection is not None
        print("  ✅ Memory components initialized")
        
        print("\n🎉 All imports successful - no mock fallbacks used!")
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        print("  🔧 Fix: Check that all dependencies are installed")
        print("  🔧 Run: pip install -r requirements-dev.txt")
        traceback.print_exc()
        return False
    
    except Exception as e:
        print(f"  ❌ Initialization error: {e}")
        print("  🔧 Check that Redis and PostgreSQL services are running")
        print("  🔧 Run: docker-compose up redis postgres")
        traceback.print_exc()
        return False

def test_dependencies():
    """Test that all required dependencies are available."""
    print("\n🔍 Testing Dependencies...")
    
    dependencies = [
        ("redis", "Redis client"),
        ("psycopg2", "PostgreSQL client"),
        ("mem0", "Mem0 AI memory"),
        ("openai", "OpenAI API client"),
        ("langchain_core", "LangChain core"),
        ("langgraph", "LangGraph"),
        ("pytest", "Pytest testing framework"),
        ("pytest_asyncio", "Async pytest support")
    ]
    
    missing_deps = []
    
    for dep_name, desc in dependencies:
        try:
            __import__(dep_name)
            print(f"  ✅ {desc} available")
        except ImportError:
            print(f"  ❌ {desc} missing")
            missing_deps.append(dep_name)
    
    if missing_deps:
        print(f"\n🔧 Missing dependencies: {', '.join(missing_deps)}")
        print("🔧 Run: pip install -r requirements-dev.txt")
        return False
    
    print("\n🎉 All dependencies available!")
    return True

async def test_basic_functionality():
    """Test basic ExecutiveAssistant functionality."""
    print("\n🔍 Testing Basic EA Functionality...")
    
    try:
        from src.agents.executive_assistant import ExecutiveAssistant, ConversationChannel
        
        # Create EA instance
        ea = ExecutiveAssistant(customer_id="test_functionality_123")
        
        # Test basic conversation handling (will use mock services if real ones unavailable)
        print("  ✓ Testing basic conversation...")
        response = await ea.handle_customer_interaction(
            "Hello, I need help with my business",
            ConversationChannel.CHAT
        )
        
        assert response is not None
        assert len(response) > 0
        print(f"  ✅ Got response: {response[:100]}...")
        
        # Test memory operations
        print("  ✓ Testing memory storage...")
        await ea.memory.store_business_knowledge(
            "Test business knowledge",
            {"category": "test", "priority": "low"}
        )
        print("  ✅ Memory storage successful")
        
        # Test memory retrieval
        print("  ✓ Testing memory retrieval...")
        results = await ea.memory.search_business_knowledge("test business")
        print(f"  ✅ Found {len(results)} memory results")
        
        # Cleanup
        try:
            ea.memory.redis_client.delete(f"conv:*")
        except:
            pass  # Cleanup not critical for test
        
        print("\n🎉 Basic functionality test passed!")
        return True
        
    except Exception as e:
        print(f"  ❌ Functionality test failed: {e}")
        print("  🔧 This might be due to missing services (Redis/PostgreSQL)")
        print("  🔧 Tests will still run but may use mock services")
        traceback.print_exc()
        return False

def main():
    """Run all import and functionality tests."""
    print("=" * 60)
    print("🧪 TESTING REAL EXECUTIVE ASSISTANT INFRASTRUCTURE")
    print("=" * 60)
    
    success = True
    
    # Test dependencies
    if not test_dependencies():
        success = False
    
    # Test imports
    if not test_imports():
        success = False
        return
    
    # Test basic functionality 
    import asyncio
    try:
        functionality_success = asyncio.run(test_basic_functionality())
        if not functionality_success:
            success = False
    except Exception as e:
        print(f"❌ Could not test functionality: {e}")
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALL TESTS PASSED - Ready to run real EA tests!")
        print("🚀 Run: pytest tests/integration/test_real_executive_assistant.py")
    else:
        print("❌ SOME TESTS FAILED - Check errors above")
        print("🔧 Fix dependencies and services before running real tests")
    print("=" * 60)

if __name__ == "__main__":
    main()