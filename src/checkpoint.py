"""
Checkpoint and Resume System (Feature 5)

This module provides checkpoint creation, listing, and resume functionality
for workflow state persistence across sessions.

V3 additions:
- Checkpoint chaining (parent_checkpoint_id)
- File locking (FileLock class)
- Lock management (LockManager class)
"""

import atexit
import json
import logging
import hashlib
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING
from dataclasses import dataclass, field, asdict

# Platform-specific imports for file locking
WINDOWS = sys.platform == 'win32'
if WINDOWS:
    import msvcrt
    fcntl = None  # Not available on Windows
else:
    import fcntl
    msvcrt = None  # Not available on Unix

# Try to import psutil for cross-platform PID checking
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

if TYPE_CHECKING:
    from .path_resolver import OrchestratorPaths

logger = logging.getLogger(__name__)


# ============================================================================
# V3: File Locking for Concurrent Access
# ============================================================================

class LockTimeoutError(Exception):
    """Raised when lock acquisition times out."""
    pass


class FileLock:
    """
    File-based locking for concurrent access control.

    Cross-platform support:
    - Unix/Linux: Uses fcntl.flock()
    - Windows: Uses msvcrt.locking()

    Supports both shared (read) and exclusive (write) locks.
    """

    # Lock type constants (cross-platform)
    LOCK_EX = 1  # Exclusive lock
    LOCK_SH = 2  # Shared lock

    def __init__(self, lock_path: Path):
        """
        Initialize file lock.

        Args:
            lock_path: Path to the lock file
        """
        self.lock_path = Path(lock_path)
        self._fd: Optional[int] = None
        self._locked = False
        self._lock_type: Optional[int] = None

    def acquire_exclusive(self, timeout: float = 10.0) -> None:
        """
        Acquire exclusive (write) lock.

        Args:
            timeout: Maximum time to wait for lock (seconds)

        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout
        """
        self._acquire(self.LOCK_EX, timeout)

    def acquire_shared(self, timeout: float = 10.0) -> None:
        """
        Acquire shared (read) lock.

        Args:
            timeout: Maximum time to wait for lock (seconds)

        Raises:
            LockTimeoutError: If lock cannot be acquired within timeout
        """
        self._acquire(self.LOCK_SH, timeout)

    def _acquire(self, lock_type: int, timeout: float) -> None:
        """Internal method to acquire lock with timeout."""
        import time

        # Ensure parent directory exists
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Open/create lock file with close-on-exec flag
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, 'O_CLOEXEC'):
            flags |= os.O_CLOEXEC

        fd = None
        try:
            fd = os.open(str(self.lock_path), flags, 0o644)

            start = time.monotonic()
            while True:
                try:
                    if WINDOWS:
                        # Windows: msvcrt.locking
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        # Unix: fcntl.flock
                        flock_type = fcntl.LOCK_EX if lock_type == self.LOCK_EX else fcntl.LOCK_SH
                        fcntl.flock(fd, flock_type | fcntl.LOCK_NB)

                    # Lock acquired successfully
                    self._fd = fd
                    self._locked = True
                    self._lock_type = lock_type
                    return

                except (BlockingIOError, OSError):
                    # Lock held by another process - check timeout
                    if time.monotonic() - start >= timeout:
                        raise LockTimeoutError(
                            f"Could not acquire lock on {self.lock_path} within {timeout}s"
                        )
                    time.sleep(0.05)

        except LockTimeoutError:
            # Clean up fd on timeout
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            raise
        except Exception:
            # Clean up fd on any other exception
            if fd is not None:
                try:
                    os.close(fd)
                except Exception:
                    pass
            raise

    def release(self) -> None:
        """Release the lock."""
        if self._fd is not None:
            try:
                if WINDOWS:
                    msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._fd, fcntl.LOCK_UN)
            except Exception:
                pass  # Ignore errors during unlock
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
            self._locked = False
            self._lock_type = None

    def is_locked(self) -> bool:
        """Check if lock is currently held."""
        return self._locked

    @contextmanager
    def exclusive(self, timeout: float = 10.0):
        """Context manager for exclusive lock."""
        self.acquire_exclusive(timeout)
        try:
            yield
        finally:
            self.release()

    @contextmanager
    def shared(self, timeout: float = 10.0):
        """Context manager for shared lock."""
        self.acquire_shared(timeout)
        try:
            yield
        finally:
            self.release()

    def __del__(self):
        """Ensure lock is released on garbage collection."""
        self.release()


def _process_exists(pid: int) -> bool:
    """
    Check if a process with the given PID exists.

    Cross-platform: Uses psutil if available, falls back to os.kill on Unix.
    """
    if HAS_PSUTIL:
        return psutil.pid_exists(pid)

    if WINDOWS:
        # On Windows without psutil, we can't reliably check
        # Assume process exists to be safe
        return True

    # Unix fallback: use signal 0
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class LockManager:
    """
    Manages locks for orchestrator resources.

    Provides:
    - Named resource locking
    - Reentrant locks (same thread can acquire multiple times)
    - Stale lock detection and cleanup
    - Cross-platform support (Unix/Windows)
    """

    def __init__(self, lock_dir: Path, stale_timeout: float = 300.0):
        """
        Initialize lock manager.

        Args:
            lock_dir: Directory to store lock files
            stale_timeout: Time after which locks are considered stale (seconds)
        """
        self.lock_dir = Path(lock_dir).resolve()  # Resolve to prevent symlink attacks
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.stale_timeout = stale_timeout
        self._locks: dict[str, FileLock] = {}
        self._lock_counts: dict[str, int] = {}
        self._thread_lock = threading.Lock()
        self._thread_ids: dict[str, int] = {}  # Track which thread holds each lock

        # Register cleanup on exit
        atexit.register(self._cleanup_all)

    @contextmanager
    def acquire(self, resource_name: str, timeout: float = 10.0):
        """
        Acquire lock on a named resource.

        Args:
            resource_name: Name of the resource to lock
            timeout: Maximum time to wait for lock

        Yields:
            None (lock is held while in context)

        Note:
            This implementation carefully avoids holding the thread lock while
            yielding, to prevent deadlocks. The pattern is:
            1. Hold thread lock to check/update state
            2. Release thread lock before yielding
            3. Re-acquire thread lock in finally to cleanup
        """
        current_thread = threading.current_thread().ident
        lock_path = self.lock_dir / f"{resource_name}.lock"
        is_reentrant = False
        lock = None

        # Phase 1: Check state and prepare (under thread lock)
        with self._thread_lock:
            # Check for reentrant acquisition (same thread re-acquiring)
            if resource_name in self._locks:
                if self._thread_ids.get(resource_name) == current_thread:
                    self._lock_counts[resource_name] += 1
                    is_reentrant = True

            if not is_reentrant:
                # Clean stale lock if needed
                self._clean_stale_lock(lock_path)

                # Create new lock
                lock = FileLock(lock_path)
                self._locks[resource_name] = lock
                self._lock_counts[resource_name] = 1
                self._thread_ids[resource_name] = current_thread

        # Phase 2: Acquire file lock (outside thread lock to prevent deadlock)
        if is_reentrant:
            try:
                yield
            finally:
                with self._thread_lock:
                    self._lock_counts[resource_name] -= 1
            return

        try:
            lock.acquire_exclusive(timeout)
            # Write PID to lock file (atomically using the fd we already have)
            try:
                with open(lock_path, 'w') as f:
                    f.write(str(os.getpid()))
            except Exception:
                pass  # Non-critical if we can't write PID

            yield

        finally:
            # Phase 3: Cleanup (under thread lock)
            with self._thread_lock:
                self._lock_counts[resource_name] -= 1
                if self._lock_counts[resource_name] == 0:
                    lock.release()
                    self._locks.pop(resource_name, None)
                    self._lock_counts.pop(resource_name, None)
                    self._thread_ids.pop(resource_name, None)

    def _clean_stale_lock(self, lock_path: Path) -> None:
        """Remove stale lock if process is dead."""
        if not lock_path.exists():
            return

        # Security: Verify lock_path is within lock_dir (prevent symlink attacks)
        try:
            resolved_path = lock_path.resolve()
            if not str(resolved_path).startswith(str(self.lock_dir)):
                logger.warning(f"Lock path outside lock_dir, ignoring: {lock_path}")
                return
        except (OSError, ValueError):
            return

        try:
            content = lock_path.read_text().strip()
            if content:
                pid = int(content)
                # Check if process exists using cross-platform function
                if not _process_exists(pid):
                    logger.info(f"Removing stale lock: {lock_path} (PID {pid} not running)")
                    lock_path.unlink()
        except (ValueError, FileNotFoundError):
            pass

    def _cleanup_all(self) -> None:
        """Release all locks on process exit."""
        for lock in list(self._locks.values()):
            try:
                lock.release()
            except Exception:
                pass
        self._locks.clear()
        self._lock_counts.clear()
        self._thread_ids.clear()


@dataclass
class CheckpointData:
    """
    Data model for a workflow checkpoint.

    Contains all information needed to resume a workflow in a new session.
    V3: Added parent_checkpoint_id for checkpoint chaining.
    """
    checkpoint_id: str
    workflow_id: str
    phase_id: str
    item_id: Optional[str]
    timestamp: str
    message: Optional[str] = None
    context_summary: Optional[str] = None
    key_decisions: List[str] = field(default_factory=list)
    file_manifest: List[str] = field(default_factory=list)
    workflow_state_snapshot: Optional[dict] = None
    parent_checkpoint_id: Optional[str] = None  # V3: Checkpoint chaining

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CheckpointData':
        """Create from dictionary."""
        # Handle legacy checkpoints without parent_checkpoint_id
        if 'parent_checkpoint_id' not in data:
            data['parent_checkpoint_id'] = None
        return cls(**data)


class CheckpointManager:
    """
    Manages checkpoint creation, storage, and retrieval.
    """

    def __init__(
        self,
        working_dir: str = ".",
        paths: Optional["OrchestratorPaths"] = None
    ):
        self.working_dir = Path(working_dir).resolve()

        # CORE-025: Use OrchestratorPaths if provided, else use legacy path
        if paths is not None:
            self.checkpoints_dir = paths.checkpoints_dir()
        else:
            # Legacy path for backward compatibility
            self.checkpoints_dir = self.working_dir / ".workflow_checkpoints"

        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
    
    def create_checkpoint(
        self,
        workflow_id: str,
        phase_id: str,
        item_id: Optional[str] = None,
        message: Optional[str] = None,
        context_summary: Optional[str] = None,
        key_decisions: Optional[List[str]] = None,
        file_manifest: Optional[List[str]] = None,
        workflow_state: Optional[dict] = None,
        auto_detect_files: bool = True,
        parent_checkpoint_id: Optional[str] = None  # V3: Checkpoint chaining
    ) -> CheckpointData:
        """
        Create a new checkpoint.

        Args:
            workflow_id: ID of the workflow
            phase_id: Current phase ID
            item_id: Optional current item ID
            message: Optional checkpoint message
            context_summary: Optional summary of current context
            key_decisions: Optional list of key decisions made
            file_manifest: Optional list of important files
            workflow_state: Optional workflow state snapshot
            auto_detect_files: Whether to auto-detect recently modified files
            parent_checkpoint_id: V3: ID of parent checkpoint for chaining

        Returns:
            CheckpointData: The created checkpoint
        """
        import random
        timestamp = datetime.now(timezone.utc)

        # Generate checkpoint ID (includes microseconds + random suffix to avoid collisions)
        random_suffix = random.randint(0, 9999)
        checkpoint_id = f"cp_{timestamp.strftime('%Y%m%d_%H%M%S')}_{timestamp.microsecond:06d}_{random_suffix:04d}_{hashlib.md5(workflow_id.encode()).hexdigest()[:4]}"

        # Auto-detect files if requested
        files = list(file_manifest or [])
        if auto_detect_files:
            auto_files = self._auto_detect_important_files()
            files.extend(f for f in auto_files if f not in files)

        # Auto-generate context summary if not provided
        if not context_summary and workflow_state:
            context_summary = self._generate_context_summary(workflow_state, phase_id)

        checkpoint = CheckpointData(
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            phase_id=phase_id,
            item_id=item_id,
            timestamp=timestamp.isoformat(),
            message=message,
            context_summary=context_summary,
            key_decisions=key_decisions or [],
            file_manifest=files,
            workflow_state_snapshot=workflow_state,
            parent_checkpoint_id=parent_checkpoint_id  # V3: Checkpoint chaining
        )

        # Save checkpoint
        self._save_checkpoint(checkpoint)

        logger.info(f"Created checkpoint: {checkpoint_id}")
        return checkpoint
    
    def _save_checkpoint(self, checkpoint: CheckpointData) -> None:
        """Save a checkpoint to disk."""
        filepath = self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json"
        with open(filepath, 'w') as f:
            json.dump(checkpoint.to_dict(), f, indent=2, default=str)
    
    def _auto_detect_important_files(self, max_files: int = 10) -> List[str]:
        """
        Auto-detect important files based on recent modifications.
        
        Returns files modified in the last hour, excluding hidden files and common artifacts.
        """
        import time
        
        one_hour_ago = time.time() - 3600
        important_files = []
        
        # Patterns to exclude
        exclude_patterns = {
            '.git', '__pycache__', 'node_modules', '.pytest_cache',
            '.workflow_state.json', '.workflow_log.jsonl', '.workflow_checkpoints'
        }
        
        # Extensions to include
        include_extensions = {
            '.py', '.js', '.ts', '.yaml', '.yml', '.json', '.md',
            '.html', '.css', '.sh', '.sql', '.env'
        }
        
        try:
            for filepath in self.working_dir.rglob('*'):
                if filepath.is_file():
                    # Skip excluded patterns
                    if any(p in str(filepath) for p in exclude_patterns):
                        continue
                    
                    # Check extension
                    if filepath.suffix.lower() not in include_extensions:
                        continue
                    
                    # Check modification time
                    if filepath.stat().st_mtime > one_hour_ago:
                        rel_path = str(filepath.relative_to(self.working_dir))
                        important_files.append(rel_path)
                        
                        if len(important_files) >= max_files:
                            break
        except Exception as e:
            logger.warning(f"Error auto-detecting files: {e}")
        
        return important_files
    
    def _generate_context_summary(self, workflow_state: dict, phase_id: str) -> str:
        """Generate a context summary from workflow state."""
        lines = []
        
        task = workflow_state.get('task_description', 'Unknown task')
        lines.append(f"Task: {task}")
        lines.append(f"Current Phase: {phase_id}")
        
        # Count completed items
        phases = workflow_state.get('phases', {})
        total_completed = 0
        total_items = 0
        for phase_data in phases.values():
            items = phase_data.get('items', {})
            for item_data in items.values():
                total_items += 1
                if item_data.get('status') == 'completed':
                    total_completed += 1
        
        lines.append(f"Progress: {total_completed}/{total_items} items completed")
        
        # Add constraints if present
        constraints = workflow_state.get('constraints', [])
        if constraints:
            lines.append(f"Constraints: {len(constraints)} active")
        
        return "; ".join(lines)
    
    def list_checkpoints(
        self,
        workflow_id: Optional[str] = None,
        include_completed: bool = False
    ) -> List[CheckpointData]:
        """
        List all checkpoints, optionally filtered by workflow.
        
        Args:
            workflow_id: Optional workflow ID to filter by
            include_completed: Whether to include checkpoints from completed workflows
        
        Returns:
            List of checkpoints, sorted by timestamp (newest first)
        """
        checkpoints = []
        
        for filepath in self.checkpoints_dir.glob("cp_*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    checkpoint = CheckpointData.from_dict(data)
                    
                    # Filter by workflow if specified
                    if workflow_id and checkpoint.workflow_id != workflow_id:
                        continue
                    
                    checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(f"Error loading checkpoint {filepath}: {e}")
        
        # Sort by timestamp (newest first)
        checkpoints.sort(key=lambda c: c.timestamp, reverse=True)
        
        return checkpoints
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointData]:
        """Get a specific checkpoint by ID."""
        filepath = self.checkpoints_dir / f"{checkpoint_id}.json"
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                return CheckpointData.from_dict(data)
        except Exception as e:
            logger.error(f"Error loading checkpoint {checkpoint_id}: {e}")
            return None
    
    def get_latest_checkpoint(self, workflow_id: Optional[str] = None) -> Optional[CheckpointData]:
        """Get the most recent checkpoint."""
        checkpoints = self.list_checkpoints(workflow_id=workflow_id)
        return checkpoints[0] if checkpoints else None

    def get_checkpoint_chain(self, checkpoint_id: str, max_depth: int = 1000) -> List[CheckpointData]:
        """
        V3: Get the full checkpoint chain (lineage) from a checkpoint.

        Follows parent_checkpoint_id links to build the complete chain.
        Returns checkpoints in order from newest to oldest.

        Args:
            checkpoint_id: ID of the checkpoint to start from
            max_depth: Maximum chain depth to prevent infinite loops (default 1000)

        Returns:
            List of checkpoints in the chain (newest first)
        """
        chain = []
        current_id = checkpoint_id
        seen_ids = set()  # Cycle detection

        while current_id and len(chain) < max_depth:
            # Cycle detection
            if current_id in seen_ids:
                logger.warning(f"Cycle detected in checkpoint chain at {current_id}")
                break
            seen_ids.add(current_id)

            checkpoint = self.get_checkpoint(current_id)
            if checkpoint is None:
                break
            chain.append(checkpoint)
            current_id = checkpoint.parent_checkpoint_id

        return chain

    def cleanup_old_checkpoints(
        self,
        max_age_days: int = 30,
        keep_min: int = 5
    ) -> int:
        """
        Remove old checkpoints.
        
        Args:
            max_age_days: Maximum age in days for checkpoints to keep
            keep_min: Minimum number of checkpoints to keep regardless of age
        
        Returns:
            Number of checkpoints removed
        """
        from datetime import timedelta
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        checkpoints = self.list_checkpoints()
        
        # Keep at least keep_min checkpoints
        if len(checkpoints) <= keep_min:
            return 0
        
        removed = 0
        for checkpoint in checkpoints[keep_min:]:
            try:
                checkpoint_time = datetime.fromisoformat(checkpoint.timestamp.replace('Z', '+00:00'))
                if checkpoint_time < cutoff:
                    filepath = self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json"
                    filepath.unlink()
                    removed += 1
                    logger.info(f"Removed old checkpoint: {checkpoint.checkpoint_id}")
            except Exception as e:
                logger.warning(f"Error removing checkpoint {checkpoint.checkpoint_id}: {e}")
        
        return removed
    
    def generate_resume_prompt(self, checkpoint: CheckpointData) -> str:
        """
        Generate a prompt for resuming from a checkpoint.
        
        This prompt is designed to be fed to an LLM to restore context.
        """
        lines = [
            "=" * 60,
            "WORKFLOW RESUME FROM CHECKPOINT",
            "=" * 60,
            "",
            f"Checkpoint: {checkpoint.checkpoint_id}",
            f"Created: {checkpoint.timestamp}",
            f"Workflow: {checkpoint.workflow_id}",
            f"Phase: {checkpoint.phase_id}",
        ]
        
        if checkpoint.item_id:
            lines.append(f"Last Item: {checkpoint.item_id}")
        
        if checkpoint.message:
            lines.append("")
            lines.append(f"Message: {checkpoint.message}")
        
        if checkpoint.context_summary:
            lines.append("")
            lines.append("Context Summary:")
            lines.append(f"  {checkpoint.context_summary}")
        
        if checkpoint.key_decisions:
            lines.append("")
            lines.append("Key Decisions Made:")
            for decision in checkpoint.key_decisions:
                lines.append(f"  - {decision}")
        
        if checkpoint.file_manifest:
            lines.append("")
            lines.append("Important Files:")
            for filepath in checkpoint.file_manifest:
                lines.append(f"  - {filepath}")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append("Run 'orchestrator status' to see current workflow state.")
        lines.append("=" * 60)
        
        return "\n".join(lines)
