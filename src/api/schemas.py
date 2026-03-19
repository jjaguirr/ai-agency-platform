"""
Pydantic request/response models for the REST API.

Channel values mirror ConversationChannel enum in executive_assistant.py.
We declare them as a Literal here rather than importing the enum to keep
the schema layer independent of agent internals.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ConversationChannel: PHONE | WHATSAPP | EMAIL | CHAT → lowercase wire format
Channel = Literal["phone", "whatsapp", "email", "chat"]
Tier = Literal["basic", "professional", "enterprise"]

# Customer ID flows into Docker network/container names, volume paths, and
# Redis keys via InfrastructureOrchestrator. Shell metacharacters, path
# separators, or unbounded length are injection vectors. Docker object
# names are typically [a-zA-Z0-9_.-], max ~63 chars. We're stricter:
# lowercase alnum + underscore + hyphen, 3-48 chars.
_CUSTOMER_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{2,47}$"


class MessageRequest(BaseModel):
    message: str = Field(min_length=1)
    channel: Channel
    conversation_id: Optional[str] = None

    @field_validator("conversation_id")
    @classmethod
    def _strip_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        # "   " should not become a Redis key. Normalize whitespace-only
        # to None so the route generates a fresh UUID.
        if v is None:
            return None
        v = v.strip()
        return v or None


class MessageResponse(BaseModel):
    response: str
    conversation_id: str


class ProvisionRequest(BaseModel):
    customer_id: Optional[str] = Field(
        default=None,
        pattern=_CUSTOMER_ID_PATTERN,
        description="Lowercase alphanumeric, underscore, hyphen; 3-48 chars. "
                    "Omit to auto-generate.",
    )
    tier: Tier = "professional"


class ProvisionResponse(BaseModel):
    customer_id: str
    token: str
    tier: Tier


class HistoryMessage(BaseModel):
    role: str
    content: str
    timestamp: str


class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    customer_id: str
    messages: list[HistoryMessage]
    channel: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class NotificationResponse(BaseModel):
    id: str
    domain: str
    trigger_type: str
    priority: str
    title: str
    message: str
    created_at: str
