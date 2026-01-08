"""
Spawn Scheduler - Smart task spawning to minimize merge conflicts.

This module schedules PRD tasks into waves based on predicted file overlaps.
Tasks that would likely conflict are placed in different waves, so they
run sequentially rather than in parallel.

Key insight: Prevention > Resolution. By avoiding conflicts at spawn time,
we reduce the need for complex merge resolution later.

Based on wave_resolver.py and clusterer.py logic, repurposed for spawning.
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from .schema import PRDTask

logger = logging.getLogger(__name__)


@dataclass
class TaskOverlapPrediction:
    """Predicted file overlap for a task."""
    task_id: str
    predicted_paths: list[str] = field(default_factory=list)
    predicted_domains: list[str] = field(default_factory=list)
    confidence: float = 0.5  # 0.0 = guess, 1.0 = explicit paths provided

    @property
    def has_predictions(self) -> bool:
        return len(self.predicted_paths) > 0 or len(self.predicted_domains) > 0


@dataclass
class SpawnWave:
    """A group of tasks to spawn together (non-conflicting)."""
    wave_number: int
    tasks: list[PRDTask] = field(default_factory=list)
    reason: str = ""  # Why these tasks are grouped

    @property
    def task_ids(self) -> list[str]:
        return [t.id for t in self.tasks]


@dataclass
class ScheduleResult:
    """Result of scheduling tasks into waves."""
    waves: list[SpawnWave] = field(default_factory=list)
    explanation: Optional[str] = None  # For --explain mode
    predictions: dict[str, TaskOverlapPrediction] = field(default_factory=dict)

    @property
    def total_tasks(self) -> int:
        return sum(len(w.tasks) for w in self.waves)


# Domain detection patterns (from clusterer.py)
DOMAIN_PATTERNS = {
    "auth": ["auth", "login", "logout", "session", "permission", "jwt", "oauth", "password"],
    "api": ["api", "route", "endpoint", "handler", "rest", "graphql", "controller"],
    "database": ["model", "migration", "schema", "db", "database", "table", "query", "orm"],
    "ui": ["component", "view", "page", "template", "frontend", "react", "vue", "dashboard"],
    "config": ["config", "setting", "environment", "env", ".yaml", ".json", ".toml"],
    "test": ["test", "spec", "mock", "fixture"],
    "docs": ["doc", "readme", "guide", "tutorial"],
}

# Path patterns for domains
DOMAIN_PATH_PATTERNS = {
    "auth": ["src/auth/", "auth/", "lib/auth/"],
    "api": ["src/api/", "api/", "routes/", "handlers/"],
    "database": ["src/models/", "models/", "migrations/", "db/"],
    "ui": ["src/components/", "components/", "views/", "pages/"],
    "config": ["config/", "settings/", ".env"],
    "test": ["tests/", "test/", "spec/"],
    "docs": ["docs/", "doc/"],
}


class SpawnScheduler:
    """
    Schedules PRD tasks into waves to minimize merge conflicts.

    Strategy:
    1. Predict file/domain overlap for each task
    2. Build adjacency graph (overlapping tasks are connected)
    3. Find independent sets (non-overlapping clusters)
    4. Schedule clusters as waves
    5. Respect explicit dependencies
    """

    def __init__(self):
        self._predictions_cache: dict[str, TaskOverlapPrediction] = {}

    def predict_files(self, task: PRDTask) -> TaskOverlapPrediction:
        """
        Predict which files/domains a task will touch.

        Uses:
        1. Explicit paths from task metadata (highest confidence)
        2. Keyword matching from description
        3. Domain inference
        """
        # Check cache
        if task.id in self._predictions_cache:
            return self._predictions_cache[task.id]

        predicted_paths: list[str] = []
        predicted_domains: list[str] = []
        confidence = 0.3  # Base confidence for keyword-only

        # 1. Check for explicit paths in metadata
        if task.metadata and "files" in task.metadata:
            explicit_files = task.metadata["files"]
            if isinstance(explicit_files, list):
                predicted_paths.extend(explicit_files)
                confidence = 0.9  # High confidence with explicit paths

        # 2. Infer domains from description
        description_lower = task.description.lower()
        for domain, keywords in DOMAIN_PATTERNS.items():
            if any(kw in description_lower for kw in keywords):
                predicted_domains.append(domain)
                # Add typical paths for this domain
                for path_pattern in DOMAIN_PATH_PATTERNS.get(domain, []):
                    if path_pattern not in predicted_paths:
                        predicted_paths.append(path_pattern)

        # 3. Boost confidence if multiple signals
        if predicted_domains and not task.metadata:
            confidence = 0.5  # Medium confidence with domain match

        prediction = TaskOverlapPrediction(
            task_id=task.id,
            predicted_paths=predicted_paths,
            predicted_domains=predicted_domains,
            confidence=confidence,
        )

        self._predictions_cache[task.id] = prediction
        return prediction

    def schedule_waves(
        self,
        tasks: list[PRDTask],
        explain: bool = False,
    ) -> ScheduleResult:
        """
        Schedule tasks into non-overlapping waves.

        Args:
            tasks: List of tasks to schedule
            explain: If True, include explanation of scheduling decisions

        Returns:
            ScheduleResult with waves and optional explanation
        """
        if not tasks:
            return ScheduleResult(waves=[], explanation="No tasks to schedule" if explain else None)

        # Get predictions for all tasks
        predictions = {t.id: self.predict_files(t) for t in tasks}

        # Build task lookup
        task_by_id = {t.id: t for t in tasks}

        # Build dependency graph (task -> tasks it depends on)
        dependencies: dict[str, set[str]] = defaultdict(set)
        for task in tasks:
            if task.dependencies:
                dependencies[task.id].update(task.dependencies)

        # Build overlap adjacency (tasks that share files/domains)
        adjacency = self._build_overlap_adjacency(tasks, predictions)

        # Schedule waves using graph coloring approach
        waves = self._assign_waves(tasks, adjacency, dependencies)

        explanation = None
        if explain:
            explanation = self._generate_explanation(waves, predictions, adjacency)

        return ScheduleResult(
            waves=waves,
            explanation=explanation,
            predictions=predictions,
        )

    def _build_overlap_adjacency(
        self,
        tasks: list[PRDTask],
        predictions: dict[str, TaskOverlapPrediction],
    ) -> dict[str, set[str]]:
        """Build adjacency graph based on file/domain overlap."""
        adjacency: dict[str, set[str]] = defaultdict(set)

        # Map paths to tasks
        path_to_tasks: dict[str, set[str]] = defaultdict(set)
        domain_to_tasks: dict[str, set[str]] = defaultdict(set)

        for task in tasks:
            pred = predictions[task.id]
            for path in pred.predicted_paths:
                path_to_tasks[path].add(task.id)
            for domain in pred.predicted_domains:
                domain_to_tasks[domain].add(task.id)

        # Tasks sharing paths are adjacent
        for path, task_ids in path_to_tasks.items():
            task_list = list(task_ids)
            for i, t1 in enumerate(task_list):
                for t2 in task_list[i + 1:]:
                    adjacency[t1].add(t2)
                    adjacency[t2].add(t1)

        # Tasks sharing domains are adjacent
        for domain, task_ids in domain_to_tasks.items():
            task_list = list(task_ids)
            for i, t1 in enumerate(task_list):
                for t2 in task_list[i + 1:]:
                    adjacency[t1].add(t2)
                    adjacency[t2].add(t1)

        return adjacency

    def _assign_waves(
        self,
        tasks: list[PRDTask],
        adjacency: dict[str, set[str]],
        dependencies: dict[str, set[str]],
    ) -> list[SpawnWave]:
        """
        Assign tasks to waves using greedy graph coloring.

        Constraints:
        1. Adjacent tasks (overlapping) must be in different waves
        2. Dependent tasks must be in later waves than their dependencies
        """
        waves: list[SpawnWave] = []
        assigned: dict[str, int] = {}  # task_id -> wave_number

        # Sort tasks by: dependencies first, then by adjacency count (more conflicts = earlier)
        def task_priority(t: PRDTask) -> tuple:
            dep_count = len(dependencies.get(t.id, []))
            adj_count = len(adjacency.get(t.id, []))
            return (dep_count, -adj_count)  # Fewer deps first, more conflicts first

        sorted_tasks = sorted(tasks, key=task_priority)

        for task in sorted_tasks:
            # Find minimum wave that satisfies constraints
            min_wave = 1

            # Constraint 1: Must be after all dependencies
            for dep_id in dependencies.get(task.id, []):
                if dep_id in assigned:
                    min_wave = max(min_wave, assigned[dep_id] + 1)

            # Constraint 2: Must be different wave from overlapping tasks
            forbidden_waves: set[int] = set()
            for adj_id in adjacency.get(task.id, []):
                if adj_id in assigned:
                    forbidden_waves.add(assigned[adj_id])

            # Find first available wave >= min_wave
            wave_num = min_wave
            while wave_num in forbidden_waves:
                wave_num += 1

            assigned[task.id] = wave_num

            # Add to wave
            while len(waves) < wave_num:
                waves.append(SpawnWave(wave_number=len(waves) + 1))
            waves[wave_num - 1].tasks.append(task)

        return waves

    def _generate_explanation(
        self,
        waves: list[SpawnWave],
        predictions: dict[str, TaskOverlapPrediction],
        adjacency: dict[str, set[str]],
    ) -> str:
        """Generate human-readable explanation of scheduling."""
        lines = ["# Spawn Schedule Explanation", ""]

        for wave in waves:
            lines.append(f"## Wave {wave.wave_number}")
            lines.append(f"Tasks: {', '.join(wave.task_ids)}")
            lines.append("")

            for task_id in wave.task_ids:
                pred = predictions[task_id]
                adj = adjacency.get(task_id, set())

                lines.append(f"### {task_id}")
                lines.append(f"- Predicted domains: {pred.predicted_domains}")
                lines.append(f"- Predicted paths: {pred.predicted_paths[:3]}...")
                lines.append(f"- Confidence: {pred.confidence:.0%}")
                if adj:
                    lines.append(f"- Conflicts with: {', '.join(adj)}")
                lines.append("")

        return "\n".join(lines)

    def get_next_wave(
        self,
        tasks: list[PRDTask],
        spawned_tasks: list[str],
        merged_tasks: list[str],
    ) -> Optional[SpawnWave]:
        """
        Get the next wave of tasks to spawn.

        Args:
            tasks: All tasks in the PRD
            spawned_tasks: Task IDs that have been spawned
            merged_tasks: Task IDs that have been merged

        Returns:
            Next wave to spawn, or None if all done
        """
        # Filter to unspawned tasks
        unspawned = [t for t in tasks if t.id not in spawned_tasks]

        if not unspawned:
            return None

        # Filter to tasks with satisfied dependencies
        ready = []
        for task in unspawned:
            if task.dependencies:
                # All dependencies must be merged
                if all(dep in merged_tasks for dep in task.dependencies):
                    ready.append(task)
            else:
                ready.append(task)

        if not ready:
            return None

        # Schedule just the ready tasks
        result = self.schedule_waves(ready)

        if result.waves:
            return result.waves[0]  # Return first wave
        return None

    def force_spawn(
        self,
        tasks: list[PRDTask],
        task_ids: list[str],
        merged_tasks: Optional[list[str]] = None,
    ) -> SpawnWave:
        """
        Force spawn specific tasks, bypassing overlap scheduling.

        Still respects explicit dependencies.

        Args:
            tasks: All tasks
            task_ids: Tasks to force spawn
            merged_tasks: Already merged tasks (for dependency check)

        Returns:
            Wave containing forced tasks

        Raises:
            ValueError: If dependencies not satisfied
        """
        merged = merged_tasks or []
        task_by_id = {t.id: t for t in tasks}
        forced_tasks = []

        for tid in task_ids:
            if tid not in task_by_id:
                raise ValueError(f"Unknown task: {tid}")

            task = task_by_id[tid]

            # Check dependencies
            if task.dependencies:
                unmet = [d for d in task.dependencies if d not in merged]
                if unmet:
                    raise ValueError(
                        f"Cannot force spawn {tid}: unmet dependencies {unmet}"
                    )

            forced_tasks.append(task)

        return SpawnWave(
            wave_number=0,  # Special wave number for forced
            tasks=forced_tasks,
            reason="Forced by user (--force flag)",
        )
