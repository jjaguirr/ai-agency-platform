"""
REST API for the AI Agency Platform.

Public exports:
    create_app(...)       — DI factory for tests/composition
    create_default_app()  — production entrypoint (`uvicorn --factory`)
    create_token(...)     — issue JWT for a customer (testing/admin)
    EARegistry            — per-customer EA cache
"""
from .app import create_app, create_default_app
from .auth import create_token, decode_token
from .ea_registry import EARegistry

__all__ = [
    "create_app",
    "create_default_app",
    "create_token",
    "decode_token",
    "EARegistry",
]
