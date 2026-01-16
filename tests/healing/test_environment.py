"""Tests for healing environment detection."""

import os
import pytest
from unittest.mock import patch


class TestEnvironmentDetection:
    """Test environment detection functionality."""

    def test_detect_cloud_with_claude_code_web(self):
        """ENV-001: CLAUDE_CODE_WEB=1 should return CLOUD."""
        from src.healing.environment import detect_environment, Environment

        with patch.dict(os.environ, {"CLAUDE_CODE_WEB": "1"}, clear=False):
            result = detect_environment()
            assert result == Environment.CLOUD

    def test_detect_ci_with_ci_env(self):
        """ENV-002: CI=true should return CI."""
        from src.healing.environment import detect_environment, Environment

        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            # Remove other env vars that might interfere
            env = os.environ.copy()
            env.pop("CLAUDE_CODE_WEB", None)
            with patch.dict(os.environ, env, clear=True):
                with patch.dict(os.environ, {"CI": "true"}):
                    result = detect_environment()
                    assert result == Environment.CI

    def test_detect_ci_with_github_actions(self):
        """ENV-003: GITHUB_ACTIONS=true should return CI."""
        from src.healing.environment import detect_environment, Environment

        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True):
            result = detect_environment()
            assert result == Environment.CI

    def test_detect_local_by_default(self):
        """ENV-004: No special env vars should return LOCAL."""
        from src.healing.environment import detect_environment, Environment

        # Clear all relevant env vars
        with patch.dict(os.environ, {}, clear=True):
            result = detect_environment()
            assert result == Environment.LOCAL

    def test_environment_singleton_initialized(self):
        """ENV-005: ENVIRONMENT singleton should be set on import."""
        from src.healing.environment import ENVIRONMENT, Environment

        assert ENVIRONMENT is not None
        assert isinstance(ENVIRONMENT, Environment)


class TestEnvironmentEnum:
    """Test Environment enum values."""

    def test_environment_has_local(self):
        """Environment should have LOCAL value."""
        from src.healing.environment import Environment

        assert hasattr(Environment, "LOCAL")
        assert Environment.LOCAL.value == "local"

    def test_environment_has_cloud(self):
        """Environment should have CLOUD value."""
        from src.healing.environment import Environment

        assert hasattr(Environment, "CLOUD")
        assert Environment.CLOUD.value == "cloud"

    def test_environment_has_ci(self):
        """Environment should have CI value."""
        from src.healing.environment import Environment

        assert hasattr(Environment, "CI")
        assert Environment.CI.value == "ci"
