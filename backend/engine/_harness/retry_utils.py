"""Jittered exponential-backoff delay for LLM API retries."""

import asyncio
import random
import time


def jittered_backoff(
    attempt: int,
    base_ms: float = 1000,
    max_ms: float = 30000,
    jitter_ratio: float = 0.3,
) -> float:
    """Compute exponential-backoff delay with jitter.

    Returns delay in milliseconds. Suitable for LLM API rate-limit
    and transient-error retry strategies.
    """
    exponent = max(0, attempt - 1)
    delay = min(base_ms * (2 ** exponent), max_ms)
    jitter = random.uniform(-jitter_ratio * delay, jitter_ratio * delay)
    result = delay + jitter
    return result


def sleep_jittered(attempt: int, base_ms: float = 1000,
                   max_ms: float = 30000) -> None:
    """Block for jittered_backoff milliseconds. Prefer async_sleep_jittered in async code."""
    delay_s = jittered_backoff(attempt, base_ms, max_ms) / 1000.0
    time.sleep(max(0, delay_s))


async def async_sleep_jittered(attempt: int, base_ms: float = 1000,
                                max_ms: float = 30000) -> None:
    """Non-blocking version of sleep_jittered for async contexts."""
    delay_s = jittered_backoff(attempt, base_ms, max_ms) / 1000.0
    await asyncio.sleep(max(0, delay_s))
