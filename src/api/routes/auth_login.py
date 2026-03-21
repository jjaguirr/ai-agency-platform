"""
Dashboard login endpoint.

POST /v1/auth/login
  body: {customer_id, secret}
  auth: none
  → {token, customer_id}

MVP bootstrap auth: a per-customer pre-shared key is stored in Redis at
`auth:{customer_id}:secret`. This is NOT a production auth scheme — no
password hashing, no OAuth, no account recovery. It exists so the
dashboard has *something* to trade for a JWT. Real OAuth replaces this
when we have an identity provider to delegate to. See the spec comment
on the LoginRequest schema for the threat model we're accepting.

The secret comparison is constant-time to avoid leaking prefix length
via response timing.
"""
import hmac
import logging

from fastapi import APIRouter, HTTPException, Request, status

from ..auth import create_token
from ..schemas import LoginRequest, LoginResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/auth", tags=["auth"])

_REDIS_KEY = "auth:{customer_id}:secret"


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    redis = request.app.state.redis_client

    stored = await redis.get(_REDIS_KEY.format(customer_id=req.customer_id))
    if stored is None:
        # Same error for "no such customer" and "wrong secret" — don't
        # leak which customer_ids are valid.
        logger.info("login failed: unknown customer_id=%s", req.customer_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # redis.asyncio returns bytes unless decode_responses=True; handle both.
    if isinstance(stored, bytes):
        stored = stored.decode("utf-8")

    if not hmac.compare_digest(stored, req.secret):
        logger.info("login failed: bad secret for customer_id=%s", req.customer_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_token(req.customer_id)
    return LoginResponse(token=token, customer_id=req.customer_id)
