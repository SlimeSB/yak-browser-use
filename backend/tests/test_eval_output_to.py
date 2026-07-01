"""Tests for browser_eval_js script_file, output_to, and return_format features."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from yak_browser_use.tools.registry import (
    ToolContext,
    build_registry,
    registry,
)


@pytest.fixture(autouse=True)
def _ensure_registry():
    build_registry()
    yield


def _patch_workspace(tmp_path: Path):
    """Patch WORKSPACES_ROOT in _path_utils to point at tmp_path."""
    import yak_browser_use.tools._path_utils as pu
    pu.WORKSPACES_ROOT = tmp_path


def _make_ctx(shared_store: dict | None = None, tmp_dir: Path | None = None) -> ToolContext:
    bridge = MagicMock()
    bridge.evaluate = AsyncMock()
    cdp = MagicMock()
    cdp.bridge = bridge
    ctx = ToolContext(cdp_helpers=cdp, shared_store=shared_store or {})
    if tmp_dir:
        ctx.pipeline_name = "__test__"
        (tmp_dir / "__test__").mkdir(exist_ok=True)
    return ctx


@pytest.mark.asyncio
async def test_script_file_executes(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "extract.js"
    js_file.write_text("document.title", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(tmp_dir=tmp_path)
    result = await registry.dispatch("browser_eval_js", {"script_file": "extract.js"}, ctx)
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_script_file_not_found(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(tmp_dir=tmp_path)
    result = await registry.dispatch("browser_eval_js", {"script_file": "nonexistent.js"}, ctx)
    assert result["ok"] is False
    assert "不存在" in result["error"]


@pytest.mark.asyncio
async def test_missing_script_file_param():
    ctx = _make_ctx()
    result = await registry.dispatch("browser_eval_js", {}, ctx)
    assert result["ok"] is False
    assert "script_file" in result["error"]


@pytest.mark.asyncio
async def test_output_to_stores_in_shared_store(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("42", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(shared_store={}, tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = 42
    result = await registry.dispatch("browser_eval_js", {"script_file": "script.js", "output_to": "my_var"}, ctx)
    assert result["ok"] is True
    assert ctx.shared_store["my_var"] == 42


@pytest.mark.asyncio
async def test_output_to_not_provided_does_not_modify_store(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("99", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(shared_store={"existing": "val"}, tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = 99
    result = await registry.dispatch("browser_eval_js", {"script_file": "script.js"}, ctx)
    assert result["ok"] is True
    assert "existing" in ctx.shared_store
    assert "my_var" not in ctx.shared_store


@pytest.mark.asyncio
async def test_return_format_raw(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("42", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = 42
    result = await registry.dispatch("browser_eval_js", {"script_file": "script.js", "return_format": "raw"}, ctx)
    assert result["ok"] is True
    assert result["result"] == 42


@pytest.mark.asyncio
async def test_return_format_json(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("[1,2,3]", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = [1, 2, 3]
    result = await registry.dispatch("browser_eval_js", {"script_file": "script.js", "return_format": "json"}, ctx)
    assert result["ok"] is True
    assert result["result"] == "[1, 2, 3]"


@pytest.mark.asyncio
async def test_return_format_csv_array_of_dicts(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("data", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    result = await registry.dispatch("browser_eval_js", {"script_file": "script.js", "return_format": "csv"}, ctx)
    assert result["ok"] is True
    csv_text = result["result"]
    assert "Alice" in csv_text
    assert "Bob" in csv_text


@pytest.mark.asyncio
async def test_return_format_csv_non_array_fallback(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("'hello'", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = "hello"
    result = await registry.dispatch("browser_eval_js", {"script_file": "script.js", "return_format": "csv"}, ctx)
    assert result["ok"] is True
    assert "requires array" in result["result"]


@pytest.mark.asyncio
async def test_output_to_and_return_format_together(tmp_path, monkeypatch):
    (tmp_path / "__test__").mkdir(exist_ok=True)
    js_file = tmp_path / "__test__" / "script.js"
    js_file.write_text("data", encoding="utf-8")
    monkeypatch.setattr("yak_browser_use.tools._path_utils.WORKSPACES_ROOT", tmp_path)
    ctx = _make_ctx(shared_store={}, tmp_dir=tmp_path)
    ctx.cdp_helpers.bridge.evaluate.return_value = [{"x": 1}]
    result = await registry.dispatch(
        "browser_eval_js",
        {"script_file": "script.js", "output_to": "my_data", "return_format": "csv"},
        ctx,
    )
    assert result["ok"] is True
    assert "my_data" in ctx.shared_store
    assert ctx.shared_store["my_data"] == [{"x": 1}]
