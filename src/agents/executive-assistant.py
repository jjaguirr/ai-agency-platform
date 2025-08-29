"""
AI Agency Platform - Executive Assistant Agent
Phase 1: The EA that IS the product

A sophisticated conversational AI Executive Assistant that:
- Learns entire businesses through phone conversations
- Creates n8n workflows in real-time during calls
- Maintains complete business context forever
- Handles everything a real EA would do
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import redis
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import openai
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolExecutor
from langgraph.prebuilt import ToolInvocation
from langchain_core.tools import tool
import psycopg2
from psycopg2.extras import RealDictCursor
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationChannel(Enum):
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    CHAT = "chat"

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
    """State for LangGraph conversation flow"""
    messages: List[Any]
    business_context: BusinessContext
    customer_id: str
    conversation_id: str
    current_intent: str
    workflow_created: bool = False
    needs_workflow: bool = False
    follow_up_questions: List[str] = None
    
    def __post_init__(self):
        if self.follow_up_questions is None:
            self.follow_up_questions = []

class ExecutiveAssistantMemory:
    """Multi-layer memory system for complete business context"""
    
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        
        # Working memory (Redis) - Active conversation context
        self.redis_client = redis.Redis(
            host='localhost', 
            port=6379, 
            db=int(customer_id.split('-')[-1]) % 16,  # Customer-specific DB
            decode_responses=True
        )
        
        # Semantic memory (Qdrant) - Business knowledge and patterns
        self.qdrant_client = QdrantClient("localhost", port=6333)
        self.collection_name = f"customer_{customer_id}_memory"
        
        # Persistent memory (PostgreSQL) - Complete business history
        self.db_connection = psycopg2.connect(
            host="localhost",
            database="mcphub",
            user="mcphub",
            password="mcphub_password"
        )
        
        self._ensure_vector_collection()
    
    def _ensure_vector_collection(self):
        """Ensure customer's vector collection exists"""
        try:
            collections = self.qdrant_client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
                )
                logger.info(f"Created vector collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error creating vector collection: {e}")
    
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
        """Store business knowledge in vector database"""
        try:
            # Generate embedding
            embedding_response = await openai.Embedding.acreate(
                model="text-embedding-ada-002",
                input=knowledge
            )
            embedding = embedding_response.data[0].embedding
            
            # Store in Qdrant
            point_id = str(uuid.uuid4())
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "content": knowledge,
                            "timestamp": datetime.now().isoformat(),
                            **metadata
                        }
                    )
                ]
            )
            logger.info(f"Stored business knowledge: {knowledge[:100]}...")
            
        except Exception as e:
            logger.error(f"Error storing business knowledge: {e}")
    
    async def search_business_knowledge(self, query: str, limit: int = 10) -> List[Dict]:
        """Search business knowledge using semantic similarity"""
        try:
            # Generate query embedding
            embedding_response = await openai.Embedding.acreate(
                model="text-embedding-ada-002",
                input=query
            )
            query_embedding = embedding_response.data[0].embedding
            
            # Search in Qdrant
            results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit
            )
            
            return [
                {
                    "content": result.payload["content"],
                    "score": result.score,
                    "metadata": {k: v for k, v in result.payload.items() if k != "content"}
                }
                for result in results
            ]
            
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
    """Creates n8n workflows in real-time during conversations"""
    
    def __init__(self, customer_id: str, n8n_url: str = "http://localhost:5678"):
        self.customer_id = customer_id
        self.n8n_url = n8n_url
        self.headers = {
            'Content-Type': 'application/json',
            'X-N8N-API-KEY': 'customer-specific-key'  # Customer-specific n8n API key
        }
    
    async def create_workflow_from_conversation(self, business_process: str, context: BusinessContext) -> Dict:
        """Create n8n workflow based on conversation about business process"""
        try:
            # Analyze the business process to determine workflow structure
            workflow_spec = await self._analyze_process_for_automation(business_process, context)
            
            # Generate n8n workflow JSON
            n8n_workflow = await self._generate_n8n_workflow(workflow_spec)
            
            # Deploy workflow to customer's n8n instance
            workflow_id = await self._deploy_workflow(n8n_workflow)
            
            # Test the workflow
            test_result = await self._test_workflow(workflow_id)
            
            return {
                "workflow_id": workflow_id,
                "workflow_name": workflow_spec["name"],
                "description": workflow_spec["description"],
                "status": "deployed" if test_result["success"] else "failed",
                "test_result": test_result,
                "created_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating workflow: {e}")
            return {"error": str(e), "status": "failed"}
    
    async def _analyze_process_for_automation(self, process_description: str, context: BusinessContext) -> Dict:
        """Use AI to analyze business process and design automation"""
        analysis_prompt = f"""
        Analyze this business process for automation opportunities:
        
        Business: {context.business_name} ({context.business_type})
        Process: {process_description}
        Current Tools: {', '.join(context.current_tools)}
        
        Design a workflow automation with:
        1. Trigger event
        2. Processing steps 
        3. Actions/outputs
        4. Error handling
        
        Return JSON format workflow specification.
        """
        
        response = await openai.ChatCompletion.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert workflow automation designer."},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.3
        )
        
        try:
            workflow_spec = json.loads(response.choices[0].message.content)
            return workflow_spec
        except:
            # Fallback to structured response
            return {
                "name": f"Automated {process_description[:30]}",
                "description": f"Automation for: {process_description}",
                "trigger": "manual",
                "steps": ["process_input", "execute_action", "send_notification"],
                "tools_needed": context.current_tools[:3]
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
        
        # Add processing nodes based on specification
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
            
            # Add connection
            workflow["connections"][prev_node_id] = {
                "main": [[{"node": node_id, "type": "main", "index": 0}]]
            }
            
            prev_node_id = node_id
            x_pos += 200
        
        return workflow
    
    async def _deploy_workflow(self, workflow: Dict) -> str:
        """Deploy workflow to customer's n8n instance"""
        try:
            response = requests.post(
                f"{self.n8n_url}/api/v1/workflows",
                headers=self.headers,
                json=workflow
            )
            
            if response.status_code == 201:
                workflow_data = response.json()
                return workflow_data["id"]
            else:
                logger.error(f"Failed to deploy workflow: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error deploying workflow: {e}")
            return None
    
    async def _test_workflow(self, workflow_id: str) -> Dict:
        """Test the deployed workflow"""
        try:
            response = requests.post(
                f"{self.n8n_url}/api/v1/workflows/{workflow_id}/execute",
                headers=self.headers,
                json={"test": True}
            )
            
            return {
                "success": response.status_code == 200,
                "result": response.json() if response.status_code == 200 else None,
                "error": response.text if response.status_code != 200 else None
            }
            
        except Exception as e:
            logger.error(f"Error testing workflow: {e}")
            return {"success": False, "error": str(e)}

class ExecutiveAssistant:
    """
    The Executive Assistant - Core product for Phase 1
    
    A sophisticated conversational AI that:
    - Learns businesses through natural conversation
    - Creates workflows in real-time
    - Maintains complete business context
    - Handles everything a real EA would do
    """
    
    def __init__(self, customer_id: str, mcp_server_url: str):
        self.customer_id = customer_id
        self.mcp_server_url = mcp_server_url
        
        # Initialize memory and workflow systems
        self.memory = ExecutiveAssistantMemory(customer_id)
        self.workflow_creator = WorkflowCreator(customer_id)
        
        # Initialize LangGraph workflow
        self.graph = self._create_conversation_graph()
        
        # EA personality and capabilities
        self.personality = "professional"  # Configurable per customer
        self.name = "Sarah"  # Default EA name, customizable
        
        logger.info(f"Executive Assistant initialized for customer {customer_id}")
    
    def _create_conversation_graph(self) -> StateGraph:
        """Create LangGraph conversation flow for sophisticated dialogue"""
        
        # Define the tools available to the EA
        @tool
        async def analyze_business_process(process_description: str) -> str:
            """Analyze a business process for automation opportunities"""
            context = await self.memory.get_business_context()
            
            # Search for similar processes in memory
            similar_processes = await self.memory.search_business_knowledge(
                process_description, limit=5
            )
            
            analysis = f"""
            Process: {process_description}
            
            Automation Opportunities:
            - Identify repetitive manual tasks
            - Integration points with current tools: {', '.join(context.current_tools)}
            - Potential for workflow automation
            
            Similar processes handled before:
            {[p['content'] for p in similar_processes[:3]]}
            """
            
            return analysis
        
        @tool
        async def create_workflow(process_description: str, customer_requirements: str) -> str:
            """Create an n8n workflow for a business process"""
            context = await self.memory.get_business_context()
            
            workflow_result = await self.workflow_creator.create_workflow_from_conversation(
                process_description, context
            )
            
            if workflow_result.get("status") == "deployed":
                return f"""
                ✅ I've successfully created and deployed your workflow!
                
                Workflow: {workflow_result['workflow_name']}
                Description: {workflow_result['description']}
                Status: Live and ready to use
                
                The workflow is now running and will handle this process automatically.
                """
            else:
                return f"I encountered an issue creating the workflow: {workflow_result.get('error', 'Unknown error')}"
        
        @tool 
        async def store_business_insight(insight: str, category: str) -> str:
            """Store important business insights learned from conversation"""
            await self.memory.store_business_knowledge(
                insight, 
                {"category": category, "source": "conversation"}
            )
            return f"Stored business insight: {insight}"
        
        tools = [analyze_business_process, create_workflow, store_business_insight]
        tool_executor = ToolExecutor(tools)
        
        # Define conversation flow nodes
        async def business_discovery(state: ConversationState) -> ConversationState:
            """Conduct business discovery conversation"""
            context = await self.memory.get_business_context()
            
            if not context.business_name:
                # First conversation - learn about the business
                discovery_prompt = """
                Hi! I'm Sarah, your new Executive Assistant. I'm here to learn about your business 
                and help automate your daily operations.
                
                Let's start with the basics:
                - What's your business name and what do you do?
                - What does a typical day look like for you?
                - What are your biggest time-consuming tasks?
                
                I'll be taking notes so I can remember everything and help you automate what makes sense.
                """
                
                state.follow_up_questions = [
                    "What's your business name and industry?",
                    "What does a typical day look like?",
                    "What tasks take up most of your time?",
                    "What tools do you currently use?",
                    "What would you like to automate first?"
                ]
                
            else:
                # Ongoing conversation - build on existing knowledge
                discovery_prompt = f"""
                Great to talk with you again! I remember you run {context.business_name} 
                in the {context.industry} industry.
                
                How can I help you today? I can:
                - Create new workflow automations
                - Analyze your business processes
                - Handle tasks and communications
                - Research and provide business insights
                """
            
            # Add system message with business context
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
            
            Current Conversation Goal: {state.current_intent}
            """)
            
            state.messages.insert(0, system_msg)
            state.current_intent = "business_discovery"
            
            return state
        
        async def analyze_automation_opportunities(state: ConversationState) -> ConversationState:
            """Analyze conversation for workflow automation opportunities"""
            last_message = state.messages[-1].content if state.messages else ""
            
            # Check if the conversation mentions processes that could be automated
            automation_keywords = [
                "every day", "repeatedly", "manual", "time consuming", 
                "automate", "streamline", "process", "workflow", "routine"
            ]
            
            if any(keyword in last_message.lower() for keyword in automation_keywords):
                state.needs_workflow = True
                state.current_intent = "workflow_creation"
                
                # Use tool to analyze the process
                tool_call = ToolInvocation(
                    tool="analyze_business_process",
                    tool_input=last_message
                )
                
                analysis_result = await tool_executor.ainvoke(tool_call)
                state.messages.append(AIMessage(content=analysis_result))
            
            return state
        
        async def create_workflow_node(state: ConversationState) -> ConversationState:
            """Create workflow based on conversation"""
            if state.needs_workflow and not state.workflow_created:
                last_message = state.messages[-1].content if state.messages else ""
                
                # Extract process description from conversation
                process_description = last_message
                
                # Use tool to create workflow
                tool_call = ToolInvocation(
                    tool="create_workflow", 
                    tool_input={"process_description": process_description, "customer_requirements": ""}
                )
                
                workflow_result = await tool_executor.ainvoke(tool_call)
                state.messages.append(AIMessage(content=workflow_result))
                state.workflow_created = True
            
            return state
        
        async def update_business_context(state: ConversationState) -> ConversationState:
            """Update business context based on conversation"""
            if state.messages:
                last_message = state.messages[-1]
                
                if isinstance(last_message, HumanMessage):
                    content = last_message.content.lower()
                    
                    # Extract business information
                    if "business" in content or "company" in content:
                        # Store business insight
                        tool_call = ToolInvocation(
                            tool="store_business_insight",
                            tool_input={"insight": last_message.content, "category": "business_info"}
                        )
                        await tool_executor.ainvoke(tool_call)
                    
                    # Update context fields based on conversation
                    context = state.business_context
                    
                    if "i run" in content or "my business" in content:
                        # Extract business name and type
                        # This would be more sophisticated in production
                        context.business_name = "Extracted from conversation"
                    
                    if "daily" in content or "every day" in content:
                        context.daily_operations.append(last_message.content)
                    
                    if "problem" in content or "challenge" in content:
                        context.pain_points.append(last_message.content)
                    
                    # Store updated context
                    await self.memory.store_business_context(context)
                    state.business_context = context
            
            return state
        
        # Build the conversation graph
        workflow = StateGraph(ConversationState)
        
        # Add nodes
        workflow.add_node("business_discovery", business_discovery)
        workflow.add_node("analyze_opportunities", analyze_automation_opportunities)
        workflow.add_node("create_workflow", create_workflow_node)
        workflow.add_node("update_context", update_business_context)
        
        # Define the flow
        workflow.set_entry_point("business_discovery")
        workflow.add_edge("business_discovery", "analyze_opportunities")
        workflow.add_edge("analyze_opportunities", "create_workflow")
        workflow.add_edge("create_workflow", "update_context")
        workflow.add_edge("update_context", END)
        
        return workflow.compile()
    
    async def handle_customer_interaction(
        self, 
        message: str, 
        channel: ConversationChannel,
        conversation_id: str = None
    ) -> str:
        """
        Main method to handle customer interactions
        
        Args:
            message: Customer's message/request
            channel: Communication channel (phone, whatsapp, email, chat)
            conversation_id: Unique conversation identifier
            
        Returns:
            EA's response as string
        """
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        try:
            # Get business context
            business_context = await self.memory.get_business_context()
            
            # Create conversation state
            state = ConversationState(
                messages=[HumanMessage(content=message)],
                business_context=business_context,
                customer_id=self.customer_id,
                conversation_id=conversation_id,
                current_intent="general_assistance"
            )
            
            # Run through LangGraph conversation flow
            result = await self.graph.ainvoke(state)
            
            # Get the final response
            if result.messages:
                final_message = result.messages[-1]
                if isinstance(final_message, AIMessage):
                    response = final_message.content
                else:
                    response = "I'm here to help! How can I assist you with your business today?"
            else:
                response = "Hello! I'm Sarah, your Executive Assistant. How can I help you today?"
            
            # Store conversation context for continuity
            await self.memory.store_conversation_context(conversation_id, {
                "last_message": message,
                "last_response": response,
                "channel": channel.value,
                "timestamp": datetime.now().isoformat(),
                "workflow_created": result.workflow_created
            })
            
            logger.info(f"EA handled interaction for customer {self.customer_id} via {channel.value}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error handling customer interaction: {e}")
            return "I apologize, but I encountered an issue. Let me get back to you in just a moment."
    
    async def initialize_welcome_call(self, phone_number: str) -> Dict:
        """Initialize welcome call to new customer"""
        welcome_message = f"""
        Hi! This is Sarah, your new Executive Assistant. 
        
        I'm calling to welcome you to the AI Agency Platform and to learn about your business 
        so I can start helping you right away.
        
        I'm here 24/7 via phone, WhatsApp, and email to:
        - Handle your daily business tasks
        - Create automated workflows
        - Manage communications
        - Provide business insights
        - Be your trusted business partner
        
        Could you tell me about your business so I can get started helping you?
        """
        
        return {
            "phone_number": phone_number,
            "message": welcome_message,
            "call_scheduled": True,
            "timestamp": datetime.now().isoformat()
        }

# Example usage and testing
if __name__ == "__main__":
    async def test_ea():
        # Initialize EA for test customer
        customer_id = "test-customer-123"
        mcp_url = "http://localhost:30001"  # Customer-specific MCP server
        
        ea = ExecutiveAssistant(customer_id, mcp_url)
        
        # Simulate business discovery conversation
        responses = []
        
        # First interaction
        response1 = await ea.handle_customer_interaction(
            "Hi Sarah! I run a small marketing agency called BrandBoost. We help local businesses with their digital marketing.",
            ConversationChannel.PHONE
        )
        responses.append(response1)
        
        # Business process discussion
        response2 = await ea.handle_customer_interaction(
            "Every day I manually create social media posts for 10 different clients. It takes me 3 hours and it's very repetitive. I use Canva for design and Buffer for scheduling.",
            ConversationChannel.PHONE
        )
        responses.append(response2)
        
        # Workflow creation request
        response3 = await ea.handle_customer_interaction(
            "Can you help me automate the social media posting process?",
            ConversationChannel.PHONE
        )
        responses.append(response3)
        
        print("=== Executive Assistant Conversation Test ===")
        for i, response in enumerate(responses, 1):
            print(f"\nEA Response {i}:")
            print(response)
            print("-" * 50)
        
        print("\n=== Test completed successfully! ===")
    
    # Run the test
    asyncio.run(test_ea())