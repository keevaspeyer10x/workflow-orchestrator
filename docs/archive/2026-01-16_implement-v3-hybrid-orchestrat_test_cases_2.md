# V3 Hybrid Orchestration - Phase 2 Test Cases

**Task:** Implement v3 hybrid orchestration Phase 2: Artifact-Based Gates
**Date:** 2026-01-16

## Test Categories

### ArtifactGate Tests

| ID | Test | Expected |
|----|------|----------|
| AG-01 | not_empty rejects empty file | False |
| AG-02 | not_empty accepts content | True |
| AG-03 | exists accepts empty file | True |
| AG-04 | json_valid validates JSON | True/False |

### CommandGate Tests

| ID | Test | Expected |
|----|------|----------|
| CG-01 | Command timeout | False, timeout error |
| CG-02 | Success exit code | True |
| CG-03 | Failure exit code | False |

### Adversarial Tests

| ID | Test | Expected |
|----|------|----------|
| ADV-01 | Symlink blocked | Rejected |
| ADV-02 | Path traversal blocked | ValueError |
| ADV-03 | Shell injection blocked | Safe execution |
