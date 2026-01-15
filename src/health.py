"""
Health Check System for v3 Hybrid Orchestration.

Provides system health checks for workflow orchestrator components.

Features:
- State file integrity checks
- Lock state verification
- Structured health reports
- JSON output for automation
"""

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Literal

# Try to import psutil for cross-platform PID checking
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

WINDOWS = sys.platform == 'win32'

logger = logging.getLogger(__name__)


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
    import os
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

StatusType = Literal["ok", "warning", "error"]


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: StatusType
    message: str = ""
    details: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}


@dataclass
class HealthReport:
    """Full health report for all components."""
    overall_status: StatusType
    components: List[ComponentHealth] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'overall_status': self.overall_status,
            'timestamp': self.timestamp,
            'components': [c.to_dict() for c in self.components]
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class HealthChecker:
    """
    Health checker for workflow orchestrator components.

    Checks:
    - State file integrity (valid JSON, correct version)
    - Lock state (no stale locks)
    - Checkpoint directory (accessible, not corrupted)
    """

    def __init__(self, working_dir: Path):
        """
        Initialize health checker.

        Args:
            working_dir: Working directory for orchestrator
        """
        self.working_dir = Path(working_dir)
        self.orchestrator_dir = self.working_dir / ".orchestrator"
        self.lock_dir = self.orchestrator_dir / "locks"

        # V3 Phase 5: Look for state in current session or v3 directory
        # Check for current session first
        current_session_file = self.orchestrator_dir / "current"
        if current_session_file.exists():
            session_id = current_session_file.read_text().strip()
            self.state_file = self.orchestrator_dir / "sessions" / session_id / "state.json"
        else:
            # Fall back to v3 directory (for backward compatibility)
            self.state_file = self.orchestrator_dir / "v3" / "state.json"

    def check_state(self) -> ComponentHealth:
        """
        Check state file health.

        Returns:
            ComponentHealth for state file
        """
        if not self.state_file.exists():
            return ComponentHealth(
                name="state_file",
                status="ok",
                message="No active workflow (state file does not exist)"
            )

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            # Verify version
            version = state.get('_version')
            if version is None or not version.startswith('3.'):
                return ComponentHealth(
                    name="state_file",
                    status="warning",
                    message=f"State version mismatch: expected 3.x, got {version}"
                )

            # Verify checksum exists
            stored_checksum = state.get('_checksum')
            if not stored_checksum:
                return ComponentHealth(
                    name="state_file",
                    status="warning",
                    message="State file missing checksum"
                )

            # Verify checksum integrity
            from .state_version import compute_state_checksum
            computed_checksum = compute_state_checksum(state)
            if stored_checksum != computed_checksum:
                return ComponentHealth(
                    name="state_file",
                    status="error",
                    message="State file integrity check failed (checksum mismatch)",
                    details={
                        "stored_checksum": stored_checksum,
                        "computed_checksum": computed_checksum
                    }
                )

            return ComponentHealth(
                name="state_file",
                status="ok",
                message="State file is valid"
            )

        except json.JSONDecodeError as e:
            return ComponentHealth(
                name="state_file",
                status="error",
                message=f"Invalid JSON in state file: {e}"
            )
        except Exception as e:
            return ComponentHealth(
                name="state_file",
                status="error",
                message=f"Error reading state file: {e}"
            )

    def check_locks(self) -> ComponentHealth:
        """
        Check lock state health.

        Returns:
            ComponentHealth for locks
        """
        if not self.lock_dir.exists():
            return ComponentHealth(
                name="locks",
                status="ok",
                message="No locks present"
            )

        stale_locks = []
        for lock_file in self.lock_dir.glob("*.lock"):
            try:
                content = lock_file.read_text().strip()
                if content:
                    pid = int(content)
                    # Check if process exists (cross-platform)
                    if not _process_exists(pid):
                        stale_locks.append(lock_file.name)
            except (ValueError, FileNotFoundError):
                pass

        if stale_locks:
            return ComponentHealth(
                name="locks",
                status="warning",
                message=f"Found {len(stale_locks)} stale lock(s)",
                details={"stale_locks": stale_locks}
            )

        return ComponentHealth(
            name="locks",
            status="ok",
            message="No stale locks"
        )

    def check_checkpoints(self) -> ComponentHealth:
        """
        Check checkpoint directory health.

        Returns:
            ComponentHealth for checkpoints
        """
        checkpoint_dir = self.working_dir / ".workflow_checkpoints"

        if not checkpoint_dir.exists():
            return ComponentHealth(
                name="checkpoints",
                status="ok",
                message="No checkpoints present"
            )

        # Count checkpoints and check for corruption
        valid_count = 0
        corrupted = []

        for checkpoint_file in checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file, 'r') as f:
                    json.load(f)
                valid_count += 1
            except json.JSONDecodeError:
                corrupted.append(checkpoint_file.name)

        if corrupted:
            return ComponentHealth(
                name="checkpoints",
                status="warning",
                message=f"Found {len(corrupted)} corrupted checkpoint(s)",
                details={"corrupted": corrupted, "valid": valid_count}
            )

        return ComponentHealth(
            name="checkpoints",
            status="ok",
            message=f"{valid_count} checkpoint(s) valid"
        )

    def full_check(self) -> HealthReport:
        """
        Run full health check on all components.

        Returns:
            HealthReport with all component statuses
        """
        from datetime import datetime, timezone

        components = [
            self.check_state(),
            self.check_locks(),
            self.check_checkpoints(),
        ]

        # Determine overall status
        statuses = [c.status for c in components]
        if "error" in statuses:
            overall = "error"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "ok"

        return HealthReport(
            overall_status=overall,
            components=components,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
