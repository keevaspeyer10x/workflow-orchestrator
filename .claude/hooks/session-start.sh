#!/bin/bash
# Keeva Devtools - Update All Tools Hook
# This hook runs at Claude Code session start to:
# - Auto-install/update devtools (orchestrator, multiminds, ai-tool-bridge)
# - Load secrets from encrypted files
#
# Location: keeva-devtools/.claude/hooks/update-all-devtools.sh
# Note: "orchestrator" refers to the workflow process (orchestrator start/finish),
#       not this hook or its location.

set -e

# Get the project directory (where this hook lives)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$PROJECT_DIR"

echo "=== Keeva Devtools Session Start ==="

# 1. Auto-cleanup stale worktrees (older than 7 days)
if command -v orchestrator &> /dev/null; then
    echo "Cleaning up stale worktrees..."
    orchestrator doctor --cleanup --older-than 7 2>/dev/null || true
fi

# 2. Update all devtools
echo "Checking workflow orchestrator..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git 2>/dev/null || true

echo "Checking ai-tool-bridge..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/ai-tool-bridge.git 2>/dev/null || true

echo "Checking multiminds..."
pip install -q --upgrade multiminds 2>/dev/null || true

# 3. Install aider if not available (for Gemini reviews with repo context)
if ! command -v aider &> /dev/null; then
    echo "Installing aider-chat for reviews..."
    pip install -q aider-chat 2>/dev/null || echo "Note: aider-chat install skipped"
fi

# 4. Load secrets from simple encrypted file (preferred method)
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
    echo "Note: No simple secrets file found at $SECRETS_FILE"
    echo "      To set up simple encrypted secrets, run: orchestrator secrets init"
    echo "      Or use SOPS/AGE encryption (see secrets.enc.yaml support below)"
fi

# 5. Parse SOPS_KEY_PASSWORD from CLAUDE.md if not set in environment
if [ -z "$SOPS_KEY_PASSWORD" ] && [ -f "CLAUDE.md" ]; then
    # Look for uncommented: export SOPS_KEY_PASSWORD="..." or export SOPS_KEY_PASSWORD='...'
    # Must start with 'export' (not '#' or other comment chars)
    PARSED_PASSWORD=$(grep -oP '^\s*export\s+SOPS_KEY_PASSWORD\s*=\s*["\x27]\K[^"\x27]+' CLAUDE.md 2>/dev/null | head -1) || true
    if [ -n "$PARSED_PASSWORD" ]; then
        SOPS_KEY_PASSWORD="$PARSED_PASSWORD"
        echo "SOPS_KEY_PASSWORD loaded from CLAUDE.md"
    fi
fi

# 6. Load password-encrypted SOPS AGE key
# Priority: .claude/keys/ (repo, for Claude Code Web) > global config > legacy local
SOPS_KEY_LOADED=false
if [ -n "$SOPS_KEY_PASSWORD" ] && [ -z "$SOPS_AGE_KEY" ]; then
    # Try repo key first (persists in Claude Code Web)
    REPO_KEY=".claude/keys/age.key.enc"
    GLOBAL_KEY="$HOME/.config/workflow-orchestrator/keys/age.key.enc"
    LEGACY_KEY=".workflow-orchestrator/keys/age.key.enc"

    if [ -f "$REPO_KEY" ]; then
        AGE_KEY=$(echo "$SOPS_KEY_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in "$REPO_KEY" -pass stdin 2>/dev/null) || true
        if [ -n "$AGE_KEY" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
            echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
            echo "SOPS AGE key loaded from $REPO_KEY"
            SOPS_KEY_LOADED=true
        else
            echo "Warning: Failed to decrypt $REPO_KEY (wrong SOPS_KEY_PASSWORD?)"
        fi
    elif [ -f "$GLOBAL_KEY" ]; then
        AGE_KEY=$(echo "$SOPS_KEY_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in "$GLOBAL_KEY" -pass stdin 2>/dev/null) || true
        if [ -n "$AGE_KEY" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
            echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
            echo "SOPS AGE key loaded from global config"
            SOPS_KEY_LOADED=true
        else
            echo "Warning: Failed to decrypt $GLOBAL_KEY (wrong SOPS_KEY_PASSWORD?)"
        fi
    elif [ -f "$LEGACY_KEY" ]; then
        AGE_KEY=$(echo "$SOPS_KEY_PASSWORD" | openssl enc -aes-256-cbc -pbkdf2 -d -in "$LEGACY_KEY" -pass stdin 2>/dev/null) || true
        if [ -n "$AGE_KEY" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
            echo "export SOPS_AGE_KEY='$AGE_KEY'" >> "$CLAUDE_ENV_FILE"
            echo "SOPS AGE key loaded from legacy location"
            SOPS_KEY_LOADED=true
        else
            echo "Warning: Failed to decrypt $LEGACY_KEY (wrong SOPS_KEY_PASSWORD?)"
        fi
    else
        echo "Note: SOPS_KEY_PASSWORD set but no encrypted key file found"
        echo "      Run bootstrap.sh with SOPS_AGE_KEY to create one"
    fi
elif [ -n "$SOPS_KEY_PASSWORD" ] && [ -n "$SOPS_AGE_KEY" ]; then
    SOPS_KEY_LOADED=true
fi

# 7. Check for unencrypted key (for desktop/local use - NOT recommended for Claude Code Web)
if [ -z "$SOPS_AGE_KEY" ]; then
    GLOBAL_PLAIN="$HOME/.config/workflow-orchestrator/keys/age.key"
    LEGACY_PLAIN=".workflow-orchestrator/keys/age.key"

    if [ -f "$GLOBAL_PLAIN" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$(cat "$GLOBAL_PLAIN")'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded from global unencrypted key (desktop mode)"
    elif [ -f "$LEGACY_PLAIN" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
        echo "export SOPS_AGE_KEY='$(cat "$LEGACY_PLAIN")'" >> "$CLAUDE_ENV_FILE"
        echo "SOPS AGE key loaded from legacy unencrypted key"
    fi
fi

# 8. Load secrets from SOPS file if available (skip ANTHROPIC_API_KEY if Claude is authenticated)
if [ -f "secrets.enc.yaml" ]; then
    if ! command -v sops &> /dev/null; then
        echo ""
        echo "Warning: secrets.enc.yaml found but SOPS not installed"
        echo "         Run bootstrap.sh to install SOPS"
    elif [ -z "$SOPS_AGE_KEY" ]; then
        echo ""
        echo "Warning: secrets.enc.yaml found but no AGE key configured"
        echo "         minds and other tools will fail without API keys!"
        echo ""
        echo "         Quick fix - add to CLAUDE.md:"
        echo "           export SOPS_KEY_PASSWORD=\"your-password\""
        echo ""
        echo "         First-time setup:"
        echo "           export SOPS_AGE_KEY='AGE-SECRET-KEY-1...'"
        echo "           export SOPS_KEY_PASSWORD='your-password'"
        echo "           ./scripts/bootstrap.sh"
    else
        # Check if Claude is authenticated (claude.ai token exists)
        CLAUDE_AUTHENTICATED=false
        if [ -f "$HOME/.claude/.credentials.json" ]; then
            CLAUDE_AUTHENTICATED=true
        fi

        # Decrypt and load secrets
        SOPS_SECRETS=$(sops -d secrets.enc.yaml 2>/dev/null) || true
        if [ -n "$SOPS_SECRETS" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
            SECRET_COUNT=0
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
                    SECRET_COUNT=$((SECRET_COUNT + 1))
                fi
            done <<< "$SOPS_SECRETS"
            echo "SOPS secrets loaded ($SECRET_COUNT API keys)"
        else
            echo "Warning: Failed to decrypt secrets.enc.yaml"
            echo "         Check that your AGE key matches the encryption key"
        fi
    fi
fi

echo "=== Session Start Complete ==="
