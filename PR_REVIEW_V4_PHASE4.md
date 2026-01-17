# Code Review: V4.2 Phase 4 Chat Mode

## Summary
The implementation structure closely follows the design plan. The separation of concerns between `ChatSession`, `SafeContextManager`, and `SummaryValidator` is clean. However, there is a **critical logical flaw** in how session restoration interacts with crash recovery that invalidates the "undo" functionality of a restore.

## Critical Issues

### 1. Broken Crash Recovery for Restored Sessions
**Severity: High**
The `restore` command resets the in-memory state and appends a `SESSION_RESTORED` event, but it **does not** create a new checkpoint. The `recover` method loads the *latest* checkpoint and replays *all* subsequent `MESSAGE_ADDED` events, ignoring `SESSION_RESTORED`.

**Scenario:**
1. User sends `A`, `B`. Checkpoint `C1` created (State: `[A, B]`).
2. User sends `C`. (Event Stream: `... C1 -> Msg(C)`).
3. User runs `/restore C1`. In-memory state reverts to `[A, B]`. (Event Stream: `... C1 -> Msg(C) -> Restore(C1)`).
4. User sends `D`. (State: `[A, B, D]`. Event Stream: `... C1 -> Msg(C) -> Restore(C1) -> Msg(D)`).
5. **CRASH & RECOVER**:
   - Loads `C1` (State: `[A, B]`).
   - Replays `Msg(C)` -> State: `[A, B, C]`.
   - Replays `Restore(C1)` -> **Ignored** (no logic to handle it).
   - Replays `Msg(D)` -> State: `[A, B, C, D]`.

**Result:** The message `C` (which was explicitly removed by the user) is resurrected. The session state is corrupted.

**Fix:**
The `restore` method must create a new checkpoint immediately after resetting the state. This ensures `recover` loads from this new, correct baseline.

```python
# In ChatSession.restore():
# ... restore state ...
self._event_version = await self.event_store.get_stream_version(self.stream_id)

# Create a new checkpoint immediately to anchor this state
await self.checkpoint(message=f"Restored from {checkpoint_id}") 
```

## Code Quality & Concerns

### 2. Hardcoded Model Names
**Severity: Medium**
`src/v4/chat/session.py` and `src/v4/chat/context.py` both have `claude-sonnet-4-20250514` hardcoded.
- **Risk:** If the model is deprecated or we switch providers, this breaks.
- **Fix:** Move this to `SessionConfig` or use the `LLMCallWrapper`'s default model.

### 3. Context Construction Ordering
**Severity: Low (UX)**
In `SafeContextManager.prepare_context`, the order is `[Summary] + [Pinned] + [Recent]`.
- If a user pins a message from the middle of a conversation, it will appear *after* the summary (which covers the beginning). This is generally acceptable but might lose some chronological nuance.
- **Suggestion:** No code change needed immediately, but verify this behavior matches user mental models.

### 4. Validator "Decision" Logic
**Severity: Low**
The regex-based decision extraction (`DECISION_KEYWORDS`) is a heuristic. It might be too aggressive (flagging "I decided to go for lunch" as a critical decision).
- **Suggestion:** Acceptable for Phase 4.2, but mark for future improvement (possibly small LLM classifier later).

## Questions
1. Why is the model hardcoded instead of passed via `config`?
2. Are there plans to handle `SESSION_RESTORED` events in the `recover` replay loop if we don't checkpoint? (Checkpointing is the better fix).

## Recommendation
**Request Changes.** Do not merge until the restore/recover bug is fixed. The system currently fails to guarantee state consistency after a crash if a restore has occurred.
