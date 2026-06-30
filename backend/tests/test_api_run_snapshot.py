"""Tests for api.routes — snapshot preservation on pipeline error."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yak_browser_use.api.errors import register_error_handlers
from yak_browser_use.api.routes import register_all_routes


@pytest.fixture
def app():
    a = FastAPI()
    register_error_handlers(a)
    register_all_routes(a)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def _mock_engine_state(**overrides):
    state = MagicMock()
    state.current_state = overrides.get("current_state", "idle")
    state.chrome_connected = overrides.get("chrome_connected", False)
    state.bridge = overrides.get("bridge", None)
    state.running_pipeline = overrides.get("running_pipeline", None)
    state.ws_clients = overrides.get("ws_clients", [])
    state._service = overrides.get("_service", None)
    return state


class TestSnapshotPreservedOnError:
    def test_snapshot_moved_to_errors_on_pipeline_failure(self, client, tmp_path):
        workspace_root = tmp_path / "workspace"
        versions_dir = workspace_root / "versions"
        versions_dir.mkdir(parents=True)

        mock_wm = MagicMock()
        mock_wm.ensure_workspace.return_value = workspace_root
        mock_wm.versions_dir = versions_dir

        state = _mock_engine_state(chrome_connected=True)
        pipeline_text = "name: test_pipeline\nsteps:\n  - name: s1\n"

        with patch("yak_browser_use.api.routes.engine_state", state):
            with patch("yak_browser_use.api.routes._get_workspace_manager", return_value=mock_wm):
                with patch(
                    "yak_browser_use.engine.runner_preset.run_pipeline",
                    side_effect=RuntimeError("pipeline failed"),
                ):
                    resp = client.post("/api/run", json={"pipeline": pipeline_text})

        assert resp.status_code == 500

        errors_dir = versions_dir / "_errors"
        assert errors_dir.exists()
        error_files = list(errors_dir.glob("snapshot_*.pipeline.yaml"))
        assert len(error_files) == 1

        snapshot_files = list(versions_dir.glob("snapshot_*.pipeline.yaml"))
        assert len(snapshot_files) == 0

        content = error_files[0].read_text(encoding="utf-8")
        assert "test_pipeline" in content
