# Phase 2: Conflict Detection - Implementation Plan

## Overview

Phase 2 enhances the basic conflict detection from Phase 1 with a full detection pipeline that catches "clean but broken" merges and classifies conflicts accurately.

**Goal:** Accurate conflict classification
**Deliverable:** System that accurately identifies and classifies conflicts

## Current State (Phase 1 Complete)

- `src/conflict/detector.py` - Basic `git merge-tree` detection
- Returns `ConflictInfo` with `ConflictType`, `ConflictSeverity`, file list

## Phase 2 Components

### 1. Full Detection Pipeline (`src/conflict/pipeline.py`)

Orchestrates the 6-step detection process:

```
Step 1: Textual conflict check (git merge-tree) - EXISTING
Step 2: Create temporary merge - NEW
Step 3: Build test (compile/typecheck) - NEW
Step 4: Smoke test (targeted tests) - NEW
Step 5: Dependency check - NEW
Step 6: Semantic analysis - NEW
```

**Implementation:**
- Create `DetectionPipeline` class that runs steps sequentially
- Each step can short-circuit if it finds critical conflicts
- Return enhanced `ConflictClassification` with all results

### 2. Build/Test Runner (`src/conflict/build_tester.py`)

Runs build and tests on merged code:

- Create temp branch with merged result
- Run project's build command (from config or auto-detect)
- Run targeted tests for modified files
- Clean up temp branch

**Configuration:**
- Auto-detect build system (npm, pip, cargo, etc.)
- Support custom build commands in `.claude/config.yaml`

### 3. Dependency Analyzer (`src/conflict/dependency.py`)

Detects dependency conflicts:

- Parse `package.json`, `requirements.txt`, `Cargo.toml`, etc.
- Detect version conflicts between branches
- Detect incompatible package combinations
- Return `DependencyConflict` list

### 4. Semantic Analyzer (`src/conflict/semantic.py`)

Detects semantic conflicts:

- Module dependency graph overlap (imports)
- Symbol/function overlap (same names, different implementations)
- Domain overlap (auth, db, api based on file paths)
- API surface changes (public function signatures)

### 5. Conflict Clusterer (`src/conflict/clusterer.py`)

Groups related conflicts for efficient resolution:

- Build file overlap graph
- Build domain overlap graph
- Find connected components = clusters
- Order clusters by dependencies

### 6. Risk Flag Detection (enhance `detector.py`)

Detect high-risk areas:
- Security-related files (auth, crypto, secrets)
- Database migrations
- Public API changes
- Configuration changes

## File Structure

```
src/conflict/
├── __init__.py         # Update exports
├── detector.py         # Existing - enhance with risk flags
├── pipeline.py         # NEW - orchestrates detection steps
├── build_tester.py     # NEW - build/test on merged code
├── dependency.py       # NEW - dependency conflict detection
├── semantic.py         # NEW - semantic conflict detection
└── clusterer.py        # NEW - conflict clustering
```

## Implementation Order

1. **Risk flag detection** - Enhance existing detector.py
2. **Detection pipeline** - Orchestration framework
3. **Build tester** - Critical for catching "clean but broken"
4. **Dependency analyzer** - Common conflict source
5. **Semantic analyzer** - Advanced detection
6. **Conflict clusterer** - Scalability for many agents

## Testing Strategy

- Unit tests for each component
- Integration test with mock git repo
- Test "clean but broken" scenarios specifically

## Configuration

Add to `.claude/config.yaml`:

```yaml
conflict_detection:
  build_command: "npm run build"  # or auto-detect
  test_command: "npm test"
  timeout_seconds: 300
  semantic_analysis: true
  dependency_check: true
```

## Success Criteria

- [ ] Detect textual conflicts (existing)
- [ ] Detect build failures in merged code
- [ ] Detect test failures in merged code
- [ ] Detect dependency version conflicts
- [ ] Classify conflict severity accurately
- [ ] Identify risk flags (security, auth, db)
- [ ] Cluster conflicts by domain/files
