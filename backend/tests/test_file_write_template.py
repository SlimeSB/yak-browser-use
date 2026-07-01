"""Tests for file_write {key} template replacement."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yak_browser_use.tools.registry import (
    ToolContext,
    _file_write_handler,
)


@pytest.mark.asyncio
async def test_template_replacement():
    ctx = ToolContext(shared_store={"csv_data": "a,b,c\n1,2,3"})
    with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = {"ok": True, "result": "ok"}
        result = await _file_write_handler(
            {"path": "out.csv", "content": "{csv_data}"},
            ctx,
        )
        assert result["ok"] is True
        mock_write.assert_called_once()
        assert mock_write.call_args.kwargs["content"] == '"a,b,c\\n1,2,3"'


@pytest.mark.asyncio
async def test_no_template_unchanged():
    ctx = ToolContext(shared_store={"x": "val"})
    with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = {"ok": True, "result": "ok"}
        result = await _file_write_handler(
            {"path": "note.txt", "content": "hello world"},
            ctx,
        )
        assert result["ok"] is True
        mock_write.assert_called_once()
        assert mock_write.call_args.kwargs["content"] == "hello world"


@pytest.mark.asyncio
async def test_missing_variable_keeps_original():
    ctx = ToolContext(shared_store={})
    with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = {"ok": True, "result": "ok"}
        result = await _file_write_handler(
            {"path": "out.txt", "content": "{nonexistent}"},
            ctx,
        )
        assert result["ok"] is True
        assert "_warnings" in result
        assert "nonexistent" in result["_warnings"][0]
        mock_write.assert_called_once()
        assert mock_write.call_args.kwargs["content"] == "{nonexistent}"


@pytest.mark.asyncio
async def test_mixed_static_and_template():
    ctx = ToolContext(shared_store={"summary": "data summary"})
    with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = {"ok": True, "result": "ok"}
        result = await _file_write_handler(
            {"path": "report.md", "content": "Header:\n{summary}\n---Footer---"},
            ctx,
        )
        assert result["ok"] is True
        content = mock_write.call_args.kwargs["content"]
        assert "Header:" in content
        assert '"data summary"' in content
        assert "---Footer---" in content


@pytest.mark.asyncio
async def test_no_shared_store_does_not_crash():
    ctx = ToolContext(shared_store=None)
    with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
        mock_write.return_value = {"ok": True, "result": "ok"}
        result = await _file_write_handler(
            {"path": "out.txt", "content": "{key}"},
            ctx,
        )
        assert result["ok"] is True
        mock_write.assert_called_once()
        assert mock_write.call_args.kwargs["content"] == "{key}"
