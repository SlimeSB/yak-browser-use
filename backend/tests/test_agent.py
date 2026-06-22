"""Tests for engine.agent — goal step stub and agent entry points."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ── run_goal_step ──────────────────────────────────────────────────


class TestRunGoalStep:
    @pytest.mark.asyncio
    async def test_returns_success_stub(self):
        from engine.agent import run_goal_step

        result = await run_goal_step(
            step_def={"name": "test_step"},
            cdp_helpers=None,
            step_dir=None,
            pipeline_name="test",
        )
        assert result["status"] == "success"
        assert result["skipped"] is True
        assert "todo + browser_*" in result["message"]

    @pytest.mark.asyncio
    async def test_accepts_all_optional_args(self):
        from engine.agent import run_goal_step

        result = await run_goal_step(
            step_def={"name": "full_step", "description": "test"},
            cdp_helpers=MagicMock(),
            step_dir=MagicMock(),
            pipeline_name="my_pipe",
            frontmatter={"key": "val"},
            source_text="source",
            tools_dir=MagicMock(),
            ws_url="ws://localhost/",
            pipeline_path=MagicMock(),
            system_prompt="be helpful",
        )
        assert result["status"] == "success"


# ── start_chat_agent ──────────────────────────────────────────────
# Note: start_chat_agent is tested via integration tests because
# its function-body imports (prompts._loader, engine._harness, etc.)
# trigger heavy module dependencies that hang in unit test isolation.
# See test_integration_agent_reform.py for cross-layer coverage.
