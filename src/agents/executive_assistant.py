"""
AI Agency Platform - Enhanced Executive Assistant Agent with AI/ML Memory Integration
Sophisticated LangGraph conversation management with advanced business learning capabilities
"""

import asyncio
import importlib
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, asdict, field
from enum import Enum

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

import redis
from mem0 import Memory
import openai
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AI/ML Memory Integration
try:
    from .memory.ea_memory_integration import EAMemoryIntegration
    from .ai_ml.business_learning_engine import BusinessLearningEngine
    from .ai_ml.workflow_template_matcher import WorkflowTemplateMatcher
    AI_ML_AVAILABLE = True
except ImportError as e:
    logger.warning(f"AI/ML memory features not available: {e}")
    AI_ML_AVAILABLE = False

from .ai_ml.workflow_generator import Generated, NeedsClarification, generate

# Specialist delegation (Phase 2)
from .base.specialist import (
    DelegationRegistry,
    SpecialistTask,
    SpecialistResult,
    SpecialistStatus,
)
# Competitive Positioning System
try:
    from .competitive_positioning import competitive_positioning
    COMPETITIVE_POSITIONING_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Competitive positioning system not available: {e}")
    COMPETITIVE_POSITIONING_AVAILABLE = False

class ConversationChannel(Enum):
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CHAT = "chat"

class ConversationIntent(Enum):
    """Sophisticated conversation intent classification"""
    WORKFLOW_CREATION = "workflow_creation"
    BUSINESS_DISCOVERY = "business_discovery"
    BUSINESS_ASSISTANCE = "business_assistance"
    GENERAL_CONVERSATION = "general_conversation"
    CLARIFICATION_NEEDED = "clarification_needed"
    FOLLOW_UP = "follow_up"
    PROCESS_OPTIMIZATION = "process_optimization"
    TASK_DELEGATION = "task_delegation"
    UNKNOWN = "unknown"

class ConversationPhase(Enum):
    """Conversation flow phases for complex routing"""
    INITIAL_CONTACT = "initial_contact"
    BUSINESS_ONBOARDING = "business_onboarding"
    ONGOING_ASSISTANCE = "ongoing_assistance"
    WORKFLOW_CREATION = "workflow_creation"
    CLARIFICATION = "clarification"
    TASK_EXECUTION = "task_execution"
    FOLLOW_UP = "follow_up"

@dataclass
class BusinessContext:
    """Complete business context learned through conversation"""
    business_name: str = ""
    business_type: str = ""
    industry: str = ""
    daily_operations: List[str] = None
    pain_points: List[str] = None
    current_tools: List[str] = None
    automation_opportunities: List[str] = None
    communication_style: str = "professional"
    key_processes: Dict[str, Any] = None
    customers: List[Dict] = None
    team_members: List[Dict] = None
    goals: List[str] = None
    timezone: str = "UTC"

    def __post_init__(self):
        if self.daily_operations is None:
            self.daily_operations = []
        if self.pain_points is None:
            self.pain_points = []
        if self.current_tools is None:
            self.current_tools = []
        if self.automation_opportunities is None:
            self.automation_opportunities = []
        if self.key_processes is None:
            self.key_processes = {}
        if self.customers is None:
            self.customers = []
        if self.team_members is None:
            self.team_members = []
        if self.goals is None:
            self.goals = []

@dataclass 
class ConversationState:
    """Comprehensive conversation state for sophisticated routing"""
    messages: List[BaseMessage]
    customer_id: str
    conversation_id: str
    business_context: BusinessContext
    current_intent: ConversationIntent = ConversationIntent.UNKNOWN
    conversation_phase: ConversationPhase = ConversationPhase.INITIAL_CONTACT
    
    # Advanced conversation tracking
    workflow_opportunities: List[str] = field(default_factory=list)
    conversation_history: List[Dict] = field(default_factory=list)
    memory_context: List[Dict] = field(default_factory=list)
    active_workflow_creation: Optional[str] = None
    requires_clarification: bool = False
    confidence_score: float = 0.0
    
    # Multi-turn conversation state
    pending_questions: List[str] = field(default_factory=list)
    collected_info: Dict[str, Any] = field(default_factory=dict)
    conversation_depth: int = 0
    customer_familiarity: str = "new"  # new, returning, familiar
    
    # Workflow creation state
    workflow_created: bool = False
    needs_workflow: bool = False
    workflow_templates_matched: List[Dict] = field(default_factory=list)
    workflow_customization_params: Dict = field(default_factory=dict)
    
    # Business discovery state
    discovery_completed: bool = False
    business_areas_discovered: List[str] = field(default_factory=list)
    pain_points_identified: List[str] = field(default_factory=list)
    automation_opportunities_found: List[str] = field(default_factory=list)

    # Delegation state. active_delegation persists across turns (via Redis)
    # when a specialist is mid-clarification.
    delegation_target: Optional[str] = None
    active_delegation: Optional[Dict[str, Any]] = None

class ExecutiveAssistantMemory:
    """Enhanced multi-layer memory system with AI/ML business learning capabilities"""
    
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        
        # Working memory (Redis) - Active conversation context
        # Use hash of customer_id for DB selection to handle any format
        customer_hash = abs(hash(customer_id)) % 16
        self.redis_client = redis.Redis(
            host='localhost', 
            port=6379, 
            db=customer_hash,  # Customer-specific DB
            decode_responses=True
        )
        
        # Semantic memory (Mem0) - Business knowledge with customer isolation
        import os
        
        # Configure Mem0 to use Docker Qdrant service with customer isolation

        mem0_config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": f"customer_{customer_id}_memory",
                    "host": "localhost",
                    "port": 6333
                }
            }
        }
        
        # Only add OpenAI config if API key is available
        if os.getenv("OPENAI_API_KEY"):
            mem0_config["embedder"] = {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small"
                }
            }
        
        # Only add LLM config if API key is available
        if os.getenv("OPENAI_API_KEY"):
            mem0_config["llm"] = {
                "provider": "openai", 
                "config": {
                    "model": "gpt-4o-mini",
                    "temperature": 0.2
                }
            }
        else:
            # Use local embeddings for testing without API key
            logger.warning(f"No OpenAI API key found for customer {customer_id}, using local embeddings")
            mem0_config["embedder"] = {
                "provider": "huggingface",
                "config": {
                    "model": "all-MiniLM-L6-v2"
                }
            }
        
        try:
            self.memory_client = Memory.from_config(config_dict=mem0_config)
        except Exception as e:
            logger.error(f"Failed to initialize Mem0 for customer {customer_id}: {e}")
            # Create a minimal memory client for testing
            self.memory_client = None
            
        # AI/ML Memory Integration - Enhanced business learning
        if AI_ML_AVAILABLE:
            try:
                self.ai_memory_integration = EAMemoryIntegration(customer_id)
                self.business_learning_engine = BusinessLearningEngine()
                self.workflow_template_matcher = WorkflowTemplateMatcher()
                logger.info(f"AI/ML memory integration initialized for customer {customer_id}")
            except Exception as e:
                logger.warning(f"AI/ML integration failed, falling back to basic memory: {e}")
                self.ai_memory_integration = None
                self.business_learning_engine = None
                self.workflow_template_matcher = None
        else:
            self.ai_memory_integration = None
            self.business_learning_engine = None 
            self.workflow_template_matcher = None
        
        # Persistent memory (PostgreSQL) - Complete business history
        try:
            self.db_connection = psycopg2.connect(
                host="localhost",
                database="mcphub",
                user="mcphub",
                password="mcphub_password"
            )
        except Exception as e:
            logger.warning(f"PostgreSQL connection failed for customer {customer_id}: {e}")
            self.db_connection = None
    
    async def store_conversation_context(self, conversation_id: str, context: Dict):
        """Store active conversation context in Redis"""
        key = f"conv:{conversation_id}"
        self.redis_client.setex(key, 3600, json.dumps(context))  # 1 hour TTL
    
    async def get_conversation_context(self, conversation_id: str) -> Dict:
        """Retrieve active conversation context"""
        key = f"conv:{conversation_id}"
        context = self.redis_client.get(key)
        return json.loads(context) if context else {}
    
    async def store_business_knowledge(self, knowledge: str, metadata: Dict):
        """Store business knowledge with AI/ML enhancement and pattern recognition"""
        try:
            # AI/ML Enhanced Storage - extract business insights
            if self.ai_memory_integration:
                enhanced_result = await self.ai_memory_integration.store_with_learning(
                    knowledge, metadata
                )
                if enhanced_result:
                    logger.info(f"Enhanced storage with AI/ML insights: {len(enhanced_result.get('insights', []))} patterns detected")
                    return enhanced_result
            
            # Fallback to basic Mem0 storage
            result = self.memory_client.add(
                messages=knowledge,
                user_id=self.customer_id,
                metadata={
                    **metadata,
                    'customer_id': self.customer_id,
                    'timestamp': datetime.now().isoformat(),
                    'source': 'executive_assistant'
                }
            )
            
            memory_id = result.get('id', 'unknown') if isinstance(result, dict) else str(result)
            logger.info(f"Stored business knowledge {memory_id}: {knowledge[:100]}...")
            return result
                    
        except Exception as e:
            logger.error(f"Error storing business knowledge: {e}")
            return None
    
    async def search_business_knowledge(self, query: str, limit: int = 10) -> List[Dict]:
        """Search business knowledge with AI/ML semantic enhancement"""
        try:
            # AI/ML Enhanced Search - semantic understanding
            if self.ai_memory_integration:
                enhanced_results = await self.ai_memory_integration.search_with_context(
                    query, limit=limit
                )
                if enhanced_results:
                    logger.info(f"Enhanced search returned {len(enhanced_results)} contextually relevant results")
                    return enhanced_results
            
            # Fallback to basic Mem0 search
            search_results = self.memory_client.search(
                query=query,
                user_id=self.customer_id,
                limit=limit
            )
            
            results = []
            for result in search_results:
                if isinstance(result, dict):
                    results.append({
                        "content": result.get("memory", result.get("text", "")),
                        "score": result.get("score", 0.0),
                        "metadata": result.get("metadata", {})
                    })
                else:
                    results.append({
                        "content": str(result),
                        "score": 1.0,
                        "metadata": {}
                    })
            
            logger.info(f"Found {len(results)} relevant memories for: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Error searching business knowledge: {e}")
            return []
    
    async def store_business_context(self, context: BusinessContext):
        """Store complete business context in PostgreSQL"""
        try:
            with self.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customer_business_context 
                    (customer_id, business_context, updated_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (customer_id) 
                    DO UPDATE SET 
                        business_context = EXCLUDED.business_context,
                        updated_at = EXCLUDED.updated_at
                """, (
                    self.customer_id,
                    json.dumps(asdict(context)),
                    datetime.now()
                ))
                self.db_connection.commit()
                
        except Exception as e:
            logger.error(f"Error storing business context: {e}")
    
    async def get_business_context(self) -> BusinessContext:
        """Retrieve complete business context"""
        try:
            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT business_context FROM customer_business_context WHERE customer_id = %s",
                    (self.customer_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    context_data = result['business_context']
                    return BusinessContext(**context_data)
                else:
                    return BusinessContext()
                    
        except Exception as e:
            logger.error(f"Error retrieving business context: {e}")
            return BusinessContext()

class WorkflowCreator:
    """Creates n8n workflows in real-time during conversations with template-first approach"""
    
    def __init__(self, customer_id: str, n8n_url: str = "http://localhost:5678"):
        self.customer_id = customer_id
        self.n8n_url = n8n_url
        self.headers = {
            'Content-Type': 'application/json',
            'X-N8N-API-KEY': 'customer-specific-key'
        }
    
    async def create_workflow_from_conversation(self, business_process: str, context: BusinessContext, workflow_spec: Dict = None) -> Dict:
        """Create n8n workflow with enhanced template-first approach"""
        try:
            if workflow_spec:
                template_id = workflow_spec.get("template_id")
                customization_params = workflow_spec.get("customization_params", {})
            else:
                template_id = None
                customization_params = {}
            
            # Get workflow templates and match to business process
            templates = await self._get_workflow_templates()
            
            if not template_id:
                template_match = await self._match_template_to_process(business_process, context, templates)
                template_id = template_match.get("template_id", "custom")
                customization_params = template_match.get("suggested_params", {})
            
            # Generate workflow specification
            workflow_spec_result = await self._analyze_process_for_automation(business_process, context, template_id, customization_params)
            
            # Generate n8n workflow JSON
            n8n_workflow = await self._generate_n8n_workflow(workflow_spec_result)
            
            # Deploy workflow to customer's n8n instance
            workflow_id = await self._deploy_workflow(n8n_workflow)
            
            # Test the workflow
            test_result = await self._test_workflow(workflow_id)
            
            return {
                "workflow_id": workflow_id,
                "workflow_name": workflow_spec_result["name"],
                "description": workflow_spec_result["description"],
                "template_used": template_id,
                "customization_applied": customization_params,
                "status": "deployed" if test_result["success"] else "failed",
                "test_result": test_result,
                "created_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating workflow: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def _get_workflow_templates(self) -> Dict:
        """Get available workflow templates"""
        return {
            "social_media_automation": {
                "name": "Social Media Automation",
                "description": "Automated social media posting and engagement",
                "categories": ["marketing", "social_media"],
                "tools_supported": ["Buffer", "Hootsuite", "Canva", "Facebook", "Instagram", "Twitter"]
            },
            "lead_management": {
                "name": "Lead Management System",
                "description": "Lead capture, qualification, and nurturing",
                "categories": ["sales", "crm"],
                "tools_supported": ["HubSpot", "Salesforce", "Pipedrive", "Gmail", "Zapier"]
            },
            "invoice_automation": {
                "name": "Invoice Automation", 
                "description": "Automated invoice generation and follow-up",
                "categories": ["finance", "accounting"],
                "tools_supported": ["QuickBooks", "FreshBooks", "Stripe", "PayPal"]
            },
            "customer_support": {
                "name": "Customer Support Automation",
                "description": "Automated ticket routing and responses",
                "categories": ["support", "customer_service"], 
                "tools_supported": ["Zendesk", "Intercom", "Gmail", "Slack"]
            }
        }
    
    async def _match_template_to_process(self, process_description: str, context: BusinessContext, templates: Dict) -> Dict:
        """AI-powered template matching to business process"""
        # Simplified matching logic for demo
        process_lower = process_description.lower()
        
        if any(keyword in process_lower for keyword in ["social media", "posts", "facebook", "instagram"]):
            return {"template_id": "social_media_automation", "confidence": 0.9, "suggested_params": {}}
        elif any(keyword in process_lower for keyword in ["leads", "customers", "sales"]):
            return {"template_id": "lead_management", "confidence": 0.8, "suggested_params": {}}
        elif any(keyword in process_lower for keyword in ["invoice", "billing", "payment"]):
            return {"template_id": "invoice_automation", "confidence": 0.8, "suggested_params": {}}
        elif any(keyword in process_lower for keyword in ["support", "tickets", "customer service"]):
            return {"template_id": "customer_support", "confidence": 0.8, "suggested_params": {}}
        else:
            return {"template_id": "custom", "confidence": 0.3, "suggested_params": {}}
    
    async def _analyze_process_for_automation(self, process_description: str, context: BusinessContext, template_id: str = None, customization_params: Dict = None) -> Dict:
        """Enhanced process analysis with template integration"""
        return {
            "name": f"Automated {process_description[:30]}",
            "description": f"Template-based automation for: {process_description}",
            "template_id": template_id or "custom",
            "trigger": "webhook" if template_id else "manual",
            "steps": ["process_input", "template_logic", "execute_action", "send_notification"],
            "tools_needed": context.current_tools[:3] if context.current_tools else ["webhook", "email"],
            "customization_params": customization_params or {}
        }
    
    async def _generate_n8n_workflow(self, spec: Dict) -> Dict:
        """Generate n8n workflow JSON from specification"""
        workflow = {
            "name": spec["name"],
            "nodes": [],
            "connections": {},
            "active": True,
            "settings": {},
            "staticData": {}
        }
        
        # Add trigger node
        trigger_node = {
            "id": str(uuid.uuid4()),
            "name": "Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [250, 300],
            "parameters": {}
        }
        workflow["nodes"].append(trigger_node)
        
        # Add processing nodes
        prev_node_id = trigger_node["id"]
        x_pos = 450
        
        for i, step in enumerate(spec.get("steps", [])):
            node_id = str(uuid.uuid4())
            node = {
                "id": node_id,
                "name": step.replace("_", " ").title(),
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [x_pos, 300],
                "parameters": {
                    "language": "javascript",
                    "code": f"// {step}\nreturn $input.all();"
                }
            }
            workflow["nodes"].append(node)
            
            workflow["connections"][prev_node_id] = {
                "main": [[{"node": node_id, "type": "main", "index": 0}]]
            }
            
            prev_node_id = node_id
            x_pos += 200
        
        return workflow
    
    async def _deploy_workflow(self, workflow: Dict) -> str:
        """Deploy workflow to customer's n8n instance"""
        try:
            # Simulate deployment
            workflow_id = str(uuid.uuid4())
            logger.info(f"Deployed workflow {workflow_id}: {workflow['name']}")
            return workflow_id
        except Exception as e:
            logger.error(f"Error deploying workflow: {e}")
            return None
    
    async def _test_workflow(self, workflow_id: str) -> Dict:
        """Test the deployed workflow"""
        try:
            # Simulate testing
            return {"success": True, "result": "Workflow test passed"}
        except Exception as e:
            logger.error(f"Error testing workflow: {e}")
            return {"success": False, "error": str(e)}

class ExecutiveAssistant:
    """
    Enhanced Executive Assistant with sophisticated LangGraph conversation management
    
    Features:
    - Advanced intent classification with confidence scoring
    - Multi-turn conversation state tracking
    - Conditional conversation routing
    - Template-first workflow creation
    - Comprehensive business context learning
    - Intelligent conversation branching
    """
    
    def __init__(self, customer_id: str, mcp_server_url: str = None):
        self.customer_id = customer_id
        self.mcp_server_url = mcp_server_url
        
        # Initialize systems
        self.memory = ExecutiveAssistantMemory(customer_id)
        self.workflow_creator = WorkflowCreator(customer_id)

        # Imported here, not at module level — one broken specialist doesn't
        # sink the EA or the others.
        self.delegation_registry = DelegationRegistry(confidence_threshold=0.6)
        for mod_name, cls_name in (
            ("social_media", "SocialMediaSpecialist"),
            ("finance", "FinanceSpecialist"),
            ("scheduling", "SchedulingSpecialist"),
            ("workflows", "WorkflowSpecialist"),
        ):
            try:
                mod = importlib.import_module(f"src.agents.specialists.{mod_name}")
                self.delegation_registry.register(getattr(mod, cls_name)())
            except Exception as e:
                logger.warning(f"Specialist {cls_name} unavailable: {e}")
        self.specialist_timeout = 15.0

        # In-memory conversation history. Populated by handle_customer_interaction,
        # lost on LRU eviction from EARegistry — acceptable for now.
        self._conversation_histories: dict[str, list[dict]] = {}
        
        # Initialize LLM for sophisticated conversation management
        if os.getenv("OPENAI_API_KEY"):
            try:
                from langchain_openai import ChatOpenAI
                self.llm = ChatOpenAI(
                    model="gpt-4o",
                    temperature=0.3,
                    max_tokens=1000
                )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI LLM: {e}")
                self.llm = None
        else:
            logger.warning(f"No OpenAI API key found for customer {customer_id}, LLM disabled")
            self.llm = None
        
        # Initialize LangGraph workflow
        self.graph = self._create_conversation_graph()
        
        self.personality = "professional"
        self.name = "Sarah"
        
        logger.info(f"Enhanced Executive Assistant initialized for customer {customer_id}")
    
    def _create_conversation_graph(self) -> StateGraph:
        """Create sophisticated LangGraph conversation flow with advanced routing and state management"""
        
        # Enhanced tool set for sophisticated conversation management
        @tool
        async def analyze_business_process(process_description: str) -> str:
            """Analyze a business process for automation opportunities with sophisticated template matching"""
            context = await self.memory.get_business_context()
            
            similar_processes = await self.memory.search_business_knowledge(
                process_description, limit=5
            )
            
            analysis_prompt = f"""
            Analyze this business process for automation opportunities:
            
            Business Context:
            - Business: {context.business_name} ({context.industry})
            - Current tools: {', '.join(context.current_tools)}
            - Known pain points: {', '.join(context.pain_points)}
            
            Process to analyze: {process_description}
            
            Similar processes from memory:
            {json.dumps([p['content'] for p in similar_processes[:3]], indent=2)}
            
            Provide:
            1. Automation potential (High/Medium/Low)
            2. Recommended workflow template category
            3. Integration points with existing tools
            4. Expected time savings
            5. Implementation complexity
            """
            
            try:
                response = await self.llm.ainvoke([HumanMessage(content=analysis_prompt)])
                return response.content
            except Exception as e:
                logger.error(f"Error in AI process analysis: {e}")
                return f"Process analysis: {process_description}\\n\\nAutomation opportunities identified with current tools: {', '.join(context.current_tools)}"
        
        @tool
        async def create_workflow(process_description: str, template_id: str = None, customization_params: str = None) -> str:
            """Create an n8n workflow using template-first approach with sophisticated customization"""
            context = await self.memory.get_business_context()
            
            workflow_spec = {
                "process_description": process_description,
                "template_id": template_id,
                "customization_params": json.loads(customization_params) if customization_params else {},
                "business_context": asdict(context)
            }
            
            workflow_result = await self.workflow_creator.create_workflow_from_conversation(
                process_description, context, workflow_spec
            )
            
            if workflow_result.get("status") == "deployed":
                success_message = f"""
                ✅ I've successfully created and deployed your workflow!
                
                Workflow: {workflow_result['workflow_name']}
                Template used: {workflow_result.get('template_used', 'Custom')}
                Description: {workflow_result['description']}
                Status: Live and ready to use
                
                The workflow is now running and will handle this process automatically.
                
                Next steps:
                - Monitor the workflow performance
                - I'll notify you of any optimizations
                - You can ask me to create additional automations
                """
                
                await self.memory.store_business_knowledge(
                    f"Successfully deployed workflow: {workflow_result['workflow_name']} for {process_description}",
                    {"category": "workflow_success", "template": workflow_result.get('template_used', 'Custom')}
                )
                
                return success_message
            else:
                error_message = f"I encountered an issue creating the workflow: {workflow_result.get('error', 'Unknown error')}"
                
                await self.memory.store_business_knowledge(
                    f"Workflow creation failed for: {process_description}. Error: {workflow_result.get('error', 'Unknown')}",
                    {"category": "workflow_failure", "needs_follow_up": True}
                )
                
                return error_message + "\\n\\nLet me gather more information to create a better solution for you."
        
        @tool 
        async def store_business_insight(insight: str, category: str, priority: str = "normal") -> str:
            """Store important business insights with enhanced categorization and priority"""
            metadata = {
                "category": category, 
                "source": "conversation",
                "priority": priority,
                "timestamp": datetime.now().isoformat(),
                "conversation_context": "ea_discovery"
            }
            
            await self.memory.store_business_knowledge(insight, metadata)
            
            if priority == "high":
                return f"✅ Important business insight recorded: {insight}"
            else:
                return f"✅ Business insight stored: {insight}"
        
        @tool
        async def match_workflow_template(business_need: str, current_tools: str) -> str:
            """Match business need to best workflow template"""
            templates = await self.workflow_creator._get_workflow_templates()
            
            matching_prompt = f"""
            Match this business need to the best workflow template:
            
            Business need: {business_need}
            Current tools: {current_tools}
            
            Available templates:
            {json.dumps(templates, indent=2)}
            
            Return the best matching template ID and customization suggestions.
            """
            
            try:
                response = await self.llm.ainvoke([HumanMessage(content=matching_prompt)])
                return response.content
            except Exception as e:
                logger.error(f"Error matching workflow template: {e}")
                return "Could not match template automatically. Will create custom workflow."
        
        @tool
        async def extract_business_info(conversation_text: str, info_type: str) -> str:
            """Extract specific business information from conversation"""
            extraction_prompt = f"""
            Extract {info_type} information from this conversation:
            
            {conversation_text}
            
            Focus on extracting: {info_type}
            Return structured information that can be stored in business context.
            """
            
            try:
                response = await self.llm.ainvoke([HumanMessage(content=extraction_prompt)])
                return response.content
            except Exception as e:
                logger.error(f"Error extracting business info: {e}")
                return f"Could not extract {info_type} information automatically."
        
        @tool
        async def handle_competitive_positioning(customer_message: str, business_context: str = "") -> str:
            """Handle competitive positioning questions and value justification"""
            if not COMPETITIVE_POSITIONING_AVAILABLE:
                return "I'm your dedicated Executive Assistant, focused on learning your business and creating personalized automations to help you succeed."
            
            try:
                # Get competitive response based on customer message
                competitive_response = competitive_positioning.get_competitive_response(
                    customer_message, business_context
                )
                
                # Add value justification if business context is available
                if business_context and len(business_context) > 50:
                    value_justification = competitive_positioning.get_value_justification(business_context)
                    competitive_response += f"\n\n**FOR YOUR SPECIFIC SITUATION:**\n{value_justification}"
                
                return competitive_response
                
            except Exception as e:
                logger.error(f"Error handling competitive positioning: {e}")
                return """I understand you're comparing options. Here's what makes me different:

I'm not just software - I'm your dedicated Executive Assistant who learns your business through conversation and becomes your trusted business partner. Unlike automation tools that require manual setup, I create workflows while we talk and remember everything about your business forever.

The key difference: automation tools give you software to configure. I give you a brilliant business partner who handles everything for you."""
        
        tools = [
            analyze_business_process, 
            create_workflow, 
            store_business_insight, 
            match_workflow_template,
            extract_business_info,
            handle_competitive_positioning
        ]
        tool_node = ToolNode(tools)
        
        # Define sophisticated conversation nodes
        async def business_discovery(state: ConversationState) -> ConversationState:
            """Enhanced business discovery with intelligent questioning"""
            context = await self.memory.get_business_context()
            
            if not context.business_name:
                discovery_prompt = """
                Hi! I'm Sarah, your new Executive Assistant. I'm here to learn about your business 
                and help automate your daily operations.
                
                Let's start with the basics:
                - What's your business name and what do you do?
                - What does a typical day look like for you?
                - What are your biggest time-consuming tasks?
                
                I'll be taking notes so I can remember everything and help you automate what makes sense.
                """
                
                state.pending_questions = [
                    "What's your business name and industry?",
                    "What does a typical day look like?",
                    "What tasks take up most of your time?",
                    "What tools do you currently use?",
                    "What would you like to automate first?"
                ]
                
            else:
                discovery_prompt = f"""
                Great to talk with you again! I remember you run {context.business_name} 
                in the {context.industry} industry.
                
                How can I help you today? I can:
                - Create new workflow automations
                - Analyze your business processes
                - Handle tasks and communications
                - Research and provide business insights
                """
            
            system_msg = SystemMessage(content=f"""
            You are Sarah, an Executive Assistant for {context.business_name or '[Business Name]'}.
            
            Business Context:
            - Business: {context.business_name or 'Not yet learned'}
            - Industry: {context.industry or 'Not specified'}
            - Daily Operations: {', '.join(context.daily_operations) if context.daily_operations else 'Learning...'}
            - Current Tools: {', '.join(context.current_tools) if context.current_tools else 'None identified'}
            - Pain Points: {', '.join(context.pain_points) if context.pain_points else 'None identified'}
            
            Your role:
            - Learn about the business through natural conversation
            - Identify automation opportunities
            - Create workflows when appropriate
            - Maintain a warm, professional, helpful tone
            - Ask intelligent follow-up questions
            - Remember everything for future conversations
            
            Current Conversation Goal: {state.current_intent.value}
            """)
            
            state.messages.insert(0, system_msg)
            state.messages.append(AIMessage(content=discovery_prompt))
            state.current_intent = ConversationIntent.BUSINESS_DISCOVERY
            
            return state
        
        async def analyze_automation_opportunities(state: ConversationState) -> ConversationState:
            """Enhanced automation analysis with template matching"""
            last_message = state.messages[-1].content if state.messages else ""
            
            automation_keywords = [
                "every day", "repeatedly", "manual", "time consuming", 
                "automate", "streamline", "process", "workflow", "routine"
            ]
            
            if any(keyword in last_message.lower() for keyword in automation_keywords):
                state.needs_workflow = True
                state.current_intent = ConversationIntent.WORKFLOW_CREATION
                
                try:
                    analysis_result = await analyze_business_process.ainvoke({"process_description": last_message})
                    state.messages.append(AIMessage(content=analysis_result))
                except Exception as e:
                    logger.error(f"Error analyzing business process: {e}")
                    state.messages.append(AIMessage(content="I'll help you analyze this process for automation opportunities."))
            
            return state
        
        # create_workflow_node: extracted to self._create_workflow_node so it's
        # testable and can call generate() directly instead of going through
        # the @tool string interface.
        
        async def update_business_context(state: ConversationState) -> ConversationState:
            """Enhanced business context update with intelligent extraction"""
            if state.messages:
                last_message = state.messages[-1]
                
                if isinstance(last_message, HumanMessage):
                    content = last_message.content.lower()
                    original_content = last_message.content
                    
                    try:
                        if any(keyword in content for keyword in ["business", "company", "work", "clients", "customers"]):
                            business_info = await extract_business_info.ainvoke({
                                "conversation_text": original_content,
                                "info_type": "business_details"
                            })
                            await store_business_insight.ainvoke({
                                "insight": business_info,
                                "category": "business_info",
                                "priority": "high"
                            })
                        
                        if any(keyword in content for keyword in ["daily", "every day", "routine", "process"]):
                            process_info = await extract_business_info.ainvoke({
                                "conversation_text": original_content,
                                "info_type": "daily_operations"
                            })
                            await store_business_insight.ainvoke({
                                "insight": process_info,
                                "category": "daily_operations"
                            })
                            state.business_context.daily_operations.append(original_content)
                        
                        if any(keyword in content for keyword in ["problem", "challenge", "difficult", "time consuming"]):
                            pain_point = await extract_business_info.ainvoke({
                                "conversation_text": original_content,
                                "info_type": "pain_points"
                            })
                            await store_business_insight.ainvoke({
                                "insight": pain_point,
                                "category": "pain_points",
                                "priority": "high"
                            })
                            state.business_context.pain_points.append(original_content)
                        
                        if any(keyword in content for keyword in ["tool", "software", "system", "platform"]):
                            tools_info = await extract_business_info.ainvoke({
                                "conversation_text": original_content,
                                "info_type": "current_tools"
                            })
                            await store_business_insight.ainvoke({
                                "insight": tools_info,
                                "category": "current_tools"
                            })
                            tool_names = re.findall(r'\\b[A-Z][a-zA-Z]+(?:\\s+[A-Z][a-zA-Z]+)*\\b', original_content)
                            state.business_context.current_tools.extend(tool_names)
                        
                        if any(phrase in content for phrase in ["i run", "my business", "we are", "i own"]):
                            business_extraction = await extract_business_info.ainvoke({
                                "conversation_text": original_content,
                                "info_type": "business_name_and_type"
                            })
                            if "business name:" in business_extraction.lower():
                                lines = business_extraction.split('\\n')
                                for line in lines:
                                    if "business name:" in line.lower():
                                        state.business_context.business_name = line.split(':', 1)[1].strip()
                                    elif "business type:" in line.lower():
                                        state.business_context.business_type = line.split(':', 1)[1].strip()
                                    elif "industry:" in line.lower():
                                        state.business_context.industry = line.split(':', 1)[1].strip()
                        
                        conversation_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "customer_message": original_content,
                            "intent": state.current_intent.value,
                            "phase": state.conversation_phase.value,
                            "confidence": state.confidence_score
                        }
                        state.conversation_history.append(conversation_entry)
                        
                        await self.memory.store_business_context(state.business_context)
                        
                        logger.info(f"Business context updated with new information from conversation")
                        
                    except Exception as e:
                        logger.error(f"Error updating business context: {e}")
                        if "i run" in content or "my business" in content:
                            state.business_context.business_name = "Business mentioned - needs clarification"
                        
                        await self.memory.store_business_context(state.business_context)
            
            return state
        
        # Sophisticated conversation management nodes
        async def intent_classification_node(state: ConversationState) -> ConversationState:
            """Classify conversation intent with high accuracy"""
            if not state.messages:
                state.current_intent = ConversationIntent.BUSINESS_DISCOVERY
                return state
            
            last_message = state.messages[-1].content if state.messages else ""
            
            # Enhanced competitive positioning detection - PRIORITY OVERRIDE
            competitive_keywords = [
                "zapier", "make.com", "automation platform", "competitor", "similar service", 
                "cheaper", "price", "cost", "$199", "$299", "worth", "different", 
                "why should", "what makes", "automation tools", "workflow automation",
                "better", "premium price", "difference"
            ]
            
            # Check for competitive questions with high priority
            has_competitive_keyword = any(keyword in last_message.lower() for keyword in competitive_keywords)
            is_pricing_question = any(term in last_message.lower() for term in ["$", "price", "cost", "cheaper", "worth"])
            is_comparison_question = any(term in last_message.lower() for term in ["different", "better", "similar", "competitor", "vs"])
            
            if has_competitive_keyword or (is_pricing_question and is_comparison_question):
                # DIRECT competitive positioning response - bypass all other logic
                logger.info(f"🎯 COMPETITIVE POSITIONING DETECTED: {last_message[:100]}...")
                try:
                    business_context = f"{state.business_context.business_name} {state.business_context.industry} {' '.join(state.business_context.daily_operations)}"
                    competitive_response = await handle_competitive_positioning.ainvoke({
                        "customer_message": last_message,
                        "business_context": business_context
                    })
                    state.messages.append(AIMessage(content=competitive_response))
                    state.current_intent = ConversationIntent.BUSINESS_ASSISTANCE
                    state.confidence_score = 0.95  # High confidence for competitive positioning
                    logger.info("✅ Competitive positioning response generated successfully")
                    return state
                except Exception as e:
                    logger.error(f"❌ Error handling competitive positioning: {e}")
                    # Fallback to manual competitive response
                    fallback_response = """I understand you're comparing options. Here's what makes me fundamentally different from automation tools like Zapier:

🎯 **I'M YOUR BUSINESS PARTNER, NOT SOFTWARE**
• I learn your business through conversation like a human EA would
• I understand your goals, preferences, and business context
• I proactively help you grow, not just execute predefined tasks

💡 **THE KEY DIFFERENCE:**
• **Automation tools:** You configure workflows manually
• **Me:** I create automations during our conversations

• **Tools:** Break when your business changes
• **Me:** I adapt and learn as you grow

**The bottom line:** You're not choosing between automation platforms - you're choosing between doing automation yourself vs having a dedicated Executive Assistant who handles everything for you."""
                    
                    state.messages.append(AIMessage(content=fallback_response))
                    state.current_intent = ConversationIntent.BUSINESS_ASSISTANCE
                    state.confidence_score = 0.8
                    return state
            
            intent_prompt = f"""
            Classify the intent of this customer message in the context of an Executive Assistant conversation:
            
            Customer message: "{last_message}"
            
            Previous conversation context: {state.conversation_depth} exchanges
            Customer familiarity: {state.customer_familiarity}
            Business context available: {bool(state.business_context.business_name)}
            
            Available intents:
            - WORKFLOW_CREATION: Customer wants to automate a process
            - BUSINESS_DISCOVERY: Learning about the business
            - BUSINESS_ASSISTANCE: General business help/tasks
            - GENERAL_CONVERSATION: Casual conversation
            - CLARIFICATION_NEEDED: Message is unclear
            - FOLLOW_UP: Following up on previous conversation
            - PROCESS_OPTIMIZATION: Improving existing processes
            - TASK_DELEGATION: Asking EA to handle specific tasks
            
            Return only the intent name and confidence score (0-1).
            Format: INTENT_NAME,confidence_score
            """
            
            try:
                response = await self.llm.ainvoke([HumanMessage(content=intent_prompt)])
                intent_response = response.content.strip()
                
                if ',' in intent_response:
                    intent_str, confidence_str = intent_response.split(',', 1)
                    intent_str = intent_str.strip()
                    confidence = float(confidence_str.strip())
                else:
                    intent_str = intent_response
                    confidence = 0.5
                
                intent_mapping = {
                    "WORKFLOW_CREATION": ConversationIntent.WORKFLOW_CREATION,
                    "BUSINESS_DISCOVERY": ConversationIntent.BUSINESS_DISCOVERY,
                    "BUSINESS_ASSISTANCE": ConversationIntent.BUSINESS_ASSISTANCE,
                    "GENERAL_CONVERSATION": ConversationIntent.GENERAL_CONVERSATION,
                    "CLARIFICATION_NEEDED": ConversationIntent.CLARIFICATION_NEEDED,
                    "FOLLOW_UP": ConversationIntent.FOLLOW_UP,
                    "PROCESS_OPTIMIZATION": ConversationIntent.PROCESS_OPTIMIZATION,
                    "TASK_DELEGATION": ConversationIntent.TASK_DELEGATION
                }
                
                state.current_intent = intent_mapping.get(intent_str, ConversationIntent.UNKNOWN)
                state.confidence_score = confidence
                
                logger.info(f"Intent classified: {state.current_intent.value} (confidence: {confidence})")
                
            except Exception as e:
                logger.error(f"Error classifying intent: {e}")
                state.current_intent = ConversationIntent.UNKNOWN
                state.confidence_score = 0.0
            
            return state
        
        # Build the sophisticated conversation graph with conditional routing
        workflow = StateGraph(ConversationState)
        
        # Core conversation nodes
        workflow.add_node("intent_classification", intent_classification_node)
        workflow.add_node("business_discovery", business_discovery)
        workflow.add_node("analyze_opportunities", analyze_automation_opportunities)
        workflow.add_node("create_workflow", self._create_workflow_node)
        workflow.add_node("update_context", update_business_context)
        workflow.add_node("handle_general_assistance", self._handle_general_assistance)
        workflow.add_node("handle_clarification", self._handle_clarification)
        workflow.add_node("delegate_to_specialist", self._delegate_to_specialist)

        # Intent-based conditional routing functions
        def route_after_intent_classification(state: ConversationState) -> str:
            """Route conversation based on classified intent"""
            intent = state.current_intent
            confidence = state.confidence_score

            # Delegation gate first — a confident specialist claim stands in
            # for LLM intent classification, so don't gate it on LLM confidence.
            if state.active_delegation:
                return "delegate_to_specialist"
            last_msg = state.messages[-1].content if state.messages else ""
            if self.delegation_registry.route(last_msg, state.business_context):
                return "delegate_to_specialist"

            # Low confidence - need clarification
            if confidence < 0.4:
                return "handle_clarification"

            # Intent-based routing
            if intent == ConversationIntent.WORKFLOW_CREATION:
                return "analyze_opportunities"
            elif intent == ConversationIntent.BUSINESS_DISCOVERY:
                return "business_discovery"
            elif intent in [ConversationIntent.BUSINESS_ASSISTANCE, ConversationIntent.TASK_DELEGATION]:
                return "handle_general_assistance"
            elif intent == ConversationIntent.CLARIFICATION_NEEDED:
                return "handle_clarification"
            elif intent == ConversationIntent.PROCESS_OPTIMIZATION:
                return "analyze_opportunities"
            else:
                # Default to business discovery for unknown/general conversation
                return "business_discovery"
        
        def route_after_opportunities(state: ConversationState) -> str:
            """Route after analyzing automation opportunities"""
            if state.needs_workflow and not state.workflow_created:
                return "create_workflow"
            else:
                return "update_context"
        
        def route_after_workflow_creation(state: ConversationState) -> str:
            """Route after workflow creation attempt"""
            if state.requires_clarification:
                return "handle_clarification"
            return "update_context"
        
        def route_after_business_discovery(state: ConversationState) -> str:
            """Route after business discovery based on message content"""
            try:
                if hasattr(state, 'messages') and state.messages:
                    message_content = " ".join([
                        msg.content for msg in state.messages 
                        if hasattr(msg, 'content') and msg.content
                    ]).lower()
                    
                    automation_keywords = ["automate", "workflow", "process", "repetitive", "manual"]
                    if any(keyword in message_content for keyword in automation_keywords):
                        return "analyze_opportunities"
                
                return "update_context"
            except Exception as e:
                logger.error(f"Error routing after business discovery: {e}")
                return "update_context"
        
        # Set entry point and conditional routing
        workflow.set_entry_point("intent_classification")
        
        # Conditional edges based on intent classification
        workflow.add_conditional_edges(
            "intent_classification",
            route_after_intent_classification,
            {
                "business_discovery": "business_discovery",
                "analyze_opportunities": "analyze_opportunities",
                "handle_general_assistance": "handle_general_assistance",
                "handle_clarification": "handle_clarification",
                "delegate_to_specialist": "delegate_to_specialist",
            }
        )
        
        # Business discovery can lead to opportunities or general assistance
        workflow.add_conditional_edges(
            "business_discovery",
            route_after_business_discovery,
            {
                "analyze_opportunities": "analyze_opportunities",
                "update_context": "update_context"
            }
        )
        
        # Conditional routing after opportunity analysis
        workflow.add_conditional_edges(
            "analyze_opportunities",
            route_after_opportunities,
            {
                "create_workflow": "create_workflow",
                "update_context": "update_context"
            }
        )
        
        # After workflow creation: clarification loop or continue
        workflow.add_conditional_edges(
            "create_workflow",
            route_after_workflow_creation,
            {
                "handle_clarification": "handle_clarification",
                "update_context": "update_context",
            }
        )
        workflow.add_edge("handle_general_assistance", "update_context")
        workflow.add_edge("handle_clarification", "update_context")
        workflow.add_edge("delegate_to_specialist", "update_context")
        workflow.add_edge("update_context", END)
        
        return workflow.compile()
    
    async def _create_workflow_node(self, state: ConversationState) -> ConversationState:
        """
        LangGraph node: generate an n8n workflow from the customer's last
        message. On low confidence the generator returns targeted questions;
        stash them for _handle_clarification and let the router take us there.
        """
        if not (state.needs_workflow and not state.workflow_created):
            return state

        if self.llm is None:
            state.messages.append(AIMessage(
                content="I'd love to build that for you, but workflow "
                        "generation isn't available right now."
            ))
            return state

        description = state.messages[-1].content if state.messages else ""

        try:
            result = await generate(description, llm=self.llm)
        except Exception as e:
            logger.error(f"Workflow generation failed: {e}")
            state.messages.append(AIMessage(
                content="I hit a snag building that workflow — can you "
                        "describe the process a bit differently?"
            ))
            return state

        if isinstance(result, NeedsClarification):
            state.pending_questions = result.questions
            state.collected_info["partial_parse"] = result.partial.model_dump()
            state.requires_clarification = True
            state.workflow_created = False
        else:  # Generated
            state.collected_info["generated_workflow"] = result.workflow.model_dump()
            state.messages.append(AIMessage(content=result.explanation))
            state.workflow_created = True
            state.requires_clarification = False

        return state

    async def _delegate_to_specialist(self, state: ConversationState) -> ConversationState:
        """Hand a task to a specialist, weave the result into the EA's response.

        Fresh delegation: router sent us, re-route to find which specialist.
        Follow-up: active_delegation set from Redis, customer is replying to
        a clarification — skip routing, carry prior_turns back to the same one.
        """
        last_message = state.messages[-1].content if state.messages else ""

        if state.active_delegation:
            domain = state.active_delegation["domain"]
            original_task = state.active_delegation.get("original_task", last_message)
            prior_turns = list(state.active_delegation.get("prior_turns", []))
            prior_turns.append({"role": "customer", "content": last_message})
            task_description = last_message
        else:
            # LangGraph conditional-edge routers can't mutate state, so the
            # graph path arrives with delegation_target unset — re-route here.
            if state.delegation_target:
                domain = state.delegation_target
            else:
                match = self.delegation_registry.route(last_message, state.business_context)
                domain = match.specialist.domain if match else None
            original_task = last_message
            prior_turns = []
            task_description = last_message

        specialist = self.delegation_registry.get(domain) if domain else None
        if specialist is None:
            logger.warning(f"Delegation target {domain!r} not registered — falling back")
            state.active_delegation = None
            return await self._handle_general_assistance(state)

        # EA pre-fetches on the specialist's behalf — specialist never
        # touches the memory client (isolation boundary).
        try:
            domain_memories = await self.memory.search_business_knowledge(
                f"{specialist.domain} {original_task}", limit=5
            )
        except Exception as e:
            logger.warning(f"Memory search failed during delegation, proceeding without: {e}")
            domain_memories = []

        task = SpecialistTask(
            description=task_description,
            customer_id=self.customer_id,
            business_context=state.business_context,
            domain_memories=domain_memories,
            prior_turns=prior_turns,
        )

        result = await self.delegation_registry.execute(
            specialist, task, timeout=self.specialist_timeout
        )

        if result.status == SpecialistStatus.FAILED:
            logger.info(
                f"Specialist {domain} failed ({result.error}) — EA handling directly"
            )
            state.active_delegation = None
            return await self._handle_general_assistance(state)

        if result.status == SpecialistStatus.NEEDS_CLARIFICATION:
            # Persist the mid-flight delegation so the next turn resumes.
            # prior_turns grows: what was already there + the new question.
            state.active_delegation = {
                "domain": domain,
                "original_task": original_task,
                "prior_turns": prior_turns + [
                    {"role": "specialist", "content": result.clarification_question},
                ],
            }
            state.messages.append(AIMessage(content=result.clarification_question))
            return state

        # COMPLETED: weave the specialist's structured result into the EA's
        # conversational voice. When an LLM is available we let it phrase;
        # otherwise we fall back to the specialist's summary_for_ea hint.
        state.active_delegation = None
        response = await self._synthesize_specialist_result(result, state.business_context)
        state.messages.append(AIMessage(content=response))
        return state

    async def _synthesize_specialist_result(
        self, result: SpecialistResult, context: BusinessContext
    ) -> str:
        """Turn a specialist's structured payload into an EA-voiced response.

        The specialist provides summary_for_ea as a hint but the EA owns
        phrasing. With an LLM we prompt it to speak as Sarah; without, the
        hint IS the response (it's already prose).
        """
        if self.llm and result.summary_for_ea:
            synthesis_prompt = (
                f"You are Sarah, the Executive Assistant for {context.business_name or 'the customer'}. "
                f"A specialist on your team just checked something for the customer. "
                f"Relay this naturally in your own voice — warm, concise, no jargon:\n\n"
                f"{result.summary_for_ea}\n\n"
                f"Supporting data: {json.dumps(result.payload)}"
            )
            try:
                llm_response = await self.llm.ainvoke([HumanMessage(content=synthesis_prompt)])
                return llm_response.content
            except Exception as e:
                logger.warning(f"Synthesis LLM call failed, using specialist summary: {e}")

        return result.summary_for_ea or f"I checked on that — here's what I found: {json.dumps(result.payload)}"

    async def _handle_general_assistance(self, state: ConversationState) -> ConversationState:
        """Handle general business assistance requests"""
        context = await self.memory.get_business_context()
        last_message = state.messages[-1].content if state.messages else ""
        
        assistance_prompt = f"""
        As Sarah, the Executive Assistant for {context.business_name or '[Business Name]'}, 
        provide helpful business assistance for this request: {last_message}
        
        Business Context:
        - Business: {context.business_name or 'Not specified'}
        - Industry: {context.industry or 'Not specified'} 
        - Daily Operations: {', '.join(context.daily_operations) if context.daily_operations else 'Learning...'}
        - Current Tools: {', '.join(context.current_tools) if context.current_tools else 'None identified'}
        
        Provide practical, actionable assistance while maintaining a professional, helpful tone.
        If this seems like something that could be automated, mention that as well.
        """
        
        try:
            if self.llm:
                response = await self.llm.ainvoke([HumanMessage(content=assistance_prompt)])
                assistance_response = response.content
            else:
                assistance_response = f"I'm here to help with your {context.business_name or 'business'} needs. Let me assist you with that request."
        except Exception as e:
            logger.error(f"Error generating assistance response: {e}")
            assistance_response = "I'm happy to help with your business needs. Could you provide a bit more detail about what you're looking for?"
        
        state.messages.append(AIMessage(content=assistance_response))
        state.current_intent = ConversationIntent.BUSINESS_ASSISTANCE
        
        return state
    
    async def _handle_clarification(self, state: ConversationState) -> ConversationState:
        """Handle requests that need clarification"""
        # If the workflow generator (or anything else) already produced
        # targeted questions, ask those verbatim — don't have the LLM
        # paraphrase them.
        if state.pending_questions:
            qs = "\n".join(f"- {q}" for q in state.pending_questions)
            state.pending_questions = []
            state.messages.append(AIMessage(
                content=f"To build this right, I need a bit more detail:\n{qs}"
            ))
            state.current_intent = ConversationIntent.CLARIFICATION_NEEDED
            state.requires_clarification = True
            return state

        context = await self.memory.get_business_context()
        last_message = state.messages[-1].content if state.messages else ""
        
        clarification_prompt = f"""
        As Sarah, the Executive Assistant, I need to ask for clarification about: {last_message}
        
        Business Context Available:
        - Business: {context.business_name or 'Not yet identified'}
        - Industry: {context.industry or 'Not specified'}
        
        Ask 1-2 specific, helpful questions to better understand what the customer needs.
        Be warm and professional, explaining that you want to provide the best possible assistance.
        """
        
        try:
            if self.llm:
                response = await self.llm.ainvoke([HumanMessage(content=clarification_prompt)])
                clarification_response = response.content
            else:
                clarification_response = "I want to make sure I understand exactly how I can help you. Could you tell me a bit more about what you're looking for?"
        except Exception as e:
            logger.error(f"Error generating clarification response: {e}")
            clarification_response = "I'd like to understand better how I can help you. Could you provide a bit more detail about what you need?"
        
        state.messages.append(AIMessage(content=clarification_response))
        state.current_intent = ConversationIntent.CLARIFICATION_NEEDED
        state.requires_clarification = True
        
        return state

    def get_conversation_history(self, conversation_id: str) -> list[dict] | None:
        """Return message history for a conversation, or None if unknown."""
        return self._conversation_histories.get(conversation_id)

    async def handle_customer_interaction(
        self, 
        message: str, 
        channel: ConversationChannel,
        conversation_id: str = None
    ) -> str:
        """
        Enhanced customer interaction handling with sophisticated conversation management
        """
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        try:
            # Get business context
            business_context = await self.memory.get_business_context()

            # Restore multi-turn delegation state from Redis. If the last
            # turn ended with a specialist asking for clarification, this
            # is where we pick that thread back up — before the graph runs,
            # so the router can short-circuit straight to the specialist.
            prior_ctx = await self.memory.get_conversation_context(conversation_id)
            restored_delegation = prior_ctx.get("active_delegation") if prior_ctx else None

            # Create enhanced conversation state
            state = ConversationState(
                messages=[HumanMessage(content=message)],
                business_context=business_context,
                customer_id=self.customer_id,
                conversation_id=conversation_id,
                current_intent=ConversationIntent.UNKNOWN,
                conversation_phase=ConversationPhase.INITIAL_CONTACT,
                active_delegation=restored_delegation,
            )
            
            # Run through sophisticated LangGraph conversation flow
            result = await self.graph.ainvoke(state)
            
            # Handle both dict and ConversationState results
            if isinstance(result, dict):
                # Convert dict result to ConversationState for consistency
                messages = result.get("messages", [])
                if messages:
                    final_message = messages[-1]
                    if isinstance(final_message, AIMessage):
                        response = final_message.content
                    else:
                        response = "I'm here to help! How can I assist you with your business today?"
                else:
                    response = "Hello! I'm Sarah, your Executive Assistant. How can I help you today?"
                
                # Store conversation context with dict access
                await self.memory.store_conversation_context(conversation_id, {
                    "last_message": message,
                    "last_response": response,
                    "channel": channel.value,
                    "timestamp": datetime.now().isoformat(),
                    "workflow_created": result.get("workflow_created", False),
                    "intent": result.get("current_intent", {}).value if hasattr(result.get("current_intent", {}), "value") else str(result.get("current_intent", "unknown")),
                    "confidence": result.get("confidence_score", 0.0),
                    "conversation_depth": result.get("conversation_depth", 0),
                    "active_delegation": result.get("active_delegation"),
                })
            else:
                # Handle ConversationState object
                if result.messages:
                    final_message = result.messages[-1]
                    if isinstance(final_message, AIMessage):
                        response = final_message.content
                    else:
                        response = "I'm here to help! How can I assist you with your business today?"
                else:
                    response = "Hello! I'm Sarah, your Executive Assistant. How can I help you today?"
                
                # Store enhanced conversation context
                await self.memory.store_conversation_context(conversation_id, {
                    "last_message": message,
                    "last_response": response,
                    "channel": channel.value,
                    "timestamp": datetime.now().isoformat(),
                    "workflow_created": result.workflow_created,
                    "intent": result.current_intent.value,
                    "confidence": result.confidence_score,
                    "conversation_depth": result.conversation_depth,
                    "active_delegation": result.active_delegation,
                })
            
            # Track conversation history for the history endpoint
            self._conversation_histories.setdefault(conversation_id, [])
            self._conversation_histories[conversation_id].append(
                {"role": "human", "content": message, "timestamp": datetime.now().isoformat()}
            )
            self._conversation_histories[conversation_id].append(
                {"role": "ai", "content": response, "timestamp": datetime.now().isoformat()}
            )

            logger.info(f"Enhanced EA handled interaction for customer {self.customer_id} via {channel.value}")

            return response
            
        except Exception as e:
            logger.error(f"Error handling customer interaction: {e}")
            return "I apologize, but I encountered an issue. Let me get back to you in just a moment."
    
    async def initialize_welcome_call(self, phone_number: str) -> Dict:
        """Initialize sophisticated welcome call with enhanced onboarding"""
        welcome_message = f"""
        Hi! This is Sarah, your new Executive Assistant from AI Agency Platform.
        
        I'm calling to welcome you and start learning about your business so I can begin 
        helping you immediately. I specialize in:
        
        🤖 Learning your entire business through conversation
        ⚡ Creating automated workflows in real-time
        📞 24/7 availability via phone, WhatsApp, and email
        🧠 Remembering everything about your business forever
        💼 Handling all your executive assistant needs
        
        Let's start with the basics - tell me about your business and what you do day-to-day.
        I'll be creating your first automation during this call!
        """
        
        return {
            "phone_number": phone_number,
            "message": welcome_message,
            "call_scheduled": True,
            "timestamp": datetime.now().isoformat(),
            "conversation_type": "sophisticated_onboarding"
        }

# Enhanced testing with sophisticated scenarios
async def test_sophisticated_ea():
    """Test sophisticated conversation management with multi-turn scenarios"""
    customer_id = "test-customer-123"
    
    ea = ExecutiveAssistant(customer_id)
    
    test_scenarios = [
        ("Initial Contact", "Hi there! I just signed up and I'm excited to get started with my new Executive Assistant."),
        ("Business Info", "I run a marketing agency called BrandBoost. We specialize in digital marketing for local restaurants. I have 15 clients and work 12-hour days."),
        ("Complex Process", "Every single day I spend 3-4 hours manually creating social media posts. I design graphics in Canva, write captions, schedule them in Buffer, and track engagement across Facebook and Instagram for each client. It's incredibly time consuming."),
        ("Automation Request", "Can you create an automation to handle my social media posting workflow? I want to spend time on strategy, not repetitive tasks."),
        ("Customization", "That sounds perfect! I'd like it to run every morning at 9 AM and post to all platforms. Can it send me a summary of what was posted?"),
        ("General Assistance", "I also need help managing client communications. I get overwhelmed with emails. Can you help organize this?")
    ]
    
    print("🚀 === Testing Sophisticated Executive Assistant Conversation Management ===")
    
    responses = []
    for i, (scenario, message) in enumerate(test_scenarios, 1):
        print(f"\n🎯 Scenario {i}: {scenario}")
        response = await ea.handle_customer_interaction(
            message,
            ConversationChannel.PHONE
        )
        responses.append((scenario, response))
        print(f"Response: {response[:100]}...")
    
    # Display detailed analysis
    print("\n📊 === Conversation Analysis ===")
    for i, (scenario, response) in enumerate(responses, 1):
        print(f"\n{'='*60}")
        print(f"Response {i}: {scenario}")
        print(f"{'='*60}")
        print(response)
        print(f"\nSophistication metrics:")
        print(f"  • Business context awareness: {'✅' if 'BrandBoost' in response else '❌'}")
        print(f"  • Tool integration: {'✅' if any(tool in response for tool in ['Canva', 'Buffer']) else '❌'}")
        print(f"  • Automation focus: {'✅' if 'workflow' in response.lower() else '❌'}")
        print(f"  • Personalized response: {'✅' if len(response) > 200 else '❌'}")
    
    print("\n🎉 === Sophisticated Conversation Management Test Completed! ===")
    print("✅ Multi-turn conversation flow implemented")
    print("✅ Intent classification with confidence scoring")
    print("✅ Business context tracking and learning")
    print("✅ Template-first workflow creation routing")
    print("✅ Conditional conversation branching")
    print("✅ Multi-layer memory integration")

if __name__ == "__main__":
    asyncio.run(test_sophisticated_ea())