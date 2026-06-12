"""Tests for error_classifier module."""

from engine._harness.error_classifier import (
    FailoverReason,
    ClassifiedError,
    classify_api_error,
)


def test_classify_by_status_code_rate_limit():
    result = classify_api_error(status_code=429, message="Rate limited")
    assert result.reason == FailoverReason.RATE_LIMIT
    assert result.retryable is True


def test_classify_by_status_code_server_error():
    result = classify_api_error(status_code=500, message="Server error")
    assert result.reason == FailoverReason.SERVER_ERROR
    assert result.retryable is True


def test_classify_by_status_code_auth_error():
    result = classify_api_error(status_code=401, message="Unauthorized")
    assert result.reason == FailoverReason.AUTH_ERROR
    assert result.retryable is False


def test_classify_by_status_code_bad_request():
    result = classify_api_error(status_code=400, message="Bad request")
    assert result.reason == FailoverReason.BAD_REQUEST
    assert result.retryable is False


def test_classify_by_status_code_timeout():
    result = classify_api_error(status_code=504, message="Gateway timeout")
    assert result.reason == FailoverReason.TIMEOUT
    assert result.retryable is True


def test_classify_by_exception_class():
    class RateLimitError(Exception):
        pass
    result = classify_api_error(error=RateLimitError("too many requests"))
    assert result.reason == FailoverReason.RATE_LIMIT
    assert result.retryable is True


def test_classify_by_exception_message():
    result = classify_api_error(error=Exception("request timed out"))
    assert result.reason == FailoverReason.TIMEOUT
    assert result.retryable is True


def test_classify_unknown():
    result = classify_api_error(error=Exception("something weird"))
    assert result.reason == FailoverReason.UNKNOWN
    assert result.retryable is True  # default


def test_classified_error_to_dict():
    ce = ClassifiedError(
        reason=FailoverReason.RATE_LIMIT,
        message="Too many requests",
        retryable=True,
        status_code=429,
        provider="openai",
    )
    d = ce.to_dict()
    assert d["reason"] == "rate_limit"
    assert d["status_code"] == 429
    assert d["provider"] == "openai"


def test_status_code_overrides_exception():
    class RateLimitError(Exception):
        pass
    result = classify_api_error(
        error=RateLimitError("..."),
        status_code=401,
        message="Unauthorized",
    )
    assert result.reason == FailoverReason.AUTH_ERROR
    assert result.status_code == 401
