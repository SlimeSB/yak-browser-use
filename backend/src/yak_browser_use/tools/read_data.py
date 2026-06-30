"""read_data — unified data reading tool with progressive disclosure.

This is the ONLY tool that returns file content to the LLM. Internally
chains file_read → format_convert (if needed) → limit/offset truncation.
"""

from __future__ import annotations

import os
from pathlib import Path

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


async def read_data(
    path: str,
    limit: int = 20,
    offset: int = 0,
    encoding: str = "",
    convert_to: str = "",
    pipeline: str | None = None,
) -> dict:
    """Read data from a file with progressive disclosure.

    Args:
        path: File path to read.
        limit: Maximum number of lines to return (default 20, must be > 0).
        offset: Line number to start from (0-based, default 0).
        encoding: File encoding. Empty = auto-detect.
        convert_to: Convert binary file to this format before reading.
        pipeline: Pipeline name for workspace path resolution.

    Returns:
        {"ok": True, "result": "<content>", "total_lines": N, "path": "..."}
        or {"ok": False, "error": "..."}
    """
    if limit <= 0:
        return {"ok": False, "error": f"limit 必须大于 0（当前值: {limit}）"}
    if offset < 0:
        return {"ok": False, "error": f"offset 不能为负数（当前值: {offset}）"}

    if convert_to:
        from yak_browser_use.tools.format_convert import format_convert
        from yak_browser_use.workspace.manager import WORKSPACES_ROOT
        import uuid

        tmp_dir = ".read_data_tmp"
        tmp_file = f"conv_{uuid.uuid4().hex[:8]}.{convert_to}"
        tmp_rel = f"{tmp_dir}/{tmp_file}"

        if pipeline:
            (WORKSPACES_ROOT / pipeline / tmp_dir).mkdir(parents=True, exist_ok=True)
            tmp_abs = (WORKSPACES_ROOT / pipeline / tmp_rel).resolve()
        else:
            Path(tmp_dir).mkdir(parents=True, exist_ok=True)

        try:
            conv_result = await format_convert(source=path, target=tmp_rel, pipeline=pipeline)
            if not conv_result.get("ok"):
                return conv_result
            if pipeline:
                content = tmp_abs.read_text(encoding="utf-8")
            else:
                content = Path(tmp_rel).read_text(encoding="utf-8")
        finally:
            if pipeline:
                tmp_abs.unlink(missing_ok=True)
            else:
                try:
                    os.rmdir(tmp_dir)
                except OSError:
                    pass
                Path(tmp_rel).unlink(missing_ok=True)
    else:
        from yak_browser_use.tools.file_read import file_read

        read_result = await file_read(path=path, head=0, max_chars=10_000_000, encoding=encoding, pipeline=pipeline)
        if not read_result.get("ok"):
            return read_result
        content = read_result.get("result", "")

    lines = content.split("\n")
    total_lines = len(lines)

    if offset >= total_lines:
        return {"ok": False, "error": f"offset 超出文件行数（文件共 {total_lines} 行，offset={offset}）"}

    selected = lines[offset:offset + limit]
    result = "\n".join(selected)

    return {
        "ok": True,
        "result": result,
        "total_lines": total_lines,
        "path": path,
        "offset": offset,
        "limit": limit,
    }
