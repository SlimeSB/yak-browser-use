"""VersionManager — manages version snapshots.

Versions stored in: ~/.ybu/workspaces/<pipeline_name>/versions/<N>/
LATEST file tracks the current version.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


class VersionManager:
    """Manages versions/ directory: version snapshots, LATEST, STALE."""

    def __init__(self, versions_dir: Path, pipeline_name: str):
        self.versions_dir = versions_dir
        self.pipeline_name = pipeline_name
        self.latest_file = versions_dir / "LATEST"
        self.stale_file = versions_dir / "STALE"

    def ensure(self) -> Path:
        """Create the versions directory if it doesn't exist."""
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        return self.versions_dir

    # ── LATEST ──

    def get_latest(self) -> str | None:
        """Return the latest version string, or None."""
        if self.latest_file.exists():
            return self.latest_file.read_text(encoding="utf-8").strip()
        return None

    def set_latest(self, version: str) -> None:
        """Write the version string to LATEST."""
        self.latest_file.write_text(str(version), encoding="utf-8")

    # ── version snapshot ──

    def create_version(
        self,
        trigger_run_id: str,
        summary: str,
        pipe_pipeline: Path,
        tools_dir: Path,
        upgraded_tools: list[str] | None = None,
        learned_goals: list[str] | None = None,
    ) -> str:
        """Create a new version snapshot with metadata."""
        self.ensure()
        version = str(self._next_version())
        ver_dir = self.versions_dir / version
        ver_dir.mkdir(parents=True, exist_ok=True)

        if pipe_pipeline.exists():
            shutil.copy2(pipe_pipeline, ver_dir / "pipe.pipeline.yaml")

        ver_tools = ver_dir / "tools"
        ver_tools.mkdir(exist_ok=True)
        if tools_dir.exists():
            for f in tools_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, ver_tools / f.name)

        meta: dict[str, object] = {
            "version": version,
            "created_at": _now_iso(),
            "trigger_run_id": trigger_run_id,
            "summary": summary,
        }
        if upgraded_tools:
            meta["upgraded_tools"] = upgraded_tools
        if learned_goals:
            meta["learned_goals"] = learned_goals
        with open(ver_dir / "version.meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        self.set_latest(version)
        logger.info(
            "version: created %s v%s (trigger: %s)",
            self.pipeline_name, version, trigger_run_id,
        )
        return version

    def load_version(self, version: str) -> tuple[Path, Path] | None:
        """Load a version's pipeline.yaml and tools directory.

        Returns (pipeline_path, tools_dir_path) or None.
        """
        ver_dir = self.versions_dir / version
        agent_path = ver_dir / "pipe.pipeline.yaml"
        tools_path = ver_dir / "tools"
        if agent_path.exists():
            return agent_path, tools_path
        return None

    def list_versions(self) -> list[dict]:
        """List all version metadata dicts sorted by version number."""
        result = []
        for d in sorted(self.versions_dir.iterdir()):
            if d.is_dir() and d.name.isdigit():
                meta_path = d / "version.meta.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            result.append(json.load(f))
                    except json.JSONDecodeError:
                        pass
        return result

    def get_version(self, name: str, v: str) -> dict | None:
        """Convenience: load a specific version's metadata for a pipeline name.

        Returns the version meta dict or None if not found.
        """
        for d in self.versions_dir.iterdir():
            if d.name == v and d.is_dir():
                meta_path = d / "version.meta.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except json.JSONDecodeError:
                        return None
        return None

    # ── STALE ──

    def is_stale(self) -> bool:
        """Check if this pipeline has been marked stale."""
        return self.stale_file.exists()

    def mark_stale(self) -> None:
        """Mark this pipeline as stale (no longer active)."""
        self.stale_file.write_text("", encoding="utf-8")
        logger.warning("version: %s marked STALE", self.pipeline_name)

    def clear_stale(self) -> None:
        """Clear the stale marker."""
        if self.stale_file.exists():
            self.stale_file.unlink()
            logger.info("version: %s STALE cleared", self.pipeline_name)

    # ── version trigger ──

    def try_create_version(
        self,
        trigger_run_id: str,
        upgraded_tools: list[str] | None = None,
        learned_goals: list[str] | None = None,
        pipe_pipeline: Path | None = None,
        tools_dir: Path | None = None,
    ) -> str | None:
        """Auto-create a version snapshot if there are upgrades or learned goals.

        Returns the version string, or None if no version was created.
        """
        if not upgraded_tools and not learned_goals:
            logger.info(
                "version: %s no upgrades or learned goals, skip versioning",
                self.pipeline_name,
            )
            return None

        if not pipe_pipeline or not pipe_pipeline.exists():
            logger.info("version: %s no pipeline.yaml, skip versioning", self.pipeline_name)
            return None

        parts = []
        if upgraded_tools:
            parts.append(f"upgraded tools: {', '.join(upgraded_tools)}")
        if learned_goals:
            parts.append(f"learned goals: {', '.join(learned_goals)}")
        summary = "; ".join(parts)

        version = self.create_version(
            trigger_run_id,
            summary,
            pipe_pipeline,
            tools_dir or Path(),
            upgraded_tools=upgraded_tools,
            learned_goals=learned_goals,
        )
        logger.info(
            "version: %s created v%s for run %s",
            self.pipeline_name, version, trigger_run_id,
        )
        return version

    def save_snapshot(self, pipeline_text: str, summary: str = "chat-edit") -> str:
        """Save a manual snapshot of the agent prompt."""
        self.ensure()
        version = str(self._next_version())
        ver_dir = self.versions_dir / version
        ver_dir.mkdir(parents=True, exist_ok=True)

        pipe_path = ver_dir / "pipe.pipeline.yaml"
        pipe_path.write_text(pipeline_text, encoding="utf-8")

        meta: dict[str, object] = {
            "version": version,
            "created_at": _now_iso(),
            "summary": summary,
        }
        with open(ver_dir / "version.meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        self.set_latest(version)
        logger.info("version: snapshot %s v%s (%s)", self.pipeline_name, version, summary)
        return version

    def _next_version(self) -> int:
        versions = []
        for d in self.versions_dir.iterdir():
            if d.is_dir() and d.name.isdigit():
                versions.append(int(d.name))
        return max(versions) + 1 if versions else 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
