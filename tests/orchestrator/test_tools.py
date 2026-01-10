"""
Day 8: Tool Execution Tests

Tests for tool executors and tool registry.
"""

import pytest
from pathlib import Path
import tempfile
import os

from src.orchestrator.tools import (
    ReadFilesTool,
    WriteFilesTool,
    BashTool,
    GrepTool,
    ToolRegistry,
    ToolExecutionError
)


class TestReadFilesTool:
    """Tests for ReadFilesTool"""

    def test_read_existing_file(self, tmp_path):
        """Should read file contents successfully"""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        tool = ReadFilesTool()
        result = tool.execute({"path": str(test_file)})

        assert result["status"] == "success"
        assert result["content"] == "Line 1\nLine 2\nLine 3\n"
        assert result["lines"] == 3
        assert result["path"] == str(test_file)

    def test_read_file_with_offset(self, tmp_path):
        """Should read file starting from offset"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        tool = ReadFilesTool()
        result = tool.execute({"path": str(test_file), "offset": 1})

        assert result["status"] == "success"
        assert result["content"] == "Line 2\nLine 3\n"
        assert result["lines"] == 2

    def test_read_file_with_limit(self, tmp_path):
        """Should read limited number of lines"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Line 1\nLine 2\nLine 3\n")

        tool = ReadFilesTool()
        result = tool.execute({"path": str(test_file), "limit": 2})

        assert result["status"] == "success"
        assert result["content"] == "Line 1\nLine 2\n"
        assert result["lines"] == 2

    def test_read_nonexistent_file(self):
        """Should raise error for nonexistent file"""
        tool = ReadFilesTool()

        with pytest.raises(ToolExecutionError, match="File not found"):
            tool.execute({"path": "/nonexistent/file.txt"})

    def test_read_missing_path_argument(self):
        """Should raise error when path is missing"""
        tool = ReadFilesTool()

        with pytest.raises(ToolExecutionError, match="Missing required argument: path"):
            tool.execute({})

    def test_read_directory_instead_of_file(self, tmp_path):
        """Should raise error when path is a directory"""
        tool = ReadFilesTool()

        with pytest.raises(ToolExecutionError, match="Path is not a file"):
            tool.execute({"path": str(tmp_path)})


class TestWriteFilesTool:
    """Tests for WriteFilesTool"""

    def test_write_new_file(self, tmp_path):
        """Should create and write to new file"""
        test_file = tmp_path / "output.txt"

        tool = WriteFilesTool()
        result = tool.execute({
            "path": str(test_file),
            "content": "Hello World"
        })

        assert result["status"] == "success"
        assert result["path"] == str(test_file)
        assert result["bytes_written"] > 0
        assert test_file.read_text() == "Hello World"

    def test_write_creates_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist"""
        test_file = tmp_path / "subdir" / "nested" / "file.txt"

        tool = WriteFilesTool()
        result = tool.execute({
            "path": str(test_file),
            "content": "Nested content"
        })

        assert result["status"] == "success"
        assert test_file.exists()
        assert test_file.read_text() == "Nested content"

    def test_write_overwrites_existing_file(self, tmp_path):
        """Should overwrite existing file in write mode"""
        test_file = tmp_path / "file.txt"
        test_file.write_text("Original content")

        tool = WriteFilesTool()
        result = tool.execute({
            "path": str(test_file),
            "content": "New content",
            "mode": "w"
        })

        assert result["status"] == "success"
        assert test_file.read_text() == "New content"

    def test_write_appends_to_file(self, tmp_path):
        """Should append to existing file in append mode"""
        test_file = tmp_path / "file.txt"
        test_file.write_text("Line 1\n")

        tool = WriteFilesTool()
        result = tool.execute({
            "path": str(test_file),
            "content": "Line 2\n",
            "mode": "a"
        })

        assert result["status"] == "success"
        assert test_file.read_text() == "Line 1\nLine 2\n"

    def test_write_missing_path(self):
        """Should raise error when path is missing"""
        tool = WriteFilesTool()

        with pytest.raises(ToolExecutionError, match="Missing required argument: path"):
            tool.execute({"content": "Hello"})

    def test_write_missing_content(self, tmp_path):
        """Should raise error when content is missing"""
        tool = WriteFilesTool()

        with pytest.raises(ToolExecutionError, match="Missing required argument: content"):
            tool.execute({"path": str(tmp_path / "file.txt")})

    def test_write_invalid_mode(self, tmp_path):
        """Should raise error for invalid mode"""
        tool = WriteFilesTool()

        with pytest.raises(ToolExecutionError, match="Invalid mode"):
            tool.execute({
                "path": str(tmp_path / "file.txt"),
                "content": "Hello",
                "mode": "x"
            })


class TestBashTool:
    """Tests for BashTool"""

    def test_bash_simple_command(self):
        """Should execute simple bash command"""
        tool = BashTool()
        result = tool.execute({"command": "echo 'Hello World'"})

        assert result["status"] == "completed"
        assert "Hello World" in result["stdout"]
        assert result["exit_code"] == 0

    def test_bash_command_with_exit_code(self):
        """Should capture non-zero exit codes"""
        tool = BashTool()
        result = tool.execute({"command": "exit 42"})

        assert result["status"] == "completed"
        assert result["exit_code"] == 42

    def test_bash_command_with_stderr(self):
        """Should capture stderr"""
        tool = BashTool()
        result = tool.execute({"command": "echo 'Error' >&2"})

        assert result["status"] == "completed"
        assert "Error" in result["stderr"]

    def test_bash_command_with_cwd(self, tmp_path):
        """Should execute command in specified working directory"""
        tool = BashTool()
        result = tool.execute({
            "command": "pwd",
            "cwd": str(tmp_path)
        })

        assert result["status"] == "completed"
        assert str(tmp_path) in result["stdout"]

    def test_bash_missing_command(self):
        """Should raise error when command is missing"""
        tool = BashTool()

        with pytest.raises(ToolExecutionError, match="Missing required argument: command"):
            tool.execute({})

    def test_bash_command_timeout(self):
        """Should timeout long-running commands"""
        tool = BashTool()

        with pytest.raises(ToolExecutionError, match="timed out"):
            tool.execute({
                "command": "sleep 10",
                "timeout": 1
            })


class TestGrepTool:
    """Tests for GrepTool"""

    def test_grep_finds_pattern_in_file(self, tmp_path):
        """Should find pattern in single file"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('world')\n    return True\n")

        tool = GrepTool()
        result = tool.execute({
            "pattern": "def.*:",
            "path": str(test_file)
        })

        assert result["status"] == "success"
        assert result["total"] == 1
        assert len(result["matches"]) == 1
        assert "def hello():" in result["matches"][0]["content"]

    def test_grep_multiple_matches(self, tmp_path):
        """Should find multiple matches"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def func1():\n    pass\ndef func2():\n    pass\n")

        tool = GrepTool()
        result = tool.execute({
            "pattern": "def",
            "path": str(test_file)
        })

        assert result["status"] == "success"
        assert result["total"] == 2

    def test_grep_no_matches(self, tmp_path):
        """Should return empty matches when pattern not found"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World\n")

        tool = GrepTool()
        result = tool.execute({
            "pattern": "xyz",
            "path": str(test_file)
        })

        assert result["status"] == "success"
        assert result["total"] == 0
        assert len(result["matches"]) == 0

    def test_grep_in_directory(self, tmp_path):
        """Should search all files in directory"""
        (tmp_path / "file1.txt").write_text("pattern here\n")
        (tmp_path / "file2.txt").write_text("no match\n")
        (tmp_path / "file3.txt").write_text("pattern again\n")

        tool = GrepTool()
        result = tool.execute({
            "pattern": "pattern",
            "path": str(tmp_path)
        })

        assert result["status"] == "success"
        assert result["total"] == 2

    def test_grep_missing_pattern(self, tmp_path):
        """Should raise error when pattern is missing"""
        tool = GrepTool()

        with pytest.raises(ToolExecutionError, match="Missing required argument: pattern"):
            tool.execute({"path": str(tmp_path)})

    def test_grep_missing_path(self):
        """Should raise error when path is missing"""
        tool = GrepTool()

        with pytest.raises(ToolExecutionError, match="Missing required argument: path"):
            tool.execute({"pattern": "test"})

    def test_grep_invalid_regex(self, tmp_path):
        """Should raise error for invalid regex"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello\n")

        tool = GrepTool()

        with pytest.raises(ToolExecutionError, match="Invalid regex pattern"):
            tool.execute({
                "pattern": "[invalid(",
                "path": str(test_file)
            })


class TestToolRegistry:
    """Tests for ToolRegistry"""

    def test_registry_has_default_tools(self):
        """Should register default tools on initialization"""
        registry = ToolRegistry()

        assert "read_files" in registry.list_tools()
        assert "write_files" in registry.list_tools()
        assert "bash" in registry.list_tools()
        assert "grep" in registry.list_tools()

    def test_registry_get_tool(self):
        """Should retrieve tool by name"""
        registry = ToolRegistry()
        tool = registry.get("read_files")

        assert tool is not None
        assert tool.name == "read_files"

    def test_registry_get_nonexistent_tool(self):
        """Should return None for nonexistent tool"""
        registry = ToolRegistry()
        tool = registry.get("nonexistent")

        assert tool is None

    def test_registry_execute_tool(self, tmp_path):
        """Should execute tool via registry"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Content")

        registry = ToolRegistry()
        result = registry.execute("read_files", {"path": str(test_file)})

        assert result["status"] == "success"
        assert result["content"] == "Content"

    def test_registry_execute_nonexistent_tool(self):
        """Should raise error for nonexistent tool"""
        registry = ToolRegistry()

        with pytest.raises(ToolExecutionError, match="Tool not found"):
            registry.execute("nonexistent", {})

    def test_registry_register_custom_tool(self):
        """Should allow registering custom tools"""
        from src.orchestrator.tools import ToolExecutor

        class CustomTool(ToolExecutor):
            @property
            def name(self):
                return "custom"

            def execute(self, args):
                return {"status": "custom_success"}

        registry = ToolRegistry()
        registry.register(CustomTool())

        assert "custom" in registry.list_tools()

        result = registry.execute("custom", {})
        assert result["status"] == "custom_success"


class TestToolIntegrationWithAPI:
    """Integration tests with API"""

    def test_api_executes_read_files_tool(self, tmp_path):
        """Should execute read_files tool through API"""
        # This test will need the API client fixture
        # For now, just test the tool directly
        test_file = tmp_path / "api_test.txt"
        test_file.write_text("API content")

        from src.orchestrator.tools import tool_registry

        result = tool_registry.execute("read_files", {"path": str(test_file)})

        assert result["status"] == "success"
        assert "API content" in result["content"]
