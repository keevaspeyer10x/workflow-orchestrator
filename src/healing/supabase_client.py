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
        context: Optional[dict] = None,
    ) -> None:
        """Record the result of applying a fix.

        Args:
            fingerprint: The pattern fingerprint
            success: Whether the fix was successful
            context: Optional PatternContext dict for per-project tracking
        """
        # Record via the new RPC function for per-project tracking
        try:
            await self.client.rpc(
                "record_pattern_application",
                {
                    "p_fingerprint": fingerprint,
                    "p_project_id": self.project_id,
                    "p_success": success,
                    "p_context": context or {},
                },
            ).execute()
        except Exception as e:
            # Fallback to old method if new RPC doesn't exist
            logger.warning(f"record_pattern_application failed, using fallback: {e}")
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
            except Exception as e2:
                logger.error(f"Failed to record fix result: {e2}")
                raise

    # ==================
    # Phase 6: Intelligent Pattern Filtering
    # ==================

    async def lookup_patterns_scored(
        self,
        fingerprint: str,
        language: Optional[str] = None,
        error_category: Optional[str] = None,
    ) -> list[dict]:
        """Look up patterns with relevance scoring.

        Calls the lookup_patterns_scored RPC function which returns
        patterns ordered by score, considering:
        - Wilson score for success rate
        - Context overlap
        - Universality (project count)
        - Recency

        Args:
            fingerprint: The error fingerprint
            language: Optional language filter
            error_category: Optional error category filter

        Returns:
            List of scored pattern dicts
        """
        try:
            result = await self.client.rpc(
                "lookup_patterns_scored",
                {
                    "p_fingerprint": fingerprint,
                    "p_project_id": self.project_id,
                    "p_language": language,
                    "p_error_category": error_category,
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Scored lookup failed: {e}")
            return []

    async def record_pattern_application(
        self,
        fingerprint: str,
        project_id: str,
        success: bool,
        context: dict,
    ) -> None:
        """Record pattern application for per-project tracking.

        Args:
            fingerprint: Pattern fingerprint
            project_id: Project where pattern was applied
            success: Whether fix was successful
            context: PatternContext dict
        """
        try:
            await self.client.rpc(
                "record_pattern_application",
                {
                    "p_fingerprint": fingerprint,
                    "p_project_id": project_id,
                    "p_success": success,
                    "p_context": context,
                },
            ).execute()
        except Exception as e:
            # Log warning but don't raise - consistent with record_fix_result fallback
            logger.warning(f"Failed to record pattern application: {e}")

    async def get_pattern_project_ids(self, fingerprint: str) -> list[str]:
        """Get list of projects where pattern has been applied.

        Args:
            fingerprint: Pattern fingerprint

        Returns:
            List of project IDs
        """
        try:
            result = await self.client.rpc(
                "get_pattern_project_ids",
                {"p_fingerprint": fingerprint},
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to get pattern project IDs: {e}")
            return []

    async def get_project_share_setting(self, project_id: str) -> bool:
        """Check if project has opted out of pattern sharing.

        Args:
            project_id: Project to check

        Returns:
            True if sharing is enabled (default), False if opted out
        """
        try:
            result = await (
                self.client.table("healing_config")
                .select("share_patterns")
                .eq("project_id", project_id)
                .single()
                .execute()
            )
            if result.data and "share_patterns" in result.data:
                return result.data["share_patterns"]
            return True  # Default to sharing enabled
        except Exception:
            return True  # Default to sharing enabled on error

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

    async def get_all_patterns(self) -> list[dict]:
        """Get all patterns for this project.

        Returns:
            List of all pattern dicts
        """
        try:
            result = await (
                self.client.table("error_patterns")
                .select("*")
                .eq("project_id", self.project_id)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to get all patterns: {e}")
            return []

    async def list_issues(
        self,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        has_fix: Optional[bool] = None,
        limit: int = 50,
    ) -> list[dict]:
        """List accumulated issues.

        Args:
            status: Filter by status (open, resolved, ignored)
            severity: Filter by severity (high, medium, low)
            has_fix: Filter by whether fix is available
            limit: Maximum number of results

        Returns:
            List of issue dicts
        """
        try:
            query = (
                self.client.table("error_patterns")
                .select("fingerprint, description, status, severity, has_fix, count:occurrence_count")
                .eq("project_id", self.project_id)
                .limit(limit)
            )

            if status:
                query = query.eq("status", status)
            if severity:
                query = query.eq("severity", severity)
            if has_fix is not None:
                query = query.eq("has_fix", has_fix)

            result = await query.execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to list issues: {e}")
            return []

    # ==================
    # Phase 5: Metrics
    # ==================

    async def get_error_counts(self, start_date) -> dict:
        """Get error detection counts since start_date.

        Args:
            start_date: Start of the analysis period

        Returns:
            Dict with detected and total_failures counts
        """
        try:
            result = await self.client.rpc(
                "get_error_counts",
                {
                    "p_project_id": self.project_id,
                    "p_start_date": start_date.isoformat(),
                },
            ).execute()
            return result.data or {"detected": 0, "total_failures": 0}
        except Exception as e:
            logger.warning(f"Failed to get error counts: {e}")
            return {"detected": 0, "total_failures": 0}

    async def get_fix_counts(self, start_date) -> dict:
        """Get fix application counts since start_date.

        Args:
            start_date: Start of the analysis period

        Returns:
            Dict with applied and successful counts
        """
        try:
            result = await self.client.rpc(
                "get_fix_counts",
                {
                    "p_project_id": self.project_id,
                    "p_start_date": start_date.isoformat(),
                },
            ).execute()
            return result.data or {"applied": 0, "successful": 0}
        except Exception as e:
            logger.warning(f"Failed to get fix counts: {e}")
            return {"applied": 0, "successful": 0}

    async def get_cost_data(self, start_date) -> dict:
        """Get cost tracking data since start_date.

        Args:
            start_date: Start of the analysis period

        Returns:
            Dict with total and daily_avg cost
        """
        try:
            result = await self.client.rpc(
                "get_cost_data",
                {
                    "p_project_id": self.project_id,
                    "p_start_date": start_date.isoformat(),
                },
            ).execute()
            return result.data or {"total": 0.0, "daily_avg": 0.0}
        except Exception as e:
            logger.warning(f"Failed to get cost data: {e}")
            return {"total": 0.0, "daily_avg": 0.0}

    async def get_pattern_counts(self, start_date) -> dict:
        """Get pattern counts since start_date.

        Args:
            start_date: Start of the analysis period

        Returns:
            Dict with total and new pattern counts
        """
        try:
            # Total patterns
            total_result = await (
                self.client.table("error_patterns")
                .select("id", count="exact")
                .eq("project_id", self.project_id)
                .execute()
            )
            total = total_result.count or 0

            # New patterns since start_date
            new_result = await (
                self.client.table("error_patterns")
                .select("id", count="exact")
                .eq("project_id", self.project_id)
                .gte("created_at", start_date.isoformat())
                .execute()
            )
            new = new_result.count or 0

            return {"total": total, "new": new}
        except Exception as e:
            logger.warning(f"Failed to get pattern counts: {e}")
            return {"total": 0, "new": 0}

    async def get_top_errors(self, start_date, limit: int = 10) -> list[dict]:
        """Get most frequent error patterns.

        Args:
            start_date: Start of the analysis period
            limit: Maximum number of results

        Returns:
            List of top error patterns
        """
        try:
            result = await (
                self.client.table("error_patterns")
                .select("fingerprint, description, occurrence_count")
                .eq("project_id", self.project_id)
                .order("occurrence_count", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to get top errors: {e}")
            return []

    async def get_daily_costs(self, start_date) -> list[dict]:
        """Get daily cost history.

        Args:
            start_date: Start of the analysis period

        Returns:
            List of {date, cost_usd} dicts
        """
        try:
            result = await self.client.rpc(
                "get_daily_costs",
                {
                    "p_project_id": self.project_id,
                    "p_start_date": start_date.isoformat(),
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to get daily costs: {e}")
            return []

    async def get_pattern_growth(self, start_date) -> list[dict]:
        """Get pattern growth over time.

        Args:
            start_date: Start of the analysis period

        Returns:
            List of {date, count} dicts
        """
        try:
            result = await self.client.rpc(
                "get_pattern_growth",
                {
                    "p_project_id": self.project_id,
                    "p_start_date": start_date.isoformat(),
                },
            ).execute()
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to get pattern growth: {e}")
            return []

    async def get_top_patterns(self, limit: int = 100) -> list[dict]:
        """Get top patterns by usage frequency (for cache warming).

        Args:
            limit: Maximum number of patterns

        Returns:
            List of most frequently used patterns
        """
        try:
            result = await (
                self.client.table("error_patterns")
                .select("*")
                .eq("project_id", self.project_id)
                .eq("quarantined", False)
                .order("occurrence_count", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.warning(f"Failed to get top patterns: {e}")
            return []

    # ==================
    # Phase 5: Circuit Breaker
    # ==================

    async def get_circuit_state(self) -> Optional[dict]:
        """Get circuit breaker state from config.

        Returns:
            Circuit state dict or None
        """
        try:
            result = await (
                self.client.table("healing_config")
                .select("circuit_state, circuit_opened_at, circuit_reverts")
                .eq("project_id", self.project_id)
                .single()
                .execute()
            )
            if result.data:
                return {
                    "state": result.data.get("circuit_state", "closed"),
                    "opened_at": result.data.get("circuit_opened_at"),
                    "reverts": result.data.get("circuit_reverts", []),
                }
            return None
        except Exception:
            return None

    async def save_circuit_state(self, state_data: dict) -> None:
        """Save circuit breaker state to config.

        Args:
            state_data: Circuit state dict
        """
        try:
            await (
                self.client.table("healing_config")
                .upsert({
                    "project_id": self.project_id,
                    "circuit_state": state_data.get("state"),
                    "circuit_opened_at": state_data.get("opened_at"),
                    "circuit_reverts": state_data.get("reverts", []),
                })
                .execute()
            )
        except Exception as e:
            logger.warning(f"Failed to save circuit state: {e}")

    # ==================
    # Phase 5: Flakiness Detection
    # ==================

    async def get_error_occurrences(
        self,
        fingerprint: str,
        start_time,
    ) -> list:
        """Get occurrence timestamps for an error.

        Args:
            fingerprint: Error fingerprint
            start_time: Start of analysis window

        Returns:
            List of occurrence timestamps
        """
        try:
            result = await (
                self.client.table("healing_audit")
                .select("created_at")
                .eq("project_id", self.project_id)
                .eq("details->>fingerprint", fingerprint)
                .gte("created_at", start_time.isoformat())
                .order("created_at")
                .execute()
            )
            return [r["created_at"] for r in (result.data or [])]
        except Exception as e:
            logger.warning(f"Failed to get error occurrences: {e}")
            return []

    # ==================
    # Phase 5: Backfill
    # ==================

    async def record_historical_error(self, error) -> None:
        """Record a historical error from backfill.

        Args:
            error: ErrorEvent to record
        """
        try:
            # Check if pattern already exists
            existing = await self.lookup_pattern(error.fingerprint)

            if existing:
                # Update occurrence count
                await self.client.rpc(
                    "increment_pattern_stat",
                    {
                        "p_fingerprint": error.fingerprint,
                        "p_project_id": self.project_id,
                        "p_column": "occurrence_count",
                    },
                ).execute()
            else:
                # Create new pattern
                pattern = {
                    "fingerprint": error.fingerprint,
                    "fingerprint_coarse": error.fingerprint_coarse,
                    "description": self.scrubber.scrub(error.description),
                    "project_id": self.project_id,
                    "source": "backfill",
                    "occurrence_count": 1,
                }
                await self.record_pattern(pattern)
        except Exception as e:
            logger.warning(f"Failed to record historical error: {e}")
