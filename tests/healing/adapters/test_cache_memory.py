"""Tests for in-memory cache adapter."""

import pytest
import time


class TestInMemoryCache:
    """Test InMemoryCache functionality."""

    @pytest.fixture
    def cache(self):
        """Create an InMemoryCache instance."""
        from src.healing.adapters.cache_memory import InMemoryCache

        return InMemoryCache()

    @pytest.mark.asyncio
    async def test_get_existing_key(self, cache):
        """CAM-001: get() should return cached value for existing key."""
        await cache.set("test_key", {"value": "test_data"}, ttl_seconds=60)
        result = await cache.get("test_key")

        assert result is not None
        assert result["value"] == "test_data"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, cache):
        """CAM-002: get() should return None for non-existent key."""
        result = await cache.get("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_new_key(self, cache):
        """CAM-003: set() should store value with TTL."""
        await cache.set("new_key", {"data": "value"}, ttl_seconds=3600)

        result = await cache.get("new_key")
        assert result is not None
        assert result["data"] == "value"

    @pytest.mark.asyncio
    async def test_get_expired_key(self, cache):
        """CAM-004: get() should return None for expired key."""
        await cache.set("expiring_key", {"data": "value"}, ttl_seconds=1)

        # Wait for expiry
        time.sleep(1.1)

        result = await cache.get("expiring_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_existing_key(self, cache):
        """CAM-005: delete() should remove existing key."""
        await cache.set("to_delete", {"data": "value"}, ttl_seconds=60)
        await cache.delete("to_delete")

        result = await cache.get("to_delete")
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_cleanup(self, cache):
        """CAM-006: Old entries should be cleaned up."""
        # Add entries with short TTL
        await cache.set("expire1", {"data": 1}, ttl_seconds=1)
        await cache.set("expire2", {"data": 2}, ttl_seconds=1)
        await cache.set("keep", {"data": 3}, ttl_seconds=3600)

        # Wait for expiry
        time.sleep(1.1)

        # Trigger cleanup (implementation-specific)
        # Most in-memory caches clean up on get or periodically
        await cache.get("expire1")
        await cache.get("expire2")

        # Verify expired entries are cleaned
        assert await cache.get("expire1") is None
        assert await cache.get("expire2") is None
        assert await cache.get("keep") is not None
