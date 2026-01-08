# Implementation Plan: Roadmap Items (Updated)

## Overview

Holistic implementation across two repos:
1. **visual-verification-service** - Add cost tracking
2. **workflow-orchestrator** - Client updates + all VV features

## Part 1: Visual-Verification-Service Changes

### 1.1 Add Cost Tracking to Evaluator

**File:** `src/services/evaluator.ts`

Capture usage from Anthropic API and return in response.

### 1.2 Update Types

**File:** `src/types/index.ts`

Add usage field to VerifyResponse:
```typescript
usage?: {
  inputTokens: number;
  outputTokens: number;
  estimatedCost: number;
};
```

## Part 2: Workflow-Orchestrator Changes

### 2.1 Update Visual Verification Client

**File:** `src/visual_verification.py`

- Add `device` parameter support (device presets)
- Add `auth` parameter support
- Add `/devices` endpoint method
- Add `usage` field handling
- Auto-load style guide (VV-001)
- Cost tracking (VV-006)

### 2.2 Visual Test Discovery (VV-003)

- Add `visual-verify-all` CLI command
- Test file format with YAML frontmatter
- Scan `tests/visual/*.md`

### 2.3 Workflow Step Integration (VV-002)

- Wire into `visual_regression_test` workflow item
- Add `app_url` setting

### 2.4 Baseline Management (VV-004)

- Client-side baseline storage in `tests/visual/baselines/`
- Save/compare methods
- `--save-baseline` CLI flag

### 2.5 OpenRouter Streaming (CORE-012)

**File:** `src/providers/openrouter.py`

- Add `execute_streaming()` method
- Add `--stream` flag to CLI

### 2.6 Model Selection (WF-003)

**File:** `src/model_registry.py`

- Add `get_latest_model(category)` method

### 2.7 Changelog Automation

**File:** `src/default_workflow.yaml`

- Add `update_changelog_roadmap` item to LEARN phase

## Execution Order

1. Visual-verification-service: cost tracking
2. Workflow-orchestrator: client sync with service API
3. VV-001 through VV-004, VV-006
4. CORE-012, WF-003
5. Changelog automation
