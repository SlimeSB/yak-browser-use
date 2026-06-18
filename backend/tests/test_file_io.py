"""Tests for file_read and file_write tools."""

import pytest
from pathlib import Path

from tools.file_read import file_read
from tools.file_write import file_write


@pytest.mark.asyncio
async def test_file_read_text(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("line1\nline2\nline3\nline4\nline5", encoding="utf-8")
    result = await file_read(str(p), head=3, max_chars=1000)
    assert result["ok"] is True
    assert "line1" in result["result"]
    assert "line2" in result["result"]
    assert "line3" in result["result"]
    assert "line4" not in result["result"]


@pytest.mark.asyncio
async def test_file_read_head_zero(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("a\nb\nc", encoding="utf-8")
    result = await file_read(str(p), head=0, max_chars=1000)
    assert result["ok"] is True
    assert "a" in result["result"]
    assert "b" in result["result"]
    assert "c" in result["result"]


@pytest.mark.asyncio
async def test_file_read_max_chars(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("x" * 100, encoding="utf-8")
    result = await file_read(str(p), head=0, max_chars=50)
    assert result["ok"] is True
    assert "已截断" in result["result"]


@pytest.mark.asyncio
async def test_file_read_gbk_fallback(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("中文内容", encoding="gbk")
    result = await file_read(str(p), head=0, max_chars=1000)
    assert result["ok"] is True
    assert "中文内容" in result["result"]


@pytest.mark.asyncio
async def test_file_read_explicit_encoding(tmp_path):
    p = tmp_path / "test.txt"
    p.write_text("hello", encoding="utf-8")
    result = await file_read(str(p), encoding="utf-8", head=0, max_chars=1000)
    assert result["ok"] is True
    assert "hello" in result["result"]


@pytest.mark.asyncio
async def test_file_read_binary_hint(tmp_path):
    p = tmp_path / "data.xlsx"
    p.write_text("fake binary", encoding="utf-8")
    result = await file_read(str(p))
    assert result["ok"] is False
    assert "二进制文件" in result["error"]
    assert result.get("suffix") == ".xlsx"


@pytest.mark.asyncio
async def test_file_read_not_found():
    result = await file_read("nonexistent_file.txt")
    assert result["ok"] is False
    assert "文件不存在" in result["error"]


@pytest.mark.asyncio
async def test_file_write_basic(tmp_path):
    p = tmp_path / "output.txt"
    result = await file_write(str(p), "hello world")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert p.read_text(encoding="utf-8") == "hello world"


@pytest.mark.asyncio
async def test_file_write_overwrite(tmp_path):
    p = tmp_path / "output.txt"
    p.write_text("old", encoding="utf-8")
    result = await file_write(str(p), "new")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert p.read_text(encoding="utf-8") == "new"


@pytest.mark.asyncio
async def test_file_write_auto_create_dir(tmp_path):
    p = tmp_path / "subdir" / "nested" / "output.txt"
    result = await file_write(str(p), "nested content")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert p.read_text(encoding="utf-8") == "nested content"


@pytest.mark.asyncio
async def test_file_write_encoding(tmp_path):
    p = tmp_path / "output.txt"
    result = await file_write(str(p), "中文", encoding="gbk")
    assert result["ok"] is True
    assert "已写入" in result["result"]
    assert p.read_text(encoding="gbk") == "中文"
