"""
Tests for GateEngine security hardening.

Verifies that gate_engine.py uses the security module properly:
- Command execution uses shell=False
- Path validation prevents traversal
- Glob patterns validated before use
"""
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.v4.gate_engine import GateEngine, GateSecurityConfig
from src.v4.models import (
    CommandGate,
    FileExistsGate,
    NoPatternGate,
    JsonValidGate,
    GateStatus,
)
from src.v4.security.execution import ArgumentRules


class TestGateEngineSecureExecution:
    """Test that GateEngine uses secure command execution."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

        # Create test files
        (self.working_dir / "test.py").write_text("print('hello')")
        (self.working_dir / "data.json").write_text('{"key": "value"}')

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_shell_false_enforced_in_gate_engine(self):
        """Verify gate_engine uses shell=False for command execution."""
        config = GateSecurityConfig(
            allowed_executables=["/bin/echo"],
            use_sandbox=False,
        )
        engine = GateEngine(self.working_dir, security_config=config)

        gate = CommandGate(
            cmd="echo hello",
            exit_code=0,
        )

        with patch("src.v4.security.execution.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"hello", stderr=b"")
            engine._validate_command(gate)

            # Verify shell=False was used
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("shell") == False

    def test_command_injection_blocked(self):
        """Test that command injection attempts are blocked."""
        config = GateSecurityConfig(
            allowed_executables=["/bin/echo"],
            use_sandbox=False,
        )
        engine = GateEngine(self.working_dir, security_config=config)

        # Try to inject command
        gate = CommandGate(
            cmd="echo hello; rm -rf /",
            exit_code=0,
        )

        result = engine._validate_command(gate)

        # Should fail due to semicolon (shell metacharacter)
        assert result.status == GateStatus.FAILED
        assert "security" in result.reason.lower() or "metacharacter" in result.reason.lower()

    def test_disallowed_executable_blocked(self):
        """Test that disallowed executables are blocked."""
        config = GateSecurityConfig(
            allowed_executables=["/bin/ls"],  # Only ls allowed
            use_sandbox=False,
        )
        engine = GateEngine(self.working_dir, security_config=config)

        gate = CommandGate(
            cmd="rm -rf /",
            exit_code=0,
        )

        result = engine._validate_command(gate)

        assert result.status == GateStatus.FAILED
        assert "not found or not allowed" in result.reason.lower()


class TestGateEnginePathSecurity:
    """Test that GateEngine uses path traversal prevention."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

        # Create test files
        (self.working_dir / "test.txt").write_text("content")
        (self.working_dir / "data.json").write_text('{"key": "value"}')

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_exists_path_traversal_blocked(self):
        """Test that path traversal is blocked in file_exists gate."""
        engine = GateEngine(self.working_dir)

        gate = FileExistsGate(path="../../../etc/passwd")

        result = engine._validate_file_exists(gate)

        assert result.status == GateStatus.FAILED
        assert "security" in result.reason.lower()

    def test_file_exists_valid_path_works(self):
        """Test that valid paths work in file_exists gate."""
        engine = GateEngine(self.working_dir)

        gate = FileExistsGate(path="test.txt")

        result = engine._validate_file_exists(gate)

        assert result.status == GateStatus.PASSED

    def test_json_valid_path_traversal_blocked(self):
        """Test that path traversal is blocked in json_valid gate."""
        engine = GateEngine(self.working_dir)

        gate = JsonValidGate(path="../../../etc/passwd")

        result = engine._validate_json_valid(gate)

        assert result.status == GateStatus.FAILED
        assert "security" in result.reason.lower()

    def test_json_valid_valid_path_works(self):
        """Test that valid paths work in json_valid gate."""
        engine = GateEngine(self.working_dir)

        gate = JsonValidGate(path="data.json")

        result = engine._validate_json_valid(gate)

        assert result.status == GateStatus.PASSED


class TestGateEngineGlobSecurity:
    """Test that GateEngine validates glob patterns."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

        # Create test files
        (self.working_dir / "test.py").write_text("TODO: fix this")

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_no_pattern_glob_traversal_blocked(self):
        """Test that glob traversal patterns are blocked."""
        engine = GateEngine(self.working_dir)

        gate = NoPatternGate(
            pattern="TODO",
            paths=["../**/*.py"],  # Path traversal in glob
        )

        result = engine._validate_no_pattern(gate)

        assert result.status == GateStatus.FAILED
        assert "security" in result.reason.lower()

    def test_no_pattern_absolute_glob_blocked(self):
        """Test that absolute glob patterns are blocked."""
        engine = GateEngine(self.working_dir)

        gate = NoPatternGate(
            pattern="TODO",
            paths=["/etc/*"],  # Absolute path
        )

        result = engine._validate_no_pattern(gate)

        assert result.status == GateStatus.FAILED
        assert "security" in result.reason.lower()

    def test_no_pattern_valid_glob_works(self):
        """Test that valid glob patterns work."""
        engine = GateEngine(self.working_dir)

        gate = NoPatternGate(
            pattern="NOTFOUND",
            paths=["**/*.py"],
        )

        result = engine._validate_no_pattern(gate)

        assert result.status == GateStatus.PASSED


class TestGateEngineSecurityConfig:
    """Test GateSecurityConfig customization."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_custom_allowed_executables(self):
        """Test that custom allowed executables are respected."""
        config = GateSecurityConfig(
            allowed_executables=["/custom/bin/tool"],
            use_sandbox=False,
        )
        engine = GateEngine(self.working_dir, security_config=config)

        # Standard executable should be blocked
        gate = CommandGate(cmd="python --version", exit_code=0)
        result = engine._validate_command(gate)
        assert result.status == GateStatus.FAILED

    def test_custom_argument_rules(self):
        """Test that custom argument rules are enforced."""
        config = GateSecurityConfig(
            allowed_executables=["/usr/bin/git"],
            argument_rules={
                "git": ArgumentRules(
                    allowed_subcommands=["status"],  # Only status allowed
                    denied_flags=["--force"],
                ),
            },
            use_sandbox=False,
        )
        engine = GateEngine(self.working_dir, security_config=config)

        # Allowed subcommand should work (if git exists)
        # Disallowed subcommand should fail
        gate = CommandGate(cmd="git push", exit_code=0)
        result = engine._validate_command(gate)

        # Should fail because 'push' is not in allowed_subcommands
        # (may also fail if git not found, which is fine)
        assert result.status == GateStatus.FAILED


class TestGateEngineTimeoutHandling:
    """Test that GateEngine properly handles timeouts."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_timeout_returns_proper_result(self):
        """Test that timeouts return a GateResult with timeout reason."""
        from src.v4.security.execution import TimeoutError as ExecutionTimeoutError

        config = GateSecurityConfig(
            allowed_executables=["/bin/sleep"],
            use_sandbox=False,
        )
        engine = GateEngine(self.working_dir, security_config=config)

        gate = CommandGate(
            cmd="sleep 10",
            exit_code=0,
            timeout=1,  # Very short timeout
        )

        # Mock execute_secure to raise TimeoutError
        with patch("src.v4.gate_engine.execute_secure") as mock_exec:
            mock_exec.side_effect = ExecutionTimeoutError("Command timed out")
            result = engine._validate_command(gate)

        assert result.status == GateStatus.FAILED
        assert "timed out" in result.reason.lower()
        assert result.details.get("timeout") == 1


class TestInterpreterArgumentRules:
    """Test that interpreters have proper argument restrictions."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_python_c_flag_blocked(self):
        """Test that python -c is blocked."""
        config = GateSecurityConfig(use_sandbox=False)
        engine = GateEngine(self.working_dir, security_config=config)

        # Try to run python with -c flag
        gate = CommandGate(
            cmd="python -c 'print(1)'",
            exit_code=0,
        )
        result = engine._validate_command(gate)

        # Should fail because -c is in denied_flags
        # (may also fail if python not found, which is fine)
        assert result.status == GateStatus.FAILED

    def test_node_eval_blocked(self):
        """Test that node -e is blocked."""
        config = GateSecurityConfig(use_sandbox=False)
        engine = GateEngine(self.working_dir, security_config=config)

        gate = CommandGate(
            cmd="node -e 'console.log(1)'",
            exit_code=0,
        )
        result = engine._validate_command(gate)

        # Should fail because -e is in denied_flags
        assert result.status == GateStatus.FAILED

    def test_shell_not_in_default_allowlist(self):
        """Test that shell interpreters are NOT in default allowed list."""
        config = GateSecurityConfig(use_sandbox=False)
        engine = GateEngine(self.working_dir, security_config=config)

        # Try to run bash
        gate = CommandGate(cmd="bash -c 'echo hello'", exit_code=0)
        result = engine._validate_command(gate)

        # Should fail because bash is not in allowed_executables by default
        assert result.status == GateStatus.FAILED
        assert "not found or not allowed" in result.reason.lower()


class TestSandboxValidation:
    """Test sandbox configuration validation."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.working_dir = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_placeholder_sandbox_image_rejected(self):
        """Test that placeholder sandbox image is rejected when sandbox enabled."""
        from src.v4.security.execution import SecurityError

        config = GateSecurityConfig(
            use_sandbox=True,
            sandbox_image="sandbox-runner@sha256:placeholder",
        )

        with pytest.raises(SecurityError) as exc:
            GateEngine(self.working_dir, security_config=config)
        assert "placeholder" in str(exc.value).lower()

    def test_non_sha256_sandbox_image_rejected(self):
        """Test that non-SHA256 pinned images are rejected."""
        from src.v4.security.execution import SecurityError

        config = GateSecurityConfig(
            use_sandbox=True,
            sandbox_image="sandbox-runner:latest",  # Tag, not digest
        )

        with pytest.raises(SecurityError) as exc:
            GateEngine(self.working_dir, security_config=config)
        assert "sha256" in str(exc.value).lower()

    def test_invalid_sha256_digest_rejected(self):
        """Test that invalid SHA256 digests are rejected."""
        from src.v4.security.execution import SecurityError

        config = GateSecurityConfig(
            use_sandbox=True,
            sandbox_image="sandbox-runner@sha256:abc123",  # Too short
        )

        with pytest.raises(SecurityError) as exc:
            GateEngine(self.working_dir, security_config=config)
        assert "64" in str(exc.value) or "hex" in str(exc.value).lower()

    def test_valid_sandbox_image_accepted(self):
        """Test that valid SHA256 pinned images are accepted."""
        config = GateSecurityConfig(
            use_sandbox=True,
            sandbox_image="myregistry/sandbox-runner@sha256:" + "a" * 64,
        )

        # Should not raise
        engine = GateEngine(self.working_dir, security_config=config)
        assert engine.security_config.use_sandbox is True

    def test_sandbox_disabled_accepts_placeholder(self):
        """Test that placeholder is OK when sandbox is disabled."""
        config = GateSecurityConfig(
            use_sandbox=False,
            sandbox_image="sandbox-runner@sha256:placeholder",
        )

        # Should not raise
        engine = GateEngine(self.working_dir, security_config=config)
        assert engine.security_config.use_sandbox is False
