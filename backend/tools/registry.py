"""ToolRegistry — registers and looks up BaseTool subclasses."""
from __future__ import annotations

from typing import Any

from tools.base import BaseTool
from utils.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for BaseTool classes used by the browser-use Agent."""

    _tools: dict[str, type[BaseTool]] = {}

    @classmethod
    def register(cls, tool_cls: type[BaseTool]) -> type[BaseTool]:
        name = getattr(tool_cls, "name", None) or tool_cls.__name__
        cls._tools[name] = tool_cls
        logger.debug("tool registered: %s", name)
        return tool_cls

    @classmethod
    def get(cls, name: str) -> type[BaseTool] | None:
        return cls._tools.get(name)

    @classmethod
    def list_all(cls) -> list[str]:
        return list(cls._tools.keys())
