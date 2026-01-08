#!/bin/bash
# Encrypts your SOPS AGE key with a password for safe storage in the repo
# Usage: ./scripts/encrypt-sops-key.sh
#
# This creates .manus/keys/age.key.enc which can be safely committed.
# To decrypt, set SOPS_KEY_PASSWORD env var when starting Claude Code Web.

set -e

KEY_FILE=".manus/keys/age.key.enc"

echo "SOPS AGE Key Encryption Tool"
echo "============================"
echo ""
echo "This will encrypt your AGE key so it can be stored in the repo."
echo "You'll need to remember the password to decrypt it in future sessions."
echo ""

# Read AGE key
read -sp "Enter your AGE secret key: " AGE_KEY
echo ""

# Validate it looks like an AGE key
if [[ ! "$AGE_KEY" =~ ^AGE-SECRET-KEY- ]]; then
    echo "Error: That doesn't look like an AGE secret key (should start with AGE-SECRET-KEY-)"
    exit 1
fi

# Read password (twice for confirmation)
read -sp "Enter encryption password: " PASSWORD
echo ""
read -sp "Confirm password: " PASSWORD2
echo ""

if [ "$PASSWORD" != "$PASSWORD2" ]; then
    echo "Error: Passwords don't match"
    exit 1
fi

if [ ${#PASSWORD} -lt 8 ]; then
    echo "Error: Password should be at least 8 characters"
    exit 1
fi

# Encrypt
mkdir -p "$(dirname "$KEY_FILE")"
echo "$AGE_KEY" | openssl enc -aes-256-cbc -pbkdf2 -salt -out "$KEY_FILE" -pass "pass:$PASSWORD"

echo ""
echo "Success! Encrypted key saved to $KEY_FILE"
echo ""
echo "To use in Claude Code Web:"
echo "  1. Commit and push this file"
echo "  2. Set SOPS_KEY_PASSWORD='your-password' when starting the task"
echo "  3. The SessionStart hook will automatically decrypt and load the key"
