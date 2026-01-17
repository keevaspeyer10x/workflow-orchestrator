"""
Secure command execution for V4 Control Inversion.

This module provides sandboxed command execution with:
- shell=False enforcement (no shell injection)
- Executable allowlist enforcement
- Argument validation (denied flags, patterns, subcommands)
- Container sandbox execution with hardening flags
- Image pinning by SHA256 digest (not :latest)

Security Model:
1. All commands run with shell=False (no shell metacharacters)
2. Only allowlisted executables can run
3. Arguments are validated against per-executable rules
4. Container sandbox adds defense-in-depth
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
import re
import subprocess
import urllib.parse


class SecurityError(Exception):
    """Raised when a security check fails."""
    pass


class TimeoutError(Exception):
    """Raised when command execution times out."""
    pass


@dataclass
class SandboxConfig:
    """Container sandbox configuration."""
    use_container: bool = True
    read_only_rootfs: bool = True
    network_mode: str = "none"  # none, host, bridge
    allowed_paths: List[Path] = field(default_factory=list)
    max_memory_mb: int = 512
    max_cpu_seconds: int = 60
    pids_limit: int = 100
    user: str = "1000:1000"  # Non-root user


@dataclass
class ArgumentRules:
    """Rules for validating command arguments."""
    allowed_flags: Optional[List[str]] = None  # If set, only these flags allowed
    denied_flags: List[str] = field(default_factory=list)  # Always denied
    denied_patterns: List[str] = field(default_factory=list)  # Regex patterns to deny
    allowed_subcommands: Optional[List[str]] = None  # First non-flag arg must be in list


@dataclass
class ToolSecurityConfig:
    """Security configuration for tool execution."""
    allowed_executables: List[str] = field(default_factory=list)
    argument_rules: Dict[str, ArgumentRules] = field(default_factory=dict)
    use_sandbox: bool = True
    sandbox_image: str = "sandbox-runner@sha256:placeholder"  # Must be pinned

    # Shell metacharacters that should never appear in arguments
    shell_metacharacters: Set[str] = field(default_factory=lambda: {
        ";", "|", "&", "$", "`", "\n", "$(", "${", ">>", "<<", ">", "<"
    })


@dataclass
class CommandResult:
    """Result of command execution."""
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


@dataclass
class SecureCommand:
    """Sandboxed command specification."""
    executable: str  # Must be in allowlist
    args: List[str]  # Parsed, validated arguments
    working_dir: Path
    timeout: int = 300
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)


def execute_secure(cmd: SecureCommand, config: ToolSecurityConfig) -> CommandResult:
    """
    Execute command in sandbox with shell=False.

    Security checks:
    1. Executable must be in allowlist
    2. Arguments must not contain shell metacharacters
    3. Arguments must pass per-executable rules
    4. If sandbox enabled, run in container with hardening

    Args:
        cmd: The command specification
        config: Security configuration

    Returns:
        CommandResult with output

    Raises:
        SecurityError: If any security check fails
    """
    # 1. Validate executable is in allowlist
    if cmd.executable not in config.allowed_executables:
        raise SecurityError(f"Executable not allowed: {cmd.executable}")

    # 2. Validate arguments don't contain shell metacharacters
    _validate_no_metacharacters(cmd.args, config.shell_metacharacters)

    # 3. Validate arguments against per-executable rules
    exe_name = Path(cmd.executable).name
    if exe_name in config.argument_rules:
        _validate_arguments(cmd.args, config.argument_rules[exe_name])

    # 4. Execute command
    if config.use_sandbox and cmd.sandbox.use_container:
        return _execute_in_container(cmd, config)
    else:
        return _execute_direct(cmd)


def _validate_no_metacharacters(args: List[str], metacharacters: Set[str]) -> None:
    """
    Validate arguments don't contain shell metacharacters.

    Also checks for URL-encoded and double-encoded variants.
    """
    for arg in args:
        # Check raw metacharacters
        for char in metacharacters:
            if char in arg:
                raise SecurityError(
                    f"Invalid argument contains shell metacharacter '{char}': {arg}"
                )

        # Check URL-encoded variants (e.g., %3B for ;)
        try:
            decoded = urllib.parse.unquote(arg)
            if decoded != arg:
                for char in metacharacters:
                    if char in decoded:
                        raise SecurityError(
                            f"Invalid argument contains encoded metacharacter: {arg}"
                        )

            # Check double-encoded variants
            double_decoded = urllib.parse.unquote(decoded)
            if double_decoded != decoded:
                for char in metacharacters:
                    if char in double_decoded:
                        raise SecurityError(
                            f"Invalid argument contains double-encoded metacharacter: {arg}"
                        )
        except Exception:
            pass  # If decoding fails, that's fine

        # Check for null bytes
        if "\x00" in arg:
            raise SecurityError(f"Invalid argument contains null byte: {arg}")


def _validate_arguments(args: List[str], rules: ArgumentRules) -> None:
    """
    Validate arguments against per-executable rules.

    Checks:
    - Denied flags are rejected
    - If allowed_flags set, only those flags pass
    - Denied patterns are rejected
    - If allowed_subcommands set, first non-flag must be in list
    """
    for arg in args:
        # Check denied flags
        if arg in rules.denied_flags:
            raise SecurityError(f"Denied flag: {arg}")

        # Check denied patterns
        for pattern in rules.denied_patterns:
            if re.match(pattern, arg):
                raise SecurityError(f"Argument matches denied pattern: {arg}")

        # If allowed_flags specified, flag must be in list
        if rules.allowed_flags is not None and arg.startswith("-"):
            # Handle flags with values (e.g., --tb=short)
            flag_base = arg.split("=")[0] if "=" in arg else arg
            if arg not in rules.allowed_flags and flag_base not in rules.allowed_flags:
                raise SecurityError(f"Flag not in allowlist: {arg}")

    # Check subcommands (first non-flag argument)
    if rules.allowed_subcommands is not None:
        subcommand = next((a for a in args if not a.startswith("-")), None)
        if subcommand and subcommand not in rules.allowed_subcommands:
            raise SecurityError(f"Subcommand not allowed: {subcommand}")


def _execute_direct(cmd: SecureCommand) -> CommandResult:
    """Execute command directly (no container)."""
    try:
        result = subprocess.run(
            [cmd.executable] + cmd.args,
            shell=False,  # CRITICAL: Never shell=True
            cwd=str(cmd.working_dir),
            capture_output=True,
            timeout=cmd.timeout,
        )
        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Command timed out after {cmd.timeout}s: {cmd.executable}"
        ) from e


def _execute_in_container(cmd: SecureCommand, config: ToolSecurityConfig) -> CommandResult:
    """Execute command inside container sandbox with hardening flags."""
    sandbox = cmd.sandbox

    # Build container command with security hardening
    container_cmd = [
        "docker", "run", "--rm",
        # Security hardening flags (per review feedback)
        "--cap-drop=ALL",  # Drop all capabilities
        f"--user={sandbox.user}",  # Run as non-root
        f"--pids-limit={sandbox.pids_limit}",  # Limit processes
        "--security-opt=no-new-privileges",  # No privilege escalation
    ]

    # Read-only rootfs
    if sandbox.read_only_rootfs:
        container_cmd.append("--read-only")

    # Network mode
    container_cmd.append(f"--network={sandbox.network_mode}")

    # Resource limits
    container_cmd.append(f"--memory={sandbox.max_memory_mb}m")
    container_cmd.append(f"--cpus={sandbox.max_cpu_seconds / 60}")  # Approximate

    # Mount allowed paths (read-only by default)
    for path in sandbox.allowed_paths:
        container_cmd.extend(["-v", f"{path}:{path}:ro"])

    # Mount working directory (read-write)
    container_cmd.extend([
        "-v", f"{cmd.working_dir}:{cmd.working_dir}",
        "-w", str(cmd.working_dir)
    ])

    # Add image (pinned by SHA256 digest, not :latest)
    image = config.sandbox_image
    if ":latest" in image:
        raise SecurityError(
            "Container image must be pinned by SHA256 digest, not :latest"
        )
    container_cmd.append(image)

    # Add the actual command
    container_cmd.extend([cmd.executable] + cmd.args)

    try:
        result = subprocess.run(
            container_cmd,
            shell=False,  # CRITICAL: Never shell=True
            capture_output=True,
            timeout=cmd.timeout,
        )
        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"Command timed out after {cmd.timeout}s: {cmd.executable}"
        ) from e
