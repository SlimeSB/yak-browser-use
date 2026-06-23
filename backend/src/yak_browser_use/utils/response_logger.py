from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any
from yak_browser_use.utils._path import project_root

logger = logging.getLogger("ybu.response_logger")

_RESPONSES_DIR = project_root() / "logs" / "llm"


def _ensure_dir() -> Path:
    _RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    return _RESPONSES_DIR


def log_llm_response(
    persist_id: str,
    turn: int,
    mode: str,
    request_summary: dict[str, Any],
    response_meta: dict[str, Any],
    content_length: int,
    tool_calls_count: int,
    thinking_length: int = 0,
) -> None:
    if not persist_id:
        logger.debug("LLM response (no persist_id): %s", response_meta)
        return
    record = {
        "ts": time.time(),
        "turn": turn,
        "persist_id": persist_id,
        "mode": mode,
        "request": request_summary,
        "response": response_meta,
        "content_length": content_length,
        "tool_calls_count": tool_calls_count,
        "thinking_length": thinking_length,
    }
    try:
        log_dir = _ensure_dir()
        log_path = log_dir / f"{persist_id}.jsonl"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to write LLM response log for %s", persist_id)


def _log_non_streaming_response(
    persist_id: str,
    turn: int,
    response: Any,
    request_summary: dict[str, Any],
) -> None:
    content = getattr(response, "completion", "") or ""
    tool_calls = getattr(response, "tool_calls", None) or []

    usage = getattr(response, "usage", None)
    usage_dict: dict[str, Any] = {}
    if usage is not None:
        usage_dict = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    response_meta: dict[str, Any] = {
        "id": getattr(response, "id", None),
        "model": getattr(response, "model_name", None),
        "usage": usage_dict,
        "finish_reason": getattr(response, "stop_reason", None),
    }

    log_llm_response(
        persist_id=persist_id,
        turn=turn,
        mode="non-streaming",
        request_summary=request_summary,
        response_meta=response_meta,
        content_length=len(content),
        tool_calls_count=len(tool_calls),
    )


def _log_streaming_response(
    persist_id: str,
    turn: int,
    create_kwargs: dict[str, Any],
    content: str,
    thinking: str,
    final_tool_calls: list[dict],
    usage: dict | None,
    model: str | None,
) -> None:
    response_meta: dict[str, Any] = {
        "id": None,
        "model": model,
        "usage": usage or {},
        "finish_reason": None,
    }
    request_summary = {
        "model": create_kwargs.get("model", model or "unknown"),
        "messages_count": len(create_kwargs.get("messages", [])),
        "tools_count": len(create_kwargs.get("tools", [])),
    }
    log_llm_response(
        persist_id=persist_id,
        turn=turn,
        mode="streaming",
        request_summary=request_summary,
        response_meta=response_meta,
        content_length=len(content),
        tool_calls_count=len(final_tool_calls),
        thinking_length=len(thinking),
    )
