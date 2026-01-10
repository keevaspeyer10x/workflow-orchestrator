"""
Approval Gate - Agent-side interface for requesting human approval.

Implements the consensus recommendations from multi-model review:
- Polling with exponential backoff (2s → 10s → 30s)
- Auto-approval rules by risk level
- Timeout handling with notification
- tmux notification on gate hit

Usage:
    gate = ApprovalGate(queue, agent_id="task-1")

    # Request approval and wait
    result = gate.request_approval(
        phase="PLAN",
        operation="Implement feature X",
        risk_level="medium",
        context={"files": ["src/foo.py"]}
    )

    if result == WaitResult.APPROVED:
        # Continue with operation
    elif result == WaitResult.REJECTED:
        # Handle rejection
    elif result == WaitResult.TIMEOUT:
        # Handle timeout
"""

import os
import time
import subprocess
import logging
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime, timezone

from .approval_queue import ApprovalQueue, ApprovalRequest, RiskLevel

logger = logging.getLogger(__name__)


class WaitResult(Enum):
    """Result of waiting for approval."""
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    AUTO_APPROVED = "auto_approved"


@dataclass
class AutoApprovalRule:
    """Rule for automatic approval based on risk and phase."""
    risk_level: str
    phases: list[str]  # Phases where auto-approval applies
    requires_logging: bool = False


# Default auto-approval rules based on multi-model consensus
DEFAULT_AUTO_APPROVAL_RULES = [
    # LOW risk: Always auto-approve
    AutoApprovalRule("low", ["PLAN", "EXECUTE", "REVIEW", "VERIFY", "LEARN"]),
    # MEDIUM risk: Auto-approve in PLAN and VERIFY, require human for EXECUTE
    AutoApprovalRule("medium", ["PLAN", "VERIFY", "LEARN"], requires_logging=True),
    # HIGH risk: Never auto-approve
    # CRITICAL risk: Never auto-approve
]


class ApprovalGate:
    """
    Agent-side interface for requesting human approval at workflow gates.

    Features:
    - Submits approval requests to the queue
    - Polls for decisions with exponential backoff
    - Supports auto-approval based on risk level
    - Sends notifications when waiting
    - Handles timeouts gracefully
    """

    DEFAULT_TIMEOUT_MINUTES = 30

    # Polling intervals (seconds)
    INITIAL_INTERVAL = 2
    MEDIUM_INTERVAL = 10
    MAX_INTERVAL = 30

    # Thresholds for interval changes
    MEDIUM_THRESHOLD = 30  # Switch to medium after 30s
    MAX_THRESHOLD = 300    # Switch to max after 5min

    def __init__(
        self,
        queue: ApprovalQueue,
        agent_id: str,
        auto_approval_rules: Optional[list[AutoApprovalRule]] = None,
        enable_notifications: bool = True,
    ):
        """
        Initialize the approval gate.

        Args:
            queue: The approval queue to use
            agent_id: Identifier for this agent
            auto_approval_rules: Custom auto-approval rules (default: DEFAULT_AUTO_APPROVAL_RULES)
            enable_notifications: Whether to send tmux notifications
        """
        self.queue = queue
        self.agent_id = agent_id
        self.auto_approval_rules = auto_approval_rules or DEFAULT_AUTO_APPROVAL_RULES
        self.enable_notifications = enable_notifications
        self._decision_log: List[dict] = []

    def request_approval(
        self,
        phase: str,
        operation: str,
        risk_level: str = "medium",
        context: Optional[dict] = None,
        timeout_minutes: int = DEFAULT_TIMEOUT_MINUTES,
    ) -> WaitResult:
        """
        Request approval and wait for decision.

        This is the main method agents use to request approval at gates.
        It will:
        1. Check if auto-approval applies
        2. Submit request if not auto-approved
        3. Poll for decision with exponential backoff
        4. Return result when decision made or timeout

        Args:
            phase: Current workflow phase (PLAN, EXECUTE, etc.)
            operation: Human-readable description of the operation
            risk_level: Risk level (low, medium, high, critical)
            context: Additional context (files, diff, etc.)
            timeout_minutes: How long to wait before timing out

        Returns:
            WaitResult indicating outcome
        """
        # Check auto-approval
        if self._should_auto_approve(risk_level, phase):
            rationale = self._generate_rationale(risk_level, phase, operation)
            self._log_decision(
                operation=operation,
                risk_level=risk_level,
                phase=phase,
                status="auto_approved",
                rationale=rationale,
                context=context,
            )
            logger.info(f"Auto-approved: {operation} (risk={risk_level}, phase={phase})")
            return WaitResult.AUTO_APPROVED

        # Submit request
        request = ApprovalRequest.create(
            agent_id=self.agent_id,
            phase=phase,
            operation=operation,
            risk_level=risk_level,
            context=context or {},
        )

        request_id = self.queue.submit(request)
        self._notify_user(request)

        # Log that we're awaiting decision
        self._log_decision(
            operation=operation,
            risk_level=risk_level,
            phase=phase,
            status="awaiting_decision",
            rationale=f"Requires human approval: {risk_level} risk in {phase} phase",
            context=context,
            request_id=request_id,
        )

        # Poll for decision
        return self._poll_for_decision(request_id, timeout_minutes)

    def _should_auto_approve(self, risk_level: str, phase: str) -> bool:
        """Check if this request should be auto-approved."""
        # CRITICAL never auto-approves
        if risk_level == "critical":
            return False

        # HIGH never auto-approves
        if risk_level == "high":
            return False

        for rule in self.auto_approval_rules:
            if rule.risk_level == risk_level and phase in rule.phases:
                if rule.requires_logging:
                    logger.info(f"Auto-approving with logging: {risk_level}/{phase}")
                return True

        return False

    def _poll_for_decision(
        self,
        request_id: str,
        timeout_minutes: int,
    ) -> WaitResult:
        """
        Poll the queue for a decision.

        Uses exponential backoff:
        - First 30s: Check every 2s (user actively reviewing)
        - 30s-5min: Check every 10s (user thinking)
        - 5min+: Check every 30s (user away)
        """
        start = time.time()
        timeout_seconds = timeout_minutes * 60
        last_heartbeat = start

        while True:
            elapsed = time.time() - start

            if elapsed >= timeout_seconds:
                logger.warning(f"Approval request {request_id} timed out after {timeout_minutes}m")
                return WaitResult.TIMEOUT

            # Check status
            status = self.queue.check(request_id)

            if status == "approved":
                self.queue.consume(request_id)
                return WaitResult.APPROVED
            elif status == "rejected":
                self.queue.consume(request_id)
                return WaitResult.REJECTED
            elif status == "expired":
                return WaitResult.TIMEOUT

            # Update heartbeat periodically (every 30s)
            if time.time() - last_heartbeat >= 30:
                self.queue.heartbeat(request_id)
                last_heartbeat = time.time()

            # Calculate sleep interval with exponential backoff
            if elapsed < self.MEDIUM_THRESHOLD:
                interval = self.INITIAL_INTERVAL
            elif elapsed < self.MAX_THRESHOLD:
                interval = self.MEDIUM_INTERVAL
            else:
                interval = self.MAX_INTERVAL

            self._show_waiting_indicator(elapsed, interval)
            time.sleep(interval)

    def _notify_user(self, request: ApprovalRequest):
        """Send notification that approval is needed."""
        if not self.enable_notifications:
            return

        message = f"⏳ {request.agent_id}: {request.operation} ({request.risk_level})"

        # Try tmux notification (works with Happy app)
        try:
            subprocess.run(
                ["tmux", "display-message", "-d", "5000", message],
                capture_output=True,
                timeout=2,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            pass  # tmux not available

        # Also log
        logger.info(f"Approval needed: {request.operation}")
        print(f"\n{'='*60}")
        print(f"⏳ APPROVAL NEEDED")
        print(f"{'='*60}")
        print(f"Agent: {request.agent_id}")
        print(f"Phase: {request.phase}")
        print(f"Operation: {request.operation}")
        print(f"Risk: {request.risk_level}")
        print(f"Request ID: {request.id}")
        print(f"{'='*60}")
        print(f"Run: orchestrator pending")
        print(f"Or:  orchestrator review")
        print(f"{'='*60}\n")

    def _show_waiting_indicator(self, elapsed: float, next_check: int):
        """Show that agent is alive and waiting."""
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"\r⏳ Waiting for approval... {mins}m {secs}s (next check in {next_check}s)   ",
              end="", flush=True)

    def _log_decision(
        self,
        operation: str,
        risk_level: str,
        phase: str,
        status: str,
        rationale: str,
        context: Optional[dict] = None,
        request_id: Optional[str] = None,
    ) -> None:
        """
        Log a decision for transparency.

        Args:
            operation: Description of the operation
            risk_level: Risk level (low, medium, high, critical)
            phase: Workflow phase
            status: Decision status (auto_approved, awaiting_decision, approved, rejected)
            rationale: Human-readable explanation of why this decision was made
            context: Additional context
            request_id: Queue request ID if submitted
        """
        self._decision_log.append({
            "operation": operation,
            "risk_level": risk_level,
            "phase": phase,
            "status": status,
            "rationale": rationale,
            "context": context or {},
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def _generate_rationale(self, risk_level: str, phase: str, operation: str) -> str:
        """
        Generate a human-readable rationale for auto-approval.

        Args:
            risk_level: The risk level
            phase: The workflow phase
            operation: The operation description

        Returns:
            Explanation of why this was auto-approved
        """
        if risk_level == "low":
            return (
                f"Auto-approved: Low risk operation in {phase} phase. "
                "Low risk operations (read files, run tests, lint) are safe to proceed automatically."
            )
        elif risk_level == "medium":
            return (
                f"Auto-approved: Medium risk in {phase} phase. "
                f"Medium risk operations are auto-approved in PLAN/VERIFY/LEARN phases "
                "as they don't make persistent changes. Logged for transparency."
            )
        else:
            # Should not reach here for auto-approve, but handle gracefully
            return f"Auto-approved: {risk_level} risk in {phase} phase."

    def get_decision_log(self) -> List[dict]:
        """
        Get the decision log for this session.

        Returns:
            List of decision entries with operation, risk, phase, rationale, timestamp
        """
        return self._decision_log.copy()

    def get_decision_summary(self) -> dict:
        """
        Get a summary of decisions grouped by type.

        Returns:
            Dict with 'auto_approved', 'human_required', 'approved', 'rejected' lists
        """
        summary = {
            "auto_approved": [],
            "human_required": [],
        }

        for entry in self._decision_log:
            if entry["status"] == "auto_approved":
                summary["auto_approved"].append(entry)
            else:
                summary["human_required"].append(entry)

        return summary


def create_gate(
    agent_id: str,
    db_path: Optional[str] = None,
) -> ApprovalGate:
    """
    Convenience function to create an approval gate.

    Args:
        agent_id: Identifier for this agent
        db_path: Optional path to approval database

    Returns:
        Configured ApprovalGate
    """
    queue = ApprovalQueue(db_path) if db_path else ApprovalQueue()
    return ApprovalGate(queue, agent_id)
