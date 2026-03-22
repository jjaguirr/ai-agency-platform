"""
Demo account seeding — realistic sample data for prospect evaluation.

Populates everything the dashboard reads so every card has content:
  - settings (configured hours, briefing on, friendly tone)
  - onboarding state (completed — demo users skip the wizard)
  - notifications (morning briefing, finance alert, workflow status)
  - activity counters (messages + delegations for today's card)
  - conversations (3-5 exchanges across specialist domains, if a
    Postgres repo is provided)

All keys are customer-scoped. Called by the provisioning endpoint when
``demo=true``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from src.api.schemas import Settings, WorkingHours, BriefingSettings, PersonalitySettings
from src.proactive.state import ProactiveStateStore

from .state import OnboardingStateStore


async def seed_demo_account(
    redis_client,
    customer_id: str,
    *,
    conversation_repo=None,
) -> None:
    await _seed_settings(redis_client, customer_id)
    await _mark_onboarded(redis_client, customer_id)
    await _seed_notifications(redis_client, customer_id)
    await _seed_activity(redis_client, customer_id)
    if conversation_repo is not None:
        await _seed_conversations(conversation_repo, customer_id)


async def _seed_settings(redis, customer_id: str) -> None:
    settings = Settings(
        working_hours=WorkingHours(
            start="08:30", end="17:30", timezone="America/New_York",
        ),
        briefing=BriefingSettings(enabled=True, time="08:00"),
        personality=PersonalitySettings(
            tone="friendly", language="en", name="Sarah",
        ),
    )
    await redis.set(f"settings:{customer_id}", settings.model_dump_json())


async def _mark_onboarded(redis, customer_id: str) -> None:
    store = OnboardingStateStore(redis)
    await store.complete(customer_id)


async def _seed_notifications(redis, customer_id: str) -> None:
    store = ProactiveStateStore(redis)
    now = datetime.now(timezone.utc)
    samples = [
        {
            "domain": "scheduling",
            "trigger_type": "briefing",
            "priority": "MEDIUM",
            "title": "Morning briefing",
            "message": "3 meetings today. First at 10:00 with Acme Corp.",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        },
        {
            "domain": "finance",
            "trigger_type": "anomaly",
            "priority": "HIGH",
            "title": "Unusual expense detected",
            "message": "$2,400 software charge — 3× your monthly average.",
            "created_at": (now - timedelta(hours=1)).isoformat(),
        },
        {
            "domain": "workflows",
            "trigger_type": "status",
            "priority": "LOW",
            "title": "Weekly report generated",
            "message": "Your weekly summary automation ran successfully.",
            "created_at": (now - timedelta(minutes=30)).isoformat(),
        },
    ]
    for n in samples:
        await store.add_pending_notification(customer_id, n)


async def _seed_activity(redis, customer_id: str) -> None:
    today = date.today().isoformat()
    ttl = 48 * 3600
    # Message count
    await redis.set(f"activity:{customer_id}:messages:{today}", 12, ex=ttl)
    # Delegations across domains — enough variety to show the chart
    for domain, count in (("scheduling", 4), ("finance", 3), ("workflows", 2)):
        await redis.set(
            f"activity:{customer_id}:delegation:{domain}:{today}", count, ex=ttl,
        )


# Sample exchanges. Each tuple: (channel, [(role, content, domain?), ...]).
# Domains tag assistant messages so the dashboard's specialist-activity
# view has data. User messages have no domain.
_SAMPLE_CONVERSATIONS = [
    ("whatsapp", [
        ("user", "Can you move my 3pm with Jordan to Thursday?", None),
        ("assistant", "Done — moved to Thursday 3:00 PM. Jordan's been notified.",
         "scheduling"),
    ]),
    ("whatsapp", [
        ("user", "What did we spend on software last month?", None),
        ("assistant", "$1,840 across 6 vendors. Biggest: AWS at $620. "
         "Want the full breakdown?", "finance"),
    ]),
    ("chat", [
        ("user", "Set up a weekly summary of new leads", None),
        ("assistant", "Created a workflow that pulls new leads every Friday "
         "at 5pm and emails you the summary. It's live now.", "workflows"),
    ]),
    ("whatsapp", [
        ("user", "How's engagement on the product launch post?", None),
        ("assistant", "Up 34% vs. your average — 2.1k impressions, 180 likes, "
         "42 shares. Best-performing post this quarter.", "social_media"),
    ]),
]


async def _seed_conversations(repo, customer_id: str) -> None:
    for channel, messages in _SAMPLE_CONVERSATIONS:
        conv_id = f"demo_{uuid.uuid4().hex[:12]}"
        await repo.create_conversation(
            customer_id=customer_id,
            conversation_id=conv_id,
            channel=channel,
        )
        for role, content, domain in messages:
            await repo.append_message(
                customer_id=customer_id,
                conversation_id=conv_id,
                role=role,
                content=content,
                specialist_domain=domain,
            )
