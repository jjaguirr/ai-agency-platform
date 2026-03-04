"""Unit tests for async helper utilities."""
import asyncio
import pytest


class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        from src.utils.async_helpers import retry_async

        async def success():
            return 42

        result = await retry_async(success)
        assert result == 42

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        from src.utils.async_helpers import retry_async

        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "ok"

        result = await retry_async(flaky, max_retries=3, delay=0.01)
        assert result == "ok"
        assert call_count == 3
