# Workflow Orchestrator - Claude Code Instructions

## CRITICAL: API Keys for External Reviews

**External AI model reviews are REQUIRED for code changes.** You need YOUR OWN API keys (not someone else's!):

**Required keys:**
- `GEMINI_API_KEY` - For Gemini 3 Pro reviews
- `OPENAI_API_KEY` - For GPT-5.2 Max / Codex reviews
- `OPENROUTER_API_KEY` - For API fallback
- `XAI_API_KEY` - For Grok 4.1 reviews

### Setup: Password-Protected Secrets (Recommended)

**One-time setup:**

1. **Install SOPS** (if not already installed):
   ```bash
   # macOS
   brew install sops age

   # Linux
   wget https://github.com/getsops/sops/releases/latest/download/sops-latest.linux.amd64
   sudo mv sops-latest.linux.amd64 /usr/local/bin/sops && chmod +x /usr/local/bin/sops
   ```

2. **Generate your AGE key**:
   ```bash
   mkdir -p ~/.config/sops/age
   age-keygen -o ~/.config/sops/age/keys.txt
   ```

3. **Create your secrets file**:
   ```bash
   # Get your public key
   grep "public key:" ~/.config/sops/age/keys.txt

   # Create .sops.yaml with your public key
   cat > .sops.yaml << EOF
   creation_rules:
     - age: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  # Your public key
   EOF

   # Create and encrypt your secrets
   sops secrets.enc.yaml
   # Add your API keys in YAML format:
   # gemini_api_key: your-key-here
   # openai_api_key: your-key-here
   # openrouter_api_key: your-key-here
   # grok_api_key: your-key-here
   ```

4. **Encrypt your AGE key with a password** (global setup - works across all repos):
   ```bash
   # Create global config directory
   mkdir -p ~/.config/workflow-orchestrator/keys

   # Encrypt your AGE key with a password
   openssl enc -aes-256-cbc -pbkdf2 \
     -in ~/.config/sops/age/keys.txt \
     -out ~/.config/workflow-orchestrator/keys/age.key.enc
   # Choose a memorable password when prompted
   ```

5. **Set your password as an environment variable** (one-time setup):
   ```bash
   # For Happy: Add to Happy settings
   SOPS_KEY_PASSWORD=your-memorable-password

   # For desktop: Add to shell profile (~/.bashrc, ~/.zshrc, etc.)
   echo 'export SOPS_KEY_PASSWORD="your-memorable-password"' >> ~/.zshrc
   source ~/.zshrc
   ```

**How it works:**
- Your encrypted AGE key is stored globally in `~/.config/workflow-orchestrator/keys/age.key.enc`
- Session hook auto-decrypts your AGE key using `SOPS_KEY_PASSWORD` from your environment
- AGE key decrypts `secrets.enc.yaml` (per-repo file with your API keys)
- API keys are loaded automatically
- **Works across ALL repos** - just set the password once!
- No manual steps needed each session!

**Verify it's working:**
```bash
env | grep -i api_key
```

**If keys are not loaded:**
- Reviews will FAIL during the REVIEW phase
- The workflow will NOT complete properly
- `orchestrator finish` will show "No external model reviews recorded!"

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

**Note:** Auto-updates only update the orchestrator code. Your repo-specific files (`workflow.yaml`, workflow state, logs) are never modified.

## Automatic Updates

The orchestrator automatically updates itself at the start of each Claude Code session via the session-start hook:

**What gets auto-updated:**
- ✅ Orchestrator Python package (from GitHub main branch)
- ✅ All CLI commands and features
- ✅ Bundled default workflow template (`src/default_workflow.yaml`)
- ❌ Your project's `workflow.yaml` (intentionally preserved - you customize this per-project)

**Why your workflow.yaml doesn't auto-update:**
- Each project customizes workflow.yaml for their specific needs
- Auto-updating would overwrite your customizations
- Workflow schema is backward compatible (new features are additive)
- When you start a workflow, the definition is version-locked to that workflow instance

**Getting new workflow features:**
If the bundled workflow gets new improvements (like WF-029 tradeoff analysis), you have options:

1. **Create a new workflow** - New workflows created with `orchestrator init` get the latest template
2. **Manual merge** - Copy specific improvements from `src/default_workflow.yaml` to your `workflow.yaml`
3. **Keep as-is** - Old workflows continue working (backward compatible)

**Recent workflow improvements:**
- **WF-029 (v2.5.0)**: Mandatory tradeoff analysis in LEARN phase prevents roadmap bloat
  - Requires complexity vs benefit analysis for all roadmap items
  - Categorizes as ✅ RECOMMEND / ⚠️ DEFER / 🔍 EXPLORATORY
  - Includes YAGNI checks and evidence evaluation
  - See workflow.yaml:359-367 for implementation

**Verifying updates:**
```bash
# Check orchestrator version
orchestrator --version

# Check workflow version (in your workflow.yaml)
grep "^version:" workflow.yaml

# View bundled default workflow
cat $(python -c "import workflow_orchestrator; print(workflow_orchestrator.__file__.replace('__init__.py', 'default_workflow.yaml'))")
```

## Parallel Agent Spawning (PRD Execution)

Spawn multiple Claude Code agents to work on tasks in parallel using tmux sessions.

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
   - Requires tmux installed

2. **SubprocessAdapter** (fallback): Fire-and-forget subprocess spawning
   - Used when tmux not available (CI, containers)
   - Logs captured to `.wfo_logs/`
   - No attach capability

### Happy Integration (Mobile Access)

If you use [Happy](https://happy.engineering/) to access Claude Code from mobile, spawned agents will appear in your Happy app:

```bash
# One-time global setup (persists across all repos)
orchestrator config set claude_binary happy

# Now all spawned agents appear in Happy!
orchestrator prd spawn --count 3
```

With Happy configured:
- Start parallel agents from your phone
- Monitor agent progress in the Happy app
- Seamless handoff between mobile and desktop

## Zero-Config Workflow Enforcement (PRD-008)

The `orchestrator enforce` command provides zero-setup workflow enforcement for AI agents.

### Quick Start

```bash
# Start a workflow with zero configuration
orchestrator enforce "Add user authentication"

# Parallel execution mode (spawn multiple agents)
orchestrator enforce "Refactor API layer" --parallel

# JSON output for programmatic use
orchestrator enforce "Fix login bug" --json
```

### What It Does

Single command setup that:
1. **Auto-detects or starts orchestrator server** (checks ports 8000-8002)
2. **Analyzes your repository** (detects Python/JavaScript/Go/Rust)
3. **Generates agent_workflow.yaml** (5-phase TDD workflow with language-specific commands)
4. **Outputs agent-ready instructions** (SDK usage examples, task context, execution mode)

### Supported Languages

- **Python**: Auto-detects pytest, generates `pytest` test command
- **JavaScript**: Auto-detects jest/mocha, generates `npm test` command
- **Go**: Auto-detects go.mod, generates `go test ./...` command
- **Rust**: Auto-detects Cargo.toml, generates `cargo test` command

### Generated Files

- `.orchestrator/agent_workflow.yaml` - 5-phase workflow (PLAN → TDD → IMPL → REVIEW → VERIFY)
- `.orchestrator/agent_instructions.md` - Agent SDK usage guide (backup reference)
- `.orchestrator/server.log` - Server logs (if auto-started)
- `.orchestrator/server.pid` - Server process ID (for cleanup)

### Agent SDK Integration

The command outputs instructions for using the Agent SDK:

```python
from src.agent_sdk.client import AgentClient

# Connect to orchestrator
client = AgentClient(
    agent_id="agent-001",
    orchestrator_url="http://localhost:8000"
)

# Claim a task
task = client.claim_task(capabilities=["read_files", "write_files"])

# Work through phases
current_phase = client.get_current_phase()
client.advance_phase()
```

### Execution Modes

**Sequential (default)**: Single agent works through phases linearly
```bash
orchestrator enforce "Task"
```

**Parallel**: Multiple agents work on different phases/tasks
```bash
orchestrator enforce "Task" --parallel
```

### For AI Agents

When an AI agent runs `orchestrator enforce`, it receives:
- Complete task context
- Server URL for Agent SDK
- Workflow file location
- Phase-by-phase guidance
- Tool restrictions per phase
- Example code snippets

**All output goes to stdout** for immediate AI consumption. Backup files are saved to `.orchestrator/` for reference.

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
| `orchestrator resolve` | Resolve git merge/rebase conflicts |
| `orchestrator setup` | Enable automatic updates for this repo |
| `orchestrator setup --remove` | Disable automatic updates |
| `orchestrator config set KEY VALUE` | Set configuration value |
| `orchestrator config get KEY` | Get configuration value |
| `orchestrator secrets sources` | Show available secret sources |
| `orchestrator secrets test NAME` | Test if a secret is accessible |
| `orchestrator prd spawn --count N` | Spawn N parallel agents |
| `orchestrator prd sessions` | List active agent sessions |
| `orchestrator prd attach <task>` | Attach to agent's tmux window |
| `orchestrator prd done <task>` | Mark task complete, terminate session |
| `orchestrator prd cleanup` | Clean up all agent sessions |
| `orchestrator approval pending` | List pending approval requests from parallel agents |
| `orchestrator approval approve <id>` | Approve an agent's request |
| `orchestrator approval reject <id>` | Reject an agent's request |
| `orchestrator approval approve-all` | Approve all pending requests |
| `orchestrator approval stats` | Show approval queue statistics |
| `orchestrator approval watch` | Watch for new approval requests (with tmux bell notification) |
| `orchestrator approval summary` | Show decision summary (auto-approved vs human-approved) |

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

## Conflict Resolution

When git is in a merge or rebase conflict state, use `orchestrator resolve`:

```bash
# Preview what would be resolved (safe, no changes)
orchestrator resolve

# Apply automatic resolutions
orchestrator resolve --apply

# Force a specific strategy for all files
orchestrator resolve --apply --strategy ours    # Keep our changes
orchestrator resolve --apply --strategy theirs  # Accept target branch

# Auto-commit after resolution
orchestrator resolve --apply --commit

# Abort the merge/rebase entirely
orchestrator resolve --abort
```

**Resolution Philosophy: Rebase-First**
- Target branch is truth
- Adapt our changes to work with target
- When in doubt, escalate to user with analysis and recommendation

**Note:** `orchestrator status` will show a conflict warning if git has unresolved conflicts.

### Conflict Resolution Configuration

Configure conflict resolution behavior in `~/.orchestrator/config.yaml`:

```yaml
# Per-file resolution policies
# Override how specific files are resolved during conflicts
file_policies:
  "package-lock.json": "regenerate"   # Regenerate lock files
  "*.lock": "theirs"                  # Accept target branch for lock files
  ".env*": "ours"                     # Keep our environment files
  "*.min.js": "theirs"                # Accept minified files from target

# Sensitive file globs (never sent to LLM for resolution)
sensitive_globs:
  - "secrets/*"
  - "*.pem"
  - ".env*"
  - "*.key"
  - "*credential*"

# LLM resolution settings
resolution:
  disable_llm: false              # Set to true for air-gapped environments
  max_file_size_for_llm: 10485760 # 10MB - skip LLM for larger files
  max_conflicts_for_llm: 50       # Skip LLM if >50 conflicts
  timeout_per_file: 120           # 2 min timeout per file

# Conflict learning settings
learning:
  auto_roadmap_suggestions: true  # Auto-add suggestions to ROADMAP.md
  conflict_threshold: 3           # Flag files with >= 3 conflicts
  session_window: 10              # Analyze last 10 sessions
```

**Conflict Learning:**
- Conflict resolutions are logged to `.workflow_log.jsonl`
- The LEARN phase analyzes patterns (frequently conflicted files)
- Suggestions are auto-added to ROADMAP.md when patterns detected

## Secrets Management

The orchestrator supports multiple secret sources (checked in priority order):

1. **Environment Variables** (highest priority)
2. **SOPS-encrypted files** (for teams)
3. **GitHub Private Repos** (for Claude Code Web)

```bash
# Check available sources
orchestrator secrets sources

# Configure a private GitHub repo for secrets (for Claude Code Web)
orchestrator config set secrets_repo YOUR_USERNAME/secrets

# Test secret access
orchestrator secrets test OPENROUTER_API_KEY
```

For Claude Code Web: Store secrets as files in a private GitHub repo (file names = secret names).

## Feedback System (Two-Tier - Phase 3b)

The orchestrator captures workflow feedback to enable continuous improvement and pattern detection.

### Two Types of Feedback

**Phase 3b** introduces a two-tier feedback system that separates tool metrics from project-specific context:

1. **Tool Feedback** (`.workflow_tool_feedback.jsonl`) - About orchestrator itself
   - **Anonymized** - workflow_id hashed (salted SHA256), no repo/task names
   - **Shareable** - Safe to upload to maintainer for analysis
   - Contains: Phase timings, error counts, items skipped, review status
   - Example: `{"timestamp": "...", "workflow_id_hash": "abc123...", "phases": {...}, "repo_type": "python"}`

2. **Process Feedback** (`.workflow_process_feedback.jsonl`) - About your project
   - **Private**, stays local
   - Contains: Task description, repo URL, learnings, challenges, project errors
   - Never uploaded or shared

### Security: Salt Management

The orchestrator uses a salt when hashing workflow_id to prevent rainbow table attacks.

**Default Salt**: `workflow-orchestrator-default-salt-v1`
- Secure for single-user installations
- Provides protection against rainbow table attacks
- Same salt used across all workflows for correlation

**Custom Salt** (optional, for teams):
```bash
# Set custom salt (recommended for multi-user deployments)
export WORKFLOW_SALT="your-random-secret-salt-here"

# Generate a random salt
openssl rand -base64 32
```

**Important Security Notes**:
- Salt should be **secret** and **not committed** to version control
- Salt should be **consistent per installation** (not per-workflow)
- Salt enables correlation: same workflow_id always produces same hash
- Changing salt breaks correlation (historical analysis becomes harder)
- For teams: Store salt in secure secrets management (SOPS, 1Password, etc)

### Commands

```bash
# Capture feedback (automatic in LEARN phase)
orchestrator feedback

# Review patterns
orchestrator feedback review                 # Both tool and process
orchestrator feedback review --tool          # Tool patterns only
orchestrator feedback review --process       # Process patterns only

# Upload anonymized tool feedback (optional)
orchestrator feedback sync --dry-run         # Preview what would be uploaded
orchestrator feedback sync                    # Upload to GitHub Gist
orchestrator feedback sync --status           # Show sync statistics

# Configure sync
orchestrator config set feedback_sync false   # Disable sync (default: enabled for developer)
```

### What Gets Uploaded (Tool Feedback Only)

**Anonymized data** (safe to share):
- Phase timings (how long each phase took)
- Error counts (not error details)
- Items skipped count (not reasons)
- Reviews performed (yes/no)
- Parallel agents used (yes/no)
- Repo type (python/javascript/go/rust)
- Orchestrator version

**Never uploaded** (stays local):
- Task descriptions
- Repo names/URLs
- Error messages (may contain code/filenames)
- Learnings and challenges (project-specific)
- Any code snippets or project context

### Commands

```bash
# Capture feedback (automatic in LEARN phase)
orchestrator feedback

# Review patterns
orchestrator feedback review                  # Review both tool and process feedback
orchestrator feedback review --tool           # Review tool patterns only
orchestrator feedback review --process        # Review process patterns only
orchestrator feedback review --suggest        # Generate roadmap suggestions

# Sync anonymized tool feedback (opt-in by default for developer)
orchestrator feedback sync --dry-run          # Preview what would be uploaded
orchestrator feedback sync                     # Upload to GitHub Gist
orchestrator feedback sync --status            # Show sync statistics
orchestrator feedback sync --force             # Re-sync all entries

# Disable sync
orchestrator config set feedback_sync false
```

### Feedback Files

The orchestrator collects feedback in two files:

1. **`.workflow_tool_feedback.jsonl`** - Anonymized, shareable
   - About orchestrator itself (phase timings, error counts, reviews performed)
   - Workflow ID hashed with SHA256
   - No task descriptions, repo names, or code
   - Includes: repo_type (python/js/go/rust), phase timings, error counts, review stats

2. **`.workflow_process_feedback.jsonl`** - Private, local-only
   - Full project context (task, repo, learnings)
   - Error details and skipped item reasons
   - Project-specific challenges and improvements
   - Never uploaded, stays local

### Sync to GitHub Gist

You can optionally sync anonymized tool feedback to help improve the orchestrator:

```bash
# Preview what would be uploaded (no PII!)
orchestrator feedback sync --dry-run

# Upload anonymized tool feedback
orchestrator feedback sync

# Check sync status
orchestrator feedback sync --status

# Opt out of sync
orchestrator config set feedback_sync false
```

**Privacy guarantee:**
- Only `.workflow_tool_feedback.jsonl` is synced (anonymized)
- Process feedback (`.workflow_process_feedback.jsonl`) NEVER leaves your machine
- Tool feedback has NO task descriptions, repo names, or code
- workflow_id is hashed (SHA256)
- You can review before uploading: `orchestrator feedback sync --dry-run`

## Important Notes

- The orchestrator creates `.workflow_state.json` to track progress
- Workflow logs are stored in `.workflow_log.jsonl`
- Checkpoints are stored in `.workflow_checkpoints/`
- **Feedback files** (Phase 3b):
  - `.workflow_tool_feedback.jsonl` - Anonymized orchestrator metrics (shareable)
  - `.workflow_process_feedback.jsonl` - Project-specific learnings (private)
  - `.workflow_feedback.jsonl.migrated` - Backup of Phase 3a feedback (if migrated)
- These files should be gitignored for most projects

## Feedback System (Two-Tier)

The orchestrator collects two types of feedback to improve both the tool and your workflows:

### Two-Tier System

1. **Tool Feedback** (`.workflow_tool_feedback.jsonl`) - About orchestrator itself
   - **Anonymized** - workflow_id hashed, no repo/task names
   - **Shareable** - Safe to upload via sync command
   - **Purpose**: Help improve orchestrator features across all users

2. **Process Feedback** (`.workflow_process_feedback.jsonl`) - About your project
   - **Private**, stays local
   - Contains learnings, challenges, project-specific data
   - Never uploaded or shared

### Feedback Commands

```bash
# Capture feedback (automatic in LEARN phase)
orchestrator feedback

# Interactive mode (prompts questions)
orchestrator feedback capture --interactive

# Review patterns
orchestrator feedback review                 # Show both tool and process patterns
orchestrator feedback review --tool          # Review tool patterns only
orchestrator feedback review --process       # Review process patterns only
orchestrator feedback review --days 30       # Review last 30 days
orchestrator feedback review --suggest       # Generate ROADMAP suggestions

# Sync anonymized tool feedback to maintainer (opt-in by default)
orchestrator feedback sync                     # Upload new entries
orchestrator feedback sync --dry-run           # Preview what would be uploaded
orchestrator feedback sync --status            # Show sync statistics
orchestrator feedback sync --force             # Re-sync all entries

# Opt-out of feedback sync
orchestrator config set feedback_sync false
```

### Feedback Files

The orchestrator collects two types of feedback:

1. **Tool Feedback** (`.workflow_tool_feedback.jsonl`)
   - About orchestrator itself (performance, reliability, feature usage)
   - Automatically anonymized (workflow_id hashed, no repo/task names)
   - Safe to share with maintainers
   - Example contents: phase timings, items skipped (count only), reviews performed (yes/no)

2. **Process Feedback** (`.workflow_process_feedback.jsonl`) - About your project
   - Private, stays local (never uploaded)
   - Contains full context: task, repo, learnings, challenges
   - Used for your own pattern analysis

### Feedback Commands

```bash
# Capture feedback (runs automatically in LEARN phase)
orchestrator feedback

# Review patterns
orchestrator feedback review                 # Show both tool and process patterns
orchestrator feedback review --tool          # Show only tool patterns
orchestrator feedback review --process       # Show only process patterns
orchestrator feedback review --days 30       # Review last 30 days
orchestrator feedback review --suggest       # Generate roadmap suggestions

# Sync anonymized tool feedback to GitHub Gist (opt-in by default)
orchestrator feedback sync                   # Upload new entries
orchestrator feedback sync --dry-run         # Preview what would be uploaded
orchestrator feedback sync --status          # Show sync statistics
orchestrator feedback sync --force           # Re-sync all entries

# Opt out of sync
orchestrator config set feedback_sync false
```

### What Gets Captured

**Tool Feedback** (`.workflow_tool_feedback.jsonl`) - About orchestrator itself:
- Anonymized (workflow_id hashed, no repo/task names)
- Phase timings and duration
- Items skipped (count only)
- Reviews performed (yes/no)
- Parallel agents used (yes/no)
- Orchestrator errors (count only)
- Repo type (python/javascript/go/rust)

**Process Feedback** (`.workflow_process_feedback.jsonl`) - About your project:
- Task description
- Repo information
- Learnings and challenges
- What went well/poorly
- Project-specific errors and issues

### Privacy

- Tool feedback is **anonymized** before sync - no PII, code, or project details
- Process feedback **never leaves your machine** - stays local
- Use `orchestrator feedback sync --dry-run` to preview what would be uploaded
- All sync is opt-in (default: enabled for developer, can disable)

## Important Notes

- The orchestrator creates `.workflow_state.json` to track progress
- Workflow logs are stored in `.workflow_log.jsonl`
- Checkpoints are stored in `.workflow_checkpoints/`
- **Phase 3b**: Feedback is stored in two files:
  - `.workflow_tool_feedback.jsonl` - Anonymized, shareable
  - `.workflow_process_feedback.jsonl` - Private, local-only
  - `.workflow_feedback.jsonl.migrated` - Backup of Phase 3a format (if migrated)
- These files should be gitignored for most projects

## Getting Help

- Run `orchestrator --help` for command help
- Read `docs/SETUP_GUIDE.md` for setup instructions
- Check `ROADMAP.md` for planned features
- Review `LEARNINGS.md` for lessons learned


- The orchestrator creates `.workflow_state.json` to track progress
- Workflow logs are stored in `.workflow_log.jsonl`
- Checkpoints are stored in `.workflow_checkpoints/`
- These files should be gitignored for most projects

## Getting Help

- Run `orchestrator --help` for command help
- Read `docs/SETUP_GUIDE.md` for setup instructions
- Check `ROADMAP.md` for planned features
- Review `LEARNINGS.md` for lessons learned
