"""
Conversational onboarding wizard.

A 4-step guided exchange the EA runs for new customers before normal
routing kicks in. State persists in Redis at ``onboarding:{customer_id}``
so dropped-off customers resume where they left off.

Not to be confused with infrastructure provisioning (LAUNCH-Bot) — that
creates the customer's MCP server and EA instance; this teaches the
already-running EA who the customer is.

Public API:
    OnboardingFlow        — drives the conversation, one turn per handle()
    OnboardingStateStore  — Redis-backed step/status tracking
    OnboardingStep        — step enum (INTRO … DONE)
    seed_demo_account     — populate a fresh account with sample data
"""
from .demo_seed import seed_demo_account
from .flow import OnboardingFlow
from .state import OnboardingState, OnboardingStateStore, OnboardingStep

__all__ = [
    "OnboardingFlow",
    "OnboardingState",
    "OnboardingStateStore",
    "OnboardingStep",
    "seed_demo_account",
]
