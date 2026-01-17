"""
Programmatic gate validation with security hardening.

Gates are checked by CODE, not by LLM self-report.

Security Features:
- Command execution uses shell=False (no shell injection)
- Path validation prevents traversal attacks
- Glob patterns validated before use
- File access restricted to working directory
"""
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from .models import (
    GateSpec, GateResult, GateStatus,
    FileExistsGate, CommandGate, NoPatternGate, JsonValidGate
)
from .security.paths import safe_path, validate_glob_pattern, PathTraversalError
from .security.execution import (
    SecureCommand,
    SandboxConfig,
    ToolSecurityConfig,
    ArgumentRules,
    execute_secure,
    SecurityError,
    TimeoutError as ExecutionTimeoutError,
)


@dataclass
class GateSecurityConfig:
    """
    Security configuration for gate validation.

    IMPORTANT: The sandbox_image must be changed from the placeholder value
    before production use. Set it to a real SHA256 digest of your sandbox image:
        sandbox_image="myregistry/sandbox-runner@sha256:abc123..."

    Configure via environment variable GATE_SANDBOX_IMAGE or programmatically.
    """
    # Allowed executables for CommandGate
    # NOTE: All executables must have corresponding argument_rules to prevent
    # arbitrary code execution (e.g., python -c "malicious code")
    allowed_executables: List[str] = field(default_factory=lambda: [
        # Common test runners
        "/usr/bin/pytest",
        "/usr/bin/python",
        "/usr/bin/python3",
        "/usr/local/bin/pytest",
        "/usr/local/bin/python",
        "/usr/local/bin/python3",
        # Node.js
        "/usr/bin/npm",
        "/usr/bin/npx",
        "/usr/bin/node",
        "/usr/local/bin/npm",
        "/usr/local/bin/npx",
        "/usr/local/bin/node",
        # Go
        "/usr/bin/go",
        "/usr/local/go/bin/go",
        # Rust
        "/usr/bin/cargo",
        # Git (safe commands only)
        "/usr/bin/git",
        # Build tools
        "/usr/bin/make",
        # NOTE: Shell interpreters removed from default for security
        # If needed, add them with strict argument_rules
    ])

    # Argument rules per executable
    # CRITICAL: Every executable capable of running arbitrary code MUST have rules
    argument_rules: dict = field(default_factory=lambda: {
        # Git - only allow read-only commands
        "git": ArgumentRules(
            allowed_subcommands=["status", "diff", "log", "show", "branch"],
            denied_flags=["--force", "-f", "--hard", "--delete", "-D", "--exec"],
        ),
        # Python - block -c (eval code) and dangerous modules
        "python": ArgumentRules(
            denied_flags=["-c", "--command"],
            denied_patterns=[
                r"^-c$",  # Block -c flag
                r"^-m\s+(http\.server|SimpleHTTPServer).*",  # No starting servers
            ],
            allowed_subcommands=["-m"],  # Only allow -m for running modules
        ),
        "python3": ArgumentRules(
            denied_flags=["-c", "--command"],
            denied_patterns=[
                r"^-c$",
                r"^-m\s+(http\.server|SimpleHTTPServer).*",
            ],
            allowed_subcommands=["-m"],
        ),
        # Pytest - safe test runner
        "pytest": ArgumentRules(
            allowed_flags=["-v", "-x", "--tb=short", "--tb=long", "-k", "-s", "--collect-only"],
            denied_patterns=[r".*--exec.*"],
        ),
        # Node - block -e (eval code) and dangerous flags
        "node": ArgumentRules(
            denied_flags=["-e", "--eval", "-p", "--print", "-c", "--check"],
            denied_patterns=[r"^-e$", r"^--eval$"],
        ),
        # npm - only allow safe subcommands
        "npm": ArgumentRules(
            allowed_subcommands=["test", "run", "ci", "install", "audit"],
            denied_flags=["--unsafe-perm"],
            denied_patterns=[r".*--exec.*"],
        ),
        # npx - more restricted than npm
        "npx": ArgumentRules(
            denied_flags=["-c", "--call"],
            denied_patterns=[r".*--exec.*", r".*\|.*", r".*\$\(.*"],
        ),
        # Go - only allow safe subcommands
        "go": ArgumentRules(
            allowed_subcommands=["test", "build", "vet", "fmt", "mod"],
            denied_flags=["--exec"],
        ),
        # Cargo - only allow safe subcommands
        "cargo": ArgumentRules(
            allowed_subcommands=["test", "build", "check", "clippy", "fmt"],
            denied_flags=["--exec"],
        ),
        # Make - generally safe but limit targets
        "make": ArgumentRules(
            denied_patterns=[
                r".*\|.*",  # No pipes in targets
                r".*\$\(.*",  # No command substitution
                r".*rm\s+-rf.*",
            ],
        ),
        # Shell interpreters - VERY restricted if enabled
        # NOTE: These are NOT in allowed_executables by default
        "sh": ArgumentRules(
            denied_flags=["-c", "--command"],  # Block eval
            denied_patterns=[
                r"^-c$",  # Block -c flag
                r".*\|.*",  # No pipes
                r".*\$\(.*",  # No command substitution
                r".*`.*",  # No backticks
                r".*rm\s+-rf.*",
                r".*curl.*\|.*",  # No curl piped anywhere
                r".*wget.*\|.*",  # No wget piped anywhere
                r".*chmod\s+777.*",  # No world-writable
                r".*nc\s+.*",  # No netcat
            ],
        ),
        "bash": ArgumentRules(
            denied_flags=["-c", "--command"],
            denied_patterns=[
                r"^-c$",
                r".*\|.*",
                r".*\$\(.*",
                r".*`.*",
                r".*rm\s+-rf.*",
                r".*curl.*\|.*",
                r".*wget.*\|.*",
                r".*chmod\s+777.*",
                r".*nc\s+.*",
            ],
        ),
    })

    # Use container sandbox (requires Docker)
    use_sandbox: bool = False  # Disabled by default for compatibility

    # Sandbox image - MUST be pinned by SHA256 digest in production
    # Default is a placeholder - configure via GATE_SANDBOX_IMAGE env var
    sandbox_image: str = field(default_factory=lambda: (
        os.environ.get(
            "GATE_SANDBOX_IMAGE",
            "sandbox-runner@sha256:placeholder"  # MUST BE CHANGED FOR PRODUCTION
        )
    ))


class GateEngine:
    """
    Validates gates programmatically with security hardening.
    LLM cannot bypass these checks.

    Security features:
    - Command execution uses shell=False
    - Paths validated to prevent traversal
    - Glob patterns validated before use
    """

    def __init__(
        self,
        working_dir: Path,
        security_config: Optional[GateSecurityConfig] = None,
    ):
        self.working_dir = Path(working_dir).resolve()
        self.security_config = security_config or GateSecurityConfig()

        # Build tool security config from gate security config
        self._tool_config = ToolSecurityConfig(
            allowed_executables=self.security_config.allowed_executables,
            argument_rules=self.security_config.argument_rules,
            use_sandbox=self.security_config.use_sandbox,
            sandbox_image=self.security_config.sandbox_image,
        )

    def validate_all(self, gates: List[GateSpec]) -> List[GateResult]:
        """
        Validate all gates for a phase.
        Returns list of results (one per gate).
        """
        results = []
        for gate in gates:
            result = self._validate_gate(gate)
            results.append(result)
        return results

    def all_passed(self, results: List[GateResult]) -> bool:
        """Check if all gate results passed"""
        return all(r.passed for r in results)

    def _validate_gate(self, gate: GateSpec) -> GateResult:
        """Dispatch to appropriate validator"""
        if isinstance(gate, FileExistsGate):
            return self._validate_file_exists(gate)
        elif isinstance(gate, CommandGate):
            return self._validate_command(gate)
        elif isinstance(gate, NoPatternGate):
            return self._validate_no_pattern(gate)
        elif isinstance(gate, JsonValidGate):
            return self._validate_json_valid(gate)
        else:
            return GateResult(
                gate_type=str(type(gate)),
                status=GateStatus.FAILED,
                reason=f"Unknown gate type: {type(gate)}"
            )

    def _validate_file_exists(self, gate: FileExistsGate) -> GateResult:
        """Check if a file exists (with path traversal protection)."""
        try:
            # Use safe_path to prevent traversal attacks
            path = safe_path(self.working_dir, gate.path)

            if path.exists():
                return GateResult(
                    gate_type="file_exists",
                    status=GateStatus.PASSED,
                    details={"path": str(path.relative_to(self.working_dir))}
                )
            else:
                return GateResult(
                    gate_type="file_exists",
                    status=GateStatus.FAILED,
                    reason=f"File not found: {gate.path}",
                    details={"path": gate.path}
                )
        except PathTraversalError as e:
            return GateResult(
                gate_type="file_exists",
                status=GateStatus.FAILED,
                reason=f"Security error: {e}",
                details={"path": gate.path}
            )

    def _validate_command(self, gate: CommandGate) -> GateResult:
        """
        Run a command and check exit code.

        SECURITY: Uses shell=False to prevent command injection.
        Commands are parsed and validated before execution.
        """
        try:
            # Parse command into executable and arguments
            # This prevents shell injection by not using shell=True
            parsed = self._parse_command(gate.cmd)
            if parsed is None:
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Could not parse command: {gate.cmd}",
                    details={"cmd": gate.cmd}
                )

            executable, args = parsed

            # Find the full path to the executable
            full_executable = self._find_executable(executable)
            if full_executable is None:
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Executable not found or not allowed: {executable}",
                    details={"cmd": gate.cmd, "executable": executable}
                )

            # Create secure command
            cmd = SecureCommand(
                executable=full_executable,
                args=args,
                working_dir=self.working_dir,
                timeout=gate.timeout,
                sandbox=SandboxConfig(
                    use_container=self.security_config.use_sandbox,
                ),
            )

            # Execute securely
            result = execute_secure(cmd, self._tool_config)

            # Decode output
            stdout = result.stdout.decode("utf-8", errors="replace")
            stderr = result.stderr.decode("utf-8", errors="replace")

            # Check exit code
            if result.returncode != gate.exit_code:
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Command exited with {result.returncode}, expected {gate.exit_code}",
                    details={
                        "cmd": gate.cmd,
                        "returncode": result.returncode,
                        "stdout": stdout[:1000] if stdout else "",
                        "stderr": stderr[:1000] if stderr else ""
                    }
                )

            # Check empty output if required
            if gate.expect_empty and stdout.strip():
                return GateResult(
                    gate_type="command",
                    status=GateStatus.FAILED,
                    reason=f"Expected empty output but got: {stdout[:200]}",
                    details={"stdout": stdout[:1000]}
                )

            return GateResult(
                gate_type="command",
                status=GateStatus.PASSED,
                details={"cmd": gate.cmd, "returncode": result.returncode}
            )

        except ExecutionTimeoutError as e:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Command timed out after {gate.timeout}s",
                details={"cmd": gate.cmd, "timeout": gate.timeout}
            )
        except SecurityError as e:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Security error: {e}",
                details={"cmd": gate.cmd}
            )
        except Exception as e:
            return GateResult(
                gate_type="command",
                status=GateStatus.FAILED,
                reason=f"Command execution error: {str(e)}",
                details={"cmd": gate.cmd, "error": str(e)}
            )

    def _parse_command(self, cmd: str) -> Optional[tuple[str, List[str]]]:
        """
        Parse command string into executable and arguments.

        Uses shlex to safely parse, preventing shell metacharacter injection.
        """
        try:
            parts = shlex.split(cmd)
            if not parts:
                return None
            return parts[0], parts[1:]
        except ValueError:
            return None

    def _find_executable(self, name: str) -> Optional[str]:
        """
        Find full path to executable if it's in the allowed list.

        Returns the full path if found and allowed, None otherwise.
        """
        # If already a full path, check if allowed
        if name.startswith("/"):
            if name in self.security_config.allowed_executables:
                return name
            return None

        # Search allowed executables for matching name
        for allowed in self.security_config.allowed_executables:
            if Path(allowed).name == name and Path(allowed).exists():
                return allowed

        return None

    def _validate_no_pattern(self, gate: NoPatternGate) -> GateResult:
        """
        Check that files don't contain a pattern.

        SECURITY: Validates glob patterns to prevent traversal.
        """
        try:
            pattern = re.compile(gate.pattern)
        except re.error as e:
            return GateResult(
                gate_type="no_pattern",
                status=GateStatus.FAILED,
                reason=f"Invalid regex pattern: {e}"
            )

        matches_found = []

        for glob_pattern in gate.paths:
            # Validate glob pattern for security
            if not validate_glob_pattern(glob_pattern):
                return GateResult(
                    gate_type="no_pattern",
                    status=GateStatus.FAILED,
                    reason=f"Invalid glob pattern (security): {glob_pattern}",
                    details={"pattern": glob_pattern}
                )

            for file_path in self.working_dir.glob(glob_pattern):
                # Verify file is within working directory (double-check)
                try:
                    file_path.relative_to(self.working_dir)
                except ValueError:
                    continue  # Skip files outside working dir

                if file_path.is_file():
                    try:
                        content = file_path.read_text()
                        matches = pattern.findall(content)
                        if matches:
                            matches_found.append({
                                "file": str(file_path.relative_to(self.working_dir)),
                                "matches": matches[:5]  # Limit to first 5
                            })
                    except (UnicodeDecodeError, PermissionError):
                        continue  # Skip binary or inaccessible files

        if matches_found:
            return GateResult(
                gate_type="no_pattern",
                status=GateStatus.FAILED,
                reason=f"Pattern '{gate.pattern}' found in {len(matches_found)} file(s)",
                details={"matches": matches_found}
            )

        return GateResult(
            gate_type="no_pattern",
            status=GateStatus.PASSED,
            details={"pattern": gate.pattern, "paths_checked": gate.paths}
        )

    def _validate_json_valid(self, gate: JsonValidGate) -> GateResult:
        """
        Check that a file contains valid JSON.

        SECURITY: Uses safe_path to prevent traversal.
        """
        try:
            # Use safe_path to prevent traversal attacks
            path = safe_path(self.working_dir, gate.path)

            if not path.exists():
                return GateResult(
                    gate_type="json_valid",
                    status=GateStatus.FAILED,
                    reason=f"File not found: {gate.path}"
                )

            content = path.read_text()
            json.loads(content)
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.PASSED,
                details={"path": gate.path}
            )
        except PathTraversalError as e:
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.FAILED,
                reason=f"Security error: {e}",
                details={"path": gate.path}
            )
        except json.JSONDecodeError as e:
            return GateResult(
                gate_type="json_valid",
                status=GateStatus.FAILED,
                reason=f"Invalid JSON: {e}",
                details={"path": gate.path, "error": str(e)}
            )
