"""Agent harness — conversation_loop engine and supporting sub-modules.

Extracted from Hermes Agent for use in yak-browser-use.
"""
from __future__ import annotations

from yak_browser_use.engine._harness.retry_utils import jittered_backoff
from yak_browser_use.engine._harness.iteration_budget import IterationBudget
from yak_browser_use.engine._harness.error_classifier import (
    FailoverReason,
    ClassifiedError,
    classify_api_error,
)
from yak_browser_use.engine._harness.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailState,
    create_chat_guardrail_config,
)
from yak_browser_use.engine._harness.turn_context import (
    TurnContext,
    InterruptState,
    build_turn_context,
    save_interrupt_state,
)
from yak_browser_use.engine._harness.tool_executor import (
    execute_tool_calls_sequential,
    execute_tool_calls,
    UnrecoverableError,
)
from yak_browser_use.engine._harness.conversation_loop import (
    ConversationResult,
    run_conversation_loop,
    resume_conversation,
)
from yak_browser_use.engine._harness.tools import (
    get_all_tools,
    get_browser_tools,
)

__all__ = [
    "jittered_backoff",
    "IterationBudget",
    "FailoverReason",
    "ClassifiedError",
    "classify_api_error",
    "ToolCallGuardrailConfig",
    "ToolCallGuardrailState",
    "create_chat_guardrail_config",
    "TurnContext",
    "InterruptState",
    "build_turn_context",
    "save_interrupt_state",
    "execute_tool_calls_sequential",
    "execute_tool_calls",
    "UnrecoverableError",
    "ConversationResult",
    "run_conversation_loop",
    "resume_conversation",
    "get_all_tools",
    "get_browser_tools",
]
