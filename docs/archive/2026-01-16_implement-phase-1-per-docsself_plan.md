# Phase 0: Abstraction Layer Implementation Plan

**Task:** Implement Phase 0 of Self-Healing Infrastructure
**Reference:** `docs/self-healing-implementation-plan.md`
**Date:** 2026-01-16

---

## Overview

Phase 0 creates the abstraction layer that enables the self-healing infrastructure to work across different environments (local, cloud, CI). This is the foundation layer with no dependencies on other healing components.

## Design Decisions (from User)

1. **Environment Enum**: Separate `src/healing/environment.py` with its own `Environment` enum (LOCAL/CLOUD/CI)
2. **GitHub API**: Direct HTTP API calls via httpx (not gh CLI)
3. **Dependencies**: Required dependencies (not optional extra)

---

## Components to Implement

### 1. Environment Detection (`src/healing/environment.py`)
- `Environment` enum: LOCAL, CLOUD, CI
- `detect_environment()` function
- Global singleton `ENVIRONMENT`

### 2. Abstract Base Classes (`src/healing/adapters/base.py`)
- `StorageAdapter` - file read/write/exists/list
- `GitAdapter` - branch/diff/PR/merge operations
- `CacheAdapter` - get/set/delete with TTL
- `ExecutionAdapter` - command/test/build/lint

### 3. Local Implementations
- `src/healing/adapters/storage_local.py` - LocalStorageAdapter (pathlib)
- `src/healing/adapters/git_local.py` - LocalGitAdapter (git CLI subprocess)
- `src/healing/adapters/cache_local.py` - LocalSQLiteCache (sqlite3)
- `src/healing/adapters/execution_local.py` - LocalExecutionAdapter (asyncio.subprocess)

### 4. Cloud/GitHub Implementations
- `src/healing/adapters/storage_github.py` - GitHubStorageAdapter (Contents API)
- `src/healing/adapters/git_github.py` - GitHubAPIAdapter (Refs/Pulls API)
- `src/healing/adapters/cache_memory.py` - InMemoryCache (dict with TTL)
- `src/healing/adapters/execution_github.py` - GitHubActionsAdapter (workflow dispatch)

### 5. Adapter Factory (`src/healing/adapters/factory.py`)
- `AdapterFactory` class
- Creates appropriate adapters based on detected environment
- Accepts credentials (Supabase URL/key, GitHub token)

### 6. Package Init (`src/healing/__init__.py`, `src/healing/adapters/__init__.py`)
- Export public interfaces

---

## File Structure

```
src/healing/
├── __init__.py
├── environment.py
└── adapters/
    ├── __init__.py
    ├── base.py
    ├── storage_local.py
    ├── storage_github.py
    ├── git_local.py
    ├── git_github.py
    ├── cache_local.py
    ├── cache_memory.py
    ├── execution_local.py
    ├── execution_github.py
    └── factory.py
```

---

## Implementation Order

1. **Environment Detection** (no dependencies)
2. **Abstract Base Classes** (no dependencies)
3. **Local Adapters** (can be implemented in parallel):
   - storage_local.py
   - git_local.py
   - cache_local.py
   - execution_local.py
4. **Cloud Adapters** (can be implemented in parallel):
   - storage_github.py
   - git_github.py
   - cache_memory.py
   - execution_github.py
5. **Factory** (depends on all adapters)
6. **Tests** (depends on implementations)

---

## Dependencies to Add

Add to `pyproject.toml` dependencies:
```
httpx>=0.24.0  # Async HTTP for GitHub API
aiosqlite>=0.19.0  # Async SQLite for local cache
```

Note: `httpx` is already in dev dependencies, will move to required.

---

## Parallel Execution Assessment

**Decision: SEQUENTIAL execution**

**Reason:**
- The implementation order has dependencies (factory depends on adapters, adapters depend on base classes)
- Total files to create: 12 (relatively small)
- Strong type safety needed between components
- Better to ensure consistent code style and patterns
- Risk of merge conflicts in shared files (__init__.py, base.py)

**Alternative considered:** Could parallelize local vs cloud adapters after base classes are done, but the overhead of coordination outweighs benefits for this scope.

---

## Done Criteria (from design doc)

- [ ] All 5 adapter interfaces defined (Storage, Git, Cache, Execution, Factory)
- [ ] Local implementations work for all adapters
- [ ] GitHub API implementations work for Storage and Git
- [ ] GitHub Actions adapter triggers workflows
- [ ] Environment detection correctly identifies LOCAL/CLOUD/CI
- [ ] Factory creates correct adapters per environment
- [ ] Unit tests for each adapter
- [ ] Integration test: same code runs in both environments

---

## Test Plan

```
tests/healing/adapters/
├── test_environment.py
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

Each test file will include:
- Unit tests with mocks for external dependencies
- Integration tests (marked with `@pytest.mark.integration`) for real service tests
