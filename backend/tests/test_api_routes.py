"""Tests for api.routes — FastAPI REST + WebSocket endpoints.

Uses FastAPI TestClient with mocked engine_state to avoid
requiring a real browser or Chrome connection.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yak_browser_use.api.errors import register_error_handlers
from yak_browser_use.api.routes import register_all_routes, _extract_pipeline_name


# ── _extract_pipeline_name ─────────────────────────────────────────


class TestExtractPipelineName:
    def test_extracts_from_valid_yaml(self):
        yaml_text = "name: my_pipeline\nsteps:\n  - name: s1\n"
        assert _extract_pipeline_name(yaml_text) == "my_pipeline"

    def test_strips_quotes(self):
        yaml_text = """name: '"quoted-name"'\nsteps: []\n"""
        name = _extract_pipeline_name(yaml_text)
        assert name == "quoted-name"

    def test_returns_unnamed_on_missing_name(self):
        yaml_text = "steps:\n  - name: s1\n"
        assert _extract_pipeline_name(yaml_text) == "unnamed"

    def test_returns_unnamed_on_invalid_yaml(self):
        assert _extract_pipeline_name(": broken yaml :") == "unnamed"

    def test_returns_unnamed_on_empty_text(self):
        assert _extract_pipeline_name("") == "unnamed"

    def test_returns_unnamed_when_not_a_dict(self):
        assert _extract_pipeline_name("[1, 2, 3]") == "unnamed"


# ── FastAPI TestClient fixture ─────────────────────────────────────


@pytest.fixture
def app():
    """Create a fresh FastAPI app with routes and error handlers registered."""
    a = FastAPI()
    register_error_handlers(a)
    register_all_routes(a)
    return a


@pytest.fixture
def client(app):
    """FastAPI TestClient — engine_state is patched per-test."""
    return TestClient(app)


def _mock_engine_state(**overrides):
    """Create a mock _EngineState with sensible defaults."""
    state = MagicMock()
    state.current_state = overrides.get("current_state", "idle")
    state.chrome_connected = overrides.get("chrome_connected", False)
    state.bridge = overrides.get("bridge", None)
    state.running_pipeline = overrides.get("running_pipeline", None)
    state.ws_clients = overrides.get("ws_clients", [])
    state._service = overrides.get("_service", None)
    return state


# ── PROVIDER CONFIG endpoints ──────────────────────────────────────


class TestProviderConfig:
    def test_get_config_default(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            with patch("yak_browser_use.utils.browser._get_config_path") as mock_path:
                mock_path.return_value.exists.return_value = False
                resp = client.get("/api/provider-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["config"] == {}

    def test_get_config_with_data(self, client, tmp_path):
        config_path = tmp_path / "provider.json"
        config_path.write_text(json.dumps({"model": "gpt-4o"}), encoding="utf-8")

        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            with patch("yak_browser_use.utils.browser._get_config_path", return_value=config_path):
                resp = client.get("/api/provider-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["config"]["model"] == "gpt-4o"

    def test_set_config(self, client, tmp_path):
        config_path = tmp_path / "provider.json"
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            with patch("yak_browser_use.utils.browser._get_config_path", return_value=config_path):
                resp = client.post("/api/provider-config", json={"model": "custom-model"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert config_path.exists()
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["model"] == "custom-model"


# ── CHROME endpoints ───────────────────────────────────────────────


class TestChromeConnect:
    def test_connect_rejects_when_pipeline_running(self, client):
        state = _mock_engine_state(running_pipeline=MagicMock())

        with patch("yak_browser_use.api.routes.engine_state", state):
            resp = client.post("/api/chrome/connect", json={"mode": "user"})
        assert resp.status_code == 409
        data = resp.json()
        assert "error" in data

    def test_disconnect_rejects_when_pipeline_running(self, client):
        state = _mock_engine_state(running_pipeline=MagicMock(), chrome_connected=True)

        with patch("yak_browser_use.api.routes.engine_state", state):
            resp = client.post("/api/chrome/disconnect")
        assert resp.status_code == 409


class TestChromeStatus:
    def test_disconnected_status(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state(chrome_connected=False)):
            resp = client.get("/api/chrome/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False

    def test_connected_status(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state(chrome_connected=True)):
            resp = client.get("/api/chrome/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True

    def test_disconnect_when_already_disconnected(self, client):
        state = _mock_engine_state(chrome_connected=False)
        with patch("yak_browser_use.api.routes.engine_state", state):
            resp = client.post("/api/chrome/disconnect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["disconnected"] is True
        assert data["was_already"] is True


class TestChromeRestart:
    def test_restart_rejects_when_pipeline_running(self, client):
        state = _mock_engine_state(running_pipeline=MagicMock())
        with patch("yak_browser_use.api.routes.engine_state", state):
            resp = client.post("/api/chrome/restart")
        assert resp.status_code == 409


# ── HIGHLIGHT CONFIG endpoints ─────────────────────────────────────


class TestHighlightConfig:
    def test_set_valid_mode(self, client):
        bridge = MagicMock()
        bridge.set_highlight_config = MagicMock()
        bridge.ensure_highlights = AsyncMock()
        state = _mock_engine_state(bridge=bridge)

        with patch("yak_browser_use.api.routes.engine_state", state):
            resp = client.post("/api/highlight-config", json={"mode": "progressive"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["mode"] == "progressive"

    def test_set_invalid_mode(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            resp = client.post("/api/highlight-config", json={"mode": "invalid"})
        assert resp.status_code == 400


# ── PARAMS endpoints ───────────────────────────────────────────────


class TestParams:
    def test_list_params(self, client):
        with (
            patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()),
            patch("yak_browser_use.params.manager.list_param_keys", return_value=["key1", "key2"]),
        ):
            resp = client.get("/api/params")
        assert resp.status_code == 200
        data = resp.json()
        assert data["params"] == ["key1", "key2"]

    def test_set_param_missing_key(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            resp = client.post("/api/params", json={"value": "val"})
        assert resp.status_code == 422

    def test_set_param_missing_value(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            resp = client.post("/api/params", json={"key": "k"})
        assert resp.status_code == 422

    def test_set_and_delete_param(self, client):
        with (
            patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()),
            patch("yak_browser_use.params.manager.ParamManager") as MockPM,
        ):
            mock_pm = MagicMock()
            MockPM.return_value = mock_pm
            resp = client.post("/api/params", json={"key": "mykey", "value": "myval"})
            assert resp.status_code == 200
            mock_pm.set.assert_called_once_with("mykey", "myval")

        with (
            patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()),
            patch("yak_browser_use.params.manager.list_param_keys", return_value=["mykey"]),
            patch("yak_browser_use.params.manager.delete_param") as mock_del,
        ):
            resp = client.delete("/api/params/mykey")
            assert resp.status_code == 200
            mock_del.assert_called_once_with("mykey")


# ── PIPELINE endpoints ─────────────────────────────────────────────


# ── CHAT endpoints ─────────────────────────────────────────────────


class TestChat:
    def test_empty_message_rejected(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            resp = client.post("/api/chat", json={"message": ""})
        assert resp.status_code == 400

    def test_reset_and_cancel(self, client):
        mock_service = MagicMock()
        mock_service.get_session.return_value = MagicMock()
        mock_session = MagicMock()
        mock_session.session_id = "sess_1"
        mock_session.status = "active"
        mock_service.reset_session.return_value = mock_session

        state = _mock_engine_state()
        state._service = mock_service

        with patch("yak_browser_use.api.routes.engine_state", state):
            with patch("yak_browser_use.api.routes._get_service", return_value=mock_service):
                resp = client.post("/api/chat/reset")
                assert resp.status_code == 200
                data = resp.json()
                assert data["ok"] is True
                assert data["session_id"] == "sess_1"

                resp2 = client.post("/api/chat/cancel")
                assert resp2.status_code == 200
                data2 = resp2.json()
                assert data2["ok"] is True


# ── SESSION endpoint ───────────────────────────────────────────────


class TestSession:
    def test_no_session(self, client):
        mock_service = MagicMock()
        mock_service.get_session.return_value = None

        state = _mock_engine_state()
        with patch("yak_browser_use.api.routes.engine_state", state):
            with patch("yak_browser_use.api.routes._get_service", return_value=mock_service):
                resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"] is None

    def test_active_session(self, client):
        mock_session = MagicMock()
        mock_session.session_id = "sess_1"
        mock_session.pipeline_name = "test"
        mock_session.status = "active"
        mock_session.messages = [{"role": "user", "content": "hi"}]

        mock_service = MagicMock()
        mock_service.get_session.return_value = mock_session

        state = _mock_engine_state()
        with patch("yak_browser_use.api.routes.engine_state", state):
            with patch("yak_browser_use.api.routes._get_service", return_value=mock_service):
                resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session"]["session_id"] == "sess_1"
        assert data["session"]["message_count"] == 1


# ── PRESETS / PIPELINES endpoints ──────────────────────────────────


class TestPresets:
    def test_list_presets(self, client):
        mock_service = MagicMock()
        mock_service.list_presets.return_value = [{"name": "test_pipe", "steps": 3}]

        state = _mock_engine_state()
        state._service = mock_service

        with (
            patch("yak_browser_use.api.routes.engine_state", state),
            patch("yak_browser_use.api.routes._get_service", return_value=mock_service),
        ):
            resp = client.get("/api/presets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["presets"]) == 1
        assert data["presets"][0]["name"] == "test_pipe"


class TestPipelines:
    def test_list_pipelines(self, client):
        with (
            patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.iterdir") as mock_iter,
        ):
            mock_dir = MagicMock()
            mock_dir.is_dir.return_value = True
            mock_dir.name = "my_pipe"
            mock_subdir = MagicMock()
            mock_subdir.name = "pipeline.yaml"
            mock_dir.__truediv__.return_value = mock_subdir
            mock_subdir.exists.return_value = True
            mock_subdir.read_text.return_value = "name: my_pipe\nsteps: []\n"
            mock_iter.return_value = [mock_dir]

            resp = client.get("/api/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        assert "my_pipe" in [p["name"] for p in data["pipelines"]]

    def test_get_pipeline_not_found(self, client):
        with (
            patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()),
            patch("pathlib.Path.exists", return_value=False),
        ):
            resp = client.get("/api/pipelines/nonexistent")
        assert resp.status_code == 404


# ── STATUS endpoint ────────────────────────────────────────────────


class TestStatus:
    def test_global_state(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state(current_state="idle")):
            resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_state"] == "idle"

    def test_pipeline_status(self, client):
        with (
            patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()),
            patch("yak_browser_use.workspace.manager.WorkspaceManager") as MockWM,
        ):
            mock_wm = MagicMock()
            mock_wm.list_runs.return_value = [
                {"run_id": "run_1", "status": "completed", "pipeline": "test"}
            ]
            MockWM.return_value = mock_wm
            resp = client.get("/api/status?pipeline=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"


# ── Logs endpoint ──────────────────────────────────────────────────


class TestLogs:
    def test_forward_logs(self, client):
        with patch("yak_browser_use.api.routes.engine_state", _mock_engine_state()):
            resp = client.post("/api/logs/forward", json={
                "entries": [
                    {"ts": "12:00", "level": "INFO", "name": "test", "msg": "hello"},
                ],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["count"] == 1
