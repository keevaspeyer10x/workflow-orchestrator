# AI Workflow Orchestrator

A general-purpose workflow enforcement system for AI agents. Prevents AI agents from "forgetting" workflow steps during complex tasks through active verification, structured state management, and Claude Code integration.

## Features

- **YAML-based workflow definitions** - Define workflows as config, not code
- **Active verification** - Checks file existence, runs commands, requires manual gates
- **Structured logging** - Full audit trail for analytics and learning
- **Analytics & learning** - Aggregate insights and auto-generated improvement suggestions
- **Visual dashboard** - Real-time web UI for monitoring
- **Claude Code integration** - Delegate coding tasks to Claude Code with structured handoffs
- **Cross-phase protection** - Can't complete items from other phases
- **Security hardening** - Command injection protection, path traversal blocking

## Installation

### Global Install (Recommended)

Install the orchestrator globally to use it from any directory:

```bash
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
```

After installation, the `orchestrator` command is available globally:

```bash
orchestrator --version
orchestrator init        # Create workflow.yaml in current directory
orchestrator start "My task"
orchestrator status
```

### For AI Agents (Claude Code Web, Manus, etc.)

Add this to your project instructions or CLAUDE.md:

```bash
# Install orchestrator if not available
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

# Then use it for non-trivial tasks
orchestrator start "Task description"
orchestrator status
```

### Development Install

For contributing or local development:

```bash
git clone https://github.com/keevaspeyer10x/workflow-orchestrator.git
cd workflow-orchestrator
pip install -e .
```

## Quick Start

```bash
# 1. Install globally (or use pip install -e . for development)
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

# 2. Initialize workflow in your project (optional - works without this)
cd your-project
orchestrator init

# 3. Start a workflow
orchestrator start "Your task description"

# 4. Check status (AI should do this constantly)
orchestrator status
```

**Note:** If you don't run `orchestrator init`, the tool uses a bundled 5-phase development workflow (PLAN → EXECUTE → REVIEW → VERIFY → LEARN).

## Commands

| Command | Purpose |
|---------|---------|
| `init` | Initialize workflow.yaml in current directory |
| `start "task"` | Begin a new workflow |
| `status` | Check current state (AI should do this constantly) |
| `complete <item> --notes "..."` | Mark item done (runs verification) |
| `skip <item> --reason "..."` | Skip with documented reason |
| `approve-item <item>` | Human approval for manual gates |
| `advance` | Move to next phase |
| `handoff` | Generate Claude Code handoff prompt |
| `handoff --execute` | Execute directly with Claude Code |
| `dashboard` | Open visual dashboard |
| `analyze` | View aggregate analytics |
| `learn` | Generate learning report |
| `validate` | Validate a workflow YAML file |
| `generate-md` | Generate human-readable WORKFLOW.md |
| `finish --abandon` | Abandon current workflow |
| `install-hook` | Install auto-setup hook for Claude Code sessions |
| `uninstall-hook` | Remove the auto-setup hook |

## Workflow YAML Format

```yaml
name: "My Workflow"
version: "1.0"
description: "Description of the workflow"

settings:
  test_command: "pytest"
  docs_dir: "docs"

phases:
  - id: "PLAN"
    name: "Planning"
    description: "Plan the work"
    items:
      - id: "create_plan"
        name: "Create plan"
        description: "Document the approach"
        required: true
        verification:
          type: "file_exists"
          path: "PLAN.md"
      
      - id: "user_approval"
        name: "Get approval"
        required: true
        verification:
          type: "manual_gate"

  - id: "EXECUTE"
    name: "Implementation"
    items:
      - id: "run_tests"
        name: "Run tests"
        verification:
          type: "command"
          command: "{{test_command}}"
          expect_exit_code: 0
```

## Verification Types

| Type | Description | Example |
|------|-------------|---------|
| `file_exists` | Check if a file exists | `path: "docs/plan.md"` |
| `command` | Run a command and check exit code | `command: "pytest"` |
| `manual_gate` | Requires human approval | Use `approve-item` command |
| `none` | No verification needed | For optional items |

## Claude Code Integration

The orchestrator can delegate coding tasks to Claude Code:

```bash
# Generate a handoff prompt (copy to Claude Code manually)
orchestrator handoff --files "src/main.py,src/utils.py"

# Execute directly with Claude Code CLI
orchestrator handoff --execute --timeout 600
```

## For AI Agents

### Critical Rules

1. **ALWAYS run `status` first** - Before any work, check current state
2. **Work only on current phase items** - Cross-phase operations are blocked
3. **Complete items with notes** - `complete <item> --notes "what you did"`
4. **Skip with reasons** - `skip <item> --reason "why skipping"`
5. **Wait for human approval** - Manual gates require `approve-item`

### Example Session

```bash
# 1. Check status
orchestrator status

# 2. Do the work for an item
# ... (actual work) ...

# 3. Mark complete
orchestrator complete initial_plan --notes "Created plan in PLAN.md"

# 4. Check status again
orchestrator status

# 5. When all items done, advance
orchestrator advance
```

## Manus Project Setup

Add this to your Manus Project Instructions:

```
## AI Workflow Enforcement

Before ANY coding task:
1. Run `orchestrator status` to check current workflow state
2. If no active workflow, run `orchestrator start "task description"`
3. Work only on items in the current phase
4. After completing work, run `orchestrator complete <item> --notes "..."`
5. Check status again before moving to next item
6. When all items complete, run `orchestrator advance`

NEVER skip the status check. NEVER work on items from other phases.
```

## Security

- **Command injection protection** - Template variables are sanitized (alphanumeric, dash, underscore, dot, slash only)
- **Dangerous patterns blocked** - Shell metacharacters (`$()`, backticks, `&&`, `||`, `;`, `|`, `>`, `<`) are rejected
- **Path traversal protection** - File operations restricted to working directory
- **Localhost binding** - Dashboard only accessible locally
- **File locking** - Prevents race conditions in state updates

## Files

| File | Purpose |
|------|---------|
| `workflow.yaml` | Workflow definition |
| `.workflow_state.json` | Current state (gitignore this) |
| `.workflow_log.jsonl` | Event log for analytics |
| `WORKFLOW.md` | Human-readable state (auto-generated) |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    THE ITERATION LOOP                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   workflow.yaml ──────► orchestrator ──────► .log.jsonl     │
│        ▲                     │                   │           │
│        │                     ▼                   ▼           │
│        │              .workflow_state     analyze/learn      │
│        │                     │                   │           │
│        └────────── LEARNINGS.md ◄────────────────┘           │
│                         │                                    │
│                         ▼                                    │
│                  Human reviews                               │
│                  Updates workflow.yaml                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## License

MIT

---

*This system was designed and built collaboratively with AI assistance.*
