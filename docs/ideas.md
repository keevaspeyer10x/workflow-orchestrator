# Ideas Backlog

Reference: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

## Moved to Roadmap

## To Discuss (Design Phase)

- [ ] **Add a design phase** - Design at the start, Document at the end
  - Could be a formal DESIGN phase between PLAN and EXECUTE
  - Would include: API design, data model, component structure
  - Question: Is this overkill for smaller tasks? Make it optional?
  - Sub taskPRD with screenshots for human review** - Thallow-style visual PRDs
    - Would help with UI/UX features
    - Could integrate with visual verification service
    - Question: Best practice for AI-generated PRDs?

- [ ] **Chunk work for complex tasks** - linked to context limits
  - Partially covered by PRD-003 (automatic parallelization)
  - May need explicit "break this into chunks" workflow step
  - Consider: context-aware chunking based on token limits

- [ ]  **Integrate Mastra**

- [ ]  **Port to Codex** - may be better with long context

## Still To Consider

- [ ] Notificaions of erros and their implications
  - If it is relevant for output, the user should be notified at the end if the workflow has been compromised to an extent by the issue or error including noting the implication (eg. fewer model reviews or a step not fully run). 

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
- [ ] **Tidy up the repo** - archive unnecessary files, clean up old experiments
