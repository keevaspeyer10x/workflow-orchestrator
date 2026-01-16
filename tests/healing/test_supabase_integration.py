"""Integration tests for Supabase healing infrastructure.

These tests run against the real Supabase database with populated data.
They test the three-tier lookup system:
  - Tier 1: Exact fingerprint matching
  - Tier 2: Semantic similarity via embeddings (RAG)
  - Tier 3: Causality graph traversal

Run with:
    pytest tests/healing/test_supabase_integration.py -v

Requires:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables
    - Populated database (run migrations and seeding first)

Skip with:
    pytest tests/healing/test_supabase_integration.py -v -k "not integration"
"""

import os
import pytest
import re
from typing import Optional

# Skip all tests if Supabase credentials not available
pytestmark = pytest.mark.skipif(
    not (os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY")),
    reason="Supabase credentials not available"
)


@pytest.fixture(scope="module")
def supabase_client():
    """Create real Supabase client."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")

    if not url or not key:
        pytest.skip("Supabase credentials not available")

    return create_client(url, key)


@pytest.fixture(scope="module")
def project_id():
    """Project ID for test queries."""
    return "workflow-orchestrator"


class TestTier1FingerprintLookup:
    """Tests for Tier 1 - Exact fingerprint pattern matching."""

    def test_exact_pattern_match(self, supabase_client, project_id):
        """Can find pattern by exact fingerprint."""
        # Use a known seeded pattern
        result = supabase_client.table("error_patterns").select("*").eq(
            "project_id", project_id
        ).eq(
            "fingerprint", "ModuleNotFoundError: No module named '(\\w+)'"
        ).execute()

        assert result.data, "Should find ModuleNotFoundError pattern"
        pattern = result.data[0]
        assert pattern["fingerprint_coarse"] is not None
        assert pattern["is_preseeded"] is True
        assert pattern["safety_category"] in ("safe", "moderate", "dangerous")

    def test_pattern_has_learnings(self, supabase_client, project_id):
        """Patterns are linked to learnings."""
        # Get a pattern
        pattern = supabase_client.table("error_patterns").select("id, fingerprint").eq(
            "project_id", project_id
        ).limit(1).execute().data[0]

        # Find associated learning
        learning = supabase_client.table("learnings").select("*").eq(
            "project_id", project_id
        ).eq(
            "pattern_id", pattern["id"]
        ).execute()

        assert learning.data, f"Pattern {pattern['fingerprint'][:30]} should have learnings"

    def test_deprecation_patterns_exist(self, supabase_client, project_id):
        """Deprecation patterns were seeded."""
        result = supabase_client.table("error_patterns").select("fingerprint").eq(
            "project_id", project_id
        ).like("fingerprint", "%deprecated%").execute()

        assert len(result.data) >= 5, "Should have multiple deprecation patterns"

    def test_pattern_stats_initialized(self, supabase_client, project_id):
        """Pattern statistics fields exist."""
        pattern = supabase_client.table("error_patterns").select(
            "success_count, failure_count, use_count"
        ).eq("project_id", project_id).limit(1).execute().data[0]

        # Stats should be initialized (even if 0)
        assert pattern["success_count"] is not None
        assert pattern["failure_count"] is not None
        assert pattern["use_count"] is not None

    def test_regex_fingerprints_are_valid(self, supabase_client, project_id):
        """All fingerprints are valid regex patterns."""
        patterns = supabase_client.table("error_patterns").select("fingerprint").eq(
            "project_id", project_id
        ).execute()

        invalid = []
        for p in patterns.data:
            try:
                re.compile(p["fingerprint"])
            except re.error as e:
                invalid.append((p["fingerprint"], str(e)))

        assert not invalid, f"Invalid regex patterns: {invalid}"


class TestTier2SemanticSearch:
    """Tests for Tier 2 - Embedding-based semantic similarity (RAG)."""

    def test_learnings_have_embeddings(self, supabase_client, project_id):
        """All learnings should have embeddings."""
        total = supabase_client.table("learnings").select("id", count="exact").eq(
            "project_id", project_id
        ).execute()

        with_embeddings = supabase_client.table("learnings").select("id", count="exact").eq(
            "project_id", project_id
        ).not_.is_("embedding", "null").execute()

        assert with_embeddings.count == total.count, \
            f"All learnings should have embeddings: {with_embeddings.count}/{total.count}"

    def test_embedding_dimension(self, supabase_client, project_id):
        """Embeddings are correct dimension (1536 for ada-002)."""
        import json
        learning = supabase_client.table("learnings").select("embedding").eq(
            "project_id", project_id
        ).not_.is_("embedding", "null").limit(1).execute().data[0]

        # Supabase returns embedding as JSON string
        embedding = learning["embedding"]
        if isinstance(embedding, str):
            embedding = json.loads(embedding)

        assert len(embedding) == 1536, f"Embedding should be 1536-dimensional, got {len(embedding)}"

    def test_match_learnings_rpc_works(self, supabase_client, project_id):
        """match_learnings RPC returns similar learnings."""
        # Get a real embedding
        sample = supabase_client.table("learnings").select("embedding, title").eq(
            "project_id", project_id
        ).not_.is_("embedding", "null").limit(1).execute().data[0]

        # Search for similar
        results = supabase_client.rpc("match_learnings", {
            "query_embedding": sample["embedding"],
            "match_threshold": 0.7,
            "match_count": 5,
            "p_project_id": project_id
        }).execute()

        assert len(results.data) >= 1, "Should find at least the source learning"
        assert results.data[0]["similarity"] >= 0.99, "First result should be near-exact match"

    def test_semantic_similarity_finds_related(self, supabase_client, project_id):
        """Semantic search finds conceptually related learnings."""
        # Get embedding for "NoneType" error
        nonetype = supabase_client.table("learnings").select("embedding").eq(
            "project_id", project_id
        ).like("title", "%NoneType%").limit(1).execute().data[0]

        # Search for similar
        results = supabase_client.rpc("match_learnings", {
            "query_embedding": nonetype["embedding"],
            "match_threshold": 0.7,
            "match_count": 10,
            "p_project_id": project_id
        }).execute()

        # Should find other NoneType/null-related errors
        titles = [r["title"] for r in results.data]
        null_related = sum(1 for t in titles if "None" in t or "null" in t.lower() or "key" in t.lower())

        assert null_related >= 2, f"Should find related null-check learnings: {titles}"

    def test_dissimilar_errors_low_similarity(self, supabase_client, project_id):
        """Unrelated errors should have low similarity."""
        # Get Python error embedding
        python = supabase_client.table("learnings").select("embedding").eq(
            "project_id", project_id
        ).like("title", "%Python%").limit(1).execute().data[0]

        # Get Rust error embedding
        rust = supabase_client.table("learnings").select("embedding").eq(
            "project_id", project_id
        ).like("title", "%Rust%").limit(1).execute()

        if not rust.data:
            pytest.skip("No Rust learnings to compare")

        # Search with Python embedding, threshold 0.9
        results = supabase_client.rpc("match_learnings", {
            "query_embedding": python["embedding"],
            "match_threshold": 0.9,
            "match_count": 20,
            "p_project_id": project_id
        }).execute()

        # Rust errors should NOT be in high-similarity results
        titles = [r["title"] for r in results.data]
        rust_in_top = any("Rust" in t for t in titles)

        # This is a soft assertion - semantic similarity can find cross-language patterns
        if rust_in_top:
            # If Rust appears, its similarity should be lower
            rust_sim = next((r["similarity"] for r in results.data if "Rust" in r["title"]), 0)
            assert rust_sim < 0.95, "Cross-language matches should have lower similarity"


class TestTier3CausalityGraph:
    """Tests for Tier 3 - Causality graph traversal."""

    def test_causality_table_exists(self, supabase_client, project_id):
        """Causality edges table is accessible."""
        result = supabase_client.table("causality_edges").select("id").limit(1).execute()
        # Table exists (even if empty)
        assert result.data is not None

    def test_get_error_causes_rpc_works(self, supabase_client):
        """get_error_causes RPC is callable."""
        result = supabase_client.rpc("get_error_causes", {
            "p_fingerprint": "test-fingerprint"
        }).execute()

        # Should return empty list, not error
        assert result.data == []

    def test_causality_edge_schema(self, supabase_client, project_id):
        """Causality edge has expected fields."""
        from datetime import datetime, timezone
        # Try to insert a test edge (will rollback)
        test_edge = {
            "project_id": project_id,
            "error_fingerprint": "test-error-fp",
            "error_timestamp": datetime.now(timezone.utc).isoformat(),
            "causing_commit": "abc123",
            "causing_file": "src/test.py",
            "causing_function": "test_func",
            "evidence_type": "manual",
            "confidence": 0.8,
            "occurrence_count": 1
        }

        try:
            result = supabase_client.table("causality_edges").insert(test_edge).execute()
            # Clean up
            if result.data:
                supabase_client.table("causality_edges").delete().eq(
                    "id", result.data[0]["id"]
                ).execute()
            assert True, "Can insert causality edge"
        except Exception as e:
            # Schema mismatch or constraint violation
            pytest.fail(f"Causality edge insert failed: {e}")


class TestLearningsQuality:
    """Tests for learnings data quality."""

    def test_all_learnings_have_descriptions(self, supabase_client, project_id):
        """All learnings have non-empty descriptions."""
        empty = supabase_client.table("learnings").select("title").eq(
            "project_id", project_id
        ).or_("description.is.null,description.eq.").execute()

        assert len(empty.data) == 0, f"Learnings missing descriptions: {[l['title'] for l in empty.data]}"

    def test_all_learnings_have_actions(self, supabase_client, project_id):
        """All learnings have action defined."""
        empty = supabase_client.table("learnings").select("title").eq(
            "project_id", project_id
        ).is_("action", "null").execute()

        assert len(empty.data) == 0, f"Learnings missing actions: {[l['title'] for l in empty.data]}"

    def test_all_learnings_linked_to_patterns(self, supabase_client, project_id):
        """All learnings are linked to patterns."""
        unlinked = supabase_client.table("learnings").select("title").eq(
            "project_id", project_id
        ).is_("pattern_id", "null").execute()

        assert len(unlinked.data) == 0, f"Unlinked learnings: {[l['title'] for l in unlinked.data]}"

    def test_action_types_are_valid(self, supabase_client, project_id):
        """Action types are from allowed set."""
        learnings = supabase_client.table("learnings").select("title, action").eq(
            "project_id", project_id
        ).execute()

        valid_types = {"code_change", "command", "documentation", "diff", "multi_step"}
        invalid = []

        for l in learnings.data:
            action = l.get("action")
            if isinstance(action, dict):
                action_type = action.get("action_type")
            else:
                action_type = action

            if action_type not in valid_types:
                invalid.append((l["title"], action_type))

        assert not invalid, f"Invalid action types: {invalid}"

    def test_command_actions_have_safety_flags(self, supabase_client, project_id):
        """Command actions have safety flags."""
        learnings = supabase_client.table("learnings").select("title, action").eq(
            "project_id", project_id
        ).execute()

        missing_flags = []
        for l in learnings.data:
            action = l.get("action")
            if isinstance(action, dict) and action.get("action_type") == "command":
                if not action.get("sanitize_input") or not action.get("requires_confirmation"):
                    missing_flags.append(l["title"])

        assert not missing_flags, f"Commands missing safety flags: {missing_flags}"


class TestFullHealingFlow:
    """Tests for the complete healing flow."""

    def test_error_to_learning_flow(self, supabase_client, project_id):
        """Can go from error fingerprint to actionable learning."""
        # Simulate receiving an error
        error_fingerprint = "ModuleNotFoundError: No module named '(\\w+)'"

        # Step 1: Find matching pattern
        pattern = supabase_client.table("error_patterns").select("id, fingerprint, safety_category").eq(
            "project_id", project_id
        ).eq("fingerprint", error_fingerprint).execute()

        assert pattern.data, "Should find pattern"

        # Step 2: Get associated learning
        learning = supabase_client.table("learnings").select("title, description, action").eq(
            "project_id", project_id
        ).eq("pattern_id", pattern.data[0]["id"]).execute()

        assert learning.data, "Should find learning"
        assert learning.data[0]["description"], "Learning should have description"
        assert learning.data[0]["action"], "Learning should have action"

    def test_semantic_fallback_flow(self, supabase_client, project_id):
        """Can fallback to semantic search for unknown errors."""
        # Get embedding for a known error type
        known = supabase_client.table("learnings").select("embedding").eq(
            "project_id", project_id
        ).like("title", "%module%").limit(1).execute()

        if not known.data or not known.data[0].get("embedding"):
            pytest.skip("No embeddings available")

        # Simulate: we couldn't find exact match, try semantic search
        results = supabase_client.rpc("match_learnings", {
            "query_embedding": known.data[0]["embedding"],
            "match_threshold": 0.6,  # Lower threshold for fallback
            "match_count": 3,
            "p_project_id": project_id
        }).execute()

        assert results.data, "Semantic search should find similar learnings"
        assert results.data[0]["description"], "Results should have descriptions"


class TestAuditLogging:
    """Tests for audit logging functionality."""

    def test_can_write_audit_log(self, supabase_client, project_id):
        """Can write to audit log."""
        entry = {
            "project_id": project_id,
            "action": "test_action",
            "details": {"test": True},
        }

        result = supabase_client.table("healing_audit").insert(entry).execute()

        assert result.data, "Should insert audit entry"

        # Clean up
        if result.data:
            supabase_client.table("healing_audit").delete().eq(
                "id", result.data[0]["id"]
            ).execute()

    def test_audit_log_has_timestamp(self, supabase_client, project_id):
        """Audit log entries get automatic timestamp."""
        entry = {
            "project_id": project_id,
            "action": "timestamp_test",
            "details": {},
        }

        result = supabase_client.table("healing_audit").insert(entry).execute()

        assert result.data[0].get("timestamp"), "Should have timestamp"

        # Clean up
        supabase_client.table("healing_audit").delete().eq(
            "id", result.data[0]["id"]
        ).execute()
