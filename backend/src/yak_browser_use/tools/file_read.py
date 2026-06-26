"""file_read — read text file content, with encoding auto-detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yak_browser_use.tools._path_utils import validate_path

_BINARY_EXTENSIONS = frozenset({
    ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".gif", ".bmp",
    ".pdf", ".zip", ".tar", ".gz", ".exe", ".dll", ".so",
    ".mp3", ".mp4", ".avi", ".mov", ".webp", ".ico", ".svg",
    ".doc", ".docx", ".ppt", ".pptx", ".xlsm", ".7z", ".rar",
    ".wav", ".flac", ".mkv", ".woff", ".woff2", ".ttf", ".eot",
})


async def file_read(
    path: str,
    head: int = 20,
    max_chars: int = 3000,
    encoding: str = "",
    pipeline: str | None = None,
) -> dict[str, Any]:
    """Read a text file and return its content.

    Args:
        path: File path to read.
        head: Return first N lines (0 = all lines).
        max_chars: Maximum characters to return.
        encoding: File encoding. Empty = auto-detect (UTF-8 → GBK fallback).
        pipeline: Pipeline name for downloads/ prefix resolution.

    Returns:
        {"ok": True, "result": "<content>"} or {"ok": False, "error": "<message>"}
    """
    try:
        p = validate_path(path, pipeline=pipeline)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    suffix = p.suffix.lower()
    if suffix in _BINARY_EXTENSIONS:
        return {"ok": False, "error": f"二进制文件（{suffix}），请使用 format_convert 工具处理", "suffix": suffix}

    if not p.exists():
        return {"ok": False, "error": f"文件不存在 — {path}"}
    if not p.is_file():
        return {"ok": False, "error": f"路径不是文件 — {path}"}

    if encoding:
        try:
            content = p.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError) as e:
            return {"ok": False, "error": f"无法以编码 {encoding} 读取文件 — {e}"}
    else:
        try:
            content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = p.read_text(encoding="gbk")
            except UnicodeDecodeError as e:
                return {"ok": False, "error": f"无法自动检测编码（UTF-8 和 GBK 均失败）— {e}"}

    lines = content.split("\n")
    if head > 0 and len(lines) > head:
        content = "\n".join(lines[:head])

    if len(content) > max_chars:
        total = len(content)
        content = content[:max_chars]
        content += f"\n\n...（已截断，共 {total - max_chars} 字符未显示）"

    return {"ok": True, "result": content}
