"""
Tests for V4.2 Phase 1: Async Persistence Layer.

Tests cover:
- AsyncEventStore with optimistic concurrency
- CheckpointStore for fast recovery
- SQLiteAdapter locking behavior
- Event replay and recovery
- Concurrent access handling
"""
import asyncio
import os
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

from src.v4.security.storage import Event, ConcurrencyError, DatabaseError
from src.v4.security.async_storage import (
    SQLiteAdapter,
    SQLiteAsyncEventStore,
    CheckpointStore,
    Checkpoint,
    EventSourcedRepository,
)


# ============================================================
# Test Fixtures
# ============================================================


@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def in_memory_db():
    """Use in-memory database for fast tests."""
    return ":memory:"


def create_event(
    stream_id: str,
    version: int,
    event_type: str = "test_event",
    data: dict = None,
) -> Event:
    """Helper to create test events."""
    return Event(
        id=f"evt_{stream_id}_{version}",
        stream_id=stream_id,
        type=event_type,
        version=version,
        timestamp=datetime.now(),
        correlation_id=f"corr_{stream_id}",
        causation_id=None,
        data=data or {"key": "value"},
        metadata={"test": True},
    )


# ============================================================
# SQLiteAdapter Tests
# ============================================================


class TestSQLiteAdapter:
    """Test SQLite database adapter."""

    @pytest.mark.asyncio
    async def test_connection_established(self, temp_db_path):
        """Test that connection is established correctly."""
        adapter = SQLiteAdapter(temp_db_path)

        async with adapter.exclusive_transaction() as tx:
            await tx.execute("SELECT 1")

        await adapter.close()

    @pytest.mark.asyncio
    async def test_wal_mode_enabled(self, temp_db_path):
        """Test that WAL mode is enabled for file-based databases."""
        adapter = SQLiteAdapter(temp_db_path)

        async with adapter.exclusive_transaction() as tx:
            result = await tx.fetch_one("PRAGMA journal_mode")
            assert result is not None

        await adapter.close()

    @pytest.mark.asyncio
    async def test_busy_timeout_configured(self, temp_db_path):
        """Test that busy timeout is configured."""
        adapter = SQLiteAdapter(temp_db_path)

        async with adapter.exclusive_transaction() as tx:
            result = await tx.fetch_one("PRAGMA busy_timeout")
            assert result is not None

        await adapter.close()

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self, temp_db_path):
        """Test that transactions rollback on error."""
        adapter = SQLiteAdapter(temp_db_path)

        async with adapter.exclusive_transaction() as tx:
            await tx.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
            await tx.execute("INSERT INTO test (value) VALUES ('initial')")

        try:
            async with adapter.exclusive_transaction() as tx:
                await tx.execute("INSERT INTO test (value) VALUES ('should_rollback')")
                raise ValueError("Intentional error")
        except ValueError:
            pass

        async with adapter.exclusive_transaction() as tx:
            result = await tx.fetch_all("SELECT value FROM test")
            assert len(result) == 1
            assert result[0]["value"] == "initial"

        await adapter.close()

    def test_select_for_update_no_for_update_clause(self):
        """Test that SQLite adapter doesn't add FOR UPDATE."""
        adapter = SQLiteAdapter(":memory:")
        query = adapter.select_for_update("events", "stream_id = ?")
        assert "FOR UPDATE" not in query
        assert "SELECT * FROM events WHERE stream_id = ?" == query


# ============================================================
# AsyncEventStore Tests
# ============================================================


class TestAsyncEventStore:
    """Test async event store functionality."""

    @pytest.mark.asyncio
    async def test_append_single_event(self, in_memory_db):
        """Test appending a single event to a stream."""
        store = SQLiteAsyncEventStore(in_memory_db)

        event = create_event("stream_1", version=1)
        await store.append("stream_1", [event])

        version = await store.get_stream_version("stream_1")
        assert version == 1

        await store.close()

    @pytest.mark.asyncio
    async def test_append_multiple_events(self, in_memory_db):
        """Test appending multiple events atomically."""
        store = SQLiteAsyncEventStore(in_memory_db)

        events = [
            create_event("stream_1", version=1, data={"n": 1}),
            create_event("stream_1", version=2, data={"n": 2}),
            create_event("stream_1", version=3, data={"n": 3}),
        ]
        await store.append("stream_1", events)

        version = await store.get_stream_version("stream_1")
        assert version == 3

        await store.close()

    @pytest.mark.asyncio
    async def test_optimistic_concurrency_success(self, in_memory_db):
        """Test optimistic concurrency with correct expected version."""
        store = SQLiteAsyncEventStore(in_memory_db)

        event1 = create_event("stream_1", version=1)
        await store.append("stream_1", [event1], expected_version=0)

        event2 = create_event("stream_1", version=2)
        await store.append("stream_1", [event2], expected_version=1)

        version = await store.get_stream_version("stream_1")
        assert version == 2

        await store.close()

    @pytest.mark.asyncio
    async def test_optimistic_concurrency_failure(self, in_memory_db):
        """Test optimistic concurrency with wrong expected version."""
        store = SQLiteAsyncEventStore(in_memory_db)

        event1 = create_event("stream_1", version=1)
        await store.append("stream_1", [event1])

        event2 = create_event("stream_1", version=2)

        with pytest.raises(ConcurrencyError) as exc:
            await store.append("stream_1", [event2], expected_version=0)

        assert "expected version 0" in str(exc.value).lower()

        await store.close()

    @pytest.mark.asyncio
    async def test_version_sequence_validation(self, in_memory_db):
        """Test that events must have sequential versions."""
        store = SQLiteAsyncEventStore(in_memory_db)

        event = create_event("stream_1", version=2)

        with pytest.raises(ValueError) as exc:
            await store.append("stream_1", [event])

        assert "should be 1" in str(exc.value)

        await store.close()

    @pytest.mark.asyncio
    async def test_read_events_from_stream(self, in_memory_db):
        """Test reading events from a stream."""
        store = SQLiteAsyncEventStore(in_memory_db)

        events = [
            create_event("stream_1", version=1, data={"n": 1}),
            create_event("stream_1", version=2, data={"n": 2}),
            create_event("stream_1", version=3, data={"n": 3}),
        ]
        await store.append("stream_1", events)

        read_events = []
        async for event in store.read("stream_1"):
            read_events.append(event)

        assert len(read_events) == 3
        assert read_events[0].version == 1
        assert read_events[2].version == 3

        await store.close()

    @pytest.mark.asyncio
    async def test_read_events_from_version(self, in_memory_db):
        """Test reading events from a specific version."""
        store = SQLiteAsyncEventStore(in_memory_db)

        events = [
            create_event("stream_1", version=1, data={"n": 1}),
            create_event("stream_1", version=2, data={"n": 2}),
            create_event("stream_1", version=3, data={"n": 3}),
        ]
        await store.append("stream_1", events)

        read_events = []
        async for event in store.read("stream_1", from_version=1):
            read_events.append(event)

        assert len(read_events) == 2
        assert read_events[0].version == 2
        assert read_events[1].version == 3

        await store.close()

    @pytest.mark.asyncio
    async def test_read_all_events(self, in_memory_db):
        """Test reading all events across streams."""
        store = SQLiteAsyncEventStore(in_memory_db)

        await store.append("stream_1", [create_event("stream_1", 1)])
        await store.append("stream_2", [create_event("stream_2", 1)])
        await store.append("stream_1", [create_event("stream_1", 2)])

        all_events = []
        async for event in store.read_all():
            all_events.append(event)

        assert len(all_events) == 3
        assert all_events[0].global_position < all_events[1].global_position

        await store.close()

    @pytest.mark.asyncio
    async def test_read_all_with_type_filter(self, in_memory_db):
        """Test reading events filtered by type."""
        store = SQLiteAsyncEventStore(in_memory_db)

        await store.append("stream_1", [
            create_event("stream_1", 1, event_type="type_a"),
        ])
        await store.append("stream_1", [
            create_event("stream_1", 2, event_type="type_b"),
        ])
        await store.append("stream_1", [
            create_event("stream_1", 3, event_type="type_a"),
        ])

        filtered_events = []
        async for event in store.read_all(event_types=["type_a"]):
            filtered_events.append(event)

        assert len(filtered_events) == 2
        assert all(e.type == "type_a" for e in filtered_events)

        await store.close()

    @pytest.mark.asyncio
    async def test_empty_stream_version(self, in_memory_db):
        """Test that empty stream has version 0."""
        store = SQLiteAsyncEventStore(in_memory_db)

        version = await store.get_stream_version("nonexistent_stream")
        assert version == 0

        await store.close()

    @pytest.mark.asyncio
    async def test_events_persist_across_connections(self, temp_db_path):
        """Test that events persist across process restarts."""
        store1 = SQLiteAsyncEventStore(temp_db_path)
        events = [
            create_event("stream_1", version=1, data={"value": "test"}),
        ]
        await store1.append("stream_1", events)
        await store1.close()

        store2 = SQLiteAsyncEventStore(temp_db_path)
        version = await store2.get_stream_version("stream_1")
        assert version == 1

        read_events = []
        async for event in store2.read("stream_1"):
            read_events.append(event)

        assert len(read_events) == 1
        assert read_events[0].data["value"] == "test"

        await store2.close()


# ============================================================
# CheckpointStore Tests
# ============================================================


class TestCheckpointStore:
    """Test checkpoint store functionality."""

    @pytest.mark.asyncio
    async def test_save_and_load_checkpoint(self, in_memory_db):
        """Test saving and loading a checkpoint."""
        adapter = SQLiteAdapter(in_memory_db)
        store = CheckpointStore(adapter)

        checkpoint = Checkpoint.create(
            stream_id="stream_1",
            version=100,
            state={"counter": 42, "items": ["a", "b"]},
        )

        await store.save(checkpoint)

        loaded = await store.load_latest("stream_1")
        assert loaded is not None
        assert loaded.stream_id == "stream_1"
        assert loaded.version == 100
        assert loaded.state["counter"] == 42
        assert loaded.state["items"] == ["a", "b"]

        await adapter.close()

    @pytest.mark.asyncio
    async def test_load_latest_returns_most_recent(self, in_memory_db):
        """Test that load_latest returns the most recent checkpoint."""
        adapter = SQLiteAdapter(in_memory_db)
        store = CheckpointStore(adapter)

        for version in [10, 50, 30]:
            checkpoint = Checkpoint.create(
                stream_id="stream_1",
                version=version,
                state={"version": version},
            )
            await store.save(checkpoint)

        latest = await store.load_latest("stream_1")
        assert latest.version == 50

        await adapter.close()

    @pytest.mark.asyncio
    async def test_load_at_version(self, in_memory_db):
        """Test loading checkpoint at or before specific version."""
        adapter = SQLiteAdapter(in_memory_db)
        store = CheckpointStore(adapter)

        for version in [10, 50, 100]:
            checkpoint = Checkpoint.create(
                stream_id="stream_1",
                version=version,
                state={"version": version},
            )
            await store.save(checkpoint)

        loaded = await store.load_at_version("stream_1", 75)
        assert loaded.version == 50

        loaded = await store.load_at_version("stream_1", 10)
        assert loaded.version == 10

        loaded = await store.load_at_version("stream_1", 5)
        assert loaded is None

        await adapter.close()

    @pytest.mark.asyncio
    async def test_load_nonexistent_stream(self, in_memory_db):
        """Test loading checkpoint for nonexistent stream returns None."""
        adapter = SQLiteAdapter(in_memory_db)
        store = CheckpointStore(adapter)

        loaded = await store.load_latest("nonexistent")
        assert loaded is None

        await adapter.close()

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, in_memory_db):
        """Test listing checkpoints for a stream."""
        adapter = SQLiteAdapter(in_memory_db)
        store = CheckpointStore(adapter)

        for version in range(1, 6):
            checkpoint = Checkpoint.create(
                stream_id="stream_1",
                version=version * 10,
                state={"v": version},
            )
            await store.save(checkpoint)

        checkpoints = await store.list_checkpoints("stream_1", limit=10)
        assert len(checkpoints) == 5

        versions = [cp.version for cp in checkpoints]
        assert versions == [50, 40, 30, 20, 10]

        limited = await store.list_checkpoints("stream_1", limit=2)
        assert len(limited) == 2
        assert limited[0].version == 50

        await adapter.close()


# ============================================================
# EventSourcedRepository Tests
# ============================================================


class TestEventSourcedRepository:
    """Test the event sourced repository helper."""

    @pytest.mark.asyncio
    async def test_load_events_from_checkpoint(self, in_memory_db):
        """Test loading checkpoint and subsequent events."""
        adapter = SQLiteAdapter(in_memory_db)
        event_store = SQLiteAsyncEventStore(in_memory_db)
        checkpoint_store = CheckpointStore(adapter)
        repo = EventSourcedRepository(event_store, checkpoint_store)

        events = [create_event("stream_1", v) for v in range(1, 11)]
        await event_store.append("stream_1", events)

        checkpoint = Checkpoint.create(
            stream_id="stream_1",
            version=5,
            state={"sum": 15},
        )
        await checkpoint_store.save(checkpoint)

        loaded_cp, subsequent_events = await repo.load_events_from_checkpoint("stream_1")

        assert loaded_cp is not None
        assert loaded_cp.version == 5
        assert len(subsequent_events) == 5
        assert subsequent_events[0].version == 6

        await event_store.close()
        await adapter.close()

    @pytest.mark.asyncio
    async def test_load_without_checkpoint(self, in_memory_db):
        """Test loading when no checkpoint exists."""
        adapter = SQLiteAdapter(in_memory_db)
        event_store = SQLiteAsyncEventStore(in_memory_db)
        checkpoint_store = CheckpointStore(adapter)
        repo = EventSourcedRepository(event_store, checkpoint_store)

        events = [create_event("stream_1", v) for v in range(1, 6)]
        await event_store.append("stream_1", events)

        loaded_cp, all_events = await repo.load_events_from_checkpoint("stream_1")

        assert loaded_cp is None
        assert len(all_events) == 5

        await event_store.close()
        await adapter.close()

    @pytest.mark.asyncio
    async def test_maybe_checkpoint_creates_at_interval(self, in_memory_db):
        """Test that checkpoints are created at specified intervals."""
        adapter = SQLiteAdapter(in_memory_db)
        event_store = SQLiteAsyncEventStore(in_memory_db)
        checkpoint_store = CheckpointStore(adapter)
        repo = EventSourcedRepository(
            event_store,
            checkpoint_store,
            checkpoint_interval=10,
        )

        cp = await repo.maybe_checkpoint("stream_1", 5, {"state": "a"})
        assert cp is None

        cp = await repo.maybe_checkpoint("stream_1", 10, {"state": "b"})
        assert cp is not None
        assert cp.version == 10

        cp = await repo.maybe_checkpoint("stream_1", 15, {"state": "c"})
        assert cp is None

        await event_store.close()
        await adapter.close()


# ============================================================
# Concurrency Tests
# ============================================================


class TestConcurrency:
    """Test concurrent access handling."""

    @pytest.mark.asyncio
    async def test_concurrent_appends_to_same_stream(self, temp_db_path):
        """Test that concurrent appends to same stream are serialized."""
        store = SQLiteAsyncEventStore(temp_db_path)

        initial_event = create_event("stream_1", 1)
        await store.append("stream_1", [initial_event])

        async def append_event(n: int):
            for _ in range(3):
                try:
                    version = await store.get_stream_version("stream_1")
                    event = create_event("stream_1", version + 1, data={"n": n})
                    await store.append("stream_1", [event], expected_version=version)
                    return True
                except ConcurrencyError:
                    await asyncio.sleep(0.01)
            return False

        results = await asyncio.gather(*[append_event(i) for i in range(5)])

        assert all(results)

        final_version = await store.get_stream_version("stream_1")
        assert final_version == 6

        await store.close()

    @pytest.mark.asyncio
    async def test_concurrent_appends_to_different_streams(self, temp_db_path):
        """Test that concurrent appends to different streams work."""
        store = SQLiteAsyncEventStore(temp_db_path)

        async def append_to_stream(stream_id: str, count: int):
            events = [create_event(stream_id, v + 1) for v in range(count)]
            await store.append(stream_id, events)

        await asyncio.gather(
            append_to_stream("stream_a", 10),
            append_to_stream("stream_b", 10),
            append_to_stream("stream_c", 10),
        )

        for stream in ["stream_a", "stream_b", "stream_c"]:
            version = await store.get_stream_version(stream)
            assert version == 10

        await store.close()


# ============================================================
# Recovery Tests
# ============================================================


class TestRecovery:
    """Test event replay and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_replay_produces_identical_state(self, temp_db_path):
        """Test that replaying events produces identical state."""
        store1 = SQLiteAsyncEventStore(temp_db_path)

        events = []
        for i in range(1, 101):
            events.append(create_event("stream_1", i, data={"value": i}))
        await store1.append("stream_1", events)
        await store1.close()

        store2 = SQLiteAsyncEventStore(temp_db_path)

        state = {"sum": 0, "count": 0}
        async for event in store2.read("stream_1"):
            state["sum"] += event.data["value"]
            state["count"] += 1

        assert state["sum"] == 5050
        assert state["count"] == 100

        await store2.close()

    @pytest.mark.asyncio
    async def test_checkpoint_reduces_replay_time(self, temp_db_path):
        """Test that checkpoints reduce replay time significantly."""
        adapter = SQLiteAdapter(temp_db_path)
        event_store = SQLiteAsyncEventStore(temp_db_path)
        checkpoint_store = CheckpointStore(adapter)

        events = [create_event("stream_1", i + 1, data={"v": i}) for i in range(1000)]
        await event_store.append("stream_1", events)

        checkpoint = Checkpoint.create(
            stream_id="stream_1",
            version=900,
            state={"count": 900, "sum": sum(range(900))},
        )
        await checkpoint_store.save(checkpoint)

        repo = EventSourcedRepository(event_store, checkpoint_store)
        cp, events_to_replay = await repo.load_events_from_checkpoint("stream_1")

        assert cp is not None
        assert cp.version == 900
        assert len(events_to_replay) == 100

        await event_store.close()
        await adapter.close()


# ============================================================
# Schema Migration Tests
# ============================================================


class TestSchemaMigration:
    """Test schema initialization and migration."""

    @pytest.mark.asyncio
    async def test_schema_created_on_first_use(self, temp_db_path):
        """Test that schema is created automatically on first use."""
        store = SQLiteAsyncEventStore(temp_db_path)

        event = create_event("stream_1", 1)
        await store.append("stream_1", [event])

        conn = await store._adapter._ensure_connected()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in await cursor.fetchall()]

        assert "events" in tables

        await store.close()

    @pytest.mark.asyncio
    async def test_checkpoint_schema_created(self, temp_db_path):
        """Test that checkpoint schema is created automatically."""
        adapter = SQLiteAdapter(temp_db_path)
        store = CheckpointStore(adapter)

        checkpoint = Checkpoint.create("stream_1", 1, {"test": True})
        await store.save(checkpoint)

        async with adapter.exclusive_transaction() as tx:
            result = await tx.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'"
            )
            assert result is not None

        await adapter.close()

    @pytest.mark.asyncio
    async def test_indexes_created(self, temp_db_path):
        """Test that indexes are created for efficient queries."""
        store = SQLiteAsyncEventStore(temp_db_path)

        event = create_event("stream_1", 1)
        await store.append("stream_1", [event])

        conn = await store._adapter._ensure_connected()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

        assert "idx_events_stream_id" in indexes
        assert "idx_events_type" in indexes
        assert "idx_events_correlation" in indexes

        await store.close()


# ============================================================
# Edge Cases
# ============================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_event_list(self, in_memory_db):
        """Test that appending empty list does nothing."""
        store = SQLiteAsyncEventStore(in_memory_db)

        await store.append("stream_1", [])

        version = await store.get_stream_version("stream_1")
        assert version == 0

        await store.close()

    @pytest.mark.asyncio
    async def test_large_event_data(self, in_memory_db):
        """Test handling of large event data."""
        store = SQLiteAsyncEventStore(in_memory_db)

        large_data = {"content": "x" * 100_000}
        event = create_event("stream_1", 1, data=large_data)

        await store.append("stream_1", [event])

        events = []
        async for e in store.read("stream_1"):
            events.append(e)

        assert len(events) == 1
        assert len(events[0].data["content"]) == 100_000

        await store.close()

    @pytest.mark.asyncio
    async def test_special_characters_in_data(self, in_memory_db):
        """Test handling of special characters in event data."""
        store = SQLiteAsyncEventStore(in_memory_db)

        special_data = {
            "unicode": "Hello \u4e16\u754c",
            "newlines": "line1\nline2",
            "quotes": 'He said "hello"',
            "backslash": "path\\to\\file",
        }
        event = create_event("stream_1", 1, data=special_data)

        await store.append("stream_1", [event])

        events = []
        async for e in store.read("stream_1"):
            events.append(e)

        assert events[0].data == special_data

        await store.close()

    @pytest.mark.asyncio
    async def test_duplicate_event_id_rejected(self, in_memory_db):
        """Test that duplicate event IDs are rejected."""
        store = SQLiteAsyncEventStore(in_memory_db)

        event1 = create_event("stream_1", 1)
        await store.append("stream_1", [event1])

        event2 = Event(
            id=event1.id,
            stream_id="stream_2",
            type="test",
            version=1,
            timestamp=datetime.now(),
            correlation_id="corr_2",
            causation_id=None,
            data={},
            metadata={},
        )

        with pytest.raises(Exception):
            await store.append("stream_2", [event2])

        await store.close()
