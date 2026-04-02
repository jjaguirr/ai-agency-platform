"""Shared constants for the API layer."""

# EA has an internal specialist_timeout (15s) but the overall LangGraph
# run has no bound. A hung LLM endpoint or half-open Redis connection would
# otherwise hold a request — and its worker — indefinitely.
EA_CALL_TIMEOUT = 60.0
