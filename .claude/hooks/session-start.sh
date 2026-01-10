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

# 2. Install aider if not available (for Gemini reviews with repo context)
if ! command -v aider &> /dev/null; then
    echo "Installing aider-chat for reviews..."
    pip install -q aider-chat 2>/dev/null || echo "Note: aider-chat install skipped"
fi

# 3. Load secrets from simple encrypted file (preferred method)
SECRETS_FILE=".secrets.enc"

if [ -f "$SECRETS_FILE" ]; then
    if [ -n "$SECRETS_PASSWORD" ]; then
        echo "Decrypting secrets..."
        # Pass password via stdin for security (not visible in process list)
        SECRETS_YAML=$(echo "$SECRETS_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in "$SECRETS_FILE" -pass stdin 2>/dev/null) || {
            echo "Warning: Failed to decrypt secrets (wrong password?)"
            SECRETS_YAML=""
        }

        if [ -n "$SECRETS_YAML" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
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
                    echo "export $key='$value'" >> "$CLAUDE_ENV_FILE"
                fi
            done <<< "$SECRETS_YAML"
            echo "Secrets loaded successfully"

            # Auto-login to Codex CLI if OpenAI key is available
            if command -v codex &> /dev/null && [ -n "$OPENAI_API_KEY" ]; then
                echo "$OPENAI_API_KEY" | codex login --with-api-key 2>/dev/null && \
                    echo "Codex CLI logged in" || true
            fi
        fi
    else
        echo "Note: Encrypted secrets found but SECRETS_PASSWORD not set"
        echo "      Set SECRETS_PASSWORD env var to enable automatic decryption"
    fi
else
    echo "Note: No secrets file found at $SECRETS_FILE"
    echo "      Run 'orchestrator secrets init' to set up secrets"
fi

# 4. Load password-encrypted SOPS AGE key (global first, then local)
if [ -n "$SOPS_KEY_PASSWORD" ] && [ -z "$SOPS_AGE_KEY" ]; then
    # Try global encrypted key first
    GLOBAL_KEY="$HOME/.config/workflow-orchestrator/keys/age.key.enc"
    if [ -f "$GLOBAL_KEY" ]; then
        AGE_KEY=$(echo "$SOPS_KEY_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in "$GLOBAL_KEY" -pass stdin 2>/dev/null) || true
        if [ -n "$AGE_KEY" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
            echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
            echo "SOPS AGE key loaded from global password-protected key"
        fi
    # Fall back to local encrypted key
    elif [ -f ".workflow-orchestrator/keys/age.key.enc" ]; then
        AGE_KEY=$(echo "$SOPS_KEY_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in ".workflow-orchestrator/keys/age.key.enc" -pass stdin 2>/dev/null) || true
        if [ -n "$AGE_KEY" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
            echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
            echo "SOPS AGE key loaded from local password-protected key"
        fi
    fi
fi

# 5. Check for unencrypted key (global first, then local - for desktop use)
if [ -z "$SOPS_AGE_KEY" ]; then
    # Try global unencrypted key first
    GLOBAL_PLAIN="$HOME/.config/workflow-orchestrator/keys/age.key"
    if [ -f "$GLOBAL_PLAIN" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$(cat "$GLOBAL_PLAIN")'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded from global unencrypted key"
    # Fall back to local unencrypted key
    elif [ -f ".workflow-orchestrator/keys/age.key" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$(cat ".workflow-orchestrator/keys/age.key")'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded from local unencrypted key"
    fi
fi

# 6. Load secrets from SOPS file if available (skip ANTHROPIC_API_KEY if Claude is authenticated)
if [ -n "$SOPS_AGE_KEY" ] && [ -f "secrets.enc.yaml" ] && command -v sops &> /dev/null; then
    # Check if Claude is authenticated (claude.ai token exists)
    CLAUDE_AUTHENTICATED=false
    if [ -f "$HOME/.claude/.credentials.json" ]; then
        CLAUDE_AUTHENTICATED=true
    fi

    # Decrypt and load secrets
    SOPS_SECRETS=$(sops -d secrets.enc.yaml 2>/dev/null) || true
    if [ -n "$SOPS_SECRETS" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
        while IFS=': ' read -r key value; do
            # Skip empty lines and comments
            [[ -z "$key" || "$key" =~ ^# ]] && continue

            # Skip ANTHROPIC_API_KEY if Claude is authenticated
            if [ "$CLAUDE_AUTHENTICATED" = true ] && ([[ "$key" =~ ^anthropic_api_key$ ]] || [[ "$key" =~ ^ANTHROPIC_API_KEY$ ]]); then
                echo "Skipping $key (Claude authenticated via claude.ai)"
                continue
            fi

            # Remove quotes if present
            value="${value%\"}"
            value="${value#\"}"
            value="${value%\'}"
            value="${value#\'}"
            if [ -n "$key" ] && [ -n "$value" ]; then
                # Export with uppercase key name
                KEY_UPPER=$(echo "$key" | tr '[:lower:]' '[:upper:]')
                echo "export $KEY_UPPER='$value'" >> "$CLAUDE_ENV_FILE"
            fi
        done <<< "$SOPS_SECRETS"
        echo "SOPS secrets loaded (excluding ANTHROPIC_API_KEY)"
    fi
fi

echo "=== Session Start Complete ==="
