# Code Review: External Review Enforcement & API Key Handling

## Summary
This PR enforces external AI reviews by making API keys mandatory, adding tracking for review execution, and surfacing review status in the workflow finish summary. It also refactors `run_auto_review` to return structured metadata.

## 🔍 Findings & Analysis

### 1. Security & Configuration (`install.sh`, `CLAUDE.md`, `workflow.yaml`)
*   **API Key Enforcement:** The scripts now explicitly check for `GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.
    *   *Critique:* Hardcoding specific provider keys (`GEMINI`, `XAI`, `OPENAI`) in `install.sh` makes the tooling brittle. If we switch providers or add a new one, this script breaks or becomes outdated.
    *   *Security:* The recommended `eval "$(sops -d ...)"` pattern is standard for local dev but assumes the user has `sops` and the correct GPG/Age keys set up. The warning message is helpful.

### 2. Logic & Architecture (`src/cli.py`)
*   **Signature Change:** `run_auto_review` now returns a 4-element tuple.
    *   *Verification:* I confirmed `run_auto_review` is internal to `src/cli.py` and used in `cmd_complete`. The change is safe from a refactoring perspective.
*   **Metadata Tracking:** Storing review results in `engine.state.metadata["review_models"]` is a good addition for audit trails.
*   **Error Handling (Concern):** In `cmd_finish`, the parsing of `LEARNINGS.md` is wrapped in a broad `try...except Exception: pass`.
    *   *Risk:* If parsing fails due to a minor formatting issue, the user gets no feedback, and the section just silently disappears. Debugging this will be painful.
    *   *Recommendation:* Log the error to stderr or a debug log instead of silencing it completely.

### 3. Testing (`tests/`)
*   **Test Deletion:** `tests/test_cases.md` was deleted.
    *   *Major Concern:* I see no corresponding *automated* tests added to replace these manual test cases. `grep` checks confirmed `run_auto_review` has **zero** direct unit test coverage in `tests/`.
    *   *Gap:* We are adding logic to enforce reviews and track metadata, but we have no tests verifying:
        1.  That metadata is actually saved correctly.
        2.  That `cmd_finish` renders the summary correctly.
        3.  That missing keys actually fail the review as expected (programmatically).

### 4. Schema (`src/schema.py`)
*   Added `REVIEW_STARTED`, `REVIEW_COMPLETED`, etc.
    *   *Note:* Good, but are these events actually *emitted*? The diff shows changes to `cli.py` but I didn't see explicit `engine.emit(EventType.REVIEW_STARTED)` calls in the diff for `cli.py`. (checked again: `src/cli.py` changes didn't show event emission updates, just metadata updates).

## 🛠 Recommendations

1.  **Add Tests:** Please add a unit test for `run_auto_review` in a new `tests/test_cli_reviews.py` or similar. Mock `ReviewRouter` and verify the returned dictionary structure.
2.  **Fix Error Swallowing:** Change the `except Exception:` block in `cmd_finish` to at least print a warning: `print(f"Warning: Could not parse LEARNINGS.md: {e}", file=sys.stderr)`.
3.  **Verify Event Emission:** Ensure the new `EventType` values are actually used. If they are just unused constants, remove them or implement the emission logic.

## 🏁 Conclusion
**Request Changes.** The logic is sound, but deleting the test plan without adding automated tests—especially while adding complexity to the review workflow—is a regression in quality assurance. The "silently fail" behavior in `cmd_finish` also needs addressing.
