"""Engine utilities for pipeline execution and recovery."""
from __future__ import annotations

import json


def truncate_step_result(result: dict, max_chars: int = 10000) -> dict:
    """Truncate step result values to prevent oversized recovery prompts."""
    truncated = {}
    for k, v in result.items():
        try:
            text = json.dumps(v, ensure_ascii=False, default=str)
            if len(text) > max_chars:
                truncated[k] = text[:max_chars] + "...[truncated]"
            else:
                truncated[k] = v
        except Exception:
            truncated[k] = v
    return truncated
