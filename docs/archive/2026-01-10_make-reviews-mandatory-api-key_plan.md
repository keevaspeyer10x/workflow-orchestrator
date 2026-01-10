# Implementation Plan: Orchestrator Improvements

**Date:** 2026-01-10
**Workflow:** wf_69263b67
**Source:** MultiMinds project feedback

## Overview

Implementing six improvements to make the orchestrator more language-agnostic and user-friendly, based on real-world usage feedback from the MultiMinds Python project.

## Changes

### 1. Project Type Auto-Detection (P0)

**Problem:** Default workflow uses `npm run build` as test command, which fails for Python projects.

**Solution:**
- Extract `BUILD_SYSTEMS` detection from `build_tester.py` into a shared utility
- Auto-detect project type at `orchestrator start` when using bundled workflow
- Override `test_command` and `build_command` based on detected type

**Files to modify:**
- `src/config.py` - Add `detect_project_type()` and `get_project_commands()`
- `src/cli.py` - Call detection in `cmd_start()` when using bundled workflow
- `src/conflict/build_tester.py` - Import shared detection (avoid duplication)

**Detection priority (existing):**
1. `package.json` → npm test
2. `Cargo.toml` → cargo test
3. `go.mod` → go test ./...
4. `pyproject.toml` → pytest
5. `setup.py` → pytest
6. `requirements.txt` → pytest
7. `Makefile` → make test
8. `CMakeLists.txt` → ctest

### 2. Increase Note Limit (P1)

**Problem:** 500 character limit too restrictive for documenting clarifying questions.

**Solution:** Increase `MAX_NOTE_LENGTH` from 500 to 2000 characters.

**Files to modify:**
- `src/validation.py` - Change constant

### 3. Add --test-command Flag (P1)

**Problem:** No easy CLI override for test command without creating workflow.yaml.

**Solution:** Add `--test-command` and `--build-command` flags to `orchestrator start`.

**Files to modify:**
- `src/cli.py` - Add arguments to start_parser, apply in cmd_start()

**Usage:**
```bash
orchestrator start "Task" --test-command "pytest -v" --build-command "pip install -e ."
```

### 4. Support .orchestrator.yaml Overrides (P2)

**Problem:** Creating full workflow.yaml is heavyweight just to change test command.

**Solution:** Support minimal `.orchestrator.yaml` file that only overrides settings.

**Files to modify:**
- `src/config.py` - Add `load_settings_overrides()` function
- `src/engine.py` - Merge overrides into workflow settings on load

**Format:**
```yaml
# .orchestrator.yaml - minimal project-specific overrides
test_command: "pytest -v"
build_command: "pip install -e ."
docs_dir: "docs"
```

### 5. Add --force-skip for Gates (P2)

**Problem:** Gate steps can't be skipped even when verification command is wrong.

**Solution:** Add `--force` flag to skip command for gates with strong warning.

**Files to modify:**
- `src/cli.py` - Add --force flag to skip_parser
- `src/engine.py` - Handle force_skip in skip_item()

**Usage:**
```bash
orchestrator skip all_tests_pass --force --reason "Wrong test command for Python project"
```

**Output:**
```
⚠️  WARNING: Force-skipping a gate bypasses verification!
This should only be used when the verification command is incorrect.
Recording forced skip with reason...
```

### 6. Add First-Run Mismatch Warning (P2)

**Problem:** User doesn't realize bundled workflow has wrong commands until gate fails.

**Solution:** Show warning at `orchestrator start` when detected project type doesn't match default commands.

**Files to modify:**
- `src/cli.py` - Add check in cmd_start() with user prompt

**Example output:**
```
⚠️  Project type mismatch detected!
    Detected: Python project (pyproject.toml)
    Default test command: npm run build
    Recommended: pytest

    Auto-correcting test_command to 'pytest'
    (Use --test-command to override, or create .orchestrator.yaml)
```

## Test Plan

1. **test_project_detection.py** - Test detection for each project type
2. **test_validation.py** - Test increased note limit
3. **test_cli_flags.py** - Test --test-command and --build-command flags
4. **test_settings_override.py** - Test .orchestrator.yaml loading
5. **test_force_skip.py** - Test --force flag for gate skipping
6. **test_mismatch_warning.py** - Test first-run warning output

## Implementation Order

1. Extract shared detection utility (foundation for other changes)
2. Increase note limit (quick win)
3. Add --test-command flag (builds on detection)
4. Add first-run mismatch warning (uses detection)
5. Support .orchestrator.yaml (independent)
6. Add --force-skip (independent)

## Backwards Compatibility

- All changes are additive
- Default behavior unchanged if no flags/overrides provided
- Existing workflow.yaml files continue to work
- Auto-detection only activates when using bundled workflow
