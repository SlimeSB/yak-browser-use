"""Tests for engine.delivery — delivery report writer."""

from __future__ import annotations

from pathlib import Path

import pytest

from yak_browser_use.engine.delivery import write_delivery_report


class TestWriteDeliveryReport:
    def test_writes_report_file(self, tmp_path):
        result = write_delivery_report(
            step_dir=tmp_path,
            pipeline_name="test_pipe",
            step_name="step_1",
            goal_description="Navigate to site",
            status="completed",
            duration_ms=1234,
        )
        assert result == tmp_path / "delivery-report.md"
        assert result.exists()

    def test_content_structure(self, tmp_path):
        write_delivery_report(
            step_dir=tmp_path,
            pipeline_name="my_pipeline",
            step_name="search_step",
            goal_description="Search for keyword",
            status="completed",
            duration_ms=500,
        )
        content = (tmp_path / "delivery-report.md").read_text(encoding="utf-8")
        assert "search_step" in content
        assert "my_pipeline" in content
        assert "Search for keyword" in content
        assert "completed" in content
        assert "500ms" in content or "500" in content

    def test_with_saved_version(self, tmp_path):
        write_delivery_report(
            step_dir=tmp_path,
            pipeline_name="test",
            step_name="s1",
            goal_description="test",
            status="completed",
            duration_ms=100,
            saved_version="v2",
        )
        content = (tmp_path / "delivery-report.md").read_text(encoding="utf-8")
        assert "v2" in content

    def test_without_saved_version(self, tmp_path):
        write_delivery_report(
            step_dir=tmp_path,
            pipeline_name="test",
            step_name="s1",
            goal_description="test",
            status="completed",
            duration_ms=100,
        )
        content = (tmp_path / "delivery-report.md").read_text(encoding="utf-8")
        assert "Saved Version" not in content

    def test_all_status_icons(self, tmp_path):
        for status in ("completed", "partial", "failed", "interrupted"):
            d = tmp_path / status
            d.mkdir(exist_ok=True)
            write_delivery_report(
                step_dir=d,
                pipeline_name="test",
                step_name="s1",
                goal_description="test",
                status=status,
                duration_ms=50,
            )
            content = (d / "delivery-report.md").read_text(encoding="utf-8")
            assert status in content

    def test_unknown_status_uses_question_mark(self, tmp_path):
        write_delivery_report(
            step_dir=tmp_path,
            pipeline_name="test",
            step_name="s1",
            goal_description="test",
            status="unknown_status",
            duration_ms=0,
        )
        content = (tmp_path / "delivery-report.md").read_text(encoding="utf-8")
        # Unknown status icon is ❓
        assert "❓" in content or "?" in content
