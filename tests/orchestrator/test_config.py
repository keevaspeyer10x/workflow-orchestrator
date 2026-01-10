"""
Days 17-18: Configuration System Tests

Tests for configuration loading, validation, and management.
"""

import pytest
from pathlib import Path
import os
import yaml

from src.orchestrator.config import (
    ConfigManager,
    OrchestratorConfig,
    ServerConfig,
    SecurityConfig,
    RetryConfig,
    CircuitBreakerConfig,
)


class TestDefaultConfiguration:
    """Tests for default configuration values"""

    def test_creates_with_defaults(self):
        """Should create config with default values"""
        config = OrchestratorConfig()

        assert config.server.host == "localhost"
        assert config.server.port == 8000
        assert config.security.token_expiry_seconds == 7200
        assert config.retry.max_attempts == 3
        assert config.circuit_breaker.failure_threshold == 5

    def test_server_defaults(self):
        """Should have correct server defaults"""
        config = ServerConfig()

        assert config.host == "localhost"
        assert config.port == 8000
        assert config.workers == 4
        assert config.timeout == 30

    def test_security_defaults(self):
        """Should have correct security defaults"""
        config = SecurityConfig()

        assert config.jwt_secret_env_var == "ORCHESTRATOR_JWT_SECRET"
        assert config.token_expiry_seconds == 7200
        assert config.require_token_rotation is True

    def test_retry_defaults(self):
        """Should have correct retry defaults"""
        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.initial_delay_ms == 100
        assert config.max_delay_ms == 5000
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_circuit_breaker_defaults(self):
        """Should have correct circuit breaker defaults"""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout_seconds == 60


class TestConfigurationFromDict:
    """Tests for loading configuration from dictionary"""

    def test_from_dict_server(self):
        """Should load server config from dict"""
        data = {
            "server": {
                "host": "0.0.0.0",
                "port": 9000,
                "workers": 8
            }
        }

        config = OrchestratorConfig.from_dict(data)

        assert config.server.host == "0.0.0.0"
        assert config.server.port == 9000
        assert config.server.workers == 8

    def test_from_dict_security(self):
        """Should load security config from dict"""
        data = {
            "security": {
                "jwt_secret_env_var": "CUSTOM_SECRET",
                "token_expiry_seconds": 3600
            }
        }

        config = OrchestratorConfig.from_dict(data)

        assert config.security.jwt_secret_env_var == "CUSTOM_SECRET"
        assert config.security.token_expiry_seconds == 3600

    def test_from_dict_partial(self):
        """Should handle partial configuration"""
        data = {
            "server": {
                "port": 9000
            }
        }

        config = OrchestratorConfig.from_dict(data)

        # Specified value
        assert config.server.port == 9000

        # Default values for unspecified
        assert config.server.host == "localhost"
        assert config.security.token_expiry_seconds == 7200

    def test_to_dict_round_trip(self):
        """Should convert to dict and back"""
        original = OrchestratorConfig()
        original.server.port = 9000
        original.security.token_expiry_seconds = 3600

        dict_data = original.to_dict()
        restored = OrchestratorConfig.from_dict(dict_data)

        assert restored.server.port == 9000
        assert restored.security.token_expiry_seconds == 3600


class TestConfigManager:
    """Tests for ConfigManager"""

    def test_init_with_defaults(self, tmp_path):
        """Should initialize with defaults when no file"""
        config_file = tmp_path / "nonexistent.yaml"
        manager = ConfigManager(config_file)

        config = manager.get()
        assert config.server.port == 8000

    def test_load_from_file(self, tmp_path):
        """Should load configuration from file"""
        config_file = tmp_path / "config.yaml"

        # Write config file
        data = {
            "server": {"port": 9000, "host": "0.0.0.0"},
            "security": {"token_expiry_seconds": 3600}
        }
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        # Load config
        manager = ConfigManager(config_file)
        config = manager.get()

        assert config.server.port == 9000
        assert config.server.host == "0.0.0.0"
        assert config.security.token_expiry_seconds == 3600

    def test_env_override_server_port(self, tmp_path, monkeypatch):
        """Should override server port from environment"""
        config_file = tmp_path / "config.yaml"

        # Write config file
        data = {"server": {"port": 8000}}
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        # Set environment variable
        monkeypatch.setenv("ORCHESTRATOR_SERVER_PORT", "9000")

        # Load config
        manager = ConfigManager(config_file)
        config = manager.get()

        # Environment should override file
        assert config.server.port == 9000

    def test_env_override_multiple(self, tmp_path, monkeypatch):
        """Should apply multiple environment overrides"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        monkeypatch.setenv("ORCHESTRATOR_SERVER_PORT", "9000")
        monkeypatch.setenv("ORCHESTRATOR_SERVER_HOST", "0.0.0.0")
        monkeypatch.setenv("ORCHESTRATOR_LOG_LEVEL", "DEBUG")

        manager.reload()
        config = manager.get()

        assert config.server.port == 9000
        assert config.server.host == "0.0.0.0"
        assert config.logging.level == "DEBUG"

    def test_get_section(self, tmp_path):
        """Should get specific configuration section"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        server_config = manager.get("server")
        assert isinstance(server_config, ServerConfig)
        assert server_config.port == 8000

        security_config = manager.get("security")
        assert isinstance(security_config, SecurityConfig)

    def test_get_invalid_section(self, tmp_path):
        """Should return None for invalid section"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        result = manager.get("nonexistent")
        assert result is None

    def test_update_config(self, tmp_path):
        """Should update configuration at runtime"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        manager.update("server", "port", 9000)

        config = manager.get()
        assert config.server.port == 9000

    def test_update_invalid_section(self, tmp_path):
        """Should raise error for invalid section"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        with pytest.raises(ValueError, match="Unknown configuration section"):
            manager.update("nonexistent", "key", "value")

    def test_update_invalid_key(self, tmp_path):
        """Should raise error for invalid key"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        with pytest.raises(ValueError, match="Unknown configuration key"):
            manager.update("server", "nonexistent", "value")

    def test_save_config(self, tmp_path):
        """Should save configuration to file"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        # Update config
        manager.update("server", "port", 9000)

        # Save
        manager.save()

        # Load in new manager
        manager2 = ConfigManager(config_file)
        config = manager2.get()

        assert config.server.port == 9000

    def test_reload_config(self, tmp_path):
        """Should reload configuration from file"""
        config_file = tmp_path / "config.yaml"

        # Initial config
        data = {"server": {"port": 8000}}
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        manager = ConfigManager(config_file)
        assert manager.get().server.port == 8000

        # Update file
        data = {"server": {"port": 9000}}
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        # Reload
        manager.reload()
        assert manager.get().server.port == 9000


class TestConfigValidation:
    """Tests for configuration validation"""

    def test_valid_config(self, tmp_path):
        """Should validate correct configuration"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        is_valid, errors = manager.validate()

        assert is_valid is True
        assert len(errors) == 0

    def test_invalid_server_port(self, tmp_path):
        """Should detect invalid server port"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        manager.update("server", "port", 99999)

        is_valid, errors = manager.validate()

        assert is_valid is False
        assert any("port" in err.lower() for err in errors)

    def test_invalid_token_expiry(self, tmp_path):
        """Should detect invalid token expiry"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        manager.update("security", "token_expiry_seconds", 30)

        is_valid, errors = manager.validate()

        assert is_valid is False
        assert any("token expiry" in err.lower() for err in errors)

    def test_invalid_retry_attempts(self, tmp_path):
        """Should detect invalid retry attempts"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        manager.update("retry", "max_attempts", 0)

        is_valid, errors = manager.validate()

        assert is_valid is False
        assert any("retry" in err.lower() for err in errors)

    def test_invalid_log_level(self, tmp_path):
        """Should detect invalid log level"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        manager.update("logging", "level", "INVALID")

        is_valid, errors = manager.validate()

        assert is_valid is False
        assert any("logging level" in err.lower() for err in errors)

    def test_multiple_validation_errors(self, tmp_path):
        """Should detect multiple validation errors"""
        config_file = tmp_path / "config.yaml"
        manager = ConfigManager(config_file)

        manager.update("server", "port", 99999)
        manager.update("retry", "max_attempts", 0)
        manager.update("logging", "level", "INVALID")

        is_valid, errors = manager.validate()

        assert is_valid is False
        assert len(errors) >= 3


class TestConfigurationPriority:
    """Tests for configuration source priority"""

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        """Environment should override file"""
        config_file = tmp_path / "config.yaml"

        # File says 8000
        data = {"server": {"port": 8000}}
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        # Env says 9000
        monkeypatch.setenv("ORCHESTRATOR_SERVER_PORT", "9000")

        manager = ConfigManager(config_file)
        config = manager.get()

        # Env wins
        assert config.server.port == 9000

    def test_file_overrides_defaults(self, tmp_path):
        """File should override defaults"""
        config_file = tmp_path / "config.yaml"

        # File specifies custom value
        data = {"server": {"port": 9000}}
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        manager = ConfigManager(config_file)
        config = manager.get()

        # File wins over default (8000)
        assert config.server.port == 9000

    def test_defaults_used_when_nothing_specified(self, tmp_path):
        """Defaults should be used when nothing specified"""
        config_file = tmp_path / "nonexistent.yaml"

        manager = ConfigManager(config_file)
        config = manager.get()

        # Default value
        assert config.server.port == 8000


class TestConfigurationEdgeCases:
    """Tests for edge cases"""

    def test_malformed_yaml_file(self, tmp_path):
        """Should handle malformed YAML gracefully"""
        config_file = tmp_path / "bad.yaml"

        # Write invalid YAML
        with open(config_file, 'w') as f:
            f.write("invalid: yaml: content:\n  - bad")

        # Should fall back to defaults
        manager = ConfigManager(config_file)
        config = manager.get()

        assert config.server.port == 8000

    def test_empty_config_file(self, tmp_path):
        """Should handle empty config file"""
        config_file = tmp_path / "empty.yaml"
        config_file.touch()

        manager = ConfigManager(config_file)
        config = manager.get()

        assert config.server.port == 8000

    def test_config_file_with_null_values(self, tmp_path):
        """Should handle null values in config"""
        config_file = tmp_path / "nulls.yaml"

        data = {"server": None}
        with open(config_file, 'w') as f:
            yaml.dump(data, f)

        manager = ConfigManager(config_file)
        config = manager.get()

        # Should use defaults
        assert config.server.port == 8000
