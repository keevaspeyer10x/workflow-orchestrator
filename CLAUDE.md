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

4. **Encrypt your AGE key with a password**:
   ```bash
   mkdir -p .workflow-orchestrator/keys
   openssl enc -aes-256-cbc -pbkdf2 \
     -in ~/.config/sops/age/keys.txt \
     -out .workflow-orchestrator/keys/age.key.enc
   # Choose a memorable password when prompted
   ```

5. **Set your password as an environment variable**:
   ```bash
   # For Happy: Add to settings
   SOPS_KEY_PASSWORD=your-memorable-password

   # For desktop: Add to shell profile (~/.bashrc, ~/.zshrc, etc.)
   echo 'export SOPS_KEY_PASSWORD="your-memorable-password"' >> ~/.zshrc
   ```

**How it works:**
- Session hook auto-decrypts your AGE key using `SOPS_KEY_PASSWORD`
- AGE key decrypts `secrets.enc.yaml`
- API keys are loaded automatically
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

## Happy Integration (Optional)

If the user uses [Happy](https://happy.engineering/) to access Claude Code from mobile, configure the orchestrator to spawn sessions using Happy:

```bash
# One-time global setup (persists across all repos)
orchestrator config set claude_binary happy

# Or per-session override
CLAUDE_BINARY=happy orchestrator prd spawn --count 3
```

This allows Claude Squad sessions to appear in the Happy mobile app.

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
