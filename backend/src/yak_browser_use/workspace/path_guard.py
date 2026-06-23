"""PathGuard — validates file paths are within the workspace root or run directory.

Prevents path traversal attacks.
"""
from __future__ import annotations

from pathlib import Path

from yak_browser_use.utils.logging import get_logger

logger = get_logger(__name__)


class PathGuard:
    """Validates that file paths do not escape the workspace or run directory."""

    def __init__(self, workspace_root: Path, run_dir: Path):
        self._workspace_root = workspace_root.resolve()
        self._run_dir = run_dir.resolve()

    def _check_allowed(self, path: str | Path) -> bool:
        """Check if the resolved path is under the workspace root or run dir."""
        resolved = Path(path).resolve()
        for allowed_root in (self._workspace_root, self._run_dir):
            try:
                resolved.relative_to(allowed_root)
                return True
            except ValueError:
                continue
        logger.warning("path_guard: blocked escape attempt: %s", path)
        return False

    def validate_input(self, path: str | Path) -> Path:
        """Validate an input path is within the workspace or run directory.

        Raises PermissionError if path escapes.
        """
        resolved = Path(path).resolve()
        if not self._check_allowed(resolved):
            raise PermissionError(
                f"Path security check failed: {path} is not inside workspace "
                f"{self._workspace_root} or run directory {self._run_dir}"
            )
        return resolved

    def validate_output_dir(self, output_dir: str | Path) -> Path:
        """Validate an output directory is within the run directory.

        Raises PermissionError if path escapes.
        """
        resolved = Path(output_dir).resolve()
        try:
            resolved.relative_to(self._run_dir)
        except ValueError:
            raise PermissionError(
                f"Output directory check failed: {output_dir} is not inside "
                f"run directory {self._run_dir}"
            )
        return resolved
