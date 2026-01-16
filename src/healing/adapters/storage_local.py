"""Local filesystem storage adapter."""

import fnmatch
from pathlib import Path
from typing import Optional

from .base import StorageAdapter


class LocalStorageAdapter(StorageAdapter):
    """Local filesystem implementation of StorageAdapter."""

    def __init__(self, base_path: Optional[Path] = None):
        """Initialize local storage adapter.

        Args:
            base_path: Base directory for file operations. Defaults to cwd.
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def _resolve_path(self, path: str) -> Path:
        """Resolve relative path to absolute path within base."""
        return self.base_path / path

    async def read_file(self, path: str) -> str:
        """Read file content from local filesystem."""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return full_path.read_text()

    async def write_file(self, path: str, content: str) -> None:
        """Write file content to local filesystem."""
        full_path = self._resolve_path(path)
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    async def file_exists(self, path: str) -> bool:
        """Check if file exists in local filesystem."""
        full_path = self._resolve_path(path)
        return full_path.exists()

    async def list_files(self, pattern: str) -> list[str]:
        """List files matching glob pattern in local filesystem."""
        matching_files = []

        # Handle recursive patterns with **
        if "**" in pattern:
            for file_path in self.base_path.rglob(pattern.replace("**", "*")):
                if file_path.is_file():
                    matching_files.append(str(file_path.relative_to(self.base_path)))
        else:
            for file_path in self.base_path.glob(pattern):
                if file_path.is_file():
                    matching_files.append(str(file_path.relative_to(self.base_path)))

        return matching_files
