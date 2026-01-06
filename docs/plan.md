# Implementation Plan: Roadmap Items CORE-007, CORE-008, ARCH-001, WF-004

## Overview

This plan covers 4 low-complexity roadmap items that improve code quality, security, and developer experience.

## Items to Implement

### 1. CORE-007: Deprecate Legacy Claude Integration
**File:** `src/claude_integration.py`

**Tasks:**
- Add deprecation warning at module import
- Point users to `src.providers.claude_code` as the replacement

**Implementation:**
```python
import warnings
warnings.warn(
    "claude_integration module is deprecated. Use src.providers.claude_code instead.",
    DeprecationWarning,
    stacklevel=2
)
```

---

### 2. CORE-008: Input Length Limits
**Files:** `src/cli.py`, `src/validation.py` (new)

**Tasks:**
- Create new `src/validation.py` module with constants and validation functions
- Add `MAX_CONSTRAINT_LENGTH = 1000` constant
- Add `MAX_NOTE_LENGTH = 500` constant
- Validate constraints in `cmd_start()` before storing
- Validate notes in `cmd_complete()`, `cmd_approve_item()`, `cmd_finish()`
- Add tests for validation

**Implementation:**
```python
# src/validation.py
MAX_CONSTRAINT_LENGTH = 1000
MAX_NOTE_LENGTH = 500

def validate_constraint(constraint: str) -> str:
    if len(constraint) > MAX_CONSTRAINT_LENGTH:
        raise ValueError(f"Constraint exceeds {MAX_CONSTRAINT_LENGTH} characters")
    return constraint

def validate_note(note: str) -> str:
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ValueError(f"Note exceeds {MAX_NOTE_LENGTH} characters")
    return note
```

---

### 3. ARCH-001: Extract Retry Logic
**Files:** `src/utils.py` (new), `src/visual_verification.py`

**Tasks:**
- Create new `src/utils.py` module with reusable retry decorator
- Implement `@retry_with_backoff` decorator with configurable:
  - `max_retries` (default: 3)
  - `base_delay` (default: 1.0 seconds)
  - `max_delay` (default: 60 seconds)
  - `exceptions` (tuple of exception types to catch)
- Refactor `visual_verification.py` to use the new decorator
- Add tests for retry utility

**Implementation:**
```python
# src/utils.py
import time
import functools
from typing import Tuple, Type

def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """Decorator that retries a function with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        time.sleep(delay)
            raise last_error
        return wrapper
    return decorator
```

---

### 4. WF-004: Auto-Archive Workflow Documents
**File:** `src/engine.py`

**Tasks:**
- Add `archive_existing_docs()` method to `WorkflowEngine`
- Call it in `start_workflow()` before creating new state
- Archive files: `docs/plan.md`, `docs/risk_analysis.md`, `tests/test_cases.md`
- Create archive directory: `docs/archive/`
- Naming format: `{date}_{task_slug}_{type}.md`
- Add `--no-archive` flag to start command
- Log archived files

**Implementation:**
```python
def archive_existing_docs(self, task_slug: str) -> list[str]:
    """Archive existing workflow docs before starting new workflow."""
    docs_to_archive = [
        ("docs/plan.md", "plan"),
        ("docs/risk_analysis.md", "risk"),
        ("tests/test_cases.md", "test_cases"),
    ]
    archive_dir = self.working_dir / "docs" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived = []
    date_str = datetime.now().strftime("%Y-%m-%d")

    for doc_path, suffix in docs_to_archive:
        src = self.working_dir / doc_path
        if src.exists():
            dst = archive_dir / f"{date_str}_{task_slug}_{suffix}.md"
            # Handle duplicate names by adding counter
            counter = 1
            while dst.exists():
                dst = archive_dir / f"{date_str}_{task_slug}_{suffix}_{counter}.md"
                counter += 1
            src.rename(dst)
            archived.append(str(dst))

    return archived
```

---

## Implementation Order

1. **ARCH-001** (Extract Retry Logic) - Creates utility used by other code
2. **CORE-007** (Deprecation Warning) - Simple, standalone change
3. **CORE-008** (Input Validation) - Creates validation module
4. **WF-004** (Auto-Archive) - Modifies workflow engine

## Files to Create
- `src/utils.py` - Reusable utilities (retry decorator)
- `src/validation.py` - Input validation functions

## Files to Modify
- `src/claude_integration.py` - Add deprecation warning
- `src/cli.py` - Add validation calls, --no-archive flag
- `src/engine.py` - Add archive_existing_docs method
- `src/visual_verification.py` - Refactor to use retry utility

## Tests to Add
- `tests/test_utils.py` - Test retry decorator
- `tests/test_validation.py` - Test input validation
- Update `tests/test_v2_2_features.py` - Test auto-archive
