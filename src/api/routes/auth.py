"""
Bootstrap login endpoint for the dashboard MVP.

POST /v1/auth/login
  body: {customer_id, secret}
  -> {token, customer_id}

Validates against a pre-shared key stored in Redis at
``customer_secret:{customer_id}``. Returns a JWT via the existing
create_token() machinery.

Limitations (MVP — intentional):
  - No password hashing — secrets are operator-provisioned shared keys
  - No user management or registration
  - No OAuth, no refresh tokens, no MFA
  - Real auth integration comes in a later task
"""
import hmac
import logging

from fastapi import APIRouter, Request

from ..auth import create_token
from ..errors import UnauthorizedError
from ..schemas import LoginRequest, LoginResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request):
    redis = request.app.state.redis_client
    key = f"customer_secret:{req.customer_id}"
    stored = await redis.get(key)

    if stored is None:
        # Same error as wrong secret — don't reveal whether customer exists
        raise UnauthorizedError()

    stored_str = stored.decode() if isinstance(stored, bytes) else stored
    if not hmac.compare_digest(stored_str, req.secret):
        raise UnauthorizedError()

    token = create_token(req.customer_id)
    return LoginResponse(token=token, customer_id=req.customer_id)
