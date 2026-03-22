"""Onboarding flow engine — pure functions, no I/O.

Each step takes the customer's message + personality + accumulated data
and returns a response, parsed data, and whether to advance.  The API
layer orchestrates Redis reads/writes around these calls.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Step indices
STEP_INTRODUCTION = 0
STEP_BUSINESS_CONTEXT = 1
STEP_PREFERENCES = 2
STEP_QUICK_WIN = 3
STEP_COMPLETION = 4
NUM_STEPS = 5

# ── Business-type classification ──────────────────────────────────────────

_BUSINESS_KEYWORDS: dict[str, list[str]] = {
    "restaurant": ["restaurant", "café", "cafe", "bistro", "diner", "food truck",
                    "catering", "bakery", "bar", "pub", "pizzeria"],
    "consulting": ["consulting", "consultancy", "advisory", "professional services",
                    "agency", "law firm", "accounting"],
    "retail": ["retail", "store", "shop", "e-commerce", "ecommerce", "boutique"],
    "healthcare": ["clinic", "healthcare", "medical", "dental", "therapy",
                    "veterinary", "vet", "pharmacy"],
    "fitness": ["gym", "fitness", "yoga", "personal training", "studio"],
    "real_estate": ["real estate", "property", "realty"],
    "construction": ["construction", "contractor", "builder", "plumbing",
                      "electrical", "hvac"],
}

# Quick-win mapping: business_type → (feature_key, suggestion_text)
_QUICK_WINS: dict[str, tuple[str, str]] = {
    "restaurant": (
        "reservation_summary",
        "I can send you a daily summary of your reservations each morning. Want me to set that up?",
    ),
    "consulting": (
        "morning_briefing",
        "I can send you a morning briefing with today's meetings and any pending follow-ups. Want me to turn that on?",
    ),
    "retail": (
        "morning_briefing",
        "I can send you a daily morning briefing with your schedule and any updates. Want me to enable that?",
    ),
    "healthcare": (
        "morning_briefing",
        "I can send you a morning briefing each day with your appointments and updates. Shall I set that up?",
    ),
}

_DEFAULT_QUICK_WIN = (
    "morning_briefing",
    "I can send you a morning briefing each day with your schedule and any updates. Want me to turn that on?",
)

# ── Real-request detection ────────────────────────────────────────────────

_REAL_REQUEST_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(schedule|book|cancel|reschedule)\b.*(meeting|appointment|call)", re.I),
    re.compile(r"\b(send|draft|write)\b.*(email|invoice|message|report)", re.I),
    re.compile(r"\b(check|track|show|review)\b.*(financ|expens|spend|budget|payment)", re.I),
    re.compile(r"\b(create|set up|build|deploy)\b.*(workflow|automation|integration)", re.I),
    re.compile(r"\b(remind|alert|notify)\b.*\b(me|us)\b", re.I),
    re.compile(r"\bneed to\b.*\b(send|pay|call|meet|finish|complete)\b", re.I),
    re.compile(r"\bcan you\b.*\b(schedule|book|send|check|find|help)\b", re.I),
]

# Answers that clearly belong to the onboarding flow, not real requests
_ONBOARDING_ANSWER_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(yes|yeah|yep|sure|ok|okay|no|nah|not now|maybe later|later)[\s.!?]*$", re.I),
    re.compile(r"^\d{1,2}(:\d{2})?\s*(am|pm)?\s*(to|-)\s*\d{1,2}(:\d{2})?\s*(am|pm)?", re.I),
    re.compile(r"\b(i run|we run|i own|we own|i have|we have|my business|our business|i'm in|we're in)\b", re.I),
    re.compile(r"\b(restaurant|consulting|retail|store|shop|clinic|gym|agency)\b", re.I),
]

# ── Working-hours parser ─────────────────────────────────────────────────

_TIMEZONE_MAP: dict[str, str] = {
    "eastern": "US/Eastern", "est": "US/Eastern", "et": "US/Eastern",
    "central": "US/Central", "cst": "US/Central", "ct": "US/Central",
    "mountain": "US/Mountain", "mst": "US/Mountain", "mt": "US/Mountain",
    "pacific": "US/Pacific", "pst": "US/Pacific", "pt": "US/Pacific",
    "utc": "UTC", "gmt": "GMT",
}

# Matches patterns like: "9 to 5", "9am to 5pm", "08:00 to 17:00", "8am-6pm"
_HOURS_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:to|-)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.I,
)


@dataclass
class StepResult:
    response: str
    collected: Optional[dict] = None
    advance: bool = True
    settings_update: Optional[dict] = None


# ── Public API ────────────────────────────────────────────────────────────


def generate_step_response(
    step: int,
    customer_message: Optional[str],
    personality: dict,
    collected_so_far: dict,
) -> StepResult:
    """Pure function.  Returns the EA's onboarding response for *step*."""
    handlers = {
        STEP_INTRODUCTION: _step_introduction,
        STEP_BUSINESS_CONTEXT: _step_business_context,
        STEP_PREFERENCES: _step_preferences,
        STEP_QUICK_WIN: _step_quick_win,
        STEP_COMPLETION: _step_completion,
    }
    handler = handlers.get(step, _step_completion)
    return handler(customer_message, personality, collected_so_far)


def detect_real_request(message: str) -> bool:
    """Heuristic: does *message* look like a real business request?"""
    if not message or not message.strip():
        return False

    # If it matches an onboarding answer pattern, it's not a real request
    for pat in _ONBOARDING_ANSWER_PATTERNS:
        if pat.search(message):
            return False

    # If it matches a real-request pattern, it is a real request
    for pat in _REAL_REQUEST_PATTERNS:
        if pat.search(message):
            return True

    return False


def parse_working_hours(text: str) -> Optional[dict]:
    """Parse natural language hours into ``{start, end, timezone?}``."""
    m = _HOURS_RE.search(text)
    if not m:
        return None

    start_h, start_m, start_ampm, end_h, end_m, end_ampm = m.groups()
    start_hour = _to_24h(int(start_h), start_m, start_ampm)
    end_hour = _to_24h(int(end_h), end_m, end_ampm)

    if start_hour is None or end_hour is None:
        return None

    result: dict = {
        "start": f"{start_hour:02d}:{int(start_m or 0):02d}",
        "end": f"{end_hour:02d}:{int(end_m or 0):02d}",
    }

    # Timezone extraction
    tz = _extract_timezone(text)
    if tz:
        result["timezone"] = tz

    return result


# ── Step handlers ─────────────────────────────────────────────────────────


def _step_introduction(
    _message: Optional[str], personality: dict, _collected: dict,
) -> StepResult:
    name = personality.get("name", "Assistant")
    return StepResult(
        response=(
            f"Hi! I'm {name}, your executive assistant. "
            f"I can help you manage scheduling, track finances, automate workflows, "
            f"and proactively keep you informed about what matters.\n\n"
            f"To get started, could you tell me a bit about your business?"
        ),
        advance=True,
    )


def _step_business_context(
    message: Optional[str], personality: dict, _collected: dict,
) -> StepResult:
    text = message or ""
    business_type = _classify_business(text)
    return StepResult(
        response=(
            f"Great, thanks for sharing! "
            f"Now, what are your typical working hours and timezone? "
            f"For example, \"9am to 5pm Eastern\" — or just tell me in your own words."
        ),
        collected={
            "business_type": business_type,
            "business_description": text.strip(),
        },
        advance=True,
    )


def _step_preferences(
    message: Optional[str], personality: dict, collected: dict,
) -> StepResult:
    text = message or ""
    parsed = parse_working_hours(text)

    if parsed:
        wh = {
            "start": parsed["start"],
            "end": parsed["end"],
            "timezone": parsed.get("timezone", "UTC"),
        }
    else:
        # Sensible defaults; tell the customer
        wh = {"start": "09:00", "end": "18:00", "timezone": "UTC"}

    business_type = collected.get("business_type", "other")
    _, suggestion = _QUICK_WINS.get(business_type, _DEFAULT_QUICK_WIN)

    if parsed:
        prefix = "Got it!"
    else:
        prefix = (
            "I wasn't sure about the exact hours, so I've set sensible defaults "
            "(9:00–18:00 UTC). You can always change them later from the dashboard."
        )

    return StepResult(
        response=f"{prefix} {suggestion}",
        collected={"working_hours": wh},
        advance=True,
        settings_update={"working_hours": wh},
    )


def _step_quick_win(
    message: Optional[str], personality: dict, collected: dict,
) -> StepResult:
    text = (message or "").strip().lower()
    accepted = _is_affirmative(text)
    business_type = collected.get("business_type", "other")
    feature_key, _ = _QUICK_WINS.get(business_type, _DEFAULT_QUICK_WIN)

    if accepted:
        if feature_key == "reservation_summary":
            resp = (
                "Done! I'll send you a daily reservation summary each morning. "
            )
            settings_update: Optional[dict] = {"briefing": {"enabled": True}}
        else:
            resp = "Done! I'll send you a morning briefing each day. "
            settings_update = {"briefing": {"enabled": True}}
    else:
        resp = (
            "No problem — you can enable that anytime from the dashboard or just ask me. "
        )
        settings_update = None

    return StepResult(
        response=resp + "You're all set! You can message me anytime for help, "
        "or head to the dashboard to customize your settings further.",
        collected={"quick_win_accepted": accepted, "quick_win_feature": feature_key},
        advance=True,
        settings_update=settings_update,
    )


def _step_completion(
    _message: Optional[str], _personality: dict, _collected: dict,
) -> StepResult:
    return StepResult(
        response=(
            f"You're all set! I'm here whenever you need me — just send a message. "
            f"You can also use the dashboard to adjust your settings anytime."
        ),
        advance=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────

_AFFIRMATIVE = frozenset({
    "yes", "yep", "yeah", "sure", "ok", "okay",
    "go ahead", "do it", "proceed", "yes please",
    "confirmed", "confirm", "absolutely", "definitely",
    "sounds good", "let's do it",
})


def _is_affirmative(text: str) -> bool:
    normalized = text.strip().strip(".!?,").lower()
    return normalized in _AFFIRMATIVE


def _classify_business(text: str) -> str:
    text_lower = text.lower()
    for btype, keywords in _BUSINESS_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return btype
    return "other"


def _to_24h(hour: int, minutes: Optional[str], ampm: Optional[str]) -> Optional[int]:
    """Convert hour + am/pm to 24-hour. Infers am/pm when omitted."""
    if ampm:
        ampm = ampm.lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
    else:
        # Heuristic: numbers 1-7 without am/pm are likely pm (end of day)
        # numbers 8-12 without am/pm are likely am (start of day)
        # But context matters — this is for the common "9 to 5" pattern
        if hour <= 7:
            hour += 12  # 5 → 17:00
    if hour < 0 or hour > 23:
        return None
    return hour


def _extract_timezone(text: str) -> Optional[str]:
    text_lower = text.lower()
    for keyword, tz in _TIMEZONE_MAP.items():
        if keyword in text_lower:
            return tz
    return None
