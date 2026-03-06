"""
JWT bearer-token auth for the multi-tenant API.

Scope: extract customer_id from a signed token. Nothing more. No users,
no sessions, no OAuth. Provisioning mints a token; every subsequent
request presents it.
"""
import os
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

_ALGORITHM = "HS256"
_DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET not set. Export it before starting the server."
        )
    return secret


class InvalidTokenError(Exception):
    """Token is expired, tampered, malformed, or missing required claims."""


def create_token(customer_id: str, *, expires_in: int = _DEFAULT_TTL_SECONDS) -> str:
    """Mint a signed JWT carrying the customer_id claim."""
    now = int(time.time())
    payload = {
        "customer_id": customer_id,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Verify signature + expiry; return claims. Raises InvalidTokenError."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except JWTError as e:
        raise InvalidTokenError(str(e)) from e

    if "customer_id" not in claims:
        raise InvalidTokenError("token missing customer_id claim")

    return claims


# --- FastAPI dependency ---------------------------------------------------

# auto_error=False so we can return our own 401 with a clean body instead
# of FastAPI's default 403. Spec says 401 for "credentials missing/invalid".
_bearer = HTTPBearer(auto_error=False)


async def get_current_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Extract + validate customer_id from the Authorization header."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(creds.credentials)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return claims["customer_id"]
