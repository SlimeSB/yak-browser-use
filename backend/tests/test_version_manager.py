"""Tests for workspace.version_manager — version snapshots."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from yak_browser_use.workspace.version_manager import VersionManager


class TestVersionManagerInit:
    def test_sets_paths(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        assert vm.pipeline_name == "test_pipe"
        assert vm.versions_dir == tmp_path
        assert vm.latest_file == tmp_path / "LATEST"
        assert vm.stale_file == tmp_path / "STALE"


class TestVersionManagerEnsure:
    def test_creates_directory(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        versions_dir = vm.ensure()
        assert versions_dir.exists()


class TestVersionManagerLatest:
    def test_no_latest_initially(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        assert vm.get_latest() is None

    def test_set_and_get_latest(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.set_latest("3")
        assert vm.get_latest() == "3"

    def test_overwrite_latest(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.set_latest("1")
        vm.set_latest("2")
        assert vm.get_latest() == "2"


class TestVersionManagerCreateVersion:
    def test_creates_version_directory(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        (tmp_path / "..").mkdir(parents=True, exist_ok=True)  # ensure parent exists
        vm.ensure()

        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "tool.py").write_text("def tool(): pass", encoding="utf-8")

        version = vm.create_version(
            trigger_run_id="run_123",
            summary="Initial version",
            pipe_pipeline=pipe_file,
            tools_dir=tools_dir,
            upgraded_tools=["tool1"],
            learned_goals=["goal1"],
        )
        assert version == "1"

        ver_dir = tmp_path / "1"
        assert ver_dir.exists()
        assert (ver_dir / "pipe.pipeline.yaml").exists()
        assert (ver_dir / "tools" / "tool.py").exists()
        assert (ver_dir / "version.meta.json").exists()

        meta = json.loads((ver_dir / "version.meta.json").read_text(encoding="utf-8"))
        assert meta["version"] == "1"
        assert meta["trigger_run_id"] == "run_123"
        assert meta["summary"] == "Initial version"
        assert meta["upgraded_tools"] == ["tool1"]
        assert meta["learned_goals"] == ["goal1"]

    def test_version_number_increments(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)

        v1 = vm.create_version("r1", "first", pipe_file, tools_dir)
        v2 = vm.create_version("r2", "second", pipe_file, tools_dir)
        assert v1 == "1"
        assert v2 == "2"

    def test_missing_pipe_pipeline_does_not_crash(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)
        # pipe_pipeline doesn't exist
        version = vm.create_version("run_1", "test", tmp_path / "nonexistent.yaml", tools_dir)
        ver_dir = tmp_path / version
        assert ver_dir.exists()
        # Just shouldn't crash

    def test_sets_latest_after_create(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)
        vm.create_version("r1", "v1", pipe_file, tools_dir)
        assert vm.get_latest() == "1"


class TestVersionManagerLoadVersion:
    def test_load_existing(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test_pipe\nsteps: []\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)
        (tools_dir / "tool.py").write_text("", encoding="utf-8")
        vm.create_version("r1", "test", pipe_file, tools_dir)

        result = vm.load_version("1")
        assert result is not None
        agent_path, tools_path = result
        assert agent_path.exists()
        assert tools_path.exists()

    def test_load_nonexistent(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        assert vm.load_version("999") is None

    def test_load_missing_pipeline_file(self, tmp_path):
        """Version dir exists but pipe.pipeline.yaml is missing."""
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        (tmp_path / "1").mkdir()
        result = vm.load_version("1")
        assert result is None


class TestVersionManagerListVersions:
    def test_empty(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        assert vm.list_versions() == []

    def test_lists_all(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)

        vm.create_version("r1", "first", pipe_file, tools_dir)
        vm.create_version("r2", "second", pipe_file, tools_dir)

        versions = vm.list_versions()
        assert len(versions) == 2
        assert versions[0]["version"] == "1"
        assert versions[1]["version"] == "2"


class TestVersionManagerGetVersion:
    def test_get_existing(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)
        vm.create_version("r1", "test", pipe_file, tools_dir)

        meta = vm.get_version("test_pipe", "1")
        assert meta is not None
        assert meta["version"] == "1"

    def test_get_nonexistent(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        assert vm.get_version("test_pipe", "999") is None

    def test_get_corrupted_meta(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        (tmp_path / "1").mkdir()
        (tmp_path / "1" / "version.meta.json").write_text("not json", encoding="utf-8")
        assert vm.get_version("test_pipe", "1") is None


class TestVersionManagerStale:
    def test_not_stale_initially(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        assert vm.is_stale() is False

    def test_mark_stale(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.mark_stale()
        assert vm.is_stale() is True

    def test_clear_stale(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.mark_stale()
        vm.clear_stale()
        assert vm.is_stale() is False

    def test_clear_stale_when_not_stale(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.clear_stale()  # should not crash


class TestVersionManagerTryCreateVersion:
    def test_no_upgrades_no_version(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        result = vm.try_create_version(
            trigger_run_id="r1",
            upgraded_tools=[],
            learned_goals=[],
        )
        assert result is None

    def test_with_upgrades_creates_version(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)

        result = vm.try_create_version(
            trigger_run_id="r1",
            upgraded_tools=["tool_a"],
            learned_goals=["goal_a"],
            pipe_pipeline=pipe_file,
            tools_dir=tools_dir,
        )
        assert result == "1"
        assert vm.get_latest() == "1"

    def test_no_pipeline_file_skips(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        result = vm.try_create_version(
            trigger_run_id="r1",
            upgraded_tools=["tool_a"],
            pipe_pipeline=tmp_path / "nonexistent.yaml",
        )
        assert result is None

    def test_with_only_learned_goals(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.ensure()
        pipe_file = tmp_path / "pipe.pipeline.yaml"
        pipe_file.write_text("name: test\nsteps:\n  - name: s1\n", encoding="utf-8")
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir(exist_ok=True)

        result = vm.try_create_version(
            trigger_run_id="r1",
            learned_goals=["new_goal"],
            pipe_pipeline=pipe_file,
            tools_dir=tools_dir,
        )
        assert result == "1"


class TestVersionManagerSaveSnapshot:
    def test_saves_snapshot(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        pipeline_text = "name: test\nsteps:\n  - name: s1\n"
        version = vm.save_snapshot(pipeline_text, summary="chat-edit")
        assert version == "1"
        ver_dir = tmp_path / "1"
        assert (ver_dir / "pipe.pipeline.yaml").exists()
        assert (ver_dir / "pipe.pipeline.yaml").read_text(encoding="utf-8") == pipeline_text
        meta = json.loads((ver_dir / "version.meta.json").read_text(encoding="utf-8"))
        assert meta["summary"] == "chat-edit"

    def test_version_increments(self, tmp_path):
        vm = VersionManager(tmp_path, "test_pipe")
        vm.save_snapshot("v1")
        vm.save_snapshot("v2")
        assert vm.get_latest() == "2"
