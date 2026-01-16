"""In-memory cache adapter."""

import time
from typing import Optional

from .base import CacheAdapter


class InMemoryCache(CacheAdapter):
    """In-memory cache for cloud environments (session-scoped)."""

    def __init__(self):
        """Initialize in-memory cache."""
        self._cache: dict[str, tuple[dict, float]] = {}  # key -> (value, expires_at)

    async def get(self, key: str) -> Optional[dict]:
        """Get cached value from memory."""
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]
        if time.time() > expires_at:
            # Expired, delete it
            del self._cache[key]
            return None

        return value

    async def set(self, key: str, value: dict, ttl_seconds: int = 3600) -> None:
        """Set cached value in memory."""
        expires_at = time.time() + ttl_seconds
        self._cache[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        """Delete cached value from memory."""
        self._cache.pop(key, None)

    async def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of deleted entries."""
        now = time.time()
        expired_keys = [
            key for key, (_, expires_at) in self._cache.items() if expires_at < now
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
