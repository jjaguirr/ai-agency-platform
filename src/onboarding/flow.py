"""
Onboarding flow — 4-step guided conversation (intro → business context
→ preferences → quick win).

Each ``handle()`` call consumes one customer message and returns one EA
reply (or None once onboarding is complete — signals the caller to route
normally). State lives in OnboardingStateStore so the flow survives
process restarts and dropped conversations.

The flow writes directly to ``settings:{customer_id}`` — the same key
the dashboard PUT /v1/settings endpoint owns. That's deliberate: there's
one source of truth for settings, and onboarding is just another writer.
"""
from __future__ import annotations

import json
import re
from typing import Dict, Optional

from src.api.schemas import Settings

from .state import OnboardingStateStore, OnboardingStep

# Timezone abbreviations → IANA names. Not exhaustive — covers the
# common US zones customers actually say out loud. Anything else
# passes through as-is (UTC, Europe/London) or falls back to default.
_TZ_ALIASES = {
    "eastern": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "central": "America/Chicago",
    "cst": "America/Chicago",
    "mountain": "America/Denver",
    "mst": "America/Denver",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
}

# Business-type → quick-win suggestion. Keyword match on the free-text
# business context. Order matters — first match wins.
_QUICK_WINS = [
    (("restaurant", "cafe", "bar", "diner", "bistro"),
     "Want me to set up a daily reservation summary each morning?"),
    (("consult", "agency", "law", "firm", "advisor"),
     "I can send you a morning briefing with today's meetings and any "
     "follow-ups due. Want me to turn that on?"),
    (("retail", "shop", "store", "ecommerce", "jewelry"),
     "Want me to send a daily sales and inventory check-in?"),
]
_GENERIC_QUICK_WIN = (
    "Want me to send you a morning briefing each day with your schedule "
    "and any updates?"
)

# Interrupt detection — imperative verbs that signal "actually do
# something" rather than answering an onboarding question. Deliberately
# conservative: false negatives (missing an interrupt) are fine because
# the customer can just repeat themselves after onboarding; false
# positives (treating "I run a scheduling business" as a scheduling
# request) break the flow.
_INTERRUPT_PATTERNS = [
    r"\b(schedule|book|set up|create|cancel|reschedule)\b.*\b(meeting|call|appointment|event)\b",
    r"\b(send|draft|write)\b.*\b(email|message|invoice)\b",
    r"\b(add|log|record|track)\b.*\b(expense|transaction|payment)\b",
    r"\bremind me\b",
    r"^actually\b",
]


class OnboardingFlow:
    def __init__(
        self,
        *,
        state_store: OnboardingStateStore,
        settings_redis,
        personality: Dict[str, str],
    ) -> None:
        self._store = state_store
        self._settings_redis = settings_redis
        self._personality = personality

    async def handle(self, customer_id: str, message: str) -> Optional[str]:
        """Process one turn. Returns the EA's reply, or None if
        onboarding is already complete (caller should route normally)."""
        state = await self._store.get(customer_id)

        if state.status == "completed":
            return None

        if state.step == OnboardingStep.INTRO:
            return await self._intro(customer_id)

        if state.step == OnboardingStep.BUSINESS_CONTEXT:
            return await self._business_context(customer_id, message)

        if state.step == OnboardingStep.PREFERENCES:
            return await self._preferences(customer_id, message)

        if state.step == OnboardingStep.QUICK_WIN:
            return await self._quick_win(customer_id, message)

        # Shouldn't reach — DONE implies status==completed
        return None

    def looks_like_real_request(self, message: str) -> bool:
        """Heuristic: does this look like a task request rather than an
        onboarding answer? Caller decides whether to interrupt the flow."""
        lowered = message.lower()
        return any(re.search(p, lowered) for p in _INTERRUPT_PATTERNS)

    # ─── steps ───────────────────────────────────────────────────────────

    async def _intro(self, customer_id: str) -> str:
        name = self._personality.get("name", "Assistant")
        await self._store.advance(customer_id, OnboardingStep.BUSINESS_CONTEXT)
        return (
            f"Hi! I'm {name}, your executive assistant. I can manage your "
            f"scheduling, track finances, automate workflows, and "
            f"proactively keep you informed. "
            f"To get started — what kind of business do you run?"
        )

    async def _business_context(self, customer_id: str, message: str) -> str:
        await self._store.advance(
            customer_id,
            OnboardingStep.PREFERENCES,
            collected={"business_context": message.strip()},
        )
        return (
            "Got it. What are your working hours and timezone? "
            "(e.g. '9 to 5 Eastern' — or just say 'skip' and I'll use "
            "sensible defaults.)"
        )

    async def _preferences(self, customer_id: str, message: str) -> str:
        hours = _parse_working_hours(message)
        used_defaults = hours is None
        settings = await self._load_settings(customer_id)
        if hours:
            settings.working_hours.start = hours["start"]
            settings.working_hours.end = hours["end"]
            if hours.get("timezone"):
                settings.working_hours.timezone = hours["timezone"]
        await self._save_settings(customer_id, settings)

        state = await self._store.get(customer_id)
        suggestion = _pick_quick_win(state.collected.get("business_context", ""))
        await self._store.advance(
            customer_id, OnboardingStep.QUICK_WIN,
            collected={"quick_win_offered": suggestion},
        )

        prefix = ""
        if used_defaults:
            prefix = ("No problem — I'll use 9-to-6 for now. You can change "
                      "it anytime from the dashboard. ")
        return f"{prefix}One more thing: {suggestion}"

    async def _quick_win(self, customer_id: str, message: str) -> str:
        accepted = _is_affirmative(message)
        if accepted:
            settings = await self._load_settings(customer_id)
            settings.briefing.enabled = True
            await self._save_settings(customer_id, settings)
            confirm = "Done — you'll get your first briefing tomorrow morning. "
        else:
            confirm = "No problem, you can turn it on later. "

        await self._store.complete(customer_id)
        return (
            f"{confirm}You're all set — message me anytime. "
            f"The dashboard has more configuration if you want to tweak "
            f"anything."
        )

    # ─── settings I/O ────────────────────────────────────────────────────

    async def _load_settings(self, customer_id: str) -> Settings:
        raw = await self._settings_redis.get(f"settings:{customer_id}")
        if raw is None:
            return Settings()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return Settings.model_validate(json.loads(raw))

    async def _save_settings(self, customer_id: str, settings: Settings) -> None:
        await self._settings_redis.set(
            f"settings:{customer_id}", settings.model_dump_json()
        )


# ─── parsing helpers ─────────────────────────────────────────────────────

_HOUR_PATTERNS = [
    # "9 to 5", "9am to 5pm", "9:30 to 17:00"
    re.compile(
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-|–|until)\s*"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
        re.IGNORECASE,
    ),
]


def _parse_working_hours(text: str) -> Optional[Dict[str, str]]:
    for pat in _HOUR_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        sh, sm, sap, eh, em, eap = m.groups()
        start = _to_24h(int(sh), int(sm or 0), sap)
        end = _to_24h(int(eh), int(em or 0), eap)
        if start is None or end is None:
            continue
        result = {"start": start, "end": end}
        tz = _extract_tz(text)
        if tz:
            result["timezone"] = tz
        return result
    return None


def _to_24h(hour: int, minute: int, ampm: Optional[str]) -> Optional[str]:
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    # Heuristic: bare hours ≤ 7 without am/pm are probably pm in a
    # work-hours context ("9 to 5" → 09:00–17:00, not 05:00).
    elif hour <= 7:
        hour += 12
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    return f"{hour:02d}:{minute:02d}"


def _extract_tz(text: str) -> Optional[str]:
    lowered = text.lower()
    for alias, iana in _TZ_ALIASES.items():
        if alias in lowered:
            return iana
    # Pass through explicit IANA-ish tokens or UTC
    m = re.search(r"\b(UTC|[A-Z][a-z]+/[A-Z][a-z_]+)\b", text)
    if m:
        return m.group(1)
    return None


def _pick_quick_win(business_context: str) -> str:
    lowered = business_context.lower()
    for keywords, suggestion in _QUICK_WINS:
        if any(k in lowered for k in keywords):
            return suggestion
    return _GENERIC_QUICK_WIN


def _is_affirmative(text: str) -> bool:
    lowered = text.lower().strip()
    return any(
        w in lowered
        for w in ("yes", "yeah", "sure", "ok", "okay", "please", "sounds good",
                  "do it", "go ahead", "yep")
    ) and not any(w in lowered for w in ("no", "not", "later", "skip"))
