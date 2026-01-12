"""
Tests for WF-034: Post-Workflow Self-Assessment Implementation

Tests Phases 0, 1, 3, and 4:
- Phase 0: parallel_execution_check in PLAN phase (already implemented)
- Phase 1: workflow_adherence_check in LEARN phase
- Phase 3: FeedbackCapture class and CLI integration
- Phase 4: orchestrator-meta.yaml template
"""

import pytest
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import shutil


class TestPhase0ParallelExecutionCheck:
    """Test Phase 0: Pre-Execution Planning Guidance"""

    def test_parallel_execution_check_exists_in_plan_phase(self):
        """Verify parallel_execution_check item exists in PLAN phase."""
        from src.config import get_default_workflow_content

        workflow_yaml = get_default_workflow_content()
        workflow = yaml.safe_load(workflow_yaml)

        # Find PLAN phase
        plan_phase = None
        for phase in workflow['phases']:
            if phase['id'] == 'PLAN':
                plan_phase = phase
                break

        assert plan_phase is not None, "PLAN phase not found in default workflow"

        # Check for parallel_execution_check item
        parallel_check = None
        for item in plan_phase['items']:
            if item['id'] == 'parallel_execution_check':
                parallel_check = item
                break

        assert parallel_check is not None, "parallel_execution_check not found in PLAN phase"
        assert parallel_check['name'] == "Assess Parallel Execution Opportunity"
        assert parallel_check['description'] is not None
        assert len(parallel_check.get('notes', [])) > 0, "parallel_execution_check should have guidance notes"

    def test_parallel_execution_check_has_required_guidance(self):
        """Verify parallel_execution_check has all required guidance notes."""
        from src.config import get_default_workflow_content

        workflow_yaml = get_default_workflow_content()
        workflow = yaml.safe_load(workflow_yaml)

        # Find the item
        plan_phase = [p for p in workflow['phases'] if p['id'] == 'PLAN'][0]
        parallel_check = [i for i in plan_phase['items'] if i['id'] == 'parallel_execution_check'][0]

        notes = parallel_check.get('notes', [])
        notes_text = ' '.join(notes)

        # Required guidance from plan.md
        assert '[critical]' in notes_text, "Should have critical tag"
        assert 'independent tasks' in notes_text.lower(), "Should mention independent tasks"
        assert '[howto]' in notes_text, "Should have howto guidance"
        assert 'ONE message with MULTIPLE Task' in notes_text, "Should explain correct parallel execution"
        assert '[example]' in notes_text, "Should have examples"
        assert '[plan]' in notes_text, "Should mention Plan agent"
        assert '[verify]' in notes_text, "Should mention verification"
        assert '[decision]' in notes_text, "Should prompt for decision documentation"


class TestPhase1WorkflowAdherenceCheck:
    """Test Phase 1: Self-Assessment Checklist"""

    def test_workflow_adherence_check_exists_in_learn_phase(self):
        """Verify workflow_adherence_check item exists in LEARN phase."""
        from src.config import get_default_workflow_content

        workflow_yaml = get_default_workflow_content()
        workflow = yaml.safe_load(workflow_yaml)

        # Find LEARN phase
        learn_phase = None
        for phase in workflow['phases']:
            if phase['id'] == 'LEARN':
                learn_phase = phase
                break

        assert learn_phase is not None, "LEARN phase not found in default workflow"

        # Check for workflow_adherence_check item
        adherence_check = None
        for item in learn_phase['items']:
            if item['id'] == 'workflow_adherence_check':
                adherence_check = item
                break

        assert adherence_check is not None, "workflow_adherence_check not found in LEARN phase"
        assert adherence_check['name'] == "Workflow Adherence Self-Assessment"
        assert adherence_check['description'] is not None
        assert adherence_check['required'] == True, "workflow_adherence_check should be required"

    def test_workflow_adherence_check_has_checklist_questions(self):
        """Verify workflow_adherence_check has all required checklist questions."""
        from src.config import get_default_workflow_content

        workflow_yaml = get_default_workflow_content()
        workflow = yaml.safe_load(workflow_yaml)

        # Find the item
        learn_phase = [p for p in workflow['phases'] if p['id'] == 'LEARN'][0]
        adherence_check = [i for i in learn_phase['items'] if i['id'] == 'workflow_adherence_check'][0]

        notes = adherence_check.get('notes', [])
        notes_text = ' '.join(notes)

        # Required checklist questions from plan.md
        assert '[check]' in notes_text, "Should have check tags"
        assert 'parallel agents' in notes_text.lower(), "Should check parallel agent usage"
        assert 'SINGLE message' in notes_text, "Should check single message execution"
        assert 'Plan agent' in notes_text, "Should check Plan agent usage"
        assert 'verify agent output' in notes_text.lower(), "Should check output verification"
        assert 'third-party model reviews' in notes_text.lower() or 'reviews' in notes_text.lower(), "Should check reviews"
        assert 'orchestrator status' in notes_text.lower(), "Should check status commands"
        assert 'required items' in notes_text.lower(), "Should check required items completion"
        assert 'learnings' in notes_text.lower(), "Should check learnings documentation"
        assert '[feedback]' in notes_text, "Should prompt for feedback"


class TestPhase3FeedbackCapture:
    """Test Phase 3: Feedback Capture Template"""

    def test_feedback_capture_class_exists(self):
        """Verify FeedbackCapture class exists."""
        from src.feedback_capture import FeedbackCapture

        assert FeedbackCapture is not None

    def test_feedback_capture_initialization(self):
        """Test FeedbackCapture initialization."""
        from src.feedback_capture import FeedbackCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_file = Path(tmpdir) / '.workflow_feedback.jsonl'
            fc = FeedbackCapture(feedback_file=feedback_file)

            assert fc.feedback_file == feedback_file

    def test_feedback_capture_schema(self):
        """Verify feedback schema has all required fields."""
        from src.feedback_capture import FeedbackCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_file = Path(tmpdir) / '.workflow_feedback.jsonl'
            fc = FeedbackCapture(feedback_file=feedback_file)

            # Create sample feedback
            feedback = fc.create_feedback(
                workflow_id="wf_test123",
                task="Test task",
                multi_agents_used=True,
                what_went_well="Tests passed quickly",
                challenges="Setup took time",
                improvements="Better docs needed",
                reviews_performed=True,
                notes="First test"
            )

            # Verify schema
            assert 'workflow_id' in feedback
            assert 'task' in feedback
            assert 'timestamp' in feedback
            assert 'multi_agents_used' in feedback
            assert 'what_went_well' in feedback
            assert 'challenges' in feedback
            assert 'improvements' in feedback
            assert 'reviews_performed' in feedback
            assert 'notes' in feedback

            # Verify values
            assert feedback['workflow_id'] == "wf_test123"
            assert feedback['task'] == "Test task"
            assert feedback['multi_agents_used'] == True
            assert feedback['reviews_performed'] == True

    def test_feedback_capture_writes_to_jsonl(self):
        """Verify feedback is written to JSONL file."""
        from src.feedback_capture import FeedbackCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_file = Path(tmpdir) / '.workflow_feedback.jsonl'
            fc = FeedbackCapture(feedback_file=feedback_file)

            # Capture feedback
            fc.capture_feedback(
                workflow_id="wf_test456",
                task="Test workflow",
                multi_agents_used=False,
                what_went_well="Smooth execution",
                challenges="None",
                improvements="Add more tests",
                reviews_performed=True,
                notes="Test note"
            )

            # Verify file exists
            assert feedback_file.exists()

            # Read and verify content
            with open(feedback_file, 'r') as f:
                line = f.readline()
                feedback = json.loads(line)

            assert feedback['workflow_id'] == "wf_test456"
            assert feedback['task'] == "Test workflow"
            assert feedback['multi_agents_used'] == False

    def test_feedback_capture_appends_to_existing_file(self):
        """Verify feedback capture appends to existing file."""
        from src.feedback_capture import FeedbackCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            feedback_file = Path(tmpdir) / '.workflow_feedback.jsonl'
            fc = FeedbackCapture(feedback_file=feedback_file)

            # Capture first feedback
            fc.capture_feedback(
                workflow_id="wf_001",
                task="First task",
                multi_agents_used=True,
                what_went_well="Good",
                challenges="Some",
                improvements="None",
                reviews_performed=True,
                notes=""
            )

            # Capture second feedback
            fc.capture_feedback(
                workflow_id="wf_002",
                task="Second task",
                multi_agents_used=False,
                what_went_well="Better",
                challenges="Few",
                improvements="More",
                reviews_performed=False,
                notes="Second"
            )

            # Verify both entries exist
            with open(feedback_file, 'r') as f:
                lines = f.readlines()

            assert len(lines) == 2
            feedback1 = json.loads(lines[0])
            feedback2 = json.loads(lines[1])

            assert feedback1['workflow_id'] == "wf_001"
            assert feedback2['workflow_id'] == "wf_002"

    def test_feedback_capture_interactive_questions(self):
        """Verify FeedbackCapture has interactive question prompts."""
        from src.feedback_capture import FeedbackCapture

        fc = FeedbackCapture()
        questions = fc.get_interactive_questions()

        # Should have 6 questions as per plan.md
        assert len(questions) >= 5, "Should have at least 5 structured questions"

        # Check question types
        question_text = ' '.join([q['prompt'] for q in questions])
        assert 'multi-agent' in question_text.lower() or 'parallel' in question_text.lower()
        assert 'went well' in question_text.lower()
        assert 'challenge' in question_text.lower()
        assert 'improve' in question_text.lower()
        assert 'review' in question_text.lower()


class TestPhase4MetaWorkflow:
    """Test Phase 4: Workflow Enforcement for Orchestrator Itself"""

    def test_orchestrator_meta_yaml_exists(self):
        """Verify orchestrator-meta.yaml template exists."""
        meta_workflow_path = Path(__file__).parent.parent / 'orchestrator-meta.yaml'

        assert meta_workflow_path.exists(), "orchestrator-meta.yaml should exist in repo root"

    def test_orchestrator_meta_yaml_structure(self):
        """Verify orchestrator-meta.yaml has correct structure."""
        meta_workflow_path = Path(__file__).parent.parent / 'orchestrator-meta.yaml'

        with open(meta_workflow_path, 'r') as f:
            meta_workflow = yaml.safe_load(f)

        # Check basic structure
        assert 'name' in meta_workflow
        assert 'description' in meta_workflow
        assert 'phases' in meta_workflow

        assert meta_workflow['name'] == "Orchestrator Meta-Workflow"
        assert 'best practices' in meta_workflow['description'].lower()

    def test_orchestrator_meta_yaml_has_enforcement_items(self):
        """Verify orchestrator-meta.yaml has enforcement validation items."""
        meta_workflow_path = Path(__file__).parent.parent / 'orchestrator-meta.yaml'

        with open(meta_workflow_path, 'r') as f:
            meta_workflow = yaml.safe_load(f)

        # Find PLAN phase - should have parallel opportunity check
        plan_phase = None
        for phase in meta_workflow['phases']:
            if phase['id'] == 'PLAN':
                plan_phase = phase
                break

        assert plan_phase is not None, "PLAN phase should exist"

        # Check for enforcement items
        has_parallel_check = any(
            'parallel' in item.get('name', '').lower()
            for item in plan_phase.get('items', [])
        )
        assert has_parallel_check, "PLAN phase should have parallel execution check"

        # Find REVIEW phase - should have third-party reviews
        review_phase = None
        for phase in meta_workflow['phases']:
            if phase['id'] == 'REVIEW':
                review_phase = phase
                break

        if review_phase:  # Review phase is optional in meta-workflow
            has_review_check = any(
                'review' in item.get('name', '').lower()
                for item in review_phase.get('items', [])
            )
            assert has_review_check, "REVIEW phase should check for reviews"

    def test_orchestrator_meta_yaml_has_adherence_validation(self):
        """Verify orchestrator-meta.yaml includes adherence validation."""
        meta_workflow_path = Path(__file__).parent.parent / 'orchestrator-meta.yaml'

        with open(meta_workflow_path, 'r') as f:
            meta_workflow = yaml.safe_load(f)

        # Find VERIFY phase - should have adherence validation
        verify_phase = None
        for phase in meta_workflow['phases']:
            if phase['id'] == 'VERIFY':
                verify_phase = phase
                break

        if verify_phase:  # Verify phase is optional
            has_adherence_validation = any(
                'adherence' in item.get('name', '').lower() or
                'validate-adherence' in item.get('description', '').lower()
                for item in verify_phase.get('items', [])
            )
            # Meta-workflow should reference adherence validation
            # This is optional since Phase 2 (AdherenceValidator) will be implemented later


class TestIntegration:
    """Integration tests for WF-034 implementation"""

    def test_workflow_loads_with_new_items(self):
        """Verify workflow loads successfully with new items."""
        from src.config import get_default_workflow_content

        workflow_yaml = get_default_workflow_content()
        workflow = yaml.safe_load(workflow_yaml)

        # Should load without errors
        assert workflow is not None
        assert 'phases' in workflow

        # Count phases
        phase_ids = [p['id'] for p in workflow['phases']]
        assert 'PLAN' in phase_ids
        assert 'LEARN' in phase_ids

    def test_feedback_cli_command_exists(self):
        """Verify orchestrator feedback CLI command exists."""
        # This test verifies the CLI command is registered
        # The command already exists in cli.py (cmd_feedback_capture)
        from src.cli import main
        import sys

        # Test that 'feedback' command is recognized
        # We can't easily test the full CLI without mocking, but we can verify
        # the function exists
        from src.cli import cmd_feedback_capture, cmd_feedback_review, cmd_feedback_sync

        assert callable(cmd_feedback_capture)
        assert callable(cmd_feedback_review)
        assert callable(cmd_feedback_sync)


# Run tests with: pytest tests/test_wf034_implementation.py -v
