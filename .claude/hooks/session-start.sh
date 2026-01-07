#!/bin/bash
# Workflow Orchestrator Session Start Hook
# - Auto-installs/updates the orchestrator
# - Loads SOPS AGE key from encrypted storage

set -e

# Get the project directory (where this hook lives)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$PROJECT_DIR"

echo "=== Workflow Orchestrator Session Start ==="

# 1. Update orchestrator
echo "Checking workflow orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git 2>/dev/null || true

# 2. Load SOPS AGE key if available
KEY_FILE=".manus/keys/age.key.enc"

if [ -f "$KEY_FILE" ]; then
    if [ -n "$SOPS_KEY_PASSWORD" ]; then
        echo "Decrypting SOPS AGE key..."
        AGE_KEY=$(openssl enc -aes-256-cbc -pbkdf2 -d -in "$KEY_FILE" -pass "pass:$SOPS_KEY_PASSWORD" 2>/dev/null) || {
            echo "Warning: Failed to decrypt SOPS key (wrong password?)"
            AGE_KEY=""
        }

        if [ -n "$AGE_KEY" ]; then
            # Export to CLAUDE_ENV_FILE so it's available in subsequent commands
            if [ -n "$CLAUDE_ENV_FILE" ]; then
                echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
                echo "SOPS AGE key loaded successfully"
            else
                # Fallback: just export for this session
                export SOPS_AGE_KEY="$AGE_KEY"
                echo "SOPS AGE key loaded (direct export)"
            fi
        fi
    else
        echo "Note: Encrypted SOPS key found but SOPS_KEY_PASSWORD not set"
        echo "      Set SOPS_KEY_PASSWORD env var to enable automatic decryption"
    fi
elif [ -n "$SOPS_AGE_KEY" ]; then
    echo "SOPS AGE key already set in environment"
else
    echo "Note: No SOPS key configured (optional - needed for encrypted secrets)"
fi

# 3. Check for local unencrypted key (for desktop use)
LOCAL_KEY=".manus/keys/age.key"
if [ -f "$LOCAL_KEY" ] && [ -z "$SOPS_AGE_KEY" ]; then
    if [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$(cat "$LOCAL_KEY")'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded from local file"
    fi
fi

echo "=== Session Start Complete ==="
