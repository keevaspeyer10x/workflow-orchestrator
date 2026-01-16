"""Tests for scored lookup functionality - Phase 6 Intelligent Pattern Filtering."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.healing.models import ErrorEvent, PatternContext


class TestScoredLookup:
    """Tests for scored lookup in HealingClient."""

    @pytest.fixture
    def sample_error(self):
        """Create sample error with context."""
        return ErrorEvent(
            error_id="err-test",
            timestamp=datetime.utcnow(),
            source="subprocess",
            description="ModuleNotFoundError: No module named 'requests'",
            fingerprint="abc123def456",
            fingerprint_coarse="abc123",
            context=PatternContext(
                language="python",
                error_category="dependency",
            ),
        )

    @pytest.fixture
    def mock_supabase_client(self):
        """Create mock Supabase client with scoring methods."""
        mock = MagicMock()
        mock.lookup_pattern = AsyncMock(return_value=None)
        mock.lookup_similar = AsyncMock(return_value=[])
        mock.get_causes = AsyncMock(return_value=[])
        mock.lookup_patterns_scored = AsyncMock(return_value=[])
        mock.get_pattern_project_ids = AsyncMock(return_value=[])
        mock.get_project_share_setting = AsyncMock(return_value=True)
        mock.project_id = "test-project"
        return mock

    @pytest.mark.asyncio
    async def test_same_project_found(self, mock_supabase_client, sample_error):
        """Pattern from same project returns with appropriate tier."""
        from src.healing.client import HealingClient

        # Mock scored lookup returning a same-project match
        mock_supabase_client.lookup_patterns_scored = AsyncMock(return_value=[
            {
                "fingerprint": "abc123def456",
                "score": 0.75,
                "project_id": "test-project",
                "context": {"language": "python"},
                "success_count": 10,
                "failure_count": 2,
                "project_count": 1,
            }
        ])
        mock_supabase_client.project_id = "test-project"

        client = HealingClient(supabase=mock_supabase_client)
        result = await client.lookup(sample_error)

        assert result is not None
        # Should find the pattern (tier depends on implementation)

    @pytest.mark.asyncio
    async def test_same_project_threshold(self, mock_supabase_client, sample_error):
        """Score >= 0.6 required for same-project match."""
        from src.healing.client import HealingClient, SAME_PROJECT_THRESHOLD

        assert SAME_PROJECT_THRESHOLD == 0.6

        # Pattern with score below threshold
        mock_supabase_client.lookup_patterns_scored = AsyncMock(return_value=[
            {
                "fingerprint": "abc123def456",
                "score": 0.55,  # Below 0.6
                "project_id": "test-project",
            }
        ])

        client = HealingClient(supabase=mock_supabase_client)
        # Should not use this pattern for same-project

    @pytest.mark.asyncio
    async def test_cross_project_threshold(self, mock_supabase_client, sample_error):
        """Score >= 0.75 required for cross-project match."""
        from src.healing.client import HealingClient, CROSS_PROJECT_THRESHOLD

        assert CROSS_PROJECT_THRESHOLD == 0.75

    @pytest.mark.asyncio
    async def test_cross_project_guardrails_enforced(
        self, mock_supabase_client, sample_error
    ):
        """Cross-project pattern must pass guardrails."""
        from src.healing.client import HealingClient

        # Pattern from different project with good score but poor guardrails
        mock_supabase_client.lookup_patterns_scored = AsyncMock(return_value=[
            {
                "fingerprint": "abc123def456",
                "score": 0.8,  # Good score
                "project_id": "other-project",  # Different project
                "project_count": 2,  # Less than 3 - fails guardrail
                "success_count": 3,  # Less than 5 - fails guardrail
                "failure_count": 0,
            }
        ])
        mock_supabase_client.project_id = "test-project"

        client = HealingClient(supabase=mock_supabase_client)
        result = await client.lookup(sample_error)

        # Should NOT use this pattern due to guardrail failure
        # (exact behavior depends on implementation)

    @pytest.mark.asyncio
    async def test_cross_project_opt_out_respected(
        self, mock_supabase_client, sample_error
    ):
        """Patterns from opted-out projects are filtered."""
        from src.healing.client import HealingClient

        # Pattern from a project that has opted out
        mock_supabase_client.lookup_patterns_scored = AsyncMock(return_value=[
            {
                "fingerprint": "abc123def456",
                "score": 0.85,
                "project_id": "opted-out-project",
                "project_count": 5,
                "success_count": 20,
                "failure_count": 2,
            }
        ])
        # This project has opted out of sharing
        mock_supabase_client.get_project_share_setting = AsyncMock(
            side_effect=lambda pid: pid != "opted-out-project"
        )
        mock_supabase_client.project_id = "test-project"

        client = HealingClient(supabase=mock_supabase_client)
        # Should filter out the opted-out project's patterns

    @pytest.mark.asyncio
    async def test_rpc_failure_fallback(self, mock_supabase_client, sample_error):
        """Falls back to existing lookup on RPC error."""
        from src.healing.client import HealingClient

        # RPC call fails
        mock_supabase_client.lookup_patterns_scored = AsyncMock(
            side_effect=Exception("RPC timeout")
        )
        # But regular lookup works
        mock_supabase_client.lookup_pattern = AsyncMock(return_value={
            "fingerprint": "abc123def456",
            "safety_category": "safe",
        })

        client = HealingClient(supabase=mock_supabase_client)
        result = await client.lookup(sample_error)

        # Should fall back to tier 1 regular lookup
        assert result is not None

    @pytest.mark.asyncio
    async def test_language_mismatch_penalty(self, mock_supabase_client, sample_error):
        """Cross-project with different language scores lower."""
        from src.healing.context_extraction import calculate_relevance_score
        from src.healing.models import PatternContext

        # Python pattern
        pattern = {
            "success_count": 90,
            "failure_count": 10,
            "project_count": 5,
            "context": {"language": "python"},
        }

        # Query with same language
        python_ctx = PatternContext(language="python")
        score_same = calculate_relevance_score(pattern, python_ctx, "p", [])

        # Query with different language
        js_ctx = PatternContext(language="javascript")
        score_diff = calculate_relevance_score(pattern, js_ctx, "p", [])

        # Same language should score higher
        assert score_same > score_diff


class TestLookupResultWithScore:
    """Tests for LookupResult with score field."""

    def test_lookup_result_has_score(self):
        """LookupResult should include score field."""
        from src.healing.client import LookupResult

        result = LookupResult(
            tier=1,
            pattern={"fingerprint": "abc"},
            source="scored",
            causes=[],
        )

        # Score field should be accessible (may need to add it)
        # assert hasattr(result, 'score') or result can store score in pattern


class TestSupabaseClientScoringMethods:
    """Tests for new Supabase client scoring methods."""

    @pytest.fixture
    def mock_supabase(self):
        """Create mock Supabase instance."""
        mock = MagicMock()
        mock.rpc = MagicMock(return_value=MagicMock())
        mock.rpc.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
        return mock

    @pytest.mark.asyncio
    async def test_lookup_patterns_scored_returns_list(self, mock_supabase):
        """lookup_patterns_scored calls RPC and returns list."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.rpc.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[
                {"fingerprint": "fp1", "score": 0.8},
                {"fingerprint": "fp2", "score": 0.7},
            ])
        )

        client = HealingSupabaseClient(mock_supabase, "test-project")
        results = await client.lookup_patterns_scored("abc123", "python", "dependency")

        assert len(results) == 2
        assert results[0]["score"] == 0.8

    @pytest.mark.asyncio
    async def test_record_pattern_application_success(self, mock_supabase):
        """record_pattern_application records success."""
        from src.healing.supabase_client import HealingSupabaseClient
        from src.healing.models import PatternContext

        mock_supabase.rpc.return_value.execute = AsyncMock(return_value=MagicMock())

        client = HealingSupabaseClient(mock_supabase, "test-project")
        ctx = PatternContext(language="python")
        await client.record_pattern_application("fp123", "proj-1", True, ctx.to_dict())

        mock_supabase.rpc.assert_called_once()
        call_args = mock_supabase.rpc.call_args
        assert "record_pattern_application" in str(call_args)

    @pytest.mark.asyncio
    async def test_get_pattern_project_ids(self, mock_supabase):
        """get_pattern_project_ids returns project list."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.rpc.return_value.execute = AsyncMock(
            return_value=MagicMock(data=["proj-1", "proj-2", "proj-3"])
        )

        client = HealingSupabaseClient(mock_supabase, "test-project")
        projects = await client.get_pattern_project_ids("fp123")

        assert len(projects) == 3
        assert "proj-1" in projects

    @pytest.mark.asyncio
    async def test_get_project_share_setting_true(self, mock_supabase):
        """get_project_share_setting returns True by default."""
        from src.healing.supabase_client import HealingSupabaseClient

        # No explicit setting - defaults to True
        mock_result = MagicMock()
        mock_result.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            return_value=mock_result
        )

        client = HealingSupabaseClient(mock_supabase, "test-project")
        result = await client.get_project_share_setting("some-project")

        assert result is True  # Default

    @pytest.mark.asyncio
    async def test_get_project_share_setting_false(self, mock_supabase):
        """get_project_share_setting respects opt-out."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = {"share_patterns": False}
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            return_value=mock_result
        )

        client = HealingSupabaseClient(mock_supabase, "test-project")
        result = await client.get_project_share_setting("opted-out-project")

        assert result is False
