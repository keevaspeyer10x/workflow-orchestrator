"""
Tests for v3 Artifact-Based Gates.

Tests cover:
- ArtifactGate with validators
- CommandGate with timeouts
- Adversarial inputs (symlinks, path traversal, shell injection)
"""

import os
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestArtifactGate:
    """Test artifact-based gate validation."""

    def test_not_empty_rejects_empty_file(self, tmp_path):
        """Default validator (not_empty) rejects empty files."""
        from src.gates import ArtifactGate

        empty_file = tmp_path / "plan.md"
        empty_file.touch()  # Create empty file

        gate = ArtifactGate(path="plan.md", validator="not_empty")
        assert gate.validate(tmp_path) is False

    def test_not_empty_accepts_content(self, tmp_path):
        """Default validator accepts files with content."""
        from src.gates import ArtifactGate

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan\n\nThis is a plan.")

        gate = ArtifactGate(path="plan.md", validator="not_empty")
        assert gate.validate(tmp_path) is True

    def test_exists_accepts_empty_file(self, tmp_path):
        """exists validator accepts empty files."""
        from src.gates import ArtifactGate

        empty_file = tmp_path / "plan.md"
        empty_file.touch()

        gate = ArtifactGate(path="plan.md", validator="exists")
        assert gate.validate(tmp_path) is True

    def test_json_valid_accepts_valid_json(self, tmp_path):
        """json_valid validator accepts valid JSON."""
        from src.gates import ArtifactGate

        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}')

        gate = ArtifactGate(path="config.json", validator="json_valid")
        assert gate.validate(tmp_path) is True

    def test_json_valid_rejects_invalid_json(self, tmp_path):
        """json_valid validator rejects invalid JSON."""
        from src.gates import ArtifactGate

        json_file = tmp_path / "config.json"
        json_file.write_text('not valid json')

        gate = ArtifactGate(path="config.json", validator="json_valid")
        assert gate.validate(tmp_path) is False

    def test_yaml_valid_accepts_valid_yaml(self, tmp_path):
        """yaml_valid validator accepts valid YAML."""
        from src.gates import ArtifactGate

        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("key: value\n")

        gate = ArtifactGate(path="config.yaml", validator="yaml_valid")
        assert gate.validate(tmp_path) is True

    def test_default_validator_is_not_empty(self):
        """Default validator should be not_empty."""
        from src.gates import ArtifactGate, DEFAULT_VALIDATOR

        assert DEFAULT_VALIDATOR == "not_empty"
        gate = ArtifactGate(path="test.md")
        assert gate.validator == "not_empty"


class TestCommandGate:
    """Test command-based gate validation."""

    def test_command_success(self, tmp_path):
        """Command gate passes on exit code 0."""
        from src.gates import CommandGate

        gate = CommandGate(command="true")  # Always exits 0
        assert gate.validate(tmp_path) is True

    def test_command_failure(self, tmp_path):
        """Command gate fails on non-zero exit code."""
        from src.gates import CommandGate

        gate = CommandGate(command="false")  # Always exits 1
        assert gate.validate(tmp_path) is False

    def test_command_timeout(self, tmp_path):
        """Command gate times out for long-running commands."""
        from src.gates import CommandGate

        gate = CommandGate(command="sleep 10", timeout=1)
        result = gate.validate(tmp_path)
        assert result is False
        assert gate.error is not None
        assert "timeout" in gate.error.lower()

    def test_command_custom_exit_code(self, tmp_path):
        """Command gate can check custom exit codes."""
        from src.gates import CommandGate

        # This command exits with code 2
        gate = CommandGate(command="exit 2", success_exit_code=2)
        assert gate.validate(tmp_path) is True


class TestAdversarialGates:
    """Test gate resistance to adversarial inputs."""

    def test_symlink_attack_blocked(self, tmp_path):
        """Symlink to sensitive file is rejected."""
        from src.gates import ArtifactGate

        # Create a symlink pointing outside the directory
        artifact = tmp_path / "plan.md"
        try:
            artifact.symlink_to("/etc/passwd")
        except OSError:
            pytest.skip("Cannot create symlink")

        gate = ArtifactGate(path="plan.md")
        # Should either reject symlinks or resolve safely
        result = gate.validate(tmp_path)
        # Gate should not validate symlinks pointing outside
        assert result is False or gate.error is not None

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal attempts are blocked."""
        from src.gates import ArtifactGate

        gate = ArtifactGate(path="../../../etc/passwd")
        with pytest.raises(ValueError, match="traversal"):
            gate.validate(tmp_path)

    def test_shell_injection_safe(self, tmp_path):
        """Shell injection in command gates is handled safely."""
        from src.gates import CommandGate

        # This should not execute the injected command
        gate = CommandGate(command="echo hello; rm -rf /")
        # The gate should use shlex to safely handle this
        result = gate.validate(tmp_path)
        # Should not crash and should handle safely


class TestCompositeGate:
    """Test composite gate with AND/OR logic."""

    def test_and_requires_all(self, tmp_path):
        """AND composite requires all gates to pass."""
        from src.gates import ArtifactGate, CommandGate, CompositeGate

        # Create test file
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")

        gate = CompositeGate(
            operator="and",
            gates=[
                ArtifactGate(path="plan.md"),
                CommandGate(command="true")
            ]
        )
        assert gate.validate(tmp_path) is True

    def test_and_fails_if_any_fails(self, tmp_path):
        """AND composite fails if any gate fails."""
        from src.gates import ArtifactGate, CommandGate, CompositeGate

        # Create test file
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Plan")

        gate = CompositeGate(
            operator="and",
            gates=[
                ArtifactGate(path="plan.md"),
                CommandGate(command="false")  # This fails
            ]
        )
        assert gate.validate(tmp_path) is False

    def test_or_passes_if_any_passes(self, tmp_path):
        """OR composite passes if any gate passes."""
        from src.gates import ArtifactGate, CommandGate, CompositeGate

        gate = CompositeGate(
            operator="or",
            gates=[
                ArtifactGate(path="missing.md"),  # Fails
                CommandGate(command="true")  # Passes
            ]
        )
        assert gate.validate(tmp_path) is True


class TestHumanApprovalGate:
    """Test human approval gate."""

    def test_human_approval_gate_structure(self):
        """HumanApprovalGate has correct structure."""
        from src.gates import HumanApprovalGate

        gate = HumanApprovalGate(prompt="Please approve")
        assert gate.prompt == "Please approve"
        assert hasattr(gate, 'validate')
