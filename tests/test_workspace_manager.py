"""Tests for workspace.manager — workspace directory management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workspace.manager import (
    WorkspaceManager,
    _generate_run_id,
    _looks_like_run_id,
    _now_iso,
    _read_json,
    _write_json,
    DEFAULT_MAX_RUNS,
    VALID_STATUSES,
)


# ── Helper function tests ─────────────────────────────────────


class TestLookLikeRunId:
    def test_valid_format(self):
        assert _looks_like_run_id("20240101_120000") is True
        assert _looks_like_run_id("20240101_120000_2") is True

    def test_invalid_format(self):
        assert _looks_like_run_id("") is False
        assert _looks_like_run_id("abc") is False
        assert _looks_like_run_id("2024-01-01") is False
        assert _looks_like_run_id("20240101") is False


class TestGenerateRunId:
    def test_generates_timestamp_format(self, tmp_path):
        run_id = _generate_run_id(tmp_path)
        assert _looks_like_run_id(run_id) is True

    def test_unique_on_conflict(self, tmp_path):
        # Create a run dir with the same name as the first candidate
        first = _generate_run_id(tmp_path)
        (tmp_path / first).mkdir()
        second = _generate_run_id(tmp_path)
        assert second != first  # should have a suffix


class TestReadWriteJson:
    def test_read_write(self, tmp_path):
        data = {"key": "value", "num": 42}
        path = tmp_path / "test.json"
        _write_json(path, data)
        assert path.exists()
        result = _read_json(path)
        assert result == {"key": "value", "num": 42}

    def test_read_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _read_json(tmp_path / "nonexistent.json")

    def test_read_empty(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            _read_json(path)


class TestValidStatuses:
    def test_known_statuses(self):
        assert "running" in VALID_STATUSES
        assert "completed" in VALID_STATUSES
        assert "failed" in VALID_STATUSES
        assert "paused" in VALID_STATUSES
        assert "cancelled" in VALID_STATUSES
        assert "crashed" in VALID_STATUSES

    def test_invalid_status(self):
        assert "unknown" not in VALID_STATUSES


# ── WorkspaceManager ──────────────────────────────────────────


class TestWorkspaceManagerInit:
    def test_sets_paths(self):
        wm = WorkspaceManager("test_pipe")
        assert wm.pipeline_name == "test_pipe"
        assert wm.root.name == "test_pipe"
        assert wm.root.parent.name == "workspaces"
        assert ".lbu" in str(wm.root)


class TestWorkspaceManagerEnsureWorkspace:
    def test_creates_directories(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        root = wm.ensure_workspace()
        assert root.exists()
        assert wm.runs_dir.exists()
        assert wm.versions_dir.exists()
        assert wm.tools_dir.exists()

    def test_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        wm.ensure_workspace()
        wm.ensure_workspace()  # should not crash
        assert wm.root.exists()


class TestWorkspaceManagerCreateRun:
    def test_creates_run_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        assert run_dir.exists()
        assert (run_dir / "final").exists()
        assert (run_dir / "_run.json").exists()

    def test_run_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["pipeline"] == "test_pipe"
        assert meta["status"] == "pending"
        assert "run_id" in meta
        assert "created_at" in meta
        assert meta["version"] is None  # no versions yet


class TestWorkspaceManagerSetGetStatus:
    def test_set_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "running")
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["status"] == "running"

    def test_get_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "completed")
        assert wm.get_status(run_dir) == "completed"

    def test_set_status_with_current_step(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "running", current_step="step_1")
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["current_step"] == "step_1"

    def test_invalid_status_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        with pytest.raises(ValueError, match="Invalid status"):
            wm.set_status(run_dir, "invalid_status")

    def test_completed_sets_completed_at(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "completed")
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["completed_at"] is not None

    def test_failed_sets_completed_at(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "failed")
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["completed_at"] is not None

    def test_crashed_sets_both_timestamps(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "crashed")
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["completed_at"] is not None
        assert meta["crashed_detected_at"] is not None

    def test_get_status_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        assert wm.get_status(tmp_path / "nonexistent_run") is None


class TestWorkspaceManagerListRuns:
    def test_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        assert wm.list_runs() == []

    def test_returns_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run1 = wm.create_run()
        run2 = wm.create_run()
        wm.set_status(run1, "completed")
        wm.set_status(run2, "running")

        runs = wm.list_runs()
        assert len(runs) == 2
        statuses = [r["status"] for r in runs]
        assert "completed" in statuses
        assert "running" in statuses


class TestWorkspaceManagerDetectCrashed:
    def test_no_crashed_runs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "completed")
        crashed = wm.detect_crashed_runs()
        assert crashed == []

    def test_detects_running_as_crashed(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        wm.set_status(run_dir, "running")
        crashed = wm.detect_crashed_runs()
        assert len(crashed) == 1
        assert crashed[0] == run_dir
        # Verify the run is now marked crashed
        meta = json.loads((run_dir / "_run.json").read_text(encoding="utf-8"))
        assert meta["status"] == "crashed"

    def test_skips_non_run_dirs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        # Create a non-run directory
        (wm.runs_dir / "not_a_run").mkdir(parents=True, exist_ok=True)
        crashed = wm.detect_crashed_runs()
        assert crashed == []

    def test_detect_only_marks_running(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        r1 = wm.create_run()
        r2 = wm.create_run()
        r3 = wm.create_run()
        wm.set_status(r1, "running")
        wm.set_status(r2, "completed")
        wm.set_status(r3, "failed")

        crashed = wm.detect_crashed_runs()
        assert len(crashed) == 1
        assert crashed[0] == r1


class TestWorkspaceManagerCleanup:
    def test_removes_oldest_beyond_max(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        # Create 5 runs
        for _ in range(5):
            wm.create_run()
        removed = wm.cleanup_old_runs(max_runs=3)
        assert removed == 2
        assert len(wm.list_runs()) == 3

    def test_no_removal_below_max(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        for _ in range(3):
            wm.create_run()
        removed = wm.cleanup_old_runs(max_runs=5)
        assert removed == 0
        assert len(wm.list_runs()) == 3

    def test_no_runs_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        # Don't create any runs
        removed = wm.cleanup_old_runs()
        assert removed == 0


class TestWorkspaceManagerFillFinal:
    def test_copies_step_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()

        # Create a last_step_dir with some files
        last_step = run_dir / "last_step"
        last_step.mkdir()
        (last_step / "result.txt").write_text("done", encoding="utf-8")
        (last_step / "data.json").write_text("{}", encoding="utf-8")

        wm.fill_final(run_dir, last_step)
        final_dir = run_dir / "final"
        assert (final_dir / "result.txt").exists()
        assert (final_dir / "data.json").exists()

    def test_handles_missing_last_step_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()
        # Should not crash when last_step_dir doesn't exist
        wm.fill_final(run_dir, run_dir / "nonexistent")

    def test_copies_subdirectories(self, tmp_path, monkeypatch):
        monkeypatch.setattr("workspace.manager.Path.home", lambda: tmp_path)
        wm = WorkspaceManager("test_pipe")
        run_dir = wm.create_run()

        last_step = run_dir / "last_step"
        last_step.mkdir()
        (last_step / "subdir").mkdir()
        (last_step / "subdir" / "nested.txt").write_text("nested", encoding="utf-8")

        wm.fill_final(run_dir, last_step)
        assert (run_dir / "final" / "subdir" / "nested.txt").exists()
