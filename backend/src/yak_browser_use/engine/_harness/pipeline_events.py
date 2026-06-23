"""Shared pipeline.edit event push — single source of truth for WebSocket events.

Replaces 4 ad-hoc implementations with one async function that
uses _EngineState.broadcast_event().  No diff_lines included
(the frontend computes its own diff from original + modified).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yak_browser_use.api.state import _EngineState


async def push_pipeline_edit_event(
    engine_state: _EngineState,
    *,
    edit_id: str,
    original: str,
    modified: str,
    explanation: str,
) -> dict:
    """Build and broadcast a pipeline.edit event, return the event dict.

    The caller is responsible for checkpoint management and edit_id
    generation (each caller has unique lifecycle rules).
    """
    event = {
        "type": "pipeline.edit",
        "edit_id": edit_id,
        "original": original,
        "modified": modified,
        "explanation": explanation,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    await engine_state.broadcast_event(event)
    return event
