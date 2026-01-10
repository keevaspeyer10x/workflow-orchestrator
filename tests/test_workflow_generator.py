"""
Tests for workflow YAML generation.

Tests repo analysis, workflow template generation, and file saving.
"""

import json
import pytest
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, mock_open

from src.orchestrator.workflow_generator import (
    RepoAnalysis,
    analyze_repo,
    generate_workflow_yaml,
    save_workflow_yaml,
    WorkflowGeneratorError,
)


class TestRepoAnalysis:
    """Tests for analyze_repo function."""

    def test_analyze_repo_python_pytest(self, tmp_path):
        """Test analysis of Python project with pytest."""
        # Create Python project structure
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\nrequests==2.28.0")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").touch()
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_example.py").touch()

        result = analyze_repo(tmp_path)

        assert result.language == "python"
        assert result.test_framework == "pytest"
        assert result.test_command == "pytest"
        assert result.has_tests is True

    def test_analyze_repo_javascript_jest(self, tmp_path):
        """Test analysis of JavaScript project with jest."""
        package_json = {
            "name": "test-project",
            "devDependencies": {"jest": "^29.0.0"},
            "scripts": {"test": "jest"}
        }
        (tmp_path / "package.json").write_text(yaml.dump(package_json))
        (tmp_path / "__tests__").mkdir()
        (tmp_path / "__tests__" / "example.test.js").touch()

        result = analyze_repo(tmp_path)

        assert result.language == "javascript"
        assert result.test_framework == "jest"
        assert result.test_command == "npm test"
        assert result.has_tests is True

    def test_analyze_repo_go_project(self, tmp_path):
        """Test analysis of Go project."""
        (tmp_path / "go.mod").write_text("module example.com/myproject\n\ngo 1.21")
        (tmp_path / "main.go").touch()
        (tmp_path / "main_test.go").touch()

        result = analyze_repo(tmp_path)

        assert result.language == "go"
        assert result.test_framework == "go test"
        assert result.test_command == "go test ./..."
        assert result.has_tests is True

    def test_analyze_repo_rust_cargo(self, tmp_path):
        """Test analysis of Rust project."""
        (tmp_path / "Cargo.toml").write_text("[package]\nname = \"test\"\nversion = \"0.1.0\"")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").touch()
        (tmp_path / "tests").mkdir()

        result = analyze_repo(tmp_path)

        assert result.language == "rust"
        assert result.test_framework == "cargo test"
        assert result.test_command == "cargo test"
        assert result.has_tests is True

    def test_analyze_repo_unknown_type(self, tmp_path):
        """Test analysis when project type cannot be determined."""
        # Create empty directory with no recognizable structure
        (tmp_path / "README.md").touch()

        result = analyze_repo(tmp_path)

        assert result.language == "unknown"
        assert result.test_framework == "unknown"
        assert result.test_command == ""
        assert result.has_tests is False

    def test_analyze_repo_python_no_tests(self, tmp_path):
        """Test Python project without tests directory."""
        (tmp_path / "requirements.txt").write_text("requests==2.28.0")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").touch()

        result = analyze_repo(tmp_path)

        assert result.language == "python"
        assert result.test_framework == "pytest"  # Assume pytest
        assert result.has_tests is False

    def test_analyze_repo_javascript_mocha(self, tmp_path):
        """Test JavaScript project with Mocha."""
        package_json = {
            "name": "test-project",
            "devDependencies": {"mocha": "^10.0.0"},
            "scripts": {"test": "mocha"}
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json))
        (tmp_path / "test").mkdir()

        result = analyze_repo(tmp_path)

        assert result.language == "javascript"
        assert result.test_framework == "mocha"
        assert result.test_command == "npm test"


class TestGenerateWorkflowYAML:
    """Tests for generate_workflow_yaml function."""

    def test_generate_workflow_yaml_python(self):
        """Test workflow generation for Python project."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={"src": True, "tests": True}
        )

        result = generate_workflow_yaml(
            task_description="Add user authentication",
            analysis=analysis
        )

        # Parse YAML to verify structure
        workflow = yaml.safe_load(result)

        assert workflow["name"] == "Auto-Generated Agent Workflow"
        assert workflow["task"] == "Add user authentication"
        assert workflow["language"] == "python"
        assert workflow["test_framework"] == "pytest"
        assert len(workflow["phases"]) == 5
        assert workflow["phases"][0]["id"] == "PLAN"
        assert workflow["phases"][1]["id"] == "TDD"
        assert workflow["phases"][2]["id"] == "IMPL"

    def test_generate_workflow_yaml_javascript(self):
        """Test workflow generation for JavaScript project."""
        analysis = RepoAnalysis(
            language="javascript",
            test_framework="jest",
            test_command="npm test",
            has_tests=True,
            project_structure={"src": True, "__tests__": True}
        )

        result = generate_workflow_yaml(
            task_description="Add REST API",
            analysis=analysis
        )

        workflow = yaml.safe_load(result)

        assert workflow["language"] == "javascript"
        assert workflow["test_framework"] == "jest"
        assert workflow["task"] == "Add REST API"

    def test_generate_workflow_yaml_includes_phases(self):
        """Test that generated workflow includes all 5 phases."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        phase_ids = [phase["id"] for phase in workflow["phases"]]
        assert phase_ids == ["PLAN", "TDD", "IMPL", "REVIEW", "VERIFY"]

    def test_generate_workflow_yaml_includes_tools(self):
        """Test that workflow includes appropriate allowed/forbidden tools."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        # Check PLAN phase
        plan_phase = workflow["phases"][0]
        assert "read_files" in plan_phase["allowed_tools"]
        assert "search_codebase" in plan_phase["allowed_tools"]
        assert "write_files" in plan_phase["forbidden_tools"]

    def test_generate_workflow_yaml_includes_gates(self):
        """Test that workflow includes gates with validation."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        # Check TDD phase has gates
        tdd_phase = workflow["phases"][1]
        assert "gates" in tdd_phase
        assert len(tdd_phase["gates"]) > 0

    def test_generate_workflow_yaml_embeds_task(self):
        """Test that task description is embedded in workflow."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        task_desc = "Very specific task with details"
        result = generate_workflow_yaml(task_desc, analysis)
        workflow = yaml.safe_load(result)

        assert workflow["task"] == task_desc

    def test_generate_workflow_yaml_unknown_language(self):
        """Test workflow generation for unknown language (fallback)."""
        analysis = RepoAnalysis(
            language="unknown",
            test_framework="unknown",
            test_command="",
            has_tests=False,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        assert workflow["language"] == "unknown"
        assert workflow["test_framework"] == "unknown"
        # Should still have 5 phases
        assert len(workflow["phases"]) == 5


class TestSaveWorkflowYAML:
    """Tests for save_workflow_yaml function."""

    def test_save_workflow_yaml_creates_directory(self, tmp_path):
        """Test that .orchestrator directory is created."""
        workflow_content = "name: Test\nversion: 1.0"

        result = save_workflow_yaml(workflow_content, tmp_path)

        assert (tmp_path / ".orchestrator").exists()
        assert (tmp_path / ".orchestrator").is_dir()
        assert result == tmp_path / ".orchestrator" / "agent_workflow.yaml"

    def test_save_workflow_yaml_writes_content(self, tmp_path):
        """Test that workflow content is written correctly."""
        workflow_content = "name: Test Workflow\nphases:\n  - id: PLAN"

        result = save_workflow_yaml(workflow_content, tmp_path)

        saved_content = result.read_text()
        assert saved_content == workflow_content

    def test_save_workflow_yaml_creates_gitignore(self, tmp_path):
        """Test that .gitignore is created in .orchestrator."""
        workflow_content = "name: Test"

        save_workflow_yaml(workflow_content, tmp_path)

        gitignore_path = tmp_path / ".orchestrator" / ".gitignore"
        assert gitignore_path.exists()

        gitignore_content = gitignore_path.read_text()
        assert "*.pid" in gitignore_content
        assert "*.log" in gitignore_content
        assert "server.log" in gitignore_content

    def test_save_workflow_yaml_existing_directory(self, tmp_path):
        """Test saving when .orchestrator already exists."""
        # Create directory first
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir()
        (orchestrator_dir / "existing_file.txt").write_text("keep me")

        workflow_content = "name: Test"
        save_workflow_yaml(workflow_content, tmp_path)

        # Existing file should still be there
        assert (orchestrator_dir / "existing_file.txt").exists()
        # New workflow file should be created
        assert (orchestrator_dir / "agent_workflow.yaml").exists()

    def test_save_workflow_yaml_overwrites_existing_workflow(self, tmp_path):
        """Test that existing workflow.yaml is overwritten."""
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir()
        workflow_path = orchestrator_dir / "agent_workflow.yaml"
        workflow_path.write_text("old content")

        new_content = "new workflow content"
        save_workflow_yaml(new_content, tmp_path)

        assert workflow_path.read_text() == new_content

    def test_save_workflow_yaml_returns_path(self, tmp_path):
        """Test that correct path is returned."""
        workflow_content = "name: Test"

        result = save_workflow_yaml(workflow_content, tmp_path)

        assert isinstance(result, Path)
        assert result.name == "agent_workflow.yaml"
        assert result.parent.name == ".orchestrator"


class TestWorkflowTemplate:
    """Tests for workflow template structure and content."""

    def test_template_has_required_metadata(self):
        """Test that generated workflow has required metadata fields."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        assert "name" in workflow
        assert "version" in workflow
        assert "description" in workflow
        assert "task" in workflow
        assert "language" in workflow
        assert "test_framework" in workflow

    def test_template_plan_phase_structure(self):
        """Test PLAN phase has correct structure."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        plan_phase = workflow["phases"][0]
        assert plan_phase["id"] == "PLAN"
        assert "name" in plan_phase
        assert "description" in plan_phase
        assert "required_artifacts" in plan_phase
        assert "allowed_tools" in plan_phase
        assert "forbidden_tools" in plan_phase
        assert "gates" in plan_phase

    def test_template_tdd_phase_references_test_framework(self):
        """Test that TDD phase references correct test framework."""
        analysis = RepoAnalysis(
            language="javascript",
            test_framework="jest",
            test_command="npm test",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        # Check that test_command is in the workflow metadata
        assert workflow["test_command"] == "npm test"
        assert workflow["test_framework"] == "jest"

    def test_template_review_phase_includes_review_types(self):
        """Test that REVIEW phase includes appropriate review gates."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("Task", analysis)
        workflow = yaml.safe_load(result)

        review_phase = workflow["phases"][3]
        assert review_phase["id"] == "REVIEW"
        assert "gates" in review_phase or "required_artifacts" in review_phase


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_analyze_repo_nonexistent_path(self):
        """Test analysis of non-existent directory."""
        with pytest.raises(WorkflowGeneratorError, match="not found"):
            analyze_repo(Path("/nonexistent/path"))

    def test_analyze_repo_file_not_directory(self, tmp_path):
        """Test analysis when path is a file not directory."""
        file_path = tmp_path / "file.txt"
        file_path.touch()

        with pytest.raises(WorkflowGeneratorError, match="not a directory"):
            analyze_repo(file_path)

    def test_generate_workflow_yaml_empty_task(self):
        """Test workflow generation with empty task description."""
        analysis = RepoAnalysis(
            language="python",
            test_framework="pytest",
            test_command="pytest",
            has_tests=True,
            project_structure={}
        )

        result = generate_workflow_yaml("", analysis)
        workflow = yaml.safe_load(result)

        assert workflow["task"] == ""
        # Workflow should still be valid
        assert len(workflow["phases"]) == 5

    def test_save_workflow_yaml_permission_error(self, tmp_path):
        """Test save when directory is read-only."""
        # Create orchestrator directory first
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir()

        # Create workflow file and make it read-only
        workflow_file = orchestrator_dir / "agent_workflow.yaml"
        workflow_file.write_text("old content")
        workflow_file.chmod(0o444)  # Read-only file

        try:
            with pytest.raises(WorkflowGeneratorError, match="Permission denied"):
                save_workflow_yaml("new content", tmp_path)
        finally:
            # Cleanup: restore permissions
            workflow_file.chmod(0o644)
