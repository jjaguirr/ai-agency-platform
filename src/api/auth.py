"""
JWT bearer-token auth for the multi-tenant API.

The token's `sub` claim carries the customer ID. Every authenticated request
resolves to a customer — no user management, no login flow, no OAuth. Token
issuance happens at provisioning time (see routes/provisioning.py) or via
`create_token` directly for testing.

Secret comes from `app.state.jwt_secret`, set by the app factory.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

ALGORITHM = "HS256"
DEFAULT_TTL = timedelta(hours=24)


class AuthError(Exception):
    """Token validation failed. Message is safe to surface to clients."""


# --- Token primitives ------------------------------------------------------

def create_token(
    customer_id: str,
    *,
    secret: str,
    expires_delta: timedelta = DEFAULT_TTL,
) -> str:
    """
    Issue a JWT carrying the customer ID.

    `expires_delta` may be negative — useful in tests to mint already-expired
    tokens without monkeypatching the clock.
    """
    exp = datetime.now(timezone.utc) + expires_delta
    claims = {"sub": customer_id, "exp": exp}
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def decode_token(token: str, *, secret: str) -> str:
    """
    Validate signature + expiry and return the customer ID.

    Raises AuthError on any failure. The underlying jose exception hierarchy
    is collapsed to a single error type so callers don't leak jose types.
    """
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except ExpiredSignatureError as e:
        raise AuthError("Token expired") from e
    except JWTError as e:
        raise AuthError("Invalid token") from e

    sub = payload.get("sub")
    if not sub:
        raise AuthError("Token missing subject")
    return sub


# --- FastAPI dependency ----------------------------------------------------

def require_auth(request: Request) -> str:
    """
    Extract and validate the bearer token from the Authorization header.

    Returns the customer ID on success. Raises 401 on any auth failure —
    FastAPI converts this to a JSON response automatically.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Missing or malformed Authorization header")

    secret = request.app.state.jwt_secret
    try:
        return decode_token(token, secret=secret)
    except AuthError as e:
        raise _unauthorized(str(e)) from e


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
