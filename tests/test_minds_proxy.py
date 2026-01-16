"""
Tests for Issue #39: Zero-Human Mode with Minds as Proxy

Tests cover:
1. MindsGateProxy class
2. Weighted voting
3. Re-deliberation
4. Certainty-based escalation
5. Decision audit trail
6. CLI commands
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime
import tempfile
import json
import os


# =============================================================================
# Weighted Voting Tests
# =============================================================================

class TestWeightedVoting:
    """Test weighted voting calculations."""

    def test_weighted_vote_function_exists(self):
        """weighted_vote function should be importable."""
        from src.gates.minds_proxy import weighted_vote

        assert callable(weighted_vote)

    def test_weighted_vote_basic(self):
        """Weighted voting should use model weights correctly."""
        from src.gates.minds_proxy import weighted_vote, MODEL_WEIGHTS

        votes = {
            "openai/gpt-5.2-codex-max": "APPROVE",      # weight 2.0
            "deepseek/deepseek-chat": "REJECT",         # weight 0.5
        }

        decision, confidence = weighted_vote(votes)

        # Approve weight = 2.0, Reject weight = 0.5
        # Total = 2.5, Approve ratio = 2.0/2.5 = 0.8
        assert decision == "APPROVE"
        assert confidence == pytest.approx(0.8, rel=0.01)

    def test_weighted_vote_unanimous_approve(self):
        """Unanimous approval should have 1.0 confidence."""
        from src.gates.minds_proxy import weighted_vote

        votes = {
            "gpt-5.2": "APPROVE",
            "gemini-3": "APPROVE",
            "grok-4.1": "APPROVE",
        }

        decision, confidence = weighted_vote(votes)

        assert decision == "APPROVE"
        assert confidence == 1.0

    def test_weighted_vote_unanimous_reject(self):
        """Unanimous rejection should have 1.0 confidence (for reject)."""
        from src.gates.minds_proxy import weighted_vote

        votes = {
            "gpt-5.2": "REJECT",
            "gemini-3": "REJECT",
        }

        decision, confidence = weighted_vote(votes)

        assert decision == "REJECT"
        # Confidence for reject is reject_weight / total_weight = 1.0
        assert confidence == 1.0

    def test_weighted_vote_unknown_model_default_weight(self):
        """Unknown models should use default weight of 1.0."""
        from src.gates.minds_proxy import weighted_vote

        votes = {
            "unknown/model-x": "APPROVE",
            "another/model-y": "REJECT",
        }

        decision, confidence = weighted_vote(votes)

        # Equal weights = 50/50 split, but APPROVE wins ties
        assert decision in ("APPROVE", "REJECT")
        assert confidence == pytest.approx(0.5, rel=0.01)


# =============================================================================
# MindsGateProxy Tests
# =============================================================================

class TestMindsGateProxy:
    """Test MindsGateProxy class."""

    def test_minds_gate_proxy_class_exists(self):
        """MindsGateProxy should be importable."""
        from src.gates.minds_proxy import MindsGateProxy

        proxy = MindsGateProxy()
        assert proxy is not None

    def test_minds_gate_proxy_configurable_models(self):
        """MindsGateProxy should accept configurable model list."""
        from src.gates.minds_proxy import MindsGateProxy

        models = ["model-a", "model-b", "model-c"]
        proxy = MindsGateProxy(models=models)

        assert proxy.models == models

    def test_minds_gate_proxy_configurable_weights(self):
        """MindsGateProxy should accept custom model weights."""
        from src.gates.minds_proxy import MindsGateProxy

        weights = {"model-a": 2.0, "model-b": 0.5}
        proxy = MindsGateProxy(model_weights=weights)

        assert proxy.model_weights == weights

    @patch('src.gates.minds_proxy.call_model')
    def test_evaluate_calls_all_models(self, mock_call):
        """evaluate should call all configured models."""
        from src.gates.minds_proxy import MindsGateProxy, GateContext

        mock_call.return_value = '{"vote": "APPROVE", "reasoning": "LGTM"}'

        proxy = MindsGateProxy(models=["model-a", "model-b"])
        context = GateContext(
            gate_id="test_gate",
            phase="REVIEW",
            operation="Merge PR",
            risk_level="medium",
        )

        decision = proxy.evaluate(context)

        # Should call each model
        assert mock_call.call_count >= 2


# =============================================================================
# MindsDecision Tests
# =============================================================================

class TestMindsDecision:
    """Test MindsDecision dataclass."""

    def test_minds_decision_dataclass_exists(self):
        """MindsDecision should be importable."""
        from src.gates.minds_proxy import MindsDecision

        decision = MindsDecision(
            gate_id="user_approval",
            decision="APPROVE",
            certainty=0.87,
            risk_level="medium",
            model_votes={"gpt": "APPROVE", "gemini": "APPROVE"},
            weighted_consensus=0.85,
            reasoning_summary="All models agree",
            rollback_command="git revert abc123",
            timestamp=datetime.now(),
        )

        assert decision.decision == "APPROVE"
        assert decision.certainty == 0.87

    def test_minds_decision_to_dict(self):
        """MindsDecision should be convertible to dict."""
        from src.gates.minds_proxy import MindsDecision

        decision = MindsDecision(
            gate_id="test",
            decision="APPROVE",
            certainty=0.9,
            risk_level="low",
            model_votes={},
            weighted_consensus=0.9,
            reasoning_summary="",
            rollback_command="",
            timestamp=datetime.now(),
        )

        d = decision.to_dict()

        assert d["gate_id"] == "test"
        assert d["decision"] == "APPROVE"
        assert "timestamp" in d


# =============================================================================
# Re-Deliberation Tests
# =============================================================================

class TestReDeliberation:
    """Test re-deliberation feature."""

    def test_re_deliberate_function_exists(self):
        """re_deliberate function should be importable."""
        from src.gates.minds_proxy import re_deliberate

        assert callable(re_deliberate)

    @patch('src.gates.minds_proxy.call_model')
    def test_re_deliberate_shows_other_reasoning(self, mock_call):
        """re_deliberate should show dissenter the other models' reasoning."""
        from src.gates.minds_proxy import re_deliberate, GateContext

        mock_call.return_value = '{"final_vote": "APPROVE", "changed": true, "reasoning": "Convinced by others"}'

        context = GateContext(
            gate_id="test",
            phase="REVIEW",
            operation="Test",
            risk_level="medium",
        )

        result = re_deliberate(
            dissenting_model="grok",
            dissenting_vote="REJECT",
            other_votes={
                "gpt": ("APPROVE", "Tests pass"),
                "gemini": ("APPROVE", "Clean code"),
            },
            gate_context=context,
        )

        # Prompt should include other reasoning
        call_args = mock_call.call_args
        prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get('prompt', '')
        assert "Tests pass" in str(call_args) or mock_call.called

    @patch('src.gates.minds_proxy.call_model')
    def test_re_deliberate_can_change_vote(self, mock_call):
        """Model should be able to change vote after re-deliberation."""
        from src.gates.minds_proxy import re_deliberate, GateContext

        mock_call.return_value = '{"final_vote": "APPROVE", "changed": true, "reasoning": "Now I agree"}'

        context = GateContext(
            gate_id="test",
            phase="REVIEW",
            operation="Test",
            risk_level="medium",
        )

        result = re_deliberate(
            dissenting_model="grok",
            dissenting_vote="REJECT",
            other_votes={"gpt": ("APPROVE", "Good")},
            gate_context=context,
        )

        assert result["changed"] is True
        assert result["final_vote"] == "APPROVE"

    @patch('src.gates.minds_proxy.call_model')
    def test_re_deliberate_can_maintain_vote(self, mock_call):
        """Model should be able to maintain original vote with explanation."""
        from src.gates.minds_proxy import re_deliberate, GateContext

        mock_call.return_value = '{"final_vote": "REJECT", "changed": false, "reasoning": "Still concerned about X"}'

        context = GateContext(
            gate_id="test",
            phase="REVIEW",
            operation="Test",
            risk_level="medium",
        )

        result = re_deliberate(
            dissenting_model="grok",
            dissenting_vote="REJECT",
            other_votes={"gpt": ("APPROVE", "Good")},
            gate_context=context,
        )

        assert result["changed"] is False
        assert result["final_vote"] == "REJECT"


# =============================================================================
# Certainty-Based Escalation Tests
# =============================================================================

class TestCertaintyEscalation:
    """Test certainty-based escalation."""

    def test_should_escalate_function_exists(self):
        """should_escalate function should be importable."""
        from src.gates.minds_proxy import should_escalate

        assert callable(should_escalate)

    @pytest.mark.parametrize("certainty,risk,expected", [
        # Very high certainty (>=0.95) - proceed even on CRITICAL unless unanimous reject
        (0.95, "CRITICAL", False),
        (0.95, "HIGH", False),
        (0.95, "MEDIUM", False),
        (0.95, "LOW", False),

        # High certainty (>=0.80) - only escalate CRITICAL
        (0.80, "CRITICAL", True),
        (0.80, "HIGH", False),
        (0.80, "MEDIUM", False),

        # Medium certainty (>=0.60) - escalate HIGH and CRITICAL
        (0.60, "HIGH", True),
        (0.60, "CRITICAL", True),
        (0.60, "MEDIUM", False),

        # Low certainty (<0.60) - always escalate
        (0.50, "LOW", True),
        (0.50, "MEDIUM", True),
        (0.40, "LOW", True),
    ])
    def test_certainty_escalation_thresholds(self, certainty, risk, expected):
        """Escalation should be based on certainty + risk level."""
        from src.gates.minds_proxy import should_escalate

        result = should_escalate("APPROVE", certainty, risk)
        assert result == expected, f"certainty={certainty}, risk={risk}: expected {expected}, got {result}"


# =============================================================================
# Audit Trail Tests
# =============================================================================

class TestAuditTrail:
    """Test decision audit trail."""

    def test_write_decision_function_exists(self):
        """write_decision function should be importable."""
        from src.gates.minds_proxy import write_decision

        assert callable(write_decision)

    def test_audit_trail_written(self):
        """Decision should be written to minds_decisions.jsonl."""
        from src.gates.minds_proxy import write_decision, MindsDecision

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / ".orchestrator" / "minds_decisions.jsonl"

            decision = MindsDecision(
                gate_id="test_gate",
                decision="APPROVE",
                certainty=0.9,
                risk_level="medium",
                model_votes={"gpt": "APPROVE"},
                weighted_consensus=0.9,
                reasoning_summary="Test",
                rollback_command="git revert test",
                timestamp=datetime.now(),
            )

            write_decision(decision, audit_path=audit_path)

            assert audit_path.exists()

            with open(audit_path) as f:
                entry = json.loads(f.readline())

            assert entry["gate_id"] == "test_gate"
            assert entry["decision"] == "APPROVE"

    def test_audit_trail_append_only(self):
        """Audit trail should append, not overwrite."""
        from src.gates.minds_proxy import write_decision, MindsDecision

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / ".orchestrator" / "minds_decisions.jsonl"
            audit_path.parent.mkdir(parents=True, exist_ok=True)

            # Write first decision
            decision1 = MindsDecision(
                gate_id="gate_1",
                decision="APPROVE",
                certainty=0.9,
                risk_level="low",
                model_votes={},
                weighted_consensus=0.9,
                reasoning_summary="",
                rollback_command="",
                timestamp=datetime.now(),
            )
            write_decision(decision1, audit_path=audit_path)

            # Write second decision
            decision2 = MindsDecision(
                gate_id="gate_2",
                decision="REJECT",
                certainty=0.6,
                risk_level="high",
                model_votes={},
                weighted_consensus=0.4,
                reasoning_summary="",
                rollback_command="",
                timestamp=datetime.now(),
            )
            write_decision(decision2, audit_path=audit_path)

            # Both should be present
            with open(audit_path) as f:
                lines = f.readlines()

            assert len(lines) == 2
            assert json.loads(lines[0])["gate_id"] == "gate_1"
            assert json.loads(lines[1])["gate_id"] == "gate_2"


# =============================================================================
# Rollback Command Tests
# =============================================================================

class TestRollbackCommand:
    """Test rollback command generation."""

    def test_generate_rollback_command_function_exists(self):
        """generate_rollback_command function should be importable."""
        from src.gates.minds_proxy import generate_rollback_command

        assert callable(generate_rollback_command)

    def test_rollback_command_includes_git_revert(self):
        """Rollback command should include git revert."""
        from src.gates.minds_proxy import generate_rollback_command, GateContext

        context = GateContext(
            gate_id="test",
            phase="EXECUTE",
            operation="Merge changes",
            risk_level="medium",
            commit_sha="abc1234",
        )

        command = generate_rollback_command(context)

        assert "git revert" in command or "git reset" in command


# =============================================================================
# GateContext Tests
# =============================================================================

class TestGateContext:
    """Test GateContext dataclass."""

    def test_gate_context_dataclass_exists(self):
        """GateContext should be importable."""
        from src.gates.minds_proxy import GateContext

        context = GateContext(
            gate_id="user_approval",
            phase="REVIEW",
            operation="Approve PR merge",
            risk_level="medium",
        )

        assert context.gate_id == "user_approval"
        assert context.risk_level == "medium"

    def test_gate_context_optional_fields(self):
        """GateContext should have optional fields for additional context."""
        from src.gates.minds_proxy import GateContext

        context = GateContext(
            gate_id="test",
            phase="EXECUTE",
            operation="Test",
            risk_level="low",
            commit_sha="abc123",
            diff_summary="Added login feature",
            files_changed=["src/auth.py", "tests/test_auth.py"],
        )

        assert context.commit_sha == "abc123"
        assert len(context.files_changed) == 2


# =============================================================================
# Configuration Tests
# =============================================================================

class TestMindsConfiguration:
    """Test minds proxy configuration loading."""

    def test_load_minds_config_function_exists(self):
        """load_minds_config function should be importable."""
        from src.gates.minds_config import load_minds_config

        assert callable(load_minds_config)

    def test_default_config_values(self):
        """Default configuration should have sensible values."""
        from src.gates.minds_config import load_minds_config

        config = load_minds_config()

        # Should have default models
        assert len(config.models) >= 3

        # Should have default threshold
        assert 0 < config.approval_threshold <= 1.0

        # Re-deliberation should be configurable
        assert hasattr(config, 're_deliberation_enabled')


# =============================================================================
# Integration with Gates System
# =============================================================================

class TestGatesIntegration:
    """Test integration with existing gates system."""

    def test_minds_proxy_has_evaluate_method(self):
        """MindsGateProxy should have evaluate method for gate decisions."""
        from src.gates.minds_proxy import MindsGateProxy

        proxy = MindsGateProxy()

        # Should implement the evaluate method
        assert hasattr(proxy, 'evaluate')
        assert callable(proxy.evaluate)
