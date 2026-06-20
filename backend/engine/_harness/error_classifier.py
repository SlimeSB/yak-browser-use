"""LLM API error classification.

Handles HTTP status codes, SDK exceptions, network timeouts,
rate limits, and auth failures from LLM providers.
Never handles browser tool execution errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from utils.logging import get_logger

logger = get_logger(__name__)


class FailoverReason(Enum):
    """Reason an LLM call failed and needs failover."""

    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    AUTH_ERROR = "auth_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    BAD_REQUEST = "bad_request"
    CONTENT_FILTER = "content_filter"
    CONTEXT_LENGTH = "context_length"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """Structured error from LLM API classification."""

    reason: FailoverReason
    message: str
    retryable: bool = True
    status_code: int | None = None
    provider: str = ""
    raw_error: object | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "reason": self.reason.value,
            "message": self.message,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "provider": self.provider,
        }


# HTTP status -> FailoverReason mapping
_STATUS_MAP: dict[int, tuple[FailoverReason, bool]] = {
    400: (FailoverReason.BAD_REQUEST, False),
    401: (FailoverReason.AUTH_ERROR, False),
    402: (FailoverReason.AUTH_ERROR, False),
    403: (FailoverReason.AUTH_ERROR, False),
    404: (FailoverReason.BAD_REQUEST, False),
    408: (FailoverReason.TIMEOUT, True),
    409: (FailoverReason.RATE_LIMIT, True),
    413: (FailoverReason.CONTEXT_LENGTH, False),
    429: (FailoverReason.RATE_LIMIT, True),
    500: (FailoverReason.SERVER_ERROR, True),
    502: (FailoverReason.SERVER_ERROR, True),
    503: (FailoverReason.SERVER_ERROR, True),
    504: (FailoverReason.TIMEOUT, True),
}

# Exception class names to reason mapping
_EXCEPTION_MAP: dict[str, tuple[FailoverReason, bool]] = {
    "RateLimitError": (FailoverReason.RATE_LIMIT, True),
    "APIConnectionError": (FailoverReason.NETWORK_ERROR, True),
    "APITimeoutError": (FailoverReason.TIMEOUT, True),
    "AuthenticationError": (FailoverReason.AUTH_ERROR, False),
    "BadRequestError": (FailoverReason.BAD_REQUEST, False),
    "PermissionDeniedError": (FailoverReason.AUTH_ERROR, False),
    "InternalServerError": (FailoverReason.SERVER_ERROR, True),
    "ServiceUnavailableError": (FailoverReason.SERVER_ERROR, True),
    "ConflictError": (FailoverReason.RATE_LIMIT, True),
    "ContentFilterError": (FailoverReason.CONTENT_FILTER, False),
    "ContextLengthExceededError": (FailoverReason.CONTEXT_LENGTH, False),
    "InvalidRequestError": (FailoverReason.BAD_REQUEST, False),
}


def classify_api_error(
    error: Exception | None = None,
    status_code: int | None = None,
    message: str = "",
    provider: str = "",
) -> ClassifiedError:
    """Classify an LLM API error for structured handling.

    Args:
        error: The exception object (for class-name matching).
        status_code: HTTP status code (for code-based matching).
        message: Human-readable error message.
        provider: LLM provider name (openai, anthropic, etc.).

    Returns:
        ClassifiedError with failover reason and retryability.
    """
    reason = FailoverReason.UNKNOWN
    retryable = True

    if status_code is not None:
        mapping = _STATUS_MAP.get(status_code)
        if mapping:
            reason, retryable = mapping

    if error is not None and reason == FailoverReason.UNKNOWN:
        cls_name = type(error).__name__
        for keyword, mapping in _EXCEPTION_MAP.items():
            if keyword in cls_name:
                reason, retryable = mapping
                break

    if not message:
        message = str(error) if error else ""

    if reason == FailoverReason.UNKNOWN and error is not None:
        msg_lower = str(error).lower()
        if "rate" in msg_lower or "throttle" in msg_lower:
            reason = FailoverReason.RATE_LIMIT
            retryable = True
        elif "timeout" in msg_lower or "timed out" in msg_lower:
            reason = FailoverReason.TIMEOUT
            retryable = True
        elif "auth" in msg_lower or "permission" in msg_lower:
            reason = FailoverReason.AUTH_ERROR
            retryable = False
        elif "context length" in msg_lower or "maximum length" in msg_lower or "token limit" in msg_lower:
            reason = FailoverReason.CONTEXT_LENGTH
            retryable = False
        elif ("context" in msg_lower and ("length" in msg_lower or "limit" in msg_lower or "window" in msg_lower or "size" in msg_lower or "exceed" in msg_lower)):
            reason = FailoverReason.CONTEXT_LENGTH
            retryable = False

    logger.debug(
        "Classified API error: reason=%s, retryable=%s, provider=%s, message=%s",
        reason.value,
        retryable,
        provider,
        message,
    )

    return ClassifiedError(
        reason=reason,
        message=message,
        retryable=retryable,
        status_code=status_code,
        provider=provider,
        raw_error=error,
    )
