"""
Wave-based conflict resolution for PRD execution.

When multiple agents complete work, conflicts may arise.
This module resolves conflicts in waves:
1. Cluster related conflicts
2. Resolve each cluster
3. Merge to integration branch
4. Repeat for remaining clusters
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..conflict.clusterer import ConflictClusterer, ConflictCluster
from ..resolution.pipeline import ResolutionPipeline, Resolution
from .schema import PRDTask, TaskResult
from .integration import IntegrationBranchManager, MergeRecord

logger = logging.getLogger(__name__)


@dataclass
class WaveResult:
    """Result of a resolution wave."""

    wave_number: int
    clusters_resolved: int
    conflicts_resolved: int
    merge_records: list[MergeRecord] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class WaveResolutionResult:
    """Complete result of wave-based resolution."""

    total_waves: int
    total_conflicts_resolved: int
    all_merge_records: list[MergeRecord] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class WaveResolver:
    """
    Resolves conflicts in waves using clustering.

    Strategy:
    1. Group completed agent branches by conflict relationship
    2. Resolve conflicts within each cluster
    3. Merge resolved work to integration branch
    4. Continue until all work is merged
    """

    def __init__(
        self,
        integration_manager: IntegrationBranchManager,
        clusterer: Optional[ConflictClusterer] = None,
        resolution_pipeline: Optional[ResolutionPipeline] = None,
        timeout_minutes: int = 30,
    ):
        """
        Initialize the wave resolver.

        Args:
            integration_manager: Integration branch manager
            clusterer: Conflict clusterer (creates default if None)
            resolution_pipeline: Resolution pipeline (creates default if None)
            timeout_minutes: Timeout per cluster resolution
        """
        self.integration_manager = integration_manager
        self.clusterer = clusterer or ConflictClusterer()
        self.resolution_pipeline = resolution_pipeline
        self.timeout_minutes = timeout_minutes

    def resolve_in_waves(
        self,
        completed_tasks: list[tuple[PRDTask, TaskResult]],
        prd_id: str,
    ) -> WaveResolutionResult:
        """
        Resolve conflicts from completed tasks in waves.

        Args:
            completed_tasks: List of (task, result) tuples
            prd_id: PRD identifier

        Returns:
            WaveResolutionResult with all resolution details
        """
        if not completed_tasks:
            return WaveResolutionResult(
                total_waves=0,
                total_conflicts_resolved=0,
                success=True,
            )

        # Extract branches from completed tasks
        branches = [
            result.branch for task, result in completed_tasks
            if result.branch and result.success
        ]

        if not branches:
            return WaveResolutionResult(
                total_waves=0,
                total_conflicts_resolved=0,
                success=True,
            )

        all_merge_records: list[MergeRecord] = []
        failed_tasks: list[str] = []
        wave_number = 0

        # Keep resolving until all branches are merged
        remaining_tasks = list(completed_tasks)

        while remaining_tasks:
            wave_number += 1
            logger.info(f"Starting wave {wave_number} with {len(remaining_tasks)} tasks")

            # Try to merge non-conflicting work first (fast path)
            merged_this_wave: list[tuple[PRDTask, TaskResult]] = []
            still_remaining: list[tuple[PRDTask, TaskResult]] = []

            for task, result in remaining_tasks:
                if not result.branch or not result.success:
                    failed_tasks.append(task.id)
                    continue

                try:
                    # Attempt merge
                    record = self.integration_manager.merge_agent_work(
                        agent_branch=result.branch,
                        agent_id=task.agent_id or "unknown",
                        task_id=task.id,
                        prd_id=prd_id,
                    )
                    all_merge_records.append(record)
                    merged_this_wave.append((task, result))
                    logger.info(f"Merged task {task.id} (wave {wave_number})")

                except RuntimeError as e:
                    if "conflict" in str(e).lower():
                        # Has conflicts, will resolve later
                        still_remaining.append((task, result))
                        logger.info(f"Task {task.id} has conflicts, deferring")
                    else:
                        # Other error
                        failed_tasks.append(task.id)
                        logger.error(f"Failed to merge task {task.id}: {e}")

            # If we merged some work, the conflicts might be resolvable now
            remaining_tasks = still_remaining

            if not merged_this_wave and remaining_tasks:
                # We have conflicts that need resolution
                logger.info(f"Resolving conflicts for {len(remaining_tasks)} tasks")

                # Use resolution pipeline if available
                if self.resolution_pipeline:
                    # TODO: Implement full conflict resolution
                    # For now, mark as failed and continue
                    for task, result in remaining_tasks:
                        failed_tasks.append(task.id)
                        logger.warning(
                            f"Task {task.id} has unresolved conflicts, "
                            f"manual resolution required"
                        )
                    remaining_tasks = []
                else:
                    # No resolution pipeline, mark as failed
                    for task, result in remaining_tasks:
                        failed_tasks.append(task.id)
                    remaining_tasks = []

            # Safety: prevent infinite loop
            if wave_number > 100:
                logger.error("Wave resolution exceeded 100 iterations, aborting")
                for task, result in remaining_tasks:
                    failed_tasks.append(task.id)
                break

        return WaveResolutionResult(
            total_waves=wave_number,
            total_conflicts_resolved=len(all_merge_records),
            all_merge_records=all_merge_records,
            failed_tasks=failed_tasks,
            success=len(failed_tasks) == 0,
            error=f"{len(failed_tasks)} tasks failed" if failed_tasks else None,
        )

    def resolve_cluster(
        self,
        cluster: ConflictCluster,
        prd_id: str,
    ) -> list[MergeRecord]:
        """
        Resolve conflicts within a single cluster.

        Args:
            cluster: The conflict cluster to resolve
            prd_id: PRD identifier

        Returns:
            List of merge records for resolved conflicts
        """
        # TODO: Implement cluster-specific resolution
        # This would use the ResolutionPipeline to generate
        # resolution candidates and apply them

        logger.warning(f"Cluster resolution not yet implemented for cluster {cluster}")
        return []

    def estimate_waves(self, task_count: int, avg_conflict_rate: float = 0.3) -> int:
        """
        Estimate number of waves needed.

        Args:
            task_count: Number of tasks
            avg_conflict_rate: Expected conflict rate (0-1)

        Returns:
            Estimated wave count
        """
        if task_count <= 1:
            return 1

        # Rough estimate: log2(conflicts) + 1
        expected_conflicts = int(task_count * avg_conflict_rate)
        if expected_conflicts <= 0:
            return 1

        import math
        return max(1, int(math.log2(expected_conflicts)) + 1)
