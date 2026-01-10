"""
Tests for agent context and instruction generation.

Tests instruction markdown generation, prompt formatting, and file saving.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.orchestrator.agent_context import (
    generate_agent_instructions,
    save_agent_instructions,
    format_agent_prompt,
    AgentContextError,
)


class TestGenerateAgentInstructions:
    """Tests for generate_agent_instructions function."""

    def test_generate_agent_instructions_basic(self):
        """Test basic instruction generation."""
        result = generate_agent_instructions(
            task="Add user authentication",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        assert "Add user authentication" in result
        assert "http://localhost:8000" in result
        assert "agent_workflow.yaml" in result
        assert "sequential" in result.lower()

    def test_generate_agent_instructions_includes_sdk_import(self):
        """Test that instructions include SDK import example."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        assert "from src.agent_sdk.client import AgentClient" in result
        assert "AgentClient" in result
        assert "claim_task" in result

    def test_generate_agent_instructions_includes_phases(self):
        """Test that instructions mention workflow phases."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        assert "PLAN" in result
        assert "TDD" in result
        assert "IMPL" in result
        assert "REVIEW" in result
        assert "VERIFY" in result

    def test_generate_agent_instructions_sequential_mode(self):
        """Test instructions for sequential mode."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        assert "sequential" in result.lower()
        assert "single agent" in result.lower()

    def test_generate_agent_instructions_parallel_mode(self):
        """Test instructions for parallel mode."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="parallel"
        )

        assert "parallel" in result.lower()
        assert "multiple agents" in result.lower() or "coordination" in result.lower()

    def test_generate_agent_instructions_includes_allowed_tools(self):
        """Test that PLAN phase tools are mentioned."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # PLAN phase allowed tools
        assert "read_files" in result or "search_codebase" in result

    def test_generate_agent_instructions_includes_forbidden_tools(self):
        """Test that PLAN phase forbidden tools are mentioned."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # PLAN phase forbidden tools
        assert "forbidden" in result.lower() or "not allowed" in result.lower()

    def test_generate_agent_instructions_markdown_format(self):
        """Test that output is valid markdown."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Check for markdown headers
        assert result.startswith("#")
        # Check for code blocks
        assert "```python" in result
        assert "```" in result

    def test_generate_agent_instructions_includes_docs_link(self):
        """Test that instructions link to full documentation."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        assert "AGENT_SDK_GUIDE" in result or "documentation" in result.lower()


class TestFormatAgentPrompt:
    """Tests for format_agent_prompt function."""

    def test_format_agent_prompt_structure(self):
        """Test that prompt has clear structure."""
        instructions = "# Test Instructions\n\nSome content"

        result = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="sequential"
        )

        # Should have header
        assert "===" in result
        assert "AGENT WORKFLOW READY" in result
        # Should include server URL
        assert "http://localhost:8000" in result

    def test_format_agent_prompt_includes_instructions(self):
        """Test that formatted prompt includes full instructions."""
        instructions = "# Custom Instructions\n\nStep 1: Do this\nStep 2: Do that"

        result = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="sequential"
        )

        assert "Custom Instructions" in result
        assert "Step 1: Do this" in result
        assert "Step 2: Do that" in result

    def test_format_agent_prompt_highlights_server(self):
        """Test that server URL is highlighted."""
        instructions = "Test"

        result = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="sequential"
        )

        # Check that server URL appears in a prominent section
        lines = result.split('\n')
        server_line_idx = next(i for i, line in enumerate(lines) if "8000" in line)
        # Should be near the top (within first 20 lines)
        assert server_line_idx < 20

    def test_format_agent_prompt_includes_mode(self):
        """Test that execution mode is mentioned."""
        instructions = "Test"

        result_seq = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="sequential"
        )
        assert "sequential" in result_seq.lower()

        result_par = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="parallel"
        )
        assert "parallel" in result_par.lower()

    def test_format_agent_prompt_includes_quick_start(self):
        """Test that prompt includes quick-start section."""
        instructions = "Test"

        result = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="sequential"
        )

        # Should have a quick-start or getting started section
        assert "start" in result.lower()

    def test_format_agent_prompt_footer(self):
        """Test that prompt has closing footer."""
        instructions = "Test"

        result = format_agent_prompt(
            instructions=instructions,
            server_url="http://localhost:8000",
            mode="sequential"
        )

        # Should have footer with separator
        assert result.count("===") >= 2  # Header and footer


class TestSaveAgentInstructions:
    """Tests for save_agent_instructions function."""

    def test_save_agent_instructions_creates_file(self, tmp_path):
        """Test that instructions file is created."""
        content = "# Agent Instructions\n\nTest content"

        result = save_agent_instructions(content, tmp_path)

        assert result.exists()
        assert result.name == "agent_instructions.md"
        assert result.parent.name == ".orchestrator"

    def test_save_agent_instructions_writes_content(self, tmp_path):
        """Test that content is written correctly."""
        content = "# Test Instructions\n\nStep 1\nStep 2"

        result = save_agent_instructions(content, tmp_path)

        saved_content = result.read_text()
        assert saved_content == content

    def test_save_agent_instructions_creates_directory(self, tmp_path):
        """Test that .orchestrator directory is created if needed."""
        content = "Test"

        save_agent_instructions(content, tmp_path)

        assert (tmp_path / ".orchestrator").exists()
        assert (tmp_path / ".orchestrator").is_dir()

    def test_save_agent_instructions_existing_directory(self, tmp_path):
        """Test saving when .orchestrator already exists."""
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir()
        (orchestrator_dir / "other_file.txt").write_text("keep me")

        content = "Test"
        save_agent_instructions(content, tmp_path)

        # Other files should not be affected
        assert (orchestrator_dir / "other_file.txt").exists()
        assert (orchestrator_dir / "agent_instructions.md").exists()

    def test_save_agent_instructions_overwrites_existing(self, tmp_path):
        """Test that existing instructions are overwritten."""
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir()
        instructions_path = orchestrator_dir / "agent_instructions.md"
        instructions_path.write_text("Old content")

        new_content = "New instructions"
        save_agent_instructions(new_content, tmp_path)

        assert instructions_path.read_text() == new_content

    def test_save_agent_instructions_returns_path(self, tmp_path):
        """Test that correct path is returned."""
        content = "Test"

        result = save_agent_instructions(content, tmp_path)

        assert isinstance(result, Path)
        assert result == tmp_path / ".orchestrator" / "agent_instructions.md"

    def test_save_agent_instructions_permission_error(self, tmp_path):
        """Test handling of permission errors."""
        orchestrator_dir = tmp_path / ".orchestrator"
        orchestrator_dir.mkdir()
        orchestrator_dir.chmod(0o444)  # Read-only

        try:
            with pytest.raises(AgentContextError, match="Permission denied"):
                save_agent_instructions("content", tmp_path)
        finally:
            # Cleanup
            orchestrator_dir.chmod(0o755)


class TestInstructionContent:
    """Tests for specific content in generated instructions."""

    def test_instructions_have_task_header(self):
        """Test that task is prominently displayed."""
        result = generate_agent_instructions(
            task="Implement user authentication system",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Task should appear near the top
        lines = result.split('\n')[:10]
        task_mentioned = any("Implement user authentication" in line for line in lines)
        assert task_mentioned

    def test_instructions_have_setup_confirmation(self):
        """Test that setup status is confirmed."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Should mention that setup is complete
        assert "✓" in result or "complete" in result.lower() or "ready" in result.lower()

    def test_instructions_include_sdk_example_with_actual_url(self):
        """Test that SDK example uses actual server URL."""
        server_url = "http://localhost:9876"

        result = generate_agent_instructions(
            task="Task",
            server_url=server_url,
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # SDK example should use actual URL, not placeholder
        assert server_url in result

    def test_instructions_explain_workflow_path(self):
        """Test that workflow file location is explained."""
        workflow_path = Path("/custom/path/workflow.yaml")

        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=workflow_path,
            mode="sequential"
        )

        assert "workflow" in result.lower()
        assert ".yaml" in result.lower()

    def test_instructions_include_phase_guidance(self):
        """Test that instructions explain what to do in each phase."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Should explain at least the PLAN phase (current phase)
        assert "PLAN" in result
        # Should mention what tools are available
        assert "tools" in result.lower() or "allowed" in result.lower()

    def test_instructions_readable_by_ai(self):
        """Test that instructions are structured for AI consumption."""
        result = generate_agent_instructions(
            task="Task",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Should have clear sections
        assert result.count("#") >= 3  # Multiple headers
        # Should have code examples
        assert "```" in result
        # Should have lists
        assert "-" in result or "*" in result or "1." in result


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_generate_instructions_empty_task(self):
        """Test instruction generation with empty task."""
        result = generate_agent_instructions(
            task="",
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Should still generate valid instructions
        assert "AgentClient" in result
        assert len(result) > 100  # Substantial content

    def test_generate_instructions_very_long_task(self):
        """Test instruction generation with very long task description."""
        long_task = "A" * 10000  # 10KB task description

        result = generate_agent_instructions(
            task=long_task,
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Should handle long task without error
        assert long_task in result

    def test_generate_instructions_special_characters_in_task(self):
        """Test task with special characters."""
        task = "Add feature: <script>alert('xss')</script> & \"quotes\""

        result = generate_agent_instructions(
            task=task,
            server_url="http://localhost:8000",
            workflow_path=Path("/tmp/.orchestrator/agent_workflow.yaml"),
            mode="sequential"
        )

        # Should include task without breaking markdown
        assert "Add feature" in result

    def test_save_instructions_empty_content(self, tmp_path):
        """Test saving empty instructions."""
        result = save_agent_instructions("", tmp_path)

        assert result.exists()
        assert result.read_text() == ""

    def test_format_prompt_empty_instructions(self):
        """Test formatting with empty instructions."""
        result = format_agent_prompt(
            instructions="",
            server_url="http://localhost:8000",
            mode="sequential"
        )

        # Should still have header/footer structure
        assert "===" in result
        assert "http://localhost:8000" in result
