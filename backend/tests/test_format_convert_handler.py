"""Tests for _format_convert_handler — now actually calls format_convert()."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from yak_browser_use.tools.registry import (
    ToolContext,
    _format_convert_handler,
)


@pytest.mark.asyncio
async def test_handler_calls_format_convert():
    with patch("yak_browser_use.tools.format_convert.format_convert", new_callable=AsyncMock) as mock_fc:
        mock_fc.return_value = {"ok": True, "result": "已转换 data.csv → data.json（csv → json）", "target": "data.json"}
        result = await _format_convert_handler(
            {"source": "data.csv", "target": "data.json"},
            ToolContext(),
        )
        assert result["ok"] is True
        mock_fc.assert_called_once()
        kwargs = mock_fc.call_args.kwargs
        assert kwargs["source"] == "data.csv"
        assert kwargs["target"] == "data.json"
        assert kwargs["pipeline"] is None


@pytest.mark.asyncio
async def test_handler_no_source():
    result = await _format_convert_handler({}, ToolContext())
    assert result["ok"] is False
    assert "required" in result["error"]


@pytest.mark.asyncio
async def test_handler_with_source_json():
    with patch("yak_browser_use.tools.format_convert.format_convert", new_callable=AsyncMock) as mock_fc:
        mock_fc.return_value = {"ok": True, "result": "已从内存数据转换 → out.csv（csv）", "target": "out.csv"}
        result = await _format_convert_handler(
            {"source_json": [{"a": 1}], "target": "out.csv", "target_fmt": "csv"},
            ToolContext(),
        )
        assert result["ok"] is True
        mock_fc.assert_called_once()
        kwargs = mock_fc.call_args.kwargs
        assert kwargs["source_json"] == [{"a": 1}]
