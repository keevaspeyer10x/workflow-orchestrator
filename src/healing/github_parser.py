"""GitHub issue parser for pattern learning.

This module fetches closed issues from GitHub and extracts error patterns
from their bodies. Uses the gh CLI for API access.
"""

import json
import logging
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .context_extraction import extract_context
from .fingerprint import Fingerprinter
from .models import ErrorEvent

logger = logging.getLogger(__name__)


@dataclass
class GitHubIssueParser:
    """Parser for extracting error patterns from GitHub issues.

    Uses the gh CLI to fetch closed issues and extracts error patterns
    from their bodies.
    """

    # Labels that indicate bug/error issues
    BUG_LABELS = ["bug", "error", "fix", "crash", "exception", "failure"]

    # Error patterns to extract from issue bodies
    ERROR_PATTERNS = [
        # Python errors with traceback
        r"Traceback \(most recent call last\):[\s\S]*?(?:\w+(?:Error|Exception)): .+",
        # Python errors standalone
        r"(\w+Error): (.+)",
        r"(\w+Exception): (.+)",
        # Node.js errors
        r"Error: (.+)",
        r"Cannot find module '([^']+)'",
        r"at .+ \([^)]+:\d+:\d+\)",
        # Rust errors
        r"error\[E\d+\]: .+",
        r"error: .+",
        # Go errors
        r"panic: .+",
        r"fatal error: .+",
        # Generic patterns
        r"FAILED|FATAL|CRITICAL|ERROR",
    ]

    def __init__(self):
        """Initialize the parser."""
        self.fingerprinter = Fingerprinter()

    def _is_gh_available(self) -> bool:
        """Check if gh CLI is installed and available."""
        return shutil.which("gh") is not None

    def fetch_closed_issues(
        self,
        labels: Optional[list[str]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch closed issues from GitHub using gh CLI.

        Args:
            labels: Filter by these labels (default: bug-related labels)
            since: Only fetch issues closed after this date
            limit: Maximum number of issues to fetch

        Returns:
            List of issue dictionaries
        """
        if not self._is_gh_available():
            logger.warning("gh CLI not available, skipping GitHub issue fetch")
            return []

        labels = labels or self.BUG_LABELS

        try:
            # Build gh command
            cmd = [
                "gh",
                "issue",
                "list",
                "--state",
                "closed",
                "--json",
                "number,title,body,labels,closedAt,state",
                "--limit",
                str(limit),
            ]

            # Add label filter
            for label in labels:
                cmd.extend(["--label", label])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning(f"gh CLI failed: {result.stderr}")
                return []

            try:
                issues = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse gh output: {e}")
                return []

            # Filter by date if specified
            if since:
                issues = self._filter_by_date(issues, since)

            return issues

        except subprocess.TimeoutExpired:
            logger.warning("gh CLI timed out")
            return []
        except subprocess.CalledProcessError as e:
            logger.warning(f"gh CLI error: {e}")
            return []
        except Exception as e:
            logger.warning(f"Failed to fetch GitHub issues: {e}")
            return []

    def _filter_by_date(
        self, issues: list[dict[str, Any]], since: datetime
    ) -> list[dict[str, Any]]:
        """Filter issues to only those closed after the given date."""
        filtered = []
        for issue in issues:
            closed_at = issue.get("closedAt")
            if closed_at:
                try:
                    # Parse ISO timestamp
                    closed_date = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                    if closed_date.replace(tzinfo=None) >= since:
                        filtered.append(issue)
                except (ValueError, TypeError):
                    # Include issue if we can't parse the date
                    filtered.append(issue)
        return filtered

    def extract_errors(self, issue: dict[str, Any]) -> list[ErrorEvent]:
        """Extract error patterns from an issue body.

        Args:
            issue: Issue dictionary with title, body, etc.

        Returns:
            List of ErrorEvent objects extracted from the issue
        """
        body = issue.get("body")
        if not body:
            return []

        errors = []
        seen_fingerprints = set()
        issue_url = f"https://github.com/issues/{issue.get('number', 'unknown')}"

        for pattern in self.ERROR_PATTERNS:
            for match in re.finditer(pattern, body, re.MULTILINE | re.IGNORECASE):
                error_text = match.group(0)

                # Skip very short matches
                if len(error_text) < 10:
                    continue

                # Skip generic patterns that matched non-error text
                if error_text.upper() in ("FAILED", "FATAL", "CRITICAL", "ERROR"):
                    # Check surrounding context
                    start = max(0, match.start() - 50)
                    end = min(len(body), match.end() + 50)
                    context_text = body[start:end]
                    if not any(
                        indicator in context_text.lower()
                        for indicator in ("error", "exception", "failed", "crash")
                    ):
                        continue

                # Extract error type
                error_type = None
                description = error_text

                # Try to parse specific error types
                type_match = re.match(r"(\w+(?:Error|Exception)):\s*(.+)", error_text)
                if type_match:
                    error_type = type_match.group(1)

                # Extract stack trace if present
                stack_trace = None
                if "Traceback" in error_text:
                    stack_trace = error_text

                # Extract context
                context = extract_context(
                    description=description,
                    error_type=error_type,
                    stack_trace=stack_trace,
                )

                # Parse timestamp
                try:
                    closed_at = issue.get("closedAt")
                    if closed_at:
                        timestamp = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                        timestamp = timestamp.replace(tzinfo=None)  # Make naive
                    else:
                        timestamp = datetime.now()
                except (ValueError, TypeError):
                    timestamp = datetime.now()

                # Create error event
                # Source must be one of: workflow_log, transcript, subprocess, hook
                error = ErrorEvent(
                    error_id=str(uuid.uuid4()),
                    timestamp=timestamp,
                    source="transcript",  # GitHub issues are like transcript text
                    error_type=error_type,
                    description=description,
                    stack_trace=stack_trace,
                    context=context,
                )

                # Generate fingerprint
                error.fingerprint = self.fingerprinter.fingerprint(error)
                error.fingerprint_coarse = self.fingerprinter.fingerprint_coarse(error)

                # Deduplicate
                if error.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(error.fingerprint)
                    errors.append(error)

        return errors

    def has_bug_label(self, issue: dict[str, Any]) -> bool:
        """Check if an issue has a bug-related label."""
        labels = issue.get("labels", [])
        label_names = [
            label.get("name", "").lower() if isinstance(label, dict) else str(label).lower()
            for label in labels
        ]
        return any(bug_label in label_names for bug_label in self.BUG_LABELS)
