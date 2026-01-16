"""
Tests for V3 Concurrency Fixes (Issues #73, #80).

Tests cover:
- Issue #73: TOCTOU fix in stale lock cleanup (atomic rename pattern)
- Issue #80: Directory fsync after atomic rename
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest


class TestTOCTOUStaleLockFix:
    """Test TOCTOU fix in _clean_stale_lock (Issue #73)."""

    def test_stale_lock_removed_atomically(self, tmp_path):
        """Stale lock is removed using atomic rename pattern."""
        from src.checkpoint import LockManager, _process_exists

        manager = LockManager(lock_dir=tmp_path)

        # Find a PID that definitely doesn't exist
        non_existent_pid = 99999999
        while _process_exists(non_existent_pid) and non_existent_pid > 0:
            non_existent_pid -= 1000000

        # Create a stale lock file
        lock_file = tmp_path / "stale.lock"
        lock_file.write_text(str(non_existent_pid))

        # Clean stale lock
        manager._clean_stale_lock(lock_file)

        # Lock file should be removed
        assert not lock_file.exists()
        # No .removing temp file should remain
        assert not lock_file.with_suffix('.removing').exists()

    def test_live_process_lock_preserved(self, tmp_path):
        """Lock with live process PID is preserved."""
        from src.checkpoint import LockManager

        manager = LockManager(lock_dir=tmp_path)

        # Create lock file with current process PID
        lock_file = tmp_path / "live.lock"
        lock_file.write_text(str(os.getpid()))

        # Try to clean (should not remove)
        manager._clean_stale_lock(lock_file)

        # Lock file should still exist
        assert lock_file.exists()

    def test_concurrent_removal_handled_gracefully(self, tmp_path):
        """Handles case where lock is removed by another process."""
        from src.checkpoint import LockManager, _process_exists

        manager = LockManager(lock_dir=tmp_path)

        # Find non-existent PID
        non_existent_pid = 99999999
        while _process_exists(non_existent_pid) and non_existent_pid > 0:
            non_existent_pid -= 1000000

        # Create a stale lock file
        lock_file = tmp_path / "race.lock"
        lock_file.write_text(str(non_existent_pid))

        # Simulate race: remove file between check and rename
        original_rename = Path.rename

        def racing_rename(self, target):
            # First time called, delete the file to simulate race
            if self.suffix == '.lock':
                self.unlink()
                raise FileNotFoundError("Simulated race condition")
            return original_rename(self, target)

        with patch.object(Path, 'rename', racing_rename):
            # Should not raise exception
            manager._clean_stale_lock(lock_file)

        # No files should remain
        assert not lock_file.exists()
        assert not lock_file.with_suffix('.removing').exists()

    def test_symlink_outside_lockdir_ignored(self, tmp_path):
        """Symlink pointing outside lock_dir is ignored (security)."""
        from src.checkpoint import LockManager

        manager = LockManager(lock_dir=tmp_path)

        # Create a target file outside lock_dir
        external_dir = tmp_path.parent / "external"
        external_dir.mkdir(exist_ok=True)
        external_file = external_dir / "target.txt"
        external_file.write_text("secret")

        # Create symlink in lock_dir pointing to external file
        symlink = tmp_path / "symlink.lock"
        symlink.symlink_to(external_file)

        # Try to clean (should be ignored due to security check)
        manager._clean_stale_lock(symlink)

        # External file should not be affected
        assert external_file.exists()
        assert external_file.read_text() == "secret"


class TestDirectoryFsync:
    """Test directory fsync after atomic rename (Issue #80)."""

    def test_fsync_called_after_rename(self, tmp_path):
        """os.fsync is called on directory fd after rename."""
        from src.state_version import save_state_with_integrity

        state_file = tmp_path / "state.json"
        state_data = {"workflow_id": "wf_test", "phase": "PLAN"}

        # Track fsync calls
        fsync_calls = []
        original_fsync = os.fsync

        def tracking_fsync(fd):
            fsync_calls.append(fd)
            return original_fsync(fd)

        with patch('os.fsync', side_effect=tracking_fsync):
            save_state_with_integrity(state_file, state_data)

        # Should have at least 2 fsync calls: file and directory
        assert len(fsync_calls) >= 2, f"Expected at least 2 fsync calls, got {len(fsync_calls)}"

    def test_directory_fd_opened_and_closed(self, tmp_path):
        """Directory fd is properly opened and closed."""
        from src.state_version import save_state_with_integrity

        state_file = tmp_path / "state.json"
        state_data = {"workflow_id": "wf_test"}

        open_calls = []
        close_calls = []
        original_open = os.open
        original_close = os.close

        def tracking_open(path, flags, *args):
            fd = original_open(path, flags, *args)
            open_calls.append((path, flags, fd))
            return fd

        def tracking_close(fd):
            close_calls.append(fd)
            return original_close(fd)

        with patch('os.open', side_effect=tracking_open):
            with patch('os.close', side_effect=tracking_close):
                save_state_with_integrity(state_file, state_data)

        # Find directory open call (should have O_DIRECTORY or O_RDONLY on dir)
        dir_opens = [c for c in open_calls if str(tmp_path) in str(c[0])]
        assert len(dir_opens) >= 1, "Directory should be opened for fsync"

        # All opened fds should be closed
        opened_fds = {c[2] for c in open_calls}
        closed_fds = set(close_calls)
        assert opened_fds == closed_fds, "All opened fds should be closed"

    def test_state_integrity_preserved_with_fsync(self, tmp_path):
        """State file integrity is maintained after save with fsync."""
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_file = tmp_path / "state.json"
        state_data = {"workflow_id": "wf_integrity", "phase": "EXECUTE", "data": [1, 2, 3]}

        save_state_with_integrity(state_file, state_data)
        loaded = load_state_with_verification(state_file)

        # Verify data roundtrip
        assert loaded["workflow_id"] == "wf_integrity"
        assert loaded["phase"] == "EXECUTE"
        assert loaded["data"] == [1, 2, 3]

    @pytest.mark.skipif(sys.platform == 'win32', reason="O_DIRECTORY not on Windows")
    def test_o_directory_flag_used_on_unix(self, tmp_path):
        """O_DIRECTORY flag is used when available."""
        from src.state_version import save_state_with_integrity

        state_file = tmp_path / "state.json"
        state_data = {"test": True}

        open_calls = []
        original_open = os.open

        def tracking_open(path, flags, *args):
            open_calls.append((path, flags))
            return original_open(path, flags, *args)

        with patch('os.open', side_effect=tracking_open):
            save_state_with_integrity(state_file, state_data)

        # Find directory open call
        dir_opens = [c for c in open_calls if str(tmp_path) in str(c[0])]
        if hasattr(os, 'O_DIRECTORY'):
            # Should use O_DIRECTORY flag
            assert any(c[1] & os.O_DIRECTORY for c in dir_opens), \
                "O_DIRECTORY flag should be used when available"

    def test_fsync_error_non_fatal(self, tmp_path):
        """fsync error on directory doesn't prevent state save."""
        from src.state_version import save_state_with_integrity, load_state_with_verification

        state_file = tmp_path / "state.json"
        state_data = {"workflow_id": "wf_fsync_error"}

        call_count = [0]
        original_fsync = os.fsync

        def failing_dir_fsync(fd):
            call_count[0] += 1
            # Fail on second fsync (directory), succeed on first (file)
            if call_count[0] > 1:
                raise OSError("Simulated fsync failure")
            return original_fsync(fd)

        with patch('os.fsync', side_effect=failing_dir_fsync):
            # Should not raise despite fsync failure
            save_state_with_integrity(state_file, state_data)

        # State should still be saved
        assert state_file.exists()
        loaded = load_state_with_verification(state_file)
        assert loaded["workflow_id"] == "wf_fsync_error"
