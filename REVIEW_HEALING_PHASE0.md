# Code Review: Self-Healing Infrastructure (Phase 0)

## Summary
The implementation establishes a solid abstraction layer for the self-healing infrastructure, with a clear separation of concerns between local and cloud environments. The interface design (`StorageAdapter`, `GitAdapter`, `CacheAdapter`, `ExecutionAdapter`) is clean and extensible.

However, there is a **critical issue** in the local cache implementation that breaks the async contract, and several cloud adapter methods are currently incomplete placeholders.

## Critical Issues

### 1. Blocking I/O in Async Code (`src/healing/adapters/cache_local.py`)
The `LocalSQLiteCache` implements async methods (`get`, `set`, etc.) but uses the synchronous `sqlite3` library internally.
- **Impact:** This blocks the entire asyncio event loop during database operations, negating the benefits of async/await and potentially freezing the application during heavy cache usage.
- **Recommendation:** Use `aiosqlite` (which is correctly added to `pyproject.toml`) for non-blocking database access.

```python
# Current (Blocking)
conn = sqlite3.connect(str(self.path))
cursor = conn.execute(...)

# Recommended (Async)
async with aiosqlite.connect(self.path) as db:
    async with db.execute(...) as cursor:
        ...
```

## Major Concerns

### 2. Incomplete GitHub API Implementations
Several methods in the GitHub adapters are placeholders:
- **`GitHubAPIAdapter.apply_diff`**: Currently creates an empty commit with a placeholder tree. It does **not** apply the actual diff. This renders the "healing" aspect non-functional in cloud environments if code changes are required.
- **`GitHubStorageAdapter.list_files`**: Returns an empty list `[]`. This will break any logic relying on file discovery (e.g., scanning for test files).

### 3. Missing Conflict Handling in GitHub Storage
`GitHubStorageAdapter.write_file` fetches the current SHA before writing to handle updates, but `_put` does not handle `409 Conflict` responses.
- **Risk:** Race conditions during concurrent fixes could lead to unhandled exceptions rather than retries or graceful failures.

## Minor Issues & Suggestions

1.  **Environment Detection:** The `detect_environment` logic is sound, but consider caching the result or making `ENVIRONMENT` a lazy-loaded property to facilitate testing without patching `os.environ` globally.
2.  **Test Coverage:** `test_concurrent_access` in `test_cache_local.py` passes because the synchronous code forces serial execution. Once switched to `aiosqlite`, this test will actually verify concurrency.
3.  **Type Safety:** `TestResult.failed_tests` is initialized to `None` but post-init sets it to `[]`. Consider setting the default to `field(default_factory=list)` to avoid mutable default argument pitfalls (though dataclasses handle this better than standard classes, it's safer).

## Questions for the Author

1.  What is the plan for implementing the actual diff application in `GitHubAPIAdapter`? Is there a library or strategy selected for parsing diffs and constructing Git trees via API?
2.  Is `GitHubActionsAdapter` intended to support `run_command` in the future (e.g., via a dispatch to a generic "run command" workflow), or will this limitation strictly constrain the types of repairs possible in cloud/CI?

## Verdict
**Changes Requested.** The local cache adapter must be converted to `aiosqlite` before merging. The incomplete GitHub adapter methods should either be implemented or clearly marked as known limitations blocking specific features.