# AI Agent Usage Guide

This guide explains how an AI agent (like Manus or Claude) should use the Workflow Orchestrator to enforce multi-phase workflows.

---

## Core Principle: Recitation

The most important concept is **recitation**. Before taking any action on a task, the AI agent MUST:

1. Run `orchestrator status` to get the current state
2. Read the output carefully
3. Identify the current phase and pending items
4. Act on the appropriate item

This prevents context drift and ensures the agent never "forgets" where it is in the workflow.

---

## Standard Workflow for AI Agents

### At the Start of a Task

```bash
# 1. Start the workflow
orchestrator start "Your task description" --project "ProjectName"

# 2. Check status (ALWAYS do this)
orchestrator status
```

### Before Every Action

```bash
# ALWAYS check status first
orchestrator status

# Then act on the appropriate item
```

### After Completing Work

```bash
# Mark the item as complete
orchestrator complete <item_id> --notes "What you did"

# Check status again to see what's next
orchestrator status
```

### When Skipping an Item

```bash
# Skip with a documented reason (min 10 characters)
orchestrator skip <item_id> --reason "Detailed reason for skipping"
```

### When Ready to Move to Next Phase

```bash
# First check if you can advance
orchestrator status

# If ready, advance
orchestrator advance
```

### When Human Approval is Needed

```bash
# The status will show a blocker like "Requires human approval"
# Inform the user and wait for them to run:
orchestrator approve
```

### At the End of a Task

```bash
# Finish the workflow
orchestrator finish

# This will automatically generate a learning report
```

---

## Example Session

Here's a complete example of an AI agent working through the PLAN phase:

```
AI: Let me check the current workflow status.

$ orchestrator status
============================================================
WORKFLOW STATE (READ THIS FIRST)
============================================================
Task: Add user authentication feature
Phase: PLAN - Planning & Scoping
Progress: 0/4 items
Checklist:
  ○ [*] Generate initial plan
  ○ [*] Risk & Impact Analysis
  ○ [*] Define Test Cases
  ○ [*] Get User Approval
============================================================

AI: I'm in the PLAN phase. The first item is "Generate initial plan". 
    Let me create the plan document.

[AI creates docs/plan.md]

AI: Now I'll mark this item as complete.

$ orchestrator complete initial_plan --notes "Created comprehensive plan in docs/plan.md"
✓ Item completed successfully

AI: Let me check status again.

$ orchestrator status
============================================================
WORKFLOW STATE (READ THIS FIRST)
============================================================
Task: Add user authentication feature
Phase: PLAN - Planning & Scoping
Progress: 1/4 items
Checklist:
  ✓ [*] Generate initial plan
  ○ [*] Risk & Impact Analysis
  ...
============================================================

AI: Good. Next is "Risk & Impact Analysis". This is a simple feature,
    so I'll skip it with a reason.

$ orchestrator skip risk_analysis --reason "Simple feature with minimal risk, no external dependencies"
✓ Item risk_analysis skipped

AI: Now I need to define test cases...
```

---

## Key Rules for AI Agents

1. **ALWAYS run `orchestrator status` before taking any action**
2. **NEVER skip the status check** - even if you think you know what's next
3. **ALWAYS provide notes** when completing items
4. **ALWAYS provide a reason** when skipping items (min 10 characters)
5. **NEVER force-advance** unless explicitly instructed by the user
6. **WAIT for human approval** when a manual gate is required

---

## Manus Project Instructions

To ensure Manus follows this workflow, add the following to your Manus Project Master Instruction:

```
## MANDATORY WORKFLOW ENFORCEMENT

Before ANY coding task:
1. Run `orchestrator status` to check current state
2. Read the output carefully
3. Act ONLY on the current pending item
4. After completing work, run `orchestrator complete <item_id>`
5. Run `orchestrator status` again before the next action

NEVER skip the status check. NEVER proceed without checking.
```

---

## Troubleshooting

### "No active workflow"
Run `orchestrator start "task description"` to begin.

### "Cannot advance to next phase"
Check the blockers in the status output. Complete or skip all required items.

### "Verification failed"
The system checked your work and found it incomplete. Review the error message and fix the issue.

### "Requires human approval"
Wait for the user to run `orchestrator approve`.

---

## Dashboard Access

For visual monitoring, the user can run:

```bash
orchestrator dashboard
```

This opens a web-based dashboard showing real-time workflow status.

---

*This guide is part of the AI Workflow Orchestrator system.*
