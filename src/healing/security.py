"""Security Scrubber - Phase 2 Pattern Memory & Lookup.

Removes secrets and PII before storing data in Supabase or sending to external APIs.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ErrorEvent


@dataclass
class SecurityScrubber:
    """Remove secrets and PII before storage.

    This scrubber is applied to all text before:
    - Storing patterns in Supabase
    - Sending text for embeddings
    - Recording in audit logs

    The patterns are case-insensitive and cover common secret formats.
    """

    # Patterns as (regex, replacement) tuples
    # Order matters - more specific patterns should come first
    secret_patterns: list[tuple[str, str]] = field(default_factory=lambda: [
        # API keys (various formats)
        (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[\w-]{20,}["\']?', r'\1=<REDACTED>'),
        # Authorization: Bearer header format
        (r'(?i)(Authorization:\s*Bearer)\s+[\w.-]+', r'\1 <REDACTED>'),
        # Bearer tokens (other formats)
        (r'(?i)(bearer|token)\s*[=:]\s*["\']?[\w.-]{20,}["\']?', r'\1=<REDACTED>'),
        # Passwords
        (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']+["\']?', r'\1=<REDACTED>'),
        # AWS access keys (AKIA prefix is standard)
        (r'AKIA[0-9A-Z]{16}', '<AWS_KEY>'),
        # Private keys (PEM format)
        (r'-----BEGIN[\w\s]+PRIVATE KEY-----[\s\S]*?-----END[\w\s]+PRIVATE KEY-----', '<PRIVATE_KEY>'),
        # Connection strings (postgres, mysql, mongodb, redis)
        (r'(?i)(postgres|postgresql|mysql|mongodb|redis)://[^\s]+', r'\1://<REDACTED>'),
        # Email addresses (PII)
        (r'[\w.-]+@[\w.-]+\.\w{2,}', '<EMAIL>'),
        # Generic secrets with common names
        (r'(?i)(secret|credential|auth_token)\s*[=:]\s*["\']?[\w.-]{10,}["\']?', r'\1=<REDACTED>'),
        # GitHub tokens (ghp_, gho_, ghu_, ghs_, ghr_)
        (r'gh[pous]_[A-Za-z0-9_]{36,}', '<GITHUB_TOKEN>'),
        # Slack tokens
        (r'xox[baprs]-[\w-]+', '<SLACK_TOKEN>'),
        # Generic long hex strings (might be secrets)
        (r'(?i)(key|token|secret)\s*[=:]\s*["\']?[a-f0-9]{32,}["\']?', r'\1=<REDACTED>'),
    ])

    def scrub(self, text: str) -> str:
        """Remove secrets and PII from text.

        Args:
            text: Input text that may contain secrets

        Returns:
            Text with secrets replaced by placeholders
        """
        if not text:
            return text

        result = text
        for pattern, replacement in self.secret_patterns:
            result = re.sub(pattern, replacement, result)

        return result

    def scrub_error(self, error: "ErrorEvent") -> "ErrorEvent":
        """Scrub all text fields in an ErrorEvent.

        Creates a new ErrorEvent with scrubbed fields.
        Non-text fields (like error_id, timestamp) are preserved.

        Args:
            error: The ErrorEvent to scrub

        Returns:
            New ErrorEvent with scrubbed text fields
        """
        # Import here to avoid circular imports
        from .models import ErrorEvent

        return ErrorEvent(
            error_id=error.error_id,
            timestamp=error.timestamp,
            source=error.source,
            description=self.scrub(error.description) if error.description else None,
            error_type=error.error_type,
            file_path=error.file_path,
            line_number=error.line_number,
            stack_trace=self.scrub(error.stack_trace) if error.stack_trace else None,
            command=error.command,
            exit_code=error.exit_code,
            fingerprint=error.fingerprint,
            fingerprint_coarse=error.fingerprint_coarse,
            workflow_id=error.workflow_id,
            phase_id=error.phase_id,
            project_id=error.project_id,
        )

    def scrub_dict(self, data: dict, fields: list[str] = None) -> dict:
        """Scrub specified fields in a dictionary.

        Args:
            data: Dictionary that may contain secrets
            fields: List of fields to scrub (defaults to common text fields)

        Returns:
            New dictionary with scrubbed fields
        """
        if fields is None:
            fields = ["description", "stack_trace", "error_message", "message", "content"]

        result = data.copy()
        for field_name in fields:
            if field_name in result and isinstance(result[field_name], str):
                result[field_name] = self.scrub(result[field_name])

        return result
