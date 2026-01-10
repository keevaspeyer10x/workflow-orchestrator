"""
Session Transcript Logging with Secret Scrubbing.

CORE-024: Provides session transcript logging with automatic secret scrubbing
to enable debugging and pattern analysis without exposing sensitive data.

Features:
- Known-secret replacement via SecretsManager integration
- Pattern-based scrubbing for common API key formats
- Configurable custom patterns
- Session listing, retrieval, and cleanup
- Configurable retention policy
"""

import re
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Default session directory name (in working directory)
SESSIONS_DIR_NAME = ".workflow_sessions"

# Default retention period in days
DEFAULT_RETENTION_DAYS = 30

# Default scrubbing patterns for common API key formats
# Format: (regex_pattern, replacement_label)
DEFAULT_SCRUB_PATTERNS: List[Tuple[str, str]] = [
    # OpenAI API keys (sk-... or sk-proj-...)
    (r"sk-[a-zA-Z0-9_-]{20,}", "[REDACTED:OPENAI_KEY]"),

    # GitHub tokens (ghp_... for personal access tokens)
    (r"ghp_[a-zA-Z0-9]{36,}", "[REDACTED:GITHUB_TOKEN]"),

    # GitHub tokens (gho_, ghu_, ghs_, ghr_ for other token types)
    (r"gh[ours]_[a-zA-Z0-9]{36,}", "[REDACTED:GITHUB_TOKEN]"),

    # xAI API keys (xai-...)
    (r"xai-[a-zA-Z0-9_-]{20,}", "[REDACTED:XAI_KEY]"),

    # Stripe API keys (pk_live_..., sk_live_..., pk_test_..., sk_test_...)
    (r"[ps]k_(live|test)_[a-zA-Z0-9]{20,}", "[REDACTED:STRIPE_KEY]"),

    # Bearer tokens in Authorization headers
    (r"Bearer\s+[a-zA-Z0-9_.-]{20,}", "[REDACTED:BEARER_TOKEN]"),

    # OpenRouter API keys
    (r"sk-or-v1-[a-zA-Z0-9]{64}", "[REDACTED:OPENROUTER_KEY]"),

    # Anthropic API keys
    (r"sk-ant-[a-zA-Z0-9_-]{40,}", "[REDACTED:ANTHROPIC_KEY]"),

    # Google/Gemini API keys (AIza...)
    (r"AIza[a-zA-Z0-9_-]{35,}", "[REDACTED:GOOGLE_KEY]"),

    # AWS access keys
    (r"AKIA[A-Z0-9]{16}", "[REDACTED:AWS_ACCESS_KEY]"),

    # Generic long alphanumeric tokens (potential secrets)
    # This is intentionally last and more conservative
    (r"(?<![a-zA-Z0-9])[a-f0-9]{40}(?![a-zA-Z0-9])", "[REDACTED:HEX_TOKEN]"),
]


class TranscriptLogger:
    """
    Session transcript logger with automatic secret scrubbing.

    Logs session transcripts to .workflow_sessions/ directory with
    all secrets automatically scrubbed using:
    1. Known-secret replacement (from SecretsManager)
    2. Pattern-based scrubbing for common API key formats
    3. Configurable custom patterns

    Usage:
        from src.secrets import get_secrets_manager
        from src.transcript_logger import TranscriptLogger

        secrets_manager = get_secrets_manager()
        logger = TranscriptLogger(secrets_manager=secrets_manager)

        logger.log("session-123", "User said something with sk-abc123...")

        sessions = logger.list_sessions()
        content = logger.get_session("session-123")

        logger.clean(older_than_days=30)
    """

    def __init__(
        self,
        secrets_manager=None,
        sessions_dir: Optional[Path] = None,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        custom_patterns: Optional[List[Tuple[str, str]]] = None,
    ):
        """
        Initialize the transcript logger.

        Args:
            secrets_manager: SecretsManager instance for known-secret lookup.
                            If None, only pattern-based scrubbing is used.
            sessions_dir: Directory to store session logs.
                         Defaults to .workflow_sessions/ in current directory.
            retention_days: Number of days to keep sessions. Default 30.
            custom_patterns: Additional (regex, replacement) patterns to use.
        """
        self._secrets_manager = secrets_manager
        self._sessions_dir = sessions_dir or Path.cwd() / SESSIONS_DIR_NAME
        self._retention_days = retention_days

        # Build pattern list: default + custom
        self._patterns = list(DEFAULT_SCRUB_PATTERNS)
        if custom_patterns:
            self._patterns.extend(custom_patterns)

        # Compile patterns for efficiency
        self._compiled_patterns = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self._patterns
        ]

        # Cache for known secrets (refreshed on each scrub call)
        self._known_secrets: Dict[str, str] = {}

        # Track session files for append mode
        self._session_files: Dict[str, Path] = {}

    def _load_known_secrets(self) -> Dict[str, str]:
        """Load known secrets from the secrets manager."""
        if self._secrets_manager is None:
            return {}

        try:
            # Use the get_all_known_secrets method if available
            if hasattr(self._secrets_manager, 'get_all_known_secrets'):
                return self._secrets_manager.get_all_known_secrets()

            # Fallback: manually check common secret names
            secrets = {}
            common_names = [
                'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY',
                'GEMINI_API_KEY', 'XAI_API_KEY', 'GITHUB_TOKEN',
                'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
            ]
            for name in common_names:
                value = self._secrets_manager.get_secret(name)
                if value:
                    secrets[name] = value
            return secrets
        except Exception as e:
            logger.warning(f"Failed to load known secrets: {e}")
            return {}

    def scrub(self, text: str) -> str:
        """
        Scrub secrets from text.

        Applies two layers of scrubbing:
        1. Known-secret replacement: Exact matches from SecretsManager
        2. Pattern-based scrubbing: Regex patterns for common formats

        Args:
            text: Text to scrub

        Returns:
            Text with secrets replaced by [REDACTED:...] placeholders
        """
        if not text:
            return text

        # Refresh known secrets
        self._known_secrets = self._load_known_secrets()

        # Layer 1: Known-secret replacement (highest priority)
        # Sort by length descending to avoid partial replacements
        for name, value in sorted(
            self._known_secrets.items(),
            key=lambda x: len(x[1]),
            reverse=True
        ):
            if value and len(value) > 4:  # Avoid replacing very short strings
                text = text.replace(value, f"[REDACTED:{name}]")

        # Layer 2: Pattern-based scrubbing
        for pattern, replacement in self._compiled_patterns:
            text = pattern.sub(replacement, text)

        return text

    def _ensure_sessions_dir(self) -> None:
        """Ensure the sessions directory exists."""
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_file_path(self, session_id: str) -> Path:
        """Get the file path for a session."""
        # Check if we already have a file for this session
        if session_id in self._session_files:
            return self._session_files[session_id]

        # Look for existing file
        for f in self._sessions_dir.glob(f"*_{session_id}.jsonl"):
            self._session_files[session_id] = f
            return f

        # Create new file with date prefix
        date_prefix = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_path = self._sessions_dir / f"{date_prefix}_{session_id}.jsonl"
        self._session_files[session_id] = file_path
        return file_path

    def log(self, session_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Log content to a session transcript.

        Content is automatically scrubbed before writing.
        Multiple calls with the same session_id append to the same file.

        Args:
            session_id: Unique identifier for the session
            content: Content to log (will be scrubbed)
            metadata: Optional metadata to include with the log entry
        """
        self._ensure_sessions_dir()

        # Scrub the content
        scrubbed_content = self.scrub(content)

        # Build log entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "content": scrubbed_content,
        }
        if metadata:
            entry["metadata"] = metadata

        # Append to session file
        file_path = self._get_session_file_path(session_id)
        with open(file_path, 'a') as f:
            f.write(json.dumps(entry) + "\n")

        logger.debug(f"Logged to session {session_id}: {len(scrubbed_content)} chars")

    def list_sessions(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List recent sessions.

        Args:
            limit: Maximum number of sessions to return. None for all.

        Returns:
            List of session info dicts, sorted by date (newest first).
            Each dict contains: session_id, file_path, date, size_bytes
        """
        if not self._sessions_dir.exists():
            return []

        sessions = []
        for f in self._sessions_dir.glob("*.jsonl"):
            # Extract session ID from filename (format: DATE_SESSION-ID.jsonl)
            name = f.stem
            parts = name.split("_", 3)  # Split on first 3 underscores (date_time_session)

            if len(parts) >= 4:
                session_id = parts[3]
                date_str = f"{parts[0]}_{parts[1]}_{parts[2]}"
            elif len(parts) >= 2:
                session_id = parts[-1]
                date_str = parts[0]
            else:
                session_id = name
                date_str = "unknown"

            sessions.append({
                "session_id": session_id,
                "file_path": str(f),
                "date": date_str,
                "size_bytes": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime),
            })

        # Sort by modified time, newest first
        sessions.sort(key=lambda x: x["modified"], reverse=True)

        if limit:
            sessions = sessions[:limit]

        return sessions

    def get_session(self, session_id: str) -> Optional[str]:
        """
        Get the content of a session.

        Args:
            session_id: Session identifier to retrieve

        Returns:
            Session content as a formatted string, or None if not found
        """
        if not self._sessions_dir.exists():
            return None

        # Find the session file
        matches = list(self._sessions_dir.glob(f"*_{session_id}.jsonl"))
        if not matches:
            # Try exact match
            matches = list(self._sessions_dir.glob(f"{session_id}.jsonl"))

        if not matches:
            return None

        # Read and format the content
        file_path = matches[0]
        lines = []

        with open(file_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    timestamp = entry.get("timestamp", "")
                    content = entry.get("content", "")
                    lines.append(f"[{timestamp}] {content}")
                except json.JSONDecodeError:
                    lines.append(line.strip())

        return "\n".join(lines)

    def clean(self, older_than_days: Optional[int] = None) -> int:
        """
        Clean old sessions.

        Args:
            older_than_days: Remove sessions older than this.
                            Defaults to retention_days from init.

        Returns:
            Number of sessions removed
        """
        if not self._sessions_dir.exists():
            return 0

        days = older_than_days if older_than_days is not None else self._retention_days
        cutoff = datetime.now() - timedelta(days=days)

        removed = 0
        for f in self._sessions_dir.glob("*.jsonl"):
            # Try to parse date from filename first (format: YYYY-MM-DD_...)
            # This is more accurate than relying on filesystem mtime
            try:
                name = f.stem
                # Extract date portion (first part before underscore)
                parts = name.split("_")
                if len(parts) >= 1:
                    date_str = parts[0]
                    # Try parsing as YYYY-MM-DD
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    should_remove = file_date < cutoff
                else:
                    # Fall back to mtime if can't parse filename
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    should_remove = mtime < cutoff
            except (ValueError, IndexError):
                # If date parsing fails, fall back to file modification time
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                should_remove = mtime < cutoff

            if should_remove:
                try:
                    f.unlink()
                    removed += 1
                    logger.debug(f"Removed old session: {f.name}")
                except OSError as e:
                    logger.warning(f"Failed to remove {f.name}: {e}")

        if removed:
            logger.info(f"Cleaned {removed} session(s) older than {days} days")

        return removed


def get_transcript_logger(
    working_dir: Optional[Path] = None,
    secrets_manager=None,
) -> TranscriptLogger:
    """
    Get a TranscriptLogger instance.

    Convenience function to create a logger with sensible defaults.

    Args:
        working_dir: Working directory. Sessions stored in
                    {working_dir}/.workflow_sessions/
        secrets_manager: SecretsManager for known-secret lookup.
                        If None, attempts to get default manager.

    Returns:
        Configured TranscriptLogger instance
    """
    from src.secrets import get_secrets_manager

    if secrets_manager is None:
        try:
            secrets_manager = get_secrets_manager()
        except Exception:
            pass  # Will use pattern-only scrubbing

    sessions_dir = (working_dir or Path.cwd()) / SESSIONS_DIR_NAME

    return TranscriptLogger(
        secrets_manager=secrets_manager,
        sessions_dir=sessions_dir,
    )
