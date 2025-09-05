"""
Simple FastAPI server to connect chat UI with Executive Assistant
"""

import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agents.executive_assistant import ExecutiveAssistant, ConversationChannel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Agency Chat API")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

class ChatMessage(BaseModel):
    message: str
    customer_id: str
    conversation_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    status: str

# Store EA instances per customer
ea_instances = {}

def get_or_create_ea(customer_id: str) -> ExecutiveAssistant:
    """Get or create EA instance for customer"""
    if customer_id not in ea_instances:
        ea_instances[customer_id] = ExecutiveAssistant(customer_id)
        logger.info(f"Created new EA instance for customer {customer_id}")
    return ea_instances[customer_id]

@app.get("/")
async def root():
    return RedirectResponse(url="/chat")

@app.get("/chat")
async def chat_ui():
    """Serve the chat interface directly"""
    chat_html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "chat", "index.html")
    return FileResponse(chat_html_path)

@app.get("/style.css")
async def chat_css():
    """Serve chat CSS"""
    css_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "chat", "style.css")
    return FileResponse(css_path, media_type="text/css")

@app.get("/script.js")
async def chat_js():
    """Serve chat JavaScript"""
    js_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "chat", "script.js")
    return FileResponse(js_path, media_type="application/javascript")

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatMessage):
    """Handle chat messages from frontend"""
    try:
        logger.info(f"Chat request from {request.customer_id}: {request.message[:100]}...")
        
        # Get or create EA for this customer
        ea = get_or_create_ea(request.customer_id)
        
        # Process message through EA
        response = await ea.handle_customer_interaction(
            message=request.message,
            channel=ConversationChannel.CHAT,
            conversation_id=request.conversation_id
        )
        
        logger.info(f"EA response length: {len(response)} chars")
        
        return ChatResponse(
            response=response,
            conversation_id=request.conversation_id or "default",
            status="success"
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Chat processing failed: {str(e)}"
        )

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "ea_instances": len(ea_instances)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)