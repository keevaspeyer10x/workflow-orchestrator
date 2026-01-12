"""
Smoke tests for orchestrator CLI.

These are lightweight tests that verify critical paths work.
Should complete in < 2 minutes.
"""

import subprocess
import sys


def test_cli_version():
    """Test that orchestrator --version works."""
    result = subprocess.run(
        ["orchestrator", "--version"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "orchestrator" in result.stdout.lower()


def test_cli_help():
    """Test that orchestrator --help works."""
    result = subprocess.run(
        ["orchestrator", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "workflow" in result.stdout.lower()


def test_sessions_command_exists():
    """Test that new sessions command exists (CORE-024)."""
    result = subprocess.run(
        ["orchestrator", "sessions", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "sessions" in result.stdout.lower()


def test_feedback_command_exists():
    """Test that feedback command exists (WF-034)."""
    result = subprocess.run(
        ["orchestrator", "feedback", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "feedback" in result.stdout.lower()


def test_core_imports():
    """Test that core modules can be imported."""
    try:
        from src.session_logger import SessionLogger, SessionAnalyzer
        from src.adherence_validator import AdherenceValidator
        from src.feedback_capture import FeedbackCapture
        assert True
    except ImportError as e:
        assert False, f"Failed to import core modules: {e}"
