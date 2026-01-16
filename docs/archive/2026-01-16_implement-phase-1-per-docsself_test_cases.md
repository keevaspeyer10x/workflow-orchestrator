# Phase 0: Abstraction Layer - Test Cases

**Task:** Implement Phase 0 of Self-Healing Infrastructure
**Date:** 2026-01-16

---

## Test Structure

```
tests/healing/
├── __init__.py
├── test_environment.py
└── adapters/
    ├── __init__.py
    ├── test_storage_local.py
    ├── test_storage_github.py
    ├── test_git_local.py
    ├── test_git_github.py
    ├── test_cache_local.py
    ├── test_cache_memory.py
    ├── test_execution_local.py
    ├── test_execution_github.py
    └── test_factory.py
```

---

## Test Cases by Component

### 1. Environment Detection (`test_environment.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| ENV-001 | `detect_environment()` with `CLAUDE_CODE_WEB=1` | Returns `Environment.CLOUD` |
| ENV-002 | `detect_environment()` with `CI=true` | Returns `Environment.CI` |
| ENV-003 | `detect_environment()` with `GITHUB_ACTIONS=true` | Returns `Environment.CI` |
| ENV-004 | `detect_environment()` without special env vars | Returns `Environment.LOCAL` |
| ENV-005 | `ENVIRONMENT` singleton is set on module import | Global is populated |

### 2. Storage Adapter - Local (`test_storage_local.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| STL-001 | `read_file()` existing file | Returns file content |
| STL-002 | `read_file()` non-existent file | Raises `FileNotFoundError` |
| STL-003 | `write_file()` new file | Creates file with content |
| STL-004 | `write_file()` existing file | Overwrites content |
| STL-005 | `file_exists()` existing file | Returns `True` |
| STL-006 | `file_exists()` non-existent file | Returns `False` |
| STL-007 | `list_files()` with pattern | Returns matching files |
| STL-008 | `list_files()` empty directory | Returns empty list |

### 3. Storage Adapter - GitHub (`test_storage_github.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| STG-001 | `read_file()` existing file | Returns decoded content from API |
| STG-002 | `read_file()` non-existent file | Raises appropriate error |
| STG-003 | `write_file()` new file | Creates commit via API |
| STG-004 | `write_file()` existing file | Updates file via API |
| STG-005 | `file_exists()` existing file | Returns `True` |
| STG-006 | `file_exists()` non-existent file | Returns `False` |
| STG-007 | API rate limit handling | Retries with backoff on 429 |
| STG-008 | Invalid token | Raises `AuthenticationError` |

### 4. Git Adapter - Local (`test_git_local.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| GTL-001 | `create_branch()` new branch | Branch created from base |
| GTL-002 | `create_branch()` existing branch | Raises error |
| GTL-003 | `apply_diff()` valid diff | Commit created, returns SHA |
| GTL-004 | `apply_diff()` invalid diff | Raises error |
| GTL-005 | `create_pr()` | Not applicable (local-only) |
| GTL-006 | `merge_branch()` clean merge | Merge succeeds |
| GTL-007 | `merge_branch()` with conflicts | Raises `MergeConflictError` |
| GTL-008 | `delete_branch()` existing | Branch deleted |
| GTL-009 | `get_recent_commits()` | Returns commit list |

### 5. Git Adapter - GitHub (`test_git_github.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| GTG-001 | `create_branch()` new branch | Ref created via API |
| GTG-002 | `create_branch()` existing branch | Raises error |
| GTG-003 | `apply_diff()` | Commit created via Trees API |
| GTG-004 | `create_pr()` valid params | PR created, returns URL |
| GTG-005 | `create_pr()` invalid branch | Raises error |
| GTG-006 | `merge_branch()` via API | Merge succeeds |
| GTG-007 | `delete_branch()` | Ref deleted via API |
| GTG-008 | API authentication failure | Raises `AuthenticationError` |

### 6. Cache Adapter - Local SQLite (`test_cache_local.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| CAL-001 | `get()` existing key | Returns cached value |
| CAL-002 | `get()` non-existent key | Returns `None` |
| CAL-003 | `set()` new key with TTL | Value stored with expiry |
| CAL-004 | `set()` existing key | Value updated |
| CAL-005 | `get()` expired key | Returns `None` |
| CAL-006 | `delete()` existing key | Key removed |
| CAL-007 | `delete()` non-existent key | No error |
| CAL-008 | Concurrent access | No deadlocks |

### 7. Cache Adapter - In-Memory (`test_cache_memory.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| CAM-001 | `get()` existing key | Returns cached value |
| CAM-002 | `get()` non-existent key | Returns `None` |
| CAM-003 | `set()` new key with TTL | Value stored with expiry |
| CAM-004 | `get()` expired key | Returns `None` |
| CAM-005 | `delete()` existing key | Key removed |
| CAM-006 | Memory cleanup on expiry | Old entries cleaned |

### 8. Execution Adapter - Local (`test_execution_local.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| EXL-001 | `run_command()` successful | Returns (0, stdout, "") |
| EXL-002 | `run_command()` failure | Returns (non-zero, stdout, stderr) |
| EXL-003 | `run_command()` timeout | Raises `ExecutionTimeoutError` |
| EXL-004 | `run_tests()` all pass | Returns `TestResult(passed=True)` |
| EXL-005 | `run_tests()` some fail | Returns `TestResult(passed=False)` |
| EXL-006 | `run_build()` success | Returns `BuildResult(passed=True)` |
| EXL-007 | `run_build()` failure | Returns `BuildResult(passed=False)` |
| EXL-008 | `run_lint()` clean | Returns `LintResult(passed=True)` |

### 9. Execution Adapter - GitHub Actions (`test_execution_github.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| EXG-001 | `run_tests()` triggers workflow | Workflow dispatched |
| EXG-002 | `run_tests()` workflow success | Returns `TestResult(passed=True)` |
| EXG-003 | `run_tests()` workflow failure | Returns `TestResult(passed=False)` |
| EXG-004 | `run_tests()` workflow timeout | Raises `ExecutionTimeoutError` |
| EXG-005 | `run_build()` triggers workflow | Workflow dispatched |
| EXG-006 | Workflow polling with backoff | Respects rate limits |

### 10. Adapter Factory (`test_factory.py`)

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| FAC-001 | `create_storage()` LOCAL env | Returns `LocalStorageAdapter` |
| FAC-002 | `create_storage()` CLOUD env | Returns `GitHubStorageAdapter` |
| FAC-003 | `create_git()` LOCAL env | Returns `LocalGitAdapter` |
| FAC-004 | `create_git()` CLOUD env | Returns `GitHubAPIAdapter` |
| FAC-005 | `create_cache()` LOCAL env | Returns `LocalSQLiteCache` |
| FAC-006 | `create_cache()` CLOUD env | Returns `InMemoryCache` |
| FAC-007 | `create_execution()` LOCAL env | Returns `LocalExecutionAdapter` |
| FAC-008 | `create_execution()` CLOUD env | Returns `GitHubActionsAdapter` |
| FAC-009 | Factory with missing credentials | Raises `ConfigurationError` |

---

## Integration Tests

| ID | Test Case | Expected Result |
|----|-----------|-----------------|
| INT-001 | Same code path works LOCAL | End-to-end storage/git ops |
| INT-002 | Same code path works CLOUD | End-to-end with GitHub API |
| INT-003 | Environment switch at runtime | Factory produces correct adapters |

---

## Test Fixtures Required

1. **Temporary Git Repository** - For local git adapter tests
2. **Mock HTTP Server** - For GitHub API adapter tests
3. **Temporary SQLite Database** - For local cache tests
4. **Environment Variable Context Manager** - For environment detection tests

---

## Running Tests

```bash
# Run all Phase 0 tests
pytest tests/healing/ -v

# Run only unit tests (fast)
pytest tests/healing/ -v -m "not integration"

# Run integration tests (requires credentials)
pytest tests/healing/ -v -m integration

# Run with coverage
pytest tests/healing/ --cov=src/healing --cov-report=term-missing
```
