# Test Cases: Archive ROADMAP/PRD Files and Changelog Tracking

**Workflow ID:** wf_344f016c
**Issues:** #57, #59
**Date:** 2026-01-15

## Task 1: Archive Planning Files (#57)

### TC-1.1: Archive Directory Created
- **Precondition:** `docs/archive/planning/` does not exist
- **Action:** Create directory
- **Expected:** Directory exists at `docs/archive/planning/`
- **Verification:** `ls -la docs/archive/planning/`

### TC-1.2: Root Files Moved
- **Precondition:** Files exist in root directory
- **Action:** Move ROADMAP.md, PRD_v2.2_ENHANCEMENTS.md, prd_summary.md, process-compliance.prd.yaml
- **Expected:** Files exist in `docs/archive/planning/`, not in root
- **Verification:**
  ```bash
  ls docs/archive/planning/ROADMAP.md
  ! ls ROADMAP.md 2>/dev/null
  ```

### TC-1.3: docs/prd Files Moved
- **Precondition:** Files exist in `docs/prd/`
- **Action:** Move all files from docs/prd/
- **Expected:** Files in `docs/archive/planning/`, `docs/prd/` removed
- **Verification:**
  ```bash
  ls docs/archive/planning/PRD-007-agent-workflow-enforcement.md
  ! ls docs/prd/ 2>/dev/null
  ```

### TC-1.4: Git History Preserved
- **Precondition:** Files moved with `git mv`
- **Action:** Check git log for moved file
- **Expected:** History shows original commits
- **Verification:** `git log --follow docs/archive/planning/ROADMAP.md | head -20`

### TC-1.5: No Broken References
- **Precondition:** Files moved
- **Action:** Search for references to moved files
- **Expected:** No references point to old locations (or references updated)
- **Verification:** `grep -r "ROADMAP.md" CLAUDE.md README.md`

## Task 2: Changelog Process (#59)

### TC-2.1: Process Documented
- **Precondition:** CLAUDE.md exists
- **Action:** Add changelog update process section
- **Expected:** CLAUDE.md contains "Changelog Update Process" or similar section
- **Verification:** `grep -i "changelog" CLAUDE.md`

### TC-2.2: Issue Closed with Documentation
- **Precondition:** #59 open
- **Action:** Close with comment referencing documentation
- **Expected:** Issue closed, comment links to CLAUDE.md section
- **Verification:** `gh issue view 59 --json state`

## Acceptance Criteria

- [ ] All TC-1.x tests pass
- [ ] All TC-2.x tests pass
- [ ] Both issues (#57, #59) closed
- [ ] No regressions in existing functionality
