"""
Tests for SpawnScheduler - smart task spawning to minimize conflicts.

The SpawnScheduler predicts file overlaps between tasks and groups
non-conflicting tasks into waves for parallel execution.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.prd.spawn_scheduler import (
    SpawnScheduler,
    SpawnWave,
    TaskOverlapPrediction,
    ScheduleResult,
)
from src.prd.schema import PRDTask, TaskStatus


class TestTaskOverlapPrediction:
    """Tests for file overlap prediction."""

    def test_predict_from_keywords(self):
        """Should predict files from task description keywords."""
        scheduler = SpawnScheduler()

        # Auth-related task
        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Add user authentication with JWT")
        )
        assert any("auth" in f.lower() for f in prediction.predicted_paths)

    def test_predict_from_explicit_paths(self):
        """Should use explicit paths if provided in task."""
        scheduler = SpawnScheduler()

        task = PRDTask(
            id="t1",
            description="Update the API",
            metadata={"files": ["src/api/routes.py", "src/api/handlers.py"]}
        )
        prediction = scheduler.predict_files(task)

        assert "src/api/routes.py" in prediction.predicted_paths
        assert "src/api/handlers.py" in prediction.predicted_paths

    def test_predict_domains(self):
        """Should predict domains from description."""
        scheduler = SpawnScheduler()

        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Fix database migration for users table")
        )
        assert "database" in prediction.predicted_domains

    def test_confidence_higher_with_explicit_paths(self):
        """Explicit paths should have higher confidence than keywords."""
        scheduler = SpawnScheduler()

        # Implicit (keyword-based)
        implicit = scheduler.predict_files(
            PRDTask(id="t1", description="Update authentication")
        )

        # Explicit (paths provided)
        explicit = scheduler.predict_files(
            PRDTask(
                id="t2",
                description="Update authentication",
                metadata={"files": ["src/auth/login.py"]}
            )
        )

        assert explicit.confidence > implicit.confidence


class TestSpawnWave:
    """Tests for SpawnWave dataclass."""

    def test_wave_creation(self):
        """Should create a wave with tasks."""
        tasks = [
            PRDTask(id="t1", description="Task 1"),
            PRDTask(id="t2", description="Task 2"),
        ]
        wave = SpawnWave(wave_number=1, tasks=tasks)

        assert wave.wave_number == 1
        assert len(wave.tasks) == 2

    def test_wave_task_ids(self):
        """Should provide list of task IDs."""
        tasks = [
            PRDTask(id="t1", description="Task 1"),
            PRDTask(id="t2", description="Task 2"),
        ]
        wave = SpawnWave(wave_number=1, tasks=tasks)

        assert wave.task_ids == ["t1", "t2"]


class TestScheduleWaves:
    """Tests for wave scheduling logic."""

    @pytest.fixture
    def scheduler(self):
        """Create a scheduler instance."""
        return SpawnScheduler()

    def test_single_task_single_wave(self, scheduler):
        """Single task should be in wave 1."""
        tasks = [PRDTask(id="t1", description="Task 1")]

        result = scheduler.schedule_waves(tasks)

        assert len(result.waves) == 1
        assert result.waves[0].wave_number == 1
        assert "t1" in result.waves[0].task_ids

    def test_non_overlapping_tasks_same_wave(self, scheduler):
        """Non-overlapping tasks should be in the same wave."""
        tasks = [
            PRDTask(id="t1", description="Update documentation in docs/"),
            PRDTask(id="t2", description="Fix API endpoint in src/api/"),
            PRDTask(id="t3", description="Add database migration"),
        ]

        result = scheduler.schedule_waves(tasks)

        # All should be in wave 1 (no overlap)
        assert len(result.waves) == 1
        assert len(result.waves[0].tasks) == 3

    def test_overlapping_tasks_different_waves(self, scheduler):
        """Overlapping tasks should be in different waves."""
        tasks = [
            PRDTask(id="t1", description="Add user authentication"),
            PRDTask(id="t2", description="Add admin authentication"),  # Overlaps with t1
            PRDTask(id="t3", description="Update documentation"),  # No overlap
        ]

        result = scheduler.schedule_waves(tasks)

        # t1 and t2 overlap (both auth), should be in different waves
        assert len(result.waves) >= 2

        # Find which waves contain auth tasks
        wave_for_t1 = next(w for w in result.waves if "t1" in w.task_ids)
        wave_for_t2 = next(w for w in result.waves if "t2" in w.task_ids)

        assert wave_for_t1.wave_number != wave_for_t2.wave_number

    def test_respects_dependencies(self, scheduler):
        """Dependent tasks should be in later waves."""
        tasks = [
            PRDTask(id="t1", description="Create user model"),
            PRDTask(id="t2", description="Add user API", dependencies=["t1"]),
            PRDTask(id="t3", description="Add user tests", dependencies=["t2"]),
        ]

        result = scheduler.schedule_waves(tasks)

        wave_for_t1 = next(w for w in result.waves if "t1" in w.task_ids)
        wave_for_t2 = next(w for w in result.waves if "t2" in w.task_ids)
        wave_for_t3 = next(w for w in result.waves if "t3" in w.task_ids)

        assert wave_for_t1.wave_number < wave_for_t2.wave_number
        assert wave_for_t2.wave_number < wave_for_t3.wave_number

    def test_empty_tasks_empty_result(self, scheduler):
        """Empty task list should return empty result."""
        result = scheduler.schedule_waves([])

        assert len(result.waves) == 0

    def test_explain_mode(self, scheduler):
        """Explain mode should include reasoning."""
        tasks = [
            PRDTask(id="t1", description="Add authentication"),
            PRDTask(id="t2", description="Add authorization"),
        ]

        result = scheduler.schedule_waves(tasks, explain=True)

        assert result.explanation is not None
        assert len(result.explanation) > 0


class TestGetNextWave:
    """Tests for getting the next wave to spawn."""

    @pytest.fixture
    def scheduler(self):
        return SpawnScheduler()

    def test_returns_first_wave_initially(self, scheduler):
        """Should return wave 1 when nothing spawned yet."""
        tasks = [
            PRDTask(id="t1", description="Task 1"),
            PRDTask(id="t2", description="Task 2"),
        ]

        wave = scheduler.get_next_wave(tasks, spawned_tasks=[], merged_tasks=[])

        assert wave is not None
        assert wave.wave_number == 1

    def test_returns_next_wave_after_merge(self, scheduler):
        """Should return next wave after previous wave merged."""
        tasks = [
            PRDTask(id="t1", description="Add authentication"),
            PRDTask(id="t2", description="Add authorization"),  # Overlaps, wave 2
        ]

        # First wave spawned and merged
        wave = scheduler.get_next_wave(
            tasks,
            spawned_tasks=["t1"],
            merged_tasks=["t1"]
        )

        assert wave is not None
        assert "t2" in wave.task_ids

    def test_returns_none_when_all_spawned(self, scheduler):
        """Should return None when all tasks already spawned."""
        tasks = [PRDTask(id="t1", description="Task 1")]

        wave = scheduler.get_next_wave(
            tasks,
            spawned_tasks=["t1"],
            merged_tasks=[]
        )

        assert wave is None

    def test_waits_for_dependencies(self, scheduler):
        """Should not return wave with unmet dependencies."""
        tasks = [
            PRDTask(id="t1", description="Base task"),
            PRDTask(id="t2", description="Dependent task", dependencies=["t1"]),
        ]

        # t1 spawned but not merged
        wave = scheduler.get_next_wave(
            tasks,
            spawned_tasks=["t1"],
            merged_tasks=[]  # t1 not merged yet
        )

        # Should not return t2 yet
        assert wave is None or "t2" not in wave.task_ids


class TestForceSpawn:
    """Tests for --force flag to bypass scheduler."""

    @pytest.fixture
    def scheduler(self):
        return SpawnScheduler()

    def test_force_ignores_overlap(self, scheduler):
        """Force should spawn task even if it overlaps."""
        tasks = [
            PRDTask(id="t1", description="Add authentication"),
            PRDTask(id="t2", description="Add authorization"),
        ]

        # Force t2 even though t1 is in same domain
        result = scheduler.force_spawn(tasks, task_ids=["t2"])

        assert "t2" in result.task_ids

    def test_force_respects_dependencies(self, scheduler):
        """Force should still respect explicit dependencies."""
        tasks = [
            PRDTask(id="t1", description="Base task"),
            PRDTask(id="t2", description="Dependent", dependencies=["t1"]),
        ]

        # Try to force t2 before t1 is done
        with pytest.raises(ValueError, match="dependencies"):
            scheduler.force_spawn(tasks, task_ids=["t2"], merged_tasks=[])


class TestDomainPatterns:
    """Tests for domain detection patterns."""

    @pytest.fixture
    def scheduler(self):
        return SpawnScheduler()

    def test_auth_domain(self, scheduler):
        """Should detect auth domain."""
        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Add login with OAuth")
        )
        assert "auth" in prediction.predicted_domains

    def test_api_domain(self, scheduler):
        """Should detect API domain."""
        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Create REST endpoints for users")
        )
        assert "api" in prediction.predicted_domains

    def test_database_domain(self, scheduler):
        """Should detect database domain."""
        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Add migration for orders table")
        )
        assert "database" in prediction.predicted_domains

    def test_ui_domain(self, scheduler):
        """Should detect UI domain."""
        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Create dashboard component")
        )
        assert "ui" in prediction.predicted_domains

    def test_config_domain(self, scheduler):
        """Should detect config domain."""
        prediction = scheduler.predict_files(
            PRDTask(id="t1", description="Update environment settings")
        )
        assert "config" in prediction.predicted_domains


class TestIntegrationWithClusterer:
    """Tests for integration with existing clusterer logic."""

    @pytest.fixture
    def scheduler(self):
        return SpawnScheduler()

    def test_uses_file_adjacency(self, scheduler):
        """Should use file adjacency for clustering."""
        tasks = [
            PRDTask(
                id="t1",
                description="Update auth",
                metadata={"files": ["src/auth/login.py"]}
            ),
            PRDTask(
                id="t2",
                description="Fix auth bug",
                metadata={"files": ["src/auth/login.py"]}  # Same file!
            ),
            PRDTask(
                id="t3",
                description="Update docs",
                metadata={"files": ["docs/README.md"]}
            ),
        ]

        result = scheduler.schedule_waves(tasks)

        # t1 and t2 share a file, should be in different waves
        wave_for_t1 = next(w for w in result.waves if "t1" in w.task_ids)
        wave_for_t2 = next(w for w in result.waves if "t2" in w.task_ids)

        assert wave_for_t1.wave_number != wave_for_t2.wave_number

    def test_uses_domain_adjacency(self, scheduler):
        """Should use domain adjacency for clustering."""
        tasks = [
            PRDTask(id="t1", description="Add user login"),
            PRDTask(id="t2", description="Add admin login"),  # Same domain
            PRDTask(id="t3", description="Update API docs"),  # Different domain
        ]

        result = scheduler.schedule_waves(tasks)

        # t1 and t2 share auth domain
        wave_for_t1 = next(w for w in result.waves if "t1" in w.task_ids)
        wave_for_t2 = next(w for w in result.waves if "t2" in w.task_ids)

        assert wave_for_t1.wave_number != wave_for_t2.wave_number
