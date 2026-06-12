"""Tests for tool_guardrails module."""

from engine._harness.tool_guardrails import (
    ToolCallGuardrailConfig,
    ToolCallGuardrailState,
    create_chat_guardrail_config,
)


def test_chat_config_relaxed_defaults():
    cfg = create_chat_guardrail_config()
    assert cfg.hard_stop_enabled is False
    assert cfg.exact_failure_warn_after == 5
    assert cfg.same_tool_failure_warn_after == 6
    assert cfg.no_progress_warn_after == 3


def test_default_config():
    cfg = ToolCallGuardrailConfig()
    assert cfg.hard_stop_enabled is False
    assert cfg.exact_failure_warn_after == 5


def test_state_reset():
    state = ToolCallGuardrailState()
    state._exact_failures["key"] = 10
    state._tool_failures["tool"] = 5
    state.reset()
    assert len(state._exact_failures) == 0
    assert len(state._tool_failures) == 0


def test_before_call_allows_first_call():
    state = ToolCallGuardrailState()
    result = state.before_call("browser_click", {"selector": "#btn"})
    assert result is True


def test_after_call_records_failure():
    state = ToolCallGuardrailState()
    state.after_call("browser_click", {"selector": "#btn"}, ok=False, result_str="error")
    key = "browser_click:[('selector', '#btn')]"
    assert state._exact_failures[key] == 1
    assert state._tool_failures["browser_click"] == 1


def test_after_call_below_warn_threshold_no_warning():
    state = ToolCallGuardrailState()
    for _ in range(4):
        warning = state.after_call(
            "browser_click", {"selector": "#btn"}, ok=False, result_str="error"
        )
        assert warning is None


def test_after_call_exact_failure_warn_at_threshold():
    state = ToolCallGuardrailState()
    for _ in range(4):
        state.after_call("browser_click", {"selector": "#btn"}, ok=False, result_str="error")
    warning = state.after_call(
        "browser_click", {"selector": "#btn"}, ok=False, result_str="error"
    )
    assert warning is not None
    assert "browser_click" in warning
    assert "5" in warning or "5 times" in warning


def test_no_progress_detection():
    state = ToolCallGuardrailState()
    state.config.no_progress_warn_after = 2
    for _ in range(2):
        warning = state.after_call(
            "browser_snapshot", {}, ok=True, result_str="same result"
        )
        assert warning is None
    warning = state.after_call(
        "browser_snapshot", {}, ok=True, result_str="same result"
    )
    assert warning is not None
