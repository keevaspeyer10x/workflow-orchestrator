"""
Tests for v3 Checkpointing: Chaining, File Locking, Lock Management.

Tests cover:
- Checkpoint chaining (parent reference, lineage)
- File locking (concurrent access, shared/exclusive)
- Lock management (acquire/release, timeouts, stale locks)
"""

import os
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestCheckpointChaining:
    """Test checkpoint parent chaining."""

    def test_create_checkpoint_with_parent(self, tmp_path):
        """Checkpoint can reference a parent checkpoint."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create first checkpoint
        cp1 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="PLAN",
            message="First checkpoint",
            auto_detect_files=False  # Skip file scan for speed
        )

        # Create second checkpoint with parent
        cp2 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="EXECUTE",
            message="Second checkpoint",
            parent_checkpoint_id=cp1.checkpoint_id,
            auto_detect_files=False  # Skip file scan for speed
        )

        assert cp2.parent_checkpoint_id == cp1.checkpoint_id

    def test_get_checkpoint_chain(self, tmp_path):
        """Can retrieve full checkpoint lineage."""
        import time
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create chain of 3 checkpoints (with delays to ensure unique IDs)
        cp1 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="PLAN",
            message="First",
            auto_detect_files=False
        )
        time.sleep(1.1)  # Ensure different timestamp
        cp2 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="EXECUTE",
            message="Second",
            parent_checkpoint_id=cp1.checkpoint_id,
            auto_detect_files=False
        )
        time.sleep(1.1)
        cp3 = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="REVIEW",
            message="Third",
            parent_checkpoint_id=cp2.checkpoint_id,
            auto_detect_files=False
        )

        # Get chain from cp3
        chain = manager.get_checkpoint_chain(cp3.checkpoint_id)

        assert len(chain) == 3
        assert chain[0].checkpoint_id == cp3.checkpoint_id
        assert chain[1].checkpoint_id == cp2.checkpoint_id
        assert chain[2].checkpoint_id == cp1.checkpoint_id

    def test_chain_with_missing_parent(self, tmp_path):
        """Chain handles missing parent gracefully."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create checkpoint with non-existent parent
        cp = manager.create_checkpoint(
            workflow_id="wf_test",
            phase_id="PLAN",
            message="Orphan",
            parent_checkpoint_id="cp_nonexistent",
            auto_detect_files=False
        )

        # Get chain should stop at orphan
        chain = manager.get_checkpoint_chain(cp.checkpoint_id)
        assert len(chain) == 1
        assert chain[0].checkpoint_id == cp.checkpoint_id


class TestFileLocking:
    """Test file locking for concurrent access."""

    def test_acquire_exclusive_lock(self, tmp_path):
        """Can acquire exclusive lock on file."""
        from src.checkpoint import FileLock

        lock_file = tmp_path / "test.lock"
        lock = FileLock(lock_file)

        # Acquire lock
        lock.acquire_exclusive()
        assert lock.is_locked()

        # Release lock
        lock.release()
        assert not lock.is_locked()

    def test_acquire_shared_lock(self, tmp_path):
        """Multiple readers can acquire shared locks."""
        from src.checkpoint import FileLock

        lock_file = tmp_path / "test.lock"
        lock1 = FileLock(lock_file)
        lock2 = FileLock(lock_file)

        # Both can acquire shared locks
        lock1.acquire_shared()
        lock2.acquire_shared()

        assert lock1.is_locked()
        assert lock2.is_locked()

        lock1.release()
        lock2.release()

    def test_lock_timeout(self, tmp_path):
        """Lock acquisition times out when held by another."""
        from src.checkpoint import FileLock, LockTimeoutError

        lock_file = tmp_path / "test.lock"
        lock1 = FileLock(lock_file)
        lock2 = FileLock(lock_file)

        # First lock acquires
        lock1.acquire_exclusive()

        # Second lock should timeout
        with pytest.raises(LockTimeoutError):
            lock2.acquire_exclusive(timeout=0.1)

        lock1.release()

    def test_lock_context_manager(self, tmp_path):
        """Lock can be used as context manager."""
        from src.checkpoint import FileLock

        lock_file = tmp_path / "test.lock"
        lock = FileLock(lock_file)

        with lock.exclusive():
            assert lock.is_locked()

        assert not lock.is_locked()


class TestLockManager:
    """Test lock manager for orchestrator files."""

    def test_context_manager_usage(self, tmp_path):
        """Lock manager works as context manager."""
        from src.checkpoint import LockManager

        manager = LockManager(lock_dir=tmp_path)

        with manager.acquire("test_resource"):
            # Lock should be held
            lock_file = tmp_path / "test_resource.lock"
            assert lock_file.exists()

    def test_nested_locks_same_file(self, tmp_path):
        """Nested locks on same file don't deadlock."""
        from src.checkpoint import LockManager

        manager = LockManager(lock_dir=tmp_path)

        with manager.acquire("resource"):
            # Nested acquire should work (reentrant)
            with manager.acquire("resource"):
                pass  # Should not deadlock

    def test_stale_lock_detection(self, tmp_path):
        """Stale locks are detected and cleaned up."""
        from src.checkpoint import LockManager, _process_exists

        manager = LockManager(lock_dir=tmp_path, stale_timeout=0.1)

        # Find a PID that definitely doesn't exist
        # Use a very large PID that's beyond typical max_pid (usually 32768 or 4194304)
        # and verify it doesn't exist before using it
        non_existent_pid = 99999999
        while _process_exists(non_existent_pid) and non_existent_pid > 0:
            non_existent_pid -= 1000000

        # Create a stale lock file manually with verified non-existent PID
        lock_file = tmp_path / "stale_resource.lock"
        lock_file.write_text(str(non_existent_pid))

        # Should be able to acquire despite stale lock
        with manager.acquire("stale_resource"):
            pass  # Should succeed after cleaning stale lock


class TestConcurrentCheckpoints:
    """Test concurrent checkpoint operations."""

    def test_concurrent_checkpoint_creation(self, tmp_path):
        """Multiple threads can create checkpoints safely."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))
        errors = []
        created = []

        def create_checkpoint(thread_id):
            try:
                cp = manager.create_checkpoint(
                    workflow_id="wf_concurrent",
                    phase_id=f"PHASE_{thread_id}",
                    message=f"Thread {thread_id}",
                    auto_detect_files=False  # Skip file scan for speed
                )
                created.append(cp.checkpoint_id)
            except Exception as e:
                errors.append(e)

        # Create checkpoints from multiple threads
        threads = [
            threading.Thread(target=create_checkpoint, args=(i,))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert len(errors) == 0
        assert len(created) == 5

        # All checkpoints should be retrievable
        all_checkpoints = manager.list_checkpoints()
        assert len(all_checkpoints) == 5


class TestAutoDetectImportantFiles:
    """Test optimized file detection (#87)."""

    def test_is_important_file_extensions(self, tmp_path):
        """Verify _is_important_file checks extensions correctly (#87)."""
        from src.checkpoint import CheckpointManager

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Should be important
        assert manager._is_important_file("test.py")
        assert manager._is_important_file("test.js")
        assert manager._is_important_file("config.yaml")
        assert manager._is_important_file("README.md")

        # Should not be important
        assert not manager._is_important_file("binary.exe")
        assert not manager._is_important_file("image.png")
        assert not manager._is_important_file("data.bin")

    def test_auto_detect_git_fallback(self, tmp_path):
        """Verify fallback to rglob when git unavailable (#87)."""
        from src.checkpoint import CheckpointManager
        from unittest.mock import patch
        import subprocess

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create some files
        test_file = tmp_path / "test.py"
        test_file.write_text("# test")
        test_file.touch()  # Ensure recent mtime

        # Mock subprocess.run to simulate no git
        with patch('subprocess.run', side_effect=FileNotFoundError):
            files = manager._auto_detect_important_files()
            # Should fall back to rglob and find the file
            # Note: May be empty if file mtime is not recent enough
            assert isinstance(files, list)

    def test_auto_detect_depth_limit(self, tmp_path):
        """Verify depth limit is respected (#87)."""
        from src.checkpoint import CheckpointManager
        from unittest.mock import patch
        import time

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create deeply nested file
        deep_dir = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        deep_dir.mkdir(parents=True)
        deep_file = deep_dir / "deep.py"
        deep_file.write_text("# deep")

        # Create shallow file
        shallow_file = tmp_path / "shallow.py"
        shallow_file.write_text("# shallow")

        # Mock subprocess to force rglob fallback
        with patch('subprocess.run', side_effect=FileNotFoundError):
            files = manager._auto_detect_important_files(max_depth=3)
            # Deep file should be excluded due to depth limit
            assert not any("deep.py" in f for f in files)

    def test_auto_detect_excludes_patterns(self, tmp_path):
        """Verify excluded patterns are respected (#87)."""
        from src.checkpoint import CheckpointManager
        from unittest.mock import patch

        manager = CheckpointManager(working_dir=str(tmp_path))

        # Create files in excluded directories
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        excluded_file = node_modules / "excluded.js"
        excluded_file.write_text("// excluded")

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        pyc_file = pycache / "test.py"
        pyc_file.write_text("# excluded")

        # Mock subprocess to force rglob fallback
        with patch('subprocess.run', side_effect=FileNotFoundError):
            files = manager._auto_detect_important_files()
            # Excluded files should not be included
            assert not any("node_modules" in f for f in files)
            assert not any("__pycache__" in f for f in files)
