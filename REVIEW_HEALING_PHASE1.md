# Code Review: Self-Healing Infrastructure Phase 1

## Summary
This PR implements **Phase 1: Detection, Fingerprinting & Config** of the self-healing infrastructure. It establishes the foundation for error observation by introducing configuration management, unified error models, stable fingerprinting for deduplication, and four distinct error detectors. This is primarily an additive change providing the "eyes" of the system before the "hands" (fix application) are added in Phase 2.

## Critical Issues
*   **None identified.** The changes are additive and well-isolated. The code uses standard library components and introduces no new external dependencies.

## Code Quality & Style
*   **Architecture:** Excellent separation of concerns. The `BaseDetector` pattern allows for easy extension. The split between `Fingerprinter`, `Accumulator`, and `Detectors` makes the logic testable and modular.
*   **Type Safety:** Comprehensive use of type hints (`typing` module) and `dataclasses`.
*   **Robustness:** 
    *   The regex patterns in `SubprocessDetector` cover multiple languages (Python, Rust, Go, Node, pytest) and include fallback mechanisms.
    *   `Fingerprinter` includes extensive normalization (timestamps, UUIDs, memory addresses, temp paths) to ensure stable hashes across environments and runs.
*   **Configuration:** `HealingConfig` correctly implements the "configuration from environment" pattern with sensible defaults and type conversion. The inclusion of safety features like `kill_switch_active` and `protected_paths` is proactive.

## Testing
*   **Coverage:** Extensive new test suite in `tests/healing/`.
    *   **Fingerprinting:** `test_fingerprint.py` thoroughly tests normalization and stability (100 variations test).
    *   **Detectors:** Specific tests for each detector type verify regex matching against realistic error strings.
    *   **Accumulator:** Verifies deduplication logic.
*   **Quality:** Tests use proper mocking and cover edge cases (e.g., unknown error formats, empty inputs).

## Observations & Questions
1.  **Integration Point:** I notice these new components (`Detectors`, `Accumulator`) are not yet instantiated or called by the main orchestrator logic (e.g., `src/engine.py`). This is consistent with a phased "infrastructure-first" rollout, but confirms this code is currently "dormant" until the integration phase.
2.  **Secrets:** A new key `gemini_api_key_fallback` was added to `secrets.enc.yaml`. Ensure this is intended for future redundancy handling.

## Recommendation
**Approve.**
The implementation is high-quality, safe, and strictly follows the design plan. It provides a solid foundation for the subsequent self-healing phases.