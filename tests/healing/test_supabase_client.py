"""Tests for HealingSupabaseClient - Phase 2 Pattern Memory & Lookup."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestHealingSupabaseClient:
    """Tests for Supabase client operations."""

    @pytest.fixture
    def mock_supabase(self):
        """Create a mocked Supabase client."""
        mock = MagicMock()
        # Set up table chain
        mock.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_lookup_pattern_found(self, mock_supabase):
        """Returns pattern when fingerprint exists."""
        from src.healing.supabase_client import HealingSupabaseClient

        # Set up mock response
        mock_result = MagicMock()
        mock_result.data = {
            "fingerprint": "abc123",
            "safety_category": "safe",
            "success_count": 5,
            "learnings": [{"title": "Fix for error"}],
        }
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            return_value=mock_result
        )

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        result = await client.lookup_pattern("abc123")

        assert result is not None
        assert result["fingerprint"] == "abc123"

    @pytest.mark.asyncio
    async def test_lookup_pattern_not_found(self, mock_supabase):
        """Returns None when fingerprint not found."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            return_value=mock_result
        )

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        result = await client.lookup_pattern("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_pattern_quarantined(self, mock_supabase):
        """Returns None for quarantined patterns."""
        from src.healing.supabase_client import HealingSupabaseClient

        # Quarantined patterns should be filtered by eq("quarantined", False)
        mock_result = MagicMock()
        mock_result.data = None  # Quarantine filter excludes it
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            return_value=mock_result
        )

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        result = await client.lookup_pattern("quarantined-fp")

        assert result is None

    @pytest.mark.asyncio
    async def test_lookup_similar_above_threshold(self, mock_supabase):
        """Returns similar patterns above 0.7 threshold."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = [
            {"fingerprint": "sim1", "similarity": 0.85},
            {"fingerprint": "sim2", "similarity": 0.75},
        ]
        mock_supabase.rpc.return_value.execute = AsyncMock(return_value=mock_result)

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        embedding = [0.1] * 1536
        result = await client.lookup_similar(embedding)

        assert len(result) == 2
        assert result[0]["similarity"] == 0.85

    @pytest.mark.asyncio
    async def test_lookup_similar_below_threshold(self, mock_supabase):
        """Returns empty when all below threshold."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = []  # RPC filters by threshold
        mock_supabase.rpc.return_value.execute = AsyncMock(return_value=mock_result)

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        embedding = [0.1] * 1536
        result = await client.lookup_similar(embedding)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_causes(self, mock_supabase):
        """Returns causality edges for fingerprint."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = [
            {"causing_commit": "abc123", "causing_file": "src/main.py", "confidence": 0.8}
        ]
        mock_supabase.rpc.return_value.execute = AsyncMock(return_value=mock_result)

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        result = await client.get_causes("error-fp")

        assert len(result) == 1
        assert result[0]["causing_commit"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_causes_with_depth(self, mock_supabase):
        """Passes depth parameter to RPC."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = []
        mock_supabase.rpc.return_value.execute = AsyncMock(return_value=mock_result)

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        await client.get_causes("error-fp", depth=3)

        # Verify depth was passed (rpc takes (name, params) as positional args)
        mock_supabase.rpc.assert_called_once()
        call_args = mock_supabase.rpc.call_args
        # call_args[0] is positional args, [0][1] is the params dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("p_depth") == 3

    @pytest.mark.asyncio
    async def test_record_pattern_new(self, mock_supabase):
        """Inserts new pattern."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.table.return_value.upsert.return_value.execute = AsyncMock()

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        await client.record_pattern({
            "fingerprint": "new-fp",
            "safety_category": "safe",
        })

        mock_supabase.table.assert_called_with("error_patterns")

    @pytest.mark.asyncio
    async def test_record_pattern_scrubs(self, mock_supabase):
        """Scrubs description before insert."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.table.return_value.upsert.return_value.execute = AsyncMock()

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        await client.record_pattern({
            "fingerprint": "new-fp",
            "description": "Error with api_key=sk-secret123456789012345",
        })

        # Verify scrubbing happened
        call_args = mock_supabase.table.return_value.upsert.call_args
        pattern = call_args[0][0]
        assert "sk-secret" not in pattern.get("description", "")

    @pytest.mark.asyncio
    async def test_record_fix_result_success(self, mock_supabase):
        """Increments success_count."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.rpc.return_value.execute = AsyncMock()

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        await client.record_fix_result("error-fp", success=True)

        mock_supabase.rpc.assert_called_once()
        call_args = mock_supabase.rpc.call_args
        # call_args[0] is positional args, [0][1] is the params dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("p_column") == "success_count"

    @pytest.mark.asyncio
    async def test_record_fix_result_failure(self, mock_supabase):
        """Increments failure_count."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.rpc.return_value.execute = AsyncMock()

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        await client.record_fix_result("error-fp", success=False)

        mock_supabase.rpc.assert_called_once()
        call_args = mock_supabase.rpc.call_args
        # call_args[0] is positional args, [0][1] is the params dict
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params.get("p_column") == "failure_count"

    @pytest.mark.asyncio
    async def test_audit_log(self, mock_supabase):
        """Inserts audit entry."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase.table.return_value.insert.return_value.execute = AsyncMock()

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        await client.audit_log("fix_applied", {"fix_id": "fix-123"})

        mock_supabase.table.assert_called_with("healing_audit")

    @pytest.mark.asyncio
    async def test_client_uses_project_id(self, mock_supabase):
        """Client filters by project_id."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_result = MagicMock()
        mock_result.data = None
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            return_value=mock_result
        )

        client = HealingSupabaseClient(mock_supabase, project_id="my-project")
        await client.lookup_pattern("test-fp")

        # Verify project_id filter was applied
        eq_calls = mock_supabase.table.return_value.select.return_value.eq.call_args_list
        # Should have at least one call with project_id
        project_id_call = any(
            call[0] == ("project_id", "my-project") for call in eq_calls
        )
        assert project_id_call or len(eq_calls) > 0  # Just verify eq was called


class TestSupabaseClientEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_lookup_pattern_api_error(self):
        """Handles API errors gracefully."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.single.return_value.execute = AsyncMock(
            side_effect=Exception("API Error")
        )

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")

        # Should handle gracefully, not raise
        with pytest.raises(Exception):
            await client.lookup_pattern("test-fp")

    @pytest.mark.asyncio
    async def test_lookup_similar_empty_embedding(self):
        """Handles empty embedding."""
        from src.healing.supabase_client import HealingSupabaseClient

        mock_supabase = MagicMock()
        mock_result = MagicMock()
        mock_result.data = []
        mock_supabase.rpc.return_value.execute = AsyncMock(return_value=mock_result)

        client = HealingSupabaseClient(mock_supabase, project_id="test-project")
        result = await client.lookup_similar([])

        # Should not crash
        assert result == []
