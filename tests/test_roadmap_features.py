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
