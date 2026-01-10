"""
Tool Execution Framework

Provides tool execution capabilities with enforcement integration.
"""

from typing import Any, Dict, Optional
from pathlib import Path
from abc import ABC, abstractmethod
import subprocess
import json


class ToolExecutor(ABC):
    """
    Base class for tool executors

    Each tool executor implements a specific tool (e.g., read_files, bash)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name"""
        pass

    @abstractmethod
    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with given arguments

        Args:
            args: Tool-specific arguments

        Returns:
            Dict with execution result

        Raises:
            ToolExecutionError: If execution fails
        """
        pass


class ToolExecutionError(Exception):
    """Raised when tool execution fails"""
    pass


class ReadFilesTool(ToolExecutor):
    """
    Read files from filesystem

    Args:
        path: File path to read
        offset: Line offset to start reading (optional)
        limit: Maximum lines to read (optional)
    """

    @property
    def name(self) -> str:
        return "read_files"

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read file contents

        Args:
            args: {"path": str, "offset": int, "limit": int}

        Returns:
            {"content": str, "lines": int, "path": str}
        """
        path = args.get("path")
        if not path:
            raise ToolExecutionError("Missing required argument: path")

        file_path = Path(path)
        if not file_path.exists():
            raise ToolExecutionError(f"File not found: {path}")

        if not file_path.is_file():
            raise ToolExecutionError(f"Path is not a file: {path}")

        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # Apply offset and limit if specified
            offset = args.get("offset", 0)
            limit = args.get("limit")

            if offset > 0:
                lines = lines[offset:]

            if limit:
                lines = lines[:limit]

            content = ''.join(lines)

            return {
                "status": "success",
                "content": content,
                "lines": len(lines),
                "path": str(file_path)
            }

        except Exception as e:
            raise ToolExecutionError(f"Failed to read file: {str(e)}")


class WriteFilesTool(ToolExecutor):
    """
    Write files to filesystem

    Args:
        path: File path to write
        content: Content to write
        mode: Write mode ('w' for overwrite, 'a' for append)
    """

    @property
    def name(self) -> str:
        return "write_files"

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Write file contents

        Args:
            args: {"path": str, "content": str, "mode": str}

        Returns:
            {"status": str, "path": str, "bytes_written": int}
        """
        path = args.get("path")
        content = args.get("content")
        mode = args.get("mode", "w")

        if not path:
            raise ToolExecutionError("Missing required argument: path")

        if content is None:
            raise ToolExecutionError("Missing required argument: content")

        if mode not in ["w", "a"]:
            raise ToolExecutionError(f"Invalid mode: {mode}. Must be 'w' or 'a'")

        file_path = Path(path)

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(file_path, mode) as f:
                bytes_written = f.write(content)

            return {
                "status": "success",
                "path": str(file_path),
                "bytes_written": bytes_written,
                "mode": mode
            }

        except Exception as e:
            raise ToolExecutionError(f"Failed to write file: {str(e)}")


class BashTool(ToolExecutor):
    """
    Execute bash commands

    Args:
        command: Bash command to execute
        timeout: Timeout in seconds (default: 30)
        cwd: Working directory (optional)
    """

    @property
    def name(self) -> str:
        return "bash"

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute bash command

        Args:
            args: {"command": str, "timeout": int, "cwd": str}

        Returns:
            {"status": str, "stdout": str, "stderr": str, "exit_code": int}
        """
        command = args.get("command")
        if not command:
            raise ToolExecutionError("Missing required argument: command")

        timeout = args.get("timeout", 30)
        cwd = args.get("cwd")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )

            return {
                "status": "completed",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "command": command
            }

        except subprocess.TimeoutExpired:
            raise ToolExecutionError(f"Command timed out after {timeout} seconds")

        except Exception as e:
            raise ToolExecutionError(f"Failed to execute command: {str(e)}")


class GrepTool(ToolExecutor):
    """
    Search for patterns in files (simplified grep)

    Args:
        pattern: Regex pattern to search for
        path: File or directory to search in
    """

    @property
    def name(self) -> str:
        return "grep"

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Search for pattern in files

        Args:
            args: {"pattern": str, "path": str}

        Returns:
            {"status": str, "matches": list, "total": int}
        """
        pattern = args.get("pattern")
        path = args.get("path")

        if not pattern:
            raise ToolExecutionError("Missing required argument: pattern")

        if not path:
            raise ToolExecutionError("Missing required argument: path")

        file_path = Path(path)
        if not file_path.exists():
            raise ToolExecutionError(f"Path not found: {path}")

        try:
            import re
            regex = re.compile(pattern)

            matches = []

            if file_path.is_file():
                # Search single file
                with open(file_path, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        if regex.search(line):
                            matches.append({
                                "file": str(file_path),
                                "line": line_num,
                                "content": line.rstrip()
                            })

            else:
                # Search directory
                for file in file_path.rglob("*"):
                    if file.is_file():
                        try:
                            with open(file, 'r') as f:
                                for line_num, line in enumerate(f, 1):
                                    if regex.search(line):
                                        matches.append({
                                            "file": str(file),
                                            "line": line_num,
                                            "content": line.rstrip()
                                        })
                        except (UnicodeDecodeError, PermissionError):
                            # Skip binary files or files we can't read
                            continue

            return {
                "status": "success",
                "pattern": pattern,
                "path": str(file_path),
                "matches": matches,
                "total": len(matches)
            }

        except re.error as e:
            raise ToolExecutionError(f"Invalid regex pattern: {str(e)}")

        except Exception as e:
            raise ToolExecutionError(f"Failed to search: {str(e)}")


class ToolRegistry:
    """
    Registry of available tools

    Manages tool executors and provides lookup by name.
    """

    def __init__(self):
        """Initialize tool registry with default tools"""
        self._tools: Dict[str, ToolExecutor] = {}

        # Register default tools
        self.register(ReadFilesTool())
        self.register(WriteFilesTool())
        self.register(BashTool())
        self.register(GrepTool())

    def register(self, tool: ToolExecutor) -> None:
        """
        Register a tool executor

        Args:
            tool: Tool executor instance
        """
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> Optional[ToolExecutor]:
        """
        Get tool executor by name

        Args:
            tool_name: Tool name

        Returns:
            ToolExecutor instance or None if not found
        """
        return self._tools.get(tool_name)

    def list_tools(self) -> list[str]:
        """
        Get list of registered tool names

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name

        Args:
            tool_name: Tool name
            args: Tool arguments

        Returns:
            Tool execution result

        Raises:
            ToolExecutionError: If tool not found or execution fails
        """
        tool = self.get(tool_name)
        if not tool:
            raise ToolExecutionError(
                f"Tool not found: {tool_name}. Available tools: {self.list_tools()}"
            )

        return tool.execute(args)


# Global tool registry instance
tool_registry = ToolRegistry()
