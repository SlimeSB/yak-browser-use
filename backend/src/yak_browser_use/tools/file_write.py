"""file_write — write text content to a file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yak_browser_use.tools._path_utils import validate_path

_MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10 MB


async def file_write(
    path: str,
    content: str,
    encoding: str = "utf-8",
    pipeline: str | None = None,
) -> dict[str, Any]:
    """Write text content to a file.

    Args:
        path: File path to write.
        content: Text content to write.
        encoding: File encoding (default: utf-8).
        pipeline: Pipeline name for workspace path resolution.

    Returns:
        {"ok": True, "result": "<message>"} or {"ok": False, "error": "<message>"}
    """
    if len(content) > _MAX_CONTENT_SIZE:
        return {"ok": False, "error": f"内容过大（{len(content)} 字符），最大允许 {_MAX_CONTENT_SIZE} 字符"}

    try:
        p = validate_path(path, pipeline=pipeline)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=encoding)
        return {"ok": True, "result": f"已写入 {len(content)} 字符到 {path}"}
    except PermissionError:
        return {"ok": False, "error": f"权限不足，无法写入文件: {path}"}
    except OSError as e:
        return {"ok": False, "error": f"文件写入失败（操作系统错误）: {e}"}
    except UnicodeEncodeError as e:
        return {"ok": False, "error": f"编码错误（{encoding}）: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"写入失败 — {e}"}
