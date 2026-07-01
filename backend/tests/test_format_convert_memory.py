"""Tests for format_convert source_json parameter."""
from __future__ import annotations

import csv
import json

import openpyxl
import pytest
from pathlib import Path

from yak_browser_use.tools.format_convert import format_convert


@pytest.mark.asyncio
async def test_source_json_to_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    result = await format_convert(source_json=data, target="output.csv", target_fmt="csv")
    assert result["ok"] is True
    assert Path("output.csv").exists()
    with open("output.csv", "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["name"] == "Alice"
    assert rows[1]["name"] == "Bob"


@pytest.mark.asyncio
async def test_source_json_to_xlsx(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = [{"a": 1}]
    result = await format_convert(source_json=data, target="output.xlsx", target_fmt="xlsx")
    assert result["ok"] is True
    assert Path("output.xlsx").exists()
    wb = openpyxl.load_workbook("output.xlsx", read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == ("a",)
    assert rows[1] == (1,)
    wb.close()


@pytest.mark.asyncio
async def test_source_json_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data.json").write_text(json.dumps([{"x": "old"}]), encoding="utf-8")
    data = [{"x": "new"}]
    result = await format_convert(
        source="data.json", source_json=data, target="output.csv", target_fmt="csv",
    )
    assert result["ok"] is True
    assert "_note" in result
    assert "precedence" in result["_note"]
    with open("output.csv", "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["x"] == "new"


@pytest.mark.asyncio
async def test_source_json_not_provided_uses_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("data.json").write_text(json.dumps([{"val": "from_file"}]), encoding="utf-8")
    result = await format_convert(source="data.json", target="output.csv", target_fmt="csv")
    assert result["ok"] is True
    with open("output.csv", "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["val"] == "from_file"


@pytest.mark.asyncio
async def test_source_json_empty_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await format_convert(source_json=[], target="empty.csv", target_fmt="csv")
    assert result["ok"] is True
    assert Path("empty.csv").exists()
    assert Path("empty.csv").read_text(encoding="utf-8-sig") == ""
