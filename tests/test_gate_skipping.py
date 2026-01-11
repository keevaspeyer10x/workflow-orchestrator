"""
Tests for gate skipping logic based on supervision mode.

These tests verify that:
1. In supervised mode, manual gates block (current behavior)
2. In zero_human mode, manual gates are auto-skipped with warnings
3. Gate skips are properly logged for audit trail
4. Hybrid mode logic works correctly (future)
"""

import pytest
import logging
from src.schema import WorkflowDef, ChecklistItemDef, VerificationConfig, VerificationType, SupervisionMode, WorkflowSettings
from src.engine import WorkflowEngine


class TestSupervisedModeGates:
    """Test gate behavior in supervised mode (default)."""

    def test_supervised_mode_blocks_manual_gates(self):
        """In supervised mode, manual gates should NOT be skipped."""
        settings = WorkflowSettings(supervision_mode="supervised")

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        engine = WorkflowEngine(settings=settings)
        should_skip = engine.should_skip_gate(gate_item)

        assert should_skip is False  # Should NOT skip in supervised mode

    def test_default_mode_blocks_gates(self):
        """Default supervision mode should block gates (backward compatible)."""
        settings = WorkflowSettings()  # No supervision_mode specified (defaults to supervised)

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        engine = WorkflowEngine(settings=settings)
        should_skip = engine.should_skip_gate(gate_item)

        assert should_skip is False  # Should block by default


class TestZeroHumanModeGates:
    """Test gate behavior in zero_human mode."""

    def test_zero_human_mode_skips_manual_gates(self):
        """In zero_human mode, manual gates should be auto-skipped."""
        settings = WorkflowSettings(supervision_mode="zero_human")

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        engine = WorkflowEngine(settings=settings)
        should_skip = engine.should_skip_gate(gate_item)

        assert should_skip is True  # Should skip in zero_human mode

    def test_all_manual_gates_skipped_in_zero_human(self):
        """All manual gate types should be skipped in zero_human mode."""
        settings = WorkflowSettings(supervision_mode="zero_human")
        engine = WorkflowEngine(settings=settings)

        gate_items = [
            ChecklistItemDef(id="user_approval", name="User Approval",
                           verification=VerificationConfig(type=VerificationType.MANUAL_GATE)),
            ChecklistItemDef(id="manual_smoke_test", name="Manual Smoke Test",
                           verification=VerificationConfig(type=VerificationType.MANUAL_GATE)),
            ChecklistItemDef(id="final_approval", name="Final Approval",
                           verification=VerificationConfig(type=VerificationType.MANUAL_GATE)),
        ]

        for gate in gate_items:
            should_skip = engine.should_skip_gate(gate)
            assert should_skip is True, f"Gate {gate.id} should be skipped in zero_human mode"

    def test_non_gate_items_not_affected(self):
        """Non-gate items should not be affected by zero_human mode."""
        settings = WorkflowSettings(supervision_mode="zero_human")
        engine = WorkflowEngine(settings=settings)

        non_gate_items = [
            ChecklistItemDef(id="write_code", name="Write Code",
                           verification=VerificationConfig(type=VerificationType.NONE)),
            ChecklistItemDef(id="run_tests", name="Run Tests",
                           verification=VerificationConfig(type=VerificationType.COMMAND, command="pytest")),
            ChecklistItemDef(id="check_file", name="Check File",
                           verification=VerificationConfig(type=VerificationType.FILE_EXISTS, path="README.md")),
        ]

        for item in non_gate_items:
            should_skip = engine.should_skip_gate(item)
            assert should_skip is False, f"Non-gate item {item.id} should not be auto-skipped"


class TestGateSkipLogging:
    """Test that gate skips are properly logged."""

    def test_gate_skip_logged_with_warning(self, caplog):
        """Skipped gates should log warning for audit trail."""
        settings = WorkflowSettings(supervision_mode="zero_human")
        engine = WorkflowEngine(settings=settings)

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        with caplog.at_level(logging.WARNING):
            engine.should_skip_gate(gate_item)

        # Check that warning was logged
        assert any("ZERO-HUMAN MODE" in record.message for record in caplog.records)
        assert any("user_approval" in record.message for record in caplog.records)
        assert any("skipping manual gate" in record.message.lower() for record in caplog.records)

    def test_gate_skip_includes_gate_details(self, caplog):
        """Log message should include gate ID and name."""
        settings = WorkflowSettings(supervision_mode="zero_human")
        engine = WorkflowEngine(settings=settings)

        gate_item = ChecklistItemDef(
            id="manual_smoke_test",
            name="Manual Smoke Test",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        with caplog.at_level(logging.WARNING):
            engine.should_skip_gate(gate_item)

        log_text = " ".join(record.message for record in caplog.records)
        assert "manual_smoke_test" in log_text
        assert "Manual Smoke Test" in log_text

    def test_supervised_mode_does_not_log_skip_warning(self, caplog):
        """Supervised mode should not log skip warnings (gates block, not skipped)."""
        settings = WorkflowSettings(supervision_mode="supervised")
        engine = WorkflowEngine(settings=settings)

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        with caplog.at_level(logging.WARNING):
            should_skip = engine.should_skip_gate(gate_item)

        assert should_skip is False
        # Should not have logged skip warning (because gate was not skipped)
        assert not any("ZERO-HUMAN MODE" in record.message for record in caplog.records)


class TestHybridMode:
    """Test hybrid mode behavior (future enhancement)."""

    def test_hybrid_mode_basic_behavior(self):
        """Hybrid mode should be supported (for future)."""
        settings = WorkflowSettings(supervision_mode="hybrid")

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        engine = WorkflowEngine(settings=settings)

        # For now, hybrid mode should behave like supervised (conservative default)
        # Future: implement risk-based + timeout logic
        should_skip = engine.should_skip_gate(gate_item)
        assert should_skip is False  # Conservative: block until hybrid logic implemented

    @pytest.mark.skip(reason="Hybrid mode not yet implemented - future WF-036")
    def test_hybrid_mode_timeout_logic(self):
        """Hybrid mode should auto-approve after timeout (future)."""
        # Placeholder for future implementation
        pass

    @pytest.mark.skip(reason="Hybrid mode not yet implemented - future WF-036")
    def test_hybrid_mode_risk_assessment(self):
        """Hybrid mode should assess risk before skipping (future)."""
        # Placeholder for future implementation
        pass


class TestGateSkipConditions:
    """Test gate skip conditions and edge cases."""

    @pytest.mark.skip(reason="skip_conditions evaluation not in WF-035 scope")
    def test_gate_with_skip_conditions(self):
        """Gates with skip_conditions should respect those conditions."""
        settings = WorkflowSettings(supervision_mode="supervised")
        engine = WorkflowEngine(settings=settings)

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE),
            skip_conditions=["no_code_changes", "docs_only"]
        )

        # In supervised mode with skip_conditions, gate should still evaluate skip conditions
        # (supervision_mode only controls whether manual gates auto-skip, not skip_conditions logic)
        should_skip = engine.evaluate_skip_conditions(gate_item, context={"docs_only": True})
        assert should_skip is True  # Skip condition met

    def test_zero_human_overrides_skip_conditions(self):
        """In zero_human mode, gates skip regardless of skip_conditions."""
        settings = WorkflowSettings(supervision_mode="zero_human")
        engine = WorkflowEngine(settings=settings)

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE),
            skip_conditions=["no_code_changes"]  # Has skip conditions
        )

        # Even without skip conditions being met, zero_human mode should skip
        should_skip = engine.should_skip_gate(gate_item)
        assert should_skip is True  # Skipped due to zero_human mode


class TestWorkflowEngineIntegration:
    """Test gate skipping integrated into WorkflowEngine."""

    def test_engine_respects_supervision_mode(self):
        """WorkflowEngine should respect settings.supervision_mode."""
        settings_supervised = WorkflowSettings(supervision_mode="supervised")
        settings_zero_human = WorkflowSettings(supervision_mode="zero_human")

        gate_item = ChecklistItemDef(
            id="user_approval",
            name="User Approval",
            verification=VerificationConfig(type=VerificationType.MANUAL_GATE)
        )

        engine_supervised = WorkflowEngine(settings=settings_supervised)
        engine_zero_human = WorkflowEngine(settings=settings_zero_human)

        # Same gate, different behavior based on supervision mode
        assert engine_supervised.should_skip_gate(gate_item) is False
        assert engine_zero_human.should_skip_gate(gate_item) is True

    def test_engine_loads_supervision_mode_from_workflow(self):
        """Engine should load supervision_mode from workflow settings."""
        workflow = WorkflowDef(
            name="Test",
            phases=[],
            settings={
                "supervision_mode": "zero_human",
                "smoke_test_command": "echo test"
            }
        )

        engine = WorkflowEngine.from_workflow(workflow)

        # Verify supervision mode was loaded
        assert engine.settings.supervision_mode == SupervisionMode.ZERO_HUMAN

    def test_complete_item_auto_skips_in_zero_human(self):
        """complete_item should succeed and mark item SKIPPED in zero_human mode."""
        import tempfile
        import yaml
        from pathlib import Path
        from src.schema import ItemStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            
            workflow_dict = {
                "name": "Zero Human Test",
                "version": "1.0",
                "settings": {"supervision_mode": "zero_human"},
                "phases": [{
                    "id": "TEST",
                    "name": "Test Phase",
                    "items": [{
                        "id": "manual_gate_item",
                        "name": "Manual Gate",
                        "verification": {"type": "manual_gate"}
                    }]
                }]
            }
            
            yaml_path = temp_dir / "workflow.yaml"
            with open(yaml_path, 'w') as f:
                yaml.dump(workflow_dict, f)
            
            engine = WorkflowEngine(working_dir=str(temp_dir))
            engine.start_workflow(str(yaml_path), "Test task")
            engine.start_item("manual_gate_item")
            
            success, message = engine.complete_item("manual_gate_item")
            
            assert success
            assert "auto-skipped" in message
            
            item_state = engine.state.phases["TEST"].items["manual_gate_item"]
            assert item_state.status == ItemStatus.SKIPPED
            assert item_state.skip_reason == "Auto-skipped (zero_human mode)"
