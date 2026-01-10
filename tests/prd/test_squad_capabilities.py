"""
Tests for Claude Squad capability detection.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.prd._deprecated.squad_capabilities import CapabilityDetector, SquadCapabilities


class TestSquadCapabilities:
    """Tests for SquadCapabilities dataclass."""

    def test_default_values(self):
        """Default capabilities should be conservative."""
        caps = SquadCapabilities()

        assert caps.installed is False
        assert caps.is_compatible is False
        assert caps.compatibility_issues == []

    def test_compatibility_issues_list(self):
        """Compatibility issues should be a mutable list."""
        caps = SquadCapabilities()
        caps.compatibility_issues.append("test issue")

        assert "test issue" in caps.compatibility_issues


class TestCapabilityDetector:
    """Tests for CapabilityDetector."""

    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return CapabilityDetector("claude-squad")

    def test_not_installed(self, detector):
        """Should detect when claude-squad is not installed."""
        with patch.object(detector, '_run', return_value=None):
            caps = detector.detect()

        assert caps.installed is False
        assert caps.is_compatible is False
        assert any("not installed" in issue for issue in caps.compatibility_issues)

    def test_installed_but_old_version(self, detector):
        """Should detect old version."""
        def mock_run(args):
            if "--version" in args:
                return "claude-squad v0.1.0"
            return ""

        with patch.object(detector, '_run', side_effect=mock_run):
            caps = detector.detect()

        assert caps.installed is True
        assert caps.version == "0.1.0"
        assert any("0.5.0" in issue for issue in caps.compatibility_issues)

    def test_full_capability_detection(self, detector):
        """Should detect all capabilities from help output."""
        def mock_run(args):
            if "--version" in args:
                return "claude-squad v1.2.3"
            if args == ["--help"]:
                return "Commands: new, list, status, attach, kill"
            if args == ["new", "--help"]:
                return "Flags: --name, --dir, --branch, --prompt-file, --autoyes"
            if args == ["list", "--help"]:
                return "Flags: --json"
            return ""

        with patch.object(detector, '_run', side_effect=mock_run):
            caps = detector.detect()

        assert caps.installed is True
        assert caps.version == "1.2.3"
        assert caps.supports_new is True
        assert caps.supports_list is True
        assert caps.supports_status is True
        assert caps.supports_attach is True
        assert caps.supports_kill is True
        assert caps.supports_prompt_file is True
        assert caps.supports_branch is True
        assert caps.supports_dir is True
        assert caps.supports_autoyes is True
        assert caps.supports_json_output is True
        assert caps.is_compatible is True
        assert len(caps.compatibility_issues) == 0

    def test_missing_required_commands(self, detector):
        """Should report missing required commands."""
        def mock_run(args):
            if "--version" in args:
                return "claude-squad v1.0.0"
            if args == ["--help"]:
                return "Commands: new"  # Missing list, attach
            if args == ["new", "--help"]:
                return "Flags: --name, --dir"
            return ""

        with patch.object(detector, '_run', side_effect=mock_run):
            caps = detector.detect()

        assert caps.is_compatible is False
        assert any("Missing required commands" in issue for issue in caps.compatibility_issues)

    def test_missing_dir_flag(self, detector):
        """Should report missing --dir flag."""
        def mock_run(args):
            if "--version" in args:
                return "claude-squad v1.0.0"
            if args == ["--help"]:
                return "Commands: new, list, attach"
            if args == ["new", "--help"]:
                return "Flags: --name"  # Missing --dir
            return ""

        with patch.object(detector, '_run', side_effect=mock_run):
            caps = detector.detect()

        assert caps.is_compatible is False
        assert any("--dir" in issue for issue in caps.compatibility_issues)

    def test_version_parsing(self, detector):
        """Should parse various version formats."""
        test_cases = [
            ("v1.2.3", "1.2.3"),
            ("1.2.3", "1.2.3"),
            ("claude-squad 1.2.3", "1.2.3"),
            ("Claude Squad version 1.2.3", "1.2.3"),
            ("no version here", None),
        ]

        for output, expected in test_cases:
            result = detector._parse_version(output)
            assert result == expected, f"Failed for input: {output}"

    def test_version_comparison(self, detector):
        """Should correctly compare versions."""
        assert detector._version_gte("1.0.0", "0.5.0") is True
        assert detector._version_gte("0.5.0", "0.5.0") is True
        assert detector._version_gte("0.4.0", "0.5.0") is False
        assert detector._version_gte("1.0.0", "0.9.9") is True
        assert detector._version_gte("2.0.0", "1.9.9") is True

    def test_subprocess_timeout(self, detector):
        """Should handle subprocess timeout gracefully."""
        import subprocess

        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="test", timeout=5)):
            result = detector._run(["--version"])

        assert result is None

    def test_file_not_found(self, detector):
        """Should handle FileNotFoundError gracefully."""
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            result = detector._run(["--version"])

        assert result is None

    def test_alternative_flag_names(self, detector):
        """Should detect alternative flag names like --directory."""
        def mock_run(args):
            if "--version" in args:
                return "claude-squad v1.0.0"
            if args == ["--help"]:
                return "Commands: new, list, attach"
            if args == ["new", "--help"]:
                return "Flags: --name, --directory, --prompt"  # --directory instead of --dir
            return ""

        with patch.object(detector, '_run', side_effect=mock_run):
            caps = detector.detect()

        assert caps.supports_dir is True
        assert caps.supports_prompt_file is True

    def test_stop_command_as_kill(self, detector):
        """Should recognize 'stop' as alternative to 'kill'."""
        def mock_run(args):
            if "--version" in args:
                return "claude-squad v1.0.0"
            if args == ["--help"]:
                return "Commands: new, list, attach, stop"  # 'stop' instead of 'kill'
            if args == ["new", "--help"]:
                return "Flags: --name, --dir"
            return ""

        with patch.object(detector, '_run', side_effect=mock_run):
            caps = detector.detect()

        assert caps.supports_kill is True
