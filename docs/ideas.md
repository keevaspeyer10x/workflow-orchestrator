# Ideas Backlog

Reference: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

## Moved to Roadmap

- [x] **Add a final stage - document** - update PRD, spec document, README files, set-up instructions etc. → **WF-009: Document Phase**
- [x] **Should we have an AI critique the plan - or every step?** → **WF-008: AI Critique at Phase Gates**
- [x] **Need a link to the relevant files in the comments after each section before approve** → **WF-006: File Links in Status Output**
- [x] **Provide a summary on screen before asking for approval** + summary of learnings and AI feedback → **WF-005: Summary Before Approval Gates**
- [x] **Are we checking if Learnings implies new things for the ROADMAP?** → **WF-007: Learnings to Roadmap Pipeline**
- [x] **Proactively add CI/CD tests on PR or merge** - Code reviews, CI/CD practices → Added to ROADMAP.md (2026-01-07)
- [x] **North Star / context documents for AI alignment** → **CONTEXT-001: Context Documents System**
- [x] **Multiple agents for parallel execution** → **PRD-001, PRD-003, CORE-015**
- [x] **Merge including rerunning all tests** → **CORE-023: Simple orchestrator resolve**
- [x] **Learnings need to have recommendations which are then implemented** → **WF-007 + LEARN-001**

## To Discuss (Design Phase)

- [ ] **Add a design phase** - Design at the start, Document at the end
  - Could be a formal DESIGN phase between PLAN and EXECUTE
  - Would include: API design, data model, component structure
  - Question: Is this overkill for smaller tasks? Make it optional?

- [ ] **Chunk work for complex tasks** - linked to context limits
  - Partially covered by PRD-003 (automatic parallelization)
  - May need explicit "break this into chunks" workflow step
  - Consider: context-aware chunking based on token limits

## Still To Consider

- [ ] **PRD with screenshots for human review** - Thallow-style visual PRDs
  - Would help with UI/UX features
  - Could integrate with visual verification service
  - Question: Best practice for AI-generated PRDs?

- [ ] **VS Code extension** → See DEF-008 in roadmap (deferred)

- [ ] **Formal test phase** - separate from VERIFY?
  - Currently tests are in EXECUTE (write) and VERIFY (run)
  - Could have dedicated TEST phase with:
    - Unit tests
    - Integration tests
    - E2E tests
    - Performance tests
  - Question: Is current EXECUTE+VERIFY sufficient?

## Quick Fixes (Don't Forget)

- [ ] **Installation instructions** - recommend running with `--dangerously-skip-permissions` for trusted repos
- [x] **Suggest committing at end** - if changes uncommitted when workflow finishes, prompt user → **Added to WF-023**
- [ ] **Tidy up the repo** - archive unnecessary files, clean up old experiments
