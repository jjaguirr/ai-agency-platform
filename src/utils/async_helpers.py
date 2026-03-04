"""Async utility functions."""
import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar("T")


async def retry_async(
    fn: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff."""
    last_error = None
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= backoff

    raise last_error


async def gather_with_limit(coros, limit: int = 5):
    """Run coroutines with concurrency limit."""
    semaphore = asyncio.Semaphore(limit)

    async def _wrap(coro):
        async with semaphore:
            return await coro

    return await asyncio.gather(*[_wrap(c) for c in coros])
