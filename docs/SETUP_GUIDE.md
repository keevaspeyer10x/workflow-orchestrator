# Workflow Orchestrator Setup Guide

This guide covers setting up the workflow-orchestrator in different environments:

1. **Claude Code CLI on Windows (via WSL2)** - For desktop/laptop development
2. **Claude Code Web** - For mobile/browser-based development
3. **Using with External Repositories** - Working on projects outside the orchestrator repo

---

## Prerequisites

- **Anthropic API Key** - Get one from [console.anthropic.com](https://console.anthropic.com)
- **Claude Pro subscription** (recommended) or API credits
- **Git** installed

---

## Option 1: Claude Code CLI on Windows (WSL2)

WSL2 (Windows Subsystem for Linux) provides the best compatibility for Claude Code CLI on Windows.

### Step 1: Install WSL2

Open **PowerShell as Administrator** and run:

```powershell
# Install WSL with Ubuntu (default)
wsl --install

# Restart your computer when prompted
```

After restart, Ubuntu will launch automatically to complete setup. Create a username and password when prompted.

### Step 2: Update Ubuntu and Install Dependencies

In the Ubuntu terminal:

```bash
# Update package lists
sudo apt update && sudo apt upgrade -y

# Install essential tools
sudo apt install -y git curl wget build-essential

# Install Python 3.11+
sudo apt install -y python3 python3-pip python3-venv
```

### Step 3: Install Node.js (for Claude Code CLI)

```bash
# Install Node.js 22.x (LTS)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
node --version  # Should show v22.x.x
npm --version
```

### Step 4: Install Claude Code CLI

```bash
# Install Claude Code globally
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version
```

### Step 5: Configure API Key

```bash
# Set API key (replace with your actual key)
export ANTHROPIC_API_KEY="sk-ant-xxxxx"

# Make it permanent
echo 'export ANTHROPIC_API_KEY="sk-ant-xxxxx"' >> ~/.bashrc
source ~/.bashrc
```

### Step 6: Clone and Setup Workflow Orchestrator

```bash
# Clone the repository
git clone https://github.com/keevaspeyer10x/workflow-orchestrator.git
cd workflow-orchestrator

# Install Python dependencies
pip3 install -r requirements.txt

# Verify orchestrator works
./orchestrator status
```

### Step 7: Test Claude Code Integration

```bash
# Test that Claude Code CLI is detected
./orchestrator handoff --provider auto

# Should show: "Detected Claude Code environment" or similar
```

### Using the Orchestrator with Claude Code CLI

```bash
# Start a workflow
./orchestrator start "Implement feature X"

# When ready to hand off to Claude Code for implementation
./orchestrator handoff --execute

# Claude Code will automatically receive the prompt and execute it
```

---

## Option 2: Claude Code Web (Browser/Mobile)

Claude Code Web runs in a **remote sandbox** with full terminal access. Great for:
- Mobile "vibe coding" from your phone
- Working without local setup
- Background task processing

### Step 1: Access Claude Code Web

1. Go to [claude.ai](https://claude.ai)
2. Sign in with your Anthropic account
3. Start a new conversation

### Step 2: Install the Orchestrator

Simply ask Claude to install it:

```
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
```

That's it! The orchestrator is now available globally.

### Step 3: Use the Orchestrator

```bash
# Check status
orchestrator status

# Start a workflow for your task
orchestrator start "Implement feature X"

# Work through the phases
orchestrator complete <item> --notes "What was done"
orchestrator advance
```

### Step 4: Clone Your Project (Optional)

If working on an existing project:

```bash
git clone https://github.com/your-username/your-project.git
cd your-project
orchestrator start "Task description"
```

### Option A: Automatic Setup (Recommended)

Run once to enable auto-updates for your project:

```bash
orchestrator setup
```

This creates a hook that:
- Auto-updates orchestrator at session start
- Works in both Claude Code CLI and Claude Code Web
- Always gets the latest version from GitHub

**Your files are safe:** Auto-updates only update the orchestrator code. Your repo-specific files (`workflow.yaml`, workflow state, logs) are never modified.

To disable: `orchestrator setup --remove`

### Option B: Manual Setup

Add to your project's CLAUDE.md:

```markdown
## Setup
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
```

Then say "run setup" at the start of each session.

### Notes

- **No local workflow.yaml needed**: Uses bundled 5-phase workflow by default
- **Works everywhere**: Claude Code CLI, Claude Code Web, Manus

---

## Option 3: Using with External Repositories

The workflow-orchestrator is designed to work with **any project**, not just itself.

### Method A: Symlink Approach (Recommended)

Keep the orchestrator in one location and symlink to your projects:

```bash
# In WSL2 or any Linux environment
cd ~/workflow-orchestrator

# Create a workflow for your project
./orchestrator start "Work on Pingxa feature" --working-dir ~/pingxa

# Or symlink the orchestrator to your project
ln -s ~/workflow-orchestrator/orchestrator ~/pingxa/orchestrator
cd ~/pingxa
./orchestrator status
```

### Method B: Copy workflow.yaml to Your Project

```bash
# Copy the workflow definition to your project
cp ~/workflow-orchestrator/workflow.yaml ~/your-project/
cp -r ~/workflow-orchestrator/src ~/your-project/.workflow-orchestrator/

# Create a wrapper script in your project
cat > ~/your-project/orchestrator << 'EOF'
#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
python3 "$DIR/.workflow-orchestrator/cli.py" "$@"
EOF
chmod +x ~/your-project/orchestrator
```

### Method C: Global Installation (Recommended)

Install globally with pip:
```bash
pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
```

Then use from any directory:
```bash
cd ~/your-project
orchestrator status        # Uses bundled workflow if no local workflow.yaml
orchestrator init          # Creates workflow.yaml in current directory
orchestrator start "Task"
```

This is the simplest approach for most users and works in all environments (local, Claude Code Web, Manus).

### Working Directory Configuration

The orchestrator respects the `--working-dir` flag:

```bash
# Run orchestrator commands for a different project
./orchestrator status --working-dir /path/to/your/project
./orchestrator handoff --execute --working-dir /path/to/your/project
```

---

## Environment-Specific Behavior

The orchestrator automatically detects your environment and adjusts:

| Environment | Detection | Default Provider | Notes |
|-------------|-----------|------------------|-------|
| Claude Code CLI | `.claude` dir, `CLAUDE_CODE` env var | `claude_code` | Full auto-execution |
| Claude Code Web | `CLAUDE_CODE_REMOTE` env var | `claude_code` | Remote sandbox |
| Manus | `/home/ubuntu`, `MANUS_SESSION` env var | `openrouter` | API-based execution |
| Standalone | None of the above | `manual` | Copy/paste prompts |

### Override Environment Detection

```bash
# Force a specific environment
./orchestrator handoff --env claude_code
./orchestrator handoff --env standalone

# Force a specific provider
./orchestrator handoff --provider manual
./orchestrator handoff --provider openrouter --model anthropic/claude-3.5-sonnet
```

---

## Secrets Management

The orchestrator supports multiple secret sources, checked in priority order:

1. **Environment Variables** (highest priority)
2. **SOPS-encrypted files** (for teams)
3. **GitHub Private Repos** (for Claude Code Web with `gh` CLI)

### Check Available Sources

```bash
orchestrator secrets sources
```

### Option 1: Environment Variables (Simplest)

```bash
# Set in your shell profile
export ANTHROPIC_API_KEY="sk-ant-xxxxx"
export OPENROUTER_API_KEY="sk-or-xxxxx"
```

### Option 2: SOPS with Auto-Loading (Recommended for Claude Code Web)

For Claude Code Web sessions, you can store your SOPS AGE key encrypted in the repo.
This requires only a short password per session instead of pasting the full key.

**One-time setup:**

```bash
# Run the encryption script
./scripts/encrypt-sops-key.sh

# Enter your AGE secret key when prompted
# Choose a memorable password

# Commit the encrypted key (safe to commit!)
git add .manus/keys/age.key.enc
git commit -m "Add encrypted SOPS key"
git push
```

**Using in Claude Code Web:**

1. When starting a new task, set the environment variable:
   - `SOPS_KEY_PASSWORD` = your chosen password

2. The SessionStart hook will automatically:
   - Decrypt your AGE key
   - Set `SOPS_AGE_KEY` for the session
   - Enable SOPS secret access

**For desktop use:** Store the unencrypted key at `.manus/keys/age.key` (gitignored).

### Option 3: SOPS Manual Setup (for Teams)

SOPS provides encrypted secrets that can be safely committed to git:

```bash
# Install SOPS and age
sudo apt install -y sops age

# Generate a key
age-keygen -o ~/.sops-key.txt

# Create encrypted secrets
sops --encrypt --age $(cat ~/.sops-key.txt | grep "public key" | cut -d: -f2 | tr -d ' ') \
    secrets.yaml > .manus/secrets.enc.yaml

# Set the key for decryption
export SOPS_AGE_KEY="AGE-SECRET-KEY-..."
```

### Option 4: GitHub Private Repo

When using Claude Code CLI (desktop) with `gh` authenticated:

```bash
# Configure your secrets repo (one time)
orchestrator config set secrets_repo YOUR_USERNAME/secrets

# Create your secrets repo on GitHub (private)
# Add files named exactly as the secret: OPENROUTER_API_KEY, OPENAI_API_KEY, etc.
```

Note: This requires `gh auth login` and works best on desktop where you can authenticate the GitHub CLI.

### Testing Secret Access

```bash
# Test if a secret is accessible
orchestrator secrets test OPENROUTER_API_KEY

# See which source provides a secret
orchestrator secrets source OPENROUTER_API_KEY
```

---

## Troubleshooting

### "Claude Code CLI not found"

```bash
# Check if installed
which claude
claude --version

# If not found, reinstall
npm install -g @anthropic-ai/claude-code
```

### "Permission denied" on orchestrator

```bash
chmod +x ./orchestrator
```

### "Python module not found"

```bash
pip3 install -r requirements.txt
```

### WSL2 Issues

```powershell
# In PowerShell, check WSL status
wsl --status

# Update WSL
wsl --update

# Reset if needed
wsl --unregister Ubuntu
wsl --install Ubuntu
```

### Claude Code Web Sandbox Reset

The Web sandbox resets between sessions. Use SessionStart Hooks or re-run setup commands each session.

---

## Quick Reference

### Daily Workflow (After Global Install)

```bash
# Start your day
cd ~/your-project
orchestrator status

# Start a new task
orchestrator start "Implement user authentication"

# Work through the phases
orchestrator complete check_roadmap --notes "No relevant items"
orchestrator complete clarifying_questions --notes "Requirements clear"
# ... continue through workflow

# Hand off to Claude Code for implementation
orchestrator handoff --execute

# After Claude completes, continue
orchestrator complete implement_code --notes "Feature implemented"
```

### Daily Workflow (Claude Code Web)

```
1. Go to claude.ai
2. Install the orchestrator:
   pip install git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
3. Clone your project (if needed):
   git clone https://github.com/your-username/your-project.git
   cd your-project
4. Start and follow the workflow:
   orchestrator start "My task"
   orchestrator status
5. At end of workflow, commit when prompted (commit_and_sync step)
```

---

## Next Steps

1. **Read the workflow.yaml** - Understand the 5-phase workflow
2. **Customize for your project** - Modify phases, items, and settings
3. **Set up your first task** - Try `./orchestrator start "Hello World"`
4. **Explore advanced features** - Checkpoints, constraints, notes

For more information, see:
- [ROADMAP.md](./ROADMAP.md) - Planned features
- [LEARNINGS.md](../LEARNINGS.md) - Lessons learned
- [PRD_v2.2_ENHANCEMENTS.md](../PRD_v2.2_ENHANCEMENTS.md) - Feature specifications
