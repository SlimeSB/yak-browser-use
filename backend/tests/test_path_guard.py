"""Tests for workspace.path_guard — path traversal protection."""

from __future__ import annotations

from pathlib import Path

import pytest

from workspace.path_guard import PathGuard


class TestPathGuard:
    def test_valid_input_within_workspace(self, tmp_path):
        guard = PathGuard(tmp_path, tmp_path / "run")
        file_path = tmp_path / "data" / "file.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("data", encoding="utf-8")

        result = guard.validate_input(file_path)
        assert result == file_path.resolve()

    def test_valid_input_within_run_dir(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        guard = PathGuard(tmp_path, run_dir)
        file_path = run_dir / "output.txt"
        file_path.write_text("data", encoding="utf-8")

        result = guard.validate_input(file_path)
        assert result == file_path.resolve()

    def test_path_traversal_blocked(self, tmp_path):
        guard = PathGuard(tmp_path, tmp_path / "run")
        with pytest.raises(PermissionError, match=".."):
            guard.validate_input(tmp_path / ".." / "outside")

    def test_absolute_outside_path_blocked(self, tmp_path):
        guard = PathGuard(tmp_path, tmp_path / "run")
        with pytest.raises(PermissionError, match="security check"):
            guard.validate_input("/etc/passwd")

    def test_output_dir_within_run(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        guard = PathGuard(tmp_path, run_dir)
        output = run_dir / "step_1"
        output.mkdir()

        result = guard.validate_output_dir(output)
        assert result == output.resolve()

    def test_output_dir_outside_run_blocked(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        guard = PathGuard(tmp_path, run_dir)

        with pytest.raises(PermissionError, match="Output directory check failed"):
            guard.validate_output_dir(tmp_path / "outside")

    def test_output_dir_workspace_path_blocked(self, tmp_path):
        """Output dir must be inside run dir, even if inside workspace."""
        run_dir = tmp_path / "run"
        run_dir.mkdir(parents=True)
        guard = PathGuard(tmp_path, run_dir)

        # A file in workspace root (not in run dir) should be blocked as output
        with pytest.raises(PermissionError, match="Output directory check failed"):
            guard.validate_output_dir(tmp_path / "versions")

    def test_nonexistent_path(self, tmp_path):
        guard = PathGuard(tmp_path, tmp_path / "run")
        result = guard.validate_input(tmp_path / "does_not_exist")
        # Should still resolve the path (it just doesn't exist on disk)
        assert str(result).endswith("does_not_exist")
