"""Tests for prompts/_loader module."""

from yak_browser_use.prompts._loader import load_prompt


def test_load_prompt_basic():
    text = load_prompt("guardrails/exact_failure",
                       tool_name="browser_click",
                       count="5")
    assert "browser_click" in text
    assert "5" in text


def test_load_prompt_variable_not_passed_remains():
    text = load_prompt("guardrails/exact_failure",
                       tool_name="browser_click")
    assert "browser_click" in text
    assert "{count}" in text  # not replaced


def test_load_prompt_no_variables():
    text = load_prompt("guidance/tool_strategy")
    assert "browser_goto" in text
    assert "browser_snapshot" in text
