"""Tests for HealingClient - Phase 2 Pattern Memory & Lookup."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestHealingClientLookup:
    """Tests for three-tier lookup functionality."""

    @pytest.fixture
    def mock_supabase_client(self):
        """Create mock Supabase client."""
        mock = MagicMock()
        mock.lookup_pattern = AsyncMock(return_value=None)
        mock.lookup_similar = AsyncMock(return_value=[])
        mock.get_causes = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_cache(self):
        """Create mock cache adapter."""
        mock = MagicMock()
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        return mock

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        mock = MagicMock()
        mock.available = True
        mock.embed_error = AsyncMock(return_value=[0.1] * 1536)
        return mock

    @pytest.fixture
    def sample_error(self):
        """Create sample error for testing."""
        from src.healing.models import ErrorEvent

        return ErrorEvent(
            error_id="err-test",
            timestamp=datetime.utcnow(),
            source="subprocess",
            description="ModuleNotFoundError: No module named 'requests'",
            fingerprint="abc123def456",
            fingerprint_coarse="abc123",
        )

    @pytest.mark.asyncio
    async def test_lookup_tier1_cache_hit(
        self, mock_supabase_client, mock_cache, mock_embedding_service, sample_error
    ):
        """Returns from cache when present (Tier 1)."""
        from src.healing.client import HealingClient

        # Set up cache hit
        mock_cache.get = AsyncMock(return_value={
            "fingerprint": "abc123def456",
            "safety_category": "safe",
        })

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=mock_embedding_service,
        )
        result = await client.lookup(sample_error)

        assert result is not None
        assert result.tier == 1
        assert result.source == "cache"
        assert result.pattern is not None
        # Supabase should NOT have been called
        mock_supabase_client.lookup_pattern.assert_not_called()

    @pytest.mark.asyncio
    async def test_lookup_tier1_supabase_hit(
        self, mock_supabase_client, mock_cache, mock_embedding_service, sample_error
    ):
        """Returns from Supabase and caches (Tier 1)."""
        from src.healing.client import HealingClient

        # Cache miss, Supabase hit
        mock_cache.get = AsyncMock(return_value=None)
        mock_supabase_client.lookup_pattern = AsyncMock(return_value={
            "fingerprint": "abc123def456",
            "safety_category": "safe",
        })

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=mock_embedding_service,
        )
        result = await client.lookup(sample_error)

        assert result is not None
        assert result.tier == 1
        assert result.source == "supabase"
        # Should have cached the result
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_lookup_tier2_similar_found(
        self, mock_supabase_client, mock_cache, mock_embedding_service, sample_error
    ):
        """Falls back to RAG search when no exact match (Tier 2)."""
        from src.healing.client import HealingClient

        # Tier 1 miss
        mock_cache.get = AsyncMock(return_value=None)
        mock_supabase_client.lookup_pattern = AsyncMock(return_value=None)
        # Tier 2 hit
        mock_supabase_client.lookup_similar = AsyncMock(return_value=[
            {"fingerprint": "similar-fp", "similarity": 0.9}
        ])

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=mock_embedding_service,
        )
        result = await client.lookup(sample_error)

        assert result is not None
        assert result.tier == 2
        assert result.source == "rag"

    @pytest.mark.asyncio
    async def test_lookup_tier3_causality(
        self, mock_supabase_client, mock_cache, mock_embedding_service, sample_error
    ):
        """Returns causality edges when no pattern (Tier 3)."""
        from src.healing.client import HealingClient

        # Tier 1 & 2 miss
        mock_cache.get = AsyncMock(return_value=None)
        mock_supabase_client.lookup_pattern = AsyncMock(return_value=None)
        mock_supabase_client.lookup_similar = AsyncMock(return_value=[])
        # Tier 3 has data
        mock_supabase_client.get_causes = AsyncMock(return_value=[
            {"causing_commit": "abc123", "causing_file": "src/main.py"}
        ])

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=mock_embedding_service,
        )
        result = await client.lookup(sample_error)

        assert result is not None
        assert result.tier == 3
        assert result.pattern is None
        assert len(result.causes) == 1

    @pytest.mark.asyncio
    async def test_lookup_no_match(
        self, mock_supabase_client, mock_cache, mock_embedding_service, sample_error
    ):
        """Returns empty result when nothing found."""
        from src.healing.client import HealingClient

        # All tiers miss
        mock_cache.get = AsyncMock(return_value=None)
        mock_supabase_client.lookup_pattern = AsyncMock(return_value=None)
        mock_supabase_client.lookup_similar = AsyncMock(return_value=[])
        mock_supabase_client.get_causes = AsyncMock(return_value=[])

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=mock_embedding_service,
        )
        result = await client.lookup(sample_error)

        assert result is not None
        assert result.tier is None
        assert result.pattern is None
        assert result.causes == []
        assert result.source == "none"

    @pytest.mark.asyncio
    async def test_lookup_no_embedding_service(
        self, mock_supabase_client, mock_cache, sample_error
    ):
        """Skips Tier 2 when embedding service unavailable."""
        from src.healing.client import HealingClient

        # No embedding service
        mock_cache.get = AsyncMock(return_value=None)
        mock_supabase_client.lookup_pattern = AsyncMock(return_value=None)
        mock_supabase_client.get_causes = AsyncMock(return_value=[])

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=None,  # No embeddings
        )
        result = await client.lookup(sample_error)

        # Should skip to Tier 3
        mock_supabase_client.lookup_similar.assert_not_called()
        assert result.tier is None or result.tier == 3

    @pytest.mark.asyncio
    async def test_lookup_embedding_service_unavailable(
        self, mock_supabase_client, mock_cache, sample_error
    ):
        """Skips Tier 2 when embedding service has no API key."""
        from src.healing.client import HealingClient

        mock_embedding = MagicMock()
        mock_embedding.available = False

        mock_cache.get = AsyncMock(return_value=None)
        mock_supabase_client.lookup_pattern = AsyncMock(return_value=None)
        mock_supabase_client.get_causes = AsyncMock(return_value=[])

        client = HealingClient(
            supabase=mock_supabase_client,
            cache=mock_cache,
            embeddings=mock_embedding,
        )
        result = await client.lookup(sample_error)

        # Tier 2 should be skipped
        mock_supabase_client.lookup_similar.assert_not_called()


class TestHealingClientConcurrency:
    """Tests for concurrent lookup handling."""

    @pytest.mark.asyncio
    async def test_lookup_concurrent(self):
        """Handles multiple concurrent lookups."""
        import asyncio
        from src.healing.client import HealingClient
        from src.healing.models import ErrorEvent

        mock_supabase = MagicMock()
        mock_supabase.lookup_pattern = AsyncMock(return_value=None)
        mock_supabase.lookup_similar = AsyncMock(return_value=[])
        mock_supabase.get_causes = AsyncMock(return_value=[])

        mock_cache = MagicMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        client = HealingClient(
            supabase=mock_supabase,
            cache=mock_cache,
            embeddings=None,
        )

        errors = [
            ErrorEvent(
                error_id=f"err-{i}",
                timestamp=datetime.utcnow(),
                source="subprocess",
                description=f"Error {i}",
                fingerprint=f"fp{i}",
            )
            for i in range(5)
        ]

        # Run lookups concurrently
        results = await asyncio.gather(*[client.lookup(e) for e in errors])

        assert len(results) == 5
        assert all(r is not None for r in results)


class TestLookupResult:
    """Tests for LookupResult dataclass."""

    def test_lookup_result_creation(self):
        """LookupResult can be created with all fields."""
        from src.healing.client import LookupResult

        result = LookupResult(
            tier=1,
            pattern={"fingerprint": "abc"},
            source="cache",
            causes=[],
        )

        assert result.tier == 1
        assert result.pattern == {"fingerprint": "abc"}
        assert result.source == "cache"
        assert result.causes == []

    def test_lookup_result_no_match(self):
        """LookupResult for no match."""
        from src.healing.client import LookupResult

        result = LookupResult(
            tier=None,
            pattern=None,
            source="none",
            causes=[],
        )

        assert result.tier is None
        assert result.pattern is None
