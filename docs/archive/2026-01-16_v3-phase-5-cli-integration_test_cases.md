# V3 Hybrid Orchestration - Phase 4 Test Cases

**Task:** Implement v3 hybrid orchestration Phase 4: Integration & Hardening
**Date:** 2026-01-16

## Test Categories

### Audit Logging Tests

| ID | Test | Expected |
|----|------|----------|
| AL-01 | Log checkpoint create | Entry with chained hash |
| AL-02 | Log mode change | Entry with old/new modes |
| AL-03 | Tamper detection | Raises on hash mismatch |
| AL-04 | Log rotation | Old logs archived |

### Health Check Tests

| ID | Test | Expected |
|----|------|----------|
| HC-01 | State file healthy | Returns OK status |
| HC-02 | State file corrupted | Returns ERROR status |
| HC-03 | Lock state healthy | Returns OK status |
| HC-04 | Full health report | All components checked |

### Integration Tests

| ID | Test | Expected |
|----|------|----------|
| INT-01 | Full workflow cycle | All phases complete |
| INT-02 | Checkpoint round-trip | State restored correctly |
| INT-03 | Gate integration | Gates block/allow correctly |

### Adversarial Tests

| ID | Test | Expected |
|----|------|----------|
| ADV-01 | Concurrent state access | No corruption |
| ADV-02 | Malformed JSON state | Graceful error |
| ADV-03 | Large checkpoint | Memory limits respected |
