"""
Review context collector.

Gathers repository context for review prompts in API mode.
In CLI mode, the tools (Codex/Gemini) access the repo directly.
"""

import os
import re
import subprocess
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ReviewContextError(Exception):
    """Error collecting review context."""
    pass


@dataclass
class ReviewContext:
    """Context gathered for a review."""
    git_diff: str = ""
    changed_files: dict[str, str] = field(default_factory=dict)  # path -> content
    related_files: dict[str, str] = field(default_factory=dict)  # path -> content
    architecture_docs: Optional[str] = None
    context_summary: Optional[str] = None  # For holistic review
    project_context: Optional[str] = None  # Project type and build info
    truncated: bool = False
    truncation_warning: Optional[str] = None

    def total_size(self) -> int:
        """Approximate total context size in characters."""
        size = len(self.git_diff)
        size += sum(len(c) for c in self.changed_files.values())
        size += sum(len(c) for c in self.related_files.values())
        if self.architecture_docs:
            size += len(self.architecture_docs)
        if self.context_summary:
            size += len(self.context_summary)
        return size

    def format_changed_files(self) -> str:
        """Format changed files for prompt insertion."""
        if not self.changed_files:
            return "(no changed files)"

        parts = []
        for path, content in self.changed_files.items():
            parts.append(f"### {path}\n```\n{content}\n```")
        return "\n\n".join(parts)

    def format_related_files(self) -> str:
        """Format related files for prompt insertion."""
        if not self.related_files:
            return "(no related files identified)"

        parts = []
        for path, content in self.related_files.items():
            parts.append(f"### {path}\n```\n{content}\n```")
        return "\n\n".join(parts)


class ReviewContextCollector:
    """
    Collects repository context for review prompts.

    Used in API mode where the model doesn't have direct repo access.
    """

    # Default context limit (approximate tokens, assuming ~4 chars/token)
    DEFAULT_CONTEXT_LIMIT = 100000  # ~25K tokens
    MAX_FILE_SIZE = 50000  # Skip files larger than this

    def __init__(
        self,
        working_dir: Path,
        context_limit: Optional[int] = None,
        base_branch: str = "main"
    ):
        self.working_dir = Path(working_dir).resolve()
        self.context_limit = context_limit or self.DEFAULT_CONTEXT_LIMIT
        self.base_branch = base_branch

    def collect(self, review_type: str) -> ReviewContext:
        """
        Collect context appropriate for the review type.

        Args:
            review_type: One of "security", "consistency", "quality", "holistic"

        Returns:
            ReviewContext with gathered information
        """
        context = ReviewContext()

        # Always get project context (type, build system, etc.)
        context.project_context = self._detect_project_context()

        # Always get git diff and changed files
        context.git_diff = self._get_git_diff()
        context.changed_files = self._get_changed_file_contents()

        # Consistency and holistic reviews need related files
        if review_type in ("consistency", "consistency_review", "holistic", "holistic_review"):
            context.related_files = self._get_related_files(context.changed_files)

        # Try to get architecture docs for consistency review
        if review_type in ("consistency", "consistency_review"):
            context.architecture_docs = self._get_architecture_docs()

        # For holistic review, add any context summary
        if review_type in ("holistic", "holistic_review"):
            context.context_summary = self._get_context_summary()

        # Truncate if needed
        self._truncate_if_needed(context)

        return context

    def _detect_project_context(self) -> str:
        """Detect project type and build configuration."""
        indicators = []

        # Check for Python
        if (self.working_dir / "requirements.txt").exists():
            indicators.append("Python project (requirements.txt)")
        if (self.working_dir / "pyproject.toml").exists():
            indicators.append("Python project (pyproject.toml)")
        if (self.working_dir / "setup.py").exists():
            indicators.append("Python project (setup.py)")

        # Check for Node.js
        if (self.working_dir / "package.json").exists():
            indicators.append("Node.js project (package.json)")

        # Check for Go
        if (self.working_dir / "go.mod").exists():
            indicators.append("Go project (go.mod)")

        # Check for Rust
        if (self.working_dir / "Cargo.toml").exists():
            indicators.append("Rust project (Cargo.toml)")

        # Check for Java/Kotlin
        if (self.working_dir / "pom.xml").exists():
            indicators.append("Java/Maven project (pom.xml)")
        if (self.working_dir / "build.gradle").exists():
            indicators.append("Java/Gradle project (build.gradle)")

        # Check for Ruby
        if (self.working_dir / "Gemfile").exists():
            indicators.append("Ruby project (Gemfile)")

        # Check for Docker
        if (self.working_dir / "Dockerfile").exists():
            indicators.append("Uses Docker")
        if (self.working_dir / "docker-compose.yml").exists():
            indicators.append("Uses Docker Compose")

        if not indicators:
            return "Project type: Unknown (no standard build files detected)"

        return "Project type: " + ", ".join(indicators)

    def _run_git(self, *args: str) -> str:
        """Run a git command and return output."""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logger.warning(f"git {' '.join(args)} failed: {result.stderr}")
                return ""
            return result.stdout
        except subprocess.TimeoutExpired:
            logger.warning(f"git {' '.join(args)} timed out")
            return ""
        except FileNotFoundError:
            raise ReviewContextError("git not found. Is git installed?")

    def _get_git_diff(self) -> str:
        """Get git diff for current changes."""
        # Try diff against base branch first
        diff = self._run_git("diff", f"{self.base_branch}...HEAD")

        # If empty, try uncommitted changes
        if not diff.strip():
            diff = self._run_git("diff", "HEAD")

        # If still empty, try staged changes
        if not diff.strip():
            diff = self._run_git("diff", "--cached")

        # If still empty, try all changes including untracked
        if not diff.strip():
            diff = self._run_git("diff")

        return diff

    def _get_changed_file_paths(self) -> list[str]:
        """Get list of changed file paths."""
        # Get files changed compared to base branch
        output = self._run_git("diff", "--name-only", f"{self.base_branch}...HEAD")
        paths = [p.strip() for p in output.strip().split("\n") if p.strip()]

        # Also include uncommitted changes
        uncommitted = self._run_git("diff", "--name-only", "HEAD")
        paths.extend([p.strip() for p in uncommitted.strip().split("\n") if p.strip()])

        # Also include staged changes
        staged = self._run_git("diff", "--name-only", "--cached")
        paths.extend([p.strip() for p in staged.strip().split("\n") if p.strip()])

        # Deduplicate while preserving order
        seen = set()
        unique_paths = []
        for p in paths:
            if p and p not in seen:
                seen.add(p)
                unique_paths.append(p)

        return unique_paths

    def _get_changed_file_contents(self) -> dict[str, str]:
        """Get content of changed files."""
        contents = {}
        paths = self._get_changed_file_paths()

        for path in paths:
            file_path = self.working_dir / path
            if not file_path.exists():
                continue

            # Skip binary files and large files
            if file_path.stat().st_size > self.MAX_FILE_SIZE:
                contents[path] = f"(file too large: {file_path.stat().st_size} bytes)"
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                contents[path] = content
            except UnicodeDecodeError:
                contents[path] = "(binary file)"
            except Exception as e:
                contents[path] = f"(error reading file: {e})"

        return contents

    def _get_related_files(self, changed_files: dict[str, str]) -> dict[str, str]:
        """
        Get files related to the changed files (imports, dependencies).

        This is a best-effort analysis using regex patterns.
        """
        related = {}
        import_patterns = [
            # Python: from X import Y, import X
            r'(?:from|import)\s+([\w.]+)',
            # JavaScript/TypeScript: import X from "Y"
            r'import\s+.*?\s+from\s+["\']([^"\']+)["\']',
            # JavaScript/TypeScript: require("X")
            r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
            # Go: import "X"
            r'import\s+["\']([^"\']+)["\']',
        ]

        imported_modules = set()

        for path, content in changed_files.items():
            if content.startswith("("):  # Skip error placeholders
                continue

            for pattern in import_patterns:
                for match in re.finditer(pattern, content):
                    module = match.group(1)
                    imported_modules.add(module)

        # Try to resolve imports to files
        for module in imported_modules:
            # Skip standard library / external packages
            if module.startswith(("os", "sys", "re", "json", "typing", "datetime",
                                   "pathlib", "subprocess", "logging", "dataclasses",
                                   "enum", "abc", "functools", "collections",
                                   "react", "vue", "angular", "@", "lodash", "axios")):
                continue

            # Try to find the file
            possible_paths = [
                f"{module.replace('.', '/')}.py",
                f"{module.replace('.', '/')}/index.py",
                f"{module.replace('.', '/')}/__init__.py",
                f"{module}.ts",
                f"{module}.js",
                f"{module}/index.ts",
                f"{module}/index.js",
                f"src/{module.replace('.', '/')}.py",
                f"src/{module}.ts",
                f"src/{module}.js",
            ]

            for possible_path in possible_paths:
                file_path = self.working_dir / possible_path
                if file_path.exists() and possible_path not in changed_files:
                    try:
                        if file_path.stat().st_size <= self.MAX_FILE_SIZE:
                            related[possible_path] = file_path.read_text(encoding="utf-8")
                            break
                    except Exception:
                        pass

        return related

    def _get_architecture_docs(self) -> Optional[str]:
        """Load architecture documentation if available."""
        doc_paths = [
            "ARCHITECTURE.md",
            "docs/ARCHITECTURE.md",
            "docs/architecture.md",
            "DESIGN.md",
            "docs/DESIGN.md",
            "README.md",  # Often contains architecture overview
        ]

        for doc_path in doc_paths:
            file_path = self.working_dir / doc_path
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    # Truncate if too long
                    if len(content) > 10000:
                        content = content[:10000] + "\n\n... (truncated)"
                    return content
                except Exception:
                    pass

        return None

    def _get_context_summary(self) -> Optional[str]:
        """Get a summary of the repository context for holistic review."""
        parts = []

        # Get recent commit messages for context
        log = self._run_git("log", "--oneline", "-10")
        if log:
            parts.append(f"## Recent Commits\n{log}")

        # Get list of directories for structure overview
        try:
            dirs = []
            for item in self.working_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    dirs.append(item.name + "/")
            if dirs:
                parts.append(f"## Project Structure\n" + "\n".join(sorted(dirs)))
        except Exception:
            pass

        return "\n\n".join(parts) if parts else None

    def _truncate_if_needed(self, context: ReviewContext):
        """Truncate context if it exceeds the limit."""
        if context.total_size() <= self.context_limit:
            return

        context.truncated = True
        original_size = context.total_size()

        # Priority: keep changed files, truncate related files first
        if context.related_files:
            # Keep only most relevant related files
            sorted_related = sorted(
                context.related_files.items(),
                key=lambda x: len(x[1])  # Smaller files first
            )
            context.related_files = {}
            for path, content in sorted_related:
                if context.total_size() + len(content) > self.context_limit * 0.8:
                    break
                context.related_files[path] = content

        # Truncate architecture docs
        if context.architecture_docs and context.total_size() > self.context_limit * 0.9:
            context.architecture_docs = context.architecture_docs[:5000] + "\n\n... (truncated)"

        # Truncate git diff if still too large
        if context.git_diff and context.total_size() > self.context_limit:
            max_diff = self.context_limit // 3
            context.git_diff = context.git_diff[:max_diff] + "\n\n... (diff truncated)"

        context.truncation_warning = (
            f"Context truncated from {original_size} to {context.total_size()} characters. "
            "Some related files may be missing."
        )
