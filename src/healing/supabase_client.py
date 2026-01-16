"""Supabase Client - Phase 2 Pattern Memory & Lookup.

Client for interacting with Supabase to store and retrieve patterns.
Implements three-tier lookup: exact match, RAG search, causality.
"""

import logging
from typing import Any, Optional

from .security import SecurityScrubber


logger = logging.getLogger(__name__)


class HealingSupabaseClient:
    """Client for healing operations in Supabase.

    This client provides:
    - Tier 1: Exact fingerprint lookup
    - Tier 2: RAG semantic search via pgvector
    - Tier 3: Causality edge queries

    All text data is scrubbed before storage.
    """

    def __init__(
        self,
        client: Any,  # Supabase client instance
        project_id: str,
    ):
        """Initialize the Supabase client.

        Args:
            client: A supabase-py client instance
            project_id: The project identifier for filtering
        """
        self.client = client
        self.project_id = project_id
        self.scrubber = SecurityScrubber()

    # ==================
    # Tier 1: Exact Match
    # ==================

    async def lookup_pattern(self, fingerprint: str) -> Optional[dict]:
        """Look up a pattern by exact fingerprint match.

        Args:
            fingerprint: The error fingerprint to look up

        Returns:
            Pattern dict with learnings, or None if not found
        """
        try:
            result = await (
                self.client.table("error_patterns")
                .select("*, learnings(*)")
                .eq("project_id", self.project_id)
                .eq("fingerprint", fingerprint)
                .eq("quarantined", False)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            logger.warning(f"Pattern lookup failed: {e}")
            raise

    # ==================
    # Tier 2: RAG Search
    # ==================

    async def lookup_similar(
        self,
        embedding: list[float],
        limit: int = 5,
        threshold: float = 0.7,
    ) -> list[dict]:
        """Find similar patterns using vector similarity.

        Args:
            embedding: The query embedding vector
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0-1)

        Returns:
            List of similar patterns with similarity scores
        """
        try:
            result = await self.client.rpc(
                "match_learnings",
                {
                    "query_embedding": embedding,
                    "match_threshold": threshold,
                    "match_count": limit,
                    "p_project_id": self.project_id,
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Similar lookup failed: {e}")
            return []

    # ==================
    # Tier 3: Causality
    # ==================

    async def get_causes(
        self,
        fingerprint: str,
        depth: int = 2,
    ) -> list[dict]:
        """Get causality edges for an error.

        Args:
            fingerprint: The error fingerprint
            depth: How many levels of causality to traverse

        Returns:
            List of causality edges
        """
        try:
            result = await self.client.rpc(
                "get_error_causes",
                {
                    "p_fingerprint": fingerprint,
                    "p_depth": depth,
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Causality lookup failed: {e}")
            return []

    # ==================
    # Write Operations
    # ==================

    async def record_pattern(self, pattern: dict) -> None:
        """Record a new error pattern.

        The pattern is scrubbed before storage to remove secrets.

        Args:
            pattern: Pattern data to store
        """
        # Scrub any text fields
        if "description" in pattern:
            pattern["description"] = self.scrubber.scrub(pattern["description"])

        # Ensure project_id is set
        pattern["project_id"] = self.project_id

        try:
            await (
                self.client.table("error_patterns")
                .upsert(pattern)
                .execute()
            )
        except Exception as e:
            logger.error(f"Failed to record pattern: {e}")
            raise

    async def record_learning(self, learning: dict) -> None:
        """Record a learning associated with a pattern.

        Args:
            learning: Learning data to store
        """
        # Ensure project_id is set
        learning["project_id"] = self.project_id

        try:
            await (
                self.client.table("learnings")
                .insert(learning)
                .execute()
            )
        except Exception as e:
            logger.error(f"Failed to record learning: {e}")
            raise

    async def record_fix_result(
        self,
        fingerprint: str,
        success: bool,
    ) -> None:
        """Record the result of applying a fix.

        Args:
            fingerprint: The pattern fingerprint
            success: Whether the fix was successful
        """
        column = "success_count" if success else "failure_count"

        try:
            await self.client.rpc(
                "increment_pattern_stat",
                {
                    "p_fingerprint": fingerprint,
                    "p_project_id": self.project_id,
                    "p_column": column,
                },
            ).execute()
        except Exception as e:
            logger.error(f"Failed to record fix result: {e}")
            raise

    async def audit_log(self, action: str, details: dict) -> None:
        """Write an entry to the audit log.

        Args:
            action: The action being logged (e.g., 'fix_applied')
            details: Additional details about the action
        """
        try:
            await (
                self.client.table("healing_audit")
                .insert({
                    "project_id": self.project_id,
                    "action": action,
                    "details": details,
                })
                .execute()
            )
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # Don't raise - audit log failures shouldn't block operations

    # ==================
    # Utility Methods
    # ==================

    async def get_stats(self) -> dict:
        """Get statistics about patterns for this project.

        Returns:
            Dict with pattern counts and other stats
        """
        try:
            result = await (
                self.client.table("error_patterns")
                .select("id", count="exact")
                .eq("project_id", self.project_id)
                .execute()
            )
            return {
                "pattern_count": result.count or 0,
            }
        except Exception as e:
            logger.warning(f"Failed to get stats: {e}")
            return {"pattern_count": 0}

    async def quarantine_pattern(
        self,
        fingerprint: str,
        reason: str,
    ) -> None:
        """Quarantine a pattern (disable it from being used).

        Args:
            fingerprint: The pattern fingerprint
            reason: Why the pattern is being quarantined
        """
        try:
            await (
                self.client.table("error_patterns")
                .update({
                    "quarantined": True,
                    "quarantine_reason": reason,
                })
                .eq("project_id", self.project_id)
                .eq("fingerprint", fingerprint)
                .execute()
            )
        except Exception as e:
            logger.error(f"Failed to quarantine pattern: {e}")
            raise

    async def unquarantine_pattern(
        self,
        fingerprint: str,
        reason: str,
    ) -> None:
        """Remove a pattern from quarantine.

        Args:
            fingerprint: The pattern fingerprint
            reason: Why the pattern is being unquarantined
        """
        try:
            await (
                self.client.table("error_patterns")
                .update({
                    "quarantined": False,
                    "quarantine_reason": None,
                })
                .eq("project_id", self.project_id)
                .eq("fingerprint", fingerprint)
                .execute()
            )

            await self.audit_log("pattern_unquarantined", {
                "fingerprint": fingerprint,
                "reason": reason,
            })
        except Exception as e:
            logger.error(f"Failed to unquarantine pattern: {e}")
            raise
