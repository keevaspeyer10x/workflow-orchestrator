"""
Stage 1: Context Assembly

Gathers all context needed for conflict resolution:
- Agent manifests (from artifacts)
- Derived changes (from git diff) - verified against manifest
- Base commit state
- Conflicting file contents (base, agent versions)
- Related files (imports, callers)
- Project conventions
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from .schema import (
    ConflictContext,
    FileVersion,
    RelatedFile,
    ProjectConvention,
)
from ..conflict.pipeline import PipelineResult
from ..coordinator.schema import AgentManifest, DerivedManifest
from ..coordinator.manifest_store import ManifestStore

logger = logging.getLogger(__name__)


def _sanitize_filepath(filepath: str) -> str:
    """
    Sanitize a filepath by removing dangerous sequences.

    SECURITY: Prevents path traversal and injection attacks.
    """
    if not filepath:
        return ""

    # Remove null bytes (path injection)
    filepath = filepath.replace('\x00', '')

    # Normalize path separators
    filepath = filepath.replace('\\', '/')

    # Remove leading slashes (treat as relative)
    while filepath.startswith('/'):
        filepath = filepath[1:]

    # Collapse multiple slashes
    filepath = re.sub(r'/+', '/', filepath)

    # Remove leading/trailing whitespace
    filepath = filepath.strip()

    return filepath


def _validate_repo_path(filepath: str, repo_path: Path) -> bool:
    """
    Validate that a filepath is within repository bounds.

    SECURITY: Prevents path traversal attacks like:
    - ../../../etc/passwd
    - /etc/passwd (absolute paths)
    - .git/config (accessing git internals)

    Args:
        filepath: Path to validate (should be relative)
        repo_path: Root of the repository

    Returns:
        True if filepath is safe, False otherwise
    """
    if not filepath:
        return False

    # Reject absolute paths
    if filepath.startswith('/'):
        return False

    # Reject null bytes
    if '\x00' in filepath:
        return False

    # Reject .git access
    if '.git' in filepath.split('/'):
        return False

    # Normalize and check if path stays within repo
    try:
        # Resolve the path (handles ../ etc.)
        full_path = (repo_path / filepath).resolve()
        repo_resolved = repo_path.resolve()

        # Check that resolved path is within repo
        full_path.relative_to(repo_resolved)
        return True
    except (ValueError, RuntimeError, OSError):
        # relative_to() raises ValueError if not relative
        return False


class ContextAssembler:
    """
    Assembles complete context for conflict resolution.

    CRITICAL: Derives actual changes from git, doesn't trust manifests blindly.
    """

    def __init__(
        self,
        base_branch: str = "main",
        manifest_store: Optional[ManifestStore] = None,
        repo_path: Optional[Path] = None,
    ):
        self.base_branch = base_branch
        self.manifest_store = manifest_store or ManifestStore()
        self.repo_path = repo_path or Path.cwd()

    def assemble(
        self,
        detection_result: PipelineResult,
        agent_ids: Optional[list[str]] = None,
    ) -> ConflictContext:
        """
        Assemble complete context for resolution.

        Args:
            detection_result: Result from detection pipeline
            agent_ids: Optional list of agent IDs (derived from branches if not provided)

        Returns:
            ConflictContext with all gathered information
        """
        logger.info("Stage 1: Assembling conflict context")

        # Initialize context
        context = ConflictContext(
            detection_result=detection_result,
            base_branch=self.base_branch,
        )

        # Get base SHA
        context.base_sha = self._get_sha(self.base_branch)

        # Extract agent info from branches
        branches = detection_result.branches
        if not agent_ids:
            agent_ids = [self._extract_agent_id(b) for b in branches]

        # Map agents to branches
        for agent_id, branch in zip(agent_ids, branches):
            context.agent_branches[agent_id] = branch

        # Step 1: Load agent manifests (if available)
        logger.info("Loading agent manifests...")
        context.agent_manifests = self._load_manifests(agent_ids)

        # Step 2: Derive actual changes from git
        logger.info("Deriving changes from git...")
        context.derived_manifests = self._derive_manifests(agent_ids, branches)

        # Step 3: Get conflicting files content
        logger.info("Gathering file contents...")
        conflicting_files = self._get_conflicting_files(detection_result)
        context.base_files = self._get_base_files(conflicting_files)
        context.agent_files = self._get_agent_files(conflicting_files, agent_ids, branches)

        # Step 4: Find related files
        logger.info("Finding related files...")
        context.related_files = self._find_related_files(conflicting_files)

        # Step 5: Detect project conventions
        logger.info("Detecting project conventions...")
        context.conventions = self._detect_conventions(conflicting_files)

        logger.info(f"Context assembled: {len(conflicting_files)} conflicting files, "
                   f"{len(context.related_files)} related files")
        return context

    def _extract_agent_id(self, branch: str) -> str:
        """Extract agent ID from branch name."""
        # Branch format: claude/task-description-sessionid
        parts = branch.split("/")
        if len(parts) >= 2:
            # Last segment after last dash is session ID
            name_parts = parts[-1].rsplit("-", 1)
            if len(name_parts) == 2:
                return f"claude-{name_parts[1]}"
        return branch.replace("/", "-")

    def _get_sha(self, ref: str) -> str:
        """Get SHA for a git reference."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", ref],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to get SHA for {ref}: {e}")
        return ""

    def _load_manifests(self, agent_ids: list[str]) -> list[AgentManifest]:
        """Load agent manifests from storage."""
        manifests = []
        for agent_id in agent_ids:
            try:
                manifest = self.manifest_store.get_manifest(agent_id)
                if manifest:
                    manifests.append(manifest)
            except Exception as e:
                logger.warning(f"Could not load manifest for {agent_id}: {e}")
        return manifests

    def _derive_manifests(
        self,
        agent_ids: list[str],
        branches: list[str],
    ) -> list[DerivedManifest]:
        """
        Derive actual changes from git diff.

        CRITICAL: Don't trust agent-provided manifests. Always verify with git.
        """
        derived = []
        base_sha = self._get_sha(self.base_branch)

        for agent_id, branch in zip(agent_ids, branches):
            head_sha = self._get_sha(branch)

            # Get file changes from git
            files_added = []
            files_modified = []
            files_deleted = []

            try:
                result = subprocess.run(
                    ["git", "diff", "--name-status", f"{base_sha}...{head_sha}"],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_path,
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if not line:
                            continue
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            status, filepath = parts[0], parts[1]
                            if status == "A":
                                files_added.append(filepath)
                            elif status == "D":
                                files_deleted.append(filepath)
                            elif status.startswith("M") or status.startswith("R"):
                                files_modified.append(filepath)
            except Exception as e:
                logger.warning(f"Failed to get diff for {branch}: {e}")

            derived.append(DerivedManifest(
                agent_id=agent_id,
                branch=branch,
                base_sha=base_sha,
                head_sha=head_sha,
                files_added=files_added,
                files_modified=files_modified,
                files_deleted=files_deleted,
            ))

        return derived

    def _get_conflicting_files(self, detection_result: PipelineResult) -> list[str]:
        """Get list of conflicting files from detection result."""
        files = []

        if detection_result.textual_result:
            files.extend(f.file_path for f in detection_result.textual_result.conflicting_files)

        # Also include files from semantic conflicts
        if detection_result.semantic_result and detection_result.semantic_result.symbol_overlap:
            for overlap in detection_result.semantic_result.symbol_overlap.overlapping_symbols:
                for loc in overlap.get("locations", []):
                    if loc not in files:
                        files.append(loc)

        return list(set(files))

    def _get_base_files(self, files: list[str]) -> list[FileVersion]:
        """Get file contents from base branch."""
        base_files = []
        for filepath in files:
            content = self._get_file_content(self.base_branch, filepath)
            if content is not None:
                base_files.append(FileVersion(
                    path=filepath,
                    content=content,
                    source="base",
                    sha=self._get_sha(self.base_branch),
                ))
        return base_files

    def _get_agent_files(
        self,
        files: list[str],
        agent_ids: list[str],
        branches: list[str],
    ) -> dict[str, list[FileVersion]]:
        """Get file contents from each agent's branch."""
        agent_files = {}

        for agent_id, branch in zip(agent_ids, branches):
            agent_files[agent_id] = []
            for filepath in files:
                content = self._get_file_content(branch, filepath)
                if content is not None:
                    agent_files[agent_id].append(FileVersion(
                        path=filepath,
                        content=content,
                        source=agent_id,
                        sha=self._get_sha(branch),
                    ))

        return agent_files

    def _get_file_content(self, ref: str, filepath: str) -> Optional[str]:
        """Get content of a file at a specific git reference.

        SECURITY: Validates filepath before passing to git to prevent
        path traversal attacks like ../../../etc/passwd
        """
        # SECURITY: Sanitize and validate filepath
        filepath = _sanitize_filepath(filepath)
        if not _validate_repo_path(filepath, self.repo_path):
            logger.warning(f"Path traversal blocked: {filepath}")
            return None

        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{filepath}"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception as e:
            logger.debug(f"Could not get {filepath} from {ref}: {e}")
        return None

    def _find_related_files(self, conflicting_files: list[str]) -> list[RelatedFile]:
        """
        Find files related to the conflicts.

        Looks for:
        - Files that import conflicting files
        - Files that conflicting files import
        - Files in the same module/directory
        """
        related = []
        seen = set(conflicting_files)

        for filepath in conflicting_files:
            # Find imports within this file
            content = self._get_file_content(self.base_branch, filepath)
            if not content:
                continue

            # Find files this imports
            imports = self._extract_imports(content, filepath)
            for imp in imports:
                if imp not in seen:
                    imp_content = self._get_file_content(self.base_branch, imp)
                    if imp_content:
                        related.append(RelatedFile(
                            path=imp,
                            content=imp_content,
                            relationship="imports",
                        ))
                        seen.add(imp)

            # Find files in same directory (same module)
            directory = Path(filepath).parent
            try:
                result = subprocess.run(
                    ["git", "ls-tree", "--name-only", self.base_branch, str(directory) + "/"],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_path,
                )
                if result.returncode == 0:
                    for sibling in result.stdout.strip().split("\n"):
                        if sibling and sibling not in seen and sibling.endswith((".py", ".js", ".ts", ".go")):
                            sib_content = self._get_file_content(self.base_branch, sibling)
                            if sib_content:
                                related.append(RelatedFile(
                                    path=sibling,
                                    content=sib_content,
                                    relationship="same_module",
                                ))
                                seen.add(sibling)
            except Exception:
                pass

        return related[:50]  # Limit to avoid explosion

    def _extract_imports(self, content: str, filepath: str) -> list[str]:
        """Extract imported file paths from source code."""
        imports = []

        # Python imports
        if filepath.endswith(".py"):
            # from x import y, from .x import y
            for match in re.finditer(r'from\s+([.\w]+)\s+import', content):
                module = match.group(1)
                imports.extend(self._resolve_python_import(module, filepath))

            # import x
            for match in re.finditer(r'^import\s+([\w.]+)', content, re.MULTILINE):
                module = match.group(1)
                imports.extend(self._resolve_python_import(module, filepath))

        # JavaScript/TypeScript imports
        elif filepath.endswith((".js", ".ts", ".jsx", ".tsx")):
            for match in re.finditer(r'(?:import|from)\s+["\']([^"\']+)["\']', content):
                imp = match.group(1)
                if imp.startswith("."):
                    # Relative import
                    resolved = str(Path(filepath).parent / imp)
                    for ext in ["", ".js", ".ts", ".jsx", ".tsx"]:
                        imports.append(resolved + ext)

        return imports

    def _resolve_python_import(self, module: str, from_file: str) -> list[str]:
        """Resolve a Python import to file paths."""
        paths = []

        if module.startswith("."):
            # Relative import
            dots = len(module) - len(module.lstrip("."))
            base = Path(from_file).parent
            for _ in range(dots - 1):
                base = base.parent
            rest = module.lstrip(".")
            if rest:
                paths.append(str(base / rest.replace(".", "/")) + ".py")
                paths.append(str(base / rest.replace(".", "/") / "__init__.py"))
        else:
            # Absolute import - try src/ prefix
            paths.append(f"src/{module.replace('.', '/')}.py")
            paths.append(f"src/{module.replace('.', '/')}/__init__.py")

        return paths

    def _detect_conventions(self, conflicting_files: list[str]) -> list[ProjectConvention]:
        """
        Detect project conventions from the codebase.

        Looks for:
        - Code style patterns
        - Naming conventions
        - Directory structure patterns
        """
        conventions = []

        # Check for common config files
        config_files = [
            (".editorconfig", "EditorConfig"),
            ("pyproject.toml", "Python project config"),
            ("package.json", "Node.js project config"),
            (".prettierrc", "Prettier config"),
            (".eslintrc", "ESLint config"),
            ("setup.cfg", "Python setup config"),
        ]

        for config_file, description in config_files:
            content = self._get_file_content(self.base_branch, config_file)
            if content:
                conventions.append(ProjectConvention(
                    name=description,
                    description=f"Project uses {description}",
                    source_files=[config_file],
                ))

        # Detect naming patterns in conflicting files
        patterns_found = {}
        for filepath in conflicting_files:
            content = self._get_file_content(self.base_branch, filepath)
            if content:
                # Check for function naming (snake_case vs camelCase)
                snake_funcs = len(re.findall(r'def\s+[a-z][a-z_]*\(', content))
                camel_funcs = len(re.findall(r'function\s+[a-z][a-zA-Z]*\(', content))

                if snake_funcs > 0:
                    patterns_found["snake_case_functions"] = patterns_found.get("snake_case_functions", 0) + snake_funcs
                if camel_funcs > 0:
                    patterns_found["camelCase_functions"] = patterns_found.get("camelCase_functions", 0) + camel_funcs

        # Add detected patterns
        if patterns_found.get("snake_case_functions", 0) > patterns_found.get("camelCase_functions", 0):
            conventions.append(ProjectConvention(
                name="Function naming",
                description="Functions use snake_case naming",
                examples=["def my_function():", "def another_func():"],
            ))
        elif patterns_found.get("camelCase_functions", 0) > 0:
            conventions.append(ProjectConvention(
                name="Function naming",
                description="Functions use camelCase naming",
                examples=["function myFunction()", "function anotherFunc()"],
            ))

        return conventions
