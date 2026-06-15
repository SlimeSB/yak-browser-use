"""PathGuard — validates file paths are within the workspace root or run directory.

Prevents path traversal attacks.
"""
from __future__ import annotations

from pathlib import Path

from utils.logging import get_logger

logger = get_logger(__name__)


class PathGuard:
    """Validates that file paths do not escape the workspace or run directory."""

    def __init__(self, workspace_root: Path, run_dir: Path):
        self._workspace_root = workspace_root.resolve()
        self._run_dir = run_dir.resolve()

    def _check_allowed(self, path: str | Path) -> bool:
        """Check if the resolved path is under the workspace root or run dir."""
        resolved = Path(path).resolve()
        allowed = (
            str(resolved).startswith(str(self._workspace_root))
            or str(resolved).startswith(str(self._run_dir))
        )
        if not allowed:
            logger.warning("path_guard: blocked escape attempt: %s", path)
        return allowed

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
        if ".." in str(path):
            raise PermissionError(
                f"Path security check failed: {path} contains forbidden relative path '..'"
            )
        return resolved

    def validate_output_dir(self, output_dir: str | Path) -> Path:
        """Validate an output directory is within the run directory.

        Raises PermissionError if path escapes.
        """
        resolved = Path(output_dir).resolve()
        if not str(resolved).startswith(str(self._run_dir)):
            raise PermissionError(
                f"Output directory check failed: {output_dir} is not inside "
                f"run directory {self._run_dir}"
            )
        return resolved
