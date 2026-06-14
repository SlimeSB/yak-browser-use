"""Agent integration — run goal steps and chat mode entry.

Provides two entry points:
- run_goal_step() — goal_run tool backend (stub — goals execute via todo + browser_*)
- start_chat_agent() — chat mode conversation_loop entry
"""
from __future__ import annotations

from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


async def run_goal_step(
    step_def: dict,
    cdp_helpers: object | None,
    step_dir: Path,
    pipeline_name: str,
    frontmatter: dict | None = None,
    source_text: str = "",
    tools_dir: Path | None = None,
    ws_url: str = "",
    pipeline_path: Path | None = None,
    system_prompt: str = "",
) -> dict:
    """Execute a goal step — stub that delegates to todo + browser_* in chat mode.

    Goal steps no longer spawn a browser-use Agent. Instead, the main LLM
    uses todo + browser_* tools to execute complex tasks step by step.
    """
    return {
        "status": "success",
        "skipped": True,
        "message": "Goals execute via todo + browser_* in chat mode",
    }


# ── Chat mode entry ──────────────────────────────────────────────────


async def start_chat_agent(
    *,
    user_message: str,
    cdp_helpers: object,
    pipeline_name: str = "",
    tools_dir: Path | None = None,
    messages: list[dict] | None = None,
    llm_call=None,
    budget: object | None = None,
) -> dict:
    """Start a chat-mode conversation_loop with the given user message.

    This is the chat mode entry point — wraps run_conversation_loop
    with default configuration suitable for interactive chat.

    Args:
        user_message: The user's text input.
        cdp_helpers: CDPHelpers instance for browser operations.
        pipeline_name: Pipeline name for goal_run context.
        tools_dir: Directory containing tool modules.
        messages: Pre-existing conversation messages (for resume).
        llm_call: Async callable(messages, tools) -> LLMResponse.
        budget: Pre-existing IterationBudget (for resume).

    Returns:
        Dict with response, status, messages, budget.
    """
    from engine._harness.conversation_loop import run_conversation_loop
    from engine._harness.tools import get_all_tools
    from prompts._loader import load_prompt

    if messages is None:
        messages = []

    messages.append({"role": "user", "content": user_message})

    system_prompt = load_prompt("chat/system")

    if llm_call is None:
        llm_call = _create_chat_llm_call()

    result = await run_conversation_loop(
        llm_call=llm_call,
        system_prompt=system_prompt,
        messages=messages,
        tools=get_all_tools(),
        cdp_helpers=cdp_helpers,
        tools_dir=tools_dir,
        pipeline_name=pipeline_name,
        budget=budget,
    )

    return {
        "response": result.final_response,
        "status": "completed" if not result.interrupted else "cancelled",
        "messages": result.messages,
        "budget": result.budget.to_dict(),
        "turn_count": result.turn_count,
        "duration_ms": result.duration_ms,
    }


def _create_chat_llm_call():
    """Create a callable for LLM API calls compatible with conversation_loop.

    Returns an async function that takes (messages, tools) and returns
    an object with .content and .tool_calls attributes.
    """
    from utils.browser import create_llm
    from browser_use.llm.messages import UserMessage, SystemMessage, AssistantMessage

    llm = create_llm()

    async def _call(messages: list[dict], tools: list[dict]) -> object:
        converted: list = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AssistantMessage(content=content))
            else:
                converted.append(UserMessage(content=content))

        kwargs = {"messages": converted}
        if tools:
            kwargs["tools"] = tools
        response = await llm.ainvoke(**kwargs)
        return response

    return _call
