#!/bin/bash
# Workflow Orchestrator - Install Script
# Run with: curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash

echo "Installing Workflow Orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

echo "Installing review dependencies..."
pip install -q aider-chat 2>/dev/null || echo "Note: aider-chat install skipped (optional)"

echo "Enabling automatic updates for this repo..."
orchestrator setup

echo "Adding devtools instructions to CLAUDE.md..."
DEVTOOLS_SECTION='
## AI Development Tools

This project uses **keeva-devtools** for AI-assisted development.

### One-Command Install (Recommended)
For fresh environments like Claude Code Web, install all tools at once:
```bash
curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/keeva-devtools/main/scripts/bootstrap.sh | bash
```

This installs:
- **orchestrator** - Development workflow management (we call it "orchestrator")
- **minds** - Multi-model AI queries (we call it "minds")
- **ai-tool-bridge** - MCP server for tool discovery

### Quick Reference

**Orchestrator:**
- `orchestrator status` - Check current workflow state
- `orchestrator start "task"` - Start a new workflow
- `orchestrator advance` - Move to next phase

**Minds:**
- `minds ask "question"` - Query multiple AI models
- `minds review` - Multi-model code review
- `minds status` - Check configuration

### Lazy Installation Pattern
In ephemeral environments where tools do not persist, use just-in-time installation:
```bash
# Install orchestrator if missing
if ! command -v orchestrator &>/dev/null; then
    pip install -q git+https://github.com/keevaspeyer10x/workflow-orchestrator.git
fi

# Install minds if missing
if ! command -v minds &>/dev/null; then
    pip install -q git+https://github.com/keevaspeyer10x/multiminds.git
fi
```

### Usage
Say things like:
- "Use orchestrator to implement feature X"
- "Start a workflow for fixing the bug"
- "Use minds to review this code"
- "Ask minds about the best approach"

For full documentation:
- Orchestrator: https://github.com/keevaspeyer10x/workflow-orchestrator
- Minds: https://github.com/keevaspeyer10x/multiminds
- DevTools: https://github.com/keevaspeyer10x/keeva-devtools
'

# Add to CLAUDE.md if not already present
if [ -f "CLAUDE.md" ]; then
    if ! grep -q "keeva-devtools" CLAUDE.md; then
        # Remove old orchestrator-only section if present
        if grep -q "## Workflow Orchestrator" CLAUDE.md; then
            # Create temp file without the old section
            sed '/^## Workflow Orchestrator$/,/^## /{ /^## Workflow Orchestrator$/d; /^## /!d; }' CLAUDE.md > CLAUDE.md.tmp
            mv CLAUDE.md.tmp CLAUDE.md
        fi
        echo "$DEVTOOLS_SECTION" >> CLAUDE.md
        echo "  Added devtools section to existing CLAUDE.md"
    else
        echo "  CLAUDE.md already has devtools instructions"
    fi
else
    echo "$DEVTOOLS_SECTION" > CLAUDE.md
    echo "  Created CLAUDE.md with devtools instructions"
fi

echo ""
echo "============================================================"
echo "IMPORTANT: API Keys for External Reviews"
echo "============================================================"
echo ""

# Check for API keys
MISSING_KEYS=""
[ -z "$GEMINI_API_KEY" ] && MISSING_KEYS="$MISSING_KEYS GEMINI_API_KEY"
[ -z "$OPENAI_API_KEY" ] && MISSING_KEYS="$MISSING_KEYS OPENAI_API_KEY"
[ -z "$OPENROUTER_API_KEY" ] && MISSING_KEYS="$MISSING_KEYS OPENROUTER_API_KEY"

if [ -n "$MISSING_KEYS" ]; then
    echo "WARNING: Missing API keys:$MISSING_KEYS"
    echo ""
    echo "External model reviews REQUIRE these keys to be set."
    echo "Load secrets with:"
    echo '  eval "$(sops -d secrets.enc.yaml | sed '\''s/: /=/'\'' | sed '\''s/^/export /'\'')"'
    echo ""
    echo "Or with direnv:"
    echo "  direnv allow"
    echo ""
else
    echo "All required API keys are loaded."
fi

echo "============================================================"
echo ""
echo "Ready! You can now say things like:"
echo "  'Use orchestrator to build a login page'"
echo "  'Start a workflow for fixing the search bug'"
echo "  'What's the orchestrator status?'"
echo "  'Use minds to review this code'"
echo ""
