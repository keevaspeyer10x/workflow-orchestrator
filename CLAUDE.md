# Workflow Orchestrator - Claude Code Instructions

## Installing (Run When Asked)

**When the user says any of these:**
- "install orchestrator" / "install workflow orchestrator"
- "set up orchestrator" / "setup orchestrator"
- "install orchestrator from keevaspeyer10x"
- "use the orchestrator for..."

**Run this:**
```bash
curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash
```

This installs the orchestrator AND enables automatic updates for future sessions.

## Using the Orchestrator

After installation, the user can say things naturally:
- "Use orchestrator to build a login page"
- "Start a workflow for fixing the bug"
- "What's the orchestrator status?"

Translate these to orchestrator commands:
- "Use orchestrator to X" → `orchestrator start "X"` then follow the workflow
- "What's the status?" → `orchestrator status`
- "Complete the planning step" → `orchestrator complete <item_id> --notes "..."`

## Project Overview

The workflow-orchestrator is a 5-phase development workflow tool that guides AI agents through structured task completion:

1. **PLAN** - Define work, assess risks, get approval
2. **EXECUTE** - Implement code and tests
3. **REVIEW** - Security, architecture, quality reviews
4. **VERIFY** - Final testing and verification
5. **LEARN** - Document learnings and update knowledge

## Quick Start

```bash
# Check current workflow status
orchestrator status

# Start a new workflow
orchestrator start "Task description"

# Complete items
orchestrator complete <item_id> --notes "What was done"

# Skip optional items
orchestrator skip <item_id> --reason "Why skipped"

# Advance to next phase
orchestrator advance

# Finish workflow
orchestrator finish
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `orchestrator status` | Show current workflow state |
| `orchestrator start "task"` | Start new workflow |
| `orchestrator complete <id>` | Mark item complete |
| `orchestrator skip <id>` | Skip optional item |
| `orchestrator advance` | Move to next phase |
| `orchestrator init` | Create workflow.yaml in current directory |
| `orchestrator handoff` | Generate handoff prompt |
| `orchestrator checkpoint` | Create checkpoint |
| `orchestrator resume` | Resume from checkpoint |
| `orchestrator setup` | Enable automatic updates for this repo |
| `orchestrator setup --remove` | Disable automatic updates |

## Workflow Rules

1. **Always check status first** - Run `orchestrator status` before any action
2. **Follow the current phase** - Only work on items in the current phase
3. **Document everything** - Use `--notes` to explain what was done
4. **Wait for approval** - At manual gates, inform user and wait
5. **Never skip phases** - Complete or skip all items before advancing

## Working with Any Project

The orchestrator works from any directory:

```bash
cd /path/to/any/project
orchestrator start "Fix authentication bug"
orchestrator status
```

If no `workflow.yaml` exists in the directory, it uses the bundled 5-phase development workflow automatically.

To customize the workflow for a project:
```bash
orchestrator init  # Creates workflow.yaml you can edit
```

## Provider System

The orchestrator supports multiple execution providers:

- `claude_code` - Claude Code CLI (auto-detected in this environment)
- `openrouter` - OpenRouter API
- `manual` - Copy/paste prompts

Current environment is auto-detected. Override with:
```bash
orchestrator handoff --provider manual
orchestrator handoff --env standalone
```

## Constraints

When starting a workflow, you can add constraints:
```bash
orchestrator start "Task" --constraints "No database changes" --constraints "Python only"
```

Constraints are displayed in status and included in handoff prompts.

## Checkpoints

Create checkpoints to save progress:
```bash
orchestrator checkpoint --message "Completed phase 1" --decision "Using approach A"
```

Resume from a checkpoint:
```bash
orchestrator checkpoints  # List available
orchestrator resume --from cp_xxx
```

## Important Notes

- The orchestrator creates `.workflow_state.json` to track progress
- Workflow logs are stored in `.workflow_log.jsonl`
- Checkpoints are stored in `.workflow_checkpoints/`
- These files should be gitignored for most projects

## Getting Help

- Run `orchestrator --help` for command help
- Read `docs/SETUP_GUIDE.md` for setup instructions
- Check `ROADMAP.md` for planned features
- Review `LEARNINGS.md` for lessons learned
