"""Tests for engine.state — RunContext dataclass."""

from __future__ import annotations

from pathlib import Path

from yak_browser_use.engine.state import RunContext


class TestRunContext:
    def test_defaults(self):
        ctx = RunContext()
        assert ctx.pipeline_name == ""
        assert ctx.run_id == ""
        assert ctx.run_dir is None
        assert ctx.version is None
        assert ctx.step_index == 0
        assert ctx.current_step == ""
        assert ctx.errors == []
        assert ctx.compensation_history == []
        assert ctx.learned_goals == []
        assert ctx.upgraded_tools == []

    def test_with_values(self):
        ctx = RunContext(
            pipeline_name="test_pipe",
            run_id="run_123",
            run_dir=Path("/tmp/test"),
            version="v3",
            step_index=2,
            current_step="search",
            errors=[{"code": "BROWSER_ERROR"}],
            compensation_history=[{"op": "click", "compensated": True}],
            learned_goals=["goal1"],
            upgraded_tools=["tool_a"],
        )
        assert ctx.pipeline_name == "test_pipe"
        assert ctx.run_id == "run_123"
        assert ctx.run_dir == Path("/tmp/test")
        assert ctx.version == "v3"
        assert ctx.step_index == 2
        assert ctx.current_step == "search"
        assert len(ctx.errors) == 1
        assert len(ctx.compensation_history) == 1
        assert ctx.learned_goals == ["goal1"]
        assert ctx.upgraded_tools == ["tool_a"]

    def test_mutable_fields(self):
        ctx = RunContext()
        ctx.errors.append({"code": "TIMEOUT"})
        ctx.step_index += 1
        assert len(ctx.errors) == 1
        assert ctx.step_index == 1
