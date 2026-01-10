"""
Tests for ApprovalGate - Agent-side approval interface.

PRD-005: Tests for auto-approval transparency and decision logging.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.approval_queue import ApprovalQueue, ApprovalRequest
from src.approval_gate import (
    ApprovalGate,
    WaitResult,
    AutoApprovalRule,
    DEFAULT_AUTO_APPROVAL_RULES,
)


class TestApprovalGateAutoApproval:
    """Tests for auto-approval behavior."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    @pytest.fixture
    def gate(self, queue):
        """Create an approval gate."""
        return ApprovalGate(queue, "test-agent", enable_notifications=False)

    def test_low_risk_auto_approves(self, gate):
        """LOW risk operations should auto-approve."""
        result = gate.request_approval(
            phase="EXECUTE",
            operation="Read config file",
            risk_level="low"
        )
        assert result == WaitResult.AUTO_APPROVED

    def test_critical_never_auto_approves(self, gate, queue):
        """CRITICAL risk should never auto-approve."""
        # Mock the polling to return immediately
        with patch.object(gate, '_poll_for_decision', return_value=WaitResult.APPROVED):
            result = gate.request_approval(
                phase="PLAN",
                operation="Force push to main",
                risk_level="critical"
            )

        # Should have submitted to queue (not auto-approved)
        assert result == WaitResult.APPROVED  # From mocked poll

    def test_high_risk_never_auto_approves(self, gate, queue):
        """HIGH risk should never auto-approve."""
        with patch.object(gate, '_poll_for_decision', return_value=WaitResult.APPROVED):
            result = gate.request_approval(
                phase="EXECUTE",
                operation="Modify database schema",
                risk_level="high"
            )

        # Should have submitted to queue
        pending = queue.pending()
        assert len(pending) == 1

    def test_medium_execute_requires_human(self, gate, queue):
        """MEDIUM risk in EXECUTE phase should require human."""
        with patch.object(gate, '_poll_for_decision', return_value=WaitResult.APPROVED):
            gate.request_approval(
                phase="EXECUTE",
                operation="Modify source files",
                risk_level="medium"
            )

        # Should have submitted to queue
        pending = queue.pending()
        assert len(pending) == 1

    def test_medium_plan_auto_approves(self, gate):
        """MEDIUM risk in PLAN phase should auto-approve."""
        result = gate.request_approval(
            phase="PLAN",
            operation="Analyze codebase",
            risk_level="medium"
        )
        assert result == WaitResult.AUTO_APPROVED


class TestApprovalGateDecisionLogging:
    """Tests for decision transparency logging."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    @pytest.fixture
    def gate(self, queue):
        """Create an approval gate with logging."""
        return ApprovalGate(queue, "test-agent", enable_notifications=False)

    def test_auto_approval_logs_decision(self, gate):
        """Auto-approved requests should be logged with rationale."""
        gate.request_approval(
            phase="PLAN",
            operation="Read config file",
            risk_level="low"
        )

        log = gate.get_decision_log()
        assert len(log) == 1
        assert log[0]["status"] == "auto_approved"
        assert "rationale" in log[0]

    def test_auto_approval_log_includes_risk(self, gate):
        """Log entry should include risk level explanation."""
        gate.request_approval(
            phase="VERIFY",
            operation="Run tests",
            risk_level="low"
        )

        log = gate.get_decision_log()
        assert log[0]["risk_level"] == "low"
        assert "low risk" in log[0]["rationale"].lower()

    def test_get_decision_log_returns_all(self, gate, queue):
        """Decision log should include both auto and human approvals."""
        # Auto-approved
        gate.request_approval(
            phase="PLAN",
            operation="Op 1",
            risk_level="low"
        )

        # Human-required (mock the wait)
        with patch.object(gate, '_poll_for_decision', return_value=WaitResult.APPROVED):
            gate.request_approval(
                phase="EXECUTE",
                operation="Op 2",
                risk_level="high"
            )

        log = gate.get_decision_log()
        assert len(log) == 2
        statuses = [entry["status"] for entry in log]
        assert "auto_approved" in statuses
        assert "awaiting_decision" in statuses or "approved" in statuses

    def test_decision_log_format(self, gate):
        """Each log entry should have required fields."""
        gate.request_approval(
            phase="PLAN",
            operation="Test operation",
            risk_level="low",
            context={"files": ["test.py"]}
        )

        log = gate.get_decision_log()
        entry = log[0]

        required_fields = ["operation", "risk_level", "phase", "rationale", "timestamp"]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"


class TestApprovalGateRiskRationale:
    """Tests for risk-level rationale generation."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    @pytest.fixture
    def gate(self, queue):
        """Create an approval gate."""
        return ApprovalGate(queue, "test-agent", enable_notifications=False)

    def test_low_risk_rationale(self, gate):
        """LOW risk should explain why it's safe."""
        gate.request_approval(
            phase="VERIFY",
            operation="Run unit tests",
            risk_level="low"
        )

        log = gate.get_decision_log()
        rationale = log[0]["rationale"]
        assert "low risk" in rationale.lower()
        assert "auto-approved" in rationale.lower()

    def test_medium_risk_rationale_includes_phase(self, gate):
        """MEDIUM risk rationale should mention phase matters."""
        gate.request_approval(
            phase="PLAN",
            operation="Analyze code",
            risk_level="medium"
        )

        log = gate.get_decision_log()
        rationale = log[0]["rationale"]
        assert "PLAN" in rationale or "plan" in rationale.lower()


class TestApprovalGateNotifications:
    """Tests for notification behavior."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_notifications_disabled(self, queue):
        """Notifications can be disabled."""
        gate = ApprovalGate(queue, "test-agent", enable_notifications=False)

        with patch('subprocess.run') as mock_run:
            with patch.object(gate, '_poll_for_decision', return_value=WaitResult.APPROVED):
                gate.request_approval(
                    phase="EXECUTE",
                    operation="Test",
                    risk_level="high"
                )

        # subprocess.run should not be called for tmux notification
        tmux_calls = [c for c in mock_run.call_args_list if 'tmux' in str(c)]
        assert len(tmux_calls) == 0


class TestApprovalQueueDecisionSummary:
    """Tests for queue decision summary (PRD-005)."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_decision_summary_exists(self, queue):
        """Decision summary method should exist."""
        assert hasattr(queue, 'decision_summary')

    def test_decision_summary_groups_by_type(self, queue):
        """Summary should separate auto/human approved."""
        # Submit and approve some requests
        req1 = ApprovalRequest.create("a1", "PLAN", "Op 1", "low")
        req2 = ApprovalRequest.create("a2", "EXEC", "Op 2", "high")
        queue.submit(req1)
        queue.submit(req2)
        queue.approve(req2.id, reason="Looks good")

        # Mark req1 as auto-approved
        queue.mark_auto_approved(req1.id, "Low risk - auto-approved")

        summary = queue.decision_summary()
        assert "auto_approved" in summary
        assert "human_approved" in summary

    def test_decision_summary_includes_rationale(self, queue):
        """Auto-approved items should show rationale."""
        req = ApprovalRequest.create("a1", "PLAN", "Op 1", "low")
        queue.submit(req)
        queue.mark_auto_approved(req.id, "Low risk operation - auto-approved per policy")

        summary = queue.decision_summary()
        auto_items = summary.get("auto_approved", [])
        assert len(auto_items) >= 1
        assert "rationale" in auto_items[0] or auto_items[0].get("reason")


class TestCLIWatchCommand:
    """Tests for `orchestrator approval watch` command (PRD-005)."""

    @pytest.fixture
    def queue(self, tmp_path):
        """Create a queue with temp database."""
        db_path = tmp_path / "test_approvals.db"
        return ApprovalQueue(db_path)

    def test_watch_detects_pending(self, queue):
        """Watch should detect new pending requests."""
        req = ApprovalRequest.create("agent-1", "EXECUTE", "Test operation", "high")
        queue.submit(req)

        pending = queue.pending()
        assert len(pending) == 1
        assert pending[0].operation == "Test operation"

    def test_watch_shows_risk_level(self, queue):
        """Watch should display risk level."""
        req = ApprovalRequest.create("agent-1", "EXECUTE", "Risky op", "critical")
        queue.submit(req)

        pending = queue.pending()
        assert pending[0].risk_level == "critical"

    def test_watch_shows_phase(self, queue):
        """Watch should display phase."""
        req = ApprovalRequest.create("agent-1", "EXECUTE", "Test op", "high")
        queue.submit(req)

        pending = queue.pending()
        assert pending[0].phase == "EXECUTE"


class TestTmuxAdapterPromptInjection:
    """Tests for TmuxAdapter ApprovalGate injection (PRD-005)."""

    def test_prompt_template_includes_gate(self):
        """Agent prompt template should include ApprovalGate setup."""
        from src.prd.tmux_adapter import generate_approval_gate_instructions

        instructions = generate_approval_gate_instructions(
            agent_id="task-1",
            db_path="/path/to/.workflow_approvals.db"
        )

        assert "approval_gate" in instructions.lower() or "Approval Gate" in instructions
        assert "request_approval" in instructions
        assert "task-1" in instructions

    def test_prompt_template_includes_risk_guide(self):
        """Agent prompt should include risk classification guidelines."""
        from src.prd.tmux_adapter import generate_approval_gate_instructions

        instructions = generate_approval_gate_instructions(
            agent_id="task-1",
            db_path="/path/to/db"
        )

        assert "risk" in instructions.lower()
        assert "low" in instructions.lower()
        assert "high" in instructions.lower()

    def test_prompt_template_includes_sample_code(self):
        """Agent prompt should include sample approval request code."""
        from src.prd.tmux_adapter import generate_approval_gate_instructions

        instructions = generate_approval_gate_instructions(
            agent_id="task-1",
            db_path="/path/to/db"
        )

        # Should include sample code
        assert "gate.request_approval" in instructions or "request_approval(" in instructions
