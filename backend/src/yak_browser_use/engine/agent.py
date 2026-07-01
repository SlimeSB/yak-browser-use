"""Agent integration — LLM call factory for chat mode.

Provides:
- _create_chat_llm_call() — streaming llm_call for interactive chat
"""
from __future__ import annotations

from types import SimpleNamespace

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

_cached_llm: object | None = None


def _get_cached_llm() -> object:
    """Return a cached LLM client instance (created once per process).

    NOTE: The cache does NOT react to runtime config changes
    (e.g. user updating the API key via Settings).  A process
    restart is required to pick up new provider config.
    """
    global _cached_llm
    if _cached_llm is None:
        from yak_browser_use.utils.browser import create_llm
        _cached_llm = create_llm()
    return _cached_llm


class StreamingLLMCall:
    """Callable class wrapping LLM streaming/non-streaming call logic.

    Replaces the previous closure-based ``_create_chat_llm_call`` so that
    each internal concern (message conversion, model-param construction,
    streaming chunk processing) is an explicit method rather than nested
    scopes captured by the closure.

    Call signature::

        result = await instance(messages, tools)
        # result.content, result.tool_calls, result.thinking
        instance.streaming_active  # bool, True while streaming
    """

    def __init__(
        self,
        *,
        persist_id: str = "",
        on_stream_start=None,
        on_stream_end=None,
        on_text_delta=None,
        on_reasoning_delta=None,
        on_tool_generated=None,
        interrupt_check=None,
    ):
        self._persist_id = persist_id
        self._on_stream_start = on_stream_start
        self._on_stream_end = on_stream_end
        self._on_text_delta = on_text_delta
        self._on_reasoning_delta = on_reasoning_delta
        self._on_tool_generated = on_tool_generated
        self._interrupt_check = interrupt_check

        self._llm = _get_cached_llm()

        self._streaming = any(cb is not None for cb in [
            on_text_delta, on_reasoning_delta,
        ])
        self._streaming_active = False
        self._turn_counter = 0

    # ── Public API ──────────────────────────────────────────────────

    @property
    def streaming_active(self) -> bool:
        return self._streaming_active

    async def __call__(self, messages: list[dict], tools: list[dict]) -> object:
        self._turn_counter += 1
        request_summary = {
            "model": getattr(self._llm, "model", ""),
            "messages_count": len(messages),
            "tools_count": len(tools) if tools else 0,
        }

        converted = self._convert_messages(messages)

        if not self._streaming:
            return await self._non_streaming_call(converted, tools, request_summary)

        return await self._streaming_call(messages, converted, tools, request_summary)

    # ── Message conversion ─────────────────────────────────────────

    @staticmethod
    def _convert_messages(messages: list[dict]) -> list:
        from yak_browser_use.llm.messages import (
            UserMessage, SystemMessage, AssistantMessage, ToolCall,
        )
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
        return converted

    # ── Non-streaming path ─────────────────────────────────────────

    async def _non_streaming_call(
        self, converted: list, tools: list[dict], request_summary: dict,
    ) -> object:
        from yak_browser_use.utils.response_logger import _log_non_streaming_response

        kwargs: dict = {"messages": converted}
        if tools:
            kwargs["tools"] = tools
        response = await self._llm.ainvoke(**kwargs)
        _log_non_streaming_response(self._persist_id, self._turn_counter, response, request_summary)
        return response

    # ── Streaming path ─────────────────────────────────────────────

    async def _streaming_call(
        self, messages: list[dict], converted: list, tools: list[dict],
        request_summary: dict,
    ) -> object:
        from yak_browser_use.llm.client import serialize_messages
        from yak_browser_use.utils.response_logger import _log_streaming_response

        openai_messages = list(serialize_messages(converted))
        self._inject_tool_results(messages, openai_messages)

        client = self._llm.get_client()
        model_params = self._build_model_params()

        create_kwargs: dict = {
            "model": getattr(self._llm, "model", ""),
            "messages": openai_messages,
            "stream": True,
            **model_params,
        }
        if tools:
            create_kwargs["tools"] = tools

        self._streaming_active = True
        try:
            if self._on_stream_start:
                self._on_stream_start()

            stream = await client.chat.completions.create(**create_kwargs)

            content_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_calls_acc: dict[int, dict] = {}
            tool_names_seen: set[str] = set()
            last_chunk_usage = None
            last_chunk_model = None
            chunk_count = 0

            async for chunk in stream:
                chunk_count += 1
                if self._interrupt_check and chunk_count % 3 == 0 and self._interrupt_check():
                    try:
                        stream.close()
                    except Exception:
                        pass
                    break
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                reasoning = getattr(delta, "reasoning_content", None) or ""
                if reasoning:
                    thinking_parts.append(reasoning)
                    if self._on_reasoning_delta:
                        self._on_reasoning_delta(reasoning)

                if delta.content:
                    content_parts.append(delta.content)
                    if self._on_text_delta:
                        self._on_text_delta(delta.content)

                if delta.tool_calls:
                    self._accumulate_tool_calls(delta.tool_calls, tool_calls_acc, tool_names_seen)

                last_chunk_usage = chunk.usage if getattr(chunk, "usage", None) else last_chunk_usage
                last_chunk_model = getattr(chunk, "model", None) or last_chunk_model

            content = "".join(content_parts)
            thinking = "".join(thinking_parts)

            sorted_tc = sorted(tool_calls_acc.items(), key=lambda x: x[0])
            final_tool_calls = [tc for _, tc in sorted_tc]

            if self._on_stream_end:
                self._on_stream_end(bool(final_tool_calls))

            usage_dict: dict | None = None
            if last_chunk_usage is not None:
                usage_dict = {
                    "prompt_tokens": getattr(last_chunk_usage, "prompt_tokens", None),
                    "completion_tokens": getattr(last_chunk_usage, "completion_tokens", None),
                    "total_tokens": getattr(last_chunk_usage, "total_tokens", None),
                }
            _log_streaming_response(
                self._persist_id, self._turn_counter, create_kwargs,
                content, thinking, final_tool_calls,
                usage=usage_dict, model=last_chunk_model,
            )
        finally:
            self._streaming_active = False

        resp = SimpleNamespace()
        resp.content = content
        resp.tool_calls = final_tool_calls if final_tool_calls else None
        resp.thinking = thinking if thinking else None
        return resp

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _inject_tool_results(messages: list[dict], openai_messages: list) -> None:
        """Ensure ``tool``-role messages appear in the OpenAI-format list."""
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

    def _build_model_params(self) -> dict:
        model_params: dict = {}
        llm = self._llm
        if getattr(llm, "temperature", None) is not None:
            model_params["temperature"] = llm.temperature
        if getattr(llm, "frequency_penalty", None) is not None:
            model_params["frequency_penalty"] = llm.frequency_penalty
        if getattr(llm, "max_completion_tokens", None) is not None:
            model_params["max_completion_tokens"] = llm.max_completion_tokens
        if getattr(llm, "top_p", None) is not None:
            model_params["top_p"] = llm.top_p
        if getattr(llm, "seed", None) is not None:
            model_params["seed"] = llm.seed

        if getattr(llm, "reasoning_models", None) and any(
            str(m).lower() in str(getattr(llm, "model", "")).lower()
            for m in llm.reasoning_models
        ):
            model_params["reasoning_effort"] = getattr(llm, "reasoning_effort", None)
            model_params.pop("temperature", None)
            model_params.pop("frequency_penalty", None)

        return model_params

    @staticmethod
    def _accumulate_tool_calls(
        tool_calls_chunk,
        tool_calls_acc: dict[int, dict],
        tool_names_seen: set[str],
    ) -> None:
        """Accumulate streaming tool-call chunks into complete entries."""
        for tc in tool_calls_chunk:
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
                if tc.function.arguments:
                    entry["function"]["arguments"] += tc.function.arguments


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

    Returns a :class:`StreamingLLMCall` instance.  Kept as a standalone
    function for backward compatibility — new code can instantiate
    ``StreamingLLMCall`` directly.
    """
    return StreamingLLMCall(
        persist_id=persist_id,
        on_stream_start=on_stream_start,
        on_stream_end=on_stream_end,
        on_text_delta=on_text_delta,
        on_reasoning_delta=on_reasoning_delta,
        on_tool_generated=on_tool_generated,
        interrupt_check=interrupt_check,
    )



