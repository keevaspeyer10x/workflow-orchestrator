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

### Quick Install (Recommended)

Run this in any repo to install with automatic updates:

```bash
curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash
```

This installs the orchestrator AND sets up a SessionStart hook so future Claude Code sessions auto-update to the latest version.

**Your files are safe:** Auto-updates only update the orchestrator code. Your repo-specific files (`workflow.yaml`, workflow state, logs) are never modified.

### Manual Install

```bash
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
orchestrator setup  # Optional: enables auto-updates for this repo
```

After installation, the `orchestrator` command is available globally:

```bash
orchestrator --version
orchestrator init        # Create workflow.yaml in current directory
orchestrator start "My task"
orchestrator status
```

### For AI Agents (Claude Code Web, Manus, etc.)

Just ask: "install workflow-orchestrator from keevaspeyer10x github"

Or add to your project's CLAUDE.md:

```markdown
## Setup
curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash
```

### Development Install

For contributing or local development:

```bash
git clone https://github.com/keevaspeyer10x/workflow-orchestrator.git
cd workflow-orchestrator
pip install -e .
```

## Quick Start

### Zero-Config Workflow Enforcement (New!)

For AI agents, the fastest way to get started:

```bash
orchestrator enforce "Add user authentication"
```

This single command:
- Auto-detects or starts the orchestrator server
- Generates `agent_workflow.yaml` based on your repo (Python/JS/Go/Rust)
- Outputs agent-ready instructions with SDK examples
- Supports `--parallel` for multi-agent execution

**For vibe coders:** Just say to Claude:
- "Install orchestrator" (first time only)
- "Use orchestrator enforce to build a user settings page"
- "Use orchestrator to fix the login bug"

**What happens:** The orchestrator guides you through 5 phases:
1. **PLAN** - Define the work, get your approval
2. **EXECUTE** - Write tests first, then code
3. **REVIEW** - AI reviews the code for security/quality
4. **VERIFY** - Run tests, manual checks
5. **LEARN** - Document learnings, commit changes

**For developers:** See [Commands](#commands) below for direct CLI usage.

## Commands

| Command | Purpose |
|---------|---------|
| `enforce "task"` | Zero-config setup: auto-start server, generate workflow, get agent instructions |
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
| `setup` | Enable automatic updates for this repo |
| `setup --remove` | Disable automatic updates |
| `prd spawn --count N` | Spawn N parallel Claude agents |
| `prd sessions` | List active agent sessions |
| `prd attach <task>` | Attach to agent's tmux window |
| `prd done <task>` | Mark task complete, terminate session |
| `prd cleanup` | Clean up all agent sessions |

## Parallel Agent Spawning

Spawn multiple Claude Code agents to work on tasks simultaneously using tmux sessions.

### Quick Start

```bash
# Spawn 3 parallel agents
orchestrator prd spawn --count 3

# List active agents
orchestrator prd sessions

# Watch an agent work (attaches to tmux)
orchestrator prd attach task-1

# Mark task complete (terminates session)
orchestrator prd done task-1

# Clean up all sessions
orchestrator prd cleanup
```

### How It Works

1. **TmuxAdapter** (default): Spawns agents in tmux windows
   - Sessions persist if orchestrator crashes
   - You can attach to watch/interact with agents
   - Requires tmux installed (`brew install tmux` or `apt install tmux`)

2. **SubprocessAdapter** (fallback): Fire-and-forget subprocess spawning
   - Used automatically when tmux not available (CI, containers, Windows)
   - Logs captured to `.wfo_logs/`
   - No attach capability

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

## Happy Integration

If you use [Happy](https://happy.engineering/) to access Claude Code from your mobile device, you can configure the orchestrator to spawn sessions using Happy instead of Claude. This allows spawned Claude Squad sessions to appear in your Happy mobile app.

### One-Time Global Setup

```bash
# Set Happy as the default Claude binary (persists across all repos)
orchestrator config set claude_binary happy
```

This saves to `~/.config/orchestrator/config.yaml` and applies globally.

### Per-Session Override

```bash
# Override for a single session
CLAUDE_BINARY=happy orchestrator prd spawn --count 3
```

### Priority Order

1. `CLAUDE_BINARY` environment variable (highest priority)
2. Global config (`orchestrator config set claude_binary happy`)
3. Default: `claude`

### Verify Configuration

```bash
# Check current setting
orchestrator config get claude_binary
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
