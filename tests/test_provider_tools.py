"""
Tests for the provider tools module (function calling support).
"""

import os
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])

from src.providers.tools import (
    get_tool_definitions,
    execute_tool,
    execute_read_file,
    execute_list_files,
    execute_search_code,
    _validate_path,
    READ_FILE_TOOL,
    LIST_FILES_TOOL,
    SEARCH_CODE_TOOL,
    FILE_SIZE_WARNING_BYTES,
    FILE_SIZE_HARD_LIMIT_BYTES,
    TOOL_CALL_WARNING_COUNT,
    TOOL_CALL_HARD_LIMIT,
)
from src.providers.openrouter import (
    OpenRouterProvider,
    FUNCTION_CALLING_MODELS,
)
from src.providers.base import ExecutionResult


class TestToolDefinitions:
    """Tests for tool schema definitions."""

    def test_get_tool_definitions_returns_all_tools(self):
        """Test that get_tool_definitions returns all three tools."""
        tools = get_tool_definitions()
        assert len(tools) == 3
        tool_names = [t["function"]["name"] for t in tools]
        assert "read_file" in tool_names
        assert "list_files" in tool_names
        assert "search_code" in tool_names

    def test_read_file_tool_schema(self):
        """Test READ_FILE_TOOL has correct schema."""
        assert READ_FILE_TOOL["type"] == "function"
        func = READ_FILE_TOOL["function"]
        assert func["name"] == "read_file"
        assert "description" in func
        assert "parameters" in func
        params = func["parameters"]
        assert "path" in params["properties"]
        assert "path" in params["required"]

    def test_list_files_tool_schema(self):
        """Test LIST_FILES_TOOL has correct schema."""
        assert LIST_FILES_TOOL["type"] == "function"
        func = LIST_FILES_TOOL["function"]
        assert func["name"] == "list_files"
        assert "pattern" in func["parameters"]["properties"]
        assert "pattern" in func["parameters"]["required"]

    def test_search_code_tool_schema(self):
        """Test SEARCH_CODE_TOOL has correct schema."""
        assert SEARCH_CODE_TOOL["type"] == "function"
        func = SEARCH_CODE_TOOL["function"]
        assert func["name"] == "search_code"
        params = func["parameters"]
        assert "pattern" in params["properties"]
        assert "pattern" in params["required"]
        # Optional parameters
        assert "path" in params["properties"]
        assert "file_pattern" in params["properties"]


class TestPathValidation:
    """Tests for path validation and sandboxing."""

    def test_validate_path_normal(self):
        """Test validating a normal path within working_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            test_file = working_dir / "test.txt"
            test_file.touch()

            is_valid, result = _validate_path("test.txt", working_dir)
            assert is_valid is True
            assert result == test_file.resolve()

    def test_validate_path_traversal_blocked(self):
        """Test that path traversal attempts are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            is_valid, result = _validate_path("../etc/passwd", working_dir)
            assert is_valid is False
            assert "outside working directory" in result.lower()

    def test_validate_path_absolute_outside_blocked(self):
        """Test that absolute paths outside working_dir are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            is_valid, result = _validate_path("/etc/passwd", working_dir)
            assert is_valid is False
            assert "outside working directory" in result.lower()

    def test_validate_path_nested_valid(self):
        """Test validating nested paths within working_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            nested_dir = working_dir / "src" / "lib"
            nested_dir.mkdir(parents=True)
            test_file = nested_dir / "module.py"
            test_file.touch()

            is_valid, result = _validate_path("src/lib/module.py", working_dir)
            assert is_valid is True


class TestReadFile:
    """Tests for execute_read_file."""

    def test_read_file_basic(self):
        """Test reading a normal file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            test_file = working_dir / "test.txt"
            test_file.write_text("Hello, World!")

            result = execute_read_file("test.txt", working_dir)
            assert "content" in result
            assert result["content"] == "Hello, World!"
            assert result["size"] == 13

    def test_read_file_not_found(self):
        """Test reading a nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            result = execute_read_file("nonexistent.txt", working_dir)
            assert "error" in result
            assert "not found" in result["error"].lower()

    def test_read_file_path_traversal_blocked(self):
        """Test that path traversal is blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            result = execute_read_file("../../etc/passwd", working_dir)
            assert "error" in result
            assert "outside working directory" in result["error"].lower()

    def test_read_file_directory_error(self):
        """Test reading a directory returns error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            subdir = working_dir / "subdir"
            subdir.mkdir()

            result = execute_read_file("subdir", working_dir)
            assert "error" in result
            assert "not a file" in result["error"].lower()

    def test_read_file_large_file_warning(self):
        """Test that large files trigger a warning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            large_file = working_dir / "large.txt"
            # Create a file larger than 2MB
            large_file.write_text("x" * (FILE_SIZE_WARNING_BYTES + 1000))

            with patch("src.providers.tools.logger") as mock_logger:
                result = execute_read_file("large.txt", working_dir)
                assert "content" in result  # Still reads the file
                mock_logger.warning.assert_called()

    def test_read_file_binary_error(self):
        """Test that binary files return an error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            binary_file = working_dir / "binary.bin"
            binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

            result = execute_read_file("binary.bin", working_dir)
            assert "error" in result
            assert "binary" in result["error"].lower()


class TestListFiles:
    """Tests for execute_list_files."""

    def test_list_files_basic_glob(self):
        """Test listing files with a basic glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "a.py").touch()
            (working_dir / "b.py").touch()
            (working_dir / "c.txt").touch()

            result = execute_list_files("*.py", working_dir)
            assert "files" in result
            assert len(result["files"]) == 2
            assert "a.py" in result["files"]
            assert "b.py" in result["files"]
            assert "c.txt" not in result["files"]

    def test_list_files_recursive_glob(self):
        """Test listing files with recursive glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "root.py").touch()
            subdir = working_dir / "src"
            subdir.mkdir()
            (subdir / "module.py").touch()

            result = execute_list_files("**/*.py", working_dir)
            assert "files" in result
            assert len(result["files"]) == 2

    def test_list_files_no_matches(self):
        """Test listing files with no matches returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            result = execute_list_files("*.xyz", working_dir)
            assert "files" in result
            assert result["files"] == []
            assert result["count"] == 0

    def test_list_files_returns_sorted(self):
        """Test that file list is sorted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "c.txt").touch()
            (working_dir / "a.txt").touch()
            (working_dir / "b.txt").touch()

            result = execute_list_files("*.txt", working_dir)
            assert result["files"] == ["a.txt", "b.txt", "c.txt"]


class TestSearchCode:
    """Tests for execute_search_code."""

    def test_search_code_basic(self):
        """Test basic code search."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            test_file = working_dir / "test.py"
            test_file.write_text("def foo():\n    pass\n\ndef bar():\n    pass")

            result = execute_search_code(r"def \w+", working_dir)
            assert "matches" in result
            assert len(result["matches"]) == 2

    def test_search_code_with_path_filter(self):
        """Test search with path filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "a.py").write_text("def foo(): pass")
            (working_dir / "b.py").write_text("def foo(): pass")

            result = execute_search_code("def foo", working_dir, path="a.py")
            assert "matches" in result
            assert len(result["matches"]) == 1
            assert result["matches"][0]["file"] == "a.py"

    def test_search_code_with_file_pattern(self):
        """Test search with file pattern filter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "code.py").write_text("pattern here")
            (working_dir / "text.txt").write_text("pattern here")

            result = execute_search_code("pattern", working_dir, file_pattern="*.py")
            assert "matches" in result
            assert len(result["matches"]) == 1
            assert result["matches"][0]["file"] == "code.py"

    def test_search_code_no_matches(self):
        """Test search with no matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "test.py").write_text("hello world")

            result = execute_search_code("nonexistent_xyz", working_dir)
            assert "matches" in result
            assert result["matches"] == []
            assert result["count"] == 0

    def test_search_code_invalid_regex(self):
        """Test search with invalid regex pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            result = execute_search_code("[invalid", working_dir)
            assert "error" in result
            assert "regex" in result["error"].lower()

    def test_search_code_includes_line_numbers(self):
        """Test that search results include line numbers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            test_file = working_dir / "test.py"
            test_file.write_text("line1\npattern\nline3")

            result = execute_search_code("pattern", working_dir)
            assert len(result["matches"]) == 1
            assert result["matches"][0]["line"] == 2


class TestExecuteTool:
    """Tests for the execute_tool dispatcher."""

    def test_execute_tool_read_file(self):
        """Test execute_tool dispatches to read_file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "test.txt").write_text("content")

            result = execute_tool("read_file", {"path": "test.txt"}, working_dir)
            assert "content" in result

    def test_execute_tool_list_files(self):
        """Test execute_tool dispatches to list_files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "test.py").touch()

            result = execute_tool("list_files", {"pattern": "*.py"}, working_dir)
            assert "files" in result

    def test_execute_tool_search_code(self):
        """Test execute_tool dispatches to search_code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "test.py").write_text("hello")

            result = execute_tool("search_code", {"pattern": "hello"}, working_dir)
            assert "matches" in result

    def test_execute_tool_unknown(self):
        """Test execute_tool returns error for unknown tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)

            result = execute_tool("unknown_tool", {}, working_dir)
            assert "error" in result
            assert "unknown" in result["error"].lower()


class TestModelDetection:
    """Tests for model function calling support detection."""

    def test_supports_gpt4(self):
        """Test that GPT-4 models are detected as supporting function calling."""
        provider = OpenRouterProvider(api_key="test")
        assert provider._supports_function_calling("openai/gpt-4") is True
        assert provider._supports_function_calling("openai/gpt-4-turbo") is True
        assert provider._supports_function_calling("openai/gpt-4o") is True

    def test_supports_claude(self):
        """Test that Claude 3+ models are detected as supporting function calling."""
        provider = OpenRouterProvider(api_key="test")
        assert provider._supports_function_calling("anthropic/claude-3-opus") is True
        assert provider._supports_function_calling("anthropic/claude-3-sonnet") is True
        assert provider._supports_function_calling("anthropic/claude-sonnet-4") is True

    def test_supports_gemini(self):
        """Test that Gemini models are detected as supporting function calling."""
        provider = OpenRouterProvider(api_key="test")
        assert provider._supports_function_calling("google/gemini-pro") is True
        assert provider._supports_function_calling("google/gemini-2.0-flash") is True

    def test_unknown_model_returns_false(self):
        """Test that unknown models default to no function calling support."""
        provider = OpenRouterProvider(api_key="test")
        assert provider._supports_function_calling("unknown/model") is False

    def test_prefix_matching(self):
        """Test that versioned models match by prefix."""
        provider = OpenRouterProvider(api_key="test")
        # These should match "openai/gpt-4" prefix
        assert provider._supports_function_calling("openai/gpt-4-0613") is True
        assert provider._supports_function_calling("openai/gpt-4-turbo-2024") is True


class TestOpenRouterProviderWithTools:
    """Tests for OpenRouterProvider function calling integration."""

    def test_init_with_working_dir(self):
        """Test provider accepts working_dir parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = OpenRouterProvider(
                api_key="test",
                working_dir=Path(tmpdir)
            )
            assert provider._working_dir == Path(tmpdir)

    def test_init_defaults_to_cwd(self):
        """Test provider defaults to current working directory."""
        provider = OpenRouterProvider(api_key="test")
        assert provider._working_dir == Path.cwd()

    def test_enable_tools_default(self):
        """Test tools are enabled by default."""
        provider = OpenRouterProvider(api_key="test")
        assert provider._enable_tools is True

    def test_disable_tools_via_env(self):
        """Test tools can be disabled via environment variable."""
        with patch.dict(os.environ, {"ORCHESTRATOR_DISABLE_TOOLS": "1"}):
            provider = OpenRouterProvider(api_key="test")
            assert provider._enable_tools is False

    def test_disable_tools_via_param(self):
        """Test tools can be disabled via parameter."""
        provider = OpenRouterProvider(api_key="test", enable_tools=False)
        assert provider._enable_tools is False

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_execute_uses_tools_for_supported_model(self):
        """Test execute() uses function calling for supported models."""
        provider = OpenRouterProvider()

        with patch.object(provider, "execute_with_tools") as mock_execute_tools:
            mock_execute_tools.return_value = ExecutionResult(True, "done")
            provider.execute("test", model="openai/gpt-4")
            mock_execute_tools.assert_called_once()

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_execute_uses_basic_for_unsupported_model(self):
        """Test execute() uses basic execution for unsupported models."""
        provider = OpenRouterProvider()

        with patch.object(provider, "_execute_basic") as mock_basic:
            mock_basic.return_value = ExecutionResult(True, "done")
            provider.execute("test", model="unknown/model")
            mock_basic.assert_called_once()

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_execute_respects_disable_tools(self):
        """Test execute() respects enable_tools=False."""
        provider = OpenRouterProvider(enable_tools=False)

        with patch.object(provider, "_execute_basic") as mock_basic:
            mock_basic.return_value = ExecutionResult(True, "done")
            # Even with a supported model, should use basic
            provider.execute("test", model="openai/gpt-4")
            mock_basic.assert_called_once()


class TestExecuteWithToolsMocked:
    """Tests for execute_with_tools with mocked API."""

    @patch("src.providers.openrouter.requests.post")
    def test_execute_with_tools_no_tool_calls(self, mock_post):
        """Test execution when model doesn't call any tools."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "Final answer"},
                "finish_reason": "stop"
            }],
            "usage": {"total_tokens": 100}
        }
        mock_post.return_value = mock_response

        provider = OpenRouterProvider(api_key="test")
        result = provider.execute_with_tools("Test prompt", "openai/gpt-4")

        assert result.success is True
        assert result.output == "Final answer"
        assert result.metadata["tool_calls"] == 0

    @patch("src.providers.openrouter.requests.post")
    def test_execute_with_tools_single_tool_call(self, mock_post):
        """Test execution with a single tool call."""
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir)
            (working_dir / "test.txt").write_text("File content")

            # First call: model requests tool
            tool_call_response = MagicMock()
            tool_call_response.status_code = 200
            tool_call_response.json.return_value = {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "id": "call_123",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "test.txt"}'
                            }
                        }]
                    }
                }],
                "usage": {"total_tokens": 50}
            }

            # Second call: model provides final answer
            final_response = MagicMock()
            final_response.status_code = 200
            final_response.json.return_value = {
                "choices": [{
                    "message": {"content": "The file contains: File content"},
                    "finish_reason": "stop"
                }],
                "usage": {"total_tokens": 75}
            }

            mock_post.side_effect = [tool_call_response, final_response]

            provider = OpenRouterProvider(api_key="test", working_dir=working_dir)
            result = provider.execute_with_tools("Read test.txt", "openai/gpt-4")

            assert result.success is True
            assert result.metadata["tool_calls"] == 1
            assert result.tokens_used == 125  # 50 + 75

    @patch("src.providers.openrouter.requests.post")
    def test_execute_with_tools_api_error_fallback(self, mock_post):
        """Test fallback to basic execution on API error."""
        # First call fails
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"error": {"message": "Bad request"}}

        # Fallback succeeds
        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "choices": [{"message": {"content": "Fallback response"}}],
            "usage": {"total_tokens": 50}
        }

        mock_post.side_effect = [error_response, success_response]

        provider = OpenRouterProvider(api_key="test")
        result = provider.execute_with_tools("Test", "openai/gpt-4")

        assert result.success is True
        assert result.metadata.get("used_function_calling") is False


class TestBackwardsCompatibility:
    """Tests to ensure backwards compatibility."""

    def test_execute_signature_unchanged(self):
        """Test that execute() signature remains compatible."""
        provider = OpenRouterProvider(api_key="test")
        # Should accept same parameters as before
        with patch.object(provider, "_execute_basic") as mock:
            mock.return_value = ExecutionResult(True, "done")
            # Call with just prompt
            provider.execute("test prompt")
            # Call with prompt and model
            provider.execute("test prompt", model="test/model")

    def test_execution_result_format_unchanged(self):
        """Test ExecutionResult has same required fields."""
        result = ExecutionResult(
            success=True,
            output="test",
            model_used="test-model",
            error=None,
            tokens_used=100,
            duration_seconds=1.0,
            metadata={}
        )
        # All original fields should exist
        assert hasattr(result, "success")
        assert hasattr(result, "output")
        assert hasattr(result, "model_used")
        assert hasattr(result, "error")
        assert hasattr(result, "tokens_used")
        assert hasattr(result, "duration_seconds")
        assert hasattr(result, "metadata")


class TestThresholds:
    """Tests for warning and limit thresholds."""

    def test_file_size_warning_threshold(self):
        """Test FILE_SIZE_WARNING_BYTES is 2MB."""
        assert FILE_SIZE_WARNING_BYTES == 2 * 1024 * 1024

    def test_file_size_hard_limit(self):
        """Test FILE_SIZE_HARD_LIMIT_BYTES is 50MB."""
        assert FILE_SIZE_HARD_LIMIT_BYTES == 50 * 1024 * 1024

    def test_tool_call_warning_count(self):
        """Test TOOL_CALL_WARNING_COUNT is 50."""
        assert TOOL_CALL_WARNING_COUNT == 50

    def test_tool_call_hard_limit(self):
        """Test TOOL_CALL_HARD_LIMIT is 200."""
        assert TOOL_CALL_HARD_LIMIT == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
