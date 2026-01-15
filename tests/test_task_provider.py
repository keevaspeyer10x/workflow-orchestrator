"""
Tests for TaskProvider interface and backends.

Tests cover:
- Interface enums and dataclasses
- LocalTaskProvider CRUD operations
- GitHubTaskProvider URL parsing and mocking
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from src.task_provider.interface import (
    TaskStatus,
    TaskPriority,
    Task,
    TaskTemplate,
    TaskProvider,
)
from src.task_provider.backends.local import LocalTaskProvider
from src.task_provider.backends.github import GitHubTaskProvider
from src.task_provider import get_task_provider, list_providers, register_provider


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_tasks_file(tmp_path):
    """Create temporary tasks.json for testing."""
    tasks_file = tmp_path / "tasks.json"
    return tasks_file


@pytest.fixture
def local_provider(temp_tasks_file):
    """Create LocalTaskProvider with temp file."""
    return LocalTaskProvider(path=str(temp_tasks_file))


@pytest.fixture
def sample_template():
    """Create sample TaskTemplate for testing."""
    return TaskTemplate(
        title="Test Task",
        description="Test description",
        problem_solved="Solves test problem",
    )


@pytest.fixture
def sample_template_with_tasks():
    """Create sample TaskTemplate with subtasks."""
    return TaskTemplate(
        title="Feature Task",
        description="Implement feature X",
        problem_solved="Users need feature X",
        proposed_solution="Add feature X to module Y",
        tasks=["Step 1", "Step 2", "Step 3"],
        priority=TaskPriority.HIGH,
        labels=["feature", "enhancement"],
    )


# =============================================================================
# TaskStatus Tests
# =============================================================================


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_has_expected_values(self):
        """TaskStatus has OPEN, IN_PROGRESS, BLOCKED, CLOSED values."""
        assert TaskStatus.OPEN.value == "open"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.BLOCKED.value == "blocked"
        assert TaskStatus.CLOSED.value == "closed"

    def test_values_are_lowercase(self):
        """TaskStatus values are lowercase strings."""
        for status in TaskStatus:
            assert status.value == status.value.lower()


# =============================================================================
# TaskPriority Tests
# =============================================================================


class TestTaskPriority:
    """Tests for TaskPriority enum."""

    def test_has_expected_values(self):
        """TaskPriority has CRITICAL=P0, HIGH=P1, MEDIUM=P2, LOW=P3."""
        assert TaskPriority.CRITICAL.value == "P0"
        assert TaskPriority.HIGH.value == "P1"
        assert TaskPriority.MEDIUM.value == "P2"
        assert TaskPriority.LOW.value == "P3"

    def test_values_sort_correctly(self):
        """TaskPriority values sort correctly (P0 < P1 < P2 < P3)."""
        priorities = [TaskPriority.LOW, TaskPriority.CRITICAL, TaskPriority.MEDIUM, TaskPriority.HIGH]
        sorted_priorities = sorted(priorities, key=lambda p: p.value)
        assert sorted_priorities == [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.MEDIUM,
            TaskPriority.LOW,
        ]


# =============================================================================
# Task Tests
# =============================================================================


class TestTask:
    """Tests for Task dataclass."""

    def test_create_with_required_fields(self):
        """Task can be created with required fields."""
        task = Task(
            id="1",
            title="Test",
            body="Body",
            status=TaskStatus.OPEN,
        )
        assert task.id == "1"
        assert task.title == "Test"
        assert task.body == "Body"
        assert task.status == TaskStatus.OPEN

    def test_optional_fields_default_correctly(self):
        """Task optional fields default correctly."""
        task = Task(
            id="1",
            title="Test",
            body="Body",
            status=TaskStatus.OPEN,
        )
        assert task.priority is None
        assert task.labels == []
        assert task.url is None
        assert task.metadata == {}

    def test_to_dict(self):
        """Task can be serialized to dict."""
        task = Task(
            id="1",
            title="Test",
            body="Body",
            status=TaskStatus.OPEN,
            priority=TaskPriority.HIGH,
            labels=["bug"],
        )
        d = task.to_dict()
        assert d["id"] == "1"
        assert d["title"] == "Test"
        assert d["status"] == "open"
        assert d["priority"] == "P1"
        assert d["labels"] == ["bug"]

    def test_from_dict(self):
        """Task can be deserialized from dict."""
        d = {
            "id": "1",
            "title": "Test",
            "body": "Body",
            "status": "open",
            "priority": "P1",
            "labels": ["bug"],
        }
        task = Task.from_dict(d)
        assert task.id == "1"
        assert task.status == TaskStatus.OPEN
        assert task.priority == TaskPriority.HIGH


# =============================================================================
# TaskTemplate Tests
# =============================================================================


class TestTaskTemplate:
    """Tests for TaskTemplate dataclass."""

    def test_create_with_required_fields(self):
        """TaskTemplate can be created with required fields."""
        template = TaskTemplate(
            title="Test",
            description="Desc",
            problem_solved="Problem",
        )
        assert template.title == "Test"
        assert template.description == "Desc"
        assert template.problem_solved == "Problem"

    def test_defaults(self):
        """TaskTemplate has correct defaults."""
        template = TaskTemplate(
            title="Test",
            description="Desc",
            problem_solved="Problem",
        )
        assert template.recommendation == "IMPLEMENT"
        assert template.priority == TaskPriority.MEDIUM
        assert template.tasks == []
        assert template.labels == []
        assert template.yagni_actual_problem is True
        assert template.yagni_ok_without == "6 months"
        assert template.yagni_current_works is False


# =============================================================================
# LocalTaskProvider Tests
# =============================================================================


class TestLocalTaskProviderInit:
    """Tests for LocalTaskProvider initialization."""

    def test_creates_config_directory(self, tmp_path):
        """Creates config directory if not exists."""
        nested_path = tmp_path / "deeply" / "nested" / "tasks.json"
        provider = LocalTaskProvider(path=str(nested_path))
        assert nested_path.parent.exists()

    def test_creates_tasks_file(self, temp_tasks_file):
        """Creates tasks.json with empty state if not exists."""
        provider = LocalTaskProvider(path=str(temp_tasks_file))
        assert temp_tasks_file.exists()
        data = json.loads(temp_tasks_file.read_text())
        assert data == {"tasks": [], "next_id": 1}

    def test_loads_existing_file(self, temp_tasks_file):
        """Loads existing tasks.json if present."""
        # Pre-create file with data
        temp_tasks_file.write_text(json.dumps({
            "tasks": [{"id": "1", "title": "Existing", "body": "", "status": "open"}],
            "next_id": 2,
        }))
        provider = LocalTaskProvider(path=str(temp_tasks_file))
        tasks = provider.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].title == "Existing"


class TestLocalTaskProviderCreateTask:
    """Tests for LocalTaskProvider.create_task()."""

    def test_creates_task_with_auto_id(self, local_provider, sample_template):
        """Creates task with auto-incremented ID."""
        task1 = local_provider.create_task(sample_template)
        task2 = local_provider.create_task(sample_template)
        assert task1.id == "1"
        assert task2.id == "2"

    def test_persists_task_to_file(self, local_provider, sample_template, temp_tasks_file):
        """Persists task to JSON file."""
        task = local_provider.create_task(sample_template)
        data = json.loads(temp_tasks_file.read_text())
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["id"] == "1"
        assert data["tasks"][0]["title"] == "Test Task"

    def test_returns_task_with_fields(self, local_provider, sample_template):
        """Returns Task object with all fields populated."""
        task = local_provider.create_task(sample_template)
        assert task.id == "1"
        assert task.title == "Test Task"
        assert task.status == TaskStatus.OPEN
        assert task.priority == TaskPriority.MEDIUM
        assert "## Description" in task.body


class TestLocalTaskProviderListTasks:
    """Tests for LocalTaskProvider.list_tasks()."""

    def test_returns_all_tasks(self, local_provider, sample_template):
        """Returns all tasks when no filter."""
        local_provider.create_task(sample_template)
        local_provider.create_task(sample_template)
        tasks = local_provider.list_tasks()
        assert len(tasks) == 2

    def test_filters_by_status(self, local_provider, sample_template):
        """Filters by status correctly."""
        task1 = local_provider.create_task(sample_template)
        task2 = local_provider.create_task(sample_template)
        local_provider.close_task(task2.id)

        open_tasks = local_provider.list_tasks(status=TaskStatus.OPEN)
        closed_tasks = local_provider.list_tasks(status=TaskStatus.CLOSED)

        assert len(open_tasks) == 1
        assert len(closed_tasks) == 1
        assert open_tasks[0].id == "1"
        assert closed_tasks[0].id == "2"

    def test_filters_by_priority(self, local_provider):
        """Filters by priority correctly."""
        template_high = TaskTemplate(
            title="High", description="", problem_solved="",
            priority=TaskPriority.HIGH,
        )
        template_low = TaskTemplate(
            title="Low", description="", problem_solved="",
            priority=TaskPriority.LOW,
        )
        local_provider.create_task(template_high)
        local_provider.create_task(template_low)

        high_tasks = local_provider.list_tasks(priority=TaskPriority.HIGH)
        assert len(high_tasks) == 1
        assert high_tasks[0].title == "High"

    def test_returns_empty_list_when_no_matches(self, local_provider, sample_template):
        """Returns empty list when no matches."""
        local_provider.create_task(sample_template)
        tasks = local_provider.list_tasks(status=TaskStatus.BLOCKED)
        assert tasks == []


class TestLocalTaskProviderGetNextTask:
    """Tests for LocalTaskProvider.get_next_task()."""

    def test_returns_highest_priority(self, local_provider):
        """Returns highest priority open task."""
        template_low = TaskTemplate(
            title="Low", description="", problem_solved="",
            priority=TaskPriority.LOW,
        )
        template_critical = TaskTemplate(
            title="Critical", description="", problem_solved="",
            priority=TaskPriority.CRITICAL,
        )
        local_provider.create_task(template_low)
        local_provider.create_task(template_critical)

        next_task = local_provider.get_next_task()
        assert next_task.title == "Critical"
        assert next_task.priority == TaskPriority.CRITICAL

    def test_returns_none_when_empty(self, local_provider):
        """Returns None when no open tasks."""
        assert local_provider.get_next_task() is None

    def test_ignores_closed_tasks(self, local_provider):
        """Ignores closed tasks."""
        template = TaskTemplate(
            title="Test", description="", problem_solved="",
            priority=TaskPriority.CRITICAL,
        )
        task = local_provider.create_task(template)
        local_provider.close_task(task.id)

        assert local_provider.get_next_task() is None


class TestLocalTaskProviderCloseTask:
    """Tests for LocalTaskProvider.close_task()."""

    def test_updates_status_to_closed(self, local_provider, sample_template):
        """Updates task status to CLOSED."""
        task = local_provider.create_task(sample_template)
        closed = local_provider.close_task(task.id)
        assert closed.status == TaskStatus.CLOSED

    def test_persists_change(self, local_provider, sample_template, temp_tasks_file):
        """Persists change to JSON file."""
        task = local_provider.create_task(sample_template)
        local_provider.close_task(task.id)

        data = json.loads(temp_tasks_file.read_text())
        assert data["tasks"][0]["status"] == "closed"

    def test_raises_for_nonexistent_id(self, local_provider):
        """Raises error for non-existent task ID."""
        with pytest.raises(KeyError):
            local_provider.close_task("nonexistent")


class TestLocalTaskProviderUpdateTask:
    """Tests for LocalTaskProvider.update_task()."""

    def test_updates_specified_fields(self, local_provider, sample_template):
        """Updates specified fields."""
        task = local_provider.create_task(sample_template)
        updated = local_provider.update_task(task.id, {"title": "Updated Title"})
        assert updated.title == "Updated Title"

    def test_preserves_non_updated_fields(self, local_provider, sample_template):
        """Preserves non-updated fields."""
        task = local_provider.create_task(sample_template)
        original_body = task.body
        updated = local_provider.update_task(task.id, {"title": "Updated"})
        assert updated.body == original_body

    def test_raises_for_nonexistent_id(self, local_provider):
        """Raises error for non-existent task ID."""
        with pytest.raises(KeyError):
            local_provider.update_task("nonexistent", {"title": "X"})


# =============================================================================
# GitHubTaskProvider Tests
# =============================================================================


class TestGitHubTaskProviderRepoDetection:
    """Tests for GitHubTaskProvider repo detection."""

    def test_parses_https_url(self):
        """Parses HTTPS URL correctly."""
        provider = GitHubTaskProvider()
        repo = provider._parse_repo_url("https://github.com/owner/repo.git")
        assert repo == "owner/repo"

    def test_parses_https_without_git_suffix(self):
        """Parses HTTPS URL without .git suffix."""
        provider = GitHubTaskProvider()
        repo = provider._parse_repo_url("https://github.com/owner/repo")
        assert repo == "owner/repo"

    def test_parses_ssh_url(self):
        """Parses SSH URL correctly."""
        provider = GitHubTaskProvider()
        repo = provider._parse_repo_url("git@github.com:owner/repo.git")
        assert repo == "owner/repo"

    def test_parses_ssh_without_git_suffix(self):
        """Parses SSH URL without .git suffix."""
        provider = GitHubTaskProvider()
        repo = provider._parse_repo_url("git@github.com:owner/repo")
        assert repo == "owner/repo"

    def test_raises_for_invalid_url(self):
        """Raises error for invalid URL."""
        provider = GitHubTaskProvider()
        with pytest.raises(ValueError):
            provider._parse_repo_url("not-a-github-url")


class TestGitHubTaskProviderBodyRendering:
    """Tests for GitHubTaskProvider._render_body()."""

    def test_renders_all_sections(self, sample_template_with_tasks):
        """Renders all sections in body."""
        provider = GitHubTaskProvider(repo="test/repo")
        body = provider._render_body(sample_template_with_tasks)

        assert "## Status" in body
        assert "## Priority" in body
        assert "## Description" in body
        assert "## Problem Solved" in body
        assert "## Proposed Solution" in body
        assert "## Tasks" in body
        assert "## YAGNI Check" in body
        assert "## Recommendation" in body

    def test_includes_task_checkboxes(self, sample_template_with_tasks):
        """Includes task checkboxes."""
        provider = GitHubTaskProvider(repo="test/repo")
        body = provider._render_body(sample_template_with_tasks)

        assert "- [ ] Step 1" in body
        assert "- [ ] Step 2" in body
        assert "- [ ] Step 3" in body


class TestGitHubTaskProviderMocked:
    """Tests for GitHubTaskProvider with mocked gh CLI."""

    @patch("subprocess.run")
    def test_create_task_calls_gh(self, mock_run, sample_template):
        """create_task calls gh issue create with correct args."""
        mock_run.return_value = MagicMock(
            stdout="https://github.com/test/repo/issues/123\n",
            returncode=0,
        )

        provider = GitHubTaskProvider(repo="test/repo")
        task = provider.create_task(sample_template)

        # Verify gh was called with correct base args
        calls = mock_run.call_args_list
        create_call = [c for c in calls if "issue" in c[0][0] and "create" in c[0][0]][0]
        args = create_call[0][0]

        assert "gh" in args
        assert "issue" in args
        assert "create" in args
        assert "--repo" in args
        assert "test/repo" in args
        assert "--title" in args

    @patch("subprocess.run")
    def test_create_task_parses_issue_number(self, mock_run, sample_template):
        """create_task parses issue number from output."""
        mock_run.return_value = MagicMock(
            stdout="https://github.com/test/repo/issues/456\n",
            returncode=0,
        )

        provider = GitHubTaskProvider(repo="test/repo")
        task = provider.create_task(sample_template)

        assert task.id == "456"
        assert task.url == "https://github.com/test/repo/issues/456"

    @patch("subprocess.run")
    def test_list_tasks_parses_json(self, mock_run):
        """list_tasks parses JSON output into Task objects."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([
                {
                    "number": 1,
                    "title": "Issue 1",
                    "body": "Body 1",
                    "state": "OPEN",
                    "labels": [{"name": "bug"}, {"name": "P1"}],
                    "url": "https://github.com/test/repo/issues/1",
                },
                {
                    "number": 2,
                    "title": "Issue 2",
                    "body": "Body 2",
                    "state": "CLOSED",
                    "labels": [],
                    "url": "https://github.com/test/repo/issues/2",
                },
            ]),
            returncode=0,
        )

        provider = GitHubTaskProvider(repo="test/repo")
        tasks = provider.list_tasks()

        assert len(tasks) == 2
        assert tasks[0].id == "1"
        assert tasks[0].title == "Issue 1"
        assert tasks[0].status == TaskStatus.OPEN
        assert tasks[0].priority == TaskPriority.HIGH  # From P1 label
        assert "bug" in tasks[0].labels

    @patch("subprocess.run")
    def test_close_task_calls_gh(self, mock_run, sample_template):
        """close_task calls gh issue close."""
        # Mock for close and view
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0),  # close
            MagicMock(stdout=json.dumps({
                "number": 1,
                "title": "Test",
                "body": "",
                "state": "CLOSED",
                "labels": [],
                "url": "https://github.com/test/repo/issues/1",
            }), returncode=0),  # view
        ]

        provider = GitHubTaskProvider(repo="test/repo")
        task = provider.close_task("1")

        # Verify close was called
        close_call = mock_run.call_args_list[0]
        args = close_call[0][0]
        assert "close" in args
        assert "1" in args

    @patch("subprocess.run")
    def test_close_task_with_comment(self, mock_run):
        """close_task adds comment if provided."""
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0),  # comment
            MagicMock(stdout="", returncode=0),  # close
            MagicMock(stdout=json.dumps({
                "number": 1,
                "title": "Test",
                "body": "",
                "state": "CLOSED",
                "labels": [],
                "url": "https://github.com/test/repo/issues/1",
            }), returncode=0),  # view
        ]

        provider = GitHubTaskProvider(repo="test/repo")
        task = provider.close_task("1", comment="Done!")

        # Verify comment was called
        comment_call = mock_run.call_args_list[0]
        args = comment_call[0][0]
        assert "comment" in args
        assert "Done!" in args


    @patch("subprocess.run")
    def test_update_task_appends_labels(self, mock_run):
        """update_task calls gh with --add-label (additive behavior)."""
        # Mock for edit and view
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0),  # edit
            MagicMock(stdout=json.dumps({
                "number": 1,
                "title": "Test",
                "body": "",
                "state": "OPEN",
                "labels": [{"name": "existing"}, {"name": "new"}],
                "url": "https://github.com/test/repo/issues/1",
            }), returncode=0),  # view
        ]

        provider = GitHubTaskProvider(repo="test/repo")
        task = provider.update_task("1", {"labels": ["new"]})

        # Verify edit was called with --add-label
        edit_call = mock_run.call_args_list[0]
        args = edit_call[0][0]
        
        assert "issue" in args
        assert "edit" in args
        assert "1" in args
        assert "--add-label" in args
        assert "new" in args
        # Should not have --remove-label or similar
        assert "--remove-label" not in str(args)


# =============================================================================
# Factory Tests
# =============================================================================


class TestGetTaskProvider:
    """Tests for get_task_provider factory function."""

    def test_returns_local_by_name(self, tmp_path):
        """Returns LocalTaskProvider when name='local'."""
        tasks_file = tmp_path / "tasks.json"
        provider = get_task_provider("local", path=str(tasks_file))
        assert isinstance(provider, LocalTaskProvider)
        assert provider.name() == "local"

    def test_raises_for_unknown_name(self):
        """Raises ValueError for unknown provider name."""
        with pytest.raises(ValueError) as exc_info:
            get_task_provider("unknown")
        assert "Unknown provider" in str(exc_info.value)


class TestListProviders:
    """Tests for list_providers function."""

    def test_lists_registered_providers(self):
        """Lists all registered providers."""
        # Force registration by getting a provider
        try:
            get_task_provider("local", path="/tmp/test_tasks.json")
        except:
            pass

        providers = list_providers()
        assert "local" in providers
        assert "github" in providers
