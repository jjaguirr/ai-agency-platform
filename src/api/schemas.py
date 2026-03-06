"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --- Conversations ---------------------------------------------------------

# Mirrors ConversationChannel enum values from src/agents/executive_assistant.py.
# Literal instead of importing the enum here so schema validation doesn't
# pull the full EA import chain at module load.
ChannelName = Literal["phone", "whatsapp", "email", "chat"]


class MessageRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Customer's message text")
    channel: ChannelName
    conversation_id: str | None = Field(
        default=None,
        description="Continue an existing conversation. Auto-generated if omitted.",
    )


class MessageResponse(BaseModel):
    response: str
    customer_id: str
    conversation_id: str | None


# --- Provisioning ----------------------------------------------------------

class ProvisionRequest(BaseModel):
    customer_id: str = Field(..., min_length=1)
    tier: Literal["basic", "professional", "enterprise"] = "professional"


class ProvisionResponse(BaseModel):
    customer_id: str
    tier: str
    status: str
    token: str = Field(description="Bearer token for subsequent API calls")
    created_at: str


# --- Errors ----------------------------------------------------------------

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
