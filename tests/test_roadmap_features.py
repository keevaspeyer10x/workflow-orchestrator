"""
Tests for roadmap features CORE-007, WF-004
"""

import pytest
import warnings
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from src.engine import WorkflowEngine


class TestDeprecationWarning:
    """Tests for CORE-007: Deprecate Legacy Claude Integration."""

    def test_deprecation_warning_on_import(self):
        """TC-DEP-001: Importing module shows deprecation warning."""
        # Clear the module from cache to re-trigger warning
        import sys
        if 'src.claude_integration' in sys.modules:
            del sys.modules['src.claude_integration']

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import src.claude_integration

            # Check that a DeprecationWarning was raised
            deprecation_warnings = [
                x for x in w if issubclass(x.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) >= 1
            assert "deprecated" in str(deprecation_warnings[0].message).lower()
            assert "providers.claude_code" in str(deprecation_warnings[0].message)

    def test_functionality_still_works(self):
        """TC-DEP-002: Module still functions after deprecation warning."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.claude_integration import ClaudeCodeIntegration

            # Can instantiate the class
            integration = ClaudeCodeIntegration()
            assert integration is not None
            assert hasattr(integration, 'is_available')


class TestAutoArchive:
    """Tests for WF-004: Auto-Archive Workflow Documents."""

    @pytest.fixture
    def temp_workflow_dir(self):
        """Create a temporary directory with workflow files."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_archive_existing_plan(self, temp_workflow_dir):
        """TC-ARC-001: Archives docs/plan.md when starting workflow."""
        # Setup: Create docs/plan.md
        docs_dir = temp_workflow_dir / "docs"
        docs_dir.mkdir()
        plan_file = docs_dir / "plan.md"
        plan_content = "# Original Plan\nThis is the original plan."
        plan_file.write_text(plan_content)

        # Create engine and archive
        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("test-task")

        # Verify: File moved to archive
        assert len(archived) == 1
        assert not plan_file.exists()
        archive_dir = docs_dir / "archive"
        assert archive_dir.exists()

        # Verify archived file has correct content
        archived_file = Path(archived[0])
        assert archived_file.exists()
        assert archived_file.read_text() == plan_content
        assert "plan" in archived_file.name
        assert "test-task" in archived_file.name

    def test_archive_risk_analysis(self, temp_workflow_dir):
        """TC-ARC-002: Archives docs/risk_analysis.md."""
        docs_dir = temp_workflow_dir / "docs"
        docs_dir.mkdir()
        risk_file = docs_dir / "risk_analysis.md"
        risk_file.write_text("# Risk Analysis")

        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("my-task")

        assert len(archived) == 1
        assert not risk_file.exists()
        assert "risk" in archived[0]

    def test_archive_test_cases(self, temp_workflow_dir):
        """TC-ARC-003: Archives tests/test_cases.md."""
        tests_dir = temp_workflow_dir / "tests"
        tests_dir.mkdir()
        test_cases_file = tests_dir / "test_cases.md"
        test_cases_file.write_text("# Test Cases")

        # Also need docs/archive to exist for archiving
        docs_dir = temp_workflow_dir / "docs"
        docs_dir.mkdir()

        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("my-task")

        assert len(archived) == 1
        assert not test_cases_file.exists()
        assert "test_cases" in archived[0]

    def test_skip_missing_files(self, temp_workflow_dir):
        """TC-ARC-004: No error if files don't exist."""
        # Empty directory - no files to archive
        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("empty-task")

        assert archived == []  # No files archived, no error

    def test_create_archive_directory(self, temp_workflow_dir):
        """TC-ARC-005: Creates docs/archive/ if missing."""
        # Create docs/plan.md but no archive directory
        docs_dir = temp_workflow_dir / "docs"
        docs_dir.mkdir()
        plan_file = docs_dir / "plan.md"
        plan_file.write_text("# Plan")

        engine = WorkflowEngine(str(temp_workflow_dir))
        engine.archive_existing_docs("new-task")

        # Archive directory should be created
        assert (docs_dir / "archive").exists()

    def test_handle_duplicate_names(self, temp_workflow_dir):
        """TC-ARC-006: Adds counter suffix for duplicates."""
        docs_dir = temp_workflow_dir / "docs"
        archive_dir = docs_dir / "archive"
        archive_dir.mkdir(parents=True)

        # Create a file that would have the same name
        date_str = datetime.now().strftime("%Y-%m-%d")
        existing = archive_dir / f"{date_str}_same-task_plan.md"
        existing.write_text("existing")

        # Now create plan.md and archive it
        plan_file = docs_dir / "plan.md"
        plan_file.write_text("new plan")

        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("same-task")

        # Should have _1 suffix
        assert len(archived) == 1
        assert "_1" in archived[0] or "_plan_1" in archived[0]

    def test_archived_content_intact(self, temp_workflow_dir):
        """TC-ARC-009: Archived files have same content."""
        docs_dir = temp_workflow_dir / "docs"
        docs_dir.mkdir()

        original_content = """# My Plan

## Overview
This is a detailed plan with multiple lines.

## Steps
1. Step one
2. Step two
"""
        plan_file = docs_dir / "plan.md"
        plan_file.write_text(original_content)

        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("content-test")

        archived_file = Path(archived[0])
        assert archived_file.read_text() == original_content

    def test_multiple_files_archived(self, temp_workflow_dir):
        """Multiple workflow docs archived together."""
        # Create all three files
        docs_dir = temp_workflow_dir / "docs"
        docs_dir.mkdir()
        tests_dir = temp_workflow_dir / "tests"
        tests_dir.mkdir()

        (docs_dir / "plan.md").write_text("plan")
        (docs_dir / "risk_analysis.md").write_text("risk")
        (tests_dir / "test_cases.md").write_text("tests")

        engine = WorkflowEngine(str(temp_workflow_dir))
        archived = engine.archive_existing_docs("multi-file")

        assert len(archived) == 3
        # All original files should be gone
        assert not (docs_dir / "plan.md").exists()
        assert not (docs_dir / "risk_analysis.md").exists()
        assert not (tests_dir / "test_cases.md").exists()


class TestEnhancedSkipVisibility:
    """Tests for CORE-010: Enhanced Skip Visibility."""

    @pytest.fixture
    def temp_workflow_dir(self):
        """Create a temporary directory for workflow tests."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def engine_with_workflow(self, temp_workflow_dir):
        """Create engine with a basic workflow definition and state."""
        from src.schema import (
            WorkflowDef, PhaseDef, ChecklistItemDef,
            WorkflowState, PhaseState, ItemState, ItemStatus
        )

        # Create workflow definition
        workflow_def = WorkflowDef(
            name="Test Workflow",
            version="1.0",
            description="Test workflow for skip visibility",
            phases=[
                PhaseDef(
                    id="PLAN",
                    name="Planning",
                    description="Planning phase",
                    items=[
                        ChecklistItemDef(
                            id="item_a",
                            name="Item A",
                            description="First item description"
                        ),
                        ChecklistItemDef(
                            id="item_b",
                            name="Item B",
                            description="Second item description"
                        ),
                    ]
                ),
                PhaseDef(
                    id="EXECUTE",
                    name="Execution",
                    description="Execution phase",
                    items=[
                        ChecklistItemDef(
                            id="item_c",
                            name="Item C",
                            description="Third item"
                        ),
                    ]
                ),
            ]
        )

        engine = WorkflowEngine(str(temp_workflow_dir))
        engine.workflow_def = workflow_def

        # Create initial state
        engine.state = WorkflowState(
            workflow_id="test_wf",
            workflow_type="test",
            workflow_version="1.0",
            task_description="Test task",
            current_phase_id="PLAN",
            phases={
                "PLAN": PhaseState(
                    id="PLAN",
                    items={
                        "item_a": ItemState(id="item_a", status=ItemStatus.COMPLETED),
                        "item_b": ItemState(id="item_b", status=ItemStatus.PENDING),
                    }
                ),
                "EXECUTE": PhaseState(
                    id="EXECUTE",
                    items={
                        "item_c": ItemState(id="item_c", status=ItemStatus.PENDING),
                    }
                ),
            }
        )

        return engine

    # Tests for get_skipped_items()

    def test_get_skipped_items_empty_for_no_skips(self, engine_with_workflow):
        """E1: Returns empty list when no items are skipped."""
        result = engine_with_workflow.get_skipped_items("PLAN")
        assert result == []

    def test_get_skipped_items_returns_skipped_with_reason(self, engine_with_workflow):
        """E2: Returns skipped item with its reason."""
        from src.schema import ItemStatus

        # Skip an item
        engine_with_workflow.state.phases["PLAN"].items["item_b"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["PLAN"].items["item_b"].skip_reason = "Not applicable"

        result = engine_with_workflow.get_skipped_items("PLAN")

        assert len(result) == 1
        assert result[0] == ("item_b", "Not applicable")

    def test_get_skipped_items_multiple_skips(self, engine_with_workflow):
        """E3: Returns multiple skipped items."""
        from src.schema import ItemStatus

        # Skip both items
        engine_with_workflow.state.phases["PLAN"].items["item_a"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["PLAN"].items["item_a"].skip_reason = "Reason 1"
        engine_with_workflow.state.phases["PLAN"].items["item_b"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["PLAN"].items["item_b"].skip_reason = "Reason 2"

        result = engine_with_workflow.get_skipped_items("PLAN")

        assert len(result) == 2
        reasons = [r[1] for r in result]
        assert "Reason 1" in reasons
        assert "Reason 2" in reasons

    def test_get_skipped_items_missing_reason(self, engine_with_workflow):
        """E4: Returns default reason when skip_reason is None."""
        from src.schema import ItemStatus

        engine_with_workflow.state.phases["PLAN"].items["item_b"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["PLAN"].items["item_b"].skip_reason = None

        result = engine_with_workflow.get_skipped_items("PLAN")

        assert len(result) == 1
        assert result[0][1] == "No reason provided"

    def test_get_skipped_items_invalid_phase(self, engine_with_workflow):
        """E5: Returns empty list for non-existent phase."""
        result = engine_with_workflow.get_skipped_items("NONEXISTENT")
        assert result == []

    def test_get_skipped_items_no_state(self, temp_workflow_dir):
        """E6: Returns empty list when no active workflow."""
        engine = WorkflowEngine(str(temp_workflow_dir))
        result = engine.get_skipped_items("PLAN")
        assert result == []

    # Tests for get_all_skipped_items()

    def test_get_all_skipped_items_empty(self, engine_with_workflow):
        """E7: Returns empty dict when no items skipped anywhere."""
        result = engine_with_workflow.get_all_skipped_items()
        assert result == {}

    def test_get_all_skipped_items_one_phase(self, engine_with_workflow):
        """E8: Returns skips grouped by single phase."""
        from src.schema import ItemStatus

        engine_with_workflow.state.phases["PLAN"].items["item_b"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["PLAN"].items["item_b"].skip_reason = "Skipped in PLAN"

        result = engine_with_workflow.get_all_skipped_items()

        assert "PLAN" in result
        assert len(result["PLAN"]) == 1
        assert result["PLAN"][0] == ("item_b", "Skipped in PLAN")

    def test_get_all_skipped_items_multiple_phases(self, engine_with_workflow):
        """E9: Returns skips grouped by multiple phases."""
        from src.schema import ItemStatus

        engine_with_workflow.state.phases["PLAN"].items["item_b"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["PLAN"].items["item_b"].skip_reason = "PLAN skip"
        engine_with_workflow.state.phases["EXECUTE"].items["item_c"].status = ItemStatus.SKIPPED
        engine_with_workflow.state.phases["EXECUTE"].items["item_c"].skip_reason = "EXECUTE skip"

        result = engine_with_workflow.get_all_skipped_items()

        assert "PLAN" in result
        assert "EXECUTE" in result
        assert result["PLAN"][0] == ("item_b", "PLAN skip")
        assert result["EXECUTE"][0] == ("item_c", "EXECUTE skip")

    def test_get_all_skipped_items_no_state(self, temp_workflow_dir):
        """E10: Returns empty dict when no active workflow."""
        engine = WorkflowEngine(str(temp_workflow_dir))
        result = engine.get_all_skipped_items()
        assert result == {}

    # Tests for get_item_definition()

    def test_get_item_definition_found(self, engine_with_workflow):
        """E11: Returns item definition when item exists."""
        result = engine_with_workflow.get_item_definition("item_a")

        assert result is not None
        assert result.id == "item_a"
        assert result.name == "Item A"
        assert result.description == "First item description"

    def test_get_item_definition_not_found(self, engine_with_workflow):
        """E12: Returns None for unknown item."""
        result = engine_with_workflow.get_item_definition("nonexistent_item")
        assert result is None

    def test_get_item_definition_no_workflow_def(self, temp_workflow_dir):
        """E13: Returns None when no workflow definition."""
        engine = WorkflowEngine(str(temp_workflow_dir))
        result = engine.get_item_definition("item_a")
        assert result is None


class TestWorkflowCompletionSummary:
    """Tests for CORE-011: Workflow Completion Summary & Next Steps."""

    @pytest.fixture
    def temp_workflow_dir(self):
        """Create a temporary directory for workflow tests."""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def engine_with_mixed_state(self, temp_workflow_dir):
        """Create engine with mixed completed/skipped state."""
        from src.schema import (
            WorkflowDef, PhaseDef, ChecklistItemDef,
            WorkflowState, PhaseState, ItemState, ItemStatus
        )

        workflow_def = WorkflowDef(
            name="Test Workflow",
            version="1.0",
            description="Test",
            phases=[
                PhaseDef(
                    id="PLAN",
                    name="Planning",
                    description="Planning",
                    items=[
                        ChecklistItemDef(id="plan_1", name="Plan 1"),
                        ChecklistItemDef(id="plan_2", name="Plan 2"),
                        ChecklistItemDef(id="plan_3", name="Plan 3"),
                    ]
                ),
                PhaseDef(
                    id="EXECUTE",
                    name="Execution",
                    description="Execution",
                    items=[
                        ChecklistItemDef(id="exec_1", name="Exec 1"),
                        ChecklistItemDef(id="exec_2", name="Exec 2"),
                    ]
                ),
            ]
        )

        engine = WorkflowEngine(str(temp_workflow_dir))
        engine.workflow_def = workflow_def

        engine.state = WorkflowState(
            workflow_id="test_wf",
            workflow_type="test",
            workflow_version="1.0",
            task_description="Test task for summary",
            current_phase_id="EXECUTE",
            phases={
                "PLAN": PhaseState(
                    id="PLAN",
                    items={
                        "plan_1": ItemState(id="plan_1", status=ItemStatus.COMPLETED),
                        "plan_2": ItemState(id="plan_2", status=ItemStatus.COMPLETED),
                        "plan_3": ItemState(id="plan_3", status=ItemStatus.SKIPPED, skip_reason="Not needed"),
                    }
                ),
                "EXECUTE": PhaseState(
                    id="EXECUTE",
                    items={
                        "exec_1": ItemState(id="exec_1", status=ItemStatus.COMPLETED),
                        "exec_2": ItemState(id="exec_2", status=ItemStatus.COMPLETED),
                    }
                ),
            }
        )

        return engine

    # Tests for get_workflow_summary()

    def test_get_workflow_summary_mixed_statuses(self, engine_with_mixed_state):
        """E14: Summary counts completed and skipped correctly."""
        result = engine_with_mixed_state.get_workflow_summary()

        assert "PLAN" in result
        assert result["PLAN"]["completed"] == 2
        assert result["PLAN"]["skipped"] == 1
        assert result["PLAN"]["total"] == 3

        assert "EXECUTE" in result
        assert result["EXECUTE"]["completed"] == 2
        assert result["EXECUTE"]["skipped"] == 0
        assert result["EXECUTE"]["total"] == 2

    def test_get_workflow_summary_all_completed(self, engine_with_mixed_state):
        """E15: Summary shows all completed correctly."""
        from src.schema import ItemStatus

        # Complete the skipped item
        engine_with_mixed_state.state.phases["PLAN"].items["plan_3"].status = ItemStatus.COMPLETED

        result = engine_with_mixed_state.get_workflow_summary()

        assert result["PLAN"]["completed"] == 3
        assert result["PLAN"]["skipped"] == 0
        assert result["PLAN"]["total"] == 3

    def test_get_workflow_summary_no_state(self, temp_workflow_dir):
        """E16: Returns empty dict when no active workflow."""
        engine = WorkflowEngine(str(temp_workflow_dir))
        result = engine.get_workflow_summary()
        assert result == {}


class TestFormatDuration:
    """Tests for format_duration helper function."""

    def test_format_duration_hours_and_minutes(self):
        """H1: Formats hours and minutes correctly."""
        from src.cli import format_duration
        from datetime import timedelta

        result = format_duration(timedelta(hours=2, minutes=15))
        assert result == "2h 15m"

    def test_format_duration_minutes_only(self):
        """H2: Formats minutes only."""
        from src.cli import format_duration
        from datetime import timedelta

        result = format_duration(timedelta(minutes=45))
        assert result == "45m"

    def test_format_duration_less_than_minute(self):
        """H3: Shows '< 1m' for short durations."""
        from src.cli import format_duration
        from datetime import timedelta

        result = format_duration(timedelta(seconds=30))
        assert result == "< 1m"

    def test_format_duration_zero(self):
        """H4: Shows '< 1m' for zero duration."""
        from src.cli import format_duration
        from datetime import timedelta

        result = format_duration(timedelta(0))
        assert result == "< 1m"

    def test_format_duration_days(self):
        """Formats days correctly."""
        from src.cli import format_duration
        from datetime import timedelta

        result = format_duration(timedelta(days=1, hours=3, minutes=30))
        assert result == "1d 3h 30m"
