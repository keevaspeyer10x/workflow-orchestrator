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

Run once to install a SessionStart hook in your project:

```bash
orchestrator install-hook
```

This creates `.claude/hooks/session-start.sh` which:
- Auto-installs/updates orchestrator at session start
- Works in both Claude Code CLI and Claude Code Web
- Always gets the latest version from GitHub

To remove: `orchestrator uninstall-hook`

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

### Using SOPS (Recommended for Teams)

The orchestrator supports SOPS-encrypted secrets:

```bash
# Install SOPS and age
sudo apt install -y sops age

# Generate a key
age-keygen -o ~/.sops-key.txt

# Create encrypted secrets
sops --encrypt --age $(cat ~/.sops-key.txt | grep "public key" | cut -d: -f2 | tr -d ' ') \
    secrets.yaml > secrets.enc.yaml
```

### Using Environment Variables

```bash
# Set in your shell profile
export ANTHROPIC_API_KEY="sk-ant-xxxxx"
export OPENROUTER_API_KEY="sk-or-xxxxx"
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
