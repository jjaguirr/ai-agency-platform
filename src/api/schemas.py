"""
Pydantic request/response models for the REST API.

Channel values mirror ConversationChannel enum in executive_assistant.py.
We declare them as a Literal here rather than importing the enum to keep
the schema layer independent of agent internals.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ConversationChannel: PHONE | WHATSAPP | EMAIL | CHAT → lowercase wire format
Channel = Literal["phone", "whatsapp", "email", "chat"]
Tier = Literal["basic", "professional", "enterprise"]


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    channel: Channel
    conversation_id: Optional[str] = None


class MessageResponse(BaseModel):
    response: str
    conversation_id: str


class ProvisionRequest(BaseModel):
    customer_id: Optional[str] = None
    tier: Tier = "professional"


class ProvisionResponse(BaseModel):
    customer_id: str
    token: str
    tier: Tier


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]
