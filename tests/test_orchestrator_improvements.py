"""
Tests for orchestrator improvements (MultiMinds feedback).

Tests:
1. Project type auto-detection
2. Increased note limit (2000 chars)
3. --test-command and --build-command CLI flags
4. .orchestrator.yaml settings overrides
5. --force flag for gate skipping
6. First-run mismatch warning
"""

import pytest
import tempfile
from pathlib import Path
from argparse import Namespace
from unittest.mock import patch, MagicMock
import sys
import io

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestProjectDetection:
    """Tests for project type auto-detection."""

    def test_detect_python_pyproject(self, tmp_path):
        """TC-DET-001: Detects Python project from pyproject.toml."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        project_type = detect_project_type(tmp_path)
        assert project_type == "python"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "pytest"

    def test_detect_python_setup_py(self, tmp_path):
        """TC-DET-002: Detects Python project from setup.py."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "setup.py").write_text("from setuptools import setup")

        project_type = detect_project_type(tmp_path)
        assert project_type == "python"

    def test_detect_python_requirements(self, tmp_path):
        """TC-DET-003: Detects Python project from requirements.txt."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "requirements.txt").write_text("requests\npytest")

        project_type = detect_project_type(tmp_path)
        assert project_type == "python"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "pytest"
        assert commands["build_command"] is None  # No build for requirements.txt only

    def test_detect_node_package_json(self, tmp_path):
        """TC-DET-004: Detects Node.js project from package.json."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "package.json").write_text('{"name": "test"}')

        project_type = detect_project_type(tmp_path)
        assert project_type == "node"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "npm test"
        assert commands["build_command"] == "npm run build"

    def test_detect_rust_cargo(self, tmp_path):
        """TC-DET-005: Detects Rust project from Cargo.toml."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')

        project_type = detect_project_type(tmp_path)
        assert project_type == "rust"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "cargo test"
        assert commands["build_command"] == "cargo build"

    def test_detect_go_module(self, tmp_path):
        """TC-DET-006: Detects Go project from go.mod."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "go.mod").write_text("module test")

        project_type = detect_project_type(tmp_path)
        assert project_type == "go"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "go test ./..."
        assert commands["build_command"] == "go build ./..."

    def test_detect_makefile(self, tmp_path):
        """TC-DET-007: Detects Makefile project."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "Makefile").write_text("all:\n\techo 'build'")

        project_type = detect_project_type(tmp_path)
        assert project_type == "make"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "make test"
        assert commands["build_command"] == "make"

    def test_detect_cmake(self, tmp_path):
        """TC-DET-008: Detects CMake project."""
        from src.config import detect_project_type, get_project_commands

        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)")

        project_type = detect_project_type(tmp_path)
        assert project_type == "cmake"

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] == "ctest"
        assert commands["build_command"] == "cmake --build ."

    def test_detect_unknown_project(self, tmp_path):
        """TC-DET-009: Returns None for unknown project type."""
        from src.config import detect_project_type, get_project_commands

        # Empty directory
        project_type = detect_project_type(tmp_path)
        assert project_type is None

        commands = get_project_commands(tmp_path)
        assert commands["test_command"] is None
        assert commands["build_command"] is None

    def test_priority_python_over_makefile(self, tmp_path):
        """TC-DET-010: Python detection takes priority over Makefile."""
        from src.config import detect_project_type

        # Both pyproject.toml and Makefile exist
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "Makefile").write_text("all:")

        # pyproject.toml should win (earlier in priority)
        project_type = detect_project_type(tmp_path)
        assert project_type == "python"

    def test_priority_node_first(self, tmp_path):
        """TC-DET-011: Node.js has highest priority."""
        from src.config import detect_project_type

        # Both package.json and pyproject.toml exist
        (tmp_path / "package.json").write_text('{}')
        (tmp_path / "pyproject.toml").write_text("[project]")

        # package.json should win
        project_type = detect_project_type(tmp_path)
        assert project_type == "node"


class TestNoteLimitIncrease:
    """Tests for increased note limit."""

    def test_note_limit_is_2000(self):
        """TC-NOTE-001: MAX_NOTE_LENGTH is now 2000."""
        from src.validation import MAX_NOTE_LENGTH
        assert MAX_NOTE_LENGTH == 2000

    def test_note_1500_chars_accepted(self):
        """TC-NOTE-002: Notes with 1500 characters are accepted."""
        from src.validation import validate_note

        note = "a" * 1500
        result = validate_note(note)
        assert result == note

    def test_note_2000_chars_accepted(self):
        """TC-NOTE-003: Notes exactly at 2000 limit are accepted."""
        from src.validation import validate_note

        note = "a" * 2000
        result = validate_note(note)
        assert len(result) == 2000

    def test_note_2001_chars_rejected(self):
        """TC-NOTE-004: Notes over 2000 chars are rejected."""
        from src.validation import validate_note

        note = "a" * 2001
        with pytest.raises(ValueError) as exc_info:
            validate_note(note)
        assert "2000" in str(exc_info.value)


class TestTestCommandFlag:
    """Tests for --test-command and --build-command CLI flags."""

    def test_start_with_test_command_flag(self, tmp_path):
        """TC-FLAG-001: --test-command overrides default."""
        from src.cli import cmd_start
        from src.engine import WorkflowEngine

        args = Namespace(
            dir=str(tmp_path),
            task="Test task",
            workflow=None,
            project=None,
            constraints=[],
            no_archive=True,
            test_command="pytest -v --cov",
            build_command=None,
        )

        # Should not raise and should set the test command
        with patch('src.cli.print') as mock_print:
            cmd_start(args)

        # Load the engine and check settings - need to load state first
        engine = WorkflowEngine(tmp_path)
        engine.load_state()
        assert engine.workflow_def.settings.get("test_command") == "pytest -v --cov"

    def test_start_with_build_command_flag(self, tmp_path):
        """TC-FLAG-002: --build-command overrides default."""
        from src.cli import cmd_start
        from src.engine import WorkflowEngine

        args = Namespace(
            dir=str(tmp_path),
            task="Test task",
            workflow=None,
            project=None,
            constraints=[],
            no_archive=True,
            test_command=None,
            build_command="pip install -e .[dev]",
        )

        with patch('src.cli.print') as mock_print:
            cmd_start(args)

        engine = WorkflowEngine(tmp_path)
        engine.load_state()
        assert engine.workflow_def.settings.get("build_command") == "pip install -e .[dev]"

    def test_cli_flag_overrides_auto_detection(self, tmp_path):
        """TC-FLAG-003: CLI flag takes priority over auto-detection."""
        from src.cli import cmd_start
        from src.engine import WorkflowEngine

        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[project]")

        args = Namespace(
            dir=str(tmp_path),
            task="Test task",
            workflow=None,
            project=None,
            constraints=[],
            no_archive=True,
            test_command="python -m unittest discover",  # Override pytest
            build_command=None,
        )

        with patch('src.cli.print') as mock_print:
            cmd_start(args)

        engine = WorkflowEngine(tmp_path)
        engine.load_state()
        # CLI flag should win over auto-detected "pytest"
        assert engine.workflow_def.settings.get("test_command") == "python -m unittest discover"


class TestOrchestratorYaml:
    """Tests for .orchestrator.yaml settings overrides."""

    def test_load_orchestrator_yaml(self, tmp_path):
        """TC-ORCH-001: Loads settings from .orchestrator.yaml."""
        from src.config import load_settings_overrides

        override_content = """
test_command: "pytest -v"
build_command: "pip install -e ."
docs_dir: "documentation"
"""
        (tmp_path / ".orchestrator.yaml").write_text(override_content)

        overrides = load_settings_overrides(tmp_path)
        assert overrides["test_command"] == "pytest -v"
        assert overrides["build_command"] == "pip install -e ."
        assert overrides["docs_dir"] == "documentation"

    def test_no_orchestrator_yaml_returns_empty(self, tmp_path):
        """TC-ORCH-002: Returns empty dict when no .orchestrator.yaml."""
        from src.config import load_settings_overrides

        overrides = load_settings_overrides(tmp_path)
        assert overrides == {}

    def test_orchestrator_yaml_merges_with_workflow(self, tmp_path):
        """TC-ORCH-003: Overrides merge into workflow settings."""
        from src.engine import WorkflowEngine
        from src.config import find_workflow_path, load_settings_overrides

        # Create .orchestrator.yaml
        override_content = """
test_command: "pytest --tb=short"
custom_setting: "custom_value"
"""
        (tmp_path / ".orchestrator.yaml").write_text(override_content)

        engine = WorkflowEngine(tmp_path)
        yaml_path = find_workflow_path(tmp_path)
        overrides = load_settings_overrides(tmp_path)

        # Start workflow with overrides
        engine.start_workflow(str(yaml_path), "Test task", settings_overrides=overrides)

        # Check that overrides are applied
        assert engine.workflow_def.settings.get("test_command") == "pytest --tb=short"
        assert engine.workflow_def.settings.get("custom_setting") == "custom_value"

    def test_orchestrator_yaml_priority_over_auto_detect(self, tmp_path):
        """TC-ORCH-004: .orchestrator.yaml takes priority over auto-detection."""
        from src.engine import WorkflowEngine
        from src.config import find_workflow_path, load_settings_overrides, get_project_commands

        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[project]")

        # But override with custom test command
        override_content = """
test_command: "tox"
"""
        (tmp_path / ".orchestrator.yaml").write_text(override_content)

        engine = WorkflowEngine(tmp_path)
        yaml_path = find_workflow_path(tmp_path)

        # Build overrides like cmd_start does (auto-detect first, then file overrides)
        settings_overrides = {}
        detected = get_project_commands(tmp_path)
        if detected.get("test_command"):
            settings_overrides["test_command"] = detected["test_command"]
        # File overrides have higher priority
        file_overrides = load_settings_overrides(tmp_path)
        settings_overrides.update(file_overrides)

        engine.start_workflow(str(yaml_path), "Test task", settings_overrides=settings_overrides)

        # .orchestrator.yaml should win over auto-detected "pytest"
        assert engine.workflow_def.settings.get("test_command") == "tox"


class TestForceSkip:
    """Tests for --force flag on gate skipping."""

    def test_skip_gate_without_force_fails(self, tmp_path):
        """TC-SKIP-001: Skipping gate without --force fails."""
        from src.engine import WorkflowEngine
        from src.config import find_workflow_path

        # Create required files for PLAN phase
        docs_dir = tmp_path / "docs"
        tests_dir = tmp_path / "tests"
        docs_dir.mkdir(exist_ok=True)
        tests_dir.mkdir(exist_ok=True)
        (docs_dir / "plan.md").write_text("# Plan")
        (docs_dir / "risk_analysis.md").write_text("# Risks")
        (tests_dir / "test_cases.md").write_text("# Test Cases")

        engine = WorkflowEngine(tmp_path)
        yaml_path = find_workflow_path(tmp_path)
        engine.start_workflow(str(yaml_path), "Test task")

        # Complete PLAN phase items
        engine.skip_item("check_roadmap", reason="No roadmap exists for this project")
        engine.skip_item("clarifying_questions", reason="Requirements are crystal clear from the task description")
        engine.skip_item("questions_answered", reason="Clarifying questions were skipped so no answers needed")
        engine.complete_item("initial_plan", notes="Plan created")
        engine.skip_item("risk_analysis", reason="Trivial change with no significant risks identified")
        engine.complete_item("define_test_cases", notes="Test cases defined")
        engine.approve_item("user_approval")
        engine.advance_phase()

        # Now in EXECUTE phase - try to skip the user_approval gate in current phase
        # Actually user_approval is in PLAN. Let's try to skip a gate in EXECUTE.
        # The EXECUTE phase doesn't have easily skippable gates in current position.
        # Let's test the logic directly by trying user_approval before advancing.

        # Start fresh for cleaner test
        engine2 = WorkflowEngine(tmp_path)
        yaml_path2 = find_workflow_path(tmp_path)
        # Need new workflow ID
        import os
        os.remove(tmp_path / ".workflow_state.json")
        engine2.start_workflow(str(yaml_path2), "Test task 2")

        # Skip early items
        engine2.skip_item("check_roadmap", reason="No roadmap exists for this project")
        engine2.skip_item("clarifying_questions", reason="Requirements are crystal clear")
        engine2.skip_item("questions_answered", reason="Clarifying questions were skipped")
        engine2.complete_item("initial_plan", notes="Plan created")
        engine2.skip_item("risk_analysis", reason="Trivial change with no risks")
        engine2.complete_item("define_test_cases", notes="Test cases defined")

        # Try to skip the user_approval gate without force (it's a gate type)
        success, message = engine2.skip_item("user_approval", reason="Want to skip approval", force=False)

        # Should fail because it's a gate
        assert not success
        assert "gate" in message.lower()

    def test_skip_gate_with_force_succeeds(self, tmp_path):
        """TC-SKIP-002: Skipping gate with --force succeeds with warning."""
        from src.engine import WorkflowEngine
        from src.config import find_workflow_path

        # Create required files
        docs_dir = tmp_path / "docs"
        tests_dir = tmp_path / "tests"
        docs_dir.mkdir(exist_ok=True)
        tests_dir.mkdir(exist_ok=True)
        (docs_dir / "plan.md").write_text("# Plan")
        (docs_dir / "risk_analysis.md").write_text("# Risks")
        (tests_dir / "test_cases.md").write_text("# Test Cases")

        engine = WorkflowEngine(tmp_path)
        yaml_path = find_workflow_path(tmp_path)
        engine.start_workflow(str(yaml_path), "Test task")

        # Complete prerequisite items
        engine.skip_item("check_roadmap", reason="No roadmap exists for this project")
        engine.skip_item("clarifying_questions", reason="Requirements are crystal clear")
        engine.skip_item("questions_answered", reason="Clarifying questions were skipped")
        engine.complete_item("initial_plan", notes="Plan created")
        engine.skip_item("risk_analysis", reason="Trivial change with no risks")
        engine.complete_item("define_test_cases", notes="Test cases defined")

        # Skip the user_approval gate with force=True
        success, message = engine.skip_item(
            "user_approval",
            reason="Force-skipping approval because this is an automated test and we need to verify the force skip functionality works correctly",
            force=True
        )

        # Should succeed with appropriate message
        assert success
        assert "force" in message.lower() or "skipped" in message.lower()

    def test_force_skip_requires_detailed_reason(self, tmp_path):
        """TC-SKIP-003: Force skip requires detailed reason."""
        from src.engine import WorkflowEngine
        from src.config import find_workflow_path

        # Create required files
        docs_dir = tmp_path / "docs"
        tests_dir = tmp_path / "tests"
        docs_dir.mkdir(exist_ok=True)
        tests_dir.mkdir(exist_ok=True)
        (docs_dir / "plan.md").write_text("# Plan")
        (docs_dir / "risk_analysis.md").write_text("# Risks")
        (tests_dir / "test_cases.md").write_text("# Test Cases")

        engine = WorkflowEngine(tmp_path)
        yaml_path = find_workflow_path(tmp_path)
        engine.start_workflow(str(yaml_path), "Test task")

        # Complete prerequisite items
        engine.skip_item("check_roadmap", reason="No roadmap exists for this project")
        engine.skip_item("clarifying_questions", reason="Requirements are crystal clear")
        engine.skip_item("questions_answered", reason="Clarifying questions were skipped")
        engine.complete_item("initial_plan", notes="Plan created")
        engine.skip_item("risk_analysis", reason="Trivial change with no risks")
        engine.complete_item("define_test_cases", notes="Test cases defined")

        # Try force skip with short reason
        success, message = engine.skip_item("user_approval", reason="short", force=True)

        # Should fail - reason too short for force skip
        assert not success
        assert "50" in message or "reason" in message.lower()

    def test_cli_force_flag_exists(self):
        """TC-SKIP-004: CLI skip command has --force flag."""
        import subprocess
        import sys

        # Test that --force is recognized by running orchestrator skip --help
        result = subprocess.run(
            [sys.executable, "-m", "src.cli", "skip", "--help"],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent)
        )

        # Check that --force is mentioned in the help output
        assert "--force" in result.stdout or "-f" in result.stdout


class TestMismatchWarning:
    """Tests for first-run mismatch warning."""

    def test_warning_shown_for_python_with_npm_default(self, tmp_path, capsys):
        """TC-WARN-001: Warning shown when Python project uses npm default."""
        from src.cli import check_project_mismatch

        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[project]")

        # Check for mismatch with npm default
        warning = check_project_mismatch(tmp_path, "npm run build")

        assert warning is not None
        assert "python" in warning.lower() or "mismatch" in warning.lower()
        assert "pytest" in warning.lower()

    def test_no_warning_when_commands_match(self, tmp_path):
        """TC-WARN-002: No warning when project type matches command."""
        from src.cli import check_project_mismatch

        # Create a Node.js project
        (tmp_path / "package.json").write_text('{}')

        # Check with npm command (matches)
        warning = check_project_mismatch(tmp_path, "npm test")

        assert warning is None

    def test_no_warning_for_unknown_project(self, tmp_path):
        """TC-WARN-003: No warning for unknown project type."""
        from src.cli import check_project_mismatch

        # Empty directory
        warning = check_project_mismatch(tmp_path, "npm run build")

        # No warning if we can't detect project type
        assert warning is None

    def test_warning_includes_recommendation(self, tmp_path):
        """TC-WARN-004: Warning includes recommended command."""
        from src.cli import check_project_mismatch

        # Create a Rust project
        (tmp_path / "Cargo.toml").write_text('[package]')

        warning = check_project_mismatch(tmp_path, "npm test")

        assert warning is not None
        assert "cargo test" in warning.lower()


class TestAutoDetectionIntegration:
    """Integration tests for auto-detection at workflow start."""

    def test_python_project_auto_corrects_test_command(self, tmp_path):
        """TC-INT-001: Python project auto-corrects test command."""
        from src.cli import cmd_start
        from src.engine import WorkflowEngine

        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[project]")

        args = Namespace(
            dir=str(tmp_path),
            task="Test task",
            workflow=None,
            project=None,
            constraints=[],
            no_archive=True,
            test_command=None,  # No override
            build_command=None,
        )

        with patch('src.cli.print') as mock_print:
            cmd_start(args)

        engine = WorkflowEngine(tmp_path)
        engine.load_state()

        # Should auto-detect and use pytest
        assert engine.workflow_def.settings.get("test_command") == "pytest"

    def test_node_project_keeps_npm_default(self, tmp_path):
        """TC-INT-002: Node.js project keeps npm default."""
        from src.cli import cmd_start
        from src.engine import WorkflowEngine

        # Create a Node.js project
        (tmp_path / "package.json").write_text('{"name": "test"}')

        args = Namespace(
            dir=str(tmp_path),
            task="Test task",
            workflow=None,
            project=None,
            constraints=[],
            no_archive=True,
            test_command=None,
            build_command=None,
        )

        with patch('src.cli.print') as mock_print:
            cmd_start(args)

        engine = WorkflowEngine(tmp_path)
        engine.load_state()

        # Should keep npm test
        assert engine.workflow_def.settings.get("test_command") == "npm test"


class TestAPIKeyCheck:
    """Tests for smarter API key checking."""

    def test_no_keys_shows_warning(self):
        """TC-KEY-001: Warning shown when NO keys are set."""
        from src.cli import check_review_api_keys
        import os

        # Clear all keys
        old_keys = {}
        for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'XAI_API_KEY']:
            old_keys[key] = os.environ.pop(key, None)

        try:
            warning = check_review_api_keys()
            assert warning is not None
            assert "No external review API keys" in warning or "not found" in warning
        finally:
            # Restore keys
            for key, val in old_keys.items():
                if val:
                    os.environ[key] = val

    def test_one_key_no_warning(self):
        """TC-KEY-002: No warning when at least one key is set."""
        from src.cli import check_review_api_keys
        import os

        # Clear all keys, then set one
        old_keys = {}
        for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'XAI_API_KEY']:
            old_keys[key] = os.environ.pop(key, None)

        os.environ['OPENROUTER_API_KEY'] = 'test_key_value'

        try:
            warning = check_review_api_keys()
            assert warning is None, f"Expected no warning with one key, got: {warning}"
        finally:
            # Restore keys
            os.environ.pop('OPENROUTER_API_KEY', None)
            for key, val in old_keys.items():
                if val:
                    os.environ[key] = val

    def test_all_keys_no_warning(self):
        """TC-KEY-003: No warning when all keys are set."""
        from src.cli import check_review_api_keys
        import os

        # Save and set all keys
        old_keys = {}
        for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'XAI_API_KEY']:
            old_keys[key] = os.environ.get(key)
            os.environ[key] = 'test_key_value'

        try:
            warning = check_review_api_keys()
            assert warning is None
        finally:
            # Restore keys
            for key, val in old_keys.items():
                if val:
                    os.environ[key] = val
                else:
                    os.environ.pop(key, None)

    def test_empty_string_treated_as_missing(self):
        """TC-KEY-004: Empty string key treated as missing."""
        from src.cli import check_review_api_keys
        import os

        # Clear all keys, set one to empty string
        old_keys = {}
        for key in ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'XAI_API_KEY']:
            old_keys[key] = os.environ.pop(key, None)

        os.environ['OPENROUTER_API_KEY'] = ''  # Empty string

        try:
            warning = check_review_api_keys()
            # Empty string should be treated as missing, so warning should appear
            assert warning is not None
        finally:
            os.environ.pop('OPENROUTER_API_KEY', None)
            for key, val in old_keys.items():
                if val:
                    os.environ[key] = val
