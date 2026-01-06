"""
Tests for v2.2 Enhancement Features.

This module tests:
- Feature 2: Environment Detection
- Feature 3: Operating Notes
- Feature 4: Task Constraints
- Feature 5: Checkpoint/Resume
"""

import os
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.environment import (
    detect_environment,
    get_environment_info,
    get_recommended_provider,
    Environment,
)
from src.checkpoint import CheckpointManager, CheckpointData
from src.schema import WorkflowState, PhaseDef, ChecklistItemDef, WorkflowDef


class TestEnvironmentDetection:
    """Tests for Feature 2: Environment Detection."""
    
    def test_environment_enum_values(self):
        """Test Environment enum has expected values."""
        assert Environment.CLAUDE_CODE.value == "claude_code"
        assert Environment.MANUS.value == "manus"
        assert Environment.STANDALONE.value == "standalone"
    
    @patch.dict(os.environ, {'CLAUDE_CODE': '1'})
    def test_detect_claude_code_env_var(self):
        """Test detection via CLAUDE_CODE env var."""
        env = detect_environment()
        assert env == Environment.CLAUDE_CODE
    
    @patch.dict(os.environ, {'MANUS_SESSION': 'test-session'}, clear=True)
    def test_detect_manus_env_var(self):
        """Test detection via MANUS_SESSION env var."""
        # Need to also mock the home directory check
        with patch('pathlib.Path.home', return_value=Path('/home/ubuntu')):
            with patch('pathlib.Path.exists', return_value=False):
                env = detect_environment()
                assert env == Environment.MANUS
    
    def test_get_environment_info_returns_dict(self):
        """Test get_environment_info returns expected structure."""
        info = get_environment_info()
        assert isinstance(info, dict)
        assert 'environment' in info
        assert 'home' in info
        assert 'user' in info
        assert 'indicators' in info
    
    def test_get_recommended_provider_claude_code(self):
        """Test recommended provider for Claude Code environment."""
        provider = get_recommended_provider(Environment.CLAUDE_CODE)
        assert provider == "claude_code"
    
    def test_get_recommended_provider_manus(self):
        """Test recommended provider for Manus environment."""
        provider = get_recommended_provider(Environment.MANUS)
        assert provider == "openrouter"
    
    def test_get_recommended_provider_standalone(self):
        """Test recommended provider for Standalone environment."""
        provider = get_recommended_provider(Environment.STANDALONE)
        assert provider == "manual"


class TestOperatingNotes:
    """Tests for Feature 3: Operating Notes."""
    
    def test_phase_def_has_notes_field(self):
        """Test PhaseDef schema includes notes field."""
        phase = PhaseDef(id="TEST", name="Test Phase")
        assert hasattr(phase, 'notes')
        assert phase.notes == []
    
    def test_phase_def_with_notes(self):
        """Test PhaseDef can be created with notes."""
        phase = PhaseDef(
            id="TEST",
            name="Test Phase",
            notes=["[tip] This is a tip", "[caution] Be careful here"]
        )
        assert len(phase.notes) == 2
        assert "[tip]" in phase.notes[0]
    
    def test_checklist_item_def_has_notes_field(self):
        """Test ChecklistItemDef schema includes notes field."""
        item = ChecklistItemDef(id="test_item", name="Test Item")
        assert hasattr(item, 'notes')
        assert item.notes == []
    
    def test_checklist_item_def_with_notes(self):
        """Test ChecklistItemDef can be created with notes."""
        item = ChecklistItemDef(
            id="test_item",
            name="Test Item",
            notes=["[learning] Previous implementation used X approach"]
        )
        assert len(item.notes) == 1


class TestTaskConstraints:
    """Tests for Feature 4: Task Constraints."""
    
    def test_workflow_state_has_constraints_field(self):
        """Test WorkflowState schema includes constraints field."""
        state = WorkflowState(
            workflow_id="test",
            workflow_type="test",
            workflow_version="1.0",
            task_description="Test task",
            current_phase_id="TEST"
        )
        assert hasattr(state, 'constraints')
        assert state.constraints == []
    
    def test_workflow_state_with_constraints(self):
        """Test WorkflowState can be created with constraints."""
        state = WorkflowState(
            workflow_id="test",
            workflow_type="test",
            workflow_version="1.0",
            task_description="Test task",
            current_phase_id="TEST",
            constraints=["No external API calls", "Must use Python 3.11+"]
        )
        assert len(state.constraints) == 2
        assert "No external API calls" in state.constraints


class TestCheckpointSystem:
    """Tests for Feature 5: Checkpoint/Resume."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_checkpoint_data_dataclass(self):
        """Test CheckpointData dataclass."""
        checkpoint = CheckpointData(
            checkpoint_id="cp_test",
            workflow_id="wf_test",
            phase_id="TEST",
            item_id="item1",
            timestamp="2026-01-06T00:00:00+00:00",
            message="Test checkpoint"
        )
        assert checkpoint.checkpoint_id == "cp_test"
        assert checkpoint.workflow_id == "wf_test"
        assert checkpoint.message == "Test checkpoint"
    
    def test_checkpoint_data_to_dict(self):
        """Test CheckpointData serialization."""
        checkpoint = CheckpointData(
            checkpoint_id="cp_test",
            workflow_id="wf_test",
            phase_id="TEST",
            item_id=None,
            timestamp="2026-01-06T00:00:00+00:00"
        )
        data = checkpoint.to_dict()
        assert isinstance(data, dict)
        assert data['checkpoint_id'] == "cp_test"
    
    def test_checkpoint_data_from_dict(self):
        """Test CheckpointData deserialization."""
        data = {
            "checkpoint_id": "cp_test",
            "workflow_id": "wf_test",
            "phase_id": "TEST",
            "item_id": None,
            "timestamp": "2026-01-06T00:00:00+00:00",
            "message": None,
            "context_summary": None,
            "key_decisions": [],
            "file_manifest": [],
            "workflow_state_snapshot": None
        }
        checkpoint = CheckpointData.from_dict(data)
        assert checkpoint.checkpoint_id == "cp_test"
    
    def test_checkpoint_manager_init(self, temp_dir):
        """Test CheckpointManager initialization."""
        mgr = CheckpointManager(temp_dir)
        assert mgr.checkpoints_dir.exists()
    
    def test_create_checkpoint(self, temp_dir):
        """Test checkpoint creation."""
        mgr = CheckpointManager(temp_dir)
        
        checkpoint = mgr.create_checkpoint(
            workflow_id="wf_test",
            phase_id="TEST",
            message="Test checkpoint",
            auto_detect_files=False
        )
        
        assert checkpoint.checkpoint_id.startswith("cp_")
        assert checkpoint.workflow_id == "wf_test"
        assert checkpoint.phase_id == "TEST"
        assert checkpoint.message == "Test checkpoint"
    
    def test_list_checkpoints(self, temp_dir):
        """Test listing checkpoints."""
        import time
        mgr = CheckpointManager(temp_dir)
        
        # Create multiple checkpoints with delay to ensure different timestamps/IDs
        mgr.create_checkpoint(workflow_id="wf_test", phase_id="PLAN", auto_detect_files=False)
        time.sleep(1.1)  # Ensure different second in timestamp for unique ID
        mgr.create_checkpoint(workflow_id="wf_test", phase_id="EXECUTE", auto_detect_files=False)
        
        checkpoints = mgr.list_checkpoints()
        assert len(checkpoints) == 2
    
    def test_list_checkpoints_filtered_by_workflow(self, temp_dir):
        """Test listing checkpoints filtered by workflow ID."""
        mgr = CheckpointManager(temp_dir)
        
        mgr.create_checkpoint(workflow_id="wf_test1", phase_id="PLAN", auto_detect_files=False)
        mgr.create_checkpoint(workflow_id="wf_test2", phase_id="PLAN", auto_detect_files=False)
        
        checkpoints = mgr.list_checkpoints(workflow_id="wf_test1")
        assert len(checkpoints) == 1
        assert checkpoints[0].workflow_id == "wf_test1"
    
    def test_get_checkpoint(self, temp_dir):
        """Test getting a specific checkpoint."""
        mgr = CheckpointManager(temp_dir)
        
        created = mgr.create_checkpoint(
            workflow_id="wf_test",
            phase_id="TEST",
            auto_detect_files=False
        )
        
        retrieved = mgr.get_checkpoint(created.checkpoint_id)
        assert retrieved is not None
        assert retrieved.checkpoint_id == created.checkpoint_id
    
    def test_get_latest_checkpoint(self, temp_dir):
        """Test getting the latest checkpoint."""
        mgr = CheckpointManager(temp_dir)
        
        mgr.create_checkpoint(workflow_id="wf_test", phase_id="PLAN", auto_detect_files=False)
        import time
        time.sleep(0.1)  # Ensure different timestamps
        latest = mgr.create_checkpoint(workflow_id="wf_test", phase_id="EXECUTE", auto_detect_files=False)
        
        retrieved = mgr.get_latest_checkpoint()
        assert retrieved.checkpoint_id == latest.checkpoint_id
    
    def test_generate_resume_prompt(self, temp_dir):
        """Test resume prompt generation."""
        mgr = CheckpointManager(temp_dir)
        
        checkpoint = mgr.create_checkpoint(
            workflow_id="wf_test",
            phase_id="TEST",
            message="Test checkpoint",
            key_decisions=["Decision 1", "Decision 2"],
            file_manifest=["file1.py", "file2.py"],
            auto_detect_files=False
        )
        
        prompt = mgr.generate_resume_prompt(checkpoint)
        
        assert "WORKFLOW RESUME FROM CHECKPOINT" in prompt
        assert "wf_test" in prompt
        assert "TEST" in prompt
        assert "Test checkpoint" in prompt
        assert "Decision 1" in prompt
        assert "file1.py" in prompt
    
    def test_checkpoint_with_key_decisions(self, temp_dir):
        """Test checkpoint with key decisions."""
        mgr = CheckpointManager(temp_dir)
        
        checkpoint = mgr.create_checkpoint(
            workflow_id="wf_test",
            phase_id="TEST",
            key_decisions=["Used approach A", "Skipped feature B"],
            auto_detect_files=False
        )
        
        assert len(checkpoint.key_decisions) == 2
        assert "Used approach A" in checkpoint.key_decisions
    
    def test_checkpoint_with_file_manifest(self, temp_dir):
        """Test checkpoint with file manifest."""
        mgr = CheckpointManager(temp_dir)
        
        checkpoint = mgr.create_checkpoint(
            workflow_id="wf_test",
            phase_id="TEST",
            file_manifest=["src/main.py", "tests/test_main.py"],
            auto_detect_files=False
        )
        
        assert len(checkpoint.file_manifest) == 2
        assert "src/main.py" in checkpoint.file_manifest


class TestIntegration:
    """Integration tests for v2.2 features."""
    
    def test_workflow_with_all_features(self):
        """Test workflow state with all v2.2 features."""
        # Create a workflow state with constraints
        state = WorkflowState(
            workflow_id="wf_integration",
            workflow_type="test",
            workflow_version="1.0",
            task_description="Integration test",
            current_phase_id="PLAN",
            constraints=["Constraint 1", "Constraint 2"]
        )
        
        # Verify constraints are stored
        assert len(state.constraints) == 2
        
        # Verify serialization works
        state_dict = state.model_dump(mode='json')
        assert 'constraints' in state_dict
        assert len(state_dict['constraints']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
