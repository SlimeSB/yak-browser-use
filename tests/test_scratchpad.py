"""Tests for engine.scratchpad — in-memory heavy data cache."""

from __future__ import annotations

from engine.scratchpad import (
    ScratchpadRecord,
    _scratchpads,
    get,
    store,
    store_raw_html,
    sync_element_map,
    _build_element_map,
    _build_summary,
)


class TestScratchpadGet:
    def test_get_auto_create(self):
        _scratchpads.clear()
        record = get("session-1")
        assert isinstance(record, ScratchpadRecord)
        assert record.url == ""
        assert record.title == ""
        assert record.elements == []
        assert record.element_map == {}
        assert record.raw_html == ""

    def test_get_returns_same_instance(self):
        _scratchpads.clear()
        r1 = get("s1")
        r2 = get("s1")
        assert r1 is r2

    def test_session_isolation(self):
        _scratchpads.clear()
        r_a = get("a")
        r_b = get("b")
        r_a.url = "https://a.com"
        r_b.url = "https://b.com"
        assert get("a").url == "https://a.com"
        assert get("b").url == "https://b.com"


class TestScratchpadStore:
    def test_store_builds_element_map(self):
        _scratchpads.clear()
        elements = [
            {"ref": "@e1", "selector": "button#submit", "tag": "button", "text": "Submit"},
            {"ref": "@e2", "selector": "input[name='q']", "tag": "input", "text": ""},
        ]
        store({"elements": elements, "url": "https://example.com", "title": "Test Page"})
        record = get()
        assert record.element_map == {"@e1": "button#submit", "@e2": "input[name='q']"}
        assert record.url == "https://example.com"
        assert record.title == "Test Page"

    def test_store_skips_empty_ref(self):
        _scratchpads.clear()
        elements = [
            {"ref": "", "selector": "div"},
            {"ref": "@e1", "selector": "button"},
        ]
        store({"elements": elements})
        assert get().element_map == {"@e1": "button"}

    def test_store_overwrites_previous(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e1", "selector": "old"}], "url": "old.com", "title": "Old"})
        store({"elements": [{"ref": "@e2", "selector": "new"}], "url": "new.com", "title": "New"})
        record = get()
        assert record.element_map == {"@e2": "new"}
        assert record.url == "new.com"
        assert record.title == "New"

    def test_store_empty_elements(self):
        _scratchpads.clear()
        store({"elements": [], "url": "x.com", "title": ""})
        assert get().element_map == {}


class TestScratchpadStoreRawHtml:
    def test_only_updates_raw_html(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e1", "selector": "btn"}], "url": "x.com", "title": "T"})
        store_raw_html("<html><body>hello</body></html>")
        record = get()
        assert record.raw_html == "<html><body>hello</body></html>"
        assert record.url == "x.com"
        assert record.title == "T"
        assert record.element_map == {"@e1": "btn"}


class TestScratchpadSyncElementMap:
    def test_sync_updates_only_element_map(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e1", "selector": "old"}], "url": "x.com", "title": "T"})
        sync_element_map([{"ref": "@e2", "selector": "new-btn"}, {"ref": "@e3", "selector": "input"}])
        record = get()
        assert record.element_map == {"@e2": "new-btn", "@e3": "input"}
        assert record.url == "x.com"
        assert record.title == "T"

    def test_sync_empty_clears_map(self):
        _scratchpads.clear()
        store({"elements": [{"ref": "@e1", "selector": "old"}]})
        sync_element_map([])
        assert get().element_map == {}

    def test_sync_auto_create_session(self):
        _scratchpads.clear()
        sync_element_map([{"ref": "@e1", "selector": "btn"}], "new-session")
        record = get("new-session")
        assert record.element_map == {"@e1": "btn"}
        assert record.url == ""


class TestBuildSummary:
    def test_with_title_and_elements(self):
        record = ScratchpadRecord(title="淘宝网", elements=[{}] * 15)
        summary = _build_summary(record)
        assert "淘宝网" in summary
        assert "15个可交互元素" in summary

    def test_elements_only(self):
        record = ScratchpadRecord(elements=[{}] * 8)
        summary = _build_summary(record)
        assert "8个可交互元素" in summary

    def test_no_data(self):
        record = ScratchpadRecord()
        summary = _build_summary(record)
        assert summary == "页面快照已获取"
