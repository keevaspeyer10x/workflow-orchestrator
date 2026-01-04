# Manus Project Instructions Template

Copy this into your Manus Project's Master Instruction to enforce the workflow.

---

## MANDATORY WORKFLOW ENFORCEMENT

**CRITICAL: Before ANY code changes or task execution, you MUST follow this process.**

### Step 1: Check Workflow Status (ALWAYS)

Before doing ANYTHING, run:
```bash
cd /path/to/your/project
./orchestrator status
```

Read the output carefully. It will tell you:
- What phase you're in
- What items are pending
- What blockers exist

### Step 2: Act on the Current Item

Only work on the item that is currently pending. Do not skip ahead.

### Step 3: Mark Items Complete

After completing work on an item:
```bash
./orchestrator complete <item_id> --notes "What you did"
```

### Step 4: Check Status Again

After every action:
```bash
./orchestrator status
```

### Step 5: Advance When Ready

When all items in a phase are complete:
```bash
./orchestrator advance
```

### Step 6: Wait for Approval When Needed

If the status shows "Requires human approval", inform me and wait.

---

## RULES

1. **NEVER skip the status check** - even if you think you know what's next
2. **NEVER proceed without checking** - always verify the current state
3. **ALWAYS provide notes** - document what you did
4. **ALWAYS provide reasons** - when skipping items, explain why
5. **NEVER force-advance** - unless I explicitly tell you to

---

## Quick Reference

| Action | Command |
|--------|---------|
| Check status | `./orchestrator status` |
| Complete item | `./orchestrator complete <id> --notes "..."` |
| Skip item | `./orchestrator skip <id> --reason "..."` |
| Advance phase | `./orchestrator advance` |
| Approve gate | `./orchestrator approve` |
| Finish workflow | `./orchestrator finish` |

---

## If Something Goes Wrong

If you encounter an error or get stuck:
1. Run `./orchestrator status` to see the current state
2. Tell me what the error is
3. Wait for my guidance

---

*This instruction template is part of the AI Workflow Orchestrator system.*
