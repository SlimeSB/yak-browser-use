"""Tests for format_convert output_to parameter."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yak_browser_use.tools.registry import (
    ToolContext,
    _format_convert_handler,
)


@pytest.mark.asyncio
async def test_output_to_stores_absolute_path():
    with patch("yak_browser_use.tools.format_convert.format_convert", new_callable=AsyncMock) as mock_fc:
        mock_fc.return_value = {"ok": True, "result": "已转换", "target": "output.csv"}
        with patch("yak_browser_use.tools._path_utils.validate_path") as mock_vp:
            mock_vp.return_value = __file__  # any valid path
            ctx = ToolContext(shared_store={})
            result = await _format_convert_handler(
                {"source": "data.json", "target": "output.csv", "output_to": "csv_path"},
                ctx,
            )
            assert result["ok"] is True
            assert result["_output_to"] == "csv_path"
            assert ctx.shared_store["csv_path"] == str(__file__)


@pytest.mark.asyncio
async def test_source_json_output_to_stores_absolute_path():
    with patch("yak_browser_use.tools.format_convert.format_convert", new_callable=AsyncMock) as mock_fc:
        mock_fc.return_value = {"ok": True, "result": "已从内存数据转换", "target": "output.xlsx"}
        with patch("yak_browser_use.tools._path_utils.validate_path") as mock_vp:
            mock_vp.return_value = __file__
            ctx = ToolContext(shared_store={})
            result = await _format_convert_handler(
                {"source_json": [{"a": 1}], "target": "output.xlsx", "output_to": "xlsx_path"},
                ctx,
            )
            assert result["ok"] is True
            assert result["_output_to"] == "xlsx_path"
            assert ctx.shared_store["xlsx_path"] == str(__file__)


@pytest.mark.asyncio
async def test_failure_does_not_modify_store():
    with patch("yak_browser_use.tools.format_convert.format_convert", new_callable=AsyncMock) as mock_fc:
        mock_fc.return_value = {"ok": False, "error": "源文件不存在"}
        ctx = ToolContext(shared_store={"existing": "val"})
        result = await _format_convert_handler(
            {"source": "nonexistent.json", "target": "output.csv", "output_to": "result"},
            ctx,
        )
        assert result["ok"] is False
        assert "result" not in ctx.shared_store
        assert ctx.shared_store["existing"] == "val"


@pytest.mark.asyncio
async def test_no_output_to_does_not_modify_store():
    with patch("yak_browser_use.tools.format_convert.format_convert", new_callable=AsyncMock) as mock_fc:
        mock_fc.return_value = {"ok": True, "result": "已转换", "target": "data.json"}
        ctx = ToolContext(shared_store={"existing": "val"})
        result = await _format_convert_handler(
            {"source": "data.csv", "target": "data.json"},
            ctx,
        )
        assert result["ok"] is True
        assert "_output_to" not in result
        assert "existing" in ctx.shared_store
        assert len(ctx.shared_store) == 1
