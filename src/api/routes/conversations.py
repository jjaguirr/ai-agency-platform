"""
Conversation endpoint — the primary API surface.

POST /v1/conversations/message
  body: {message, channel, conversation_id?}
  auth: Bearer token (customer_id claim)
  → {response, conversation_id}

Request lifecycle:
  1. Input safety gate — reject/sanitize risky input
  2. Onboarding intercept — if onboarding is incomplete, route to the
     guided flow instead of the EA (unless the message is a real business
     request, which falls through to the EA)
  3. EA call — delegate to the executive assistant
  4. Output safety gate — redact leaked internals
  5. Persistence — write exchange to ConversationRepository
  6. Side effects — activity counters, proactive inbound hook

The EA handles its own partial failures (specialist timeout, LLM degraded)
and returns a fallback string — those are 200s. We only map to 503 when
the EA's handle_customer_interaction *raises*, which means an infrastructure
dependency is hard-down.

Persistence is a side effect: after a successful EA call, the user
message and assistant reply are written to ConversationRepository. The
EA stays unaware — it still keeps its in-memory history for LLM context;
we just also durably store the exchange. If Postgres is briefly
unavailable the user still gets their reply (storage is not on the
critical path for a live conversation).
"""
import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Request

from ..auth import get_current_customer
from ..errors import ServiceUnavailableError
from ..schemas import MessageRequest, MessageResponse

# Import at module level so import failures surface at startup, not per-request.
from src.agents.executive_assistant import ConversationChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/conversations", tags=["conversations"])

# Wire-format string → enum. Mirrors the Channel Literal in schemas.py.
_CHANNEL_MAP = {
    "phone": ConversationChannel.PHONE,
    "whatsapp": ConversationChannel.WHATSAPP,
    "email": ConversationChannel.EMAIL,
    "chat": ConversationChannel.CHAT,
}

from ..constants import EA_CALL_TIMEOUT


@router.post("/message", response_model=MessageResponse)
async def post_message(
    req: MessageRequest,
    request: Request,
    customer_id: str = Depends(get_current_customer),
):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    ea_registry = request.app.state.ea_registry

    # --- Input safety gate -------------------------------------------
    # Runs before the try block so MessageTooLongError (APIError, 422)
    # propagates to the APIError handler rather than being swallowed
    # by the broad except-Exception below. HIGH-risk injection returns
    # a canned fallback without ever touching the EA.
    pipeline = getattr(request.app.state, "safety_pipeline", None)
    if pipeline is not None:
        decision = await pipeline.scan_input(req.message, customer_id)
        if not decision.proceed:
            return MessageResponse(
                response=decision.safe_response,
                conversation_id=conversation_id,
            )
        message_to_ea = decision.sanitized_message
    else:
        message_to_ea = req.message

    # --- Onboarding intercept -----------------------------------------
    # If the customer hasn't completed onboarding, route to the guided
    # flow instead of the EA. Real requests during onboarding fall
    # through to the EA (detect_real_request heuristic).
    onboarding_store = getattr(request.app.state, "onboarding_state_store", None)
    if onboarding_store is not None:
        onboarding_status = await onboarding_store.get_status(customer_id)
        if onboarding_status in ("not_started", "in_progress"):
            from src.onboarding.flow import generate_step_response, detect_real_request

            if not detect_real_request(message_to_ea):
                onb_state = await onboarding_store.get(customer_id)
                personality = await _load_personality_from_redis(
                    request.app.state.redis_client, customer_id,
                )
                result = generate_step_response(
                    step=onb_state.current_step,
                    customer_message=message_to_ea,
                    personality=personality,
                    collected_so_far=onb_state.collected,
                )
                if result.settings_update:
                    await _merge_settings(
                        request.app.state.redis_client, customer_id,
                        result.settings_update,
                    )
                if result.advance:
                    new_state = await onboarding_store.advance(
                        customer_id, result.collected,
                    )
                    # The completion step needs no customer input — if we
                    # just advanced into it, auto-fire it so onboarding
                    # finishes in the same turn as the quick win.
                    from src.onboarding.flow import STEP_COMPLETION
                    if (new_state.status != "completed"
                            and new_state.current_step == STEP_COMPLETION):
                        await onboarding_store.advance(customer_id)

                response_text = result.response
                if pipeline is not None:
                    response_text = await pipeline.scan_output(
                        response_text, customer_id,
                    )
                return MessageResponse(
                    response=response_text,
                    conversation_id=conversation_id,
                )
            else:
                # Real request — let EA handle it, mark interrupted
                await onboarding_store.mark_interrupted(customer_id)

    try:
        ea = await ea_registry.get(customer_id)
        response_text = await asyncio.wait_for(
            ea.handle_customer_interaction(
                message=message_to_ea,
                channel=_CHANNEL_MAP[req.channel],
                conversation_id=conversation_id,
            ),
            timeout=EA_CALL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "EA timed out for customer=%s conv=%s after %.0fs",
            customer_id, conversation_id, EA_CALL_TIMEOUT,
        )
        raise ServiceUnavailableError(
            detail="Assistant temporarily unavailable.",
        )
    except Exception:
        # EA blew up entirely — not a degraded specialist, an actual
        # infra failure. Log the full exception; tell the client nothing.
        logger.exception(
            "EA interaction failed for customer=%s conv=%s",
            customer_id, conversation_id,
        )
        raise ServiceUnavailableError(
            detail="Assistant temporarily unavailable.",
        )

    # --- Output safety gate ------------------------------------------
    # Redact leaked internal keys, cross-tenant IDs, stack traces —
    # anything the OutputScanner patterns catch — before the response
    # leaves the process. response_text is guaranteed-set here; the
    # except clauses above all raise.
    if pipeline is not None:
        response_text = await pipeline.scan_output(response_text, customer_id)

    # --- Persistence side effect -------------------------------------
    # Write-after: only persist once we have a reply to persist. A
    # failed EA call doesn't leave a half-recorded exchange in the DB.
    # A failed Postgres write doesn't hide the reply from the user —
    # they already have it; history just won't show this turn. Logged
    # at WARNING because the API is still serving traffic.
    repo = request.app.state.conversation_repo
    if repo is not None:
        try:
            await repo.create_conversation(
                customer_id=customer_id,
                conversation_id=conversation_id,
                channel=req.channel,
            )
            await repo.append_message(
                customer_id=customer_id,
                conversation_id=conversation_id,
                role="user",
                content=req.message,
            )
            await repo.append_message(
                customer_id=customer_id,
                conversation_id=conversation_id,
                role="assistant",
                content=response_text,
                # Which specialist produced this reply — set by
                # _delegate_to_specialist, None if general assistance.
                # getattr default keeps mock EAs without the attribute
                # from blowing up here.
                specialist_domain=getattr(ea, "last_specialist_domain", None),
            )
        except Exception:
            logger.warning(
                "Persistence failed for customer=%s conv=%s — "
                "reply delivered but not stored",
                customer_id, conversation_id, exc_info=True,
            )

    # Fire-and-forget: bump today's activity counters for the dashboard.
    # Runs after persistence so the assistant message count and
    # delegation count stay consistent — if append_message failed above,
    # we've already logged the WARNING and the exception was swallowed,
    # so this still runs. That's the right call: the customer got a
    # reply, the dashboard should count it.
    try:
        from ..activity_counters import incr_messages, incr_delegation
        redis = request.app.state.redis_client
        await incr_messages(redis, customer_id)
        domain = getattr(ea, "last_specialist_domain", None)
        if domain:
            await incr_delegation(redis, customer_id, domain)
    except Exception:
        logger.debug("activity counter bump failed for customer=%s", customer_id)

    # Fire-and-forget: extract follow-ups and update interaction time
    proactive_store = getattr(request.app.state, "proactive_state_store", None)
    if proactive_store is not None:
        from src.proactive.inbound import process_inbound_message
        try:
            await process_inbound_message(customer_id, req.message, proactive_store)
        except Exception:
            logger.debug("Proactive inbound hook failed for customer=%s", customer_id)

    return MessageResponse(response=response_text, conversation_id=conversation_id)


# ── Onboarding helpers ────────────────────────────────────────────────────

import json as _json

_DEFAULT_PERSONALITY = {"tone": "professional", "language": "en", "name": "Assistant"}


async def _load_personality_from_redis(redis_client, customer_id: str) -> dict:
    """Read personality from settings:{customer_id}. Defaults on failure."""
    try:
        raw = await redis_client.get(f"settings:{customer_id}")
        if raw is None:
            return dict(_DEFAULT_PERSONALITY)
        decoded = raw.decode() if isinstance(raw, bytes) else raw
        data = _json.loads(decoded)
        p = data.get("personality", {})
        return {
            "tone": p.get("tone", _DEFAULT_PERSONALITY["tone"]),
            "language": p.get("language", _DEFAULT_PERSONALITY["language"]),
            "name": p.get("name", _DEFAULT_PERSONALITY["name"]),
        }
    except Exception:
        logger.debug("Failed to load personality for onboarding, using defaults")
        return dict(_DEFAULT_PERSONALITY)


async def _merge_settings(redis_client, customer_id: str, partial: dict) -> None:
    """Read-modify-write settings:{customer_id}, merging the partial dict."""
    try:
        key = f"settings:{customer_id}"
        raw = await redis_client.get(key)
        if raw is None:
            from ..schemas import Settings
            current = Settings().model_dump()
        else:
            decoded = raw.decode() if isinstance(raw, bytes) else raw
            current = _json.loads(decoded)

        for section, values in partial.items():
            if section in current and isinstance(current[section], dict):
                current[section].update(values)
            else:
                current[section] = values

        await redis_client.set(key, _json.dumps(current))
    except Exception:
        logger.warning(
            "Failed to merge settings for customer=%s during onboarding",
            customer_id, exc_info=True,
        )
