# Test Cases: Phase 1 - Detection, Fingerprinting & Config

**Date:** 2026-01-16

---

## 1. Configuration Tests (`tests/healing/test_config.py`)

### 1.1 Environment Variable Loading
- `test_config_from_environment_defaults` - Returns defaults when no env vars set
- `test_config_from_environment_enabled` - Reads HEALING_ENABLED correctly
- `test_config_from_environment_kill_switch` - Reads HEALING_KILL_SWITCH correctly
- `test_config_from_environment_cost_limits` - Parses HEALING_MAX_DAILY_COST as float
- `test_config_from_environment_protected_paths` - Parses comma-separated globs
- `test_config_from_environment_invalid_float` - Falls back to default on invalid

### 1.2 Kill Switch Behavior
- `test_kill_switch_active` - Returns True when kill_switch_active=True
- `test_kill_switch_inactive` - Returns False when kill_switch_active=False

**Total: 8 tests**

---

## 2. Error Event Model Tests (`tests/healing/test_models.py`)

### 2.1 ErrorEvent Creation
- `test_error_event_required_fields` - Creates with required fields only
- `test_error_event_all_fields` - Creates with all optional fields
- `test_error_event_timestamp_default` - Uses provided timestamp
- `test_error_event_source_literal` - Validates source is one of allowed values

**Total: 4 tests**

---

## 3. Fingerprinter Tests (`tests/healing/test_fingerprint.py`)

### 3.1 Basic Fingerprinting
- `test_fingerprint_same_error_same_hash` - Same error produces same fingerprint
- `test_fingerprint_different_error_different_hash` - Different errors produce different fingerprints
- `test_fingerprint_length` - Fingerprint is 16 hex characters
- `test_fingerprint_coarse_length` - Coarse fingerprint is 8 hex characters

### 3.2 Normalization
- `test_normalize_file_paths` - `/home/user/project/foo.py` → `<path>/foo.py`
- `test_normalize_line_numbers` - `foo.py:123` → `foo.py:<line>`
- `test_normalize_uuids` - UUIDs → `<uuid>`
- `test_normalize_timestamps` - Various timestamp formats → `<timestamp>`
- `test_normalize_memory_addresses` - `0x7fff12345678` → `<addr>`
- `test_normalize_temp_paths` - `/tmp/xxx/` → `<tmpdir>/`
- `test_normalize_pids` - `pid=12345` → `pid=<pid>`
- `test_normalize_long_strings` - Long quoted strings → `"<string>"`

### 3.3 Error Type Extraction
- `test_extract_error_type_python` - `TypeError: ...` → `TypeError`
- `test_extract_error_type_python_exception` - `ValueError: ...` → `ValueError`
- `test_extract_error_type_node` - `Error: ...` → `Error`
- `test_extract_error_type_rust` - `error[E0001]: ...` → `RustError_E0001`
- `test_extract_error_type_go` - `panic: ...` → `GoPanic`
- `test_extract_error_type_unknown` - Falls back to `UnknownError`

### 3.4 Stack Frame Extraction
- `test_extract_top_frame_python` - `File "foo.py", line 10, in main` → `foo.py:main`
- `test_extract_top_frame_node` - `at foo (/path/bar.js:10:5)` → `bar.js:foo`
- `test_extract_top_frame_none` - Returns None for unparseable traces

### 3.5 Stability Tests (Comprehensive)
- `test_fingerprint_stability_100_variations` - Same error with variations produces same fingerprint
- `test_fingerprint_stability_cross_machine` - Different absolute paths, same relative → same fingerprint
- `test_fingerprint_stability_timestamp_variation` - Different timestamps → same fingerprint

**Total: 24 tests**

---

## 4. Detector Tests

### 4.1 Base Detector (`tests/healing/detectors/test_base.py`)
- `test_base_detector_fingerprint_adds_hashes` - Adds both fingerprint and fingerprint_coarse
- `test_base_detector_abstract_detect` - Cannot instantiate abstract class

**Total: 2 tests**

### 4.2 Workflow Log Detector (`tests/healing/detectors/test_workflow_log.py`)
- `test_detect_no_errors` - Empty errors list for successful workflow
- `test_detect_single_error` - Parses single error event
- `test_detect_multiple_errors` - Parses multiple error events
- `test_detect_error_event_fields` - Correctly maps JSONL fields to ErrorEvent
- `test_detect_file_not_found` - Handles missing log file gracefully
- `test_detect_invalid_json` - Handles malformed JSONL lines

**Total: 6 tests**

### 4.3 Subprocess Detector (`tests/healing/detectors/test_subprocess.py`)
- `test_detect_success_no_errors` - Exit code 0 returns empty list
- `test_detect_python_error` - Parses Python error from stderr
- `test_detect_python_traceback` - Extracts stack trace
- `test_detect_pytest_failure` - Parses pytest failure output
- `test_detect_rust_error` - Parses Rust compiler error
- `test_detect_go_panic` - Parses Go panic
- `test_detect_node_error` - Parses Node.js error
- `test_detect_unknown_error` - Returns generic error for unrecognized patterns

**Total: 8 tests**

### 4.4 Transcript Detector (`tests/healing/detectors/test_transcript.py`)
- `test_detect_no_errors_in_transcript` - Clean conversation returns empty
- `test_detect_error_mentioned` - Finds error in conversation text
- `test_detect_error_with_context` - Extracts surrounding context
- `test_detect_multiple_errors` - Finds all errors in transcript
- `test_detect_associates_workflow_id` - Links to workflow context

**Total: 5 tests**

### 4.5 Hook Detector (`tests/healing/detectors/test_hook.py`)
- `test_detect_from_hook_output` - Parses hook stdout/stderr
- `test_detect_hook_exit_code` - Uses exit code in detection
- `test_detect_hook_context` - Includes hook name in error context

**Total: 3 tests**

---

## 5. Accumulator Tests (`tests/healing/test_accumulator.py`)

### 5.1 Basic Operations
- `test_add_new_error_returns_true` - First occurrence returns True
- `test_add_duplicate_returns_false` - Duplicate fingerprint returns False
- `test_get_unique_errors` - Returns deduplicated list
- `test_get_count` - Returns occurrence count for fingerprint
- `test_clear` - Empties all internal state

### 5.2 Summary
- `test_summary_unique_errors` - Correct unique count
- `test_summary_total_occurrences` - Correct total count
- `test_summary_by_type` - Groups by error type

### 5.3 Edge Cases
- `test_accumulator_empty` - Handles empty state gracefully
- `test_accumulator_single_error` - Handles single error
- `test_accumulator_many_duplicates` - Handles many duplicates efficiently

**Total: 11 tests**

---

## Integration Tests

### 6.1 End-to-End Detection (`tests/healing/test_integration.py`)
- `test_detect_errors_from_real_workflow_log` - Process actual workflow log fixture
- `test_fingerprint_dedup_across_detectors` - Same error from different sources deduped
- `test_config_controls_detection` - Kill switch stops detection

**Total: 3 tests**

---

## Test Summary

| Component | Test Count |
|-----------|------------|
| Config | 8 |
| Models | 4 |
| Fingerprinter | 24 |
| Base Detector | 2 |
| Workflow Log Detector | 6 |
| Subprocess Detector | 8 |
| Transcript Detector | 5 |
| Hook Detector | 3 |
| Accumulator | 11 |
| Integration | 3 |
| **Total** | **74** |
