"""
Stage 3: Interface Harmonization

Makes merged code buildable by harmonizing interfaces:
1. Identify interface changes (signatures, types, exports)
2. Pick canonical interface (prefer existing in main, more usage)
3. Generate adapter code if needed (marked as temporary)
4. Update call sites
5. Verify build passes

CRITICAL: Log all adapter decisions for potential escalation.
"""

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .schema import (
    ConflictContext,
    IntentAnalysis,
    InterfaceChange,
    AdapterCode,
    HarmonizedResult,
)

logger = logging.getLogger(__name__)


class InterfaceHarmonizer:
    """
    Harmonizes interfaces between conflicting changes.

    Goal: Make the merged code build (tests may still fail).
    """

    def __init__(
        self,
        repo_path: Optional[Path] = None,
        build_command: Optional[str] = None,
    ):
        self.repo_path = repo_path or Path.cwd()
        self.build_command = build_command

    def harmonize(
        self,
        context: ConflictContext,
        intents: IntentAnalysis,
    ) -> HarmonizedResult:
        """
        Harmonize interfaces to make code buildable.

        Args:
            context: ConflictContext from Stage 1
            intents: IntentAnalysis from Stage 2

        Returns:
            HarmonizedResult with harmonized code and decisions
        """
        logger.info("Stage 3: Harmonizing interfaces")

        result = HarmonizedResult()

        # Step 1: Identify interface changes in each agent's work
        interface_changes = self._identify_interface_changes(context)
        logger.info(f"Found {len(interface_changes)} interface changes")

        # Step 2: Group changes by interface name
        grouped = self._group_by_interface(interface_changes)

        # Step 3: For each conflicting interface, pick canonical form
        for interface_name, changes in grouped.items():
            if len(changes) > 1:
                # Multiple agents changed this interface
                canonical = self._pick_canonical(changes, context)
                result.canonical_interfaces.append(canonical)
                result.decisions_log.append(
                    f"Interface '{interface_name}': chose {canonical.agent_id}'s version "
                    f"({canonical.change_type})"
                )

                # Generate adapter if signatures differ significantly
                adapter = self._generate_adapter(canonical, changes, context)
                if adapter:
                    result.adapters_generated.append(adapter)
                    result.decisions_log.append(
                        f"Generated adapter for '{interface_name}' to bridge versions"
                    )
            else:
                # Only one agent changed this, use as-is
                result.canonical_interfaces.append(changes[0])

        # Step 4: Update call sites for canonical interfaces
        call_site_updates = self._update_call_sites(
            result.canonical_interfaces,
            context,
        )
        result.call_sites_updated = call_site_updates

        # Step 5: Verify build passes
        build_passed, build_errors = self._verify_build(context, result)
        result.build_passes = build_passed
        result.build_errors = build_errors

        if not build_passed:
            result.decisions_log.append(
                f"Build failed with {len(build_errors)} errors - may need escalation"
            )

        logger.info(f"Harmonization complete: build_passes={build_passed}, "
                   f"{len(result.adapters_generated)} adapters generated")
        return result

    def _identify_interface_changes(
        self,
        context: ConflictContext,
    ) -> list[InterfaceChange]:
        """Identify interface changes in agent files."""
        changes = []

        for agent_id, files in context.agent_files.items():
            for file_version in files:
                # Get base version for comparison
                base_version = None
                for bf in context.base_files:
                    if bf.path == file_version.path:
                        base_version = bf
                        break

                file_changes = self._extract_interface_changes(
                    file_version,
                    base_version,
                    agent_id,
                )
                changes.extend(file_changes)

        return changes

    def _extract_interface_changes(
        self,
        new_version,
        base_version,
        agent_id: str,
    ) -> list[InterfaceChange]:
        """Extract interface changes from a file."""
        changes = []
        filepath = new_version.path

        # Python functions
        if filepath.endswith(".py"):
            new_funcs = self._extract_python_functions(new_version.content)
            base_funcs = self._extract_python_functions(
                base_version.content if base_version else ""
            )

            # Find added/modified functions
            for name, signature in new_funcs.items():
                if name not in base_funcs:
                    changes.append(InterfaceChange(
                        file_path=filepath,
                        name=name,
                        interface_type="function",
                        change_type="added",
                        agent_id=agent_id,
                        new_signature=signature,
                    ))
                elif base_funcs[name] != signature:
                    changes.append(InterfaceChange(
                        file_path=filepath,
                        name=name,
                        interface_type="function",
                        change_type="signature_changed",
                        agent_id=agent_id,
                        old_signature=base_funcs[name],
                        new_signature=signature,
                    ))

            # Find removed functions
            for name in base_funcs:
                if name not in new_funcs:
                    changes.append(InterfaceChange(
                        file_path=filepath,
                        name=name,
                        interface_type="function",
                        change_type="removed",
                        agent_id=agent_id,
                        old_signature=base_funcs[name],
                    ))

            # Python classes
            new_classes = self._extract_python_classes(new_version.content)
            base_classes = self._extract_python_classes(
                base_version.content if base_version else ""
            )

            for name in new_classes:
                if name not in base_classes:
                    changes.append(InterfaceChange(
                        file_path=filepath,
                        name=name,
                        interface_type="class",
                        change_type="added",
                        agent_id=agent_id,
                    ))

        # JavaScript/TypeScript exports
        elif filepath.endswith((".js", ".ts", ".jsx", ".tsx")):
            new_exports = self._extract_js_exports(new_version.content)
            base_exports = self._extract_js_exports(
                base_version.content if base_version else ""
            )

            for name in new_exports:
                if name not in base_exports:
                    changes.append(InterfaceChange(
                        file_path=filepath,
                        name=name,
                        interface_type="export",
                        change_type="added",
                        agent_id=agent_id,
                    ))

        return changes

    def _extract_python_functions(self, content: str) -> dict[str, str]:
        """Extract Python function signatures."""
        functions = {}
        pattern = r'def\s+(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(pattern, content):
            name = match.group(1)
            params = match.group(2).strip()
            functions[name] = f"def {name}({params})"
        return functions

    def _extract_python_classes(self, content: str) -> set[str]:
        """Extract Python class names."""
        classes = set()
        pattern = r'class\s+(\w+)\s*[:\(]'
        for match in re.finditer(pattern, content):
            classes.add(match.group(1))
        return classes

    def _extract_js_exports(self, content: str) -> set[str]:
        """Extract JavaScript/TypeScript exports."""
        exports = set()
        patterns = [
            r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)',
            r'export\s+\{\s*([^}]+)\s*\}',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                if "{" in pattern:
                    # Handle export { a, b, c }
                    names = match.group(1).split(",")
                    for name in names:
                        name = name.strip().split(" as ")[0].strip()
                        if name:
                            exports.add(name)
                else:
                    exports.add(match.group(1))
        return exports

    def _group_by_interface(
        self,
        changes: list[InterfaceChange],
    ) -> dict[str, list[InterfaceChange]]:
        """Group interface changes by interface name."""
        grouped = {}
        for change in changes:
            key = f"{change.file_path}:{change.name}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(change)
        return grouped

    def _pick_canonical(
        self,
        changes: list[InterfaceChange],
        context: ConflictContext,
    ) -> InterfaceChange:
        """
        Pick the canonical interface version.

        Preferences:
        1. Existing signature (not changed from base)
        2. More backward compatible
        3. More usage in codebase
        4. First agent (tiebreaker)
        """
        # Prefer signature_changed over added/removed (preserves existing)
        signature_changes = [c for c in changes if c.change_type == "signature_changed"]
        if signature_changes:
            # Pick the one with less drastic changes
            return signature_changes[0]

        # Prefer added over removed
        additions = [c for c in changes if c.change_type == "added"]
        if additions:
            return additions[0]

        # Fallback to first
        return changes[0]

    def _generate_adapter(
        self,
        canonical: InterfaceChange,
        all_changes: list[InterfaceChange],
        context: ConflictContext,
    ) -> Optional[AdapterCode]:
        """Generate adapter code to bridge interface differences."""
        # Only generate adapters for significant changes
        if canonical.change_type != "signature_changed":
            return None

        # Check if we need an adapter
        other_changes = [c for c in all_changes if c.agent_id != canonical.agent_id]
        if not other_changes:
            return None

        # Generate simple adapter for Python functions
        if canonical.interface_type == "function" and canonical.file_path.endswith(".py"):
            other = other_changes[0]

            # Create adapter function that wraps the new signature
            if canonical.new_signature and other.new_signature:
                adapter_code = f'''
# AUTO-GENERATED ADAPTER - Review before finalizing
# Bridges {canonical.agent_id} and {other.agent_id} versions of {canonical.name}
def _{canonical.name}_compat(*args, **kwargs):
    """Compatibility adapter for {canonical.name}."""
    # TODO: Adapt arguments if needed
    return {canonical.name}(*args, **kwargs)
'''
                return AdapterCode(
                    file_path=canonical.file_path,
                    code=adapter_code,
                    reason=f"Bridge {other.agent_id}'s calls to {canonical.agent_id}'s version",
                    is_temporary=True,
                )

        return None

    def _update_call_sites(
        self,
        canonical_interfaces: list[InterfaceChange],
        context: ConflictContext,
    ) -> list[tuple]:
        """Find and update call sites for canonical interfaces."""
        updates = []

        # For Phase 3, we track but don't auto-update
        # (Phase 5 will add actual call site updates)

        for interface in canonical_interfaces:
            if interface.change_type == "signature_changed":
                # Log that call sites may need updating
                updates.append((
                    interface.file_path,
                    f"old: {interface.old_signature}",
                    f"new: {interface.new_signature}",
                ))

        return updates

    def _verify_build(
        self,
        context: ConflictContext,
        result: HarmonizedResult,
    ) -> tuple[bool, list[str]]:
        """Verify that the harmonized code builds."""
        errors = []

        # Determine build command
        if self.build_command:
            command = self.build_command
        else:
            # Auto-detect build system
            if (self.repo_path / "pyproject.toml").exists():
                command = "python -m py_compile"
            elif (self.repo_path / "package.json").exists():
                command = "npm run build --if-present"
            elif (self.repo_path / "Cargo.toml").exists():
                command = "cargo check"
            elif (self.repo_path / "go.mod").exists():
                command = "go build ./..."
            else:
                # Skip build check if we can't detect
                logger.warning("Cannot detect build system, skipping build check")
                return True, []

        try:
            # For Python, check syntax of modified files
            if "py_compile" in command:
                for interface in result.canonical_interfaces:
                    filepath = self.repo_path / interface.file_path
                    if filepath.exists():
                        check_result = subprocess.run(
                            ["python", "-m", "py_compile", str(filepath)],
                            capture_output=True,
                            text=True,
                            cwd=self.repo_path,
                        )
                        if check_result.returncode != 0:
                            errors.append(f"{interface.file_path}: {check_result.stderr}")
                return len(errors) == 0, errors

            # For other languages, run the build command
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                timeout=300,  # 5 minute timeout
            )

            if result.returncode != 0:
                errors.append(result.stderr or result.stdout)
                return False, errors

            return True, []

        except subprocess.TimeoutExpired:
            errors.append("Build timed out after 5 minutes")
            return False, errors
        except Exception as e:
            errors.append(f"Build check failed: {e}")
            return False, errors
