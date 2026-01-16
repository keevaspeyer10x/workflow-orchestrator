"""Healing Client - Phase 2 Pattern Memory & Lookup.

Unified client that provides three-tier lookup for error patterns.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .supabase_client import HealingSupabaseClient
    from .embeddings import EmbeddingService
    from .adapters.base import CacheAdapter
    from .models import ErrorEvent


logger = logging.getLogger(__name__)


@dataclass
class LookupResult:
    """Result of a three-tier pattern lookup.

    Attributes:
        tier: Which tier found the result (1, 2, 3, or None)
        pattern: The pattern data if found
        source: Where the result came from ('cache', 'supabase', 'rag', 'none')
        causes: Causality edges if tier 3 was reached
    """

    tier: Optional[int]
    pattern: Optional[dict]
    source: str
    causes: list[dict] = field(default_factory=list)


class HealingClient:
    """Unified client for pattern lookup and management.

    This client implements three-tier lookup:
    1. Tier 1: Exact fingerprint match (cache → Supabase)
    2. Tier 2: RAG semantic search using embeddings
    3. Tier 3: Causality analysis (for investigation)

    Usage:
        client = HealingClient(supabase, cache, embeddings)
        result = await client.lookup(error)
        if result.pattern:
            # Apply the fix
        elif result.causes:
            # Investigate the causes
    """

    # Similarity threshold for Tier 2 matches
    SIMILARITY_THRESHOLD = 0.85

    def __init__(
        self,
        supabase: "HealingSupabaseClient",
        cache: Optional["CacheAdapter"] = None,
        embeddings: Optional["EmbeddingService"] = None,
    ):
        """Initialize the healing client.

        Args:
            supabase: The Supabase client for pattern storage
            cache: Optional cache adapter for local caching
            embeddings: Optional embedding service for Tier 2 lookup
        """
        self.supabase = supabase
        self.cache = cache
        self.embeddings = embeddings

    async def lookup(self, error: "ErrorEvent") -> LookupResult:
        """Perform three-tier lookup for an error.

        This method tries each tier in order:
        1. Check cache, then Supabase for exact fingerprint match
        2. Generate embedding and search for similar patterns
        3. Query causality edges

        Args:
            error: The error to look up

        Returns:
            LookupResult with the best match found
        """
        # Tier 1: Exact match
        tier1_result = await self._lookup_tier1(error)
        if tier1_result.pattern:
            return tier1_result

        # Tier 2: RAG search (if embeddings available)
        tier2_result = await self._lookup_tier2(error)
        if tier2_result.pattern:
            return tier2_result

        # Tier 3: Causality
        tier3_result = await self._lookup_tier3(error)
        return tier3_result

    async def _lookup_tier1(self, error: "ErrorEvent") -> LookupResult:
        """Tier 1: Exact fingerprint match.

        Checks cache first, then Supabase.
        """
        fingerprint = error.fingerprint
        if not fingerprint:
            return LookupResult(tier=None, pattern=None, source="none")

        # Check cache first
        if self.cache:
            try:
                cached = await self.cache.get(f"pattern:{fingerprint}")
                if cached:
                    return LookupResult(tier=1, pattern=cached, source="cache")
            except Exception as e:
                logger.warning(f"Cache lookup failed: {e}")

        # Check Supabase
        try:
            pattern = await self.supabase.lookup_pattern(fingerprint)
            if pattern:
                # Cache for future lookups
                if self.cache:
                    try:
                        await self.cache.set(f"pattern:{fingerprint}", pattern)
                    except Exception as e:
                        logger.warning(f"Cache set failed: {e}")

                return LookupResult(tier=1, pattern=pattern, source="supabase")
        except Exception as e:
            logger.warning(f"Supabase lookup failed: {e}")

        return LookupResult(tier=None, pattern=None, source="none")

    async def _lookup_tier2(self, error: "ErrorEvent") -> LookupResult:
        """Tier 2: RAG semantic search.

        Generates embedding for the error and searches for similar patterns.
        """
        # Check if embeddings are available
        if not self.embeddings or not self.embeddings.available:
            return LookupResult(tier=None, pattern=None, source="none")

        try:
            # Generate embedding
            embedding = await self.embeddings.embed_error(error)
            if not embedding:
                return LookupResult(tier=None, pattern=None, source="none")

            # Search for similar patterns
            similar = await self.supabase.lookup_similar(embedding)

            if similar and len(similar) > 0:
                # Check if top result is above threshold
                top_result = similar[0]
                similarity = top_result.get("similarity", 0)

                if similarity >= self.SIMILARITY_THRESHOLD:
                    return LookupResult(
                        tier=2,
                        pattern=top_result,
                        source="rag",
                    )
        except Exception as e:
            logger.warning(f"Tier 2 lookup failed: {e}")

        return LookupResult(tier=None, pattern=None, source="none")

    async def _lookup_tier3(self, error: "ErrorEvent") -> LookupResult:
        """Tier 3: Causality analysis.

        Returns causality edges for investigation (no pattern/fix).
        """
        fingerprint = error.fingerprint
        if not fingerprint:
            return LookupResult(tier=None, pattern=None, source="none", causes=[])

        try:
            causes = await self.supabase.get_causes(fingerprint)

            if causes:
                return LookupResult(
                    tier=3,
                    pattern=None,
                    source="causality",
                    causes=causes,
                )
        except Exception as e:
            logger.warning(f"Tier 3 lookup failed: {e}")

        return LookupResult(tier=None, pattern=None, source="none", causes=[])

    async def record_fix_result(
        self,
        error: "ErrorEvent",
        success: bool,
    ) -> None:
        """Record the result of applying a fix.

        This updates pattern statistics in Supabase.

        Args:
            error: The error that was fixed
            success: Whether the fix was successful
        """
        if not error.fingerprint:
            return

        try:
            await self.supabase.record_fix_result(error.fingerprint, success)
        except Exception as e:
            logger.error(f"Failed to record fix result: {e}")

    async def get_stats(self) -> dict:
        """Get statistics about the healing system.

        Returns:
            Dict with pattern counts and other metrics
        """
        try:
            return await self.supabase.get_stats()
        except Exception as e:
            logger.warning(f"Failed to get stats: {e}")
            return {"pattern_count": 0}
