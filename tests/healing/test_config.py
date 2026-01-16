"""Tests for HealingConfig - Phase 1 Detection & Fingerprinting."""

import os
import pytest
from unittest.mock import patch


class TestConfigFromEnvironment:
    """Tests for loading config from environment variables."""

    def test_config_from_environment_defaults(self):
        """Returns defaults when no env vars set."""
        from src.healing.config import HealingConfig

        with patch.dict(os.environ, {}, clear=True):
            config = HealingConfig.from_environment()

        assert config.enabled is True
        assert config.auto_apply_safe is True
        assert config.auto_apply_moderate is False
        assert config.max_daily_cost_usd == 10.0
        assert config.max_validations_per_day == 100
        assert config.kill_switch_active is False

    def test_config_from_environment_enabled(self):
        """Reads HEALING_ENABLED correctly."""
        from src.healing.config import HealingConfig

        with patch.dict(os.environ, {"HEALING_ENABLED": "false"}):
            config = HealingConfig.from_environment()
        assert config.enabled is False

        with patch.dict(os.environ, {"HEALING_ENABLED": "true"}):
            config = HealingConfig.from_environment()
        assert config.enabled is True

    def test_config_from_environment_kill_switch(self):
        """Reads HEALING_KILL_SWITCH correctly."""
        from src.healing.config import HealingConfig

        with patch.dict(os.environ, {"HEALING_KILL_SWITCH": "true"}):
            config = HealingConfig.from_environment()
        assert config.kill_switch_active is True

        with patch.dict(os.environ, {"HEALING_KILL_SWITCH": "false"}):
            config = HealingConfig.from_environment()
        assert config.kill_switch_active is False

    def test_config_from_environment_cost_limits(self):
        """Parses HEALING_MAX_DAILY_COST as float."""
        from src.healing.config import HealingConfig

        with patch.dict(os.environ, {"HEALING_MAX_DAILY_COST": "25.50"}):
            config = HealingConfig.from_environment()
        assert config.max_daily_cost_usd == 25.50

    def test_config_from_environment_protected_paths(self):
        """Parses comma-separated globs."""
        from src.healing.config import HealingConfig

        with patch.dict(
            os.environ, {"HEALING_PROTECTED_PATHS": "src/auth/**,migrations/**,*.key"}
        ):
            config = HealingConfig.from_environment()
        assert config.protected_paths == ["src/auth/**", "migrations/**", "*.key"]

    def test_config_from_environment_invalid_float(self):
        """Falls back to default on invalid float."""
        from src.healing.config import HealingConfig

        with patch.dict(os.environ, {"HEALING_MAX_DAILY_COST": "not_a_number"}):
            config = HealingConfig.from_environment()
        assert config.max_daily_cost_usd == 10.0  # Default


class TestKillSwitch:
    """Tests for kill switch behavior."""

    def test_kill_switch_active(self):
        """Returns True when kill_switch_active=True."""
        from src.healing.config import HealingConfig

        config = HealingConfig(kill_switch_active=True)
        assert config.kill_switch_active is True

    def test_kill_switch_inactive(self):
        """Returns False when kill_switch_active=False."""
        from src.healing.config import HealingConfig

        config = HealingConfig(kill_switch_active=False)
        assert config.kill_switch_active is False
