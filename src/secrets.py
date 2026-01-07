"""
Multi-source secrets management.

Provides unified access to secrets from multiple sources:
1. Environment variables (highest priority)
2. SOPS-encrypted files
3. GitHub private repos (for Claude Code Web)

This complements existing SOPS infrastructure - it doesn't replace it.
"""

import os
import re
import json
import base64
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


# Default paths for user config
CONFIG_DIR = Path.home() / ".config" / "orchestrator"
CONFIG_FILE = CONFIG_DIR / "config.yaml"


class SecretsManager:
    """
    Multi-source secrets management with priority ordering.

    Sources are checked in order:
    1. Environment variables (always checked first)
    2. SOPS-encrypted files (if SOPS installed and SOPS_AGE_KEY set)
    3. GitHub private repo (if secrets_repo configured)

    Secrets are cached in memory only - never persisted to disk.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        working_dir: Optional[Path] = None,
        sops_file: Optional[str] = None
    ):
        """
        Initialize the secrets manager.

        Args:
            config: Configuration dict (may include secrets_repo)
            working_dir: Working directory for SOPS file lookup
            sops_file: Path to SOPS-encrypted file (relative to working_dir)
        """
        self._config = config or {}
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()
        self._sops_file = sops_file or ".manus/secrets.enc.yaml"
        self._cache: Dict[str, str] = {}

        # Load user config if exists
        self._user_config = self._load_user_config()

        # Merge configs (user config can be overridden by explicit config)
        self._merged_config = {**self._user_config, **self._config}

    def _load_user_config(self) -> Dict[str, Any]:
        """Load user configuration from ~/.config/orchestrator/config.yaml."""
        if not CONFIG_FILE.exists():
            return {}

        try:
            if yaml is None:
                # Fallback to simple parsing if yaml not available
                return {}

            with open(CONFIG_FILE) as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"Failed to load user config: {e}")
            return {}

    def get_secret(self, name: str) -> Optional[str]:
        """
        Get a secret by name, trying sources in priority order.

        Priority:
        1. Environment variable
        2. SOPS-encrypted file
        3. GitHub private repo

        Args:
            name: Secret name (e.g., "OPENROUTER_API_KEY")

        Returns:
            Secret value if found, None otherwise
        """
        # Check cache first
        if name in self._cache:
            logger.debug(f"Cache hit for secret: {name}")
            return self._cache[name]

        # 1. Environment variable (highest priority)
        if value := os.environ.get(name):
            logger.debug(f"Found {name} in environment")
            return value

        # 2. SOPS-encrypted file
        if value := self._try_sops(name):
            self._cache[name] = value
            logger.debug(f"Found {name} in SOPS")
            return value

        # 3. GitHub private repo
        if value := self._try_github_repo(name):
            self._cache[name] = value
            logger.debug(f"Found {name} in GitHub repo")
            return value

        logger.debug(f"Secret not found: {name}")
        return None

    def get_source(self, name: str) -> Optional[str]:
        """
        Determine which source provides a secret.

        Args:
            name: Secret name

        Returns:
            Source name ("env", "sops", "github") or None if not found
        """
        # Check env first
        if os.environ.get(name):
            return "env"

        # Check SOPS
        if self._try_sops(name):
            return "sops"

        # Check GitHub
        if self._try_github_repo(name):
            return "github"

        return None

    def list_sources(self) -> Dict[str, Dict[str, Any]]:
        """
        List available secret sources and their status.

        Returns:
            Dict mapping source name to status info
        """
        sources = {}

        # Environment is always available
        sources["env"] = {
            "available": True,
            "description": "Environment variables"
        }

        # SOPS availability
        sops_installed = shutil.which("sops") is not None
        sops_key_set = bool(os.environ.get("SOPS_AGE_KEY"))
        sops_file_exists = (self._working_dir / self._sops_file).exists()

        sources["sops"] = {
            "available": sops_installed and sops_key_set and sops_file_exists,
            "installed": sops_installed,
            "key_set": sops_key_set,
            "file_exists": sops_file_exists,
            "file_path": str(self._sops_file),
            "description": "SOPS-encrypted file"
        }

        # GitHub availability
        secrets_repo = self._merged_config.get("secrets_repo")
        gh_installed = shutil.which("gh") is not None

        sources["github"] = {
            "available": bool(secrets_repo) and gh_installed,
            "installed": gh_installed,
            "configured": bool(secrets_repo),
            "repo": secrets_repo,
            "description": "GitHub private repo"
        }

        return sources

    def _try_sops(self, name: str) -> Optional[str]:
        """
        Try to get a secret from SOPS-encrypted file.

        Args:
            name: Secret name

        Returns:
            Secret value if found, None otherwise
        """
        # Check if SOPS is installed
        if not shutil.which("sops"):
            logger.debug("SOPS not installed, skipping SOPS source")
            return None

        # Check if SOPS_AGE_KEY is set
        if not os.environ.get("SOPS_AGE_KEY"):
            logger.debug("SOPS_AGE_KEY not set, skipping SOPS source")
            return None

        # Check if SOPS file exists
        sops_path = self._working_dir / self._sops_file
        if not sops_path.exists():
            logger.debug(f"SOPS file not found: {sops_path}")
            return None

        try:
            # Decrypt the entire file and extract the key
            # Using --extract to get specific keys if the structure is known
            # For now, decrypt and parse
            result = subprocess.run(
                ["sops", "-d", str(sops_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.debug(f"SOPS decryption failed: {result.stderr}")
                return None

            # Parse the YAML output
            if yaml is None:
                logger.debug("PyYAML not available for SOPS parsing")
                return None

            data = yaml.safe_load(result.stdout)

            # Navigate the structure to find the secret
            # Support both flat and nested structures
            return self._extract_secret_from_data(data, name)

        except subprocess.TimeoutExpired:
            logger.warning("SOPS decryption timed out")
            return None
        except Exception as e:
            logger.debug(f"SOPS error: {e}")
            return None

    def _extract_secret_from_data(self, data: Any, name: str) -> Optional[str]:
        """
        Extract a secret from parsed SOPS data.

        Handles both flat and nested structures:
        - Direct: {OPENROUTER_API_KEY: "value"}
        - Nested: {workflow_orchestrator: {api_keys: {openrouter: "value"}}}

        Args:
            data: Parsed YAML data
            name: Secret name to find

        Returns:
            Secret value if found
        """
        if not isinstance(data, dict):
            return None

        # Try direct lookup (case-insensitive variants)
        name_lower = name.lower()
        for key, value in data.items():
            if key.upper() == name or key.lower() == name_lower:
                if isinstance(value, str):
                    return value

        # Try known nested paths for common secrets
        key_mappings = {
            "OPENROUTER_API_KEY": ["workflow_orchestrator", "api_keys", "openrouter"],
            "OPENAI_API_KEY": ["workflow_orchestrator", "api_keys", "openai"],
            "GEMINI_API_KEY": ["workflow_orchestrator", "api_keys", "gemini"],
        }

        if name in key_mappings:
            path = key_mappings[name]
            current = data
            for key in path:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    break
            else:
                if isinstance(current, str):
                    return current

        # Try recursive search
        return self._recursive_find(data, name)

    def _recursive_find(self, data: Any, name: str, depth: int = 0) -> Optional[str]:
        """Recursively search for a key in nested dict."""
        if depth > 5:  # Prevent infinite recursion
            return None

        if not isinstance(data, dict):
            return None

        name_lower = name.lower()
        for key, value in data.items():
            # Check if this key matches
            key_normalized = key.upper().replace("-", "_").replace(" ", "_")
            if key_normalized == name or key.lower() == name_lower:
                if isinstance(value, str):
                    return value

            # Recurse into nested dicts
            if isinstance(value, dict):
                result = self._recursive_find(value, name, depth + 1)
                if result:
                    return result

        return None

    def _try_github_repo(self, name: str) -> Optional[str]:
        """
        Try to get a secret from GitHub private repo.

        Args:
            name: Secret name (used as filename in repo)

        Returns:
            Secret value if found, None otherwise
        """
        secrets_repo = self._merged_config.get("secrets_repo")

        # Validate repo configuration
        if not secrets_repo:
            logger.debug("No secrets_repo configured")
            return None

        if "/" not in secrets_repo:
            logger.warning(f"Invalid secrets_repo format: {secrets_repo} (expected owner/repo)")
            return None

        # Check if gh CLI is installed
        if not shutil.which("gh"):
            logger.debug("GitHub CLI (gh) not installed")
            return None

        try:
            # Fetch file from GitHub repo
            # The file should be named exactly as the secret name
            result = subprocess.run(
                ["gh", "api", f"/repos/{secrets_repo}/contents/{name}"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                # Check for common error patterns
                if "404" in result.stderr or "Not Found" in result.stderr:
                    logger.debug(f"Secret file not found in GitHub: {name}")
                elif "401" in result.stderr or "403" in result.stderr:
                    logger.warning(f"GitHub auth error fetching {name}")
                elif "429" in result.stderr:
                    logger.warning("GitHub rate limit reached")
                else:
                    logger.debug(f"GitHub API error: {result.stderr}")
                return None

            # Parse response and decode content
            data = json.loads(result.stdout)

            # GitHub returns base64-encoded content
            if "content" in data:
                content = data["content"]
                # Remove newlines that GitHub adds
                content = content.replace("\n", "")
                decoded = base64.b64decode(content).decode("utf-8")
                # Strip whitespace (files might have trailing newlines)
                return decoded.strip()

            return None

        except subprocess.TimeoutExpired:
            logger.warning("GitHub API request timed out")
            return None
        except json.JSONDecodeError:
            logger.warning("Failed to parse GitHub API response")
            return None
        except Exception as e:
            logger.debug(f"GitHub error: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the in-memory secrets cache."""
        self._cache.clear()
        logger.debug("Secrets cache cleared")


def save_user_config(config: Dict[str, Any]) -> None:
    """
    Save configuration to user config file.

    Args:
        config: Configuration dict to save
    """
    if yaml is None:
        raise RuntimeError("PyYAML required for config management")

    # Create directory if needed
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing config
    existing = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Merge and save
    merged = {**existing, **config}
    with open(CONFIG_FILE, "w") as f:
        yaml.safe_dump(merged, f, default_flow_style=False)

    logger.info(f"Configuration saved to {CONFIG_FILE}")


def get_user_config() -> Dict[str, Any]:
    """
    Get user configuration.

    Returns:
        Configuration dict
    """
    if yaml is None or not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_user_config_value(key: str) -> Optional[str]:
    """
    Get a specific user configuration value.

    Args:
        key: Configuration key

    Returns:
        Value if set, None otherwise
    """
    config = get_user_config()
    value = config.get(key)
    return str(value) if value is not None else None


def set_user_config_value(key: str, value: str) -> None:
    """
    Set a user configuration value.

    Args:
        key: Configuration key
        value: Value to set
    """
    save_user_config({key: value})


# Singleton instance for convenience
_default_manager: Optional[SecretsManager] = None


def get_secrets_manager(
    config: Optional[Dict[str, Any]] = None,
    working_dir: Optional[Path] = None
) -> SecretsManager:
    """
    Get a SecretsManager instance.

    Creates a new instance if config/working_dir provided,
    otherwise returns/creates a default singleton.

    Args:
        config: Optional configuration
        working_dir: Optional working directory

    Returns:
        SecretsManager instance
    """
    global _default_manager

    if config is not None or working_dir is not None:
        return SecretsManager(config=config, working_dir=working_dir)

    if _default_manager is None:
        _default_manager = SecretsManager()

    return _default_manager


def get_secret(name: str) -> Optional[str]:
    """
    Convenience function to get a secret using default manager.

    Args:
        name: Secret name

    Returns:
        Secret value if found
    """
    return get_secrets_manager().get_secret(name)
