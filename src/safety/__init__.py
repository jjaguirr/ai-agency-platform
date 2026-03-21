"""Safety layer: input/output sanitization, rate limiting, audit, action risk.

Request flow through the safety layer (Starlette LIFO middleware order):

    CorrelationMiddleware   — assigns correlation ID
    → RateLimitMiddleware   — global + per-customer rate checks (Redis INCR)
    → SafetyMiddleware      — buffers body, runs InputPipeline, rejects or passes
    → Route handler         — EA processes message
    → OutputPipeline        — redacts PII/internal data from EA response
    → AuditLogger           — records safety-relevant events per customer

All middleware is pure ASGI (no BaseHTTPMiddleware). Redis failures are
fail-open: the request proceeds without rate/audit protection rather than
returning a 500 to the customer.
"""
