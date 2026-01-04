# AI Agent Usage Guide

This guide explains how an AI agent (like Manus or Claude) should use the Workflow Orchestrator to enforce multi-phase workflows.

---

## Core Principles

### 1. Recitation
Before taking any action on a task, the AI agent MUST:

1. Run `orchestrator status` to get the current state
2. Read the output carefully
3. Identify the current phase and pending items
4. Act on the appropriate item

This prevents context drift and ensures the agent never "forgets" where it is in the workflow.

### 2. Clarification First
Before creating a plan, ASK CLARIFYING QUESTIONS to fully understand the request:
- What does the issue look like?
- Is this a regression or new behavior?
- What's the expected behavior?
- Which areas/components are affected?

### 3. Questions Must Include Recommendations
When asking any question, ALWAYS provide:
- Your recommendation and reasoning
- An alternative option when applicable
- Example: "Should we use approach A or B? **I recommend A** because [reason]. Alternative: B would work better if [condition]."

### 4. Default to Claude Code
Use Claude Code for implementation unless the task is trivial:
- Only skip for: single-line config changes, documentation-only updates, or explicit user request
- Document your reasoning if not using Claude Code

### 5. Root Cause Analysis is Mandatory
Always document WHY an issue occurred, not just how it was fixed:
- What was the underlying cause?
- What systemic issues enabled this?
- What broader implications exist?

### 6. Approve Learnings Before Commit
Wait for explicit user approval of LEARNINGS.md before committing. Never embed learnings without verification.

### 7. Visual Tests for UI Changes
For any UI/styling changes, include screenshot or visual regression tests where appropriate.

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
Progress: 0/5 items
Checklist:
  ○ [*] Ask Clarifying Questions
  ○ [*] Generate initial plan
  ○ [*] Risk & Impact Analysis
  ○ [*] Define Test Cases
  ○ [*] Get User Approval
============================================================

AI: I'm in the PLAN phase. The first item is "Ask Clarifying Questions".
    Before I create a plan, I need to understand the request better.

AI: I have a few questions about this feature:
    1. Should this support OAuth providers (Google, GitHub) or just email/password?
       **I recommend** starting with email/password for simplicity, then adding OAuth later.
    2. Do we need email verification?
       **I recommend** yes, for security. Alternative: skip if this is internal-only.

[User answers questions]

AI: Now I'll mark this item as complete.

$ orchestrator complete clarifying_questions --notes "Confirmed: email/password only, with email verification"
✓ Item completed successfully

AI: Let me check status again.

$ orchestrator status
...
Progress: 1/5 items
Checklist:
  ✓ [*] Ask Clarifying Questions
  ○ [*] Generate initial plan
  ...

AI: Good. Next is "Generate initial plan". Let me create the plan document.
    This is a non-trivial feature, so I'll use Claude Code for implementation.

[AI creates docs/plan.md including "Will use Claude Code for implementation"]

$ orchestrator complete initial_plan --notes "Created comprehensive plan in docs/plan.md"
```

---

## Key Rules for AI Agents

1. **ALWAYS run `orchestrator status` before taking any action**
2. **NEVER skip the status check** - even if you think you know what's next
3. **ASK CLARIFYING QUESTIONS** before creating a plan
4. **ALWAYS PROVIDE RECOMMENDATIONS** when asking questions
5. **DEFAULT TO CLAUDE CODE** for implementation
6. **ALWAYS provide notes** when completing items
7. **ALWAYS provide a reason** when skipping items (min 10 characters)
8. **NEVER force-advance** unless explicitly instructed by the user
9. **WAIT for human approval** when a manual gate is required
10. **ROOT CAUSE ANALYSIS** is mandatory in the LEARN phase
11. **WAIT FOR LEARNINGS APPROVAL** before committing

---

## Manus Project Instructions Template

To ensure Manus follows this workflow, add the following to your Manus Project Master Instruction:

```markdown
MANDATORY: Before ANY code changes, you MUST follow the workflow.

### Workflow Enforcement

1. **Check Status First:** Run `./orchestrator status` before ANY action
2. **Start Workflow:** If none exists, run `./orchestrator start "task description"`
3. **Follow Current Phase:** Work only on items in the current phase (PLAN → EXECUTE → REVIEW → VERIFY → LEARN)
4. **Mark Progress:** Run `./orchestrator complete <item_id> --notes "what you did"` after completing items
5. **Wait for Approval:** At manual gates, inform user and wait for explicit approval
6. **Advance:** Run `./orchestrator advance` when all phase items are complete

### Key Behaviors (Non-Negotiable)

1. **ASK CLARIFYING QUESTIONS FIRST** - Before planning, ask questions to fully understand the request
2. **QUESTIONS MUST INCLUDE RECOMMENDATIONS** - Always provide your recommendation and an alternative
3. **DEFAULT TO CLAUDE CODE** - Use Claude Code for implementation unless trivial
4. **ROOT CAUSE ANALYSIS IS MANDATORY** - Document WHY issues occurred, not just how they were fixed
5. **APPROVE LEARNINGS BEFORE COMMIT** - Wait for explicit user approval of LEARNINGS.md
6. **VISUAL TESTS FOR UI CHANGES** - Include screenshot/visual regression tests where appropriate

### Rules

1. ALWAYS check status before and after every action
2. NEVER proceed without user approval at manual gates
3. NEVER skip phases or force-advance without explicit permission
4. ALWAYS document what you did with notes/reasons
5. If stuck, run `./orchestrator status` and report the error

This process is non-negotiable.
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
