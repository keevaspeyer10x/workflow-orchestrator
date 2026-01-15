# Issue #56: Test Cases

## Unit Tests - Interface (`test_task_provider.py`)

### TaskStatus Enum
- [x] TEST: TaskStatus has OPEN, IN_PROGRESS, BLOCKED, CLOSED values
- [x] TEST: TaskStatus.value returns lowercase strings

### TaskPriority Enum
- [x] TEST: TaskPriority has CRITICAL=P0, HIGH=P1, MEDIUM=P2, LOW=P3
- [x] TEST: TaskPriority values sort correctly (P0 < P1 < P2 < P3)

### Task Dataclass
- [x] TEST: Task can be created with required fields (id, title, body, status)
- [x] TEST: Task optional fields default correctly (priority=None, labels=[], url=None)
- [x] TEST: Task can be serialized to dict via asdict()

### TaskTemplate Dataclass
- [x] TEST: TaskTemplate can be created with required fields
- [x] TEST: TaskTemplate defaults: recommendation="IMPLEMENT", priority=MEDIUM

## Unit Tests - LocalTaskProvider

### Initialization
- [x] TEST: Creates config directory if not exists
- [x] TEST: Creates tasks.json with empty state if not exists
- [x] TEST: Loads existing tasks.json if present

### create_task()
- [x] TEST: Creates task with auto-incremented ID
- [x] TEST: Persists task to JSON file
- [x] TEST: Returns Task object with all fields populated

### list_tasks()
- [x] TEST: Returns all tasks when no filter
- [x] TEST: Filters by status correctly
- [x] TEST: Filters by priority correctly
- [x] TEST: Returns empty list when no matches

### get_next_task()
- [x] TEST: Returns highest priority open task
- [x] TEST: Returns None when no open tasks
- [x] TEST: P0 task returned before P2 task

### close_task()
- [x] TEST: Updates task status to CLOSED
- [x] TEST: Persists change to JSON file
- [x] TEST: Raises error for non-existent task ID

### update_task()
- [x] TEST: Updates specified fields
- [x] TEST: Preserves non-updated fields
- [x] TEST: Raises error for non-existent task ID

## Unit Tests - GitHubTaskProvider

### Initialization
- [x] TEST: Auto-detects repo from git remote
- [x] TEST: Accepts explicit repo parameter
- [x] TEST: Raises error if not in git repo and no repo specified

### _detect_repo()
- [x] TEST: Parses HTTPS URL (https://github.com/owner/repo.git)
- [x] TEST: Parses SSH URL (git@github.com:owner/repo.git)
- [x] TEST: Handles URLs without .git suffix

### _render_body()
- [x] TEST: Renders TaskTemplate to markdown
- [x] TEST: Includes all sections (Status, Priority, Description, Tasks, YAGNI)
- [x] TEST: Escapes special characters

### create_task() (integration)
- [x] TEST: Calls gh issue create with correct arguments
- [x] TEST: Parses issue URL from output
- [x] TEST: Returns Task with URL populated

### list_tasks() (integration)
- [x] TEST: Calls gh issue list with correct filters
- [x] TEST: Parses JSON output into Task objects
- [x] TEST: Maps GitHub labels to Task.labels

### close_task() (integration)
- [x] TEST: Calls gh issue close with task ID
- [x] TEST: Adds comment if provided

## Integration Tests - CLI

### orchestrator task create
- [x] TEST: Interactive prompts capture all fields
- [x] TEST: Creates task via configured backend
- [x] TEST: Displays created task info

### orchestrator task list
- [x] TEST: Displays tasks in table format
- [x] TEST: Respects --status filter
- [x] TEST: Respects --priority filter

### orchestrator task next
- [x] TEST: Displays highest priority open task
- [x] TEST: Shows "No open tasks" when empty

### orchestrator task close
- [x] TEST: Closes task by ID
- [x] TEST: Shows error for invalid ID
- [x] TEST: Accepts optional --comment

### orchestrator task add
- [x] TEST: Quick add with just title
- [x] TEST: Defaults to MEDIUM priority
- [x] TEST: Defaults to OPEN status

## Test Fixtures

```python
@pytest.fixture
def temp_tasks_file(tmp_path):
    """Create temporary tasks.json for testing"""
    tasks_file = tmp_path / "tasks.json"
    return tasks_file

@pytest.fixture
def local_provider(temp_tasks_file):
    """Create LocalTaskProvider with temp file"""
    return LocalTaskProvider(path=str(temp_tasks_file))

@pytest.fixture
def sample_template():
    """Create sample TaskTemplate for testing"""
    return TaskTemplate(
        title="Test Task",
        description="Test description",
        problem_solved="Solves test problem",
    )
```

## Mocking Strategy

- **Local backend**: Use temp directory, no mocks needed
- **GitHub backend**: Mock `subprocess.run` for gh CLI calls
- **CLI tests**: Use Click's CliRunner or subprocess
