# Manus Project Instructions Template

Copy this into your Manus Project's Master Instruction to enforce the AI Orchestration Workflow.

---

## Template (Copy Below This Line)

```
MANDATORY: Before ANY code changes, you MUST follow the workflow.

### Workflow Enforcement

1. **Check Status First:** Run `./orchestrator status` before ANY action
2. **Start Workflow:** If none exists, run `./orchestrator start "task description"`
3. **Follow Current Phase:** Work only on items in the current phase (PLAN → EXECUTE → REVIEW → VERIFY → LEARN)
4. **Mark Progress:** Run `./orchestrator complete <item_id> --notes "what you did"` after completing items
5. **Wait for Approval:** At manual gates, inform user and wait for explicit approval
6. **Advance:** Run `./orchestrator advance` when all phase items are complete

Read `AI_ORCHESTRATION_WORKFLOW.md` for full process details.

### Project Context

Before starting any task, review:
- NORTH_STAR.md (core principles)
- ARCHITECTURE.md (technical architecture)  
- docs/UI_DESIGN_BRIEF.md (visual specifications)
- specs/* (feature specifications)

### Quick Reference

| Action | Command |
|--------|---------|
| Check status | `./orchestrator status` |
| Start workflow | `./orchestrator start "task"` |
| Complete item | `./orchestrator complete <id> --notes "..."` |
| Skip item | `./orchestrator skip <id> --reason "..."` |
| Approve item | `./orchestrator approve-item <id>` |
| Advance phase | `./orchestrator advance` |
| Delegate to Claude Code | `./orchestrator handoff --execute` |

### Rules

1. ALWAYS check status before and after every action
2. NEVER proceed without user approval at manual gates
3. NEVER skip phases or force-advance without explicit permission
4. ALWAYS document what you did with notes/reasons
5. If stuck, run `./orchestrator status` and report the error

This process is non-negotiable.
```

---

## Customization Notes

**Project-specific files:** Replace the "Project Context" section with your project's key documents. Common examples:
- `README.md` - Project overview
- `ARCHITECTURE.md` - Technical decisions
- `CONTRIBUTING.md` - Contribution guidelines
- `docs/` - Additional documentation

**Workflow file:** Ensure your project has a `workflow.yaml` in the root directory. Copy and customize from `examples/pingxa_workflow.yaml`.

**Orchestrator location:** The template assumes `./orchestrator` is in the project root. Adjust the path if you've installed it elsewhere.

---

## Minimal Version

If you prefer a shorter instruction set:

```
MANDATORY: Before ANY code changes:
1. Run `./orchestrator status` (always first)
2. Follow the current phase items
3. Run `./orchestrator complete <id> --notes "..."` after each item
4. Wait for approval at manual gates
5. Run `./orchestrator advance` when phase is complete

Read AI_ORCHESTRATION_WORKFLOW.md for details.
Review: NORTH_STAR.md, ARCHITECTURE.md, docs/UI_DESIGN_BRIEF.md, specs/*
```

---

*This template is part of the [AI Workflow Orchestrator](https://github.com/keevaspeyer10x/workflow-orchestrator).*
