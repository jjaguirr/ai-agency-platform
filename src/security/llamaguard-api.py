#!/usr/bin/env python3
"""
Llama Guard 4 API Wrapper Service
Provides HTTP API for MCPhub integration with Llama Guard 4 security filtering
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import os
import yaml
import aiohttp
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import uvicorn
from jose import JWTError, jwt
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
LLAMAGUARD_ENABLED = os.getenv("LLAMAGUARD_ENABLED", "true").lower() == "true"
LLAMAGUARD_URL = os.getenv("LLAMAGUARD_URL", "http://llamaguard-security:80")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis-security:6379")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = "HS256"

# Log the current mode
if LLAMAGUARD_ENABLED:
    logger.info("Llama Guard 4 security is ENABLED - Real AI safety evaluation")
else:
    logger.warning("Llama Guard 4 security is DISABLED - BYPASS MODE for development")

# Initialize FastAPI app
app = FastAPI(
    title="Llama Guard 4 Security API",
    description="LLM Safety and Content Moderation Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration for MCPhub integration - PRODUCTION SECURE
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://mcphub-server:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Only allow specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Specific methods only
    allow_headers=["Content-Type", "Authorization", "X-Customer-ID", "X-Security-Tier"],  # Specific headers only
)

# Global variables
redis_client: Optional[redis.Redis] = None
safety_policies: Dict = {}
security_bearer = HTTPBearer()

# Authentication and Customer Isolation
class CustomerContext(BaseModel):
    """Customer context extracted from JWT token"""
    customer_id: str
    user_id: str
    security_tier: str
    group_permissions: List[str] = []

async def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> CustomerContext:
    """Verify JWT token and extract customer context"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        customer_id = payload.get("customer_id")
        user_id = payload.get("user_id") 
        security_tier = payload.get("security_tier", "basic")
        group_permissions = payload.get("groups", [])
        
        if not customer_id or not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing customer or user ID")
            
        return CustomerContext(
            customer_id=customer_id,
            user_id=user_id,
            security_tier=security_tier,
            group_permissions=group_permissions
        )
        
    except JWTError as e:
        logger.error(f"JWT validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid authentication token")

async def validate_customer_isolation(context: CustomerContext, request_customer_id: str) -> bool:
    """Ensure customer can only access their own data"""
    if context.customer_id != request_customer_id:
        logger.warning(f"Customer isolation violation: {context.customer_id} tried to access {request_customer_id}")
        raise HTTPException(status_code=403, detail="Customer isolation violation")
    return True

class SecurityRequest(BaseModel):
    """Security evaluation request model"""
    content: str = Field(..., description="Content to evaluate for safety")
    user_id: str = Field(..., description="User ID for audit logging")
    customer_id: str = Field(..., description="Customer ID for isolation")
    security_tier: str = Field("basic", description="Customer security tier")
    request_type: str = Field("input", description="input or output filtering")
    context: Optional[Dict] = Field(default_factory=dict, description="Additional context")

class SecurityResponse(BaseModel):
    """Security evaluation response model"""
    safe: bool = Field(..., description="Whether content is safe")
    violations: List[Dict] = Field(default_factory=list, description="Safety violations found")
    sanitized_content: Optional[str] = Field(None, description="Cleaned content if applicable")
    confidence: float = Field(..., description="Confidence score (0-1)")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    metadata: Dict = Field(default_factory=dict, description="Additional metadata")

class LlamaGuardClient:
    """Client for interacting with Llama Guard 4 service"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize HTTP client session"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        )
    
    async def close(self):
        """Close HTTP client session"""
        if self.session:
            await self.session.close()
    
    async def evaluate_content(self, content: str, policy_type: str = "general") -> Tuple[bool, List[Dict], float]:
        """
        Evaluate content safety using Llama Guard 4
        
        Args:
            content: Text content to evaluate
            policy_type: Type of safety policy to apply
            
        Returns:
            Tuple of (is_safe, violations, confidence)
        """
        start_time = time.time()
        
        try:
            # Construct Llama Guard prompt based on policy type
            safety_prompt = self._construct_safety_prompt(content, policy_type)
            
            # Call Llama Guard 4 service
            payload = {
                "inputs": safety_prompt,
                "parameters": {
                    "max_new_tokens": 100,
                    "temperature": 0.1,
                    "do_sample": False,
                    "return_full_text": False
                }
            }
            
            async with self.session.post(
                f"{self.base_url}/generate",
                json=payload
            ) as response:
                if response.status != 200:
                    logger.error(f"Llama Guard API error: {response.status}")
                    # Fail secure - if service is down, block potentially unsafe content
                    return False, [{"type": "service_error", "reason": "Safety service unavailable"}], 0.5
                
                result = await response.json()
                
                # Parse Llama Guard response
                is_safe, violations, confidence = self._parse_llamaguard_response(result)
                
                processing_time = (time.time() - start_time) * 1000
                logger.info(f"Safety evaluation completed in {processing_time:.2f}ms - Safe: {is_safe}")
                
                return is_safe, violations, confidence
                
        except asyncio.TimeoutError:
            logger.error("Llama Guard API timeout")
            return False, [{"type": "timeout_error", "reason": "Safety evaluation timed out"}], 0.5
        except Exception as e:
            logger.error(f"Llama Guard API error: {str(e)}")
            return False, [{"type": "api_error", "reason": str(e)}], 0.5
    
    def _construct_safety_prompt(self, content: str, policy_type: str) -> str:
        """Construct appropriate safety evaluation prompt for Llama Guard 4"""
        
        # Base safety categories (MLCommons taxonomy)
        safety_categories = """
<BEGIN UNSAFE CONTENT CATEGORIES>
S1: Violence
S2: Hate
S3: Sexual Content  
S4: Criminal Planning
S5: Defamation
S6: Elections
S7: Privacy
S8: Intellectual Property
S9: Harassment
S10: Specialized Advice
S11: Discrimination
S12: Self-Harm
<END UNSAFE CONTENT CATEGORIES>
        """.strip()
        
        # Customize based on policy type
        if policy_type == "strict":
            instruction = "Evaluate the following content with strict safety standards."
        elif policy_type == "healthcare":
            instruction = "Evaluate the following content for healthcare compliance and patient safety."
        elif policy_type == "finance":
            instruction = "Evaluate the following content for financial compliance and fraud prevention."
        else:
            instruction = "Evaluate the following content for general safety violations."
        
        prompt = f"""Task: Check if there is unsafe content in 'User' messages in conversations according to our safety policy with the below categories.

{safety_categories}

<BEGIN CONVERSATION>
User: {content}
<END CONVERSATION>

Provide your safety assessment."""

        return prompt
    
    def _parse_llamaguard_response(self, response: Dict) -> Tuple[bool, List[Dict], float]:
        """Parse Llama Guard 4 response and extract safety information"""
        
        try:
            generated_text = response.get("generated_text", "").strip()
            
            # Llama Guard typically responds with "safe" or "unsafe" followed by categories
            is_safe = "safe" in generated_text.lower() and "unsafe" not in generated_text.lower()
            violations = []
            confidence = 0.9  # High confidence in Llama Guard decisions
            
            if not is_safe:
                # Extract violated categories
                lines = generated_text.split('\n')
                for line in lines:
                    if line.startswith('S') and ':' in line:
                        category = line.strip()
                        violations.append({
                            "type": "safety_violation",
                            "category": category,
                            "confidence": confidence
                        })
            
            return is_safe, violations, confidence
            
        except Exception as e:
            logger.error(f"Error parsing Llama Guard response: {str(e)}")
            # Fail secure
            return False, [{"type": "parse_error", "reason": str(e)}], 0.5

# Global Llama Guard client
llamaguard_client = LlamaGuardClient(LLAMAGUARD_URL)

async def load_safety_policies():
    """Load safety policies configuration"""
    global safety_policies
    try:
        with open("/app/config/safety-policies.yaml", "r") as f:
            safety_policies = yaml.safe_load(f)
        logger.info("Safety policies loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load safety policies: {str(e)}")
        # Use default policies
        safety_policies = {
            "basic": {"policy_type": "general", "strict_mode": False},
            "professional": {"policy_type": "strict", "strict_mode": True},
            "enterprise": {"policy_type": "strict", "strict_mode": True, "custom_rules": True}
        }

async def get_redis_client() -> redis.Redis:
    """Get Redis client for caching and rate limiting"""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client

async def log_security_event(event_data: Dict):
    """Log security events for audit purposes"""
    try:
        redis_client = await get_redis_client()
        event_key = f"security_event:{datetime.utcnow().isoformat()}"
        await redis_client.setex(event_key, 86400 * 7, json.dumps(event_data))  # Keep for 7 days
        logger.info(f"Security event logged: {event_data.get('event_type', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to log security event: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    await llamaguard_client.initialize()
    await load_safety_policies()
    logger.info("Llama Guard API service started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await llamaguard_client.close()
    if redis_client:
        await redis_client.close()
    logger.info("Llama Guard API service stopped")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # In bypass mode, skip Llama Guard connectivity check
        if LLAMAGUARD_ENABLED:
            # Test Llama Guard connectivity
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{LLAMAGUARD_URL}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    llamaguard_healthy = response.status == 200
        else:
            llamaguard_healthy = True  # Bypass mode - always healthy
        
        # Test Redis connectivity
        redis_client = await get_redis_client()
        await redis_client.ping()
        redis_healthy = True
        
        return {
            "status": "healthy" if llamaguard_healthy and redis_healthy else "unhealthy",
            "llamaguard": "bypass" if not LLAMAGUARD_ENABLED else ("up" if llamaguard_healthy else "down"),
            "redis": "up" if redis_healthy else "down",
            "mode": "bypass" if not LLAMAGUARD_ENABLED else "production",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.post("/evaluate", response_model=SecurityResponse)
async def evaluate_content(
    request: SecurityRequest, 
    background_tasks: BackgroundTasks,
    context: CustomerContext = Depends(verify_jwt_token)
):
    """
    Evaluate content for safety violations using Llama Guard 4
    Requires JWT authentication and enforces customer isolation
    """
    start_time = time.time()
    
    try:
        # Enforce customer isolation
        await validate_customer_isolation(context, request.customer_id)
        
        # Override security tier from token (prevents privilege escalation)
        effective_security_tier = context.security_tier
        
        # Get policy configuration for customer tier
        policy_config = safety_policies.get(effective_security_tier, safety_policies.get("basic"))
        policy_type = policy_config.get("policy_type", "general")
        
        # BYPASS MODE: Return safe for all content when Llama Guard is disabled
        if not LLAMAGUARD_ENABLED:
            logger.info(f"BYPASS MODE: Content evaluation skipped for customer {request.customer_id}")
            is_safe = True
            violations = []
            confidence = 1.0
        else:
            # Evaluate content with Llama Guard 4
            is_safe, violations, confidence = await llamaguard_client.evaluate_content(
                request.content, 
                policy_type
            )
        
        processing_time = (time.time() - start_time) * 1000
        
        # Create response
        response = SecurityResponse(
            safe=is_safe,
            violations=violations,
            confidence=confidence,
            processing_time_ms=processing_time,
            metadata={
                "policy_type": policy_type,
                "security_tier": effective_security_tier,
                "request_type": request.request_type,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Log security event in background with customer isolation hash
        customer_hash = hashlib.sha256(context.customer_id.encode()).hexdigest()[:16]
        event_data = {
            "event_type": "content_evaluation",
            "user_id_hash": hashlib.sha256(context.user_id.encode()).hexdigest()[:16],
            "customer_id_hash": customer_hash,
            "safe": is_safe,
            "violations": len(violations),
            "processing_time_ms": processing_time,
            "timestamp": datetime.utcnow().isoformat()
        }
        background_tasks.add_task(log_security_event, event_data)
        
        return response
        
    except Exception as e:
        logger.error(f"Error evaluating content: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Security evaluation failed: {str(e)}")

@app.post("/batch-evaluate")
async def batch_evaluate_content(requests: List[SecurityRequest], background_tasks: BackgroundTasks):
    """
    Batch evaluate multiple content items for efficiency
    """
    start_time = time.time()
    
    try:
        tasks = []
        for req in requests:
            policy_config = safety_policies.get(req.security_tier, safety_policies.get("basic"))
            policy_type = policy_config.get("policy_type", "general")
            
            task = llamaguard_client.evaluate_content(req.content, policy_type)
            tasks.append((req, task))
        
        # Process all requests concurrently
        results = []
        for req, task in tasks:
            is_safe, violations, confidence = await task
            
            results.append(SecurityResponse(
                safe=is_safe,
                violations=violations,
                confidence=confidence,
                processing_time_ms=(time.time() - start_time) * 1000,
                metadata={
                    "user_id": req.user_id,
                    "customer_id": req.customer_id,
                    "request_type": req.request_type
                }
            ))
        
        return {"results": results, "total_processing_time_ms": (time.time() - start_time) * 1000}
        
    except Exception as e:
        logger.error(f"Error in batch evaluation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Batch evaluation failed: {str(e)}")

@app.get("/policies")
async def get_safety_policies():
    """Get current safety policies configuration"""
    return safety_policies

@app.get("/stats")
async def get_stats():
    """Get security service statistics"""
    try:
        redis_client = await get_redis_client()
        
        # Get recent security events
        keys = await redis_client.keys("security_event:*")
        event_count = len(keys)
        
        return {
            "total_events": event_count,
            "service_uptime": time.time(),
            "policies_loaded": len(safety_policies),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    uvicorn.run(
        "llamaguard-api:app",
        host="0.0.0.0",
        port=8080,
        log_level=LOG_LEVEL.lower(),
        reload=False
    )