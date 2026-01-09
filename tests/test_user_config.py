"""
Tests for User Config - CORE-023 Part 3

Tests the user configuration system at ~/.orchestrator/config.yaml
following the source plan (lines 167-178).
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_home(tmp_path):
    """Create a temporary home directory with .orchestrator folder."""
    orchestrator_dir = tmp_path / ".orchestrator"
    orchestrator_dir.mkdir()
    return tmp_path


@pytest.fixture
def config_file(temp_home):
    """Path to the config file."""
    return temp_home / ".orchestrator" / "config.yaml"


@pytest.fixture
def sample_config():
    """Sample configuration matching source plan."""
    return {
        "sensitive_globs": [
            "secrets/*",
            "*.pem",
            ".env*",
        ],
        "generated_files": {
            "package-lock.json": "regenerate",
            "yarn.lock": "regenerate",
            "*.pyc": "delete",
        },
        "resolution": {
            "disable_llm": False,
            "max_file_size_for_llm": 10485760,  # 10MB
            "max_conflicts_for_llm": 50,
            "timeout_per_file": 120,
            "auto_apply_threshold": 0.8,
        },
        "learning": {
            "auto_roadmap_suggestions": True,
            "conflict_threshold": 3,
            "session_window": 10,
        },
    }


# ============================================================================
# Config Loading Tests
# ============================================================================

class TestUserConfigLoading:
    """Tests for loading user configuration."""

    def test_load_config_from_file(self, temp_home, config_file, sample_config):
        """Should load configuration from ~/.orchestrator/config.yaml."""
        from src.user_config import UserConfig

        # Write sample config
        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.sensitive_globs == ["secrets/*", "*.pem", ".env*"]
        assert config.resolution["disable_llm"] is False

    def test_load_returns_defaults_when_no_file(self, temp_home):
        """Should return defaults when config file doesn't exist."""
        from src.user_config import UserConfig

        nonexistent = temp_home / ".orchestrator" / "config.yaml"
        with patch.object(UserConfig, 'CONFIG_PATH', nonexistent):
            config = UserConfig.load()

        # Should have default sensitive globs from source plan
        assert "secrets/*" in config.sensitive_globs
        assert "*.pem" in config.sensitive_globs
        assert ".env*" in config.sensitive_globs

    def test_get_default_config_structure(self):
        """Should have all required sections in default config."""
        from src.user_config import UserConfig

        defaults = UserConfig.get_default()

        assert "sensitive_globs" in defaults
        assert "generated_files" in defaults
        assert "resolution" in defaults
        assert "learning" in defaults

    def test_default_config_matches_source_plan(self):
        """Default config should match source plan (lines 167-172)."""
        from src.user_config import UserConfig

        defaults = UserConfig.get_default()

        # From source: disable_llm toggle for air-gapped environments
        assert "disable_llm" in defaults["resolution"]

        # From source: >10MB files skip LLM
        assert defaults["resolution"]["max_file_size_for_llm"] == 10485760

        # From source: >50 conflicts skip LLM
        assert defaults["resolution"]["max_conflicts_for_llm"] == 50


# ============================================================================
# Sensitive File Detection Tests
# ============================================================================

class TestSensitiveFileDetection:
    """Tests for sensitive file glob matching."""

    def test_is_sensitive_matches_secrets_dir(self, temp_home, config_file, sample_config):
        """Should detect files in secrets/ directory."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.is_sensitive("secrets/api_key.txt") is True
        assert config.is_sensitive("secrets/nested/token.json") is True
        assert config.is_sensitive("src/secrets.py") is False  # Not in secrets/

    def test_is_sensitive_matches_pem_files(self, temp_home, config_file, sample_config):
        """Should detect .pem files."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.is_sensitive("server.pem") is True
        assert config.is_sensitive("certs/client.pem") is True
        assert config.is_sensitive("readme.md") is False

    def test_is_sensitive_matches_env_files(self, temp_home, config_file, sample_config):
        """Should detect .env files (from source: '.env*')."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.is_sensitive(".env") is True
        assert config.is_sensitive(".env.local") is True
        assert config.is_sensitive(".env.production") is True
        assert config.is_sensitive("environment.py") is False

    def test_is_sensitive_with_default_globs(self):
        """Should use default sensitive globs when no config file."""
        from src.user_config import UserConfig

        with patch.object(UserConfig, 'CONFIG_PATH', Path("/nonexistent/config.yaml")):
            config = UserConfig.load()

        # Should have sensible defaults
        assert config.is_sensitive("secrets/key.txt") is True
        assert config.is_sensitive("cert.pem") is True
        assert config.is_sensitive(".env") is True


# ============================================================================
# Generated File Policy Tests
# ============================================================================

class TestGeneratedFilePolicy:
    """Tests for generated file policies."""

    def test_get_policy_for_lockfile(self, temp_home, config_file, sample_config):
        """Should return 'regenerate' for lockfiles."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.get_generated_file_policy("package-lock.json") == "regenerate"
        assert config.get_generated_file_policy("yarn.lock") == "regenerate"

    def test_get_policy_for_pyc(self, temp_home, config_file, sample_config):
        """Should return 'delete' for .pyc files."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.get_generated_file_policy("module.pyc") == "delete"
        assert config.get_generated_file_policy("src/module.pyc") == "delete"

    def test_get_policy_returns_none_for_unknown(self, temp_home, config_file, sample_config):
        """Should return None for files without a policy."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.get_generated_file_policy("src/main.py") is None
        assert config.get_generated_file_policy("README.md") is None


# ============================================================================
# LLM Settings Tests
# ============================================================================

class TestLLMSettings:
    """Tests for LLM-related settings."""

    def test_llm_enabled_default(self):
        """LLM should be enabled by default."""
        from src.user_config import UserConfig

        with patch.object(UserConfig, 'CONFIG_PATH', Path("/nonexistent/config.yaml")):
            config = UserConfig.load()

        assert config.llm_enabled is True

    def test_llm_disabled_via_config(self, temp_home, config_file):
        """Should disable LLM when disable_llm is True."""
        from src.user_config import UserConfig

        config_data = {
            "resolution": {
                "disable_llm": True,
            }
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.llm_enabled is False

    def test_should_skip_llm_for_large_file(self, temp_home, config_file, sample_config):
        """Should skip LLM for files >10MB (from source plan)."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        # 5MB - should not skip
        assert config.should_skip_llm_for_file("small.py", 5 * 1024 * 1024) is False

        # 15MB - should skip (>10MB)
        assert config.should_skip_llm_for_file("large.py", 15 * 1024 * 1024) is True

        # Exactly 10MB - should not skip (boundary)
        assert config.should_skip_llm_for_file("exact.py", 10 * 1024 * 1024) is False

    def test_should_skip_llm_for_many_conflicts(self, temp_home, config_file, sample_config):
        """Should skip LLM for >50 conflicts (from source plan)."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        # 30 conflicts - should not skip
        assert config.should_skip_llm_for_count(30) is False

        # 60 conflicts - should skip (>50)
        assert config.should_skip_llm_for_count(60) is True

        # Exactly 50 - should not skip (boundary)
        assert config.should_skip_llm_for_count(50) is False


# ============================================================================
# Learning Settings Tests
# ============================================================================

class TestLearningSettings:
    """Tests for learning-related settings."""

    def test_auto_roadmap_suggestions_default(self):
        """Auto roadmap suggestions should be enabled by default."""
        from src.user_config import UserConfig

        with patch.object(UserConfig, 'CONFIG_PATH', Path("/nonexistent/config.yaml")):
            config = UserConfig.load()

        assert config.learning.get("auto_roadmap_suggestions", True) is True

    def test_conflict_threshold_default(self):
        """Conflict threshold should default to 3."""
        from src.user_config import UserConfig

        with patch.object(UserConfig, 'CONFIG_PATH', Path("/nonexistent/config.yaml")):
            config = UserConfig.load()

        assert config.learning.get("conflict_threshold", 3) == 3

    def test_session_window_default(self):
        """Session window should default to 10."""
        from src.user_config import UserConfig

        with patch.object(UserConfig, 'CONFIG_PATH', Path("/nonexistent/config.yaml")):
            config = UserConfig.load()

        assert config.learning.get("session_window", 10) == 10


# ============================================================================
# Config Persistence Tests
# ============================================================================

class TestConfigPersistence:
    """Tests for saving/updating configuration."""

    def test_save_creates_config_file(self, temp_home):
        """Should create config file when saving."""
        from src.user_config import UserConfig

        config_file = temp_home / ".orchestrator" / "config.yaml"

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()
            config.save()

        assert config_file.exists()

    def test_set_value_updates_config(self, temp_home, config_file, sample_config):
        """Should update config value and persist."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()
            config.set("resolution.disable_llm", True)

        # Reload and verify
        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.resolution["disable_llm"] is True

    def test_get_value_with_dot_notation(self, temp_home, config_file, sample_config):
        """Should retrieve nested values with dot notation."""
        from src.user_config import UserConfig

        with open(config_file, 'w') as f:
            yaml.dump(sample_config, f)

        with patch.object(UserConfig, 'CONFIG_PATH', config_file):
            config = UserConfig.load()

        assert config.get("resolution.max_file_size_for_llm") == 10485760
        assert config.get("learning.conflict_threshold") == 3
