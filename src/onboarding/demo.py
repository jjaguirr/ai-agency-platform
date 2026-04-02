"""Demo data seeder — populates a customer account with sample data.

Called by provisioning when ``demo=True``.  Seeds settings, onboarding
state, notifications, and activity counters so the dashboard has
something to display in every section.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from ..api.schemas import (
    BriefingSettings,
    ConnectedServices,
    PersonalitySettings,
    ProactiveSettings,
    Settings,
    WorkingHours,
)

logger = logging.getLogger(__name__)

DEMO_SETTINGS = Settings(
    working_hours=WorkingHours(start="08:00", end="18:00", timezone="America/New_York"),
    briefing=BriefingSettings(enabled=True, time="07:30"),
    proactive=ProactiveSettings(priority_threshold="MEDIUM", daily_cap=10, idle_nudge_minutes=90),
    personality=PersonalitySettings(tone="friendly", language="en", name="Aria"),
    connected_services=ConnectedServices(calendar=False, n8n=False),
)

def _demo_notifications() -> list[dict]:
    """Build notifications with fresh timestamps (not module-load time)."""
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "domain": "finance",
            "trigger_type": "anomaly",
            "priority": "HIGH",
            "title": "Unusual transaction detected",
            "message": "A charge of $2,450 from 'AcmeParts Ltd' is 3x your typical spend with this vendor.",
            "created_at": now,
        },
        {
            "domain": "scheduling",
            "trigger_type": "conflict",
            "priority": "MEDIUM",
            "title": "Calendar conflict tomorrow",
            "message": "You have overlapping meetings at 2:00 PM: 'Design Review' and 'Client Check-in'.",
            "created_at": now,
        },
        {
            "domain": "ea",
            "trigger_type": "morning_briefing",
            "priority": "LOW",
            "title": "Morning briefing",
            "message": "Good morning! You have 3 meetings today, 2 pending follow-ups, and 1 invoice due.",
            "created_at": now,
        },
    ]


async def seed_demo_data(
    redis_client: Any,
    customer_id: str,
    onboarding_store: Optional[Any] = None,
    proactive_store: Optional[Any] = None,
) -> None:
    """Populate a customer with sample data for every dashboard section."""

    # 1. Non-default settings
    await redis_client.set(
        f"settings:{customer_id}",
        DEMO_SETTINGS.model_dump_json(),
    )

    # 2. Mark onboarding completed
    if onboarding_store is not None:
        await onboarding_store.mark_completed(customer_id)

    # 3. Sample notifications
    if proactive_store is not None:
        for notif in _demo_notifications():
            await proactive_store.add_pending_notification(customer_id, notif)

    # 4. Activity counters
    today = date.today().isoformat()
    counter_key = f"activity:{customer_id}:messages:{today}"
    await redis_client.set(counter_key, "47")

    delegation_key = f"activity:{customer_id}:delegations:{today}"
    await redis_client.set(
        delegation_key,
        json.dumps({"finance": 5, "scheduling": 8, "social_media": 3}),
    )
