"""Conversation loop — core agent turn loop for chat and preset replay modes.

The loop:
```
while budget.remaining > 0 and not interrupted:
    1. turn_context.build() — reset guardrails + retry counters
    2. prepare messages + system prompt
    3. LLM call with registered tools
    4. if tool_calls: tool_executor.execute()
       else: final_response = text, break
    5. check_exit_conditions() — guardrail/budget/interrupt check
    6. budget.consume() per round-trip
```

Extracted from Hermes Agent — gateway/plugin/persist code removed.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utils.logging import get_logger

from engine._harness.retry_utils import jittered_backoff
from engine._harness.iteration_budget import IterationBudget
from engine._harness.error_classifier import classify_api_error
from engine._harness.tool_guardrails import ToolCallGuardrailState, create_chat_guardrail_config
from engine._harness.turn_context import (
    TurnContext,
    build_turn_context,
    InterruptState,
)
from engine._harness.tool_executor import execute_tool_calls_sequential, UnrecoverableError

from prompts._loader import load_prompt

logger = get_logger(__name__)

# Default retry config for LLM API calls
_DEFAULT_MAX_LLM_RETRIES = 3
_DEFAULT_LLM_RETRY_BASE_MS = 1000
_DEFAULT_LLM_RETRY_MAX_MS = 30000

# Max consecutive LLM failures before giving up
_MAX_CONSECUTIVE_LLM_FAILURES = 5


async def _safe_inject_highlights(cdp_helpers: object) -> None:
    try:
        await cdp_helpers.add_dom_highlights()  # type: ignore[union-attr]
    except Exception:
        pass


async def run_conversation_loop(
    *,
    llm_call: Callable,
    system_prompt: str,
    messages: list[dict],
    tools: list[dict],
    cdp_helpers: object | None = None,
    tools_dir: Path | None = None,
    pipeline_name: str = "",
    budget: IterationBudget | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    stream_callback: Callable[[dict], None] | None = None,
    guardrail_config: object | None = None,
    preset_mode: bool = False,
) -> ConversationResult:
    """Run the conversation loop until complete or interrupted.

    Args:
        llm_call: Async callable(messages, tools) -> LLMResponse.
        system_prompt: System prompt text.
        messages: Initial conversation messages (mutated in-place).
        tools: Registered tool definitions for LLM.
        cdp_helpers: Browser CDP helpers instance.
        tools_dir: Directory for tool modules.
        pipeline_name: Pipeline name for goal_run.
        budget: IterationBudget (created with default 50 if None).
        interrupt_check: Returns True if conversation should be interrupted.
        stream_callback: Callback for streaming tool events.
        guardrail_config: ToolCallGuardrailConfig (chat relaxed defaults if None).
        preset_mode: True for preset replay, False for chat mode.

    Returns:
        ConversationResult with final_response and stats.
    """
    if budget is None:
        budget = IterationBudget(max_total=50)
    if guardrail_config is None and not preset_mode:
        guardrail_config = create_chat_guardrail_config()

    guardrail_state = ToolCallGuardrailState()

    if guardrail_config is not None:
        guardrail_state.config = guardrail_config  # type: ignore[assignment]

    # Inject tool strategy guidance (chat mode only; preset injects via system.md)
    if not preset_mode:
        try:
            guidance_text = load_prompt("guidance/tool_strategy")
            system_prompt = system_prompt + "\n\n" + guidance_text
        except Exception:
            pass

    start_time = time.time()
    final_response: str | None = None
    consecutive_llm_failures = 0
    interrupted = False
    turn_count = 0
    # Cache text content from turns where model also called tools
    # so it can be used as final_response if the next turn is pure text.
    last_content_with_tools: str = ""

    # Main loop
    if cdp_helpers is not None and hasattr(cdp_helpers, "add_dom_highlights"):
        asyncio.create_task(_safe_inject_highlights(cdp_helpers))

    while not check_exit_conditions(budget, interrupt_check, guardrail_state):
        turn_count += 1
        turn_ctx = build_turn_context(guardrail_state=guardrail_state)

        logger.debug("conversation_loop: turn %d (budget remaining=%d)",
                     turn_count, budget.remaining)

        if stream_callback:
            stream_callback({
                "type": "turn_start",
                "turn": turn_count,
                "budget_remaining": budget.remaining,
            })

        # Prepare messages with system prompt
        api_messages = _prepare_messages(messages, system_prompt)

        # LLM call with retry on transient errors
        response = await _call_llm_with_retry(
            llm_call=llm_call,
            messages=api_messages,
            tools=tools,
            turn_ctx=turn_ctx,
        )

        if response is None:
            consecutive_llm_failures += 1
            if consecutive_llm_failures >= _MAX_CONSECUTIVE_LLM_FAILURES:
                logger.error("conversation_loop: max consecutive LLM failures reached")
                break
            continue
        else:
            consecutive_llm_failures = 0

        # Consume budget for this round-trip
        budget.consume(1)

        # Check for tool calls
        tool_calls = getattr(response, "tool_calls", None) or []

        if tool_calls:
            logger.debug("conversation_loop: turn %d has %d tool call(s)",
                         turn_count, len(tool_calls))
            messages.append(_build_assistant_message(response))

            # Cache text content when model speaks while also calling tools
            # TODO: stream to frontend via "chat.interim" event when UI supports it
            if not preset_mode:
                content = getattr(response, "content", "") or ""
                if content.strip():
                    last_content_with_tools = content

            try:
                await execute_tool_calls_sequential(
                    messages=messages,
                    tool_calls=tool_calls,
                    cdp_helpers=cdp_helpers,
                    tools_dir=tools_dir,
                    pipeline_name=pipeline_name,
                    guardrail_state=guardrail_state,
                    budget=budget,
                    interrupt_check=interrupt_check,
                    stream_callback=stream_callback,
                )
            except UnrecoverableError as e:
                logger.error("conversation_loop: unrecoverable error, stopping: %s", e)
                if stream_callback:
                    stream_callback({"type": "chat.error", "message": str(e)})
                interrupted = True
                break
        else:
            content = getattr(response, "content", None)
            if content is None:
                content = getattr(response, "completion", "")
            final_response = content or ""

            # Fall back to cached content from prior tool-calling turns
            # TODO: push interim content from those turns via "chat.interim" when UI is ready
            if not final_response.strip():
                final_response = last_content_with_tools

            messages.append(_build_assistant_message(response))
            logger.debug("conversation_loop: turn %d text response (%d chars)",
                         turn_count, len(final_response or ""))
            if stream_callback:
                stream_callback({
                    "type": "chat.message",
                    "content": final_response,
                })
            break

    # Check for interrupt
    if interrupt_check and interrupt_check():
        interrupted = True
        logger.info("conversation_loop: interrupted by user")

    return ConversationResult(
        final_response=final_response,
        messages=messages,
        budget=budget,
        interrupted=interrupted,
        turn_count=turn_count,
        duration_ms=int((time.time() - start_time) * 1000),
    )


async def _call_llm_with_retry(
    llm_call: Callable,
    messages: list[dict],
    tools: list[dict],
    turn_ctx: TurnContext,
) -> object | None:
    """Call LLM with retry on transient errors, using error_classifier."""
    for attempt in range(1, turn_ctx.max_api_retries + 1):
        try:
            return await llm_call(messages, tools)
        except Exception as e:
            classified = classify_api_error(error=e)
            logger.warning(
                "conversation_loop: LLM call failed (attempt %d/%d): %s [%s, retryable=%s]",
                attempt, turn_ctx.max_api_retries,
                classified.message, classified.reason.value, classified.retryable,
            )

            if not classified.retryable:
                logger.error("conversation_loop: non-retryable LLM error: %s", classified.message)
                return None

            if attempt < turn_ctx.max_api_retries:
                delay_s = jittered_backoff(attempt, _DEFAULT_LLM_RETRY_BASE_MS,
                                            _DEFAULT_LLM_RETRY_MAX_MS) / 1000.0
                await asyncio.sleep(max(0, delay_s))

    return None


def check_exit_conditions(
    budget: IterationBudget,
    interrupt_check: Callable[[], bool] | None = None,
    guardrail_state: ToolCallGuardrailState | None = None,
) -> bool:
    """Check if the conversation loop should exit.

    Returns True if any exit condition is met:
    - Budget exhausted
    - User interrupted
    """
    if budget.is_exhausted:
        logger.info("conversation_loop: budget exhausted (%d/%d)",
                     budget.used, budget.max_total)
        return True

    if interrupt_check and interrupt_check():
        logger.info("conversation_loop: user interrupted")
        return True

    return False


def _prepare_messages(messages: list[dict], system_prompt: str) -> list[dict]:
    """Prepare API messages with system prompt."""
    api_messages: list[dict] = []
    if system_prompt:
        api_messages.append({"role": "system", "content": system_prompt})
    api_messages.extend(messages)
    return api_messages


def _build_assistant_message(response: object) -> dict:
    """Build an assistant message from an LLM response."""
    content = getattr(response, "content", "")
    tool_calls = getattr(response, "tool_calls", None)

    msg: dict = {"role": "assistant"}
    if content:
        msg["content"] = content
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def resume_conversation(
    interrupt_state: InterruptState,
    system_prompt: str,
) -> tuple[list[dict], IterationBudget | None, dict | None]:
    """Restore conversation from saved interrupt state.

    Explicitly creates a fresh TurnContext to reset retry counters.
    Returns: (messages, budget, error_info)
    """
    messages = interrupt_state.messages

    budget = None
    if interrupt_state.budget:
        budget = IterationBudget.from_dict(interrupt_state.budget)

    build_turn_context()

    return messages, budget, interrupt_state.error_info


@dataclass
class ConversationResult:
    """Result of a completed conversation loop."""
    final_response: str | None
    messages: list[dict]
    budget: IterationBudget
    interrupted: bool = False
    turn_count: int = 0
    duration_ms: int = 0


async def run_preset_loop(
    *,
    step_defs: list[dict],
    frontmatter: dict | None = None,
    llm_call: Callable,
    messages: list[dict] | None = None,
    cdp_helpers: object | None = None,
    tools_dir: Path | None = None,
    budget: IterationBudget | None = None,
    interrupt_check: Callable[[], bool] | None = None,
    stream_callback: Callable[[dict], None] | None = None,
) -> ConversationResult:
    """Run the conversation loop in preset replay mode.

    Converts compiled StepDef[] via PipelineTaskAdapter into a
    TaskDescriptor, injects it into the preset system prompt, and
    runs the conversation_loop with the task description as context.

    Args:
        step_defs: List of compiled step definitions from compiler.
        frontmatter: Pipeline frontmatter (name, goal, etc.).
        llm_call: Async callable(messages, tools) -> LLMResponse.
        messages: Pre-existing conversation messages.
        cdp_helpers: Browser CDP helpers instance.
        tools_dir: Directory for tool modules.
        budget: IterationBudget.
        interrupt_check: Interrupt check callback.
        stream_callback: Event streaming callback.

    Returns:
        ConversationResult.
    """
    from engine._harness.pipeline_task_adapter import PipelineTaskAdapter
    from engine._harness.tools import get_all_tools

    adapter = PipelineTaskAdapter(step_defs, frontmatter)
    task_descriptor = adapter.build_descriptor()

    try:
        tool_strategy = load_prompt("guidance/tool_strategy")
    except Exception:
        tool_strategy = ""

    try:
        error_recovery = load_prompt("guidance/error_recovery")
    except Exception:
        error_recovery = ""

    system_prompt = load_prompt(
        "preset/system",
        pipeline=task_descriptor.format(),
        tool_strategy=tool_strategy,
        error_recovery=error_recovery,
    )

    if messages is None:
        messages = []

    pipeline_name = frontmatter.get("name", "preset") if frontmatter else "preset"

    return await run_conversation_loop(
        llm_call=llm_call,
        system_prompt=system_prompt,
        messages=messages,
        tools=get_all_tools(),
        cdp_helpers=cdp_helpers,
        tools_dir=tools_dir,
        pipeline_name=pipeline_name,
        budget=budget,
        interrupt_check=interrupt_check,
        stream_callback=stream_callback,
        preset_mode=True,
    )
