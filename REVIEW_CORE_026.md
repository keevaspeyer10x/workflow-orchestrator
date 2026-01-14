# Code Review: CORE-026 Review Resilience

## Summary
The changes implement a robust system for handling review failures, specifically focusing on API key recovery. The code introduces typed errors, proactive validation, and user-friendly recovery instructions. I found and fixed duplication in API key mappings and improved the dynamic resolution of secrets file paths.

## Key Findings

### 1. Duplicate Configuration (Fixed)
*   **Issue:** `MODEL_TO_API_KEY` was defined in both `src/review/router.py` and `src/review/recovery.py`.
*   **Fix:** Extracted to `src/review/constants.py` and updated both files to import it. This ensures a single source of truth for model-to-key mappings.

### 2. Hardcoded Paths (Fixed)
*   **Issue:** Recovery instructions in `src/review/recovery.py` hardcoded `secrets.enc.yaml` as the SOPS file path.
*   **Fix:** Updated `recovery.py` to use `SecretsManager.list_sources()` to dynamically determine the configured SOPS file path (defaulting to `secrets.enc.yaml` if lookup fails).

### 3. Architecture & Patterns
*   **Pattern Adherence:** The changes follow the project's pattern of using `src/engine.py` for core logic and `src/cli.py` for user interaction. The `ReviewErrorType` enum improves error handling granularity.
*   **Resilience:** The new `validate_api_keys` (proactive) and `review-retry` command (reactive) significantly improve the user experience when API keys are missing or invalid.

### 4. Testing
*   **Coverage:** `tests/test_review_resilience.py` provides good coverage for the new types, validation logic, and recovery flow.
*   **Verification:** All 30 tests in the resilience suite passed after refactoring.

## Refactoring Actions Taken
1.  Created `src/review/constants.py`.
2.  Refactored `src/review/router.py` to remove local key mapping.
3.  Refactored `src/review/recovery.py` to use shared constants and dynamic secrets path.

## Next Steps
*   Implement the actual API ping in `validate_api_keys` (currently a TODO).
*   Ensure `required_reviews` in `workflow.yaml` is populated for standard workflows.