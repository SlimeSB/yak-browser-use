"""Tests for engine.runner_preset — preset pipeline orchestrator."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.engine.runner_preset import (
    _step_type,
    _safe_dirname,
    _resolve_step_urls,
    _setup_run_logger,
    _write_execution_tree,
    _collect_input_files,
)
from yak_browser_use.engine.step_machine import StepMachine, StepStatus


# ── _step_type ─────────────────────────────────────────────────────


class TestStepType:
    def test_browser_type(self):
        assert _step_type({"step_type": "browser"}) == "browser"

    def test_tool_type_by_field(self):
        assert _step_type({"tool_name": "extract"}) == "tool"

    def test_goal_type_by_field(self):
        assert _step_type({"is_goal": True}) == "goal"

    def test_browser_default(self):
        assert _step_type({}) == "browser"

    def test_step_type_takes_priority(self):
        assert _step_type({"step_type": "browser", "tool_name": "x"}) == "browser"


# ── _safe_dirname ─────────────────────────────────────────────────


class TestSafeDirname:
    def test_removes_special_chars(self):
        assert "/" not in _safe_dirname("step/1")
        assert "\\" not in _safe_dirname("step\\1")
        assert ":" not in _safe_dirname("step:1")
        assert "*" not in _safe_dirname("step*1")

    def test_strips_whitespace(self):
        assert _safe_dirname("  hello  ") == "hello"

    def test_normal_name_unchanged(self):
        assert _safe_dirname("hello_world") == "hello_world"

    def test_empty_string(self):
        assert _safe_dirname("") == ""


# ── _resolve_step_urls ────────────────────────────────────────────


class TestResolveStepUrls:
    def test_replaces_goto_url(self):
        steps = [
            {"name": "s1", "browser_ops": [
                {"type": "goto", "value": "{home}"},
            ]},
        ]
        result = _resolve_step_urls(steps, {"home": "https://example.com"})
        assert result[0]["browser_ops"][0]["value"] == "https://example.com"

    def test_replaces_goal_description(self):
        steps = [
            {"name": "s1", "goal_description": "Visit {home} page"},
        ]
        result = _resolve_step_urls(steps, {"home": "https://www.baidu.com"})
        assert "https://www.baidu.com" in result[0]["goal_description"]

    def test_unknown_alias_left_untouched(self):
        steps = [
            {"name": "s1", "browser_ops": [{"type": "goto", "value": "{unknown}"}]},
        ]
        result = _resolve_step_urls(steps, {"home": "https://www.baidu.com"})
        assert result[0]["browser_ops"][0]["value"] == "{unknown}"

    def test_does_not_mutate_input(self):
        original = [
            {"name": "s1", "browser_ops": [{"type": "goto", "value": "{home}"}]},
        ]
        result = _resolve_step_urls(original, {"home": "https://example.com"})
        assert original[0]["browser_ops"][0]["value"] == "{home}"
        assert result[0]["browser_ops"][0]["value"] == "https://example.com"

    def test_empty_url_aliases(self):
        steps = [{"name": "s1", "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}]}]
        result = _resolve_step_urls(steps, {})
        assert result[0]["browser_ops"][0]["value"] == "https://www.baidu.com"

    def test_mixed_ops_some_aliased(self):
        steps = [
            {"name": "s1", "browser_ops": [
                {"type": "goto", "value": "{home}"},
                {"type": "click", "selector": "#btn"},
            ]},
        ]
        result = _resolve_step_urls(steps, {"home": "https://example.com"})
        assert result[0]["browser_ops"][0]["value"] == "https://example.com"
        assert result[0]["browser_ops"][1]["type"] == "click"

    def test_deepcopy_independence(self):
        """Changes to result should not affect original."""
        steps = [
            {"name": "s1", "browser_ops": [{"type": "goto", "value": "{home}"}]},
        ]
        result = _resolve_step_urls(steps, {"home": "https://example.com"})
        result[0]["name"] = "modified"
        assert steps[0]["name"] == "s1"


# ── _setup_run_logger ─────────────────────────────────────────────


class TestSetupRunLogger:
    def test_creates_log_file(self, tmp_path):
        handler = _setup_run_logger(tmp_path)
        assert handler is not None
        assert (tmp_path / "_pipeline.log").exists()
        logging.getLogger().removeHandler(handler)
        handler.close()

    def test_returns_handler_with_debug_level(self, tmp_path):
        handler = _setup_run_logger(tmp_path)
        assert handler is not None
        assert handler.level == logging.DEBUG
        logging.getLogger().removeHandler(handler)
        handler.close()

    def test_return_none_on_permission_error(self):
        handler = _setup_run_logger(Path("/nonexistent_dir_xyz/run_1"))
        assert handler is None


# ── _write_execution_tree ─────────────────────────────────────────


class TestWriteExecutionTree:
    def test_writes_execution_tree(self, tmp_path):
        machine = MagicMock(spec=StepMachine)
        machine.to_execution_tree.return_value = {
            "nodes": [{"index": 0, "status": "success"}],
            "edges": [],
        }

        _write_execution_tree(tmp_path, machine, "test_pipe")
        tree_file = tmp_path / "_execution_tree.json"
        assert tree_file.exists()
        data = json.loads(tree_file.read_text(encoding="utf-8"))
        assert data["pipeline"] == "test_pipe"
        assert len(data["nodes"]) == 1


# ── _collect_input_files ──────────────────────────────────────────


class TestCollectInputFiles:
    def test_delegates_to_executor(self):
        mock_input_ref = {"data.json": "@step_1.output"}
        mock_run_dir = Path("/runs/1")

        with patch(
            "yak_browser_use.engine.executor._resolve_input_files",
            return_value={"data.json": "/runs/1/step_1/data.json"},
        ) as mock_resolve:
            result = _collect_input_files(mock_input_ref, mock_run_dir)
            assert result["data.json"] == "/runs/1/step_1/data.json"
            mock_resolve.assert_called_once_with(mock_input_ref, mock_run_dir)

    def test_empty_input_ref(self):
        with patch("yak_browser_use.engine.executor._resolve_input_files", return_value={}):
            result = _collect_input_files({}, Path("/"))
            assert result == {}


# ── run_pipeline (end-to-end with mocks) ───────────────────────────


class TestRunPipeline:
    @pytest.mark.asyncio
    async def test_empty_steps_returns_immediately(self, tmp_path):
        """Pipeline with no steps should complete immediately."""
        from yak_browser_use.engine.runner_preset import run_pipeline

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink"),
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.return_value = "running"
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            ctx = await run_pipeline(
                pipeline_name="empty_test",
                steps=[],
            )

        assert ctx is not None
        assert ctx.pipeline_name == "empty_test"
        assert ctx.run_dir is not None
        # Status set at least once
        assert mock_wm.set_status.call_count >= 1

    @pytest.mark.asyncio
    async def test_browser_step_executes(self, tmp_path):
        from yak_browser_use.engine.runner_preset import run_pipeline

        steps = [
            {"name": "navigate", "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}]},
        ]

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset.execute_browser_step", new_callable=AsyncMock) as mock_exec,
            patch("yak_browser_use.engine.runner_preset.write_step_json"),
            patch("yak_browser_use.engine.runner_preset.sanitize_result", side_effect=lambda x: x),
            patch("yak_browser_use.engine.runner_preset._write_execution_tree"),
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink") as MockEvents,
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.return_value = "running"
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            mock_exec.return_value = {"status": "completed", "duration_ms": 100}

            mock_events = MagicMock()
            MockEvents.return_value = mock_events

            mock_cdp = MagicMock()
            mock_bridge = MagicMock()
            mock_bridge.set_download_dir = AsyncMock()
            mock_cdp.bridge = mock_bridge

            ctx = await run_pipeline(
                pipeline_name="browser_test",
                steps=steps,
                cdp_helpers=mock_cdp,
            )

            assert len(ctx.errors) == 0

    @pytest.mark.asyncio
    async def test_cancelled_during_run(self, tmp_path):
        from yak_browser_use.engine.runner_preset import run_pipeline

        steps = [
            {"name": "s1", "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}]},
            {"name": "s2", "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}]},
        ]

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset.execute_browser_step", new_callable=AsyncMock) as mock_exec,
            patch("yak_browser_use.engine.runner_preset.write_step_json"),
            patch("yak_browser_use.engine.runner_preset.sanitize_result", side_effect=lambda x: x),
            patch("yak_browser_use.engine.runner_preset._write_execution_tree"),
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink") as MockEvents,
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.side_effect = ["running", "cancelled"]
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            mock_exec.return_value = {"status": "completed", "duration_ms": 100}

            mock_events = MagicMock()
            MockEvents.return_value = mock_events

            mock_cdp = MagicMock()
            mock_bridge = MagicMock()
            mock_bridge.set_download_dir = AsyncMock()
            mock_cdp.bridge = mock_bridge

            ctx = await run_pipeline(
                pipeline_name="cancel_test",
                steps=steps,
                cdp_helpers=mock_cdp,
            )

            assert ctx is not None
            # Pipeline was cancelled before executing second step
            assert mock_events.emit_run_end.call_args[0][0] == "cancelled"

    @pytest.mark.asyncio
    async def test_no_bridge_fails(self, tmp_path):
        """When cdp_helpers is None, browser step should fail with NO_BROWSER."""
        from yak_browser_use.engine.runner_preset import run_pipeline

        steps = [
            {"name": "s1", "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}]},
        ]

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset.write_step_json"),
            patch("yak_browser_use.engine.runner_preset.sanitize_result", side_effect=lambda x: x),
            patch("yak_browser_use.engine.runner_preset._write_execution_tree"),
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink") as MockEvents,
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.return_value = "running"
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            mock_events = MagicMock()
            MockEvents.return_value = mock_events

            ctx = await run_pipeline(
                pipeline_name="no_bridge_test",
                steps=steps,
                cdp_helpers=None,
            )

            assert len(ctx.errors) == 1
            assert ctx.errors[0]["code"] == "NO_BROWSER"

    @pytest.mark.asyncio
    async def test_browser_step_fails_terminally(self, tmp_path):
        """Browser step with non-retryable error should fail terminally."""
        from yak_browser_use.engine.runner_preset import run_pipeline

        steps = [
            {"name": "failing_step", "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}]},
        ]

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset.execute_browser_step", new_callable=AsyncMock) as mock_exec,
            patch("yak_browser_use.engine.runner_preset.write_step_json"),
            patch("yak_browser_use.engine.runner_preset.sanitize_result", side_effect=lambda x: x),
            patch("yak_browser_use.engine.runner_preset._write_execution_tree"),
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink") as MockEvents,
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.return_value = "running"
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            mock_exec.return_value = {"status": "failed", "error": {"code": "INPUT_ERROR", "message": "bad input"}}

            mock_events = MagicMock()
            MockEvents.return_value = mock_events

            mock_cdp = MagicMock()
            mock_bridge = MagicMock()
            mock_bridge.set_download_dir = AsyncMock()
            mock_cdp.bridge = mock_bridge

            ctx = await run_pipeline(
                pipeline_name="fail_test",
                steps=steps,
                cdp_helpers=mock_cdp,
            )

            assert len(ctx.errors) == 1
            assert ctx.errors[0]["code"] == "INPUT_ERROR"

    @pytest.mark.asyncio
    async def test_browser_step_retry_then_fails(self, tmp_path):
        """Browser step with retry should retry before terminal failure."""
        from yak_browser_use.engine.runner_preset import run_pipeline

        steps = [
            {
                "name": "retry_step",
                "browser_ops": [{"type": "goto", "value": "https://www.baidu.com"}],
                "params": {"max_retries": 1},
            },
        ]

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset.execute_browser_step", new_callable=AsyncMock) as mock_exec,
            patch("yak_browser_use.engine.runner_preset.write_step_json"),
            patch("yak_browser_use.engine.runner_preset.sanitize_result", side_effect=lambda x: x),
            patch("yak_browser_use.engine.runner_preset._write_execution_tree"),
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink") as MockEvents,
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.return_value = "running"
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            mock_exec.return_value = {"status": "failed", "error": {"code": "BROWSER_ERROR", "message": "browser crashed"}}

            mock_events = MagicMock()
            MockEvents.return_value = mock_events

            mock_cdp = MagicMock()
            mock_bridge = MagicMock()
            mock_bridge.set_download_dir = AsyncMock()
            mock_cdp.bridge = mock_bridge

            ctx = await run_pipeline(
                pipeline_name="retry_test",
                steps=steps,
                cdp_helpers=mock_cdp,
            )

            assert len(ctx.errors) == 1
            assert ctx.errors[0]["code"] == "BROWSER_ERROR"
            # Original attempt + 1 retry = at least 2 executions
            assert mock_exec.await_count >= 2

    @pytest.mark.asyncio
    async def test_tool_step_with_output_exists_check(self, tmp_path):
        """Tool step with output_exists check should pass when file exists."""
        from yak_browser_use.engine.runner_preset import run_pipeline

        steps = [
            {
                "name": "extract",
                "tool_name": "extract_table",
                "check": {"output_exists": "result.csv"},
            },
        ]

        with (
            patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM,
            patch("yak_browser_use.engine.runner_preset.execute_tool_step", new_callable=AsyncMock) as mock_exec,
            patch("yak_browser_use.engine.runner_preset.write_step_json"),
            patch("yak_browser_use.engine.runner_preset.sanitize_result", side_effect=lambda x: x),
            patch("yak_browser_use.engine.runner_preset._write_execution_tree"),
            patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None),
            patch("yak_browser_use.engine.runner_preset.EventSink") as MockEvents,
        ):
            mock_wm = MagicMock()
            mock_wm.root = tmp_path
            mock_wm.versions_dir = tmp_path / "versions"
            mock_wm.tools_dir = tmp_path / "tools"
            mock_wm.create_run.return_value = tmp_path / "run_1"
            mock_wm.get_status.return_value = "running"
            mock_wm.get_latest_version.return_value = "v1"
            MockWM.return_value = mock_wm

            async def _mock_exec(step_def, tools_dir, step_dir, run_dir, **kwargs):
                # Simulate tool step that creates an output file
                (step_dir / "result.csv").write_text("a,b,c", encoding="utf-8")
                return {"status": "completed", "duration_ms": 50}

            mock_exec.side_effect = _mock_exec

            mock_events = MagicMock()
            MockEvents.return_value = mock_events

            ctx = await run_pipeline(
                pipeline_name="tool_check_test",
                steps=steps,
                cdp_helpers=None,
            )

            assert len(ctx.errors) == 0
