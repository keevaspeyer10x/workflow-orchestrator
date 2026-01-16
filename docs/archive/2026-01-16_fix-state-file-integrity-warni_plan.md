# Phase 1 Implementation Plan: Detection, Fingerprinting & Config

**Workflow ID:** wf_910e4223
**Date:** 2026-01-16
**Status:** Planning

---

## Overview

Phase 1 builds on the Phase 0 abstraction layer to implement error detection, fingerprinting, and configuration management. This phase is **observation-only** - no fixes are applied yet.

## Decisions from Clarifying Questions

1. **Config Source:** Env-only in Phase 1, Supabase integration in Phase 2
2. **Detectors:** All 4 (WorkflowLog, Subprocess, Transcript, Hook)
3. **API Style:** Sync for compute-only code, async for I/O
4. **Testing:** Comprehensive fingerprint stability tests

## Components to Implement

### 1. Configuration (`src/healing/config.py`)

**Purpose:** Load configuration from environment variables (Supabase in Phase 2)

```python
@dataclass
class HealingConfig:
    # Feature flags
    enabled: bool = True
    auto_apply_safe: bool = True
    auto_apply_moderate: bool = False

    # Cost controls
    max_daily_cost_usd: float = 10.0
    max_validations_per_day: int = 100
    max_cost_per_validation_usd: float = 0.50

    # Safety
    protected_paths: list[str]  # e.g., "src/auth/**", "migrations/**"

    # Kill switch
    kill_switch_active: bool = False

    # Timeouts
    build_timeout_seconds: int = 300
    test_timeout_seconds: int = 600
    lint_timeout_seconds: int = 60
    judge_timeout_seconds: int = 30

    @classmethod
    def from_environment(cls) -> "HealingConfig"
```

**Key env vars:**
- `HEALING_ENABLED` (default: true)
- `HEALING_KILL_SWITCH` (default: false)
- `HEALING_MAX_DAILY_COST` (default: 10.0)
- `HEALING_PROTECTED_PATHS` (comma-separated globs)

### 2. Error Event Model (`src/healing/models.py`)

**Purpose:** Unified error representation from any source

```python
@dataclass
class ErrorEvent:
    error_id: str
    timestamp: datetime
    source: Literal["workflow_log", "transcript", "subprocess", "hook"]

    # Content
    description: str
    error_type: Optional[str]  # e.g., "TypeError", "ImportError"
    file_path: Optional[str]
    line_number: Optional[int]
    stack_trace: Optional[str]
    command: Optional[str]  # For subprocess errors
    exit_code: Optional[int]

    # Computed (by Fingerprinter)
    fingerprint: Optional[str]  # Fine-grained (16 hex chars)
    fingerprint_coarse: Optional[str]  # Broad grouping (8 hex chars)

    # Context
    workflow_id: Optional[str]
    phase_id: Optional[str]
    project_id: Optional[str]
```

### 3. Fingerprinter (`src/healing/fingerprint.py`)

**Purpose:** Generate stable, normalized fingerprints for error deduplication

**Key features:**
- Normalize paths, line numbers, UUIDs, timestamps, memory addresses
- Extract error type from various languages (Python, Node, Rust, Go)
- Extract top stack frame for fine-grained matching
- Coarse fingerprint for broad grouping

**Normalization patterns:**
- `/home/user/project/foo.py` → `<path>/foo.py`
- `foo.py:123` → `foo.py:<line>`
- `0x7fff12345678` → `<addr>`
- UUIDs → `<uuid>`
- Timestamps → `<timestamp>`

### 4. Error Detectors (`src/healing/detectors/`)

#### 4.1 Base Detector (`base.py`)
```python
class BaseDetector(ABC):
    def __init__(self, fingerprinter: Fingerprinter):
        self.fingerprinter = fingerprinter

    @abstractmethod
    def detect(self, source: any) -> list[ErrorEvent]:
        """Detect errors from source."""

    def _fingerprint(self, error: ErrorEvent) -> ErrorEvent:
        """Add fingerprints to error."""
```

#### 4.2 Workflow Log Detector (`workflow_log.py`)
- Parses `.workflow_log.jsonl`
- Extracts events with `event_type: "error"` or `success: false`
- Maps log fields to ErrorEvent

#### 4.3 Subprocess Detector (`subprocess.py`)
- Parses command output (stdout/stderr)
- Detects patterns for Python, Rust, Go, Node, pytest
- Maps to ErrorEvent with command and exit_code

#### 4.4 Transcript Detector (`transcript.py`)
- Parses conversation transcript (Claude Code history)
- Detects error patterns mentioned in conversation
- Associates with workflow context

#### 4.5 Hook Detector (`hook.py`)
- Real-time detection from hook output
- Integrates with orchestrator hooks (pre/post command)

### 5. Error Accumulator (`src/healing/accumulator.py`)

**Purpose:** Deduplicate errors within a session

```python
@dataclass
class ErrorAccumulator:
    _errors: dict[str, ErrorEvent]  # fingerprint -> event
    _counts: dict[str, int]  # fingerprint -> count
    _first_seen: dict[str, datetime]

    def add(self, error: ErrorEvent) -> bool:
        """Add error. Returns True if new, False if duplicate."""

    def get_unique_errors(self) -> list[ErrorEvent]
    def get_count(self, fingerprint: str) -> int
    def get_summary(self) -> dict
    def clear(self) -> None
```

## File Structure

```
src/healing/
├── __init__.py          # Updated exports
├── environment.py       # (Phase 0 - exists)
├── config.py            # NEW: Configuration
├── models.py            # NEW: ErrorEvent, etc.
├── fingerprint.py       # NEW: Fingerprinter
├── accumulator.py       # NEW: ErrorAccumulator
├── adapters/            # (Phase 0 - exists)
│   └── ...
└── detectors/           # NEW: Detection
    ├── __init__.py
    ├── base.py
    ├── workflow_log.py
    ├── subprocess.py
    ├── transcript.py
    └── hook.py

tests/healing/
├── test_config.py           # NEW
├── test_fingerprint.py      # NEW
├── test_accumulator.py      # NEW
└── detectors/
    ├── __init__.py          # NEW
    ├── test_workflow_log.py # NEW
    ├── test_subprocess.py   # NEW
    ├── test_transcript.py   # NEW
    └── test_hook.py         # NEW
```

## Implementation Order

1. `config.py` - Foundation, no dependencies
2. `models.py` - Data structures
3. `fingerprint.py` - Core algorithm
4. `detectors/base.py` - Abstract base
5. `detectors/workflow_log.py` - Most useful detector
6. `detectors/subprocess.py` - Command output parsing
7. `detectors/transcript.py` - Conversation parsing
8. `detectors/hook.py` - Real-time integration
9. `accumulator.py` - Session management
10. Tests for all components

## Dependencies

- Phase 0 adapters (for environment detection)
- Python 3.10+ (dataclasses, typing)
- Standard library only (no new deps for core)

## Execution Mode

**SEQUENTIAL execution** - Decision documented:

**Rationale:**
1. Components have tight dependencies (each builds on previous)
2. Shared data models require coordination that would add overhead
3. Total implementation ~500 lines - not large enough for parallel benefit
4. Verification between layers catches issues early

**Order:**
1. `config.py` + tests
2. `models.py` + tests
3. `fingerprint.py` + tests
4. `detectors/base.py`
5. `detectors/workflow_log.py` + `detectors/subprocess.py` + tests
6. `detectors/transcript.py` + `detectors/hook.py` + tests
7. `accumulator.py` + tests
8. Integration tests

## Success Criteria (Done Criteria from Plan)

- [ ] Config loads from env vars
- [ ] Kill switch stops all operations when active
- [ ] Fingerprinter passes stability tests (100+ error variations)
- [ ] All 4 detectors implemented
- [ ] Accumulator correctly deduplicates
- [ ] Works in both LOCAL and CLOUD environments
- [ ] Unit tests for all components
- [ ] Integration test: run detection on real workflow log
