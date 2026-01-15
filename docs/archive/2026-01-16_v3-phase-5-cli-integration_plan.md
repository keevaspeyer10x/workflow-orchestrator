# V3 Hybrid Orchestration - Phase 4 Implementation Plan

**Task:** Implement v3 hybrid orchestration Phase 4: Integration & Hardening
**Date:** 2026-01-16

## Overview

Phase 4 adds integration testing, health checks, and audit logging for production readiness.

## Files to Create/Modify

### 1. `src/audit.py` (NEW)

**Audit Logging System:**
- `AuditLogger` class for secure audit logging
- Log operations: checkpoint create/restore, mode changes, workflow state changes
- Tamper-evident log format with chained hashes
- Configurable log rotation

### 2. `src/health.py` (NEW)

**Health Check System:**
- `HealthChecker` class for system health checks
- Checks: state file integrity, lock state, API connectivity
- Returns structured `HealthReport`

### 3. `src/cli_health.py` (NEW)

**CLI Command:**
- `orchestrator health` command
- Shows status of all components
- JSON output option for automation

### 4. `tests/test_integration_v3.py` (NEW)

**End-to-End Tests:**
- Full workflow cycle (PLAN → EXECUTE → REVIEW → VERIFY → LEARN)
- Checkpoint create/restore cycle
- Gate validation integration

### 5. `tests/test_adversarial_v3.py` (NEW)

**Adversarial Tests:**
- Race conditions (concurrent state access)
- Malformed input handling
- Resource exhaustion

## Execution Strategy

**Parallel execution** - Independent components:
- Audit logging (independent)
- Health checks (independent)
- Integration tests (depends on Phase 0-3)
- Adversarial tests (depends on Phase 0-3)

## Implementation Order

1. Create src/audit.py with AuditLogger
2. Create src/health.py with HealthChecker
3. Create src/cli_health.py for CLI command
4. Create tests/test_integration_v3.py
5. Create tests/test_adversarial_v3.py
6. Run all tests and verify
7. Tag v3-phase4-complete
