"""Tests for TodoStore data class."""

import json

import pytest

from yak_browser_use.tools.todo_store import MAX_ITEMS, MAX_CONTENT_CHARS, TodoStore


class TestTodoStore:
    def test_write_read(self):
        store = TodoStore()
        items = [{"id": "1", "content": "任务一", "status": "pending"}]
        result = store.write(items)
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert result[0]["content"] == "任务一"
        assert result[0]["status"] == "pending"

    def test_read_empty(self):
        store = TodoStore()
        assert store.read() == []

    def test_merge_update_by_id(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "旧描述", "status": "pending"}])
        result = store.write(
            [{"id": "1", "content": "新描述"}],
            merge=True,
        )
        assert len(result) == 1
        assert result[0]["id"] == "1"
        assert result[0]["content"] == "新描述"
        assert result[0]["status"] == "pending"

    def test_merge_append_new(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "任务一"}])
        result = store.write(
            [{"id": "2", "content": "任务二", "status": "in_progress"}],
            merge=True,
        )
        assert len(result) == 2
        ids = [item["id"] for item in result]
        assert "1" in ids
        assert "2" in ids

    def test_dedupe_by_id(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "任务一"}])
        result = store.write(
            [{"id": "1", "content": "任务一重复"}],
            merge=True,
        )
        assert len(result) == 1
        assert result[0]["content"] == "任务一重复"

    def test_cap_content(self):
        store = TodoStore()
        long_content = "x" * (MAX_CONTENT_CHARS + 100)
        result = store.write([{"id": "1", "content": long_content}])
        assert len(result[0]["content"]) <= MAX_CONTENT_CHARS
        assert "[truncated]" in result[0]["content"]

    def test_invalid_status(self):
        store = TodoStore()
        result = store.write([{"id": "1", "content": "test", "status": "invalid_status"}])
        assert result[0]["status"] == "pending"

    def test_valid_statuses(self):
        store = TodoStore()
        for status in ("pending", "in_progress", "completed", "cancelled"):
            result = store.write([{"id": "1", "content": "test", "status": status}])
            assert result[0]["status"] == status

    def test_auto_generate_id(self):
        store = TodoStore()
        result = store.write([{"content": "无 id 任务"}])
        assert result[0]["id"]
        assert isinstance(result[0]["id"], str)
        assert len(result[0]["id"]) == 8

    def test_empty_content_default(self):
        store = TodoStore()
        result = store.write([{"id": "1", "status": "pending"}])
        assert result[0]["content"] == "(no description)"

    def test_todos_not_list_ignored(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "任务一"}])
        result = store.write("not a list")
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_merge_not_bool_treated_as_false(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "旧"}])
        result = store.write(
            [{"id": "2", "content": "新"}],
            merge="yes",
        )
        assert len(result) == 1
        assert result[0]["id"] == "2"

    def test_cap_items(self):
        store = TodoStore()
        items = [{"id": str(i), "content": f"任务{i}"} for i in range(MAX_ITEMS + 10)]
        result = store.write(items)
        assert len(result) == MAX_ITEMS

    def test_clear(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "任务一"}])
        store.clear()
        assert store.read() == []

    def test_merge_preserves_unmatched(self):
        store = TodoStore()
        store.write([
            {"id": "1", "content": "任务一"},
            {"id": "2", "content": "任务二"},
        ])
        result = store.write(
            [{"id": "1", "content": "任务一更新"}],
            merge=True,
        )
        assert len(result) == 2
        assert result[0]["content"] == "任务一更新"
        assert result[1]["content"] == "任务二"

    def test_merge_preserves_status_when_not_provided(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "旧描述", "status": "in_progress"}])
        result = store.write(
            [{"id": "1", "content": "新描述"}],
            merge=True,
        )
        assert len(result) == 1
        assert result[0]["content"] == "新描述"
        assert result[0]["status"] == "in_progress"

    def test_merge_preserves_status_when_incoming_invalid(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "旧描述", "status": "in_progress"}])
        result = store.write(
            [{"id": "1", "content": "新描述", "status": "bad_status"}],
            merge=True,
        )
        assert len(result) == 1
        assert result[0]["content"] == "新描述"
        assert result[0]["status"] == "in_progress"

    def test_todos_none_reads_only(self):
        store = TodoStore()
        store.write([{"id": "1", "content": "任务一"}])
        result = store.write(None)
        assert len(result) == 1
        assert result[0]["id"] == "1"
