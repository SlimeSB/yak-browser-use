"""Tests for compiler.diff — step diff engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yak_browser_use.compiler.diff import (
    _selector_matches,
    _selector_lists_match,
    diff_ops,
    filter_rejected,
    add_to_rejected,
    save_suggestions,
    merge_extra_ops,
    extract_summary,
)


# ── _selector_matches ─────────────────────────────────────────


class TestSelectorMatches:
    def test_exact_match(self):
        assert _selector_matches("#btn", "#btn") is True

    def test_substring_in_agent(self):
        assert _selector_matches("div.container #btn", "#btn") is True

    def test_no_match(self):
        assert _selector_matches("#other", "#btn") is False

    def test_empty_original(self):
        assert _selector_matches("#btn", "") is False

    def test_empty_agent(self):
        assert _selector_matches("", "#btn") is False

    def test_both_empty(self):
        assert _selector_matches("", "") is False


# ── _selector_lists_match ─────────────────────────────────────


class TestSelectorListsMatch:
    def test_single_match(self):
        assert _selector_lists_match(["#btn"], ["#btn"]) is True

    def test_partial_match(self):
        assert _selector_lists_match(["#btn", "#input"], ["#other", "#btn"]) is True

    def test_no_match(self):
        assert _selector_lists_match(["#a"], ["#b", "#c"]) is False

    def test_empty_lists(self):
        assert _selector_lists_match([], ["#a"]) is False
        assert _selector_lists_match(["#a"], []) is False
        assert _selector_lists_match([], []) is False

    def test_substring_matching(self):
        assert _selector_lists_match(["form input#submit"], ["#submit"]) is True


# ── diff_ops ──────────────────────────────────────────────────


class TestDiffOps:
    def test_all_match_same_order(self):
        agent = [
            {"type": "goto", "value": "https://x.com", "selectors": []},
            {"type": "click", "value": "#btn", "selectors": ["#btn"]},
        ]
        original = [
            {"type": "goto", "value": "https://x.com"},
            {"type": "click", "value": "#btn"},
        ]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 2
        assert len(extra) == 0

    def test_extra_ops_detected(self):
        agent = [
            {"type": "goto", "value": "https://x.com"},
            {"type": "click", "value": "#btn"},
            {"type": "fill", "value": "#input", "selectors": ["#input"]},
        ]
        original = [
            {"type": "goto", "value": "https://x.com"},
            {"type": "click", "value": "#btn"},
        ]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 2
        assert len(extra) == 1
        assert extra[0]["type"] == "fill"

    def test_type_mismatch_no_match(self):
        agent = [{"type": "click", "value": "#btn"}]
        original = [{"type": "goto", "value": "#btn"}]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 0
        assert len(extra) == 1

    def test_selector_containment_scoring(self):
        agent = [{"type": "click", "value": "form div.container button#submit", "selectors": ["button#submit"]}]
        original = [{"type": "click", "value": "#submit"}]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 1
        assert len(extra) == 0

    def test_selector_matching_via_lists(self):
        agent = [{"type": "click", "selectors": ["button#submit"], "value": ""}]
        original = [{"type": "click", "selector": "#submit"}]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 1

    def test_value_match_fallback(self):
        agent = [{"type": "goto", "value": "https://example.com"}]
        original = [{"type": "goto", "value": "https://example.com"}]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 1

    def test_no_value_same_type_match(self):
        agent = [{"type": "snapshot", "value": ""}]
        original = [{"type": "snapshot"}]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 1

    def test_used_flag_prevents_double_match(self):
        agent = [
            {"type": "click", "value": "#btn"},
            {"type": "click", "value": "#btn"},
        ]
        original = [{"type": "click", "value": "#btn"}]
        matched, extra = diff_ops(agent, original)
        assert len(matched) == 1
        assert len(extra) == 1

    def test_empty_inputs(self):
        matched, extra = diff_ops([], [])
        assert matched == []
        assert extra == []

    def test_index_tracking(self):
        agent = [
            {"type": "goto", "value": "https://x.com"},
            {"type": "fill", "value": "#input", "selectors": ["#input"]},
            {"type": "click", "value": "#btn"},
        ]
        original = [
            {"type": "goto", "value": "https://x.com"},
            {"type": "click", "value": "#btn"},
        ]
        matched, extra = diff_ops(agent, original)
        # Extra op (fill) should have index 1
        assert extra[0]["_index"] == 1


# ── filter_rejected ───────────────────────────────────────────


class TestFilterRejected:
    def test_no_rejected_file(self, tmp_path):
        ops = [{"type": "click", "value": "#btn"}]
        filtered = filter_rejected("nonexistent", ops)
        assert filtered == ops

    def test_malformed_rejected_file(self, tmp_path):
        rejected_dir = tmp_path / "logs" / "learn" / "test_pipe"
        rejected_dir.mkdir(parents=True, exist_ok=True)
        (rejected_dir / "rejected.json").write_text("not valid json", encoding="utf-8")
        ops = [{"type": "click", "value": "#btn"}]
        filtered = filter_rejected("test_pipe", ops)
        assert filtered == ops  # Should return ops unchanged on parse error

    def test_filters_blocked_ops(self, tmp_path, monkeypatch):
        rejected_dir = tmp_path / "logs" / "learn" / "test_pipe"
        rejected_dir.mkdir(parents=True, exist_ok=True)
        rejected_data = {
            "pipeline": "test_pipe",
            "blocked": [
                {"selector": "#btn", "type": "click"},
                {"selector": "#bad", "type": "fill"},
            ],
        }
        (rejected_dir / "rejected.json").write_text(json.dumps(rejected_data), encoding="utf-8")

        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        ops = [
            {"type": "click", "value": "#btn"},
            {"type": "goto", "value": "https://x.com"},
            {"type": "fill", "value": "#bad"},
        ]
        filtered = filter_rejected("test_pipe", ops)
        assert len(filtered) == 1
        assert filtered[0]["type"] == "goto"

    def test_empty_ops(self):
        filtered = filter_rejected("test", [])
        assert filtered == []


# ── add_to_rejected ───────────────────────────────────────────


class TestAddToRejected:
    def test_creates_new_rejected_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        ops = [{"type": "click", "value": "#btn", "reason": "test rejection"}]
        add_to_rejected("test_pipe", ops, "test_user")

        rejected_path = tmp_path / "logs" / "learn" / "test_pipe" / "rejected.json"
        assert rejected_path.exists()
        data = json.loads(rejected_path.read_text(encoding="utf-8"))
        assert data["pipeline"] == "test_pipe"
        assert len(data["blocked"]) == 1
        assert data["blocked"][0]["selector"] == "#btn"
        assert data["blocked"][0]["type"] == "click"
        assert data["blocked"][0]["rejected_by"] == "test_user"

    def test_appends_to_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        existing = {"pipeline": "test_pipe", "blocked": [{"selector": "#old", "type": "click"}]}
        rdir = tmp_path / "logs" / "learn" / "test_pipe"
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / "rejected.json").write_text(json.dumps(existing), encoding="utf-8")

        add_to_rejected("test_pipe", [{"type": "fill", "value": "#new"}], "user")
        data = json.loads((rdir / "rejected.json").read_text(encoding="utf-8"))
        assert len(data["blocked"]) == 2

    def test_empty_reason_defaults(self, tmp_path, monkeypatch):
        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        add_to_rejected("test_pipe", [{"type": "click", "value": "#btn"}], "tester")
        rejected_path = tmp_path / "logs" / "learn" / "test_pipe" / "rejected.json"
        data = json.loads(rejected_path.read_text(encoding="utf-8"))
        assert data["blocked"][0]["reason"] == "rejected"


# ── save_suggestions ──────────────────────────────────────────


class TestSaveSuggestions:
    def test_saves_new_suggestion(self, tmp_path, monkeypatch):
        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        ops = [{"type": "click", "value": "#new_btn"}]
        sid = save_suggestions(ops, "test_pipe", "pending", "Found new ops")

        sug_path = tmp_path / "logs" / "learn" / "test_pipe" / "suggestions.json"
        assert sug_path.exists()
        data = json.loads(sug_path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["id"] == sid
        assert data[0]["status"] == "pending"
        assert data[0]["reason"] == "Found new ops"
        assert data[0]["extra_ops"] == ops

    def test_appends_to_existing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        save_suggestions([], "test_pipe", "pending", "first")
        save_suggestions([], "test_pipe", "accepted", "second")

        sug_path = tmp_path / "logs" / "learn" / "test_pipe" / "suggestions.json"
        data = json.loads(sug_path.read_text(encoding="utf-8"))
        assert len(data) == 2

    def test_with_interrupt_reason(self, tmp_path, monkeypatch):
        monkeypatch.setattr("yak_browser_use.compiler.diff.LEARN_DIR", tmp_path / "logs" / "learn")
        sid = save_suggestions([], "test_pipe", "interrupted", "Interrupted",
                               interrupt_reason="user cancelled")
        sug_path = tmp_path / "logs" / "learn" / "test_pipe" / "suggestions.json"
        data = json.loads(sug_path.read_text(encoding="utf-8"))
        assert data[0]["interrupt_reason"] == "user cancelled"


# ── merge_extra_ops ───────────────────────────────────────────


class TestMergeExtraOps:
    def test_simple_merge(self):
        matched = [{"type": "goto", "_index": 0}]
        extra = [{"type": "click", "_index": 1}]
        merged = merge_extra_ops(matched, extra)
        assert len(merged) == 2
        assert merged[0]["type"] == "goto"
        assert merged[1]["type"] == "click"

    def test_interleaved_by_index(self):
        matched = [{"type": "goto", "_index": 0}, {"type": "click", "_index": 2}]
        extra = [{"type": "fill", "_index": 1}]
        merged = merge_extra_ops(matched, extra)
        assert len(merged) == 3
        assert [op["type"] for op in merged] == ["goto", "fill", "click"]

    def test_empty_matched(self):
        merged = merge_extra_ops([], [{"type": "click", "_index": 0}])
        assert len(merged) == 1

    def test_all_empty(self):
        assert merge_extra_ops([], []) == []


# ── extract_summary ───────────────────────────────────────────


class TestExtractSummary:
    def test_basic_ops(self):
        ops = [
            {"type": "goto", "value": "https://example.com"},
            {"type": "click", "value": "#btn"},
        ]
        summary = extract_summary(ops)
        assert "goto" in summary
        assert "click" in summary
        assert "example.com" in summary or "#btn" in summary

    def test_op_without_value(self):
        ops = [{"type": "snapshot"}]
        assert extract_summary(ops) == "snapshot"

    def test_op_with_selector(self):
        ops = [{"type": "fill", "selector": "#input"}]
        assert "fill" in extract_summary(ops)
        assert "#input" in extract_summary(ops)

    def test_empty_ops(self):
        assert extract_summary([]) == "(empty)"

    def test_value_truncation(self):
        long_val = "a" * 100
        ops = [{"type": "goto", "value": long_val}]
        summary = extract_summary(ops)
        assert len(summary) < 60  # truncated to 40 chars

    def test_mixed_types(self):
        ops = [
            {"type": "goto", "value": "https://x.com"},
            {"type": "click", "value": "#btn"},
            {"type": "fill", "selector": "#q", "value": "text"},
            {"type": "snapshot"},
        ]
        summary = extract_summary(ops)
        for op_type in ("goto", "click", "fill", "snapshot"):
            assert op_type in summary
