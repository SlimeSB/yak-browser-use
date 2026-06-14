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


def _create_chat_llm_call(
    on_stream_start=None,
    on_stream_end=None,
    on_text_delta=None,
    on_reasoning_delta=None,
    on_tool_generated=None,
):
    """Create a callable for LLM API calls compatible with conversation_loop.

    Args:
        on_stream_start: Optional callback() called before streaming starts.
        on_stream_end: Optional callback(has_tool_calls) called after streaming.
        on_text_delta: Optional callback(text) for each delta.content chunk.
        on_reasoning_delta: Optional callback(text) for each reasoning_content chunk.
        on_tool_generated: Optional callback(name) when tool name first appears.

    Returns an async function that takes (messages, tools) and returns
    an object with .content and .tool_calls attributes.
    """
    from types import SimpleNamespace

    from utils.browser import create_llm
    from browser_use.llm.messages import UserMessage, SystemMessage, AssistantMessage
    from browser_use.llm.openai.serializer import OpenAIMessageSerializer

    llm = create_llm()
    _streaming = any(cb is not None for cb in [on_text_delta, on_reasoning_delta])
    _streaming_active = False

    async def _call(messages: list[dict], tools: list[dict]) -> object:
        nonlocal _streaming_active

        converted: list = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AssistantMessage(content=content))
            elif role == "tool":
                converted.append(UserMessage(content=f"[tool result] {content}"))
            else:
                converted.append(UserMessage(content=content))

        if not _streaming:
            kwargs: dict = {"messages": converted}
            if tools:
                kwargs["tools"] = tools
            return await llm.ainvoke(**kwargs)

        # ── Streaming path ──────────────────────────────────────────
        openai_messages = list(OpenAIMessageSerializer.serialize_messages(converted))

        for msg in messages:
            if msg.get("role") == "tool":
                tool_msg: dict = {
                    "role": "tool",
                    "content": msg.get("content", ""),
                    "tool_call_id": msg.get("tool_call_id", ""),
                }
                found = False
                for i, existing in enumerate(openai_messages):
                    if isinstance(existing, dict) and existing.get("role") == "user":
                        openai_messages[i] = tool_msg
                        found = True
                        break
                if not found:
                    openai_messages.append(tool_msg)

        client = llm.get_client()

        model_params: dict = {}
        if llm.temperature is not None:
            model_params["temperature"] = llm.temperature
        if llm.frequency_penalty is not None:
            model_params["frequency_penalty"] = llm.frequency_penalty
        if llm.max_completion_tokens is not None:
            model_params["max_completion_tokens"] = llm.max_completion_tokens
        if llm.top_p is not None:
            model_params["top_p"] = llm.top_p
        if llm.seed is not None:
            model_params["seed"] = llm.seed

        if llm.reasoning_models and any(
            str(m).lower() in str(llm.model).lower() for m in llm.reasoning_models
        ):
            model_params["reasoning_effort"] = llm.reasoning_effort
            model_params.pop("temperature", None)
            model_params.pop("frequency_penalty", None)

        create_kwargs: dict = {
            "model": llm.model,
            "messages": openai_messages,
            "stream": True,
            **model_params,
        }
        if tools:
            create_kwargs["tools"] = tools

        _streaming_active = True
        if on_stream_start:
            on_stream_start()

        stream = await client.chat.completions.create(**create_kwargs)

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}
        tool_names_seen: set[str] = set()

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            reasoning = getattr(delta, "reasoning_content", None) or ""
            if reasoning:
                thinking_parts.append(reasoning)
                if on_reasoning_delta:
                    on_reasoning_delta(reasoning)

            if delta.content:
                content_parts.append(delta.content)
                if on_text_delta:
                    on_text_delta(delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    entry = tool_calls_acc[idx]
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            entry["function"]["name"] += tc.function.name
                            full_name = entry["function"]["name"]
                            if full_name not in tool_names_seen:
                                tool_names_seen.add(full_name)
                                if on_tool_generated:
                                    on_tool_generated(full_name)
                        if tc.function.arguments:
                            entry["function"]["arguments"] += tc.function.arguments

        content = "".join(content_parts)
        thinking = "".join(thinking_parts)

        sorted_tc = sorted(tool_calls_acc.items(), key=lambda x: x[0])
        final_tool_calls = [tc for _, tc in sorted_tc]

        if on_stream_end:
            on_stream_end(bool(final_tool_calls))

        _streaming_active = False

        resp = SimpleNamespace()
        resp.content = content
        resp.tool_calls = final_tool_calls if final_tool_calls else None
        resp.thinking = thinking if thinking else None
        return resp

    _call._streaming_active = lambda: _streaming_active

    return _call
