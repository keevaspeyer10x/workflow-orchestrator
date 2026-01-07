#!/bin/bash
# Workflow Orchestrator Session Start Hook
# - Auto-installs/updates the orchestrator
# - Loads secrets from password-encrypted file

set -e

# Get the project directory (where this hook lives)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$PROJECT_DIR"

echo "=== Workflow Orchestrator Session Start ==="

# 1. Update orchestrator
echo "Checking workflow orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git 2>/dev/null || true

# 2. Load secrets from simple encrypted file (preferred method)
SECRETS_FILE=".manus/secrets.enc"

if [ -f "$SECRETS_FILE" ]; then
    if [ -n "$SECRETS_PASSWORD" ]; then
        echo "Decrypting secrets..."
        SECRETS_YAML=$(openssl enc -aes-256-cbc -pbkdf2 -d -in "$SECRETS_FILE" -pass "pass:$SECRETS_PASSWORD" 2>/dev/null) || {
            echo "Warning: Failed to decrypt secrets (wrong password?)"
            SECRETS_YAML=""
        }

        if [ -n "$SECRETS_YAML" ]; then
            # Parse YAML and export each key
            # Simple parsing for KEY: value format
            while IFS=': ' read -r key value; do
                # Skip empty lines and comments
                [[ -z "$key" || "$key" =~ ^# ]] && continue
                # Remove quotes if present
                value="${value%\"}"
                value="${value#\"}"
                value="${value%\'}"
                value="${value#\'}"
                if [ -n "$key" ] && [ -n "$value" ]; then
                    if [ -n "$CLAUDE_ENV_FILE" ]; then
                        echo "export $key='$value'" >> "$CLAUDE_ENV_FILE"
                    fi
                fi
            done <<< "$SECRETS_YAML"
            echo "Secrets loaded successfully"
        fi
    else
        echo "Note: Encrypted secrets found but SECRETS_PASSWORD not set"
        echo "      Set SECRETS_PASSWORD env var to enable automatic decryption"
    fi
else
    echo "Note: No secrets file found at $SECRETS_FILE"
    echo "      Run 'orchestrator secrets init' to set up secrets"
fi

# 3. Legacy: Load SOPS AGE key if available (for backwards compatibility)
KEY_FILE=".manus/keys/age.key.enc"
if [ -f "$KEY_FILE" ] && [ -n "$SOPS_KEY_PASSWORD" ] && [ -z "$SOPS_AGE_KEY" ]; then
    AGE_KEY=$(openssl enc -aes-256-cbc -pbkdf2 -d -in "$KEY_FILE" -pass "pass:$SOPS_KEY_PASSWORD" 2>/dev/null) || true
    if [ -n "$AGE_KEY" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded (legacy)"
    fi
fi

# 4. Check for local unencrypted key (for desktop use)
LOCAL_KEY=".manus/keys/age.key"
if [ -f "$LOCAL_KEY" ] && [ -z "$SOPS_AGE_KEY" ]; then
    if [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$(cat "$LOCAL_KEY")'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded from local file"
    fi
fi

echo "=== Session Start Complete ==="
