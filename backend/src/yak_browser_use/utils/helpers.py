"""Miscellaneous shared helpers — validation, result formatting."""

from __future__ import annotations

import os


def sanitize_pipeline_name(pipeline_name: str) -> str:
    """Validate and sanitize *pipeline_name*, returning the safe basename.

    Raises ``ValueError`` if the name contains path separators or is empty.
    """
    safe = os.path.basename(pipeline_name.replace("\\", "/"))
    if not safe or safe != pipeline_name.replace("\\", "/"):
        raise ValueError(f"Invalid pipeline name: {pipeline_name}")
    return safe


def prepend_resolve_errors(result: dict, resolve_errors: list[str]) -> None:
    """Prepend parameter-template resolve errors to a tool *result* dict, mutating in-place.

    When *resolve_errors* is empty the call is a no-op.
    """
    if not resolve_errors:
        return
    warning = f"\u26a0\ufe0f \u53c2\u6570\u6a21\u677f\u89e3\u6790\u5931\u8d25: {resolve_errors}"
    if result.get("ok"):
        existing = result.get("result", "")
        if isinstance(existing, str):
            result["result"] = warning + "\n\n" + existing
        else:
            result["result"] = warning
    else:
        existing = result.get("error", "")
        result["error"] = warning + "\n\n" + existing


def build_snapshot_summary(elements: list[dict], url: str, title: str) -> str:
    """从 elements 列表构建中文摘要文本，供 LLM 阅读。

    输入为独立的 elements 列表、url 字符串、title 字符串，
    输出格式与原 scratchpad._build_summary 等价。
    """
    lines: list[str] = []

    if title:
        lines.append(f"页面标题: {title}")
    if url:
        lines.append(f"页面URL: {url}")

    el_count = len(elements)
    if el_count > 0:
        lines.append(f"{el_count}个可交互元素:")
        for el in elements:
            ref = el.get("ref", "")
            tag = el.get("tag", "")
            el_type = el.get("type", "")
            text = el.get("text", "")
            sel = el.get("selector", "")

            parts: list[str] = [ref, f"<{tag}"]
            if el_type:
                parts.append(f' type="{el_type}"')
            parts.append(">")

            if text:
                text_escaped = text.replace('"', '\\"')
                parts.append(f' "{text_escaped}"')
            parts.append(f" {sel}")

            lines.append("".join(parts))

    if not lines:
        return "页面快照已获取"

    return "\n".join(lines)
