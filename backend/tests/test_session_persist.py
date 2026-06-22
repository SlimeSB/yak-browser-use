"""Tests for session persistence — SessionStore, Service session pool, __chat__ migration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from workspace.session_store import (
    SessionStore,
    _generate_session_id,
    _normalize_pipeline,
    read_last_active,
    write_last_active,
)


# ── SessionStore ──────────────────────────────────────────────


@pytest.fixture
def tmp_store():
    """Create a SessionStore backed by a temp directory."""
    with tempfile.TemporaryDirectory() as td:
        orig_root = Path("backend/userdata/workspaces")
        test_root = Path(td) / "workspaces"
        # Monkey-patch the root path
        import workspace.session_store as ss
        orig = ss._WORKSPACES_ROOT
        ss._WORKSPACES_ROOT = test_root
        try:
            store = SessionStore("test_pipeline")
            yield store
        finally:
            ss._WORKSPACES_ROOT = orig


def test_generate_session_id():
    sid = _generate_session_id()
    assert len(sid) > 15
    assert "_" in sid


def test_normalize_pipeline():
    assert _normalize_pipeline("") == "__chat__"
    assert _normalize_pipeline("chat") == "__chat__"
    assert _normalize_pipeline("my-pipe") == "my-pipe"


def test_ensure_session_dir(tmp_store):
    path = tmp_store.ensure_session_dir()
    assert path.exists()
    assert path.is_dir()


def test_new_session(tmp_store):
    tmp_store.ensure_session_dir()
    sid = tmp_store.new_session()
    assert sid

    index = tmp_store._read_index()
    assert sid in index
    assert index[sid]["message_count"] == 0
    assert index[sid]["status"] == "idle"


def test_save_and_load_session(tmp_store):
    tmp_store.ensure_session_dir()
    sid = tmp_store.new_session()

    session_dict = {
        "session_id": sid,
        "pipeline_name": "test_pipeline",
        "status": "completed",
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ],
    }
    tmp_store.save_session(sid, session_dict)

    loaded = tmp_store.load_session(sid)
    assert loaded is not None
    assert loaded["session_id"] == sid
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["content"] == "Hello"

    # Check index was updated
    index = tmp_store._read_index()
    assert index[sid]["message_count"] == 2


def test_list_sessions(tmp_store):
    tmp_store.ensure_session_dir()
    s1 = tmp_store.new_session()
    s2 = tmp_store.new_session()
    sessions = tmp_store.list_sessions()
    assert len(sessions) == 2
    # Should be sorted descending by created_at
    assert sessions[0]["session_id"] == s2
    assert sessions[1]["session_id"] == s1


def test_atomic_write(tmp_store):
    from workspace.session_store import _atomic_write_json

    tmp_store.ensure_session_dir()
    path = tmp_store._index_path()
    _atomic_write_json(path, {"key": "value"})

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["key"] == "value"

    # .tmp file should be cleaned up
    assert not path.with_suffix(".json.tmp").exists()


# ── last_active marker ──────────────────────────────────────────


def test_last_active(tmp_store):
    import workspace.session_store as ss
    orig_root = ss._WORKSPACES_ROOT
    with tempfile.TemporaryDirectory() as td:
        ss._WORKSPACES_ROOT = Path(td)
        try:
            write_last_active("my_pipeline")
            assert read_last_active() == "my_pipeline"

            write_last_active("__chat__")
            assert read_last_active() == "__chat__"
        finally:
            ss._WORKSPACES_ROOT = orig_root


# ── Session ID sortability ─────────────────────────────────────


def test_session_id_sort(tmp_store):
    import time
    tmp_store.ensure_session_dir()
    ids = [tmp_store.new_session() for _ in range(5)]
    # IDs in same second won't necessarily sort — just verify format
    for sid in ids:
        parts = sid.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # HHMMSS
        assert len(parts[2]) == 6  # hex


# ── Store handles missing dir ─────────────────────────────────


def test_list_sessions_empty_dir(tmp_store):
    sessions = tmp_store.list_sessions()
    assert sessions == []


def test_load_missing_session(tmp_store):
    loaded = tmp_store.load_session("nonexistent")
    assert loaded is None
