"""Tests for engine.planner — RuntimePlanner: single-shot LLM recovery planner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.planner import RuntimePlanner, _VALID_OP_TYPES


# ── _VALID_OP_TYPES ────────────────────────────────────────────────


def test_valid_op_types():
    """Known operation types are recognised."""
    for t in ("goto", "click", "fill", "snapshot", "scroll", "source",
              "eval", "wait", "wait_for_network"):
        assert t in _VALID_OP_TYPES


# ── _parse_ops_response ────────────────────────────────────────────


class TestParseOpsResponse:
    def test_parses_plain_json_array(self):
        rp = RuntimePlanner(MagicMock())
        result = rp._parse_ops_response('[{"type": "goto", "value": "https://x.com"}]')
        assert result == [{"type": "goto", "value": "https://x.com"}]

    def test_parses_json_in_code_fence(self):
        rp = RuntimePlanner(MagicMock())
        text = """Some text before\n```json\n[{"type": "click", "selector": "#btn"}]\n```\nAfter"""
        result = rp._parse_ops_response(text)
        assert result == [{"type": "click", "selector": "#btn"}]

    def test_parses_fence_without_language(self):
        rp = RuntimePlanner(MagicMock())
        text = "```\n[{\"type\": \"wait\", \"value\": \"2\"}]\n```"
        result = rp._parse_ops_response(text)
        assert result == [{"type": "wait", "value": "2"}]

    def test_filters_invalid_ops(self):
        rp = RuntimePlanner(MagicMock())
        result = rp._parse_ops_response(
            '[{"type": "goto", "value": "x"}, {"type": "invalid_op"}]'
        )
        assert result == [{"type": "goto", "value": "x"}]

    def test_empty_content_returns_none(self):
        rp = RuntimePlanner(MagicMock())
        assert rp._parse_ops_response("") is None

    def test_all_invalid_ops_returns_none(self):
        rp = RuntimePlanner(MagicMock())
        result = rp._parse_ops_response('[{"type": "unknown"}]')
        assert result is None

    def test_empty_array_returns_none(self):
        rp = RuntimePlanner(MagicMock())
        assert rp._parse_ops_response("[]") is None

    def test_malformed_json_returns_none(self):
        rp = RuntimePlanner(MagicMock())
        assert rp._parse_ops_response("not json at all") is None

    def test_non_list_json_returns_none(self):
        rp = RuntimePlanner(MagicMock())
        assert rp._parse_ops_response('{"type": "goto"}') is None

    def test_bare_brackets_in_text(self):
        """Should extract JSON array even when surrounded by text with brackets."""
        rp = RuntimePlanner(MagicMock())
        text = "Here: [{\"type\": \"goto\", \"value\": \"https://x.com\"}] and that's it"
        result = rp._parse_ops_response(text)
        assert result == [{"type": "goto", "value": "https://x.com"}]

    def test_multiple_ops_correct_order(self):
        rp = RuntimePlanner(MagicMock())
        result = rp._parse_ops_response(
            '[{"type": "click", "selector": "#a"}, {"type": "fill", "selector": "#b", "value": "hi"}, {"type": "wait", "value": "1"}]'
        )
        assert len(result) == 3
        assert result[0]["type"] == "click"
        assert result[1]["type"] == "fill"
        assert result[2]["type"] == "wait"


# ── _build_planner_prompt ──────────────────────────────────────────


class TestBuildPlannerPrompt:
    def test_includes_goal(self):
        rp = RuntimePlanner(MagicMock())
        prompt = rp._build_planner_prompt(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="Click the submit button",
            error_message="element not found",
            simplified_html="<html><body>...</body></html>",
        )
        assert "Click the submit button" in prompt
        assert "click" in prompt
        assert "element not found" in prompt
        assert "<html" in prompt

    def test_with_unknown_op_type(self):
        rp = RuntimePlanner(MagicMock())
        prompt = rp._build_planner_prompt(
            failed_op={"type": "unknown_op"},
            goal_description="Do something",
            error_message="",
            simplified_html="",
        )
        assert "unknown_op" in prompt

    def test_truncates_long_html(self):
        rp = RuntimePlanner(MagicMock())
        long_html = "<html>" + "a" * 10000 + "</html>"
        prompt = rp._build_planner_prompt(
            failed_op={"type": "goto", "value": "x"},
            goal_description="g",
            error_message="e",
            simplified_html=long_html,
        )
        assert len(prompt) < 9000  # truncated to 8000

    def test_failed_op_params_included(self):
        rp = RuntimePlanner(MagicMock())
        prompt = rp._build_planner_prompt(
            failed_op={"type": "fill", "selector": "#q", "value": "hello"},
            goal_description="Search",
            error_message="timeout",
            simplified_html="",
        )
        assert "hello" in prompt or '"hello"' in prompt

    def test_missing_goal_description(self):
        rp = RuntimePlanner(MagicMock())
        prompt = rp._build_planner_prompt(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="",
            error_message="err",
            simplified_html="",
        )
        assert "(no description)" in prompt

    def test_missing_error_message(self):
        rp = RuntimePlanner(MagicMock())
        prompt = rp._build_planner_prompt(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="Goal",
            error_message="",
            simplified_html="",
        )
        assert "(no error details)" in prompt


# ── plan_replacement_ops ────────────────────────────────────────────


class TestPlanReplacementOps:
    @pytest.mark.asyncio
    async def test_successful_planning(self):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '[{"type": "click", "selector": "#submit-btn"}]'
        mock_llm.return_value = mock_response

        rp = RuntimePlanner(mock_llm)
        result = await rp.plan_replacement_ops(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="Click submit",
            error_message="element not found",
            simplified_html="<html/>",
        )
        assert result == [{"type": "click", "selector": "#submit-btn"}]
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_call_failure_returns_none(self):
        mock_llm = AsyncMock(side_effect=RuntimeError("API down"))
        rp = RuntimePlanner(mock_llm)
        result = await rp.plan_replacement_ops(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="g",
            error_message="e",
            simplified_html="",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_returns_empty_returns_none(self):
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = ""
        mock_llm.return_value = mock_response

        rp = RuntimePlanner(mock_llm)
        result = await rp.plan_replacement_ops(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="g",
            error_message="e",
            simplified_html="",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_waits_use_string_value(self):
        """Wait ops with string values should parse correctly."""
        mock_llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = '[{"type": "wait", "value": "2"}]'
        mock_llm.return_value = mock_response

        rp = RuntimePlanner(mock_llm)
        result = await rp.plan_replacement_ops(
            failed_op={"type": "click", "selector": "#btn"},
            goal_description="Wait for something",
            error_message="timeout",
            simplified_html="",
        )
        assert result == [{"type": "wait", "value": "2"}]
