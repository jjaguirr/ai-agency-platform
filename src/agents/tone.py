"""
Tone rendering for specialist results.

The specialist does the same work regardless of tone — the EA applies
phrasing. This module owns the LLM-free path: deterministic rewrites
of ``summary_for_ea`` that differ meaningfully across the four tones.

The LLM path uses ``guidance(tone)`` to inject instructions into the
synthesis prompt; output there is non-deterministic so the renderer
below is the fallback AND the baseline tests assert against.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.agents.base.specialist import SpecialistResult

# Must cover every value of schemas.Tone.
_GUIDANCE = {
    "professional": (
        "Keep a composed, professional tone. Full sentences, no "
        "exclamation marks, no slang."
    ),
    "friendly": (
        "Warm and casual — like a helpful colleague. Brief exclamation "
        "or an upbeat opener is fine."
    ),
    "concise": (
        "Be brief. Just the facts, minimal words, no filler."
    ),
    "detailed": (
        "Be thorough. Surface the supporting context — times, titles, "
        "amounts — so the customer doesn't have to ask follow-ups."
    ),
}


def guidance(tone: str) -> str:
    return _GUIDANCE.get(tone, _GUIDANCE["professional"])


def render(result: SpecialistResult, tone: str) -> str:
    """Deterministic tone rewrite for the LLM-free path."""
    base = result.summary_for_ea or _summarise_payload(result.payload)
    fn = _RENDERERS.get(tone, _professional)
    return fn(base, result.payload)


def _summarise_payload(payload: Dict[str, Any]) -> str:
    # Keep it human: pick out recognisable keys before falling back to
    # a raw dump. "amount" + "vendor" covers finance; "title" + "start"
    # covers scheduling.
    if "amount" in payload and "vendor" in payload:
        return f"${payload['amount']:g} → {payload['vendor']}"
    if "title" in payload and "start" in payload:
        return f"{payload['title']} at {payload['start']}"
    return json.dumps(payload)


# --- Per-tone renderers -----------------------------------------------------

def _professional(base: str, payload: Dict[str, Any]) -> str:
    # Normalise any exclamation the specialist slipped in.
    text = base.replace("!", ".")
    return text if text.endswith(".") else text + "."


def _friendly(base: str, payload: Dict[str, Any]) -> str:
    text = base.rstrip(".")
    return f"All set! {text}."


def _concise(base: str, payload: Dict[str, Any]) -> str:
    # Drop filler words the specialists tend to include.
    text = base
    for noise in ("Booked: ", "Tracked ", "Done. ", "I've ", "You have "):
        text = text.replace(noise, "")
    return text.rstrip(".")


def _detailed(base: str, payload: Dict[str, Any]) -> str:
    extras = []
    # Scheduling: end time / title if not already in the base.
    if "end" in payload and str(payload["end"])[-8:-3] not in base:
        extras.append(f"ends {str(payload['end'])[-8:-3]}")
    if "title" in payload and str(payload["title"]) not in base:
        extras.append(f"titled '{payload['title']}'")
    # Finance: category / vendor.
    if "category" in payload and str(payload["category"]) not in base.lower():
        extras.append(f"filed under {payload['category']}")
    if not extras:
        # Generic fallback: surface any payload keys not already
        # mentioned so 'detailed' is always the longest output.
        for k, v in payload.items():
            if k in ("event_id", "memories_consulted"):
                continue
            if str(v) not in base:
                extras.append(f"{k}: {v}")
                break
    suffix = f" ({', '.join(extras)})" if extras else ""
    return f"{base.rstrip('.')}{suffix}."


_RENDERERS = {
    "professional": _professional,
    "friendly": _friendly,
    "concise": _concise,
    "detailed": _detailed,
}
