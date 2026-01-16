"""
Audit Logging System for v3 Hybrid Orchestration.

Provides tamper-evident audit logging with chained hashes.

Features:
- Secure audit logging with chained hashes
- Log operations: checkpoint create/restore, mode changes, workflow state changes
- Tamper detection via hash chain verification
- Path sanitization to prevent sensitive data leakage
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class AuditTamperError(Exception):
    """Raised when audit log tampering is detected."""
    pass


@dataclass
class AuditEntry:
    """A single audit log entry."""
    timestamp: str
    event: str
    hash: str
    prev_hash: Optional[str] = None
    data: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class AuditLogger:
    """
    Tamper-evident audit logging with chained hashes.

    Each log entry includes a hash computed from its content and the
    previous entry's hash, creating a chain that can be verified.
    """

    # Patterns to sanitize from logs
    SENSITIVE_PATTERNS = [
        '.secrets', '.ssh', '.gnupg', 'credential', 'password',
        'api_key', 'token', '.env'
    ]

    def __init__(self, log_dir: Path):
        """
        Initialize audit logger.

        Args:
            log_dir: Directory to store audit logs
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "audit.jsonl"
        self._last_hash: Optional[str] = None

        # Load last hash if log exists
        if self.log_file.exists():
            self._load_last_hash()

    def _load_last_hash(self) -> None:
        """Load the hash of the last entry for chain continuation.

        Uses seek-from-end approach to avoid reading entire file into memory.
        This prevents DoS attacks via large audit log files.
        """
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, 'rb') as f:
                # Seek to end to get file size
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return

                # Read only the last chunk (4KB should be more than enough for one JSON line)
                chunk_size = min(4096, size)
                f.seek(-chunk_size, 2)
                chunk = f.read()

                # Find last complete line by splitting on newlines
                lines = chunk.split(b'\n')
                for line in reversed(lines):
                    line = line.strip()
                    if line:
                        try:
                            last_entry = json.loads(line.decode('utf-8'))
                            self._last_hash = last_entry.get('hash')
                            return
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
        except Exception as e:
            logger.warning(f"Could not load last audit hash: {e}")

    def _compute_hash(self, content: str, prev_hash: Optional[str] = None) -> str:
        """Compute hash for entry including previous hash.

        Uses SHA-256 with 32-char truncation (128 bits) for tamper-evident logging.
        This provides sufficient collision resistance for audit trail integrity.
        """
        to_hash = content
        if prev_hash:
            to_hash = f"{prev_hash}:{content}"
        return hashlib.sha256(to_hash.encode()).hexdigest()[:32]

    def _sanitize_path(self, path: str) -> str:
        """Sanitize sensitive paths from logs."""
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in path.lower():
                return "[REDACTED]"
        return path

    def _sanitize_data(self, data: dict) -> dict:
        """Sanitize sensitive data from log entries."""
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                # Sanitize path-like strings
                if '/' in value or '\\' in value:
                    sanitized[key] = self._sanitize_path(value)
                else:
                    sanitized[key] = value
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_data(value)
            else:
                sanitized[key] = value
        return sanitized

    def log_event(self, event: str, **data) -> None:
        """
        Log an audit event.

        Args:
            event: Event type (e.g., 'checkpoint_create', 'mode_change')
            **data: Additional event data
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Sanitize data
        sanitized_data = self._sanitize_data(data) if data else None

        # Create entry content for hashing
        content = json.dumps({
            'timestamp': timestamp,
            'event': event,
            'data': sanitized_data
        }, sort_keys=True)

        # Compute chained hash
        entry_hash = self._compute_hash(content, self._last_hash)

        # Create entry
        entry = AuditEntry(
            timestamp=timestamp,
            event=event,
            hash=entry_hash,
            prev_hash=self._last_hash,
            data=sanitized_data
        )

        # Write to log
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(entry.to_dict()) + '\n')

        # Update last hash
        self._last_hash = entry_hash

    def log_checkpoint_create(self, checkpoint_id: str, workflow_id: str, phase_id: str) -> None:
        """Log checkpoint creation."""
        self.log_event(
            'checkpoint_create',
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id,
            phase_id=phase_id
        )

    def log_checkpoint_restore(self, checkpoint_id: str, workflow_id: str) -> None:
        """Log checkpoint restore."""
        self.log_event(
            'checkpoint_restore',
            checkpoint_id=checkpoint_id,
            workflow_id=workflow_id
        )

    def log_mode_change(self, old_mode: str, new_mode: str, reason: str) -> None:
        """Log mode change."""
        self.log_event(
            'mode_change',
            old_mode=old_mode,
            new_mode=new_mode,
            reason=reason
        )

    def log_workflow_state_change(self, workflow_id: str, phase_id: str, item_id: Optional[str] = None) -> None:
        """Log workflow state change."""
        self.log_event(
            'workflow_state_change',
            workflow_id=workflow_id,
            phase_id=phase_id,
            item_id=item_id
        )

    def verify_integrity(self) -> bool:
        """
        Verify audit log integrity by checking hash chain.

        Returns:
            True if log is intact, raises AuditTamperError otherwise
        """
        if not self.log_file.exists():
            return True

        prev_hash = None

        with open(self.log_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    raise AuditTamperError(f"Line {line_num}: Invalid JSON - {e}")

                # Verify previous hash matches
                if entry.get('prev_hash') != prev_hash:
                    raise AuditTamperError(
                        f"Line {line_num}: Previous hash mismatch. "
                        f"Expected {prev_hash}, got {entry.get('prev_hash')}"
                    )

                # Recompute hash and verify
                content = json.dumps({
                    'timestamp': entry['timestamp'],
                    'event': entry['event'],
                    'data': entry.get('data')
                }, sort_keys=True)

                expected_hash = self._compute_hash(content, prev_hash)
                # Use hmac.compare_digest for constant-time comparison (prevents timing attacks)
                if not hmac.compare_digest(entry['hash'], expected_hash):
                    raise AuditTamperError(
                        f"Line {line_num}: Hash mismatch. "
                        f"Expected {expected_hash}, got {entry['hash']}"
                    )

                prev_hash = entry['hash']

        return True
