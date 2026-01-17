# Code Review: V4.2 Phase 2 Token Budget System

## 🏁 Verdict
**Request Changes**

While the core logic for atomic reservations is sound, there is a critical runtime safety issue and a significant architectural consistency flaw that must be addressed before merging.

## 🚨 Critical Issues

### 1. `asyncio.run()` in Library Code (Runtime Crash Risk)
**File:** `src/v4/budget/counters.py`
```python
def count_sync(self, text: str) -> int:
    import asyncio
    return asyncio.run(self.count(text))
```
**Problem:** Calling `asyncio.run()` from within an existing event loop (e.g., inside a FastAPI route or any other async application) will raise `RuntimeError: asyncio.run() cannot be called from a running event loop`.
**Fix:**
*   **Preferred:** Remove `count_sync` entirely. In an async-first framework, force the user to `await` the counter.
*   **Alternative:** If you must keep it, use a check like `asyncio.get_running_loop()` to warn or fail gracefully, but really, just remove it.

### 2. Dual-Write Inconsistency (Architecture)
**File:** `src/v4/budget/manager.py`
**Problem:** The system updates the `budgets` table and appends to the `EventStore` in two separate operations.
```python
async with adapter.exclusive_transaction() as tx:
    # ... DB Commit happens here ...

# ... if DB commit succeeds but process crashes here ...

if self._event_store:
    # ... Event is never written ...
```
**Impact:** The "Event Sourcing" audit trail is not guaranteed to match the actual budget state. If the process crashes between the DB commit and the Event Store append, you will have a "phantom" reservation that exists in the DB but not in the audit log.
**Fix:** The `EventStore` and `AtomicBudgetTracker` must share the same transaction context if they share the same database, or you need to accept eventual consistency and document it clearly.

## ⚠️ Major Concerns

### 3. Truncated UUIDs (Collision Risk)
**File:** `src/v4/budget/models.py`
```python
id=f"res_{uuid.uuid4().hex[:12]}",
```
**Problem:** Truncating a UUID to 12 hex chars (48 bits) significantly increases collision risk compared to a full UUID (122 bits of entropy). For a financial/budgeting system, "unlikely" isn't good enough.
**Fix:** Use the full UUID. Storage is cheap; debugging a collision in production is expensive.

### 4. Hardcoded Storage Dependency
**File:** `src/v4/budget/manager.py`
```python
async def _ensure_adapter(self):
    if self._adapter is None:
        from ..security.async_storage import SQLiteAdapter
        self._adapter = SQLiteAdapter(self.db_path)
```
**Problem:** `AtomicBudgetTracker` is tightly coupled to `SQLiteAdapter`. You cannot easily swap this for a PostgreSQL adapter or a mock for testing without patching imports.
**Fix:** Inject the adapter factory or the adapter instance in `__init__`.

## 📉 Optimization & Nitpicks

### 5. Schema Check Overhead
**File:** `src/v4/budget/manager.py`
`_ensure_schema()` is called on every `reserve` and `create_budget`. It executes SQL (`CREATE TABLE IF NOT EXISTS`) every time.
**Fix:** Use a properly initialized flag at the class/instance level or move schema migration to a startup script.

### 6. Token Estimation Heuristic
**File:** `src/v4/budget/counters.py`
The `EstimationTokenCounter` uses `len(text) // 4`.
**Context:** For code or special characters, this can be wildly inaccurate.
**Suggestion:** Consider a slightly more robust heuristic or simply document the margin of error clearly.

## 🧪 Testing
Tests passed, but they use `AtomicBudgetTracker` in isolation. The "Dual Write" issue isn't caught because the tests don't simulate a crash between the two operations.
