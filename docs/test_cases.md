# Test Cases: Fix State File Integrity Warnings (#94)

## Test Cases

| ID | Description | Input | Expected Output |
|----|-------------|-------|-----------------|
| TC-01 | Checksum excludes all metadata | State with _version, _checksum, _updated_at | Hash computed without those fields |
| TC-02 | Save/load roundtrip | Save state, load state | No integrity warning |
| TC-03 | Tampering detected | Modify state file content | Integrity warning appears |
| TC-04 | Existing tests pass | Run pytest | All tests pass |

## Verification

Run orchestrator commands and verify no false-positive integrity warnings.
