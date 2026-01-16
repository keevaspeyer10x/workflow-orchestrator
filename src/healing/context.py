"""Context retrieval for fix generation.

This module retrieves file context needed for generating and applying fixes.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .adapters.base import StorageAdapter
    from .models import ErrorEvent, FixAction


logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context for a single file."""

    path: str
    content: str
    exists: bool = True
    error: Optional[str] = None


@dataclass
class ContextBundle:
    """Bundle of context for fix generation/application."""

    error_file: Optional[FileContext] = None
    context_files: List[FileContext] = field(default_factory=list)
    related_files: List[FileContext] = field(default_factory=list)

    @property
    def all_files(self) -> List[FileContext]:
        """Get all files in the context."""
        files = []
        if self.error_file:
            files.append(self.error_file)
        files.extend(self.context_files)
        files.extend(self.related_files)
        return files

    def to_prompt_context(self) -> str:
        """Format context for LLM prompt."""
        parts = []

        if self.error_file and self.error_file.exists:
            parts.append(f"## {self.error_file.path}\n```\n{self.error_file.content}\n```")

        for ctx in self.context_files:
            if ctx.exists:
                parts.append(f"## {ctx.path}\n```\n{ctx.content}\n```")

        for rel in self.related_files:
            if rel.exists:
                parts.append(f"## {rel.path} (related)\n```\n{rel.content}\n```")

        return "\n\n".join(parts)


class ContextRetriever:
    """Retrieve file context for fix generation.

    This class gathers the necessary file context for:
    1. The file where the error occurred
    2. Files explicitly required by the fix action
    3. Related files (imports, tests, etc.)
    """

    def __init__(self, storage: "StorageAdapter"):
        """Initialize context retriever.

        Args:
            storage: Storage adapter for file operations
        """
        self.storage = storage

    async def get_context(
        self,
        error: "ErrorEvent",
        fix_action: Optional["FixAction"] = None,
        include_related: bool = True,
    ) -> ContextBundle:
        """Get relevant context for generating/applying a fix.

        Args:
            error: The error event
            fix_action: Optional fix action that may specify required files
            include_related: Whether to include related files

        Returns:
            ContextBundle with all relevant file context
        """
        bundle = ContextBundle()

        # Get error file content
        if error.file_path:
            bundle.error_file = await self._get_file_context(error.file_path)

        # Get context files from fix action
        if fix_action and fix_action.context_files:
            for path in fix_action.context_files:
                ctx = await self._get_file_context(path)
                bundle.context_files.append(ctx)

        # Get related files
        if include_related and error.file_path:
            related_paths = await self.get_related_files(error.file_path)
            for path in related_paths:
                # Don't duplicate files already in context
                existing_paths = {f.path for f in bundle.all_files}
                if path not in existing_paths:
                    rel = await self._get_file_context(path)
                    bundle.related_files.append(rel)

        return bundle

    async def get_related_files(self, file_path: str) -> List[str]:
        """Find related files (imports, tests, etc.).

        Args:
            file_path: Path to find related files for

        Returns:
            List of related file paths
        """
        related = []

        # Determine file type
        if file_path.endswith(".py"):
            related.extend(await self._get_python_related(file_path))
        elif file_path.endswith((".js", ".ts", ".jsx", ".tsx")):
            related.extend(await self._get_js_related(file_path))
        elif file_path.endswith(".go"):
            related.extend(await self._get_go_related(file_path))
        elif file_path.endswith(".rs"):
            related.extend(await self._get_rust_related(file_path))

        return related

    async def _get_file_context(self, path: str) -> FileContext:
        """Get context for a single file."""
        try:
            if await self.storage.file_exists(path):
                content = await self.storage.read_file(path)
                return FileContext(path=path, content=content)
            else:
                return FileContext(path=path, content="", exists=False)
        except Exception as e:
            logger.warning(f"Error reading file {path}: {e}")
            return FileContext(path=path, content="", exists=False, error=str(e))

    async def _get_python_related(self, file_path: str) -> List[str]:
        """Get related files for Python."""
        related = []

        # Find test file
        if not file_path.startswith("test_") and "test_" not in file_path:
            # Standard test naming conventions
            test_paths = [
                file_path.replace(".py", "_test.py"),
                file_path.replace(".py", ".test.py"),
                f"tests/{file_path}",
                f"tests/test_{file_path.split('/')[-1]}",
            ]
            for test_path in test_paths:
                if await self.storage.file_exists(test_path):
                    related.append(test_path)
                    break

        # Try to find imports (simplified - just local imports)
        try:
            content = await self.storage.read_file(file_path)
            imports = re.findall(r"from\s+(\.)(\w+)\s+import", content)
            for _, module in imports:
                # Convert module to path (simplified)
                import_path = f"{module}.py"
                if await self.storage.file_exists(import_path):
                    related.append(import_path)
        except Exception:
            pass

        return related

    async def _get_js_related(self, file_path: str) -> List[str]:
        """Get related files for JavaScript/TypeScript."""
        related = []

        # Find test file
        base = file_path.rsplit(".", 1)[0]  # Remove extension
        ext = file_path.rsplit(".", 1)[1] if "." in file_path else "js"

        test_paths = [
            f"{base}.test.{ext}",
            f"{base}.spec.{ext}",
            f"__tests__/{file_path.split('/')[-1]}",
        ]

        for test_path in test_paths:
            if await self.storage.file_exists(test_path):
                related.append(test_path)
                break

        return related

    async def _get_go_related(self, file_path: str) -> List[str]:
        """Get related files for Go."""
        related = []

        # Go test files are in the same directory with _test suffix
        if not file_path.endswith("_test.go"):
            test_path = file_path.replace(".go", "_test.go")
            if await self.storage.file_exists(test_path):
                related.append(test_path)

        return related

    async def _get_rust_related(self, file_path: str) -> List[str]:
        """Get related files for Rust."""
        related = []

        # Rust tests are often in the same file or in a tests/ directory
        if "/src/" in file_path:
            # Check for integration tests
            test_path = file_path.replace("/src/", "/tests/")
            if await self.storage.file_exists(test_path):
                related.append(test_path)

        return related
