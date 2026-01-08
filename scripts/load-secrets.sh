#!/bin/bash
# Load secrets from SOPS-encrypted file
# Usage: source ./scripts/load-secrets.sh

# Set the age key file location
export SOPS_AGE_KEY_FILE=/home/keeva/.config/sops/age/keys.txt

# Check if sops is available
SOPS_BIN="${HOME}/.local/bin/sops"
if [ ! -f "$SOPS_BIN" ]; then
    echo "Error: sops not found at $SOPS_BIN"
    return 1 2>/dev/null || exit 1
fi

# Check if secrets file exists
SECRETS_FILE="${HOME}/workflow-orchestrator/secrets.enc.yaml"
if [ ! -f "$SECRETS_FILE" ]; then
    echo "Error: Encrypted secrets file not found at $SECRETS_FILE"
    return 1 2>/dev/null || exit 1
fi

# Decrypt and export secrets
export GEMINI_API_KEY=$($SOPS_BIN -d "$SECRETS_FILE" | grep gemini_api_key | cut -d: -f2 | tr -d ' ')
export OPENROUTER_API_KEY=$($SOPS_BIN -d "$SECRETS_FILE" | grep openrouter_api_key | cut -d: -f2 | tr -d ' ')
export OPENAI_API_KEY=$($SOPS_BIN -d "$SECRETS_FILE" | grep openai_api_key | cut -d: -f2 | tr -d ' ')
export XAI_API_KEY=$($SOPS_BIN -d "$SECRETS_FILE" | grep grok_api_key | cut -d: -f2 | tr -d ' ')

echo "Secrets loaded successfully"
echo "  GEMINI_API_KEY: ${GEMINI_API_KEY:0:10}..."
echo "  OPENROUTER_API_KEY: ${OPENROUTER_API_KEY:0:10}..."
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:10}..."
echo "  XAI_API_KEY: ${XAI_API_KEY:0:10}..."
