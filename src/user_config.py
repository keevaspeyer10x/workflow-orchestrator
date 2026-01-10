"""
User Config - CORE-023 Part 3

User configuration system at ~/.orchestrator/config.yaml
following the source plan (lines 167-178):

- Sensitive globs: ['secrets/*', '*.pem', '.env*']
- Generated file policy: delete | ours | theirs | regenerate
- LLM toggle: disable_llm: true for air-gapped environments
- Default skip LLM for >10MB files or >50 conflicts
"""

import fnmatch
import yaml
from pathlib import Path
from typing import Any, Optional


class UserConfig:
    """
    User configuration from ~/.orchestrator/config.yaml.

    Supports:
    - Sensitive file globs (never sent to LLM)
    - Generated file policies
    - LLM enable/disable toggle
    - Resolution thresholds
    - Learning settings
    """

    CONFIG_PATH = Path.home() / ".orchestrator" / "config.yaml"

    def __init__(self, data: dict):
        """Initialize with configuration data."""
        self._data = data

    @classmethod
    def get_default(cls) -> dict:
        """
        Get default configuration.

        Matches source plan (lines 167-172):
        - Sensitive globs from Grok review
        - Skip LLM for >10MB files
        - Skip LLM for >50 conflicts
        - 2min/file timeout
        """
        return {
            "sensitive_globs": [
                "secrets/*",
                "*.pem",
                ".env*",
                "*.key",
                "*.p12",
                ".aws/*",
                ".gcp/*",
                "*credential*",
                "*password*",
            ],
            "generated_files": {
                "package-lock.json": "regenerate",
                "yarn.lock": "regenerate",
                "Cargo.lock": "regenerate",
                "poetry.lock": "regenerate",
                "*.pyc": "delete",
                "__pycache__/*": "delete",
            },
            # Per-file resolution policies (CORE-023-P3)
            # Override how specific files are resolved during conflicts
            # Policies: "ours" | "theirs" | "regenerate" | "manual"
            "file_policies": {},
            "resolution": {
                "disable_llm": False,
                "max_file_size_for_llm": 10485760,  # 10MB (from source)
                "max_conflicts_for_llm": 50,  # From source
                "timeout_per_file": 120,  # 2min (from source)
                "auto_apply_threshold": 0.8,
            },
            "learning": {
                "auto_roadmap_suggestions": True,
                "conflict_threshold": 3,
                "session_window": 10,
            },
        }

    @classmethod
    def load(cls) -> "UserConfig":
        """
        Load configuration from ~/.orchestrator/config.yaml.

        Returns defaults if file doesn't exist.
        """
        defaults = cls.get_default()

        if not cls.CONFIG_PATH.exists():
            return cls(defaults)

        try:
            with open(cls.CONFIG_PATH) as f:
                user_data = yaml.safe_load(f) or {}
        except Exception:
            return cls(defaults)

        # Merge user config with defaults (user overrides defaults)
        merged = cls._deep_merge(defaults, user_data)
        return cls(merged)

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep merge two dictionaries, with override taking precedence."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = UserConfig._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def save(self) -> None:
        """Save configuration to ~/.orchestrator/config.yaml."""
        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self.CONFIG_PATH, 'w') as f:
            yaml.dump(self._data, f, default_flow_style=False)

    # ========================================================================
    # Property Accessors
    # ========================================================================

    @property
    def sensitive_globs(self) -> list[str]:
        """Get list of sensitive file globs."""
        return self._data.get("sensitive_globs", [])

    @property
    def generated_files(self) -> dict[str, str]:
        """Get generated file policies."""
        return self._data.get("generated_files", {})

    @property
    def file_policies(self) -> dict[str, str]:
        """Get per-file resolution policies (CORE-023-P3)."""
        return self._data.get("file_policies", {})

    @property
    def resolution(self) -> dict:
        """Get resolution settings."""
        return self._data.get("resolution", {})

    @property
    def learning(self) -> dict:
        """Get learning settings."""
        return self._data.get("learning", {})

    @property
    def llm_enabled(self) -> bool:
        """Check if LLM resolution is enabled (from source: 'disable_llm toggle')."""
        return not self.resolution.get("disable_llm", False)

    # ========================================================================
    # Sensitive File Detection
    # ========================================================================

    def is_sensitive(self, path: str) -> bool:
        """
        Check if a path matches any sensitive glob.

        From source plan: files that should NEVER be sent to external LLMs.

        Args:
            path: File path to check

        Returns:
            True if path matches a sensitive glob
        """
        for glob in self.sensitive_globs:
            if fnmatch.fnmatch(path, glob):
                return True
            # Also check the basename for patterns like "*.pem"
            if fnmatch.fnmatch(Path(path).name, glob):
                return True
        return False

    # ========================================================================
    # Generated File Policies
    # ========================================================================

    def get_generated_file_policy(self, path: str) -> Optional[str]:
        """
        Get the policy for a generated file.

        From source plan: delete | ours | theirs | regenerate

        Args:
            path: File path to check

        Returns:
            Policy string or None if not a generated file
        """
        for pattern, policy in self.generated_files.items():
            if fnmatch.fnmatch(path, pattern):
                return policy
            # Also check basename
            if fnmatch.fnmatch(Path(path).name, pattern):
                return policy
        return None

    def get_file_policy(self, path: str) -> Optional[str]:
        """
        Get per-file resolution policy (CORE-023-P3).

        Checks file_policies first (user overrides), then generated_files.

        Args:
            path: File path to check

        Returns:
            Policy string ("ours", "theirs", "regenerate", "manual")
            or None if no policy defined
        """
        # Check user-defined file_policies first (takes precedence)
        for pattern, policy in self.file_policies.items():
            if fnmatch.fnmatch(path, pattern):
                return policy
            # Also check basename
            if fnmatch.fnmatch(Path(path).name, pattern):
                return policy

        # Fall back to generated_files (for backwards compatibility)
        # Note: This is intentionally NOT called to separate concerns
        # generated_files is for auto-generated files
        # file_policies is for conflict resolution
        return None

    # ========================================================================
    # LLM Thresholds
    # ========================================================================

    def should_skip_llm_for_file(self, file_path: str, file_size: int) -> bool:
        """
        Check if LLM should be skipped for a file based on size.

        From source plan: "Default skip LLM for >10MB files"

        Args:
            file_path: Path to file (for future extension)
            file_size: Size of file in bytes

        Returns:
            True if file exceeds size threshold
        """
        max_size = self.resolution.get("max_file_size_for_llm", 10485760)
        return file_size > max_size

    def should_skip_llm_for_count(self, conflict_count: int) -> bool:
        """
        Check if LLM should be skipped based on conflict count.

        From source plan: "Default skip LLM for >50 conflicts"

        Args:
            conflict_count: Number of conflicts

        Returns:
            True if count exceeds threshold
        """
        max_conflicts = self.resolution.get("max_conflicts_for_llm", 50)
        return conflict_count > max_conflicts

    # ========================================================================
    # Generic Get/Set
    # ========================================================================

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a config value using dot notation.

        Examples:
            config.get("resolution.disable_llm")
            config.get("learning.conflict_threshold")

        Args:
            key: Dot-separated key path
            default: Default value if not found

        Returns:
            Config value or default
        """
        parts = key.split(".")
        value = self._data

        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set a config value using dot notation and save.

        Examples:
            config.set("resolution.disable_llm", True)
            config.set("learning.conflict_threshold", 5)

        Args:
            key: Dot-separated key path
            value: Value to set
        """
        parts = key.split(".")
        data = self._data

        # Navigate to parent
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]

        # Set value
        data[parts[-1]] = value

        # Persist
        self.save()
