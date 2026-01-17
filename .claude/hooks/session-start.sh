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

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
esac

# 1. Install SOPS if not available (needed for secrets)
if ! command -v sops &> /dev/null; then
    echo "Installing SOPS..."
    SOPS_VERSION="3.8.1"
    SOPS_URL="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.${OS}.${ARCH}"
    mkdir -p "$HOME/.local/bin"
    curl -sSL "$SOPS_URL" -o "$HOME/.local/bin/sops" 2>/dev/null && chmod +x "$HOME/.local/bin/sops"
    export PATH="$HOME/.local/bin:$PATH"
    command -v sops &>/dev/null && echo "  SOPS installed" || echo "  SOPS install failed"
fi

# 2. Install AGE if not available (needed for SOPS decryption)
if ! command -v age &> /dev/null; then
    echo "Installing AGE..."
    AGE_VERSION="1.1.1"
    AGE_URL="https://github.com/FiloSottile/age/releases/download/v${AGE_VERSION}/age-v${AGE_VERSION}-${OS}-${ARCH}.tar.gz"
    mkdir -p "$HOME/.local/bin"
    TMPDIR=$(mktemp -d)
    curl -sSL "$AGE_URL" -o "$TMPDIR/age.tar.gz" 2>/dev/null && \
        tar -xzf "$TMPDIR/age.tar.gz" -C "$TMPDIR" && \
        cp "$TMPDIR/age/age" "$TMPDIR/age/age-keygen" "$HOME/.local/bin/" && \
        chmod +x "$HOME/.local/bin/age" "$HOME/.local/bin/age-keygen"
    rm -rf "$TMPDIR"
    export PATH="$HOME/.local/bin:$PATH"
    command -v age &>/dev/null && echo "  AGE installed" || echo "  AGE install failed"
fi

# 3. Fix cffi issue (known problem in Claude Code Web)
echo "Checking cffi..."
pip install -q cffi --force-reinstall 2>/dev/null || true

# 4. Install/update devtools
echo "Installing devtools..."
pip install -q --upgrade git+https://github.com/keevaspeyer10x/workflow-orchestrator.git 2>/dev/null || true
pip install -q --upgrade git+https://github.com/keevaspeyer10x/multiminds.git 2>/dev/null || true
pip install -q --upgrade git+https://github.com/keevaspeyer10x/ai-tool-bridge.git 2>/dev/null || true

# Verify installations
command -v orchestrator &>/dev/null && echo "  orchestrator ready" || echo "  orchestrator not found"
command -v minds &>/dev/null && echo "  minds ready" || echo "  minds not found"

# 5. Auto-cleanup stale worktrees (older than 7 days)
if command -v orchestrator &> /dev/null; then
    orchestrator doctor --cleanup --older-than 7 2>/dev/null || true
fi

# 6. Load secrets from simple encrypted file (preferred method)
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

            # Install and authenticate gh CLI if GITHUB_TOKEN is available
            if [ -n "$GITHUB_TOKEN" ]; then
                # Install gh CLI if not available
                if ! command -v gh &> /dev/null; then
                    echo "Installing GitHub CLI..."
                    GH_VERSION="2.63.2"
                    GH_URL="https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz"
                    TMPDIR=$(mktemp -d)
                    curl -sSL "$GH_URL" -o "$TMPDIR/gh.tar.gz" 2>/dev/null && \
                        tar -xzf "$TMPDIR/gh.tar.gz" -C "$TMPDIR" && \
                        cp "$TMPDIR/gh_${GH_VERSION}_linux_amd64/bin/gh" "$HOME/.local/bin/" && \
                        chmod +x "$HOME/.local/bin/gh"
                    rm -rf "$TMPDIR"
                    export PATH="$HOME/.local/bin:$PATH"
                fi

                # Authenticate gh CLI
                if command -v gh &> /dev/null; then
                    echo "$GITHUB_TOKEN" | gh auth login --with-token 2>/dev/null && \
                        echo "  gh CLI authenticated" || echo "  gh CLI auth failed"
                fi
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
