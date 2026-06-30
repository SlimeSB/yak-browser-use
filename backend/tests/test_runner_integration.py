"""Integration tests for run_pipeline — step execution order, shared_store, retry."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yak_browser_use.engine.runner_preset import run_pipeline


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_steps(names: list[str]) -> list[dict]:
    return [{"name": n, "tool_name": "noop", "description": f"step {n}"} for n in names]


def _mock_cdp_helpers():
    """Create a mock CDPHelpers with a bridge."""
    helpers = MagicMock()
    bridge = MagicMock()
    helpers.bridge = bridge
    return helpers


class FakeRoot:
    """Fake path-like object that supports / operator returning real paths."""

    def __init__(self, base: Path):
        self._base = base

    def __truediv__(self, other):
        return self._base / str(other)

    def __str__(self):
        return str(self._base)

    def __fspath__(self):
        return str(self._base)

    @property
    def name(self):
        return self._base.name

    def exists(self):
        return self._base.exists()

    def mkdir(self, *args, **kwargs):
        return self._base.mkdir(*args, **kwargs)

    def iterdir(self):
        return self._base.iterdir()


async def _run_with_mocks(steps, executor_mock, frontmatter=None, cdp_helpers=None):
    """Helper to run pipeline with mocked WorkspaceManager and executor."""
    workdir = Path(tempfile.mkdtemp())

    with patch("yak_browser_use.engine.runner_preset.WorkspaceManager") as MockWM, \
         patch("yak_browser_use.engine.runner_preset.PathGuard"), \
         patch("yak_browser_use.engine.runner_preset.EventSink"), \
         patch("yak_browser_use.engine.runner_preset._setup_run_logger", return_value=None), \
         patch("yak_browser_use.engine.runner_preset._write_execution_tree"), \
         patch("yak_browser_use.engine.runner_preset.execute_browser_step", new_callable=AsyncMock), \
         patch("yak_browser_use.engine.runner_preset.execute_tool_step", new_callable=AsyncMock) as mock_tool:

        mock_wm = MagicMock()
        mock_wm.root = FakeRoot(workdir)
        mock_wm.tools_dir = workdir / "tools"
        mock_wm.tools_dir.mkdir(parents=True, exist_ok=True)
        mock_wm.versions_dir = workdir / "versions"
        mock_wm.versions_dir.mkdir(parents=True, exist_ok=True)
        mock_wm.get_latest_version.return_value = None

        run_counter = [0]

        def _create_run():
            run_counter[0] += 1
            run_dir = workdir / f"run_{run_counter[0]}"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "final").mkdir(exist_ok=True)
            return run_dir

        mock_wm.create_run = _create_run
        MockWM.return_value = mock_wm

        if callable(executor_mock):
            mock_tool.side_effect = executor_mock
        else:
            mock_tool.return_value = executor_mock

        return await run_pipeline(
            pipeline_name="test_pipe",
            steps=steps,
            cdp_helpers=cdp_helpers or _mock_cdp_helpers(),
            frontmatter=frontmatter,
        )


# ── Tests ────────────────────────────────────────────────────────────────


class TestRunPipelineStepOrder:
    """Verify steps execute in order."""

    @pytest.mark.asyncio
    async def test_single_step_execution(self):
        steps = _make_steps(["s1"])
        result = {"status": "completed", "result": "ok", "duration_ms": 100}

        ctx = await _run_with_mocks(steps, result)

        assert len(ctx.errors) == 0

    @pytest.mark.asyncio
    async def test_multiple_steps_in_order(self):
        steps = _make_steps(["first", "second", "third"])
        call_order = []

        async def _mock_exec(step_def, tools_dir, step_dir, run_dir, **kwargs):
            call_order.append(step_def["name"])
            return {"status": "completed", "result": "ok", "duration_ms": 10}

        ctx = await _run_with_mocks(steps, _mock_exec)

        assert call_order == ["first", "second", "third"]
        assert len(ctx.errors) == 0


class TestRunPipelineSharedStore:
    """shared_store accumulates step results."""

    @pytest.mark.asyncio
    async def test_shared_store_propagated(self):
        steps = _make_steps(["alpha", "beta"])

        async def _mock_exec(step_def, tools_dir, step_dir, run_dir, **kwargs):
            assert "shared_store" in kwargs
            return {"status": "completed", "result": f"{step_def['name']}_done", "duration_ms": 10}

        ctx = await _run_with_mocks(steps, _mock_exec)

        assert len(ctx.errors) == 0

    @pytest.mark.asyncio
    async def test_constants_seeded_into_shared_store(self):
        steps = _make_steps(["s1"])
        constants = {"api_key": "test_123", "endpoint": "https://api.test"}
        captured_stores = []

        async def _mock_exec(step_def, tools_dir, step_dir, run_dir, **kwargs):
            captured_stores.append(dict(kwargs.get("shared_store", {})))
            return {"status": "completed", "result": "ok", "duration_ms": 10}

        await _run_with_mocks(steps, _mock_exec, frontmatter={"constants": constants})

        assert captured_stores[0]["api_key"] == "test_123"
        assert captured_stores[0]["endpoint"] == "https://api.test"


class TestRunPipelineRetry:
    """Verify retry behavior on step failures."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        steps = [{
            "name": "flaky_step",
            "tool_name": "noop",
            "description": "retries once",
            "params": {"max_retries": 1},
        }]
        call_count = 0

        async def _flaky_exec(step_def, tools_dir, step_dir, run_dir, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "failed", "error": {"code": "BROWSER_ERROR", "message": "timeout"}, "duration_ms": 0}
            return {"status": "completed", "result": "recovered", "duration_ms": 10}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            ctx = await _run_with_mocks(steps, _flaky_exec)

        assert call_count == 2
        assert len(ctx.errors) == 0

    @pytest.mark.asyncio
    async def test_permanent_failure_stops_pipeline(self):
        steps = _make_steps(["good_step", "bad_step"])
        call_count = 0

        async def _failing_exec(step_def, tools_dir, step_dir, run_dir, **kwargs):
            nonlocal call_count
            call_count += 1
            if step_def["name"] == "bad_step":
                return {"status": "failed", "error": {"code": "RUNTIME_ERROR", "message": "fatal"}, "duration_ms": 0}
            return {"status": "completed", "result": "ok", "duration_ms": 10}

        ctx = await _run_with_mocks(steps, _failing_exec)

        assert len(ctx.errors) == 1
        assert ctx.errors[0]["step"] == "bad_step"


class TestRunPipelineEmptySteps:
    """Edge case: empty steps list."""

    @pytest.mark.asyncio
    async def test_empty_steps_no_error(self):
        result = {"status": "completed", "result": "ok", "duration_ms": 100}

        ctx = await _run_with_mocks([], result)

        assert len(ctx.errors) == 0
