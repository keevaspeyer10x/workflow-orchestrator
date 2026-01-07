# Ideas Backlog

Reference: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

## Transcript from chat with Jack

### Moved to Roadmap

- [x] **Add a final stage - document** - update PRD, spec document, README files, set-up instructions etc. → **WF-009: Document Phase**

- [x] **Should we have an AI critique the plan - or every step?** → **WF-008: AI Critique at Phase Gates**

- [x] **Need a link to the relevant files in the comments after each section before approve** → **WF-006: File Links in Status Output**

- [x] **Provide a summary on screen before asking for approval** + summary of learnings and AI feedback → **WF-005: Summary Before Approval Gates**

- [x] **Are we checking if Learnings implies new things for the ROADMAP?** → **WF-007: Learnings to Roadmap Pipeline**

- [x] **Proactively add CI/CD tests on PR or merge** - Code reviews, CI/CD practices → Added to ROADMAP.md (2026-01-07)

### To Discuss (Design Phase)

- [ ] **Add a design phase** - Design at the start, Document at the end
- [ ] Might need to chunk the work at some stages - if complex enough

### Still To Consider

- [ ] merge - including merging to a branch and rerunning all tests
- [ ] do we create a PRD in a similar format to Thallow with screenshots for human review. what is best practice
- [ ] ultimately tool will need a front end for settings, document review and UI/UX review. Can I plug it in to VS Code or something? → See DEF-008
- [ ] currently one shots everything. may makes sense to chunky it linked to context
- [ ] do we need to maintain a north star and perhaps updated PRD for context?
- [ ] learnings need to have recommendations which are then implemented
- [ ] Do we need items like a North Star or the Manus Custom Instructions
- [ ] Do we make a formal test phase?
- [ ] Start spinning up multiple agents - to massively accelerate what we'll do → See CORE-015, DEF-010

### Quick Fixes (Don't Forget)

- [ ] In installation instructions recommend running with no checking
- [ ] At the end suggest committing changes if they haven't been
- [ ] Tidy up the repo - archive unnecessary files
Design at the start, 

Do we make a formal test phase?


Start spinning up multiple agents - to massively accelerate what we'll do. 

Provde a summary on screen before asking for approval

I'd also always like to see a summary of the learnings and the feedback from the other AI models - at least how many issues they identified.

Are we checking if Loearnings implies new things for the ROADMAP?

Don't forget
- In my installation instructions recommend running with no checking

- At the end suggest committing changes if they haven't been

- Tidy up the repo - archive unnecessary file

Proactively add CI/CD tests on PR or merge - Code reviews, other things to think about? Should we putting CI/CD practices into place as part of this whole process. Should we be reviewing the workflow from a Expert CI/CD perspective?


# Done

Document at the end.

Should we have an AI critique the plan - or every step?

Need a link to the relevant files in the comments after each section before approve. Review Things.
