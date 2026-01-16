#!/bin/bash
# Workflow Orchestrator - Install Script
# Run with: curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash

echo "Installing Workflow Orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git

echo "Installing review dependencies..."
pip install -q aider-chat 2>/dev/null || echo "Note: aider-chat install skipped (optional)"

echo "Enabling automatic updates for this repo..."
orchestrator setup

echo "Adding orchestrator instructions to CLAUDE.md..."
ORCHESTRATOR_SECTION='
## Workflow Orchestrator

This project uses **workflow-orchestrator** (we call it "orchestrator" for short).

### Quick Reference
- `orchestrator status` - Check current workflow state
- `orchestrator start "task"` - Start a new workflow
- `orchestrator advance` - Move to next phase

### Installation (for fresh environments like Claude Code Web)
```bash
curl -sSL https://raw.githubusercontent.com/keevaspeyer10x/workflow-orchestrator/main/install.sh | bash
```

### Usage
Say things like:
- "Use orchestrator to implement feature X"
- "Start a workflow for fixing the bug"
- "What'\''s the orchestrator status?"

For full documentation, see: https://github.com/keevaspeyer10x/workflow-orchestrator
'

# Add to CLAUDE.md if not already present
if [ -f "CLAUDE.md" ]; then
    if ! grep -q "workflow-orchestrator" CLAUDE.md; then
        echo "$ORCHESTRATOR_SECTION" >> CLAUDE.md
        echo "  Added orchestrator section to existing CLAUDE.md"
    else
        echo "  CLAUDE.md already has orchestrator instructions"
    fi
else
    echo "$ORCHESTRATOR_SECTION" > CLAUDE.md
    echo "  Created CLAUDE.md with orchestrator instructions"
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
