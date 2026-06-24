"""Agent integration — LLM call factory for chat mode.

Provides:
- _create_chat_llm_call() — streaming llm_call for interactive chat
"""
from __future__ import annotations

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


def _create_chat_llm_call(
    persist_id: str = "",
    on_stream_start=None,
    on_stream_end=None,
    on_text_delta=None,
    on_reasoning_delta=None,
    on_tool_generated=None,
    interrupt_check=None,
):
    """Create a callable for LLM API calls compatible with conversation_loop.

    Args:
        persist_id: Identifier for persisting LLM response logs (session_id or run_id).
        on_stream_start: Optional callback() called before streaming starts.
        on_stream_end: Optional callback(has_tool_calls) called after streaming.
        on_text_delta: Optional callback(text) for each delta.content chunk.
        on_reasoning_delta: Optional callback(text) for each reasoning_content chunk.
        on_tool_generated: Optional callback(name) when tool name first appears.
        interrupt_check: Optional callable returning True if streaming should be interrupted.

    Returns an async function that takes (messages, tools) and returns
    an object with .content and .tool_calls attributes.
    """
    from types import SimpleNamespace

    from yak_browser_use.utils.browser import create_llm
    from yak_browser_use.utils.response_logger import _log_non_streaming_response, _log_streaming_response
    from yak_browser_use.llm.messages import UserMessage, SystemMessage, AssistantMessage, ToolCall
    from yak_browser_use.llm.client import serialize_messages

    llm = create_llm()
    _streaming = any(cb is not None for cb in [on_text_delta, on_reasoning_delta])
    _streaming_active = False

    _turn_counter = {"value": 0}

    def _advance_turn():
        _turn_counter["value"] += 1
        return _turn_counter["value"]

    async def _call(messages: list[dict], tools: list[dict]) -> object:
        nonlocal _streaming_active

        request_summary = {
            "model": getattr(llm, "model", ""),
            "messages_count": len(messages),
            "tools_count": len(tools) if tools else 0,
        }

        converted: list = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                tool_calls_data = msg.get("tool_calls")
                if tool_calls_data:
                    tc_objs = [ToolCall(**tc) for tc in tool_calls_data]
                    converted.append(AssistantMessage(content=content, tool_calls=tc_objs))
                else:
                    converted.append(AssistantMessage(content=content))
            elif role == "tool":
                converted.append(UserMessage(content=f"[tool result] {content}"))
            else:
                converted.append(UserMessage(content=content))

        if not _streaming:
            kwargs: dict = {"messages": converted}
            if tools:
                kwargs["tools"] = tools
            response = await llm.ainvoke(**kwargs)
            _local_turn = _advance_turn()
            _log_non_streaming_response(persist_id, _local_turn, response, request_summary)
            return response

        # ── Streaming path ──────────────────────────────────────────
        openai_messages = list(serialize_messages(converted))

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
                        ec = existing.get("content", "")
                        if isinstance(ec, str) and ec.startswith("[tool result]"):
                            openai_messages[i] = tool_msg
                            found = True
                            break
                if not found:
                    openai_messages.append(tool_msg)

        client = llm.get_client()

        model_params: dict = {}
        if getattr(llm, "temperature", None) is not None:
            model_params["temperature"] = getattr(llm, "temperature", None)
        if getattr(llm, "frequency_penalty", None) is not None:
            model_params["frequency_penalty"] = getattr(llm, "frequency_penalty", None)
        if getattr(llm, "max_completion_tokens", None) is not None:
            model_params["max_completion_tokens"] = getattr(llm, "max_completion_tokens", None)
        if getattr(llm, "top_p", None) is not None:
            model_params["top_p"] = getattr(llm, "top_p", None)
        if getattr(llm, "seed", None) is not None:
            model_params["seed"] = getattr(llm, "seed", None)

        if getattr(llm, "reasoning_models", None) and any(
            str(m).lower() in str(getattr(llm, "model", "")).lower() for m in getattr(llm, "reasoning_models", [])
        ):
            model_params["reasoning_effort"] = getattr(llm, "reasoning_effort", None)
            model_params.pop("temperature", None)
            model_params.pop("frequency_penalty", None)

        create_kwargs: dict = {
            "model": getattr(llm, "model", ""),
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

        _last_chunk_usage = None
        _last_chunk_model = None

        _chunk_count = 0
        async for chunk in stream:
            _chunk_count += 1
            if interrupt_check and _chunk_count % 10 == 0 and interrupt_check():
                break
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

            _last_chunk_usage = chunk.usage if getattr(chunk, "usage", None) else _last_chunk_usage
            _last_chunk_model = getattr(chunk, "model", None) or _last_chunk_model

        content = "".join(content_parts)
        thinking = "".join(thinking_parts)

        sorted_tc = sorted(tool_calls_acc.items(), key=lambda x: x[0])
        final_tool_calls = [tc for _, tc in sorted_tc]

        if on_stream_end:
            on_stream_end(bool(final_tool_calls))

        _local_turn = _advance_turn()
        usage_dict: dict | None = None
        if _last_chunk_usage is not None:
            usage_dict = {
                "prompt_tokens": getattr(_last_chunk_usage, "prompt_tokens", None),
                "completion_tokens": getattr(_last_chunk_usage, "completion_tokens", None),
                "total_tokens": getattr(_last_chunk_usage, "total_tokens", None),
            }
        _log_streaming_response(
            persist_id, _local_turn, create_kwargs, content, thinking, final_tool_calls,
            usage=usage_dict,
            model=_last_chunk_model,
        )

        _streaming_active = False

        resp = SimpleNamespace()
        resp.content = content
        resp.tool_calls = final_tool_calls if final_tool_calls else None
        resp.thinking = thinking if thinking else None
        return resp

    _call._streaming_active = lambda: _streaming_active

    return _call



