"""
Pydantic request/response models for the REST API.

Channel values mirror ConversationChannel enum in executive_assistant.py.
We declare them as a Literal here rather than importing the enum to keep
the schema layer independent of agent internals.
"""
from typing import Any, Literal, Optional

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


class ConversationSummary(BaseModel):
    id: str
    channel: str
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


class NotificationResponse(BaseModel):
    """A proactive notification returned by GET /v1/notifications."""
    id: str = Field(description="Unique notification identifier (notif_…)")
    domain: str = Field(description="Source domain: ea, finance, scheduling, workflows")
    trigger_type: str = Field(description="Trigger kind, e.g. morning_briefing, finance_anomaly, scheduling_conflict, workflow_failure, follow_up_reminder, idle_nudge")
    priority: str = Field(description="LOW, MEDIUM, HIGH, or URGENT")
    title: str = Field(description="Short human-readable headline")
    message: str = Field(description="Suggested message body for the customer")
    created_at: str = Field(description="ISO-8601 creation timestamp")
    status: str = Field(default="pending", description="Lifecycle state: pending, read, snoozed, or dismissed")


class SnoozeRequest(BaseModel):
    """Body for POST /v1/notifications/{id}/snooze. The notification is hidden
    from GET listings until ``duration_seconds`` have elapsed, then reappears."""
    duration_seconds: int = Field(default=3600, ge=60, le=86400, description="Seconds before the notification reappears (1 min – 24 h, default 1 h)")


# --- Dashboard auth -------------------------------------------------------

class LoginRequest(BaseModel):
    # MVP: pre-shared key per customer. NOT a password — no hashing, no
    # rotation, no lockout. Replace with OAuth before any customer other
    # than us logs in. The customer_id format must match what the rest of
    # the API expects so the minted token is usable.
    customer_id: str = Field(pattern=_CUSTOMER_ID_PATTERN)
    secret: str = Field(min_length=1)


class LoginResponse(BaseModel):
    token: str
    customer_id: str


# --- Dashboard settings ---------------------------------------------------

Priority = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
Tone = Literal["professional", "friendly", "concise", "detailed"]


class WorkingHours(BaseModel):
    start: str = "09:00"        # HH:MM, local to timezone
    end: str = "18:00"
    timezone: str = "UTC"


class BriefingSettings(BaseModel):
    enabled: bool = True
    time: str = "08:00"         # HH:MM, local to working-hours timezone


class ProactiveSettings(BaseModel):
    """Knobs that control the noise gate and proactive behaviors."""
    priority_threshold: Priority = Field(default="MEDIUM", description="Minimum trigger priority to deliver (LOW, MEDIUM, HIGH, URGENT)")
    daily_cap: int = Field(default=5, ge=0, le=50, description="Max proactive messages per day (0 disables proactive)")
    idle_nudge_minutes: int = Field(default=120, ge=0, description="Minutes of inactivity before an idle nudge (floored to 1 day internally)")
    anomaly_threshold: float = Field(default=2.0, ge=1.0, le=10.0, description="Spending-to-average ratio that triggers a finance anomaly alert")
    monthly_budget: Optional[float] = Field(default=None, ge=0, description="Optional monthly spending cap; exceeding it generates a budget alert")


class PersonalitySettings(BaseModel):
    tone: Tone = "professional"
    language: str = "en"
    name: str = "Assistant"


class ConnectedServices(BaseModel):
    # Display-only; actual OAuth/connection flows are out of scope.
    calendar: bool = False
    n8n: bool = False


class Settings(BaseModel):
    working_hours: WorkingHours = Field(default_factory=WorkingHours)
    briefing: BriefingSettings = Field(default_factory=BriefingSettings)
    proactive: ProactiveSettings = Field(default_factory=ProactiveSettings)
    personality: PersonalitySettings = Field(default_factory=PersonalitySettings)
    connected_services: ConnectedServices = Field(default_factory=ConnectedServices)


class WorkflowResponse(BaseModel):
    workflow_id: str
    name: str
    status: str
    created_at: str


# --- Audit -------------------------------------------------------------------
# Wire shape mirrors AuditEvent.to_dict() exactly: event_type is the enum
# .value string, details is an opaque dict. The route hands the dict
# straight through rather than reconstructing an AuditEvent just to
# re-serialize it — one fewer place for field drift.

class AuditEventResponse(BaseModel):
    timestamp: str
    event_type: str
    correlation_id: str
    details: dict[str, Any]


class AuditListResponse(BaseModel):
    events: list[AuditEventResponse]
