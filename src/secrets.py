"""
Multi-source secrets management.

Provides unified access to secrets from multiple sources:
1. Environment variables (highest priority)
2. Password-encrypted files (simple, works everywhere)
3. SOPS-encrypted files (for teams with existing SOPS setup)
4. GitHub private repos (for Claude Code Web with gh CLI)

This complements existing SOPS infrastructure - it doesn't replace it.
"""

import os
import re
import json
import base64
import shutil
import logging
import subprocess
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


# Default paths for user config
CONFIG_DIR = Path.home() / ".config" / "orchestrator"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

# Simple encrypted secrets file (password-based)
SIMPLE_SECRETS_FILE = ".manus/secrets.enc"


def derive_key_from_password(password: str, salt: bytes = b"orchestrator") -> bytes:
    """Derive a consistent key from a password using PBKDF2."""
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=32)


class SecretsManager:
    """
    Multi-source secrets management with priority ordering.

    Sources are checked in order:
    1. Environment variables (always checked first)
    2. Simple password-encrypted file (SECRETS_PASSWORD env var)
    3. SOPS-encrypted files (if SOPS installed and SOPS_AGE_KEY set)
    4. GitHub private repo (if secrets_repo configured)

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
            working_dir: Working directory for secrets file lookup
            sops_file: Path to SOPS-encrypted file (relative to working_dir)
        """
        self._config = config or {}
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()
        self._sops_file = sops_file or ".manus/secrets.enc.yaml"
        self._simple_secrets_file = SIMPLE_SECRETS_FILE
        self._cache: Dict[str, str] = {}
        self._simple_secrets_cache: Optional[Dict[str, str]] = None

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
        2. Simple password-encrypted file
        3. SOPS-encrypted file
        4. GitHub private repo

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

        # 2. Simple password-encrypted file
        if value := self._try_simple_encrypted(name):
            self._cache[name] = value
            logger.debug(f"Found {name} in simple encrypted file")
            return value

        # 3. SOPS-encrypted file
        if value := self._try_sops(name):
            self._cache[name] = value
            logger.debug(f"Found {name} in SOPS")
            return value

        # 4. GitHub private repo
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
            Source name ("env", "simple", "sops", "github") or None if not found
        """
        # Check env first
        if os.environ.get(name):
            return "env"

        # Check simple encrypted
        if self._try_simple_encrypted(name):
            return "simple"

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

        # Simple encrypted file availability
        simple_file_exists = (self._working_dir / self._simple_secrets_file).exists()
        simple_password_set = bool(os.environ.get("SECRETS_PASSWORD"))

        sources["simple"] = {
            "available": simple_file_exists and simple_password_set,
            "file_exists": simple_file_exists,
            "password_set": simple_password_set,
            "file_path": str(self._simple_secrets_file),
            "description": "Password-encrypted file (simple)"
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

    def _try_simple_encrypted(self, name: str) -> Optional[str]:
        """
        Try to get a secret from simple password-encrypted file.

        Uses openssl aes-256-cbc encryption with password from SECRETS_PASSWORD env var.

        Args:
            name: Secret name

        Returns:
            Secret value if found, None otherwise
        """
        # Check if password is set
        password = os.environ.get("SECRETS_PASSWORD")
        if not password:
            logger.debug("SECRETS_PASSWORD not set, skipping simple encrypted source")
            return None

        # Check if file exists
        secrets_path = self._working_dir / self._simple_secrets_file
        if not secrets_path.exists():
            logger.debug(f"Simple secrets file not found: {secrets_path}")
            return None

        # Use cached decryption if available
        if self._simple_secrets_cache is not None:
            return self._simple_secrets_cache.get(name)

        try:
            # Decrypt using openssl
            result = subprocess.run(
                ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-d",
                 "-in", str(secrets_path), "-pass", f"pass:{password}"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.debug(f"Simple decryption failed (wrong password?): {result.stderr}")
                return None

            # Parse the YAML content
            if yaml is None:
                logger.debug("PyYAML not available for parsing")
                return None

            data = yaml.safe_load(result.stdout)
            if not isinstance(data, dict):
                logger.debug("Simple secrets file doesn't contain a dict")
                return None

            # Cache all secrets
            self._simple_secrets_cache = {k: str(v) for k, v in data.items() if v is not None}

            return self._simple_secrets_cache.get(name)

        except subprocess.TimeoutExpired:
            logger.warning("Simple decryption timed out")
            return None
        except Exception as e:
            logger.debug(f"Simple decryption error: {e}")
            return None

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


def encrypt_secrets(secrets: Dict[str, str], password: str, output_path: Path) -> bool:
    """
    Encrypt secrets to a file using password-based encryption.

    Args:
        secrets: Dict of secret names to values
        password: Encryption password
        output_path: Path to write encrypted file

    Returns:
        True if successful
    """
    if yaml is None:
        raise RuntimeError("PyYAML required for secrets encryption")

    # Create YAML content
    yaml_content = yaml.safe_dump(secrets, default_flow_style=False)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Encrypt using openssl
        result = subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
             "-out", str(output_path), "-pass", f"pass:{password}"],
            input=yaml_content,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"Encryption failed: {result.stderr}")
            return False

        return True

    except Exception as e:
        logger.error(f"Encryption error: {e}")
        return False


def decrypt_secrets(input_path: Path, password: str) -> Optional[Dict[str, str]]:
    """
    Decrypt secrets from a password-encrypted file.

    Args:
        input_path: Path to encrypted file
        password: Decryption password

    Returns:
        Dict of secrets if successful, None otherwise
    """
    if yaml is None:
        raise RuntimeError("PyYAML required for secrets decryption")

    if not input_path.exists():
        return None

    try:
        result = subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-d",
             "-in", str(input_path), "-pass", f"pass:{password}"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return None

        data = yaml.safe_load(result.stdout)
        if not isinstance(data, dict):
            return None

        return {k: str(v) for k, v in data.items() if v is not None}

    except Exception:
        return None


def init_secrets_interactive(working_dir: Path) -> bool:
    """
    Initialize secrets interactively.

    Prompts user for API keys and password, creates encrypted secrets file.

    Args:
        working_dir: Directory to create secrets in

    Returns:
        True if successful
    """
    import getpass

    print("\n=== Secrets Setup ===\n")
    print("This will create an encrypted secrets file for your API keys.")
    print("You'll set a password that you'll use in future sessions.\n")

    secrets = {}

    # Common API keys
    api_keys = [
        ("OPENROUTER_API_KEY", "OpenRouter API key (for multi-model reviews)"),
        ("ANTHROPIC_API_KEY", "Anthropic API key (optional)"),
        ("OPENAI_API_KEY", "OpenAI API key (optional)"),
    ]

    for key_name, description in api_keys:
        value = getpass.getpass(f"{description}: ").strip()
        if value:
            secrets[key_name] = value

    if not secrets:
        print("\nNo secrets provided. Aborting.")
        return False

    # Get password
    print("\nNow set your encryption password.")
    print("You'll enter this as SECRETS_PASSWORD when starting Claude Code Web sessions.\n")

    password = getpass.getpass("Encryption password (min 8 chars): ").strip()
    if len(password) < 8:
        print("Error: Password must be at least 8 characters.")
        return False

    password2 = getpass.getpass("Confirm password: ").strip()
    if password != password2:
        print("Error: Passwords don't match.")
        return False

    # Encrypt and save
    output_path = working_dir / SIMPLE_SECRETS_FILE

    if encrypt_secrets(secrets, password, output_path):
        print(f"\n✓ Secrets encrypted to {output_path}")
        print("\nNext steps:")
        print("  1. Commit the encrypted file: git add .manus/secrets.enc && git commit")
        print("  2. In Claude Code Web, set SECRETS_PASSWORD when starting a task")
        print("  3. Your API keys will be automatically available!")
        return True
    else:
        print("\nError: Failed to encrypt secrets.")
        return False
