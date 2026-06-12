"""Agent harness — conversation_loop engine and supporting sub-modules.

Extracted from Hermes Agent for use in learning-browser-use.
"""
from __future__ import annotations

from engine._harness.retry_utils import jittered_backoff
from engine._harness.iteration_budget import IterationBudget
from engine._harness.error_classifier import (
    FailoverReason,
    ClassifiedError,
    classify_api_error,
)
from engine._harness.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailState,
    create_chat_guardrail_config,
)
from engine._harness.turn_context import (
    TurnContext,
    InterruptState,
    build_turn_context,
    save_interrupt_state,
)
from engine._harness.tool_executor import (
    execute_tool_calls_sequential,
    execute_tool_calls,
    UnrecoverableError,
)
from engine._harness.conversation_loop import (
    ConversationResult,
    run_conversation_loop,
    run_preset_loop,
    resume_conversation,
    check_exit_conditions,
)
from engine._harness.pipeline_task_adapter import (
    StepInfo,
    TaskDescriptor,
    PipelineTaskAdapter,
)
from engine._harness.tools import (
    BROWSER_TOOLS,
    GOAL_RUN_TOOL,
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
    "run_preset_loop",
    "resume_conversation",
    "check_exit_conditions",
    "StepInfo",
    "TaskDescriptor",
    "PipelineTaskAdapter",
    "BROWSER_TOOLS",
    "GOAL_RUN_TOOL",
    "get_all_tools",
    "get_browser_tools",
]
