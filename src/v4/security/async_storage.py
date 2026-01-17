"""
Async persistence layer for V4 Control Inversion.

This module provides:
- DatabaseAdapter: Abstract interface for SQLite/PostgreSQL compatibility
- AsyncEventStore: Async event sourcing with optimistic concurrency
- CheckpointStore: Snapshot-based recovery for fast replay

Design Principles:
- SQLite uses BEGIN IMMEDIATE for write locking (no FOR UPDATE)
- PostgreSQL uses FOR UPDATE for row-level locking
- Both share the same high-level interface via adapter pattern
"""
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)
import json
import uuid

# Import from existing synchronous storage for Event dataclass
from .storage import Event, ConcurrencyError, DatabaseError


# ============================================================
# Database Adapter Pattern
# ============================================================


@runtime_checkable
class TransactionProtocol(Protocol):
    """Protocol for database transaction operations."""

    async def execute(self, query: str, params: tuple = ()) -> None:
        """Execute a query."""
        ...

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row as dict."""
        ...

    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows as list of dicts."""
        ...


class DatabaseAdapter(ABC):
    """
    Abstract database adapter for SQLite/PostgreSQL compatibility.

    Handles differences in:
    - Transaction locking (BEGIN IMMEDIATE vs FOR UPDATE)
    - Parameter placeholder syntax (? vs $1)
    - Type conversions
    """

    @abstractmethod
    def exclusive_transaction(self) -> AsyncContextManager[TransactionProtocol]:
        """
        Return transaction context with appropriate locking.

        SQLite: Uses BEGIN IMMEDIATE to acquire write lock before any reads
        PostgreSQL: Uses standard transaction with FOR UPDATE queries
        """
        pass

    @abstractmethod
    def select_for_update(self, table: str, where: str) -> str:
        """
        Return SELECT query with appropriate locking syntax.

        SQLite: Plain SELECT (BEGIN IMMEDIATE handles locking)
        PostgreSQL: SELECT ... FOR UPDATE
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection."""
        pass


class SQLiteTransaction:
    """SQLite transaction wrapper implementing TransactionProtocol."""

    def __init__(self, conn: Any):  # aiosqlite.Connection
        self._conn = conn

    async def execute(self, query: str, params: tuple = ()) -> None:
        """Execute a query."""
        await self._conn.execute(query, params)

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row as dict."""
        cursor = await self._conn.execute(query, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        columns = [description[0] for description in cursor.description]
        return dict(zip(columns, row))

    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows as list of dicts."""
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]


class SQLiteAdapter(DatabaseAdapter):
    """
    SQLite adapter using aiosqlite.

    Uses BEGIN IMMEDIATE for exclusive locking, which:
    - Acquires write lock immediately (before any reads)
    - Prevents race conditions between SELECT and INSERT
    - Works with single-writer, multi-reader model

    For file-based databases, each exclusive_transaction() creates a new
    connection to support concurrent operations.

    For in-memory databases (:memory:), we use a shared connection since
    separate connections would create separate databases.
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite adapter.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory
        """
        self.db_path = db_path
        self._shared_conn: Optional[Any] = None
        self._is_memory = db_path == ":memory:"
        self._conn_lock = None

    async def _get_lock(self):
        """Get or create the connection lock."""
        if self._conn_lock is None:
            import asyncio
            self._conn_lock = asyncio.Lock()
        return self._conn_lock

    async def _create_connection(self) -> Any:
        """Create a new configured connection."""
        import aiosqlite

        conn = await aiosqlite.connect(
            self.db_path,
            isolation_level=None,
        )
        conn.row_factory = aiosqlite.Row

        await conn.execute("PRAGMA busy_timeout = 5000")

        if not self._is_memory:
            await conn.execute("PRAGMA journal_mode = WAL")

        await conn.execute("PRAGMA foreign_keys = ON")

        return conn

    async def _ensure_connected(self) -> Any:
        """Ensure shared connection exists and return it."""
        if self._shared_conn is None:
            self._shared_conn = await self._create_connection()
        return self._shared_conn

    @asynccontextmanager
    async def exclusive_transaction(self) -> AsyncIterator[SQLiteTransaction]:
        """
        Return transaction context with exclusive locking.

        Uses BEGIN IMMEDIATE to acquire write lock immediately,
        preventing race conditions between version check and insert.

        For file-based databases, creates a new connection per transaction.
        For in-memory databases, uses a shared connection with a lock.
        """
        if self._is_memory:
            lock = await self._get_lock()
            conn = await self._ensure_connected()

            async with lock:
                await conn.execute("BEGIN IMMEDIATE")
                try:
                    yield SQLiteTransaction(conn)
                    await conn.execute("COMMIT")
                except Exception:
                    await conn.execute("ROLLBACK")
                    raise
        else:
            conn = await self._create_connection()
            try:
                await conn.execute("BEGIN IMMEDIATE")
                try:
                    yield SQLiteTransaction(conn)
                    await conn.execute("COMMIT")
                except Exception:
                    await conn.execute("ROLLBACK")
                    raise
            finally:
                await conn.close()

    def select_for_update(self, table: str, where: str) -> str:
        """
        Return SELECT query without FOR UPDATE.

        SQLite doesn't support FOR UPDATE, but BEGIN IMMEDIATE
        already holds the write lock.
        """
        return f"SELECT * FROM {table} WHERE {where}"

    async def close(self) -> None:
        """Close the shared connection."""
        if self._shared_conn is not None:
            await self._shared_conn.close()
            self._shared_conn = None


# ============================================================
# Async Event Store
# ============================================================


class AsyncEventStore(ABC):
    """
    Abstract async event store interface.

    Provides event sourcing with optimistic concurrency control.
    Events are immutable and ordered by version within each stream.
    """

    @abstractmethod
    async def append(
        self,
        stream_id: str,
        events: List[Event],
        expected_version: Optional[int] = None,
    ) -> None:
        """
        Append events to stream with optimistic concurrency.

        Args:
            stream_id: The stream to append to
            events: Events to append (must have sequential versions)
            expected_version: Expected current version (None for any)

        Raises:
            ConcurrencyError: If version mismatch detected
            DatabaseError: If database operation fails
        """
        pass

    @abstractmethod
    async def read(
        self,
        stream_id: str,
        from_version: int = 0,
    ) -> AsyncIterator[Event]:
        """
        Read events from stream.

        Args:
            stream_id: The stream to read from
            from_version: Start reading from this version (exclusive)

        Yields:
            Events in version order
        """
        pass

    @abstractmethod
    async def read_all(
        self,
        from_position: int = 0,
        event_types: Optional[List[str]] = None,
    ) -> AsyncIterator[Event]:
        """
        Read all events across streams (for projections).

        Args:
            from_position: Start reading from this global position
            event_types: Filter by event types (optional)

        Yields:
            Events in global position order
        """
        pass

    @abstractmethod
    async def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream (0 if stream doesn't exist)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the event store."""
        pass


class SQLiteAsyncEventStore(AsyncEventStore):
    """
    SQLite-based async event store.

    Features:
    - Event sourcing with optimistic concurrency
    - WAL mode for concurrent access
    - Retry logic for transient failures
    """

    MAX_RETRIES = 3
    RETRY_DELAY_MS = 100

    def __init__(self, db_path: str):
        """
        Initialize event store.

        Args:
            db_path: Path to SQLite database file, or ":memory:" for in-memory
        """
        self.db_path = db_path
        self._adapter = SQLiteAdapter(db_path)
        self._initialized = False

    async def _ensure_schema(self) -> None:
        """Initialize database schema if needed."""
        if self._initialized:
            return

        async with self._adapter.exclusive_transaction() as tx:
            await tx.execute("""
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

            await tx.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_stream_id
                ON events(stream_id, version)
            """)

            await tx.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_type
                ON events(type)
            """)

            await tx.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_correlation
                ON events(correlation_id)
            """)

        self._initialized = True

    async def append(
        self,
        stream_id: str,
        events: List[Event],
        expected_version: Optional[int] = None,
    ) -> None:
        """Append events with optimistic concurrency control."""
        import asyncio

        if not events:
            return

        await self._ensure_schema()

        for attempt in range(self.MAX_RETRIES):
            try:
                await self._append_internal(stream_id, events, expected_version)
                return
            except Exception as e:
                if "database is locked" in str(e) and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY_MS / 1000)
                    continue
                raise

    async def _append_internal(
        self,
        stream_id: str,
        events: List[Event],
        expected_version: Optional[int],
    ) -> None:
        """Internal append with transaction handling."""
        async with self._adapter.exclusive_transaction() as tx:
            row = await tx.fetch_one(
                "SELECT MAX(version) as max_version FROM events WHERE stream_id = ?",
                (stream_id,)
            )
            current_version = row["max_version"] if row and row["max_version"] is not None else 0

            if expected_version is not None and current_version != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}, "
                    f"but stream is at {current_version}"
                )

            for i, event in enumerate(events):
                expected = current_version + i + 1
                if event.version != expected:
                    raise ValueError(
                        f"Event version {event.version} should be {expected}"
                    )

            for event in events:
                await tx.execute(
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

    async def read(
        self,
        stream_id: str,
        from_version: int = 0,
    ) -> AsyncIterator[Event]:
        """Read events from stream."""
        await self._ensure_schema()

        conn = await self._adapter._ensure_connected()
        cursor = await conn.execute(
            """
            SELECT global_position, id, stream_id, type, version, timestamp,
                   correlation_id, causation_id, data, metadata
            FROM events
            WHERE stream_id = ? AND version > ?
            ORDER BY version
            """,
            (stream_id, from_version)
        )

        async for row in cursor:
            yield Event(
                id=row[1],
                stream_id=row[2],
                type=row[3],
                version=row[4],
                timestamp=datetime.fromisoformat(row[5]),
                correlation_id=row[6],
                causation_id=row[7],
                data=json.loads(row[8]),
                metadata=json.loads(row[9]),
                global_position=row[0],
            )

    async def read_all(
        self,
        from_position: int = 0,
        event_types: Optional[List[str]] = None,
    ) -> AsyncIterator[Event]:
        """Read all events for projections."""
        await self._ensure_schema()

        conn = await self._adapter._ensure_connected()

        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query = f"""
                SELECT global_position, id, stream_id, type, version, timestamp,
                       correlation_id, causation_id, data, metadata
                FROM events
                WHERE global_position > ? AND type IN ({placeholders})
                ORDER BY global_position
            """
            params = (from_position,) + tuple(event_types)
        else:
            query = """
                SELECT global_position, id, stream_id, type, version, timestamp,
                       correlation_id, causation_id, data, metadata
                FROM events
                WHERE global_position > ?
                ORDER BY global_position
            """
            params = (from_position,)

        cursor = await conn.execute(query, params)

        async for row in cursor:
            yield Event(
                id=row[1],
                stream_id=row[2],
                type=row[3],
                version=row[4],
                timestamp=datetime.fromisoformat(row[5]),
                correlation_id=row[6],
                causation_id=row[7],
                data=json.loads(row[8]),
                metadata=json.loads(row[9]),
                global_position=row[0],
            )

    async def get_stream_version(self, stream_id: str) -> int:
        """Get current version of a stream."""
        await self._ensure_schema()

        conn = await self._adapter._ensure_connected()
        cursor = await conn.execute(
            "SELECT MAX(version) FROM events WHERE stream_id = ?",
            (stream_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row and row[0] is not None else 0

    async def close(self) -> None:
        """Close the event store."""
        await self._adapter.close()


# ============================================================
# Checkpoint Store
# ============================================================


@dataclass
class Checkpoint:
    """
    Snapshot for fast recovery.

    Checkpoints store aggregate state at a specific version,
    allowing replay to start from the checkpoint instead of
    replaying all events from the beginning.
    """

    id: str
    stream_id: str
    version: int
    state: Dict[str, Any]
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        stream_id: str,
        version: int,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Checkpoint":
        """Create a new checkpoint."""
        return cls(
            id=f"cp_{uuid.uuid4().hex[:12]}",
            stream_id=stream_id,
            version=version,
            state=state,
            created_at=datetime.now(),
            metadata=metadata or {},
        )


class CheckpointStore:
    """
    Store and retrieve checkpoints for fast recovery.

    Checkpoints are stored separately from events and can be
    pruned independently. Only the most recent checkpoint per
    stream is typically needed.
    """

    def __init__(self, adapter: DatabaseAdapter):
        """
        Initialize checkpoint store.

        Args:
            adapter: Database adapter for persistence
        """
        self._adapter = adapter
        self._initialized = False

    async def _ensure_schema(self) -> None:
        """Initialize checkpoint table schema."""
        if self._initialized:
            return

        async with self._adapter.exclusive_transaction() as tx:
            await tx.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    UNIQUE(stream_id, version)
                )
            """)

            await tx.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkpoints_stream_version
                ON checkpoints(stream_id, version DESC)
            """)

        self._initialized = True

    async def save(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint."""
        await self._ensure_schema()

        async with self._adapter.exclusive_transaction() as tx:
            await tx.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (id, stream_id, version, state, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.id,
                    checkpoint.stream_id,
                    checkpoint.version,
                    json.dumps(checkpoint.state),
                    checkpoint.created_at.isoformat(),
                    json.dumps(checkpoint.metadata),
                )
            )

    async def load_latest(self, stream_id: str) -> Optional[Checkpoint]:
        """Load most recent checkpoint for stream."""
        await self._ensure_schema()

        async with self._adapter.exclusive_transaction() as tx:
            row = await tx.fetch_one(
                """
                SELECT id, stream_id, version, state, created_at, metadata
                FROM checkpoints
                WHERE stream_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (stream_id,)
            )

            if row is None:
                return None

            return Checkpoint(
                id=row["id"],
                stream_id=row["stream_id"],
                version=row["version"],
                state=json.loads(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                metadata=json.loads(row["metadata"]),
            )

    async def load_at_version(
        self,
        stream_id: str,
        version: int,
    ) -> Optional[Checkpoint]:
        """Load checkpoint at or before specific version."""
        await self._ensure_schema()

        async with self._adapter.exclusive_transaction() as tx:
            row = await tx.fetch_one(
                """
                SELECT id, stream_id, version, state, created_at, metadata
                FROM checkpoints
                WHERE stream_id = ? AND version <= ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (stream_id, version)
            )

            if row is None:
                return None

            return Checkpoint(
                id=row["id"],
                stream_id=row["stream_id"],
                version=row["version"],
                state=json.loads(row["state"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                metadata=json.loads(row["metadata"]),
            )

    async def delete_older_than(
        self,
        stream_id: str,
        keep_count: int = 3,
    ) -> int:
        """Delete old checkpoints, keeping most recent N."""
        await self._ensure_schema()

        async with self._adapter.exclusive_transaction() as tx:
            rows = await tx.fetch_all(
                """
                SELECT id FROM checkpoints
                WHERE stream_id = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (stream_id, keep_count)
            )
            keep_ids = [row["id"] for row in rows]

            if not keep_ids:
                return 0

            placeholders = ",".join("?" * len(keep_ids))
            await tx.execute(
                f"""
                DELETE FROM checkpoints
                WHERE stream_id = ? AND id NOT IN ({placeholders})
                """,
                (stream_id,) + tuple(keep_ids)
            )

            return 0

    async def list_checkpoints(
        self,
        stream_id: str,
        limit: int = 10,
    ) -> List[Checkpoint]:
        """List checkpoints for a stream."""
        await self._ensure_schema()

        async with self._adapter.exclusive_transaction() as tx:
            rows = await tx.fetch_all(
                """
                SELECT id, stream_id, version, state, created_at, metadata
                FROM checkpoints
                WHERE stream_id = ?
                ORDER BY version DESC
                LIMIT ?
                """,
                (stream_id, limit)
            )

            return [
                Checkpoint(
                    id=row["id"],
                    stream_id=row["stream_id"],
                    version=row["version"],
                    state=json.loads(row["state"]),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    metadata=json.loads(row["metadata"]),
                )
                for row in rows
            ]


# ============================================================
# Recovery Helper
# ============================================================


class EventSourcedRepository:
    """
    Helper for loading aggregates with checkpoint optimization.

    Combines event store and checkpoint store to provide
    fast aggregate loading:
    1. Load latest checkpoint (if exists)
    2. Replay events after checkpoint version
    3. Apply events to rebuild aggregate state
    """

    def __init__(
        self,
        event_store: AsyncEventStore,
        checkpoint_store: CheckpointStore,
        checkpoint_interval: int = 100,
    ):
        """
        Initialize repository.

        Args:
            event_store: Event store for events
            checkpoint_store: Checkpoint store for snapshots
            checkpoint_interval: Create checkpoint every N events
        """
        self.event_store = event_store
        self.checkpoint_store = checkpoint_store
        self.checkpoint_interval = checkpoint_interval

    async def load_events_from_checkpoint(
        self,
        stream_id: str,
    ) -> tuple[Optional[Checkpoint], List[Event]]:
        """
        Load checkpoint and subsequent events.

        Returns:
            Tuple of (checkpoint or None, list of events after checkpoint)
        """
        checkpoint = await self.checkpoint_store.load_latest(stream_id)
        from_version = checkpoint.version if checkpoint else 0

        events = []
        async for event in self.event_store.read(stream_id, from_version):
            events.append(event)

        return checkpoint, events

    async def maybe_checkpoint(
        self,
        stream_id: str,
        current_version: int,
        state: Dict[str, Any],
    ) -> Optional[Checkpoint]:
        """
        Create checkpoint if interval threshold reached.

        Args:
            stream_id: Stream to checkpoint
            current_version: Current event version
            state: Current aggregate state

        Returns:
            Created checkpoint, or None if not needed
        """
        latest = await self.checkpoint_store.load_latest(stream_id)

        last_checkpoint_version = latest.version if latest else 0

        if current_version - last_checkpoint_version < self.checkpoint_interval:
            return None

        checkpoint = Checkpoint.create(
            stream_id=stream_id,
            version=current_version,
            state=state,
        )
        await self.checkpoint_store.save(checkpoint)

        await self.checkpoint_store.delete_older_than(stream_id, keep_count=3)

        return checkpoint
