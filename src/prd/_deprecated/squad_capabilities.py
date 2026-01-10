"""
Claude Squad capability detection.

Addresses AI review concern: "Assumptions about Claude Squad features
(e.g., --prompt-file, JSON output for list) are unverified"
"""

import subprocess
import re
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SquadCapabilities:
    """Detected Claude Squad capabilities."""
    installed: bool = False
    version: Optional[str] = None

    # Command support
    supports_new: bool = False
    supports_list: bool = False
    supports_status: bool = False
    supports_attach: bool = False
    supports_kill: bool = False

    # Flag support
    supports_prompt_file: bool = False
    supports_branch: bool = False
    supports_dir: bool = False
    supports_autoyes: bool = False
    supports_json_output: bool = False

    # Overall
    is_compatible: bool = False
    compatibility_issues: list[str] = field(default_factory=list)


class CapabilityDetector:
    """
    Detect Claude Squad capabilities by probing the CLI.

    Strategy:
    1. Check if installed via --version
    2. Parse --help output for supported commands/flags
    3. Validate minimum required capabilities
    """

    REQUIRED_COMMANDS = {"new", "list", "attach"}
    REQUIRED_FLAGS = {"--name", "--dir"}
    MIN_VERSION = "0.5.0"  # Hypothetical minimum

    def __init__(self, claude_squad_path: str = "claude-squad"):
        self.path = claude_squad_path

    def detect(self) -> SquadCapabilities:
        """Run full capability detection."""
        caps = SquadCapabilities()

        # Check installation
        version_result = self._run(["--version"])
        if version_result is None:
            caps.compatibility_issues.append("claude-squad not installed or not in PATH")
            return caps

        caps.installed = True
        caps.version = self._parse_version(version_result)

        # Check version compatibility
        if caps.version and not self._version_gte(caps.version, self.MIN_VERSION):
            caps.compatibility_issues.append(
                f"Version {caps.version} < {self.MIN_VERSION} (minimum required)"
            )

        # Parse main help
        help_result = self._run(["--help"])
        if help_result:
            caps.supports_new = "new" in help_result
            caps.supports_list = "list" in help_result
            caps.supports_status = "status" in help_result
            caps.supports_attach = "attach" in help_result
            caps.supports_kill = "kill" in help_result or "stop" in help_result

        # Parse 'new' command help for flags
        new_help = self._run(["new", "--help"])
        if new_help:
            caps.supports_prompt_file = "--prompt-file" in new_help or "--prompt" in new_help
            caps.supports_branch = "--branch" in new_help
            caps.supports_dir = "--dir" in new_help or "--directory" in new_help
            caps.supports_autoyes = "--autoyes" in new_help or "-y" in new_help

        # Check if list supports JSON
        list_help = self._run(["list", "--help"])
        if list_help:
            caps.supports_json_output = "--json" in list_help

        # Validate required capabilities
        missing_commands = self.REQUIRED_COMMANDS - {
            cmd for cmd, supported in [
                ("new", caps.supports_new),
                ("list", caps.supports_list),
                ("attach", caps.supports_attach),
            ] if supported
        }

        if missing_commands:
            caps.compatibility_issues.append(
                f"Missing required commands: {missing_commands}"
            )

        if not caps.supports_dir:
            caps.compatibility_issues.append(
                "Missing required flag: --dir for 'new' command"
            )

        # Overall compatibility
        caps.is_compatible = len(caps.compatibility_issues) == 0

        return caps

    def _run(self, args: list[str]) -> Optional[str]:
        """Run claude-squad command and return output."""
        try:
            result = subprocess.run(
                [self.path] + args,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout + result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
            return None

    def _parse_version(self, output: str) -> Optional[str]:
        """Extract version number from --version output."""
        # Match patterns like "v1.2.3", "1.2.3", "claude-squad 1.2.3"
        match = re.search(r"v?(\d+\.\d+\.\d+)", output)
        return match.group(1) if match else None

    def _version_gte(self, version: str, minimum: str) -> bool:
        """Check if version >= minimum."""
        def parse(v):
            return tuple(int(x) for x in v.split("."))
        try:
            return parse(version) >= parse(minimum)
        except ValueError:
            return False
