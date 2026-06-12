"""Tool schemas (data structures)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolContext:
    """Context passed to tool functions during pipeline execution."""
    input_files: dict[str, str]
    output_dir: str
    params: dict[str, Any]
    cdp_helpers: Any = None
