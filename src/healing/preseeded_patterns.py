"""Pre-seeded Patterns - Phase 2 Pattern Memory & Lookup.

Common error patterns with known fixes that work out of the box.
These patterns are loaded into Supabase on first run.
"""

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .supabase_client import HealingSupabaseClient


# Pre-built patterns for common errors
# Each pattern has:
#   - fingerprint_pattern: Regex to match error messages
#   - safety_category: "safe", "moderate", or "risky"
#   - action: The fix action (command, file_edit, diff, multi_step)
PRESEEDED_PATTERNS: list[dict] = [
    # ===================
    # Python Errors
    # ===================

    # ModuleNotFoundError - missing pip package
    {
        "fingerprint_pattern": r"ModuleNotFoundError: No module named '(\w+)'",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "pip install {match_1}",
        },
        "description": "Python module not found - install with pip",
    },

    # ImportError - cannot import name
    {
        "fingerprint_pattern": r"ImportError: cannot import name '(\w+)' from '([\w.]+)'",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Python import error - check import statement",
    },

    # SyntaxError - f-string brace escape
    {
        "fingerprint_pattern": r"SyntaxError: f-string: single '\}' is not allowed",
        "safety_category": "safe",
        "action": {
            "action_type": "file_edit",
            "find": "}}",
            "replace": "\\}",
            "requires_context": True,
        },
        "description": "F-string brace escape error",
    },

    # SyntaxError - invalid syntax
    {
        "fingerprint_pattern": r"SyntaxError: invalid syntax",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Python syntax error - check line for typos",
    },

    # TypeError - NoneType is not subscriptable
    {
        "fingerprint_pattern": r"TypeError: 'NoneType' object is not subscriptable",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "NoneType subscript error - add null check",
    },

    # TypeError - NoneType is not iterable
    {
        "fingerprint_pattern": r"TypeError: 'NoneType' object is not iterable",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "NoneType iteration error - add null check or default",
    },

    # TypeError - NoneType is not callable
    {
        "fingerprint_pattern": r"TypeError: 'NoneType' object is not callable",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "NoneType callable error - check function assignment",
    },

    # AttributeError - NoneType has no attribute
    {
        "fingerprint_pattern": r"AttributeError: 'NoneType' object has no attribute '(\w+)'",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "NoneType attribute error - add null check",
    },

    # KeyError
    {
        "fingerprint_pattern": r"KeyError: '(\w+)'",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Dict key error - use .get() or check key existence",
    },

    # IndexError - list index out of range
    {
        "fingerprint_pattern": r"IndexError: list index out of range",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "List index error - check bounds before access",
    },

    # FileNotFoundError
    {
        "fingerprint_pattern": r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'",
        "safety_category": "moderate",
        "action": {
            "action_type": "multi_step",
            "steps": [
                {"action_type": "command", "command": "ls -la $(dirname '{match_1}')"},
            ],
            "requires_context": True,
        },
        "description": "File not found - check path exists",
    },

    # PermissionError
    {
        "fingerprint_pattern": r"PermissionError: \[Errno 13\] Permission denied: '([^']+)'",
        "safety_category": "risky",
        "action": {
            "action_type": "command",
            "command": "ls -la {match_1}",
        },
        "description": "Permission denied - check file permissions",
    },

    # ===================
    # pytest Errors
    # ===================

    # pytest fixture not found
    {
        "fingerprint_pattern": r"fixture '(\w+)' not found",
        "safety_category": "safe",
        "action": {
            "action_type": "multi_step",
            "steps": [
                {"action_type": "command", "command": "grep -r 'def {match_1}' tests/ conftest.py"},
            ],
        },
        "description": "Pytest fixture not found - search for definition",
    },

    # pytest collection error
    {
        "fingerprint_pattern": r"ERROR collecting ([\w/]+\.py)",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Pytest collection error - check test file syntax",
    },

    # ===================
    # Node.js Errors
    # ===================

    # Cannot find module
    {
        "fingerprint_pattern": r"Cannot find module '([^']+)'",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "npm install {match_1}",
        },
        "description": "Node module not found - install with npm",
    },

    # Cannot find module (local)
    {
        "fingerprint_pattern": r"Cannot find module '\./([^']+)'",
        "safety_category": "moderate",
        "action": {
            "action_type": "multi_step",
            "steps": [
                {"action_type": "command", "command": "ls -la ./{match_1}*"},
            ],
            "requires_context": True,
        },
        "description": "Local module not found - check path",
    },

    # TypeError: is not a function
    {
        "fingerprint_pattern": r"TypeError: (\w+) is not a function",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "JavaScript type error - check function exists",
    },

    # ReferenceError: is not defined
    {
        "fingerprint_pattern": r"ReferenceError: (\w+) is not defined",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "JavaScript reference error - check variable/import",
    },

    # ===================
    # Go Errors
    # ===================

    # cannot find package
    {
        "fingerprint_pattern": r'cannot find package "([^"]+)"',
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "go get {match_1}",
        },
        "description": "Go package not found - install with go get",
    },

    # undefined: identifier
    {
        "fingerprint_pattern": r"undefined: (\w+)",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Go undefined identifier - check import or declaration",
    },

    # ===================
    # Rust Errors
    # ===================

    # error[E0433]: failed to resolve
    {
        "fingerprint_pattern": r"error\[E0433\]: failed to resolve",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Rust resolve error - check use statements",
    },

    # error[E0425]: cannot find value
    {
        "fingerprint_pattern": r"error\[E0425\]: cannot find value `(\w+)`",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "Rust cannot find value - check variable declaration",
    },

    # ===================
    # Build/Config Errors
    # ===================

    # pip: No matching distribution
    {
        "fingerprint_pattern": r"ERROR: No matching distribution found for (\S+)",
        "safety_category": "safe",
        "action": {
            "action_type": "multi_step",
            "steps": [
                {"action_type": "command", "command": "pip search {match_1} || echo 'Check PyPI for correct package name'"},
            ],
        },
        "description": "Pip package not found - check package name spelling",
    },

    # npm ERR! 404
    {
        "fingerprint_pattern": r"npm ERR! 404 Not Found.*'(\S+)'",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "npm search {match_1}",
        },
        "description": "NPM package not found - check package name",
    },

    # EADDRINUSE
    {
        "fingerprint_pattern": r"EADDRINUSE.*port (\d+)",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "lsof -i :{match_1} || netstat -tlnp | grep :{match_1}",
        },
        "description": "Port in use - find process using port",
    },

    # Connection refused
    {
        "fingerprint_pattern": r"Connection refused.*:(\d+)",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "curl -v localhost:{match_1} 2>&1 | head -20",
        },
        "description": "Connection refused - check if service is running",
    },

    # Docker: image not found
    {
        "fingerprint_pattern": r"Error response from daemon: manifest for (\S+) not found",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "docker search {match_1} | head -10",
        },
        "description": "Docker image not found - search for correct name",
    },

    # Git: not a git repository
    {
        "fingerprint_pattern": r"fatal: not a git repository",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "git init",
        },
        "description": "Not a git repo - initialize git",
    },

    # ===================
    # TypeScript Errors
    # ===================

    # TS2307: Cannot find module
    {
        "fingerprint_pattern": r"error TS2307: Cannot find module '([^']+)'",
        "safety_category": "safe",
        "action": {
            "action_type": "command",
            "command": "npm install {match_1} @types/{match_1}",
        },
        "description": "TypeScript module not found - install package and types",
    },

    # TS2339: Property does not exist
    {
        "fingerprint_pattern": r"error TS2339: Property '(\w+)' does not exist on type",
        "safety_category": "moderate",
        "action": {
            "action_type": "diff",
            "requires_context": True,
        },
        "description": "TypeScript property error - add property or fix type",
    },
]


def generate_fingerprint(pattern: str) -> str:
    """Generate a stable fingerprint for a pattern.

    Args:
        pattern: The regex pattern string

    Returns:
        16-character hex fingerprint
    """
    return hashlib.sha256(pattern.encode()).hexdigest()[:16]


async def seed_patterns(client: "HealingSupabaseClient") -> int:
    """Seed pre-built patterns into Supabase.

    This function is idempotent - running it multiple times won't duplicate patterns.

    Args:
        client: The HealingSupabaseClient to use

    Returns:
        Number of patterns inserted
    """
    count = 0
    for pattern_def in PRESEEDED_PATTERNS:
        # Generate fingerprint from pattern
        fingerprint = generate_fingerprint(pattern_def["fingerprint_pattern"])

        pattern = {
            "fingerprint": fingerprint,
            "fingerprint_coarse": fingerprint[:8],
            "is_preseeded": True,
            "safety_category": pattern_def["safety_category"],
            "verified_apply_count": 0,
            "human_correction_count": 0,
            "success_count": 0,
            "failure_count": 0,
        }

        await client.record_pattern(pattern)

        # Create associated learning
        learning = {
            "pattern_fingerprint": fingerprint,
            "title": pattern_def.get("description", f"Fix for: {pattern_def['fingerprint_pattern'][:50]}"),
            "action": pattern_def["action"],
            "lifecycle": "active",  # Pre-seeded start as active
            "confidence": 0.8,
        }
        await client.record_learning(learning)
        count += 1

    return count


def match_preseeded(error_message: str) -> dict | None:
    """Find a matching pre-seeded pattern for an error message.

    This is a fast local lookup that doesn't require Supabase.

    Args:
        error_message: The error message to match

    Returns:
        The matching pattern dict, or None
    """
    import re

    for pattern_def in PRESEEDED_PATTERNS:
        match = re.search(pattern_def["fingerprint_pattern"], error_message)
        if match:
            # Add match groups for templating
            result = pattern_def.copy()
            result["match_groups"] = match.groups()
            return result

    return None
