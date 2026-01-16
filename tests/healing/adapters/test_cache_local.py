"""Tests for local SQLite cache adapter."""

import pytest
import tempfile
import time
from pathlib import Path


class TestLocalSQLiteCache:
    """Test LocalSQLiteCache functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, temp_dir):
        """Create a LocalSQLiteCache instance."""
        from src.healing.adapters.cache_local import LocalSQLiteCache

        return LocalSQLiteCache(path=temp_dir / "test_cache.sqlite")

    @pytest.mark.asyncio
    async def test_get_existing_key(self, cache):
        """CAL-001: get() should return cached value for existing key."""
        await cache.set("test_key", {"value": "test_data"}, ttl_seconds=60)
        result = await cache.get("test_key")

        assert result is not None
        assert result["value"] == "test_data"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache):
        """CAL-002: get() should return None for non-existent key."""
        result = await cache.get("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_new_key(self, cache):
        """CAL-003: set() should store value with TTL."""
        await cache.set("new_key", {"data": "value"}, ttl_seconds=3600)

        result = await cache.get("new_key")
        assert result is not None
        assert result["data"] == "value"

    @pytest.mark.asyncio
    async def test_set_existing_key(self, cache):
        """CAL-004: set() should update existing key."""
        await cache.set("key", {"version": 1}, ttl_seconds=60)
        await cache.set("key", {"version": 2}, ttl_seconds=60)

        result = await cache.get("key")
        assert result["version"] == 2

    @pytest.mark.asyncio
    async def test_get_expired_key(self, cache):
        """CAL-005: get() should return None for expired key."""
        await cache.set("expiring_key", {"data": "value"}, ttl_seconds=1)

        # Wait for expiry
        time.sleep(1.1)

        result = await cache.get("expiring_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache):
        """CAL-006: delete() should remove existing key."""
        await cache.set("to_delete", {"data": "value"}, ttl_seconds=60)
        await cache.delete("to_delete")

        result = await cache.get("to_delete")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache):
        """CAL-007: delete() should not raise error for non-existent key."""
        # Should not raise
        await cache.delete("nonexistent_key")

    @pytest.mark.asyncio
    async def test_concurrent_access(self, cache):
        """CAL-008: Concurrent access should not cause deadlocks."""
        import asyncio

        async def write_task(key: str, value: int):
            await cache.set(key, {"value": value}, ttl_seconds=60)
            await cache.get(key)

        # Run multiple concurrent operations
        tasks = [write_task(f"key_{i}", i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all writes succeeded
        for i in range(10):
            result = await cache.get(f"key_{i}")
            assert result is not None
