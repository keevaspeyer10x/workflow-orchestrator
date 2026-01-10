"""
Day 3: Phase Token Tests

Tests for JWT-based phase token generation and verification.
"""

import pytest
import jwt as pyjwt
import time
from datetime import datetime, timedelta, timezone
from src.orchestrator.enforcement import WorkflowEnforcement


class TestTokenGeneration:
    """Tests for generate_phase_token()"""

    def test_generate_valid_token(self, enforcement_engine):
        """Should generate valid JWT token"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 20  # JWTs are long

    def test_token_contains_task_id(self, enforcement_engine):
        """Token should contain task_id claim"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        payload = pyjwt.decode(
            token,
            enforcement_engine.jwt_secret,
            algorithms=["HS256"]
        )

        assert payload["task_id"] == "task-123"

    def test_token_contains_phase(self, enforcement_engine):
        """Token should contain phase claim"""
        token = enforcement_engine.generate_phase_token("task-123", "TDD")

        payload = pyjwt.decode(
            token,
            enforcement_engine.jwt_secret,
            algorithms=["HS256"]
        )

        assert payload["phase"] == "TDD"

    def test_token_contains_allowed_tools(self, enforcement_engine):
        """Token should contain allowed_tools claim"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        payload = pyjwt.decode(
            token,
            enforcement_engine.jwt_secret,
            algorithms=["HS256"]
        )

        assert "allowed_tools" in payload
        assert isinstance(payload["allowed_tools"], list)

    def test_token_has_expiry(self, enforcement_engine):
        """Token should have exp claim"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        payload = pyjwt.decode(
            token,
            enforcement_engine.jwt_secret,
            algorithms=["HS256"]
        )

        assert "exp" in payload
        assert isinstance(payload["exp"], int)

    def test_token_expiry_is_future(self, enforcement_engine):
        """Token expiry should be in the future"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        payload = pyjwt.decode(
            token,
            enforcement_engine.jwt_secret,
            algorithms=["HS256"]
        )

        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)

        assert exp_time > now

    def test_token_expiry_matches_config(self, enforcement_engine):
        """Token expiry should match workflow configuration"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        payload = pyjwt.decode(
            token,
            enforcement_engine.jwt_secret,
            algorithms=["HS256"]
        )

        expected_expiry = enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"]
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)

        # Should expire approximately expected_expiry seconds from now
        time_until_exp = (exp_time - now).total_seconds()
        assert abs(time_until_exp - expected_expiry) < 5  # Within 5 seconds

    def test_generate_token_nonexistent_phase(self, enforcement_engine):
        """Should raise ValueError for non-existent phase"""
        with pytest.raises(ValueError, match="Phase not found"):
            enforcement_engine.generate_phase_token("task-123", "NONEXISTENT")

    def test_tokens_for_different_tasks_are_different(self, enforcement_engine):
        """Tokens for different tasks should be different"""
        token1 = enforcement_engine.generate_phase_token("task-1", "PLAN")
        token2 = enforcement_engine.generate_phase_token("task-2", "PLAN")

        assert token1 != token2

    def test_tokens_for_different_phases_are_different(self, enforcement_engine):
        """Tokens for different phases should be different"""
        token1 = enforcement_engine.generate_phase_token("task-123", "PLAN")
        token2 = enforcement_engine.generate_phase_token("task-123", "TDD")

        assert token1 != token2


class TestTokenVerification:
    """Tests for _verify_phase_token()"""

    def test_verify_valid_token(self, enforcement_engine):
        """Should verify valid token successfully"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        is_valid = enforcement_engine._verify_phase_token(token, "task-123", "PLAN")

        assert is_valid is True

    def test_verify_rejects_expired_token(self, enforcement_engine):
        """Should reject expired token"""
        # Generate token with -1 second expiry (already expired)
        original_expiry = enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"]
        enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"] = -1

        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        # Restore original expiry
        enforcement_engine.workflow["enforcement"]["phase_tokens"]["expiry_seconds"] = original_expiry

        # Wait a moment to ensure expiry
        time.sleep(0.1)

        is_valid = enforcement_engine._verify_phase_token(token, "task-123", "PLAN")

        assert is_valid is False

    def test_verify_rejects_tampered_token(self, enforcement_engine):
        """Should reject token with modified payload"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        # Tamper with token by modifying middle section
        parts = token.split('.')
        if len(parts) == 3:
            # Modify payload (middle part)
            tampered_token = parts[0] + "." + "tampered_payload_xyz" + "." + parts[2]

            is_valid = enforcement_engine._verify_phase_token(tampered_token, "task-123", "PLAN")

            assert is_valid is False

    def test_verify_rejects_wrong_task_id(self, enforcement_engine):
        """Should reject token when task_id doesn't match"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        is_valid = enforcement_engine._verify_phase_token(token, "task-456", "PLAN")

        assert is_valid is False

    def test_verify_rejects_wrong_phase(self, enforcement_engine):
        """Should reject token when phase doesn't match"""
        token = enforcement_engine.generate_phase_token("task-123", "PLAN")

        is_valid = enforcement_engine._verify_phase_token(token, "task-123", "TDD")

        assert is_valid is False

    def test_verify_rejects_malformed_token(self, enforcement_engine):
        """Should reject malformed token"""
        is_valid = enforcement_engine._verify_phase_token("not.a.valid.jwt", "task-123", "PLAN")

        assert is_valid is False

    def test_verify_rejects_empty_token(self, enforcement_engine):
        """Should reject empty token"""
        is_valid = enforcement_engine._verify_phase_token("", "task-123", "PLAN")

        assert is_valid is False

    def test_verify_rejects_wrong_signature(self, enforcement_engine):
        """Should reject token signed with different secret"""
        # Generate token with different secret
        wrong_secret = "wrong_secret_key_1234567890"
        exp_time = datetime.now(timezone.utc) + timedelta(hours=2)
        payload = {
            "task_id": "task-123",
            "phase": "PLAN",
            "allowed_tools": [],
            "exp": int(exp_time.timestamp())
        }
        wrong_token = pyjwt.encode(payload, wrong_secret, algorithm="HS256")

        is_valid = enforcement_engine._verify_phase_token(wrong_token, "task-123", "PLAN")

        assert is_valid is False


class TestTokenLifecycle:
    """Tests for complete token lifecycle"""

    def test_generate_and_verify_cycle(self, enforcement_engine):
        """Should successfully generate and verify token"""
        # Generate
        token = enforcement_engine.generate_phase_token("task-abc", "TDD")

        # Verify with correct params
        assert enforcement_engine._verify_phase_token(token, "task-abc", "TDD") is True

        # Verify fails with wrong params
        assert enforcement_engine._verify_phase_token(token, "task-xyz", "TDD") is False
        assert enforcement_engine._verify_phase_token(token, "task-abc", "IMPL") is False

    def test_multiple_tasks_concurrent(self, enforcement_engine):
        """Should handle multiple tasks with different tokens"""
        # Generate tokens for 3 different tasks
        token1 = enforcement_engine.generate_phase_token("task-1", "PLAN")
        token2 = enforcement_engine.generate_phase_token("task-2", "TDD")
        token3 = enforcement_engine.generate_phase_token("task-3", "PLAN")

        # Each token should only validate for its own task
        assert enforcement_engine._verify_phase_token(token1, "task-1", "PLAN") is True
        assert enforcement_engine._verify_phase_token(token1, "task-2", "PLAN") is False
        assert enforcement_engine._verify_phase_token(token1, "task-3", "PLAN") is False

        assert enforcement_engine._verify_phase_token(token2, "task-2", "TDD") is True
        assert enforcement_engine._verify_phase_token(token2, "task-1", "TDD") is False

        assert enforcement_engine._verify_phase_token(token3, "task-3", "PLAN") is True
        assert enforcement_engine._verify_phase_token(token3, "task-1", "PLAN") is False

    def test_phase_transition_token_flow(self, enforcement_engine):
        """Should handle phase transition with new tokens"""
        # Start in PLAN
        plan_token = enforcement_engine.generate_phase_token("task-123", "PLAN")
        assert enforcement_engine._verify_phase_token(plan_token, "task-123", "PLAN") is True

        # Transition to TDD - get new token
        tdd_token = enforcement_engine.generate_phase_token("task-123", "TDD")
        assert enforcement_engine._verify_phase_token(tdd_token, "task-123", "TDD") is True

        # Old token should not work for new phase
        assert enforcement_engine._verify_phase_token(plan_token, "task-123", "TDD") is False


class TestEdgeCases:
    """Edge case tests for phase tokens"""

    def test_very_long_task_id(self, enforcement_engine):
        """Should handle very long task IDs"""
        long_id = "task-" + "x" * 1000
        token = enforcement_engine.generate_phase_token(long_id, "PLAN")

        assert enforcement_engine._verify_phase_token(token, long_id, "PLAN") is True

    def test_special_characters_in_task_id(self, enforcement_engine):
        """Should handle special characters in task ID"""
        special_id = "task-with-dashes_and_underscores.and.dots"
        token = enforcement_engine.generate_phase_token(special_id, "PLAN")

        assert enforcement_engine._verify_phase_token(token, special_id, "PLAN") is True

    def test_unicode_in_task_id(self, enforcement_engine):
        """Should handle unicode in task ID"""
        unicode_id = "task-🚀-with-emoji"
        token = enforcement_engine.generate_phase_token(unicode_id, "PLAN")

        assert enforcement_engine._verify_phase_token(token, unicode_id, "PLAN") is True
