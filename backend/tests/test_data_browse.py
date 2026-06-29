"""Tests for data_keys and data_browse tools — shared_store introspection handlers."""

from __future__ import annotations

import pytest

from yak_browser_use.tools.registry import (
    ToolContext,
    _data_keys_handler,
    _data_browse_handler,
)


class TestDataKeysHandler:
    @pytest.mark.asyncio
    async def test_returns_keys_with_types_and_sizes(self):
        ctx = ToolContext(shared_store={
            "elements": [{"ref": "e1"}, {"ref": "e2"}],
            "config": {"timeout": 30},
            "title": "hello world",
            "flag": True,
        })
        result = await _data_keys_handler({}, ctx)
        assert result["ok"] is True
        keys = {k["name"]: k for k in result["keys"]}
        assert keys["elements"] == {"name": "elements", "type": "list", "size": 2}
        assert keys["config"] == {"name": "config", "type": "dict", "size": 1}
        assert keys["title"] == {"name": "title", "type": "str", "size": 11}
        assert keys["flag"] == {"name": "flag", "type": "other", "size": 0}

    @pytest.mark.asyncio
    async def test_empty_store(self):
        ctx = ToolContext(shared_store={})
        result = await _data_keys_handler({}, ctx)
        assert result["ok"] is True
        assert result["keys"] == []

    @pytest.mark.asyncio
    async def test_none_store(self):
        ctx = ToolContext(shared_store=None)
        result = await _data_keys_handler({}, ctx)
        assert result["ok"] is False
        assert "shared_store 不可用" in result["error"]


class TestDataBrowseHandler:
    @pytest.mark.asyncio
    async def test_browse_element_list(self):
        ctx = ToolContext(shared_store={
            "elements": [
                {"ref": "@e_0", "tag": "button", "text": "Submit", "selector": "#btn"},
                {"ref": "@e_1", "tag": "a", "text": "Link", "selector": ".link"},
            ],
        })
        result = await _data_browse_handler({"key": "elements"}, ctx)
        assert result["ok"] is True
        assert result["key"] == "elements"
        assert result["total"] == 2
        assert result["offset"] == 0
        assert result["limit"] == 20
        assert len(result["items"]) == 2
        assert "@e_0" in result["items"][0]
        assert "button" in result["items"][0]

    @pytest.mark.asyncio
    async def test_browse_string(self):
        ctx = ToolContext(shared_store={"html": "hello world foo bar baz"})
        result = await _data_browse_handler({"key": "html", "limit": 5}, ctx)
        assert result["ok"] is True
        assert result["preview"] == "hello"
        assert result["total"] == 23
        assert result["offset"] == 0
        assert result["limit"] == 5

    @pytest.mark.asyncio
    async def test_browse_dict(self):
        ctx = ToolContext(shared_store={"cfg": {"a": 1, "b": 2}})
        result = await _data_browse_handler({"key": "cfg"}, ctx)
        assert result["ok"] is True
        assert "keys" in result
        assert "a" in result["keys"]
        assert "b" in result["keys"]
        assert "preview" in result

    @pytest.mark.asyncio
    async def test_key_not_found(self):
        ctx = ToolContext(shared_store={"x": 1})
        result = await _data_browse_handler({"key": "nonexistent"}, ctx)
        assert result["ok"] is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_offset_out_of_range(self):
        ctx = ToolContext(shared_store={"elements": [{"ref": "e1"}]})
        result = await _data_browse_handler({"key": "elements", "offset": 100}, ctx)
        assert result["ok"] is True
        assert result["items"] == []
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_none_store(self):
        ctx = ToolContext(shared_store=None)
        result = await _data_browse_handler({"key": "x"}, ctx)
        assert result["ok"] is False
        assert "shared_store 不可用" in result["error"]

    @pytest.mark.asyncio
    async def test_limit_capped_at_100(self):
        ctx = ToolContext(shared_store={"items": list(range(200))})
        result = await _data_browse_handler({"key": "items", "limit": 999}, ctx)
        assert result["ok"] is True
        assert result["limit"] == 100
        assert len(result["items"]) == 100

    @pytest.mark.asyncio
    async def test_browse_non_element_list(self):
        ctx = ToolContext(shared_store={"nums": [1, 2, 3]})
        result = await _data_browse_handler({"key": "nums"}, ctx)
        assert result["ok"] is True
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_negative_offset_clamped_to_zero(self):
        ctx = ToolContext(shared_store={"elements": [{"ref": "e1"}, {"ref": "e2"}]})
        result = await _data_browse_handler({"key": "elements", "offset": -5}, ctx)
        assert result["ok"] is True
        assert result["offset"] == 0
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_zero_limit_clamped_to_one(self):
        ctx = ToolContext(shared_store={"elements": [{"ref": "e1"}, {"ref": "e2"}]})
        result = await _data_browse_handler({"key": "elements", "limit": 0}, ctx)
        assert result["ok"] is True
        assert result["limit"] == 1
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_negative_limit_clamped_to_one(self):
        ctx = ToolContext(shared_store={"elements": [{"ref": "e1"}, {"ref": "e2"}]})
        result = await _data_browse_handler({"key": "elements", "limit": -10}, ctx)
        assert result["ok"] is True
        assert result["limit"] == 1
        assert len(result["items"]) == 1
