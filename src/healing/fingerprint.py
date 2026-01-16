"""Fingerprinting for error deduplication.

This module generates stable fingerprints for error events,
enabling deduplication across different occurrences of the same error.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .models import ErrorEvent


@dataclass
class FingerprintConfig:
    """Normalization rules for fingerprinting."""

    strip_patterns: List[Tuple[str, str]] = field(
        default_factory=lambda: [
            # File paths: /home/user/project/foo.py -> <path>/foo.py
            (r"/[\w/.-]+/([^/]+\.\w+)", r"<path>/\1"),
            # Line numbers: foo.py:123 -> foo.py:<line>
            (r"(\.\w+):(\d+)", r"\1:<line>"),
            # UUIDs
            (
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                "<uuid>",
            ),
            # Timestamps (ISO format and space-separated)
            (r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[Z\d:+-]*", "<timestamp>"),
            # Memory addresses
            (r"0x[0-9a-fA-F]+", "<addr>"),
            # PIDs
            (r"pid[=:]\s*\d+", "pid=<pid>"),
            # Temp paths
            (r"/tmp/[\w.-]+/", "<tmpdir>/"),
            # Long strings in quotes (20+ chars)
            (r'"[^"]{20,}"', '"<string>"'),
        ]
    )


class Fingerprinter:
    """Generate stable fingerprints for error deduplication.

    Fingerprints are designed to be stable across:
    - Different timestamps
    - Different machine paths
    - Different line numbers (for the same error type)
    - Different PIDs, memory addresses, etc.
    """

    def __init__(self, config: Optional[FingerprintConfig] = None):
        """Initialize fingerprinter with optional config.

        Args:
            config: Normalization rules. Uses defaults if not provided.
        """
        self.config = config or FingerprintConfig()

    def fingerprint(self, error: ErrorEvent) -> str:
        """Generate fine-grained fingerprint (16 hex chars).

        Components:
        - Error type
        - Normalized message (first 200 chars)
        - Top stack frame (if available)

        Args:
            error: The error event to fingerprint.

        Returns:
            16-character hex fingerprint.
        """
        components = []

        # Error type
        error_type = self._extract_error_type(error.error_type or error.description)
        components.append(f"type:{error_type}")

        # Normalized message
        normalized = self._normalize(error.description or "")
        components.append(f"msg:{normalized[:200]}")

        # Top stack frame
        if error.stack_trace:
            top_frame = self._extract_top_frame(error.stack_trace)
            if top_frame:
                components.append(f"frame:{top_frame}")

        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def fingerprint_coarse(self, error: ErrorEvent) -> str:
        """Generate coarse fingerprint for broad grouping (8 hex chars).

        Only uses error type for grouping similar errors.

        Args:
            error: The error event to fingerprint.

        Returns:
            8-character hex fingerprint.
        """
        error_type = self._extract_error_type(error.error_type or error.description)
        return hashlib.sha256(f"coarse:{error_type}".encode()).hexdigest()[:8]

    def _normalize(self, text: str) -> str:
        """Apply normalization patterns to text.

        Args:
            text: Text to normalize.

        Returns:
            Normalized text with variable parts replaced.
        """
        result = text
        for pattern, replacement in self.config.strip_patterns:
            result = re.sub(pattern, replacement, result)
        return result.strip()

    def _extract_error_type(self, text: str) -> str:
        """Extract error type from error text.

        Supports:
        - Python: TypeError, ValueError, etc.
        - Node.js: Error
        - Rust: error[E0001]
        - Go: panic

        Args:
            text: Error text to parse.

        Returns:
            Extracted error type or "UnknownError".
        """
        # Python errors: TypeError, ValueError, ImportError, etc.
        match = re.match(r"^(\w+Error|\w+Exception|\w+Warning):", text)
        if match:
            return match.group(1)

        # Node.js
        if text.startswith("Error:"):
            return "Error"

        # Rust errors: error[E0382]
        match = re.match(r"error\[(E\d+)\]", text)
        if match:
            return f"RustError_{match.group(1)}"

        # Go panic
        if text.startswith("panic:"):
            return "GoPanic"

        return "UnknownError"

    def _extract_top_frame(self, stack_trace: str) -> Optional[str]:
        """Extract top stack frame from trace.

        Supports:
        - Python: File "foo.py", line 10, in main
        - Node.js: at foo (/path/bar.js:10:5)

        Args:
            stack_trace: Full stack trace.

        Returns:
            Normalized frame string (filename:function) or None.
        """
        # Python format: File "foo.py", line 10, in main
        match = re.search(r'File "([^"]+)", line \d+, in (\w+)', stack_trace)
        if match:
            filename = match.group(1).split("/")[-1]
            function = match.group(2)
            return f"{filename}:{function}"

        # Node.js format: at foo (/path/bar.js:10:5)
        match = re.search(r"at (\w+) \(([^)]+)\)", stack_trace)
        if match:
            function = match.group(1)
            filename = match.group(2).split("/")[-1].split(":")[0]
            return f"{filename}:{function}"

        return None
