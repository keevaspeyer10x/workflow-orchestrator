"""
Tool definitions and execution functions for OpenRouter function calling.

This module provides tools that allow AI models to interactively explore
repository context during execution via OpenRouter's function calling API.

Tools:
- read_file: Read file contents
- list_files: List files matching a glob pattern
- search_code: Search for code/text patterns (grep-like)

All tools are read-only and sandboxed to the working directory.
"""

import re
import logging
from pathlib import Path
from typing import Any, Optional
import fnmatch

logger = logging.getLogger(__name__)

# Warning thresholds (soft limits - warn but don't block)
FILE_SIZE_WARNING_BYTES = 2 * 1024 * 1024  # 2MB
FILE_SIZE_HARD_LIMIT_BYTES = 50 * 1024 * 1024  # 50MB
TOOL_CALL_WARNING_COUNT = 50
TOOL_CALL_HARD_LIMIT = 200

# Tool definitions in OpenAI function calling format
READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read the contents of a file from the repository. Returns the file content as text. Use this to examine source code, configuration files, documentation, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path relative to the repository root (e.g., 'src/main.py', 'README.md')"
                }
            },
            "required": ["path"]
        }
    }
}

LIST_FILES_TOOL = {
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files in the repository matching a glob pattern. Use '**' for recursive matching. Returns a list of matching file paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g., '*.py', 'src/**/*.js', '**/*.md')"
                }
            },
            "required": ["pattern"]
        }
    }
}

SEARCH_CODE_TOOL = {
    "type": "function",
    "function": {
        "name": "search_code",
        "description": "Search for a pattern in the repository code. Returns matching lines with file paths and line numbers. Supports regular expressions.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The search pattern (regular expression supported)"
                },
                "path": {
                    "type": "string",
                    "description": "Optional: limit search to a specific file or directory"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional: only search files matching this glob pattern (e.g., '*.py')"
                }
            },
            "required": ["pattern"]
        }
    }
}


def get_tool_definitions() -> list[dict]:
    """Return all available tool definitions for OpenRouter API."""
    return [READ_FILE_TOOL, LIST_FILES_TOOL, SEARCH_CODE_TOOL]


def _validate_path(path: str, working_dir: Path) -> tuple[bool, Path | str]:
    """
    Validate and resolve a path, ensuring it's within the working directory.

    Args:
        path: The requested path (relative or absolute)
        working_dir: The sandbox directory

    Returns:
        Tuple of (is_valid, resolved_path_or_error_message)
    """
    try:
        # Resolve the path relative to working_dir
        resolved = (working_dir / path).resolve()

        # Security check: ensure resolved path is within working_dir
        if not resolved.is_relative_to(working_dir.resolve()):
            return False, "Path outside working directory"

        return True, resolved
    except Exception as e:
        return False, f"Invalid path: {e}"


def execute_read_file(path: str, working_dir: Path) -> dict[str, Any]:
    """
    Read a file's contents.

    Args:
        path: File path relative to working_dir
        working_dir: The sandbox directory

    Returns:
        Dict with 'content' and 'size', or 'error' on failure
    """
    is_valid, result = _validate_path(path, working_dir)
    if not is_valid:
        return {"error": result, "path": path}

    file_path = result

    if not file_path.exists():
        return {"error": "File not found", "path": path}

    if not file_path.is_file():
        return {"error": "Not a file (may be a directory)", "path": path}

    try:
        file_size = file_path.stat().st_size

        # Soft warning for large files
        if file_size > FILE_SIZE_WARNING_BYTES:
            logger.warning(
                f"Large file ({file_size / 1024 / 1024:.1f}MB): {path}"
            )

        # Hard limit for very large files
        if file_size > FILE_SIZE_HARD_LIMIT_BYTES:
            return {
                "error": f"File too large ({file_size / 1024 / 1024:.1f}MB exceeds {FILE_SIZE_HARD_LIMIT_BYTES / 1024 / 1024:.0f}MB limit)",
                "path": path,
                "size": file_size,
                "truncated": True
            }

        # Try to read as text
        try:
            content = file_path.read_text(encoding="utf-8")
            return {
                "content": content,
                "size": file_size,
                "path": path
            }
        except UnicodeDecodeError:
            # Binary file
            return {
                "error": "Binary file (cannot read as text)",
                "path": path,
                "size": file_size
            }

    except PermissionError:
        return {"error": "Permission denied", "path": path}
    except Exception as e:
        return {"error": f"Read error: {e}", "path": path}


def execute_list_files(pattern: str, working_dir: Path) -> dict[str, Any]:
    """
    List files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*.py", "**/*.js")
        working_dir: The sandbox directory

    Returns:
        Dict with 'files' list, or 'error' on failure
    """
    try:
        # Use pathlib's glob for pattern matching
        if "**" in pattern:
            matches = list(working_dir.glob(pattern))
        else:
            matches = list(working_dir.glob(pattern))

        # Filter to only files (not directories) and convert to relative paths
        files = []
        for match in matches:
            if match.is_file():
                try:
                    rel_path = match.relative_to(working_dir)
                    files.append(str(rel_path))
                except ValueError:
                    # Skip files outside working_dir (shouldn't happen with glob)
                    pass

        # Sort for consistent output
        files.sort()

        return {
            "files": files,
            "count": len(files),
            "pattern": pattern
        }

    except Exception as e:
        return {"error": f"List error: {e}", "pattern": pattern}


def execute_search_code(
    pattern: str,
    working_dir: Path,
    path: Optional[str] = None,
    file_pattern: Optional[str] = None,
    max_matches: int = 100
) -> dict[str, Any]:
    """
    Search for a pattern in repository files.

    Args:
        pattern: Regex pattern to search for
        working_dir: The sandbox directory
        path: Optional specific file/directory to search in
        file_pattern: Optional glob pattern to filter files
        max_matches: Maximum number of matches to return

    Returns:
        Dict with 'matches' list, or 'error' on failure
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return {"error": f"Invalid regex pattern: {e}", "pattern": pattern}

    matches = []
    files_searched = 0

    try:
        # Determine which files to search
        if path:
            is_valid, result = _validate_path(path, working_dir)
            if not is_valid:
                return {"error": result, "path": path}

            search_path = result
            if search_path.is_file():
                files_to_search = [search_path]
            elif search_path.is_dir():
                files_to_search = list(search_path.rglob("*"))
            else:
                return {"error": "Path not found", "path": path}
        else:
            # Search all files in working_dir
            files_to_search = list(working_dir.rglob("*"))

        # Filter by file_pattern if provided
        if file_pattern:
            files_to_search = [
                f for f in files_to_search
                if f.is_file() and fnmatch.fnmatch(f.name, file_pattern)
            ]

        for file_path in files_to_search:
            if not file_path.is_file():
                continue

            # Skip very large files
            try:
                if file_path.stat().st_size > FILE_SIZE_WARNING_BYTES:
                    continue
            except OSError:
                continue

            files_searched += 1

            # Try to read and search
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError, OSError):
                continue

            # Search line by line
            for line_num, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    try:
                        rel_path = file_path.relative_to(working_dir)
                    except ValueError:
                        continue

                    matches.append({
                        "file": str(rel_path),
                        "line": line_num,
                        "content": line.strip()[:200]  # Truncate long lines
                    })

                    if len(matches) >= max_matches:
                        return {
                            "matches": matches,
                            "count": len(matches),
                            "truncated": True,
                            "files_searched": files_searched,
                            "pattern": pattern
                        }

        return {
            "matches": matches,
            "count": len(matches),
            "truncated": False,
            "files_searched": files_searched,
            "pattern": pattern
        }

    except Exception as e:
        return {"error": f"Search error: {e}", "pattern": pattern}


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    working_dir: Path
) -> dict[str, Any]:
    """
    Execute a tool by name with the given arguments.

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments
        working_dir: The sandbox directory

    Returns:
        Tool result dict
    """
    if tool_name == "read_file":
        path = arguments.get("path", "")
        return execute_read_file(path, working_dir)

    elif tool_name == "list_files":
        pattern = arguments.get("pattern", "*")
        return execute_list_files(pattern, working_dir)

    elif tool_name == "search_code":
        pattern = arguments.get("pattern", "")
        path = arguments.get("path")
        file_pattern = arguments.get("file_pattern")
        return execute_search_code(pattern, working_dir, path, file_pattern)

    else:
        return {"error": f"Unknown tool: {tool_name}"}
