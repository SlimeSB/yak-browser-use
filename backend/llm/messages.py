"""Vendored LLM message types — minimal replacement for browser_use.llm.messages."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str = ""
    type: str = "function"
    function: dict = field(default_factory=dict)


@dataclass
class SystemMessage:
    content: str
    role: str = "system"


@dataclass
class UserMessage:
    content: str
    role: str = "user"


@dataclass
class AssistantMessage:
    content: str = ""
    role: str = "assistant"
    tool_calls: list[ToolCall] | None = None
