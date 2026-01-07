# Implementation Plan: Roadmap Items CORE-012, VV-001-004, VV-006, WF-003

## Overview

Implement 8 roadmap items plus changelog automation:
- **CORE-012**: OpenRouter Streaming Support
- **VV-001**: Auto-load Style Guide in Visual Verification
- **VV-002**: Workflow Step Integration for Visual Tests
- **VV-003**: Visual Test Discovery
- **VV-004**: Baseline Screenshot Management
- **VV-006**: Cost Tracking for Visual Tests
- **WF-003**: Model Selection Guidance
- **NEW**: Changelog/Roadmap automation in LEARN phase

## Implementation Details

### 1. CORE-012: OpenRouter Streaming Support

**Files to modify:**
- `src/providers/openrouter.py`

**Changes:**
1. Add `execute_streaming()` method that yields chunks
2. Add `--stream` flag to handoff command in `src/cli.py`
3. Handle stream interruption gracefully
4. Add progress indicator for non-streaming mode

**Implementation:**
```python
def execute_streaming(self, prompt: str, model: Optional[str] = None) -> Generator[str, None, ExecutionResult]:
    """Stream response chunks for real-time display."""
    response = requests.post(
        self.API_URL,
        headers=headers,
        json={**payload, "stream": True},
        stream=True
    )
    for line in response.iter_lines():
        if line.startswith(b'data: '):
            chunk = json.loads(line[6:])
            if chunk != '[DONE]':
                yield chunk['choices'][0]['delta'].get('content', '')
```

### 2. VV-001: Auto-load Style Guide

**Files to modify:**
- `src/visual_verification.py`

**Changes:**
1. Add `style_guide_path` parameter to `__init__`
2. Auto-load style guide content if path provided and file exists
3. Automatically include in all `verify()` calls
4. Add `include_style_guide: bool = True` parameter to override

### 3. VV-002: Workflow Step Integration

**Files to modify:**
- `src/visual_verification.py`
- `src/cli.py`

**Changes:**
1. Add `run_all_visual_tests()` function
2. Parse test files from `tests/visual/` directory
3. Integrate with orchestrator's `visual_regression_test` item
4. Add `app_url` setting to workflow.yaml

### 4. VV-003: Visual Test Discovery

**Files to modify:**
- `src/visual_verification.py`
- `src/cli.py`

**Changes:**
1. Add `visual-verify-all` CLI command
2. Define test file format (YAML frontmatter + markdown body)
3. Scan `tests/visual/*.md` for test files
4. Support filtering by tag/feature

**Test file format:**
```markdown
---
url: /dashboard
viewport: desktop
tags: [core, dashboard]
---
# Dashboard Visual Test

The dashboard should display:
- User greeting in top-left
- Navigation sidebar
- Main content area with widgets
```

### 5. VV-004: Baseline Screenshot Management

**Files to modify:**
- `src/visual_verification.py`

**Changes:**
1. Add `save_baseline()` method to save screenshots
2. Add `compare_with_baseline()` method for comparison
3. Store baselines in `tests/visual/baselines/`
4. Add `--save-baseline` flag to CLI
5. Add image diff for pixel comparison (optional, AI comparison primary)

### 6. VV-006: Cost Tracking

**Files to modify:**
- `src/visual_verification.py`

**Changes:**
1. Track token usage from API responses (if available)
2. Add `CostTracker` class to aggregate costs
3. Store per-test and per-run costs
4. Add `--show-cost` flag to CLI commands
5. Log costs to `.visual_verification_costs.json`

### 7. WF-003: Model Selection Guidance

**Files to modify:**
- `src/model_registry.py`
- `src/default_workflow.yaml`

**Changes:**
1. Add `get_latest_model(category: str)` method to ModelRegistry
2. Categories: `codex` (code-focused), `gemini` (long-context), `claude` (general)
3. Use model registry cache to determine latest available
4. Update workflow.yaml to use `review_model: "latest_available"`

### 8. Changelog/Roadmap Automation (NEW)

**Files to modify:**
- `src/default_workflow.yaml`
- `src/cli.py`
- `src/engine.py` (optional helper methods)

**Changes:**
1. Add `update_changelog_roadmap` item to LEARN phase
2. Add `roadmap_file` and `changelog_file` settings to workflow.yaml
3. Create helper to parse ROADMAP.md for completed items
4. Create helper to append to CHANGELOG.md
5. Create helper to remove completed items from ROADMAP.md

## Execution Strategy

**Use Claude Code for implementation** - This is a substantial set of features requiring:
- Multiple file modifications
- Test creation
- Integration with existing code

## Dependencies

- Existing `ModelRegistry` class (CORE-017/CORE-018)
- Existing `VisualVerificationClient` class
- External visual-verification-service (user's repo)

## Testing Strategy

1. Unit tests for each new function/method
2. Integration tests for CLI commands
3. Mock the visual verification service for VV tests
4. Test streaming with mock HTTP responses
