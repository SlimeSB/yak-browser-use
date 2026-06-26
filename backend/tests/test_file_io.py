"""Tests for file_read, file_write, and read_data tools."""

import pytest
from pathlib import Path

from yak_browser_use.tools.file_read import file_read
from yak_browser_use.tools.file_write import file_write
from yak_browser_use.tools.read_data import read_data


def _cd_tmp(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return Path.cwd().resolve()


# ── file_read (still returns full content when called directly) ─


@pytest.mark.asyncio
async def test_file_read_text(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("line1\nline2\nline3\nline4\nline5", encoding="utf-8")
    result = await file_read("test.txt", head=3, max_chars=1000)
    assert result["ok"] is True
    assert "line1" in result["result"]
    assert "line2" in result["result"]
    assert "line3" in result["result"]
    assert "line4" not in result["result"]


@pytest.mark.asyncio
async def test_file_read_head_zero(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("a\nb\nc", encoding="utf-8")
    result = await file_read("test.txt", head=0, max_chars=1000)
    assert result["ok"] is True
    assert "a" in result["result"]
    assert "b" in result["result"]
    assert "c" in result["result"]


@pytest.mark.asyncio
async def test_file_read_max_chars(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("x" * 100, encoding="utf-8")
    result = await file_read("test.txt", head=0, max_chars=50)
    assert result["ok"] is True
    assert "已截断" in result["result"]


@pytest.mark.asyncio
async def test_file_read_gbk_fallback(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("中文内容", encoding="gbk")
    result = await file_read("test.txt", head=0, max_chars=1000)
    assert result["ok"] is True
    assert "中文内容" in result["result"]


@pytest.mark.asyncio
async def test_file_read_explicit_encoding(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("hello", encoding="utf-8")
    result = await file_read("test.txt", encoding="utf-8", head=0, max_chars=1000)
    assert result["ok"] is True
    assert "hello" in result["result"]


@pytest.mark.asyncio
async def test_file_read_binary_hint(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("data.xlsx").write_text("fake binary", encoding="utf-8")
    result = await file_read("data.xlsx")
    assert result["ok"] is False
    assert "二进制文件" in result["error"]
    assert result.get("suffix") == ".xlsx"


@pytest.mark.asyncio
async def test_file_read_not_found():
    result = await file_read("nonexistent_file.txt")
    assert result["ok"] is False
    assert "文件不存在" in result["error"]


# ── file_write (direct call — no sandbox) ─────────────────────


@pytest.mark.asyncio
async def test_file_write_basic(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    result = await file_write("output.txt", "hello world")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert Path("output.txt").read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_file_write_overwrite(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("output.txt").write_text("old", encoding="utf-8")
    result = await file_write("output.txt", "new")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert Path("output.txt").read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_file_write_auto_create_dir(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    result = await file_write("subdir/nested/output.txt", "nested content")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert Path("subdir/nested/output.txt").read_text(encoding="utf-8") == "nested content"


@pytest.mark.asyncio
async def test_file_write_encoding(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    result = await file_write("output.txt", "中文", encoding="gbk")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert Path("output.txt").read_text(encoding="gbk") == "中文"


# ── read_data ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_data_default_limit(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("\n".join(f"line{i}" for i in range(50)), encoding="utf-8")
    result = await read_data("test.txt")
    assert result["ok"] is True
    assert result["total_lines"] == 50
    assert len(result["result"].split("\n")) == 20


@pytest.mark.asyncio
async def test_read_data_with_offset(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("\n".join(f"line{i}" for i in range(50)), encoding="utf-8")
    result = await read_data("test.txt", limit=10, offset=20)
    assert result["ok"] is True
    assert result["total_lines"] == 50
    assert result["result"] == "\n".join(f"line{i}" for i in range(20, 30))


@pytest.mark.asyncio
async def test_read_data_offset_out_of_bounds(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("a\nb\nc", encoding="utf-8")
    result = await read_data("test.txt", offset=100)
    assert result["ok"] is False
    assert "offset" in result["error"]


@pytest.mark.asyncio
async def test_read_data_zero_limit(tmp_path, monkeypatch):
    result = await read_data("test.txt", limit=0)
    assert result["ok"] is False
    assert "limit" in result["error"]


@pytest.mark.asyncio
async def test_read_data_negative_limit(tmp_path, monkeypatch):
    result = await read_data("test.txt", limit=-1)
    assert result["ok"] is False
    assert "limit" in result["error"]


@pytest.mark.asyncio
async def test_read_data_negative_offset(tmp_path, monkeypatch):
    result = await read_data("test.txt", offset=-1)
    assert result["ok"] is False
    assert "offset" in result["error"]


@pytest.mark.asyncio
async def test_read_data_not_found():
    result = await read_data("nonexistent_file.txt")
    assert result["ok"] is False
    assert "不存在" in result["error"]


@pytest.mark.asyncio
async def test_read_data_source_key(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("hello world", encoding="utf-8")
    result = await read_data("test.txt", source_key="my_data")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_read_data_progressive_disclosure(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")
    result_first = await read_data("test.txt", limit=20, offset=0)
    assert result_first["ok"] is True
    assert "line0" in result_first["result"]
    assert "line19" in result_first["result"]

    result_second = await read_data("test.txt", limit=20, offset=20)
    assert result_second["ok"] is True
    assert "line20" in result_second["result"]
    assert "line39" in result_second["result"]


# ── convert_to ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_data_convert_to_xlsx_to_csv(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col1", "col2"])
    ws.append(["a", "b"])
    ws.append(["c", "d"])
    wb.save("data.xlsx")
    wb.close()

    result = await read_data("data.xlsx", convert_to="csv", limit=5)
    assert result["ok"] is True, f"convert_to 失败: {result.get('error', result)}"
    assert "col1" in result["result"]
    assert "a" in result["result"]


@pytest.mark.asyncio
async def test_read_data_convert_to_missing_file():
    result = await read_data("nonexistent.xlsx", convert_to="csv")
    assert result["ok"] is False
    # error comes from format_convert or file_read


@pytest.mark.asyncio
async def test_read_data_offset_exact_boundary(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("a\nb\nc", encoding="utf-8")
    result = await read_data("test.txt", offset=3)
    assert result["ok"] is False
    assert "offset" in result["error"]


@pytest.mark.asyncio
async def test_read_data_offset_zero_empty_file(tmp_path, monkeypatch):
    _cd_tmp(monkeypatch, tmp_path)
    Path("test.txt").write_text("", encoding="utf-8")
    result = await read_data("test.txt", offset=0)
    assert result["ok"] is True
    assert result["result"] == ""
    assert result["total_lines"] == 1  # 空文件 split("\n") 产生 1 个空元素


# ── convert_to with pipeline context ─────────────────────────

@pytest.mark.asyncio
async def test_read_data_convert_to_with_pipeline(tmp_path, monkeypatch):
    from yak_browser_use.workspace import manager
    from yak_browser_use.tools import _path_utils
    import openpyxl

    ws_root = tmp_path / "workspaces"
    ws_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(manager, "WORKSPACES_ROOT", ws_root)
    monkeypatch.setattr(_path_utils, "WORKSPACES_ROOT", ws_root)

    pipe_dir = ws_root / "my_pipe"
    pipe_dir.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["col1", "col2"])
    ws.append(["a", "b"])
    wb.save(str(pipe_dir / "data.xlsx"))
    wb.close()

    result = await read_data("data.xlsx", convert_to="csv", limit=5, pipeline="my_pipe")
    assert result["ok"] is True, f"convert_to with pipeline 失败: {result.get('error', result)}"
    assert "col1" in result["result"]
    assert "a" in result["result"]
