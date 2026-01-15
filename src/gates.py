"""
Artifact-based gate validation for v3 hybrid orchestration.

Gates validate workflow items based on artifacts (files, commands, approvals)
rather than LLM assertions. This provides verifiable proof of completion.

Gate Types:
- ArtifactGate: File exists and passes validator
- CommandGate: Command exits with success code
- HumanApprovalGate: Requires human approval
- CompositeGate: Combines multiple gates with AND/OR

Security:
- Path traversal protection
- Symlink attack prevention
- Shell injection safe command execution
"""

import json
import shlex
import subprocess
from pathlib import Path
from typing import Optional, List, Literal
from dataclasses import dataclass, field


# Default validator is not_empty, not exists
# This prevents empty files from passing validation
DEFAULT_VALIDATOR = "not_empty"


def _is_valid_json(path: Path) -> bool:
    """Check if file contains valid JSON."""
    try:
        with open(path) as f:
            json.load(f)
        return True
    except (json.JSONDecodeError, FileNotFoundError):
        return False


def _is_valid_yaml(path: Path) -> bool:
    """Check if file contains valid YAML."""
    try:
        import yaml
        with open(path) as f:
            yaml.safe_load(f)
        return True
    except Exception:
        return False


# Validator functions
VALIDATORS = {
    'exists': lambda path: path.exists(),
    'not_empty': lambda path: path.exists() and path.stat().st_size > 0,
    'min_size': lambda path, size=1: path.exists() and path.stat().st_size >= size,
    'json_valid': lambda path: _is_valid_json(path),
    'yaml_valid': lambda path: _is_valid_yaml(path),
}


@dataclass
class ArtifactGate:
    """
    Gate that validates a file artifact.

    Validates that a file exists and passes the specified validator.
    Default validator is 'not_empty' to prevent empty files from passing.
    """
    path: str
    validator: str = DEFAULT_VALIDATOR
    error: Optional[str] = None

    def validate(self, base_path: Path) -> bool:
        """
        Validate the artifact at base_path / self.path.

        Args:
            base_path: Base directory to look for the artifact

        Returns:
            True if artifact passes validation, False otherwise

        Raises:
            ValueError: If path contains traversal attempts
        """
        # Security: Block path traversal
        if ".." in self.path:
            raise ValueError(f"Path traversal detected: {self.path}")

        full_path = base_path / self.path

        # Security: Block symlinks pointing outside base_path
        if full_path.is_symlink():
            try:
                resolved = full_path.resolve()
                if not str(resolved).startswith(str(base_path.resolve())):
                    self.error = "Symlink points outside base directory"
                    return False
            except (OSError, ValueError):
                self.error = "Invalid symlink"
                return False

        # Get validator function
        validator_fn = VALIDATORS.get(self.validator)
        if validator_fn is None:
            self.error = f"Unknown validator: {self.validator}"
            return False

        try:
            return validator_fn(full_path)
        except Exception as e:
            self.error = str(e)
            return False


@dataclass
class CommandGate:
    """
    Gate that validates by running a command.

    Validates that a command exits with the expected exit code.
    Uses shlex for safe command parsing to prevent shell injection.
    """
    command: str
    timeout: int = 300  # Default 5 minutes
    success_exit_code: int = 0
    error: Optional[str] = None

    def validate(self, base_path: Optional[Path] = None) -> bool:
        """
        Run the command and check exit code.

        Args:
            base_path: Working directory for command (optional)

        Returns:
            True if command exits with success code, False otherwise
        """
        try:
            # Use shlex to safely parse command (prevents shell injection)
            args = shlex.split(self.command)

            # Special case for shell builtins
            if args[0] in ('exit', 'true', 'false'):
                # Run via shell for builtins
                result = subprocess.run(
                    self.command,
                    shell=True,
                    timeout=self.timeout,
                    cwd=base_path,
                    capture_output=True
                )
            else:
                result = subprocess.run(
                    args,
                    timeout=self.timeout,
                    cwd=base_path,
                    capture_output=True
                )

            return result.returncode == self.success_exit_code

        except subprocess.TimeoutExpired:
            self.error = f"Command timeout after {self.timeout}s"
            return False
        except Exception as e:
            self.error = str(e)
            return False


@dataclass
class HumanApprovalGate:
    """
    Gate that requires human approval.

    This gate always returns False when validated programmatically.
    It's designed to be checked and approved through the UI or CLI.
    """
    prompt: str
    approved: bool = False
    error: Optional[str] = None

    def validate(self, base_path: Optional[Path] = None) -> bool:
        """
        Check if human has approved.

        Returns:
            True if approved, False otherwise
        """
        return self.approved


@dataclass
class CompositeGate:
    """
    Gate that combines multiple gates with AND/OR logic.

    AND: All gates must pass
    OR: At least one gate must pass
    """
    operator: Literal["and", "or"]
    gates: List = field(default_factory=list)
    error: Optional[str] = None

    def validate(self, base_path: Path) -> bool:
        """
        Validate all sub-gates according to operator.

        Args:
            base_path: Base directory for artifact gates

        Returns:
            True if composite validation passes, False otherwise
        """
        if not self.gates:
            return True

        results = [gate.validate(base_path) for gate in self.gates]

        if self.operator == "and":
            return all(results)
        elif self.operator == "or":
            return any(results)
        else:
            self.error = f"Unknown operator: {self.operator}"
            return False
