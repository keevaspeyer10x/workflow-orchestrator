"""
Secure SQLite storage for V4 Control Inversion event store.

This module provides:
- Proper SQLite schema with INTEGER PRIMARY KEY AUTOINCREMENT
- busy_timeout for handling concurrent access
- WAL mode for better concurrency
- Retry logic for database locks

Security Model:
1. BEGIN IMMEDIATE for write lock acquisition
2. Proper AUTOINCREMENT syntax (INTEGER PRIMARY KEY AUTOINCREMENT)
3. busy_timeout to handle concurrent access gracefully
4. WAL mode for concurrent reads during writes
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional
import json
import sqlite3
import time


class ConcurrencyError(Exception):
    """Raised when a concurrency conflict is detected."""
    pass


class DatabaseError(Exception):
    """Raised when a database operation fails."""
    pass


@dataclass
class Event:
    """Canonical event envelope."""
    id: str
    stream_id: str  # workflow_id or chat_session_id
    type: str
    version: int  # For schema evolution
    timestamp: datetime
    correlation_id: str  # Links related events
    causation_id: Optional[str]  # Event that caused this one
    data: dict
    metadata: dict
    global_position: Optional[int] = None  # Auto-assigned


class EventStore:
    """
    SQLite-based event store for single-node deployment.

    Features:
    - Event sourcing with optimistic concurrency
    - WAL mode for concurrent access
    - Busy timeout for lock handling
    - Retry logic for transient failures
    """

    # Configuration
    BUSY_TIMEOUT_MS = 5000  # 5 seconds
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 100

    def __init__(self, db_path: str):
        """
        Initialize event store.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory
        """
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_schema()

    def _connect(self) -> None:
        """Create database connection with security settings."""
        self._conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,  # Autocommit mode (we manage transactions)
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row

        # Enable busy timeout for concurrent access
        self._conn.execute(f"PRAGMA busy_timeout = {self.BUSY_TIMEOUT_MS}")

        # Enable WAL mode for better concurrency (file-based DBs only)
        if self.db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")

        # Enable foreign keys
        self._conn.execute("PRAGMA foreign_keys = ON")

    def _init_schema(self) -> None:
        """
        Initialize database schema.

        Uses INTEGER PRIMARY KEY AUTOINCREMENT for global_position.
        Note: SQLite requires "INTEGER PRIMARY KEY" (not just "AUTOINCREMENT").
        """
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                global_position INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                stream_id TEXT NOT NULL,
                type TEXT NOT NULL,
                version INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                causation_id TEXT,
                data TEXT NOT NULL,
                metadata TEXT NOT NULL,
                UNIQUE(stream_id, version)
            )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_stream_id
            ON events(stream_id, version)
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type
            ON events(type)
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_correlation
            ON events(correlation_id)
        """)

    def append(
        self,
        stream_id: str,
        events: List[Event],
        expected_version: Optional[int] = None,
    ) -> None:
        """
        Append events to stream with optimistic concurrency.

        Uses BEGIN IMMEDIATE to acquire write lock before reading,
        preventing race conditions between version check and insert.

        Args:
            stream_id: The stream to append to
            events: Events to append (must have sequential versions)
            expected_version: Expected current version (None for any)

        Raises:
            ConcurrencyError: If version mismatch detected
            DatabaseError: If database operation fails
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                self._append_with_retry(stream_id, events, expected_version)
                return
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_MS / 1000)
                    continue
                raise DatabaseError(f"Database operation failed: {e}")

    def _append_with_retry(
        self,
        stream_id: str,
        events: List[Event],
        expected_version: Optional[int],
    ) -> None:
        """Internal append with transaction handling."""
        # BEGIN IMMEDIATE acquires write lock immediately
        self._conn.execute("BEGIN IMMEDIATE")

        try:
            # Get current max version (safe - we hold write lock)
            cursor = self._conn.execute(
                "SELECT MAX(version) FROM events WHERE stream_id = ?",
                (stream_id,)
            )
            row = cursor.fetchone()
            current_version = row[0] if row[0] is not None else 0

            # Check expected version if specified
            if expected_version is not None and current_version != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}, "
                    f"but stream is at {current_version}"
                )

            # Verify events have sequential versions starting after current
            for i, event in enumerate(events):
                expected = current_version + i + 1
                if event.version != expected:
                    raise ValueError(
                        f"Event version {event.version} should be {expected}"
                    )

            # Insert events
            for event in events:
                self._conn.execute(
                    """
                    INSERT INTO events
                    (id, stream_id, type, version, timestamp,
                     correlation_id, causation_id, data, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        stream_id,
                        event.type,
                        event.version,
                        event.timestamp.isoformat(),
                        event.correlation_id,
                        event.causation_id,
                        json.dumps(event.data),
                        json.dumps(event.metadata),
                    )
                )

            self._conn.execute("COMMIT")

        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def read(
        self,
        stream_id: str,
        from_version: int = 0,
    ) -> Iterator[Event]:
        """
        Read events from stream.

        Args:
            stream_id: The stream to read from
            from_version: Start reading from this version (exclusive)

        Yields:
            Events in version order
        """
        cursor = self._conn.execute(
            """
            SELECT global_position, id, stream_id, type, version, timestamp,
                   correlation_id, causation_id, data, metadata
            FROM events
            WHERE stream_id = ? AND version > ?
            ORDER BY version
            """,
            (stream_id, from_version)
        )

        for row in cursor:
            yield Event(
                id=row["id"],
                stream_id=row["stream_id"],
                type=row["type"],
                version=row["version"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                correlation_id=row["correlation_id"],
                causation_id=row["causation_id"],
                data=json.loads(row["data"]),
                metadata=json.loads(row["metadata"]),
                global_position=row["global_position"],
            )

    def read_all(
        self,
        from_position: int = 0,
        event_types: Optional[List[str]] = None,
    ) -> Iterator[Event]:
        """
        Read all events (for projections).

        Args:
            from_position: Start reading from this global position
            event_types: Filter by event types (optional)

        Yields:
            Events in global position order
        """
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query = f"""
                SELECT global_position, id, stream_id, type, version, timestamp,
                       correlation_id, causation_id, data, metadata
                FROM events
                WHERE global_position > ? AND type IN ({placeholders})
                ORDER BY global_position
            """
            params = [from_position] + event_types
        else:
            query = """
                SELECT global_position, id, stream_id, type, version, timestamp,
                       correlation_id, causation_id, data, metadata
                FROM events
                WHERE global_position > ?
                ORDER BY global_position
            """
            params = [from_position]

        cursor = self._conn.execute(query, params)

        for row in cursor:
            yield Event(
                id=row["id"],
                stream_id=row["stream_id"],
                type=row["type"],
                version=row["version"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                correlation_id=row["correlation_id"],
                causation_id=row["causation_id"],
                data=json.loads(row["data"]),
                metadata=json.loads(row["metadata"]),
                global_position=row["global_position"],
            )

    def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream."""
        cursor = self._conn.execute(
            "SELECT MAX(version) FROM events WHERE stream_id = ?",
            (stream_id,)
        )
        row = cursor.fetchone()
        return row[0] if row[0] is not None else 0

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
