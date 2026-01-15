# Plan: Archive ROADMAP/PRD Files and Changelog Tracking

**Workflow ID:** wf_344f016c
**Issues:** #57, #59
**Date:** 2026-01-15

## Objective

1. **#57**: Move ROADMAP.md and PRD planning files to `docs/archive/planning/`
2. **#59**: Establish process for tracking closed issues in CHANGELOG.md

## Execution Mode

**Sequential** - Tasks are simple file moves and documentation updates. No benefit from parallel agents for ~10 file moves and 1 documentation update.

## Task 1: Archive Planning Files (#57)

### Files to Archive

**From root directory:**
- `ROADMAP.md` (4339 lines)
- `PRD_v2.2_ENHANCEMENTS.md`
- `prd_summary.md`
- `process-compliance.prd.yaml`

**From docs/prd/:**
- `PRD-007-agent-workflow-enforcement.md`
- `PRD-007-implementation-guide.md`
- `prd-parallel-core-work.yaml`

### Steps

1. Create `docs/archive/planning/` directory
2. Move files from root to `docs/archive/planning/`
3. Move `docs/prd/` contents to `docs/archive/planning/`
4. Remove empty `docs/prd/` directory
5. Update CLAUDE.md references (if any point to moved files)
6. Add note that GitHub Issues are source of truth

### Not Archived (Intentional)

- `examples/sample_prd.yaml` - Example file for users
- `examples/phase7_prd.yaml` - Example file for users
- Files in `docs/archive/` - Already archived

## Task 2: Changelog Tracking Process (#59)

### Recommendation: Option A (Manual) with Documentation

For a project of this size, manual changelog updates are sufficient. The key is documenting the process.

### Steps

1. Add "Changelog Update Process" section to CLAUDE.md
2. Document that closed issues should be recorded in CHANGELOG.md under appropriate version
3. Close #59 with documentation reference

## Verification

- [ ] `docs/archive/planning/` contains all moved files
- [ ] `docs/prd/` directory removed
- [ ] No broken references in CLAUDE.md
- [ ] CHANGELOG process documented
- [ ] Both issues closed with appropriate comments
