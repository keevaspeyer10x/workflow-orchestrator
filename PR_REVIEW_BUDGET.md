# Code Review: V4.2 Phase 2 Token Budget System

## 🏁 Verdict
**Approve with comments.**
The implementation effectively fulfills the requirements for V4.2 Phase 2. The code is well-structured, typed, and follows the architectural patterns established in V4. Concurrency handling in `AtomicBudgetTracker` is robust. However, there is a potential runtime error in the synchronous wrappers that needs addressing before wide usage.

## 🟢 Strengths

1.  **Atomic Operations**: The `reserve` -> `commit`/`rollback` pattern with `BEGIN IMMEDIATE` (via `exclusive_transaction`) correctly prevents race conditions and over-drafting in concurrent scenarios.
2.  **Provider Abstraction**: The `TokenCounter` ABC with specific implementations for Claude (API) and OpenAI (tiktoken) is clean and extensible.
3.  **Fail-Safe Design**:
    - Fallback to `EstimationTokenCounter` ensures the system doesn't crash if external APIs (Anthropic) or libraries (tiktoken) are unavailable.
    - `_cleanup_expired_reservations` prevents "zombie" reservations from blocking the budget indefinitely.
4.  **Event Sourcing**: Full integration with the event store provides a complete audit trail of budget operations.

## 🔴 Concerns & Risks

### 1. `asyncio.run()` in `count_sync` (Runtime Risk)
In `src/v4/budget/counters.py`:
```python
def count_sync(self, text: str) -> int:
    import asyncio
    return asyncio.run(self.count(text))
```
**Risk**: `asyncio.run()` cannot be called from within a running event loop. If a developer uses `count_sync()` inside an existing async application (e.g., inside a FastAPI route or another coroutine), this will raise `RuntimeError: asyncio.run() cannot be called from a running event loop`.
**Recommendation**:
-   Ideally, remove `count_sync` and force async usage to be consistent.
-   Alternatively, check for running loop:
    ```python
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # This is tricky without nesting, usually implies bad design if mixing sync/async this way
        raise RuntimeError("Cannot call sync method from inside event loop. Use await .count() instead.")
    else:
        return asyncio.run(self.count(text))
    ```

### 2. Dependency Injection for `SQLiteAdapter`
In `src/v4/budget/manager.py`:
```python
async def _ensure_adapter(self):
    if self._adapter is None:
        from ..security.async_storage import SQLiteAdapter  # <--- Implicit dependency
        self._adapter = SQLiteAdapter(self.db_path)
```
**Risk**: Hardcoding `SQLiteAdapter` inside the method makes unit testing with mocks harder (though you handled it with `db_path=":memory:"`). It also couples the budget system tightly to the specific storage implementation.
**Recommendation**: Accept an optional `adapter_factory` or pass the adapter instance in `__init__` more explicitly, though the current lazy import does avoid circular dependency issues.

### 3. Schema Initialization Overhead
`_ensure_schema()` runs SQL DDL (`CREATE TABLE IF NOT EXISTS`) on every `create_budget` or `reserve` call for a new `AtomicBudgetTracker` instance.
**Risk**: While low impact for long-lived instances, if trackers are created frequently (e.g., per request), this adds unnecessary DB chatter.
**Recommendation**: Move schema initialization to a dedicated application startup phase or use a shared singleton for schema management.

## 🟡 Questions

1.  **Anthropic Client Lifecycle**: `ClaudeTokenCounter` initializes `anthropic.Anthropic` inside `_get_client`. Does `anthropic.Anthropic` maintain an internal connection pool? If so, recreating it per `ClaudeTokenCounter` instance (if they are short-lived) might be inefficient.
2.  **Reservation ID Collision**: `uuid.uuid4().hex[:12]` provides 48 bits of entropy. While collision is unlikely for moderate volume, why truncate? Full UUIDs are safer if storage allows.

## 🛠️ Suggestions

1.  **Fix `count_sync`**:
    ```python
    def count_sync(self, text: str) -> int:
        """
        Synchronous wrapper. WARNING: Do not use inside async functions.
        """
        try:
            asyncio.get_running_loop()
            raise RuntimeError("Use 'await count()' inside async functions")
        except RuntimeError:
            return asyncio.run(self.count(text))
    ```
2.  **Explicit Timeout Configuration**:
    Allow passing `timeout` to `reserve()` explicitly, overriding the class default. This allows different timeouts for different priority operations (e.g., a quick check vs a long generation).

## Summary
The core logic is sound and safe. The primary actionable item is the `asyncio.run()` usage which is a common footgun in mixed sync/async codebases.
