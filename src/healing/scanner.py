"""Intelligent file scanner for pattern learning.

This module provides automatic discovery and scanning of files that contain
learnable error patterns. It integrates with the healing system to extract
patterns from workflow logs, LEARNINGS.md, and other sources.

Architecture: Session-end hook with incremental scanning (multi-model consensus).
"""

import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .context_extraction import extract_context
from .fingerprint import Fingerprinter
from .models import ErrorEvent

if TYPE_CHECKING:
    from .client import HealingClient

logger = logging.getLogger(__name__)


@dataclass
class ScanState:
    """Tracks what has been scanned to enable incremental processing.

    State is persisted to a JSON file for crash recovery and efficiency.
    """

    last_scan: Optional[str] = None
    file_hashes: dict[str, str] = field(default_factory=dict)
    github_watermark: Optional[str] = None
    ingested_sessions: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "ScanState":
        """Load state from file, returning empty state if not found or invalid."""
        if not path.exists():
            return cls()

        try:
            data = json.loads(path.read_text())
            return cls(
                last_scan=data.get("last_scan"),
                file_hashes=data.get("file_hashes", {}),
                github_watermark=data.get("github_watermark"),
                ingested_sessions=data.get("ingested_sessions", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to load scan state from {path}: {e}")
            return cls()

    def save(self, path: Path) -> None:
        """Save state atomically (write to temp, then rename)."""
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "last_scan": self.last_scan,
            "file_hashes": self.file_hashes,
            "github_watermark": self.github_watermark,
            "ingested_sessions": self.ingested_sessions,
        }

        # Atomic write: write to temp file, then rename
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, indent=2))
        temp_path.rename(path)

    def is_changed(self, file_path: str, new_hash: str) -> bool:
        """Check if a file has changed since last scan."""
        return self.file_hashes.get(file_path) != new_hash

    def is_session_ingested(self, session_id: str) -> bool:
        """Check if a session has already been processed."""
        return session_id in self.ingested_sessions

    def mark_session_ingested(self, session_id: str) -> None:
        """Mark a session as processed."""
        if session_id not in self.ingested_sessions:
            self.ingested_sessions.append(session_id)

    def update_file_hash(self, file_path: str, hash_value: str) -> None:
        """Update the stored hash for a file."""
        self.file_hashes[file_path] = hash_value


@dataclass
class ScanResult:
    """Result of scanning a single source."""

    source: str  # "workflow_log", "learnings_md", "github_issue", etc.
    path: str  # File path or issue URL
    errors_found: int  # Number of errors extracted
    recommendation: str  # Why this source is valuable


@dataclass
class ScanSummary:
    """Summary of a complete scan operation."""

    sources_scanned: int
    errors_extracted: int
    patterns_created: int
    patterns_updated: int  # Existing patterns with incremented count
    results: list[ScanResult] = field(default_factory=list)


class PatternScanner:
    """Intelligent file scanner for pattern learning.

    Scans multiple sources for error patterns:
    - .workflow_log.jsonl (WorkflowLogDetector format)
    - LEARNINGS.md (markdown with error descriptions)
    - .wfo_logs/*.log (parallel agent logs)
    - .orchestrator/sessions/* (session transcripts)
    - GitHub closed issues (via GitHubIssueParser)
    """

    # Default sources to scan
    SOURCES = {
        ".workflow_log.jsonl": {
            "recommendation": "High value - structured error events from workflow execution",
            "parser": "workflow_log",
        },
        "LEARNINGS.md": {
            "recommendation": "High value - documented errors and fixes from sessions",
            "parser": "transcript",
        },
        ".wfo_logs": {
            "recommendation": "Medium value - parallel agent execution logs",
            "parser": "transcript",
            "pattern": "*.log",
        },
    }

    # Error patterns to extract from text
    ERROR_PATTERNS = [
        # Python errors
        r"(\w+Error): (.+)",
        r"(\w+Exception): (.+)",
        r"Traceback \(most recent call last\):",
        # Node.js
        r"Error: (.+)",
        r"Cannot find module '([^']+)'",
        # Rust
        r"error\[E\d+\]: (.+)",
        # Go
        r"panic: (.+)",
        # Generic
        r"FAILED|FATAL|CRITICAL",
    ]

    def __init__(
        self,
        state_path: Path,
        project_root: Path,
        healing_client: Optional["HealingClient"] = None,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB default
    ):
        """Initialize the scanner.

        Args:
            state_path: Path to the scan state JSON file
            project_root: Root directory of the project to scan
            healing_client: Optional healing client for recording patterns
            max_file_size: Maximum file size to scan (bytes)
        """
        self.state_path = state_path
        self.project_root = project_root
        self.healing_client = healing_client
        self.max_file_size = max_file_size
        self._state: Optional[ScanState] = None
        self.fingerprinter = Fingerprinter()

    @property
    def state(self) -> ScanState:
        """Lazy-load scan state."""
        if self._state is None:
            self._state = ScanState.load(self.state_path)
        return self._state

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content (first 16 chars)."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _is_file_recent(self, path: Path, days: int) -> bool:
        """Check if file was modified within the last N days."""
        try:
            mtime = path.stat().st_mtime
            cutoff = time.time() - (days * 24 * 60 * 60)
            return mtime >= cutoff
        except OSError:
            return False

    def _get_scannable_files(self, days: int = 30) -> list[Path]:
        """Get list of files that should be scanned."""
        files = []

        for source_name, config in self.SOURCES.items():
            source_path = self.project_root / source_name

            if source_path.is_file():
                if self._is_file_recent(source_path, days):
                    files.append(source_path)
            elif source_path.is_dir():
                pattern = config.get("pattern", "*")
                for child in source_path.glob(pattern):
                    if child.is_file() and self._is_file_recent(child, days):
                        files.append(child)

        # Also check orchestrator sessions
        sessions_dir = self.project_root / ".orchestrator" / "sessions"
        if sessions_dir.exists():
            for session_dir in sessions_dir.iterdir():
                if session_dir.is_dir():
                    log_file = session_dir / "log.jsonl"
                    if log_file.exists() and self._is_file_recent(log_file, days):
                        files.append(log_file)

        return files

    def _extract_errors_from_text(self, text: str, source: str) -> list[ErrorEvent]:
        """Extract error patterns from text content."""
        errors = []
        seen_fingerprints = set()

        for pattern in self.ERROR_PATTERNS:
            for match in re.finditer(pattern, text, re.MULTILINE):
                error_text = match.group(0)

                # Skip if too short
                if len(error_text) < 10:
                    continue

                # Extract error type and message
                error_type = None
                description = error_text

                # Try to parse specific error types
                type_match = re.match(r"(\w+(?:Error|Exception)):\s*(.+)", error_text)
                if type_match:
                    error_type = type_match.group(1)
                    description = error_text

                # Extract context from surrounding text
                context = extract_context(
                    description=description,
                    error_type=error_type,
                )

                # Create error event
                # Source must be one of: workflow_log, transcript, subprocess, hook
                source_type = "transcript"  # Default for text extraction
                if ".workflow_log" in source:
                    source_type = "workflow_log"

                error = ErrorEvent(
                    error_id=str(uuid.uuid4()),
                    timestamp=datetime.now(),
                    source=source_type,
                    error_type=error_type,
                    description=description,
                    context=context,
                )

                # Generate fingerprint
                error.fingerprint = self.fingerprinter.fingerprint(error)
                error.fingerprint_coarse = self.fingerprinter.fingerprint_coarse(error)

                # Deduplicate within this scan
                if error.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(error.fingerprint)
                    errors.append(error)

        return errors

    def _extract_errors_from_jsonl(self, path: Path) -> list[ErrorEvent]:
        """Extract errors from JSONL workflow log format."""
        errors = []
        seen_fingerprints = set()

        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Look for error events
                    event_type = entry.get("event", "")
                    if event_type not in ("error", "failure", "exception"):
                        # Also check description for error patterns
                        desc = entry.get("description", "")
                        if not any(re.search(p, desc) for p in self.ERROR_PATTERNS):
                            continue

                    description = entry.get("description", entry.get("message", ""))
                    if not description:
                        continue

                    error_type = entry.get("error_type")
                    stack_trace = entry.get("stack_trace")

                    context = extract_context(
                        description=description,
                        error_type=error_type,
                        stack_trace=stack_trace,
                    )

                    # Parse timestamp from entry or use now
                    try:
                        ts = entry.get("timestamp")
                        if ts:
                            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            timestamp = timestamp.replace(tzinfo=None)  # Make naive
                        else:
                            timestamp = datetime.now()
                    except (ValueError, TypeError):
                        timestamp = datetime.now()

                    error = ErrorEvent(
                        error_id=str(uuid.uuid4()),
                        timestamp=timestamp,
                        source="workflow_log",
                        error_type=error_type,
                        description=description,
                        stack_trace=stack_trace,
                        context=context,
                    )

                    error.fingerprint = self.fingerprinter.fingerprint(error)
                    error.fingerprint_coarse = self.fingerprinter.fingerprint_coarse(error)

                    if error.fingerprint not in seen_fingerprints:
                        seen_fingerprints.add(error.fingerprint)
                        errors.append(error)

        except Exception as e:
            logger.warning(f"Failed to parse JSONL file {path}: {e}")

        return errors

    def _scan_file(self, path: Path) -> list[ErrorEvent]:
        """Scan a single file for error patterns."""
        # Check file size
        try:
            if path.stat().st_size > self.max_file_size:
                logger.info(f"Skipping large file: {path} (>{self.max_file_size} bytes)")
                return []
        except OSError:
            return []

        # Check if file has changed
        try:
            content = path.read_text()
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return []

        file_hash = self._compute_hash(content)
        file_key = str(path)

        if not self.state.is_changed(file_key, file_hash):
            logger.debug(f"Skipping unchanged file: {path}")
            return []

        # Parse based on file type
        if path.suffix == ".jsonl":
            errors = self._extract_errors_from_jsonl(path)
        else:
            errors = self._extract_errors_from_text(content, str(path))

        # Update hash after successful scan
        self.state.update_file_hash(file_key, file_hash)

        return errors

    def get_recommendations(self) -> list[dict[str, Any]]:
        """Get recommendations for scannable sources without scanning."""
        recommendations = []

        for source_name, config in self.SOURCES.items():
            source_path = self.project_root / source_name

            if source_path.is_file():
                recommendations.append({
                    "source": source_name,
                    "path": str(source_path),
                    "recommendation": config["recommendation"],
                    "exists": True,
                })
            elif source_path.is_dir():
                pattern = config.get("pattern", "*")
                files = list(source_path.glob(pattern))
                if files:
                    recommendations.append({
                        "source": source_name,
                        "path": str(source_path),
                        "recommendation": config["recommendation"],
                        "exists": True,
                        "file_count": len(files),
                    })

        # Check for LEARNINGS.md specifically
        learnings = self.project_root / "LEARNINGS.md"
        if learnings.exists() and "LEARNINGS.md" not in [r["source"] for r in recommendations]:
            recommendations.append({
                "source": "LEARNINGS.md",
                "path": str(learnings),
                "recommendation": "High value - documented errors and fixes from sessions",
                "exists": True,
            })

        return recommendations

    async def scan_all(self, days: int = 30) -> ScanSummary:
        """Scan all sources for error patterns.

        Args:
            days: Only scan files modified in the last N days

        Returns:
            ScanSummary with statistics about the scan
        """
        summary = ScanSummary(
            sources_scanned=0,
            errors_extracted=0,
            patterns_created=0,
            patterns_updated=0,
        )

        files = self._get_scannable_files(days=days)

        for file_path in files:
            errors = self._scan_file(file_path)

            if errors:
                source_name = file_path.name
                for source, config in self.SOURCES.items():
                    if source in str(file_path):
                        source_name = source
                        break

                result = ScanResult(
                    source=source_name,
                    path=str(file_path),
                    errors_found=len(errors),
                    recommendation=self.SOURCES.get(source_name, {}).get(
                        "recommendation", "Contains error patterns"
                    ),
                )
                summary.results.append(result)
                summary.sources_scanned += 1
                summary.errors_extracted += len(errors)

                # Record patterns via healing client
                if self.healing_client:
                    for error in errors:
                        try:
                            await self.healing_client.supabase.record_historical_error(error)
                            summary.patterns_created += 1
                        except Exception as e:
                            logger.warning(f"Failed to record error pattern: {e}")

        # Update last scan timestamp
        self.state.last_scan = datetime.now().isoformat()
        self.state.save(self.state_path)

        return summary

    def has_orphaned_session(self) -> bool:
        """Check if there's an incomplete session that needs recovery."""
        # Check for sessions not in ingested list
        sessions_dir = self.project_root / ".orchestrator" / "sessions"
        if not sessions_dir.exists():
            return False

        for session_dir in sessions_dir.iterdir():
            if session_dir.is_dir():
                session_id = session_dir.name
                if not self.state.is_session_ingested(session_id):
                    # Check if session has logs
                    if (session_dir / "log.jsonl").exists():
                        return True

        return False

    async def recover_orphaned(self) -> ScanSummary:
        """Recover and ingest logs from orphaned sessions."""
        summary = ScanSummary(
            sources_scanned=0,
            errors_extracted=0,
            patterns_created=0,
            patterns_updated=0,
        )

        sessions_dir = self.project_root / ".orchestrator" / "sessions"
        if not sessions_dir.exists():
            return summary

        for session_dir in sessions_dir.iterdir():
            if session_dir.is_dir():
                session_id = session_dir.name
                if not self.state.is_session_ingested(session_id):
                    log_file = session_dir / "log.jsonl"
                    if log_file.exists():
                        errors = self._scan_file(log_file)
                        if errors:
                            summary.sources_scanned += 1
                            summary.errors_extracted += len(errors)

                            if self.healing_client:
                                for error in errors:
                                    try:
                                        await self.healing_client.supabase.record_historical_error(
                                            error
                                        )
                                        summary.patterns_created += 1
                                    except Exception as e:
                                        logger.warning(f"Failed to record error: {e}")

                        self.state.mark_session_ingested(session_id)

        self.state.save(self.state_path)
        return summary
