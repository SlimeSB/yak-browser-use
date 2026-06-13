"""Tests for engine.events — EventSink event publishing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.events import EventSink


class TestEventSink:
    def test_emit_run_start(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_run_start("test_pipe", "run_123", "v1")
        events = _read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["type"] == "run_start"
        assert events[0]["pipeline"] == "test_pipe"
        assert events[0]["run_id"] == "run_123"
        assert events[0]["version"] == "v1"
        assert "_ts" in events[0]

    def test_emit_run_end(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_run_end("completed", 1500)
        events = _read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["type"] == "run_end"
        assert events[0]["status"] == "completed"
        assert events[0]["duration_ms"] == 1500

    def test_emit_step_start(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_step_start("navigate", "browser")
        events = _read_events(tmp_path)
        assert events[0]["type"] == "step_start"
        assert events[0]["step"] == "navigate"
        assert events[0]["step_type"] == "browser"

    def test_emit_step_end(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_step_end("search", "browser", "completed", 200,
                           input_files=["url.txt"], output_files=["result.json"])
        events = _read_events(tmp_path)
        assert events[0]["type"] == "step_end"
        assert events[0]["status"] == "completed"
        assert events[0]["input_files"] == ["url.txt"]

    def test_emit_error(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_error("step_1", "BROWSER_ERROR", "Page load timeout", "traceback...")
        events = _read_events(tmp_path)
        assert events[0]["type"] == "error"
        assert events[0]["code"] == "BROWSER_ERROR"
        assert events[0]["message"] == "Page load timeout"
        assert events[0]["stack"] == "traceback..."

    def test_emit_log(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_log("step_1", "Operation completed", "INFO")
        events = _read_events(tmp_path)
        assert events[0]["type"] == "log"
        assert events[0]["level"] == "INFO"
        assert events[0]["message"] == "Operation completed"

    def test_multiple_events_appended(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_run_start("p1", "r1", "v1")
        sink.emit_step_start("s1", "browser")
        sink.emit_step_end("s1", "browser", "success", 100)
        sink.emit_run_end("success", 500)
        events = _read_events(tmp_path)
        assert len(events) == 4

    def test_ws_clients_receive_events(self, tmp_path):
        received = []
        class MockWS:
            def put_nowait(self, event):
                received.append(event)

        sink = EventSink(tmp_path, ws_clients=[MockWS()])
        sink.emit_run_start("p1", "r1", "v1")
        assert len(received) == 1
        assert received[0]["type"] == "run_start"

    def test_ws_client_exception_does_not_break(self, tmp_path):
        class BrokenWS:
            def put_nowait(self, event):
                raise RuntimeError("WS error")

        sink = EventSink(tmp_path, ws_clients=[BrokenWS()])
        # Should not raise
        sink.emit_run_start("p1", "r1", "v1")
        events = _read_events(tmp_path)
        assert len(events) == 1

    def test_close_does_nothing(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.close()  # Should not crash

    def test_event_log_created(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_log("s1", "test", "DEBUG")
        assert (tmp_path / "_events.jsonl").exists()

    def test_timestamp_added_to_all_events(self, tmp_path):
        sink = EventSink(tmp_path)
        sink.emit_run_start("p1", "r1", "v1")
        sink.emit_log("s1", "msg", "INFO")
        events = _read_events(tmp_path)
        for event in events:
            assert "_ts" in event


def _read_events(run_dir: Path) -> list[dict]:
    log_path = run_dir / "_events.jsonl"
    assert log_path.exists()
    events = []
    for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            events.append(json.loads(line))
    return events
