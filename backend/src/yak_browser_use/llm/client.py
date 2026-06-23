"""LLMClient — adapter over AsyncOpenAI, replacing browser-use's ChatOpenAI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from yak_browser_use.llm.messages import AssistantMessage, SystemMessage, UserMessage
from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)

_REASONING_MODELS = [
    "o4-mini", "o3", "o3-mini", "o1", "o1-pro",
    "o3-pro", "gpt-5", "gpt-5-mini", "gpt-5-nano",
]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[dict] | None = None
    reasoning: str | None = None
    model_name: str = ""
    stop_reason: str = ""
    usage: dict | None = None
    id: str | None = None

    @property
    def completion(self) -> str:
        return self.content


def serialize_messages(messages: list) -> list[dict]:
    """Serialize vendored message dataclasses to OpenAI-compatible dicts."""
    result: list[dict] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            entry: dict = {"role": "assistant"}
            if msg.content:
                entry["content"] = msg.content
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.get("name", ""),
                            "arguments": tc.function.get("arguments", ""),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            result.append(entry)
        else:
            raise ValueError(f"Unknown message type: {type(msg)}")
    return result


class LLMClient:
    def __init__(
        self,
        model: str = "gpt-4o",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = 0.2,
        frequency_penalty: float | None = 0.3,
        max_completion_tokens: int | None = 4096,
        max_retries: int = 5,
        top_p: float | None = None,
        seed: int | None = None,
        reasoning_models: list[str] | None = None,
        reasoning_effort: str = "low",
    ):
        self.model = model
        self.temperature = temperature
        self.frequency_penalty = frequency_penalty
        self.max_completion_tokens = max_completion_tokens
        self.max_retries = max_retries
        self.top_p = top_p
        self.seed = seed
        self.reasoning_models = reasoning_models or _REASONING_MODELS
        self.reasoning_effort = reasoning_effort

        client_kwargs: dict = {"max_retries": max_retries}
        if api_key:
            client_kwargs["api_key"] = api_key
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)

    def get_client(self) -> AsyncOpenAI:
        return self._client

    async def ainvoke(
        self,
        messages: list,
        *,
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        openai_messages = serialize_messages(messages)

        model_params: dict[str, Any] = {}

        if self.temperature is not None:
            model_params["temperature"] = self.temperature
        if self.frequency_penalty is not None:
            model_params["frequency_penalty"] = self.frequency_penalty
        if self.max_completion_tokens is not None:
            model_params["max_completion_tokens"] = self.max_completion_tokens
        if self.top_p is not None:
            model_params["top_p"] = self.top_p
        if self.seed is not None:
            model_params["seed"] = self.seed

        if self.reasoning_models and any(
            str(m).lower() in str(self.model).lower() for m in self.reasoning_models
        ):
            model_params["reasoning_effort"] = self.reasoning_effort
            model_params.pop("temperature", None)
            model_params.pop("frequency_penalty", None)

        create_kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            **model_params,
        }
        if tools is not None:
            create_kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**create_kwargs)

        choice = response.choices[0] if response.choices else None
        if choice is None:
            raise RuntimeError("OpenAI returned empty choices")

        content = choice.message.content or ""

        tool_calls: list[dict] | None = None
        if choice.message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        reasoning = getattr(choice.message, "reasoning_content", None)

        usage: dict | None = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning,
            model_name=response.model or "",
            stop_reason=choice.finish_reason or "",
            usage=usage,
            id=response.id,
        )
