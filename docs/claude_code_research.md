# Claude Code Research - Environment Options

## Key Findings from Research

### Claude Code on the Web (claude.ai/code)

**YES, it has a remote sandbox with terminal access!**

From the research:
- "Claude Code on the Web runs in a **remote sandbox**" 
- "Claude Code on the Web executes tasks in a remote sandbox environment"
- The `&` prefix sends tasks from CLI to Web for background processing
- Can transfer tasks from Web back to local CLI using "Open from CLI" button
- Environment variable `CLAUDE_CODE_REMOTE` indicates when running in remote Web environment
- Supports SessionStart Hooks for environment setup in remote sessions

### Claude Code CLI vs Web

| Feature | CLI | Web |
|---------|-----|-----|
| Terminal access | Local machine | Remote sandbox |
| File system | Local | Remote sandbox |
| Background tasks | No | Yes (via `&` prefix) |
| Mobile access | No | Yes |
| Setup transfer | N/A | Via SessionStart Hooks |
| Model selection | Local config | Carries over from CLI |

### Windows Setup Options

For Windows users wanting to use Claude Code CLI:

1. **WSL2 (Windows Subsystem for Linux)** - Recommended
   - Full Linux environment
   - Native Node.js/npm support
   - Best compatibility with Claude Code CLI

2. **PowerShell** - Possible but not ideal
   - Some commands may need adaptation
   - Path handling differences

3. **Git Bash** - Alternative
   - Unix-like environment on Windows

### Recommendation for User

**Dual Setup: Claude Code CLI (WSL2) + Claude Code Web**

1. **For desktop/laptop work**: Use Claude Code CLI in WSL2
   - Full orchestrator integration
   - Auto-execution of handoff prompts
   - Local file access

2. **For mobile/on-the-go**: Use Claude Code Web
   - Remote sandbox with terminal
   - Can continue work started on CLI
   - "Vibe coding" from phone

### Setup Steps for Windows

```bash
# 1. Install WSL2 (PowerShell as Admin)
wsl --install

# 2. In WSL2 Ubuntu terminal
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# 3. Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# 4. Set API key
export ANTHROPIC_API_KEY=your_key
echo 'export ANTHROPIC_API_KEY=your_key' >> ~/.bashrc

# 5. Clone workflow-orchestrator
git clone https://github.com/keevaspeyer10x/workflow-orchestrator.git
cd workflow-orchestrator

# 6. Test
./orchestrator status
./orchestrator handoff --execute
```

### Key Claude Code Features for Orchestrator

- **Skills**: Custom workflows that can be loaded
- **Subagents**: Specialized task executors
- **CLAUDE.md**: Project-specific instructions (like our workflow.yaml)
- **Project Rules**: Conditional rules in `.claude/rules/`
- **Hooks**: Lifecycle event triggers
- **Sandbox**: File system/network restrictions
