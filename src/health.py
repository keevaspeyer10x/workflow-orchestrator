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
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Literal

logger = logging.getLogger(__name__)

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
        self.state_dir = self.working_dir / ".orchestrator" / "v3"
        self.state_file = self.state_dir / "state.json"
        self.lock_dir = self.working_dir / ".orchestrator" / "locks"

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
            if version != '3.0':
                return ComponentHealth(
                    name="state_file",
                    status="warning",
                    message=f"State version mismatch: expected 3.0, got {version}"
                )

            # Verify checksum exists
            if '_checksum' not in state:
                return ComponentHealth(
                    name="state_file",
                    status="warning",
                    message="State file missing checksum"
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
                    # Check if process exists
                    import os
                    try:
                        os.kill(pid, 0)
                    except OSError:
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
