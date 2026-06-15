"""BaseTool abstract class for browser-use Agent tools."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Base class for tools that the browser-use Agent can invoke."""

    name: str = ""
    description: str = ""
    agent_compatible: bool = True

    @classmethod
    @abstractmethod
    async def execute(cls, browser: object, **kwargs: Any) -> Any:
        ...
