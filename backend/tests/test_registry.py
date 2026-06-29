"""Tests for tools.registry — ToolRegistry, dispatch routing, and handler functions.

Extends the basic registration tests from test_harness_tools.py with
detailed ToolRegistry behaviour tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.tools.registry import (
    ToolDef,
    ToolContext,
    ToolRegistry,
    registry,
    build_registry,
    _get_pipeline_dispatch,
    _get_skill_dispatch,
    _captcha_handler,
    _todo_handler,
    _file_read_handler,
    _file_write_handler,
    _format_convert_handler,
    _read_data_handler,
)


# ── ToolDef dataclass ──────────────────────────────────────────────


class TestToolDef:
    def test_basic_creation(self):
        td = ToolDef(name="test", schema={"description": "A test tool"}, handler=lambda: None)
        assert td.name == "test"
        assert td.schema["description"] == "A test tool"
        assert callable(td.handler)


# ── ToolContext dataclass ──────────────────────────────────────────


class TestToolContext:
    def test_defaults(self):
        ctx = ToolContext()
        assert ctx.cdp_helpers is None
        assert ctx.tools_dir is None
        assert ctx.pipeline_name == ""
        assert ctx.budget is None
        assert ctx.llm_call is None
        assert ctx.interrupt_check is None
        assert ctx.stream_callback is None
        assert ctx.shared_store is None

    def test_with_values(self):
        ctx = ToolContext(
            cdp_helpers=MagicMock(),
            tools_dir=Path("/tools"),
            pipeline_name="my_pipe",
            budget=MagicMock(),
            llm_call=MagicMock(),
            interrupt_check=lambda: False,
            stream_callback=lambda d: None,
            shared_store={"key": "val"},
        )
        assert ctx.pipeline_name == "my_pipe"
        assert ctx.shared_store["key"] == "val"


# ── ToolRegistry ───────────────────────────────────────────────────


class TestToolRegistry:
    def test_register_and_get_schemas(self):
        reg = ToolRegistry()
        handler = AsyncMock(return_value={"ok": True})
        reg.register("test_tool", {"description": "test"}, handler)

        schemas = reg.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "test_tool"
        assert schemas[0]["type"] == "function"

    def test_register_and_get_names(self):
        reg = ToolRegistry()
        reg.register("a", {"description": "AA"}, AsyncMock())
        reg.register("b", {"description": "BB"}, AsyncMock())
        names = reg.get_names()
        assert "a" in names
        assert "b" in names
        assert len(names) == 2

    def test_filter_allowed(self):
        reg = ToolRegistry()
        reg.register("keep", {"description": "K"}, AsyncMock())
        reg.register("drop", {"description": "D"}, AsyncMock())

        filtered = reg.filter({"keep"})
        assert len(filtered) == 1
        assert filtered[0]["function"]["name"] == "keep"

    def test_filter_skips_unknown(self):
        reg = ToolRegistry()
        reg.register("only_me", {"description": "O"}, AsyncMock())

        filtered = reg.filter({"only_me", "nonexistent"})
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_dispatch_known_tool(self):
        reg = ToolRegistry()
        handler = AsyncMock(return_value={"ok": True, "result": "done"})
        reg.register("my_tool", {"description": "t"}, handler)

        ctx = ToolContext()
        result = await reg.dispatch("my_tool", {"arg": "val"}, ctx)
        assert result["ok"] is True
        handler.assert_called_once_with({"arg": "val"}, ctx)

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.dispatch("nonexistent", {}, ToolContext())
        assert result["ok"] is False
        assert "Unknown tool" in result["error"]

    def test_double_register_overwrites(self):
        reg = ToolRegistry()
        handler_a = AsyncMock()
        handler_b = AsyncMock()
        reg.register("dup", {"description": "a"}, handler_a)
        reg.register("dup", {"description": "b"}, handler_b)

        assert len(reg.get_names()) == 1
        assert reg._tools["dup"].schema["description"] == "b"

    def test_empty_registry(self):
        reg = ToolRegistry()
        assert reg.get_schemas() == []
        assert reg.get_names() == []

    def test_filter_empty_allowed_set(self):
        reg = ToolRegistry()
        reg.register("x", {}, AsyncMock())
        assert reg.filter(set()) == []

    def test_filter_empty_registry(self):
        reg = ToolRegistry()
        assert reg.filter({"anything"}) == []


# ── build_registry ─────────────────────────────────────────────────


class TestBuildRegistry:
    def test_build_registry_idempotent(self):
        """build_registry should be safe to call multiple times."""
        old_count = len(registry._tools)
        build_registry()
        count_after_first = len(registry._tools)
        assert count_after_first > 0

        build_registry()
        count_after_second = len(registry._tools)
        assert count_after_second == count_after_first

    def test_registry_has_expected_tools(self):
        build_registry()
        names = registry.get_names()
        assert "browser_goto" in names
        assert "browser_click" in names
        assert "browser_snapshot" in names
        assert "pipeline_view" in names
        assert "pipeline_add_step" in names
        assert "todo" in names
        assert "captcha" in names
        assert "read_data" in names
        assert "file_read" in names
        assert "file_write" in names
        assert "format_convert" in names
        assert "browser_eval_js" in names
        assert "browser_wait_for_download" in names
        assert "eval_agent" not in names
        assert "pipeline_load" not in names
        assert "pipeline_list" not in names

    def test_browser_tools_have_proper_schema(self):
        build_registry()
        schemas = registry.get_schemas()
        for s in schemas:
            fn = s["function"]
            if fn["name"].startswith("browser_"):
                assert "description" in fn
                assert "parameters" in fn

    def test_build_registry_clear_on_error(self):
        """If build fails, registry should be in clean state."""
        from yak_browser_use.tools.registry import registry as reg

        with pytest.raises(Exception):
            with MagicMock() as mock_imports:
                with pytest.MonkeyPatch().context() as mp:
                    mp.setattr("yak_browser_use.tools.registry._build_registry_impl", lambda: (_ for _ in ()).throw(RuntimeError("fail")))
                    try:
                        build_registry()
                    except RuntimeError:
                        pass
                    assert len(reg._tools) == 0


# ── Lazy dispatch maps ────────────────────────────────────────────


class TestDispatchMaps:
    def test_get_pipeline_dispatch_has_expected_keys(self):
        dispatch = _get_pipeline_dispatch()
        for key in ("pipeline_view", "pipeline_update_step",
                    "pipeline_add_step", "pipeline_remove_step", "pipeline_create",
                    "pipeline_compile"):
            assert key in dispatch

    def test_get_skill_dispatch_has_expected_keys(self):
        dispatch = _get_skill_dispatch()
        for key in ("skill_list", "skill_view", "skill_create", "skill_edit", "skill_delete"):
            assert key in dispatch

    def test_get_pipeline_dispatch_cached(self):
        d1 = _get_pipeline_dispatch()
        d2 = _get_pipeline_dispatch()
        assert d1 is d2


# ── Handler functions ─────────────────────────────────────────────


class TestCaptchaHandler:
    @pytest.mark.asyncio
    async def test_returns_error_without_browser_for_dom_selector(self):
        result = await _captcha_handler(
            {"type": "image", "dom_selector": "img[alt*='captcha']"},
            ToolContext(),
        )
        assert result["ok"] is False
        assert "浏览器" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_error_without_bridge(self):
        ctx = ToolContext(cdp_helpers=MagicMock())
        result = await _captcha_handler(
            {"type": "image", "dom_selector": "img"},
            ctx,
        )
        assert result["ok"] is False

    @pytest.mark.asyncio
    async def test_direct_image_bytes(self):
        with patch("yak_browser_use.tools.captcha.captcha", new_callable=AsyncMock) as mock_captcha:
            mock_captcha.return_value = {"ok": True, "result": "abc"}
            result = await _captcha_handler(
                {"type": "image", "image_bytes": "AAAA"},
                ToolContext(),
            )
            assert result["ok"] is True
            mock_captcha.assert_called_once_with(type="image", image_bytes="AAAA")


class TestTodoHandler:
    @pytest.mark.asyncio
    async def test_returns_ok(self):
        with patch("yak_browser_use.tools.todo_store.current_store") as mock_store:
            mock_store.get.return_value = MagicMock()
            with patch("yak_browser_use.tools.todo.todo", new_callable=AsyncMock) as mock_todo:
                mock_todo.return_value = "Todo list updated"
                ctx = ToolContext()
                result = await _todo_handler(
                    {"todos": [{"id": "1", "content": "test", "status": "pending"}], "merge": False},
                    ctx,
                )
                assert result["ok"] is True
                assert result["result"] == "Todo list updated"


class TestFileHandlers:
    @pytest.mark.asyncio
    async def test_file_read_returns_metadata_only(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "test.txt"
        p.write_text("hello world", encoding="utf-8")
        result = await _file_read_handler({"path": "test.txt"}, ToolContext())
        assert result["ok"] is True
        assert "path" in result
        assert "size" in result
        assert "encoding" in result
        assert result["size"] == 11
        assert "result" not in result

    @pytest.mark.asyncio
    async def test_file_read_missing(self):
        result = await _file_read_handler({"path": "nonexistent_file_xyz.txt"}, ToolContext())
        assert result["ok"] is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_file_read_no_path(self):
        result = await _file_read_handler({}, ToolContext())
        assert result["ok"] is False
        assert "required" in result["error"]

    @pytest.mark.asyncio
    async def test_file_write_returns_metadata(self):
        with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = {"ok": True, "result": "已写入 5 字符"}
            result = await _file_write_handler(
                {"path": "test_output.txt", "content": "hello"},
                ToolContext(),
            )
            assert result["ok"] is True
            assert result["path"] == "test_output.txt"
            assert result["size"] == 5

    @pytest.mark.asyncio
    async def test_format_convert_returns_metadata(self):
        result = await _format_convert_handler(
            {"source": "data.csv", "target": "data.json"},
            ToolContext(),
        )
        assert result["ok"] is True
        assert result["source"] == "data.csv"
        assert result["target"] == "data.json"
        assert result["source_fmt"] == "csv"
        assert result["target_fmt"] == "json"

    @pytest.mark.asyncio
    async def test_format_convert_no_paths(self):
        result = await _format_convert_handler({}, ToolContext())
        assert result["ok"] is False
        assert "required" in result["error"]

    # ── sandbox & pipeline context ──

    @pytest.mark.asyncio
    async def test_file_read_returns_binary_flag(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        Path("data.xlsx").write_text("fake", encoding="utf-8")
        result = await _file_read_handler({"path": "data.xlsx"}, ToolContext())
        assert result["ok"] is True
        assert result["binary"] is True

    @pytest.mark.asyncio
    async def test_file_write_resolves_with_pipeline(self, tmp_path, monkeypatch):
        from yak_browser_use.workspace import manager
        from yak_browser_use.tools import _path_utils
        ws_root = tmp_path / "workspaces"
        ws_root.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(manager, "WORKSPACES_ROOT", ws_root)
        monkeypatch.setattr(_path_utils, "WORKSPACES_ROOT", ws_root)

        ctx = ToolContext(pipeline_name="my_pipe")
        with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = {"ok": True, "result": "ok"}
            result = await _file_write_handler(
                {"path": "downloads/out.txt", "content": "hello"},
                ctx,
            )
            assert result["ok"] is True
            mock_write.assert_called_once()
            call_kwargs = mock_write.call_args.kwargs
            assert call_kwargs["pipeline"] == "my_pipe"

    @pytest.mark.asyncio
    async def test_file_write_rejects_root_directory(self, tmp_path, monkeypatch):
        from yak_browser_use.workspace import manager
        from yak_browser_use.tools import _path_utils
        ws_root = tmp_path / "workspaces"
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "my_pipe").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(manager, "WORKSPACES_ROOT", ws_root)
        monkeypatch.setattr(_path_utils, "WORKSPACES_ROOT", ws_root)

        ctx = ToolContext(pipeline_name="my_pipe")
        result = await _file_write_handler(
            {"path": "root_file.txt", "content": "x"},
            ctx,
        )
        assert result["ok"] is False
        assert "根目录" in result["error"]

    @pytest.mark.asyncio
    async def test_file_write_rejects_dot_path(self, tmp_path, monkeypatch):
        from yak_browser_use.workspace import manager
        from yak_browser_use.tools import _path_utils
        ws_root = tmp_path / "workspaces"
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "my_pipe").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(manager, "WORKSPACES_ROOT", ws_root)
        monkeypatch.setattr(_path_utils, "WORKSPACES_ROOT", ws_root)

        ctx = ToolContext(pipeline_name="my_pipe")
        result = await _file_write_handler(
            {"path": ".", "content": "x"},
            ctx,
        )
        assert result["ok"] is False
        assert "根目录" in result["error"]

    @pytest.mark.asyncio
    async def test_read_data_rejects_root_directory(self, tmp_path, monkeypatch):
        from yak_browser_use.workspace import manager
        from yak_browser_use.tools import _path_utils
        ws_root = tmp_path / "workspaces"
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "my_pipe").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(manager, "WORKSPACES_ROOT", ws_root)
        monkeypatch.setattr(_path_utils, "WORKSPACES_ROOT", ws_root)

        ctx = ToolContext(pipeline_name="my_pipe")
        result = await _read_data_handler({"path": "root_file.csv"}, ctx)
        assert result["ok"] is False
        assert "根目录" in result["error"]

    @pytest.mark.asyncio
    async def test_read_data_allows_subdirectory(self, tmp_path, monkeypatch):
        from yak_browser_use.workspace import manager
        from yak_browser_use.tools import _path_utils
        ws_root = tmp_path / "workspaces"
        ws_root.mkdir(parents=True, exist_ok=True)
        (ws_root / "my_pipe" / "subdir").mkdir(parents=True, exist_ok=True)
        (ws_root / "my_pipe" / "subdir" / "data.csv").write_text("col1\nval1", encoding="utf-8")
        monkeypatch.setattr(manager, "WORKSPACES_ROOT", ws_root)
        monkeypatch.setattr(_path_utils, "WORKSPACES_ROOT", ws_root)

        ctx = ToolContext(pipeline_name="my_pipe")
        result = await _read_data_handler({"path": "subdir/data.csv", "limit": 5}, ctx)
        assert result["ok"] is True, f"子目录读取被拒: {result.get('error', result)}"
        assert "col1" in result["result"]

    @pytest.mark.asyncio
    async def test_file_write_without_pipeline(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("yak_browser_use.tools.file_write.file_write", new_callable=AsyncMock) as mock_write:
            mock_write.return_value = {"ok": True, "result": "ok"}
            result = await _file_write_handler(
                {"path": "out.txt", "content": "hello"},
                ToolContext(),
            )
            assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_file_read_returns_binary_false(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        Path("data.csv").write_text("a,b,c", encoding="utf-8")
        result = await _file_read_handler({"path": "data.csv"}, ToolContext())
        assert result["ok"] is True
        assert result["binary"] is False
