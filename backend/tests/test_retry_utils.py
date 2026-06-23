"""Tests for retry_utils module."""

from yak_browser_use.engine._harness.retry_utils import jittered_backoff, sleep_jittered


def test_jittered_backoff_first_attempt():
    delay = jittered_backoff(attempt=1, base_ms=1000, max_ms=30000)
    assert 700 <= delay <= 1300


def test_jittered_backoff_exponential_growth():
    d1 = jittered_backoff(attempt=1, base_ms=1000, max_ms=30000, jitter_ratio=0)
    d2 = jittered_backoff(attempt=2, base_ms=1000, max_ms=30000, jitter_ratio=0)
    d3 = jittered_backoff(attempt=3, base_ms=1000, max_ms=30000, jitter_ratio=0)
    assert d1 == 1000
    assert d2 == 2000
    assert d3 == 4000


def test_jittered_backoff_max_cap():
    delay = jittered_backoff(attempt=20, base_ms=1000, max_ms=30000, jitter_ratio=0)
    assert delay == 30000


def test_sleep_jittered():
    sleep_jittered(attempt=1, base_ms=10, max_ms=10)
