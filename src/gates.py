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
from typing import Optional, List, Literal, Union, Protocol, runtime_checkable
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


@runtime_checkable
class GateProtocol(Protocol):
    """Protocol for gate validation.

    All gate types must implement this protocol to be used in CompositeGate.
    """
    error: Optional[str]

    def validate(self, base_path: Path) -> bool:
        """Validate the gate condition."""
        ...


# Type alias for all gate types (used for type hints and validation)
GateType = Union["ArtifactGate", "CommandGate", "HumanApprovalGate", "CompositeGate"]


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
            ValueError: If path contains traversal attempts or absolute paths
        """
        # Handle empty path - cannot validate
        if not self.path or not self.path.strip():
            self.error = "Empty artifact path"
            return False

        # Security: Block absolute paths (prevent base_path bypass)
        path_obj = Path(self.path)
        if path_obj.is_absolute():
            raise ValueError(f"Absolute paths not allowed: {self.path}")

        # Security: Block path traversal components
        if ".." in path_obj.parts:
            raise ValueError(f"Path traversal detected: {self.path}")

        # Construct full path
        full_path = base_path / self.path

        # Security: Resolve the path and verify it stays within base_path
        # This catches symlink attacks in any part of the path, not just the final component
        try:
            resolved_base = base_path.resolve()
            resolved_full = full_path.resolve()

            # Check containment using is_relative_to (Python 3.9+) or string comparison
            try:
                resolved_full.relative_to(resolved_base)
            except ValueError:
                self.error = "Path resolves outside base directory"
                return False
        except (OSError, ValueError) as e:
            self.error = f"Invalid path: {e}"
            return False

        # Get validator function
        validator_fn = VALIDATORS.get(self.validator)
        if validator_fn is None:
            self.error = f"Unknown validator: {self.validator}"
            return False

        try:
            return validator_fn(resolved_full)
        except Exception as e:
            self.error = str(e)
            return False


@dataclass
class CommandGate:
    """
    Gate that validates by running a command.

    Validates that a command exits with the expected exit code.
    Uses shlex for safe command parsing to prevent shell injection.

    Security: NEVER uses shell=True. Shell builtins (true, false, exit)
    are handled in Python directly without subprocess.
    """
    command: str
    timeout: int = 300  # Default 5 minutes
    success_exit_code: int = 0
    error: Optional[str] = None

    # Shell builtins that are handled in Python (never executed via shell)
    _BUILTIN_HANDLERS = {
        'true': 0,   # Always exits 0
        'false': 1,  # Always exits 1
    }

    def validate(self, base_path: Optional[Path] = None) -> bool:
        """
        Run the command and check exit code.

        Args:
            base_path: Working directory for command (optional)

        Returns:
            True if command exits with success code, False otherwise

        Security:
            - Never uses shell=True to prevent shell injection
            - Shell builtins (true, false) are emulated in Python
            - Commands are parsed with shlex.split() and executed as list
        """
        try:
            # Use shlex to safely parse command (prevents shell injection)
            args = shlex.split(self.command)

            if not args:
                self.error = "Empty command"
                return False

            # Handle shell builtins in Python - never use shell=True
            # This prevents injection like "true; rm -rf /"
            if args[0] in self._BUILTIN_HANDLERS:
                # Only accept the builtin itself, no additional arguments
                if len(args) != 1:
                    self.error = f"Builtin '{args[0]}' does not accept arguments for security reasons"
                    return False
                exit_code = self._BUILTIN_HANDLERS[args[0]]
                return exit_code == self.success_exit_code

            # Handle 'exit N' - also emulated in Python
            if args[0] == 'exit':
                if len(args) == 1:
                    exit_code = 0
                elif len(args) == 2:
                    try:
                        exit_code = int(args[1])
                    except ValueError:
                        self.error = f"Invalid exit code: {args[1]}"
                        return False
                else:
                    self.error = "exit accepts only one argument"
                    return False
                return exit_code == self.success_exit_code

            # Execute command without shell - safe from injection
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
        except FileNotFoundError:
            self.error = f"Command not found: {args[0]}"
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

    Type Safety:
    - gates must be a list of objects implementing GateProtocol
    - Validates gate types at runtime to prevent crashes from malformed YAML/JSON
    """
    operator: Literal["and", "or"]
    gates: List[GateType] = field(default_factory=list)
    error: Optional[str] = None

    def __post_init__(self):
        """Validate gate types after initialization."""
        self._validate_gates()

    def _validate_gates(self) -> None:
        """Validate that all gates implement GateProtocol."""
        for i, gate in enumerate(self.gates):
            if not isinstance(gate, GateProtocol):
                raise TypeError(
                    f"Gate at index {i} must implement GateProtocol, "
                    f"got {type(gate).__name__}. "
                    f"Use gate factory functions to create gates from YAML/dict."
                )

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
