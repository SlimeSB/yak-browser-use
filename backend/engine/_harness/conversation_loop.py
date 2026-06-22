"""Conversation loop — core agent turn loop for chat and preset replay modes.

The loop:
```
while budget.remaining > 0 and not interrupted:
    1. turn_context.build() — reset guardrails + retry counters
    2. prepare messages + system prompt
    3. LLM call with registered tools
    4. if tool_calls: tool_executor.execute()
       else: final_response = text, break
     5. Agent._check_exit() — budget/interrupt/final_response check
    6. budget.consume() per round-trip
```

Extracted from Hermes Agent — gateway/plugin/persist code removed.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
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
from engine._harness.tool_executor import (
    execute_tool_calls_sequential,
    UnrecoverableError,
    EVENT_TURN_START,
    EVENT_LLM_TURN,
    EVENT_TOOL_START,
    EVENT_TOOL_END,
    EVENT_ERROR,
)

from prompts._loader import load_prompt

logger = get_logger(__name__)

# Default retry config for LLM API calls
_DEFAULT_MAX_LLM_RETRIES = 3
_DEFAULT_LLM_RETRY_BASE_MS = 1000
_DEFAULT_LLM_RETRY_MAX_MS = 30000

# Max consecutive LLM failures before giving up
_MAX_CONSECUTIVE_LLM_FAILURES = 5


@dataclass
class AgentRunState:
    turn_count: int = 0
    interrupted: bool = False
    last_content_with_tools: str = ""
    final_response: str | None = None
    consecutive_llm_failures: int = 0


@dataclass
class ConversationResult:
    """Result of a completed conversation loop."""
    final_response: str | None
    messages: list[dict]
    budget: IterationBudget
    interrupted: bool = False
    turn_count: int = 0
    duration_ms: int = 0


class Agent:

    def __init__(
        self,
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
        shared_store: dict | None = None,
        on_turn_complete: Callable | None = None,
    ):
        self._llm_call = llm_call
        self._system_prompt = system_prompt
        self._messages = messages
        self._tools = tools
        self._cdp_helpers = cdp_helpers
        self._tools_dir = tools_dir
        self._pipeline_name = pipeline_name
        self._budget = budget or IterationBudget(max_total=50)
        self._interrupt_check = interrupt_check
        self._on_event = stream_callback
        self._guardrail_config = guardrail_config
        self._preset_mode = preset_mode
        self._shared_store = shared_store or {}
        self._on_turn_complete = on_turn_complete

        self._guardrail_state = ToolCallGuardrailState()
        self._state = AgentRunState()
        self._start_time = 0.0

    async def run(self) -> ConversationResult:
        if self._guardrail_config is None and not self._preset_mode:
            self._guardrail_config = create_chat_guardrail_config()

        if self._guardrail_config is not None:
            self._guardrail_state.config = self._guardrail_config  # type: ignore[assignment]

        # Load tool_strategy for both chat and preset modes
        # (preset previously used template-injection via preset/system.md;
        #  now it uses build_system_prompt() so tool_strategy is appended here)
        try:
            guidance_text = load_prompt("guidance/tool_strategy")
            self._system_prompt = self._system_prompt + "\n\n" + guidance_text
        except Exception:
            logger.warning("Failed to load guidance/tool_strategy prompt", exc_info=True)

        # Load error_recovery — must be present regardless of how system_prompt was built
        try:
            recovery_text = load_prompt("guidance/error_recovery")
            if recovery_text:
                self._system_prompt = self._system_prompt + "\n\n" + recovery_text
        except Exception:
            logger.warning("Failed to load guidance/error_recovery prompt", exc_info=True)

        self._start_time = time.time()

        while not self._check_exit():
            await self._step()

        if self._interrupt_check and self._interrupt_check():
            self._state.interrupted = True
            logger.info("conversation_loop: interrupted by user")

        return ConversationResult(
            final_response=self._state.final_response,
            messages=self._messages,
            budget=self._budget,
            interrupted=self._state.interrupted,
            turn_count=self._state.turn_count,
            duration_ms=int((time.time() - self._start_time) * 1000),
        )

    async def _step(self) -> None:
        self._state.turn_count += 1
        turn_ctx = build_turn_context(guardrail_state=self._guardrail_state)

        logger.debug("conversation_loop: turn %d (budget remaining=%d)",
                     self._state.turn_count, self._budget.remaining)

        self._emit(EVENT_TURN_START, turn=self._state.turn_count,
                   budget_remaining=self._budget.remaining)

        api_messages = _prepare_messages(self._messages, self._system_prompt)

        response = await _call_llm_with_retry(
            llm_call=self._llm_call,
            messages=api_messages,
            tools=self._tools,
            turn_ctx=turn_ctx,
        )

        if response is None:
            self._state.consecutive_llm_failures += 1
            if self._state.consecutive_llm_failures >= _MAX_CONSECUTIVE_LLM_FAILURES:
                logger.error("conversation_loop: max consecutive LLM failures reached")
                self._emit(EVENT_ERROR,
                           message=f"LLM 调用连续失败 {_MAX_CONSECUTIVE_LLM_FAILURES} 次，请检查 API 配置或网络连接。")
                self._state.interrupted = True
            return
        else:
            self._state.consecutive_llm_failures = 0

        if self._on_event:
            thinking = getattr(response, 'reasoning', None) or getattr(response, 'thinking', None)
            content = getattr(response, 'content', '') or ''
            tool_calls_data = getattr(response, 'tool_calls', None) or []
            self._emit(EVENT_LLM_TURN, turn=self._state.turn_count,
                       content=content or None, thinking=thinking or None,
                       tool_calls=[{
                           "name": (tc.get("function") or {}).get("name", ""),
                           "args": (tc.get("function") or {}).get("arguments", "{}"),
                       } for tc in tool_calls_data] if tool_calls_data else None)

        self._budget.consume(1)

        tool_calls = getattr(response, "tool_calls", None) or []

        if tool_calls:
            logger.debug("conversation_loop: turn %d has %d tool call(s)",
                         self._state.turn_count, len(tool_calls))
            self._messages.append(_build_assistant_message(response))

            if not self._preset_mode:
                content = getattr(response, "content", "") or ""
                if content.strip():
                    self._state.last_content_with_tools = content

            try:
                await execute_tool_calls_sequential(
                    messages=self._messages,
                    tool_calls=tool_calls,
                    cdp_helpers=self._cdp_helpers,
                    tools_dir=self._tools_dir,
                    pipeline_name=self._pipeline_name,
                    guardrail_state=self._guardrail_state,
                    budget=self._budget,
                    interrupt_check=self._interrupt_check,
                    stream_callback=self._on_event,
                    llm_call=self._llm_call,
                    shared_store=self._shared_store,
                )
            except UnrecoverableError as e:
                logger.error("conversation_loop: unrecoverable error, stopping: %s", e)
                self._emit(EVENT_ERROR, message=str(e))
                self._state.interrupted = True
        else:
            content = getattr(response, "content", None)
            final_response = content or ""

            if not final_response.strip():
                final_response = self._state.last_content_with_tools

            self._messages.append(_build_assistant_message(response))
            self._state.final_response = final_response
            logger.debug("conversation_loop: turn %d text response (%d chars)",
                         self._state.turn_count, len(final_response or ""))

        # Notify caller that a turn completed (for persistence etc.)
        if self._on_turn_complete:
            self._on_turn_complete()

    def _check_exit(self) -> bool:
        if self._state.interrupted:
            return True
        if self._state.final_response is not None:
            return True
        if self._budget.is_exhausted:
            logger.info("conversation_loop: budget exhausted (%d/%d)",
                         self._budget.used, self._budget.max_total)
            return True
        if self._interrupt_check and self._interrupt_check():
            logger.info("conversation_loop: user interrupted")
            return True
        return False

    def _emit(self, event_type: str, **data) -> None:
        if self._on_event:
            self._on_event({"type": event_type, **data})


# ── Backward-compatible wrappers ────────────────────────────────────────────


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
    shared_store: dict | None = None,
    on_turn_complete: Callable | None = None,
) -> ConversationResult:
    agent = Agent(
        llm_call=llm_call,
        system_prompt=system_prompt,
        messages=messages,
        tools=tools,
        cdp_helpers=cdp_helpers,
        tools_dir=tools_dir,
        pipeline_name=pipeline_name,
        budget=budget,
        interrupt_check=interrupt_check,
        stream_callback=stream_callback,
        guardrail_config=guardrail_config,
        preset_mode=preset_mode,
        shared_store=shared_store,
        on_turn_complete=on_turn_complete,
    )
    return await agent.run()


# ── Shared helpers ──────────────────────────────────────────────────────────


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

    return messages, budget, interrupt_state.error_info
