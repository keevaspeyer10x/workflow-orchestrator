# Code Review: CORE-024 & CORE-023-P3 (Session Logging & Conflict Learning)

## Summary
This PR implements two major features:
1.  **Session Management (CORE-024):** Replaces the flaky `ClaudeSquadAdapter` with a robust `TmuxAdapter` for interactive sessions and `SubprocessAdapter` for fallback. It also adds `TranscriptLogger` for secure, scrubbed session logging.
2.  **Conflict Learning (CORE-023-P3):** Introduces a learning module to analyze conflict patterns and suggest roadmap improvements.

## 🟢 Strengths

### 1. Robust Adapter Architecture (`src/prd/tmux_adapter.py`)
*   **Reliability:** Direct `tmux` management is far superior to the previous TUI wrapper approach.
*   **Safety:** The `TranscriptLogger` implements multi-layer scrubbing (known secrets + regex patterns) which is crucial for security.
*   **Fallback:** `SubprocessAdapter` ensures the system works in CI/CD and non-tmux environments.

### 2. Comprehensive CLI Updates (`src/cli.py`)
*   **New Commands:** `orchestrator sessions` command provides excellent visibility into agent activities.
*   **Integration:** `cmd_prd_spawn`, `cmd_prd_sessions`, `cmd_prd_attach` all correctly use the `BackendSelector`.
*   **Fix Applied:** I manually renamed `check-squad` to `check-backend` and updated it to use `BackendSelector`, as the original implementation was stale.

### 3. Conflict Learning (`src/resolution/learning.py`)
*   **Insights:** The ability to analyze `.workflow_log.jsonl` and auto-suggest roadmap items for frequent conflict zones is a high-value feature.
*   **Configurability:** `UserConfig` now supports `file_policies` and thresholds for learning.

## 🛠 Fixes Applied During Review

1.  **CLI Fix:** Renamed `cmd_prd_check_squad` to `cmd_prd_check_backend` in `src/cli.py` and updated it to use `BackendSelector` and `TmuxAdapter` for checks, removing the dependency on the deprecated `CapabilityDetector`.
2.  **Git State:** Added untracked new files (`src/transcript_logger.py`, `src/resolution/learning.py`, etc.) to the staging area.

## 🔍 Verification

### Automated Tests
Ran `pytest` on:
*   `tests/test_transcript_logger.py`: **PASSED** (Covers scrubbing and logging)
*   `tests/test_conflict_learning.py`: **PASSED** (Covers pattern detection and roadmap updates)
*   `tests/prd/`: **PASSED** (Covers all adapter logic including Tmux and Subprocess)

### Manual Code Inspection
*   **Secrets:** Verified `get_all_known_secrets` in `src/secrets.py` correctly aggregates secrets for the logger.
*   **Deprecation:** Confirmed old adapter code was moved to `src/prd/_deprecated/` and tests updated to point there.

## 🏁 Conclusion
**APPROVED.** The changes are architecturally sound, well-tested, and significant improvements over the previous implementation. The minor CLI fix has been applied.

```bash
# To verify the fix:
orchestrator prd check-backend
```