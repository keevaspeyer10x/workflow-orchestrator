"""
Tests for the secrets management module.
"""

import os
import json
import base64
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.secrets import (
    SecretsManager,
    get_secrets_manager,
    get_user_config,
    get_user_config_value,
    set_user_config_value,
    save_user_config,
    get_secret,
    CONFIG_FILE,
)


class TestSecretsManagerEnv:
    """Tests for environment variable secret source."""

    def test_get_from_env(self):
        """TC-SEC-001: Returns secret from environment variable."""
        with patch.dict(os.environ, {"TEST_SECRET": "test_value"}):
            secrets = SecretsManager()
            assert secrets.get_secret("TEST_SECRET") == "test_value"

    def test_env_priority_over_cache(self):
        """Environment variables are checked first, not cached."""
        with patch.dict(os.environ, {"TEST_SECRET": "first_value"}):
            secrets = SecretsManager()
            assert secrets.get_secret("TEST_SECRET") == "first_value"

        # Even after env changes, we get from env (not cached)
        with patch.dict(os.environ, {"TEST_SECRET": "second_value"}):
            # New manager instance
            secrets2 = SecretsManager()
            assert secrets2.get_secret("TEST_SECRET") == "second_value"

    def test_secret_not_found_returns_none(self):
        """TC-SEC-004: Returns None when secret not in any source."""
        with patch.dict(os.environ, {}, clear=True):
            secrets = SecretsManager()
            # Mock SOPS and GitHub to also fail
            secrets._try_sops = MagicMock(return_value=None)
            secrets._try_github_repo = MagicMock(return_value=None)
            assert secrets.get_secret("NONEXISTENT_SECRET") is None


class TestSecretsManagerSOPS:
    """Tests for SOPS secret source."""

    def test_sops_not_installed_falls_through(self):
        """TC-SOPS-002: Gracefully skips SOPS when not installed."""
        with patch("shutil.which", return_value=None):
            secrets = SecretsManager()
            result = secrets._try_sops("TEST_SECRET")
            assert result is None

    def test_sops_age_key_not_set_falls_through(self):
        """TC-SOPS-003: Skips SOPS when key not set."""
        with patch("shutil.which", return_value="/usr/bin/sops"):
            with patch.dict(os.environ, {}, clear=True):
                secrets = SecretsManager()
                result = secrets._try_sops("TEST_SECRET")
                assert result is None

    def test_sops_file_not_found_falls_through(self):
        """TC-SOPS-004: Skips SOPS when file doesn't exist."""
        with patch("shutil.which", return_value="/usr/bin/sops"):
            with patch.dict(os.environ, {"SOPS_AGE_KEY": "test-key"}):
                with tempfile.TemporaryDirectory() as tmpdir:
                    secrets = SecretsManager(working_dir=Path(tmpdir))
                    result = secrets._try_sops("TEST_SECRET")
                    assert result is None

    def test_sops_decryption_error_falls_through(self):
        """TC-SOPS-005: Handles decryption errors gracefully."""
        with patch("shutil.which", return_value="/usr/bin/sops"):
            with patch.dict(os.environ, {"SOPS_AGE_KEY": "test-key"}):
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Create a dummy SOPS file
                    sops_dir = Path(tmpdir) / ".manus"
                    sops_dir.mkdir()
                    (sops_dir / "secrets.enc.yaml").write_text("invalid: content")

                    # Mock subprocess to fail
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=1, stderr="decrypt failed")
                        secrets = SecretsManager(working_dir=Path(tmpdir))
                        result = secrets._try_sops("TEST_SECRET")
                        assert result is None


class TestSecretsManagerGitHub:
    """Tests for GitHub repo secret source."""

    def test_github_not_configured_falls_through(self):
        """TC-GH-002: Skips GitHub when not configured."""
        secrets = SecretsManager(config={})
        result = secrets._try_github_repo("TEST_SECRET")
        assert result is None

    def test_github_invalid_repo_format(self):
        """TC-GH-006: Validates repo format (owner/name)."""
        secrets = SecretsManager(config={"secrets_repo": "invalid"})
        result = secrets._try_github_repo("TEST_SECRET")
        assert result is None

    def test_github_cli_not_installed(self):
        """GitHub skipped when gh CLI not installed."""
        with patch("shutil.which", return_value=None):
            secrets = SecretsManager(config={"secrets_repo": "owner/repo"})
            result = secrets._try_github_repo("TEST_SECRET")
            assert result is None

    def test_github_success(self):
        """TC-GH-001: Fetches secret from private GitHub repo."""
        content = base64.b64encode(b"secret_value").decode()
        mock_response = json.dumps({"content": content})

        with patch("shutil.which", return_value="/usr/bin/gh"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=mock_response
                )
                secrets = SecretsManager(config={"secrets_repo": "owner/repo"})
                result = secrets._try_github_repo("TEST_SECRET")
                assert result == "secret_value"

    def test_github_not_found(self):
        """TC-GH-003: Handles 404 from GitHub gracefully."""
        with patch("shutil.which", return_value="/usr/bin/gh"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="404 Not Found"
                )
                secrets = SecretsManager(config={"secrets_repo": "owner/repo"})
                result = secrets._try_github_repo("TEST_SECRET")
                assert result is None

    def test_github_auth_error(self):
        """TC-GH-004: Handles 401/403 gracefully."""
        with patch("shutil.which", return_value="/usr/bin/gh"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="401 Unauthorized"
                )
                secrets = SecretsManager(config={"secrets_repo": "owner/repo"})
                result = secrets._try_github_repo("TEST_SECRET")
                assert result is None


class TestSecretsManagerPriority:
    """Tests for priority ordering."""

    def test_env_priority_over_sops(self):
        """TC-SEC-002: Env var takes precedence over SOPS."""
        with patch.dict(os.environ, {"DUAL_SECRET": "from_env"}):
            secrets = SecretsManager()
            # Mock SOPS to return different value
            secrets._try_sops = MagicMock(return_value="from_sops")
            # Should get env value, not SOPS
            assert secrets.get_secret("DUAL_SECRET") == "from_env"
            # SOPS should not be called
            secrets._try_sops.assert_not_called()

    def test_env_priority_over_github(self):
        """TC-SEC-003: Env var takes precedence over GitHub."""
        with patch.dict(os.environ, {"DUAL_SECRET": "from_env"}):
            secrets = SecretsManager()
            secrets._try_github_repo = MagicMock(return_value="from_github")
            assert secrets.get_secret("DUAL_SECRET") == "from_env"
            secrets._try_github_repo.assert_not_called()


class TestSecretsManagerCaching:
    """Tests for caching behavior."""

    def test_caching_works(self):
        """TC-SEC-005: Second call uses cached value."""
        with patch.dict(os.environ, {}, clear=True):
            secrets = SecretsManager()
            # Mock SOPS to return value only once
            call_count = [0]

            def mock_sops(name):
                call_count[0] += 1
                if call_count[0] == 1:
                    return "cached_value"
                return None

            secrets._try_sops = mock_sops
            secrets._try_github_repo = MagicMock(return_value=None)

            # First call
            result1 = secrets.get_secret("SOPS_SECRET")
            # Second call
            result2 = secrets.get_secret("SOPS_SECRET")

            assert result1 == "cached_value"
            assert result2 == "cached_value"
            assert call_count[0] == 1  # SOPS called only once

    def test_clear_cache(self):
        """Cache can be cleared."""
        secrets = SecretsManager()
        secrets._cache["test"] = "value"
        secrets.clear_cache()
        assert secrets._cache == {}


class TestSecretsManagerSources:
    """Tests for list_sources functionality."""

    def test_list_sources_env_always_available(self):
        """Environment source is always available."""
        secrets = SecretsManager()
        sources = secrets.list_sources()
        assert sources["env"]["available"] is True

    def test_list_sources_sops_status(self):
        """SOPS source reports correct status."""
        with patch("shutil.which", return_value=None):
            secrets = SecretsManager()
            sources = secrets.list_sources()
            assert sources["sops"]["installed"] is False
            assert sources["sops"]["available"] is False

    def test_list_sources_github_status(self):
        """GitHub source reports correct status when not configured."""
        with patch.object(SecretsManager, '_load_user_config', return_value={}):
            secrets = SecretsManager(config={})
            sources = secrets.list_sources()
            assert sources["github"]["configured"] is False
            assert sources["github"]["available"] is False


class TestSecretsManagerGetSource:
    """Tests for get_source functionality."""

    def test_get_source_env(self):
        """Returns 'env' when secret is from environment."""
        with patch.dict(os.environ, {"TEST_SECRET": "value"}):
            secrets = SecretsManager()
            assert secrets.get_source("TEST_SECRET") == "env"

    def test_get_source_not_found(self):
        """Returns None when secret not found."""
        with patch.dict(os.environ, {}, clear=True):
            secrets = SecretsManager()
            secrets._try_sops = MagicMock(return_value=None)
            secrets._try_github_repo = MagicMock(return_value=None)
            assert secrets.get_source("NONEXISTENT") is None


class TestUserConfig:
    """Tests for user configuration management."""

    def test_set_and_get_config(self):
        """TC-CLI-001/002: Config set and get work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            with patch("src.secrets.CONFIG_FILE", config_file):
                with patch("src.secrets.CONFIG_DIR", Path(tmpdir)):
                    set_user_config_value("test_key", "test_value")
                    assert get_user_config_value("test_key") == "test_value"

    def test_get_config_not_set(self):
        """Config get returns None when not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            with patch("src.secrets.CONFIG_FILE", config_file):
                assert get_user_config_value("nonexistent") is None

    def test_config_file_created(self):
        """TC-CLI-004: Config file created on first set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "orchestrator"
            config_file = config_dir / "config.yaml"
            with patch("src.secrets.CONFIG_FILE", config_file):
                with patch("src.secrets.CONFIG_DIR", config_dir):
                    assert not config_file.exists()
                    set_user_config_value("test_key", "test_value")
                    assert config_file.exists()


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_secrets_manager_singleton(self):
        """Default manager is a singleton."""
        manager1 = get_secrets_manager()
        manager2 = get_secrets_manager()
        assert manager1 is manager2

    def test_get_secrets_manager_with_args(self):
        """Creating with args returns new instance."""
        manager1 = get_secrets_manager()
        manager2 = get_secrets_manager(config={"test": "value"})
        assert manager1 is not manager2

    def test_get_secret_convenience(self):
        """get_secret convenience function works."""
        with patch.dict(os.environ, {"TEST_SECRET": "value"}):
            assert get_secret("TEST_SECRET") == "value"


class TestSecurityRequirements:
    """Tests for security requirements."""

    def test_no_secret_value_in_str(self):
        """Secret values not exposed in string representation."""
        secrets = SecretsManager()
        secrets._cache["secret"] = "sensitive_value"
        # The object should not expose cached values in repr/str
        obj_str = str(secrets)
        assert "sensitive_value" not in obj_str

    def test_age_key_not_cached(self):
        """TC-SECURITY-003: AGE key only read from env, not cached."""
        with patch.dict(os.environ, {"SOPS_AGE_KEY": "test_key"}):
            secrets = SecretsManager()
            # AGE key should never be in the cache
            _ = secrets._try_sops("TEST")
            assert "SOPS_AGE_KEY" not in secrets._cache
            assert "test_key" not in secrets._cache.values()


class TestBackwardsCompatibility:
    """Tests for backwards compatibility."""

    def test_existing_env_var_usage(self):
        """TC-BC-001: Direct env var still works."""
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            secrets = SecretsManager()
            assert secrets.get_secret("OPENROUTER_API_KEY") == "test_key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
