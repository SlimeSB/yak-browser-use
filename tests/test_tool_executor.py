"""Tests for tool_executor module (unit-level, no CDP)."""

from engine._harness.tool_executor import (
    _extract_function_name,
    _extract_function_args,
    _format_tool_result,
    _truncate_args,
    _is_cdp_disconnect,
)
from engine.executor import _build_scroll_js


def test_extract_function_name():
    tc = {"id": "1", "function": {"name": "browser_goto", "arguments": '{"url": "x"}'}}
    assert _extract_function_name(tc) == "browser_goto"


def test_extract_function_args_json():
    tc = {"function": {"name": "x", "arguments": '{"url": "https://test.com"}'}}
    args = _extract_function_args(tc)
    assert args == {"url": "https://test.com"}


def test_extract_function_args_dict():
    tc = {"function": {"name": "x", "arguments": {"url": "https://test.com"}}}
    args = _extract_function_args(tc)
    assert args == {"url": "https://test.com"}


def test_extract_function_args_invalid():
    tc = {"function": {"name": "x", "arguments": "{bad json}"}}
    args = _extract_function_args(tc)
    assert args == {}


def test_format_tool_result_ok():
    result = _format_tool_result("browser_goto", {"ok": True, "result": "done"})
    assert "done" in result


def test_format_tool_result_error():
    result = _format_tool_result("browser_goto", {"ok": False, "error": "timeout"})
    assert "Error executing browser_goto" in result
    assert "timeout" in result


def test_truncate_args():
    long_args = {"x": "y" * 100}
    result = _truncate_args(long_args, max_len=20)
    assert len(result) <= 23  # ~20 + "..."


def test_is_cdp_disconnect():
    class WebSocketError(Exception):
        pass
    assert _is_cdp_disconnect(WebSocketError("closed"))


def test_is_cdp_disconnect_negative():
    assert not _is_cdp_disconnect(ValueError("element not found"))


def test_build_scroll_js():
    assert "scrollBy(0, 300)" in _build_scroll_js("down", 300)
    assert "scrollBy(0, -300)" in _build_scroll_js("up", 300)
