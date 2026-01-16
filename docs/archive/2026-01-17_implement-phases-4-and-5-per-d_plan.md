# Phase 3: Validation Logic & Fix Application

## Overview
Implement Phase 3 of the self-healing infrastructure per `docs/self-healing-implementation-plan.md`.

## Components Implemented

### Phase 3a: Validation Logic
Components that validate fixes without applying them (testable in isolation):

1. **SafetyCategorizer** (`src/healing/safety.py`)
   - Categorizes fixes as SAFE, MODERATE, or RISKY
   - Analyzes diffs for protected paths, function signatures, security patterns
   - Detects formatting-only, import-only, comment-only changes

2. **CostTracker** (`src/healing/costs.py`)
   - Tracks daily API costs across embeddings, judge calls, lookups
   - Enforces daily limits and per-validation limits
   - Estimates validation costs based on safety category

3. **CascadeDetector** (`src/healing/cascade.py`)
   - Detects "hot" files (modified 3+ times/hour)
   - Prevents ping-pong fix cascades
   - Tracks recent fixes for causality analysis

4. **MultiModelJudge** (`src/healing/judges.py`)
   - Coordinates multiple AI models for fix validation
   - SAFE: 1 judge, MODERATE: 2 judges, RISKY: 3 judges
   - Supports Claude, Gemini, GPT-5.2, Grok

5. **ValidationPipeline** (`src/healing/validation.py`)
   - 3-phase validation: PRE_FLIGHT → VERIFICATION → APPROVAL
   - Pre-flight: Kill switch, constraints, precedent, cascade, cost
   - Verification: Parallel build/test/lint
   - Approval: Multi-model judging (tiered by safety)

### Phase 3b: Fix Application
Components that apply validated fixes:

6. **ContextRetriever** (`src/healing/context.py`)
   - Gathers file context for fix generation
   - Finds related files (tests, imports)
   - Formats context for LLM prompts

7. **FixApplicator** (`src/healing/applicator.py`)
   - Applies fixes using environment-appropriate adapters
   - LOCAL: Git CLI, can merge directly for SAFE fixes
   - CLOUD: GitHub API, always creates PRs
   - Handles verification, rollback, and audit logging

## Execution Mode
Sequential execution was used because:
- Components have dependencies (ValidationPipeline uses Safety, Costs, Cascade, Judges)
- Tests need to run after all components are implemented
- No independent parallel tasks identified

## Test Coverage
- 99 new tests for Phase 3 components
- All 339 healing tests pass
- Tests cover async operations, edge cases, error handling
