"""Cache Optimizer - Phase 5 Observability & Hardening.

Optimizes local cache performance by pre-loading frequently used patterns.

Only runs in LOCAL environments (no benefit in cloud where there's no local cache).
"""

from typing import Optional, TYPE_CHECKING

from .environment import ENVIRONMENT, Environment

if TYPE_CHECKING:
    from .client import HealingClient
    from .adapters.base import CacheAdapter


class CacheOptimizer:
    """Optimize local cache for frequently accessed patterns.

    Usage:
        optimizer = CacheOptimizer(healing_client)
        count = await optimizer.warm_cache()
        print(f"Pre-loaded {count} patterns into cache")
    """

    # Number of top patterns to cache
    DEFAULT_CACHE_LIMIT = 100

    # Cache TTL (24 hours)
    CACHE_TTL_SECONDS = 86400

    def __init__(self, client: "HealingClient"):
        self.client = client

    async def warm_cache(self, limit: int = None) -> int:
        """Pre-load frequently used patterns into local cache.

        This improves lookup performance by avoiding Supabase queries
        for the most common patterns.

        Args:
            limit: Maximum number of patterns to cache (default: 100)

        Returns:
            Number of patterns cached
        """
        # Only warm cache in local environments
        if ENVIRONMENT != Environment.LOCAL:
            return 0

        # Check if we have a cache adapter
        if not self.client.cache:
            return 0

        limit = limit or self.DEFAULT_CACHE_LIMIT

        try:
            # Get top patterns from Supabase
            top_patterns = await self.client.supabase.get_top_patterns(limit)

            cached_count = 0
            for pattern in top_patterns:
                fingerprint = pattern.get("fingerprint")
                if fingerprint:
                    try:
                        await self.client.cache.set(
                            f"pattern:{fingerprint}",
                            pattern,
                            ttl_seconds=self.CACHE_TTL_SECONDS
                        )
                        cached_count += 1
                    except Exception:
                        # Continue on individual cache failures
                        pass

            return cached_count
        except Exception:
            return 0

    async def get_cache_stats(self) -> dict:
        """Get statistics about cache usage.

        Returns:
            Dict with cache statistics
        """
        if not self.client.cache:
            return {"enabled": False}

        try:
            # Try to get cache-specific stats
            if hasattr(self.client.cache, "get_stats"):
                return await self.client.cache.get_stats()

            return {"enabled": True, "type": type(self.client.cache).__name__}
        except Exception:
            return {"enabled": True, "error": "Could not retrieve stats"}

    async def clear_cache(self) -> None:
        """Clear the local cache.

        Useful for debugging or when patterns have been updated.
        """
        if not self.client.cache:
            return

        try:
            if hasattr(self.client.cache, "clear"):
                await self.client.cache.clear()
        except Exception:
            pass

    async def invalidate_pattern(self, fingerprint: str) -> None:
        """Invalidate a specific pattern in the cache.

        Args:
            fingerprint: Pattern fingerprint to invalidate
        """
        if not self.client.cache:
            return

        try:
            await self.client.cache.delete(f"pattern:{fingerprint}")
        except Exception:
            pass
